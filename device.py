"""
talks to the iphone over usb via pymobiledevice3 (11.x, which is all async now).

iOS 17+ needs a "tunnel" running with admin rights before any developer service
works. we start it through the OS's native elevation prompt so you never open a
terminal: the mac password dialog (osascript) on macOS, the UAC prompt on Windows.
if that ever acts up, run it yourself - see the README.

the rest of the app is plain sync code, so this file runs its own asyncio loop
on a background thread and hands out normal blocking methods.
"""

import asyncio
import json
import os
import plistlib
import shlex
import site
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import AsyncExitStack
from urllib.request import urlopen

# lazy-ish import so the app still opens (in a look-around state) if the lib is missing
try:
    from pymobiledevice3.tunneld.api import get_tunneld_devices
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
    HAVE_PMD = True
    IMPORT_ERROR = ""
except Exception as e:
    HAVE_PMD = False
    IMPORT_ERROR = f"{type(e).__name__}: {e}"
    print("[decoy] pymobiledevice3 failed to import:", IMPORT_ERROR, file=sys.stderr)

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

TUNNELD_URL = "http://127.0.0.1:49151/"
TUNNEL_PORT = 49151
# keep the log somewhere writable on every OS (/tmp on unix, %TEMP% on windows)
TUNNEL_LOG = os.path.join(tempfile.gettempdir(), "decoy-tunneld.log")
TUNNEL_WAIT = 40  # seconds to wait for the tunnel before giving up

# background service so the password/UAC prompt is only needed once (at install).
# mac: a launchd daemon. windows: a Scheduled Task that runs at logon, elevated.
DAEMON_LABEL = "com.decoy.tunneld"
DAEMON_PLIST = f"/Library/LaunchDaemons/{DAEMON_LABEL}.plist"
WIN_TASK_NAME = "DecoyTunnel"
# the [t] trick stops pkill from matching the shell that's running this very command.
# two patterns: running from source (python -m pymobiledevice3 ...) and the packaged app (Decoy --tunneld)
KILL_TUNNELD = "pkill -f 'pymobiledevice3 remote [t]unneld|Decoy.*--[t]unneld'"

# true when running as the packaged app (pyinstaller sets sys.frozen)
FROZEN = getattr(sys, "frozen", False)


def tunnel_argv():
    # a packaged app has no separate python to call, so the app binary itself
    # runs the tunnel when started with --tunneld (see main.py)
    if FROZEN:
        return [sys.executable, "--tunneld"]
    return [sys.executable, "-m", "pymobiledevice3", "remote", "tunneld"]


class DeviceError(Exception):
    pass


# ---------- windows elevation helpers (ctypes, loaded only on windows) ----------

def _win_shell_execute(params, wait):
    """
    launch cmd.exe elevated (triggers the UAC prompt) with the given parameter
    string. when wait is True we block for it to finish and return its exit code
    (used for the quick install/remove scripts); when False we fire and forget
    (used for the long-running tunnel) and return None.
    """
    import ctypes
    from ctypes import wintypes

    SEE_MASK_NOCLOSEPROCESS = 0x40
    SW_HIDE = 0
    ERROR_CANCELLED = 1223

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", ctypes.c_ulong),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIcon", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"          # the verb that asks for admin -> UAC prompt
    info.lpFile = "cmd.exe"
    info.lpParameters = params
    info.nShow = SW_HIDE

    if not shell32.ShellExecuteExW(ctypes.byref(info)) or not info.hProcess:
        err = kernel32.GetLastError()
        if err == ERROR_CANCELLED:
            raise DeviceError("admin prompt was cancelled")
        raise DeviceError(f"couldn't elevate (windows error {err})")

    if not wait:
        kernel32.CloseHandle(info.hProcess)
        return None

    kernel32.WaitForSingleObject(info.hProcess, 60000)
    code = wintypes.DWORD()
    kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    kernel32.CloseHandle(info.hProcess)
    return code.value


def _win_tunnel_cmd():
    # the command the elevated cmd.exe runs: start the tunnel, send all output to
    # the log file. from source we also pass our site-packages along, since an
    # elevated shell might not see a --user pip install.
    inner = subprocess.list2cmdline(tunnel_argv())
    if not FROZEN:
        inner = f'set "PYTHONPATH={site.getusersitepackages()}" && {inner}'
    return f'{inner} > "{TUNNEL_LOG}" 2>&1'


# kills whatever is listening on the tunnel port (used before (re)installing the service)
_WIN_KILL_PORT = (
    "powershell -NoProfile -Command "
    "\"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | "
    "ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}\""
).format(port=TUNNEL_PORT)


class DeviceManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()

        self._stack = None
        self._loc = None
        self.info = {}

    # ---- plumbing ----

    def _run(self, coro, timeout=20):
        # run a coroutine on the background loop and wait for it
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    @property
    def ready(self):
        return self._loc is not None

    def status(self):
        if not HAVE_PMD:
            return {"state": "no_lib", "detail": IMPORT_ERROR, "info": {}}
        if self.ready:
            return {"state": "connected", "detail": "", "info": self.info}
        return {"state": "disconnected", "detail": "", "info": {}}

    # ---- tunnel ----

    def _tunnel_up(self):
        # tunneld answers plain http on its port, cheap way to see if it's alive
        try:
            urlopen(TUNNELD_URL, timeout=1).read()
            return True
        except Exception:
            return False

    def _tunnel_log_tail(self, n=15):
        try:
            with open(TUNNEL_LOG, errors="replace") as f:
                return f.read().splitlines()[-n:]
        except Exception:
            return []

    def _spawn_tunnel(self):
        # launch the tunnel elevated, detached, logging to TUNNEL_LOG. the native
        # prompt (mac password / windows UAC) shows here.
        if IS_WIN:
            params = f'/c "{_win_tunnel_cmd()}"'
            print("[decoy] starting tunnel (windows UAC prompt)...")
            _win_shell_execute(params, wait=False)
            return

        # mac: root doesn't see our user site-packages, so pass the path along or
        # `-m pymobiledevice3` dies instantly when pip installed with --user.
        # no nohup here: on macOS it dies with "can't detach from console" when
        # there's no terminal. redirecting all three fds + & detaches fine on its own.
        env = "" if FROZEN else f"PYTHONPATH={shlex.quote(site.getusersitepackages())} "
        argv = " ".join(shlex.quote(a) for a in tunnel_argv())
        cmd = f"{env}{argv} > {TUNNEL_LOG} 2>&1 < /dev/null &"
        script = f"do shell script {json.dumps(cmd)} with administrator privileges"
        print("[decoy] starting tunnel (mac password prompt)...")
        try:
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            err = (e.stderr or b"").decode(errors="replace").strip()
            print("[decoy] osascript failed:", err, file=sys.stderr)
            raise DeviceError("couldn't start the tunnel: " + (err or "password prompt cancelled"))

    def _start_tunnel(self):
        self._spawn_tunnel()

        # it can take a while to come up
        for _ in range(TUNNEL_WAIT * 2):
            if self._tunnel_up():
                print("[decoy] tunnel is up")
                return
            time.sleep(0.5)

        # gave up - dump the tunnel's own log so the reason shows in the Logs tab
        tail = self._tunnel_log_tail()
        print(f"[decoy] tunnel never answered. last lines of {TUNNEL_LOG}:", file=sys.stderr)
        for line in (tail or ["(log file is empty or missing)"]):
            print("[tunneld] " + line, file=sys.stderr)
        last = tail[-1] if tail else "log is empty"
        raise DeviceError(f"tunnel didn't come up. last log line: {last}")

    # ---- connect ----

    async def _open(self):
        devices = await get_tunneld_devices()
        if not devices:
            raise DeviceError("no iphone found - plug it in, unlock it, and approve the Trust / pairing prompt on the phone")
        rsd = devices[0]

        stack = AsyncExitStack()
        try:
            dvt = DvtProvider(rsd)
            await stack.enter_async_context(dvt)
            loc = LocationSimulation(dvt)
            await stack.enter_async_context(loc)
        except Exception:
            await stack.aclose()
            raise

        info = {"name": "iPhone", "ios": str(getattr(rsd, "product_version", "") or "")}
        try:
            name = await rsd.get_value(key="DeviceName")
            if name:
                info["name"] = str(name)
        except Exception:
            pass  # name is just cosmetic

        return stack, loc, info

    def connect(self):
        if not HAVE_PMD:
            raise DeviceError(f"device library failed to load: {IMPORT_ERROR}")

        with self._lock:
            if self.ready:
                return self.info

            if not self._tunnel_up():
                self._start_tunnel()

            try:
                self._stack, self._loc, self.info = self._run(self._open(), timeout=40)
            except DeviceError:
                raise
            except Exception as e:
                raise DeviceError(f"couldn't talk to the phone: {e}")
            return self.info

    # ---- the actual point of all this ----

    def set(self, lat, lon):
        if not self.ready:
            self.connect()
        with self._lock:
            try:
                self._run(self._loc.set(lat, lon), timeout=10)
            except Exception as e:
                # cable pulled / phone locked / tunnel died - reset so next try reconnects
                self._drop()
                raise DeviceError(f"lost the phone ({e}). replug it and tap the status chip")

    def clear(self):
        # hand control back to the phone's real gps
        if not self.ready:
            return
        with self._lock:
            try:
                self._run(self._loc.clear(), timeout=10)
            except Exception as e:
                self._drop()
                raise DeviceError(str(e))

    def _drop(self):
        # forget the connection without blowing up if it's already dead
        stack, self._stack, self._loc = self._stack, None, None
        self.info = {}
        if stack:
            try:
                self._run(stack.aclose(), timeout=5)
            except Exception:
                pass

    def close(self):
        with self._lock:
            if self._loc:
                try:
                    self._run(self._loc.clear(), timeout=5)
                except Exception:
                    pass
            self._drop()


# ---------- one-time background tunnel service ----------

def _admin_shell_mac(cmd):
    # run a shell command as root through the native mac password dialog
    script = f"do shell script {json.dumps(cmd)} with administrator privileges"
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode(errors="replace").strip()
        raise DeviceError(err or "password prompt cancelled")


def tunnel_service_installed():
    if IS_WIN:
        try:
            r = subprocess.run(
                ["schtasks", "/query", "/tn", WIN_TASK_NAME],
                capture_output=True,
            )
            return r.returncode == 0
        except Exception:
            return False
    return os.path.exists(DAEMON_PLIST)


def install_tunnel_service():
    if IS_WIN:
        _install_tunnel_service_win()
    else:
        _install_tunnel_service_mac()


def remove_tunnel_service():
    if IS_WIN:
        _remove_tunnel_service_win()
    else:
        _remove_tunnel_service_mac()


# ---- mac: launchd daemon ----

def _install_tunnel_service_mac():
    # launchd gives daemons a bare env; keep the user's HOME so pairing
    # records are the same ones the manual sudo run used
    env_vars = {"HOME": os.path.expanduser("~")}
    if not FROZEN:
        env_vars["PYTHONPATH"] = site.getusersitepackages()

    plist = {
        "Label": DAEMON_LABEL,
        "ProgramArguments": tunnel_argv(),
        "EnvironmentVariables": env_vars,
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": TUNNEL_LOG,
        "StandardErrorPath": TUNNEL_LOG,
    }
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".plist")
    tmp.write(plistlib.dumps(plist))
    tmp.close()

    q = shlex.quote
    cmd = (
        f"{KILL_TUNNELD}; "                                   # free port 49151 if a manual/auto tunnel is running
        f"cp {q(tmp.name)} {DAEMON_PLIST} && "
        f"chown root:wheel {DAEMON_PLIST} && chmod 644 {DAEMON_PLIST} && "
        f"(launchctl bootout system/{DAEMON_LABEL} 2>/dev/null; true) && "
        f"launchctl bootstrap system {DAEMON_PLIST}"
    )
    print("[decoy] installing background tunnel service...")
    _admin_shell_mac(cmd)
    print("[decoy] service installed")


def _remove_tunnel_service_mac():
    q = shlex.quote
    cmd = (
        f"(launchctl bootout system/{DAEMON_LABEL} 2>/dev/null; true); "
        f"rm -f {q(DAEMON_PLIST)}; "
        f"{KILL_TUNNELD}; true"
    )
    print("[decoy] removing background tunnel service...")
    _admin_shell_mac(cmd)
    print("[decoy] service removed")


# ---- windows: scheduled task (runs at logon, elevated, no password stored) ----

def _win_ps_register():
    # register the task via the ScheduledTasks module - it takes the executable and
    # args as separate fields, which dodges all the schtasks /tr quoting pain.
    # Interactive + Highest = runs at logon as you, elevated, no stored password.
    # (we only need the tunnel while you're logged in, so no need for S4U.)
    action_arg = f'/c "{_win_tunnel_cmd()}"'
    # single-quote for powershell; escape any embedded single quotes by doubling them
    exe = "cmd.exe"
    arg_ps = action_arg.replace("'", "''")
    user_ps = os.environ.get("USERNAME", "").replace("'", "''")
    return (
        f"$a = New-ScheduledTaskAction -Execute '{exe}' -Argument '{arg_ps}'; "
        "$t = New-ScheduledTaskTrigger -AtLogOn; "
        f"$p = New-ScheduledTaskPrincipal -UserId '{user_ps}' -LogonType Interactive -RunLevel Highest; "
        "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable; "
        f"Register-ScheduledTask -TaskName '{WIN_TASK_NAME}' -Action $a -Trigger $t -Principal $p -Settings $s -Force; "
        f"Start-ScheduledTask -TaskName '{WIN_TASK_NAME}'"
    )


def _install_tunnel_service_win():
    print("[decoy] installing background tunnel service (windows)...")
    # free the port first (in case a manual tunnel is running), then register + start
    script = f"{_WIN_KILL_PORT} & powershell -NoProfile -Command \"{_win_ps_register()}\""
    code = _win_shell_execute(f'/c "{script}"', wait=True)
    if code not in (0, None):
        raise DeviceError(f"couldn't install the service (exit {code}) - see the Logs tab")
    print("[decoy] service installed")


def _remove_tunnel_service_win():
    print("[decoy] removing background tunnel service (windows)...")
    unregister = (
        f"Unregister-ScheduledTask -TaskName '{WIN_TASK_NAME}' "
        "-Confirm:$false -ErrorAction SilentlyContinue"
    )
    script = f"powershell -NoProfile -Command \"{unregister}\" & {_WIN_KILL_PORT}"
    _win_shell_execute(f'/c "{script}"', wait=True)
    print("[decoy] service removed")

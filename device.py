"""
talks to the iphone over usb via pymobiledevice3 (11.x, which is all async now).

iOS 17+ needs a "tunnel" running as root before any developer service works.
we start it through the native mac password prompt (osascript) so you never
open a terminal. if that ever acts up, run it yourself - see the README.

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

TUNNELD_URL = "http://127.0.0.1:49151/"
TUNNEL_LOG = "/tmp/decoy-tunneld.log"
TUNNEL_WAIT = 40  # seconds to wait for the tunnel before giving up

# background service so the password is only needed once (at install)
DAEMON_LABEL = "com.decoy.tunneld"
DAEMON_PLIST = f"/Library/LaunchDaemons/{DAEMON_LABEL}.plist"
# the [t] trick stops pkill from matching the shell that's running this very command.
# two patterns: running from source (python -m pymobiledevice3 ...) and the packaged app (Decoy --tunneld)
KILL_TUNNELD = "pkill -f 'pymobiledevice3 remote [t]unneld|Decoy.*--[t]unneld'"

# true when running as the packaged .app (pyinstaller sets sys.frozen)
FROZEN = getattr(sys, "frozen", False)


def tunnel_argv():
    # a packaged app has no separate python to call, so the app binary itself
    # runs the tunnel when started with --tunneld (see main.py)
    if FROZEN:
        return [sys.executable, "--tunneld"]
    return [sys.executable, "-m", "pymobiledevice3", "remote", "tunneld"]


class DeviceError(Exception):
    pass


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

    def _start_tunnel(self):
        # root doesn't see our user site-packages, so pass the path along or
        # `-m pymobiledevice3` dies instantly when pip installed with --user
        # no nohup here: on macOS it dies with "can't detach from console" when
        # there's no terminal. redirecting all three fds + & detaches fine on its own.
        # (root also doesn't see our user site-packages when running from source,
        # so pass that path along. the packaged app doesn't need it.)
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

def _admin_shell(cmd):
    # run a shell command as root through the native mac password dialog
    script = f"do shell script {json.dumps(cmd)} with administrator privileges"
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode(errors="replace").strip()
        raise DeviceError(err or "password prompt cancelled")


def tunnel_service_installed():
    return os.path.exists(DAEMON_PLIST)


def install_tunnel_service():
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
    _admin_shell(cmd)
    print("[decoy] service installed")


def remove_tunnel_service():
    q = shlex.quote
    cmd = (
        f"(launchctl bootout system/{DAEMON_LABEL} 2>/dev/null; true); "
        f"rm -f {q(DAEMON_PLIST)}; "
        f"{KILL_TUNNELD}; true"
    )
    print("[decoy] removing background tunnel service...")
    _admin_shell(cmd)
    print("[decoy] service removed")

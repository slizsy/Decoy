"""
the object pywebview hands to javascript. every public method here is callable
from the ui as window.pywebview.api.<name>(...) and returns plain json.

pushes going the other way (travel progress, status changes) use
window.evaluate_js so the ui updates live without polling.
"""

import json
import threading

from device import DeviceManager, DeviceError
import device
from store import Spots
import geo
import logbuf

# speed presets in m/s. drive is ~30mph city-ish.
SPEEDS = {"walk": 1.4, "run": 3.3, "bike": 6.0, "drive": 13.4}
TICK = 0.3  # seconds between position updates while travelling


class Api:
    def __init__(self):
        self.dev = DeviceManager()
        self.spots = Spots()
        self._window = None
        self._travel_stop = threading.Event()
        self._travel_thread = None
        self._last = None  # last coords we set, so "save current" works

    def bind(self, window):
        self._window = window

    # ---- connection ----

    def status(self):
        return self.dev.status()

    # ---- one-time background tunnel service (so no password every connect) ----

    def tunnel_service_status(self):
        return {"installed": device.tunnel_service_installed()}

    def install_tunnel_service(self):
        try:
            device.install_tunnel_service()
            # give launchd a moment to bring it up
            import time
            for _ in range(30):
                if self.dev._tunnel_up():
                    break
                time.sleep(0.5)
            return {"ok": True, "up": self.dev._tunnel_up()}
        except DeviceError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": f"unexpected: {e}"}

    def remove_tunnel_service(self):
        try:
            device.remove_tunnel_service()
            return {"ok": True}
        except DeviceError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": f"unexpected: {e}"}

    def logs(self, since=0):
        # Logs tab polls this for new python-side lines
        return logbuf.get_logs(since)

    def connect(self):
        try:
            info = self.dev.connect()
            return {"ok": True, "info": info}
        except DeviceError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": f"unexpected: {e}"}

    # ---- single position ----

    def set_location(self, lat, lon):
        self._stop_travel()
        try:
            self.dev.set(lat, lon)
            self._last = (lat, lon)
            return {"ok": True}
        except DeviceError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": f"couldn't set position: {e}"}

    def jitter(self, lat, lon):
        # like set_location but quiet - used by the gps-drift wobble, fires often
        try:
            self.dev.set(lat, lon)
            self._last = (lat, lon)
            return {"ok": True}
        except Exception:
            return {"ok": False}

    def clear_location(self):
        self._stop_travel()
        try:
            self.dev.clear()
            self._last = None
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": f"couldn't restore gps: {e}"}

    # ---- spots ----

    def list_spots(self):
        return self.spots.all()

    def add_spot(self, name, lat, lon):
        return self.spots.add(name, lat, lon)

    def rename_spot(self, spot_id, name):
        self.spots.rename(spot_id, name)
        return {"ok": True}

    def remove_spot(self, spot_id):
        self.spots.remove(spot_id)
        return {"ok": True}

    def last_location(self):
        if self._last:
            return {"lat": self._last[0], "lon": self._last[1]}
        return None

    # ---- travel mode ----

    def start_travel(self, waypoints, mode):
        """waypoints: [[lat,lon],...]  mode: walk|run|bike|drive"""
        self._stop_travel()
        pts = [(w[0], w[1]) for w in waypoints]
        if len(pts) < 2:
            return {"ok": False, "error": "drop at least two points for a route"}

        speed = SPEEDS.get(mode, SPEEDS["walk"])
        self._travel_stop.clear()
        self._travel_thread = threading.Thread(
            target=self._run_travel, args=(pts, speed), daemon=True
        )
        self._travel_thread.start()
        return {"ok": True}

    def stop_travel(self):
        self._stop_travel()
        return {"ok": True}

    def _stop_travel(self):
        if self._travel_thread and self._travel_thread.is_alive():
            self._travel_stop.set()
            self._travel_thread.join(timeout=2)
        self._travel_thread = None

    def _run_travel(self, pts, speed):
        import time
        try:
            for lat, lon, done in geo.walk(pts, speed, TICK):
                if self._travel_stop.is_set():
                    self._push("decoy.onTravel", {"lat": lat, "lon": lon, "done": done, "stopped": True})
                    return
                self.dev.set(lat, lon)
                self._last = (lat, lon)
                self._push("decoy.onTravel", {"lat": lat, "lon": lon, "done": done, "stopped": False})
                time.sleep(TICK)
            self._push("decoy.onTravel", {"done": 1.0, "finished": True})
        except Exception as e:
            self._push("decoy.onToast", {"msg": f"travel stopped: {e}", "kind": "error"})

    # ---- helpers ----

    def _push(self, fn, payload):
        if not self._window:
            return
        try:
            self._window.evaluate_js(f"{fn}({json.dumps(payload)})")
        except Exception:
            pass

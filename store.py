"""saved spots live in the per-user app-data folder (differs by OS)."""

import json
import os
import sys
import uuid
from pathlib import Path


def _data_dir():
    # each OS has its own "right" place for this kind of thing
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        base = root / "Decoy"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Decoy"
    else:
        # linux / anything else - follow XDG if it's set
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        base = root / "Decoy"
    base.mkdir(parents=True, exist_ok=True)
    return base


class Spots:
    def __init__(self):
        self.path = _data_dir() / "spots.json"
        self._items = self._load()

    def _load(self):
        if not self.path.exists():
            return _seed()
        try:
            return json.loads(self.path.read_text())
        except Exception:
            # corrupt file, don't blow up - just start fresh
            return _seed()

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._items, indent=2))
        os.replace(tmp, self.path)  # atomic-ish so we don't half-write

    def all(self):
        return self._items

    def add(self, name, lat, lon):
        item = {"id": uuid.uuid4().hex[:8], "name": name.strip() or "Unnamed", "lat": lat, "lon": lon}
        self._items.append(item)
        self._save()
        return item

    def rename(self, spot_id, name):
        for it in self._items:
            if it["id"] == spot_id:
                it["name"] = name.strip() or it["name"]
        self._save()

    def remove(self, spot_id):
        self._items = [it for it in self._items if it["id"] != spot_id]
        self._save()


def _seed():
    # a couple of fun defaults so the list isn't empty on first run
    return [
        {"id": "eiffel00", "name": "Eiffel Tower", "lat": 48.8584, "lon": 2.2945},
        {"id": "shibuya0", "name": "Shibuya Crossing", "lat": 35.6595, "lon": 139.7005},
        {"id": "vegas000", "name": "Las Vegas Strip", "lat": 36.1147, "lon": -115.1728},
    ]

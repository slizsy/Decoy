"""Decoy - fake your iphone's location for find my shenanigans. made by slizsy."""

import multiprocessing
import os
import sys


def run_tunneld():
    # headless mode: the packaged app has no separate python, so it runs the
    # pymobiledevice3 tunnel itself when launched as `Decoy --tunneld`.
    # must happen before anything touches the gui or the log tee.
    from pymobiledevice3.__main__ import main as pmd_main
    sys.argv = ["pymobiledevice3", "remote", "tunneld"]
    sys.exit(pmd_main())


def main():
    # install the log tee BEFORE importing anything that might print at import time,
    # so the Logs tab catches early errors (like a bad pymobiledevice3 import)
    import logbuf
    logbuf.install()

    import webview
    from api import Api

    # inside the packaged app the web files live under sys._MEIPASS
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    index = os.path.join(base, "web", "index.html")

    print("[decoy] starting up")
    api = Api()
    window = webview.create_window(
        "Decoy",
        index,
        js_api=api,
        width=1240,
        height=820,
        min_size=(960, 640),
        background_color="#0E1116",
    )
    api.bind(window)
    window.events.closed += api.dev.close
    webview.start()


if __name__ == "__main__":
    multiprocessing.freeze_support()   # needed for frozen apps that spawn processes
    if "--tunneld" in sys.argv:
        run_tunneld()
    else:
        main()

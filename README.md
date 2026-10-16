# Decoy

Spoof your iPhone's location from your Mac. Click a map, your phone goes there, and Find My
believes it. Made by slizsy.

## Features

- Click the map, search a place, or type exact coordinates to teleport
- Travel mode: draw a route and move along it at walk, run, bike, or drive speed
- GPS drift: a small realistic wobble so the position isn't perfectly still
- Saved spots you can jump back to in one click
- Five themes (Signal, Midnight, Terminal, Mono, Daylight)
- Live Logs tab that shows Python errors, tunnel errors, and every call the UI makes
- Optional background service so you enter your password once, not on every connect

## Requirements

- A Mac
- An iPhone on iOS 17 or newer, with a USB cable
- Python 3.9 or newer (only if running from source)

## One-time phone setup

1. Plug the iPhone into the Mac.
2. On the phone: Settings > Privacy & Security > Developer Mode > on, then restart.
3. Unlock it and tap **Trust**. The first connect also shows a pairing prompt. Tap **Allow**.

## Run from source

```bash
git clone https://github.com/slizsy/decoy.git
cd decoy
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

Click the status chip in the top right to connect. The first connect asks for your Mac
password to start the tunnel (see below).

## Build the Mac app

```bash
source venv/bin/activate
./build_mac.sh
```

This makes `dist/Decoy.app` with the app icon. Drag it into Applications.

You can also build it in the cloud: on GitHub, go to Actions, pick **Build Mac app**, and
click **Run workflow**. The finished zip appears under Artifacts. An app downloaded this way
needs a right-click > Open the first time, because it isn't signed with a paid Apple certificate.

## The tunnel

iOS 17 and newer only allow location control through a background tunnel that runs as
admin. Decoy starts it for you.

To skip the password prompt on every connect, flip **Start tunnel at boot** in the Position tab.
It asks for your password once and installs a background service that starts with your Mac.
Flip it off to remove the service.

If you move or rename `Decoy.app`, flip the toggle off and on again so the service points
at the new location.

## Troubleshooting

Open the **Logs** tab first. It shows the actual error.

- **"no iphone found":** unlock the phone and look for a Trust or pairing prompt on its screen.
- **"tunnel didn't come up":** the Logs tab prints the tunnel's own log. Check that nothing
  else is using port 49151.
- **Map is blank:** the map loads from the internet. Check your connection.
- **Device library error:** the Logs tab shows the import error. Usually a missing or
  mismatched `pymobiledevice3` install.

## Project layout

```
main.py        entry point (also runs the tunnel when started with --tunneld)
device.py      phone connection and the tunnel service
api.py         bridge between the UI and Python
geo.py         distance and route math
store.py       saved spots
logbuf.py      log capture for the Logs tab
web/           the interface (HTML, CSS, JS)
assets/        app icons (Decoy.icns for Mac, Decoy.ico for Windows)
build_mac.sh   builds Decoy.app
```

## Roadmap

- Windows build (`.exe`)

## Disclaimer

For fun and for pranks between friends who are in on it. Don't use it to deceive people in
ways that could hurt them, to get around rules, or to fake your whereabouts somewhere it matters.
You're responsible for how you use it. Not affiliated with Apple.

## Credits

- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) talks to the iPhone
- [pywebview](https://pywebview.flowrl.com/) provides the native window
- [Leaflet](https://leafletjs.com/) and [OpenStreetMap](https://www.openstreetmap.org/copyright) power the map
- [Space Grotesk](https://fonts.google.com/specimen/Space+Grotesk) and [JetBrains Mono](https://www.jetbrains.com/lp/mono/) for type

## License

GPL-3.0, see [LICENSE](LICENSE). pymobiledevice3 is GPL-3.0, so Decoy is too.

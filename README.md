# Decoy

Fake your iPhone's location from your Mac. Click a map, your phone goes there, and Find My
believes it. Made by slizsy.

It runs on your computer and talks to your phone over USB using Apple's own developer
location tools, so apps like Find My, Maps, and Weather all see the fake spot. Built for
pranking friends who are in on it.

Tested on an iPhone 15 running iOS 26, with a Mac.

## Features

- Click the map, search a place, or type exact coordinates to teleport
- Travel mode: draw a route and move along it at walk, run, bike, or drive speed
- GPS drift: a small realistic wobble so the position isn't perfectly still
- Saved spots you can jump back to in one click
- Five themes: Signal, Midnight, Terminal, Mono, Daylight
- Logs tab that shows Python errors, tunnel errors, and every call the UI makes
- Optional background service so you enter your password once instead of on every connect
- Welcome animation on startup

## Platform support

| Platform | Status |
| --- | --- |
| macOS | Working |
| Windows | Planned, not working yet |
| Linux | Not planned |

## Requirements (Mac)

- A Mac
- An iPhone on iOS 17 or newer, plus a USB cable
- Python 3.9 or newer

## One-time phone setup

1. Plug the iPhone into the Mac.
2. On the phone: Settings > Privacy & Security > Developer Mode > on, then restart.
3. Unlock it and tap **Trust**. The first connect also shows a pairing prompt. Tap **Allow**.

## Run it

```bash
git clone https://github.com/YOUR-USERNAME/decoy.git
cd decoy
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

Click the status chip in the top right to connect. The first connect asks for your Mac
password to start the tunnel.

## The tunnel

On iOS 17 and newer, location control only works through a background tunnel that runs as
admin. Decoy starts it for you.

To skip the password prompt on every connect, flip **Start tunnel at boot** in the Position
tab. It asks for your password once and installs a background service that starts with your
Mac. Flip it off to remove the service.

## Windows

Not working yet. A Windows version is planned.

What it should need when it's ready (not final):

- Windows 10 or 11
- Apple's USB driver, which comes with iTunes or the Apple Devices app from the Microsoft Store
- Admin rights, to start the tunnel
- Python 3.9 or newer if running from source

What still has to be written for Windows:

- Starting the tunnel (the Mac version uses `osascript` to ask for your password)
- The "Start tunnel at boot" service (the Mac version uses `launchd`)
- Where saved spots are stored (currently a Mac folder)

The interface, map, routes, themes, and logs don't depend on the platform.

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
```

## Disclaimer

For fun and for pranks between friends who are in on it. Don't use it to deceive people in
ways that could hurt them, to get around rules, or to fake your whereabouts somewhere it
matters. You're responsible for how you use it. Not affiliated with Apple.

## Credits

- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) talks to the iPhone
- [pywebview](https://pywebview.flowrl.com/) provides the native window
- [Leaflet](https://leafletjs.com/) and [OpenStreetMap](https://www.openstreetmap.org/copyright) power the map
- Space Grotesk and JetBrains Mono for type

## License

GPL-3.0, see [LICENSE](LICENSE). pymobiledevice3 is GPL-3.0, so Decoy is too.

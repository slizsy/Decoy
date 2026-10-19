# Decoy

Spoof your iPhone's location from your Mac or Windows PC. Click a map, your phone goes there,
and Find My believes it. Made by slizsy.

It runs on your computer and talks to your phone over USB using Apple's own developer location
tools, so Find My, Maps, Weather, and everything else see the fake spot.

Mac is the most tested. Windows runs from source and builds into a single `.exe`, but it's newer
and has had less testing, especially the background service.

## Features

- Click the map, search a place, or type exact coordinates to teleport
- Travel mode: draw a route and move along it at walk, run, bike, or drive speed
- GPS drift: a small realistic wobble so the position isn't perfectly still
- Saved spots you can jump back to in one click
- Five themes (Signal, Midnight, Terminal, Mono, Daylight)
- Live Logs tab that shows Python errors, tunnel errors, and every call the UI makes
- Optional background service so you approve the admin prompt once, not on every connect
  (a launchd daemon on Mac, a Scheduled Task on Windows)

## Requirements

### Mac

- A Mac
- An iPhone on iOS 17 or newer, with a USB cable
- Python 3.9 or newer (only if running from source)

### Windows

- Windows 10 or 11
- An iPhone on iOS 17 or newer, with a USB cable
- The **Apple Devices** app from the Microsoft Store (or iTunes from apple.com). This installs
  Apple's USB service. Without it, Windows can't see the phone at all.
- Python **3.12 or 3.13** (only if running from source). Newer versions (3.14+) don't have
  prebuilt packages for everything yet, so pip tries to compile them and fails without
  Microsoft's C++ build tools.

## One-time phone setup

1. Plug the iPhone into the computer.
   - On Windows, open the **Apple Devices** app first. The Trust prompt appears once the
     phone is plugged in and unlocked.
2. On the phone: Settings > Privacy & Security > Developer Mode > on, then restart.
   - If the Developer Mode switch isn't there, run
     `python -m pymobiledevice3 amfi reveal-developer-mode` and check again.
3. Unlock it and tap **Trust**. The first connect also shows a pairing prompt. Tap **Allow**.

## Get the app

The easiest way is to grab a prebuilt app from GitHub Actions - no Python, no build tools:

1. On GitHub, open the **Actions** tab.
2. Pick **Build apps** on the left, then click **Run workflow**.
3. When it finishes, scroll to **Artifacts** and download **Decoy-macos** or **Decoy-windows**.

- **Mac:** unzip it to get `Decoy.app`, drag it into Applications. First launch needs a
  right-click > **Open**, because it isn't signed with a paid Apple certificate.
- **Windows:** you get a single `Decoy.exe`. SmartScreen may warn on first run (unsigned) -
  click **More info > Run anyway**.

Or push a tag like `v1.0` and the same workflow attaches both apps to a GitHub Release.

## Run from source

### Mac

```bash
git clone https://github.com/slizsy/decoy.git
cd decoy
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

### Windows

In Command Prompt:

```bat
git clone https://github.com/slizsy/decoy.git
cd decoy
py -3.12 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

Click the status chip in the top right to connect. The first connect asks for admin rights to
start the tunnel (the Mac password dialog, or the Windows UAC prompt).

## The tunnel

iOS 17 and newer only allow location control through a background tunnel that runs with admin
rights. Decoy starts it for you through the OS's native prompt, so you never touch a terminal.

To skip that prompt on every connect, flip **Start tunnel at boot** in the Position tab. It asks
for admin once and installs a background service that starts with your computer:

- **Mac:** a launchd daemon in `/Library/LaunchDaemons`.
- **Windows:** a Scheduled Task (`DecoyTunnel`) that runs at logon with highest privileges.

Flip it off to remove the service. If you move or rename the app, flip it off and on again so
the service points at the new location.

If the automatic prompt ever misbehaves, you can start the tunnel yourself in a terminal:

```bash
sudo python -m pymobiledevice3 remote tunneld        # mac
```
```bat
python -m pymobiledevice3 remote tunneld             :: windows, in an Administrator terminal
```

## Troubleshooting

Open the **Logs** tab first. It shows the actual error.

- **"no iphone found":** unlock the phone and look for a Trust or pairing prompt on its screen.
  On Windows, make sure the **Apple Devices** app is installed and the phone shows up there.
- **"tunnel didn't come up":** the Logs tab prints the tunnel's own log. Check that nothing
  else is using port 49151, and that you approved the admin / UAC prompt.
- **App window is blank (Windows):** you need the **WebView2 runtime**. It ships with Windows 11
  and recent Windows 10; otherwise grab it from Microsoft's Edge WebView2 page.
- **Map is blank:** the map loads from the internet. Check your connection.
- **Device library error:** the Logs tab shows the import error. Usually a missing or
  mismatched `pymobiledevice3` install.

## Project layout

```
main.py                     entry point (also runs the tunnel when started with --tunneld)
device.py                   phone connection and the per-OS tunnel service
api.py                      bridge between the UI and Python
geo.py                      distance and route math
store.py                    saved spots
logbuf.py                   log capture for the Logs tab
web/                        the interface (HTML, CSS, JS)
assets/                     app icons (Decoy.icns for Mac, Decoy.ico for Windows)
.github/workflows/build.yml builds the Mac app and Windows exe on GitHub's runners
```

## Credits

- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) talks to the iPhone
- [pywebview](https://pywebview.flowrl.com/) provides the native window
- [Leaflet](https://leafletjs.com/) and [OpenStreetMap](https://www.openstreetmap.org/copyright) power the map
- [Space Grotesk](https://fonts.google.com/specimen/Space+Grotesk) and [JetBrains Mono](https://www.jetbrains.com/lp/mono/) for type

## License

GPL-3.0, see [LICENSE](LICENSE). pymobiledevice3 is GPL-3.0, so Decoy is too.

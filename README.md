# Decoy

Spoof your iPhone's location from your Mac or Windows PC. Click a map, your phone goes there,
and Find My believes it. Made by slizsy.

Mac is the most tested. Windows works from source and has a build script for a single `.exe`,
but it's newer and has had less testing.

## Features

- Click the map, search a place, or type exact coordinates to teleport
- Travel mode: draw a route and move along it at walk, run, bike, or drive speed
- GPS drift: a small realistic wobble so the position isn't perfectly still
- Saved spots you can jump back to in one click
- Five themes (Signal, Midnight, Terminal, Mono, Daylight)
- Live Logs tab that shows Python errors, tunnel errors, and every call the UI makes
- Optional background service so you enter your password once, not on every connect
  (a launchd service on Mac, a Scheduled Task on Windows)

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
- Python **3.12 or 3.13** (only if running from source). Newer versions (3.14 and up) don't have
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

Click the status chip in the top right to connect. The first connect asks for your Mac
password to start the tunnel (see below).

### Windows

In Command Prompt:

```bat
git clone https://github.com/slizsy/decoy.git
cd decoy
py -3

# Luno for macOS

Build a release disk image from the project folder:

```sh
macOS/build-dmg.sh
```

The resulting `dist/Luno-macOS.dmg` contains `Luno.app` and an Applications
shortcut. Open the disk image and drag Luno into Applications. Double-click
Luno to start the browser interface. User files and logs are stored under
`~/Library/Application Support/Luno` and `~/Library/Logs/Luno`.

Luno requires Python 3.9 or newer on the Mac. The disk image includes Luno's
application and CLI code, but not a Python runtime. The app is not signed or
notarized; macOS may require confirmation the first time it is opened.

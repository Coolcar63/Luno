# Luno for macOS

Build a release disk image from the project folder:

```sh
sh macOS/build-dmg.sh
```

The resulting `dist/Luno-macOS.dmg` contains `Luno.app`, an Applications
shortcut, and a Read Me with installation and first-launch instructions. Open
the disk image in Finder, drag Luno onto Applications, then open Luno from the
Applications folder. It starts the interface in your default browser; quit the
Luno app with Command-Q when finished.

User files and logs are stored under `~/Library/Application Support/Luno` and
`~/Library/Logs/Luno`.

Luno requires Python 3.9 or newer on the Mac. The disk image includes Luno's
application and CLI code, but not a Python runtime. The app is not Developer
ID-signed or notarized; macOS may require confirmation the first time it is
opened.

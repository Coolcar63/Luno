#!/bin/sh
set -eu

project_directory=$(CDPATH= cd "$(/usr/bin/dirname "$0")/.." && pwd -P)
output_directory="$project_directory/dist"
output_image="$output_directory/Luno-macOS.dmg"
stage_directory=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/Luno-release.XXXXXX")

cleanup() {
	/bin/rm -rf "$stage_directory"
}
trap cleanup EXIT HUP INT TERM

if [ ! -f "$project_directory/.venv/include/Luno.py" ]; then
	printf '%s\n' "Could not find the Luno CLI at .venv/include/Luno.py." >&2
	exit 1
fi

/bin/mkdir -p "$output_directory"
/usr/bin/osacompile -s -o "$project_directory/Luno.app" "$project_directory/macOS/Luno.applescript"
/bin/mkdir -p "$project_directory/Luno.app/Contents/Resources/runtime"
/usr/bin/ditto "$project_directory/LunoApp.py" "$project_directory/Luno.app/Contents/Resources/LunoApp.py"
/usr/bin/ditto "$project_directory/.venv/include/Luno.py" "$project_directory/Luno.app/Contents/Resources/runtime/Luno.py"
/usr/bin/ditto "$project_directory/Luno.app" "$stage_directory/Luno.app"
/usr/bin/xattr -cr "$stage_directory/Luno.app"
/usr/bin/codesign --force --deep --sign - "$stage_directory/Luno.app"
/bin/ln -s /Applications "$stage_directory/Applications"

cat > "$stage_directory/Read Me.txt" <<'EOF'
Luno for macOS

INSTALL
1. Open this Luno disk image in Finder.
2. Drag Luno.app onto the Applications folder shortcut.
3. Wait for the copy to finish, then eject the Luno disk image.

OPEN
1. Open your Applications folder.
2. Double-click Luno.
3. Luno opens its interface in your default web browser. Keep Luno running
   while you use it; quit Luno with Command-Q when finished.

FIRST OPEN
Luno requires Python 3.9 or newer to be installed on your Mac.
Because this app is not notarized, macOS may show a security warning. If
macOS blocks it, open Applications, Control-click Luno, choose Open, then
confirm Open in the dialog.

YOUR FILES
Luno saves Python files in:
~/Library/Application Support/Luno/workspace

The app's log is in:
~/Library/Logs/Luno/LunoApp.log
EOF

/usr/bin/hdiutil create \
	-volname "Luno" \
	-srcfolder "$stage_directory" \
	-format UDZO \
	-imagekey zlib-level=9 \
	-ov "$output_image"

printf 'Created %s\n' "$output_image"

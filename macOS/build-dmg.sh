#!/bin/sh
set -eu

project_directory=$(/usr/bin/dirname "$(/usr/bin/dirname "$(/usr/bin/realpath "$0")")")
output_directory="$project_directory/dist"
output_image="$output_directory/Luno-macOS.dmg"
stage_directory=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/Luno-release.XXXXXX")
release_directory="$stage_directory/Luno"

cleanup() {
	/bin/rm -rf "$stage_directory"
}
trap cleanup EXIT HUP INT TERM

if [ ! -f "$project_directory/.venv/include/Luno.py" ]; then
	printf '%s\n' "Could not find the Luno CLI at .venv/include/Luno.py." >&2
	exit 1
fi

/bin/mkdir -p "$output_directory" "$release_directory"
/usr/bin/osacompile -s -o "$release_directory/Luno.app" "$project_directory/macOS/Luno.applescript"
/bin/mkdir -p "$release_directory/Luno.app/Contents/Resources/runtime"
/usr/bin/ditto "$project_directory/LunoApp.py" "$release_directory/Luno.app/Contents/Resources/LunoApp.py"
/usr/bin/ditto "$project_directory/.venv/include/Luno.py" "$release_directory/Luno.app/Contents/Resources/runtime/Luno.py"
/bin/ln -s /Applications "$stage_directory/Applications"

cat > "$stage_directory/Read Me.txt" <<'EOF'
Luno for macOS

Drag Luno.app to Applications, then open it.
Luno requires Python 3.9 or newer.

Your Luno files are stored in:
~/Library/Application Support/Luno/workspace
EOF

/usr/bin/hdiutil create \
	-volname "Luno" \
	-srcfolder "$stage_directory" \
	-format UDZO \
	-imagekey zlib-level=9 \
	-ov "$output_image"

printf 'Created %s\n' "$output_image"

property serverPID : ""

on run
	set resourcesDirectory to POSIX path of (path to resource "LunoApp.py")
	set bundledCli to resourcesDirectory & "runtime/Luno.py"
	set appScript to resourcesDirectory & "LunoApp.py"
	set workspaceDirectory to POSIX path of (path to application support from user domain) & "Luno/workspace"
	set supportDirectory to POSIX path of (path to application support from user domain) & "Luno"
	set logDirectory to POSIX path of (path to home folder) & "Library/Logs/Luno"
	set logFile to logDirectory & "/LunoApp.log"
	set venvPython to POSIX path of (path to me) & ".venv/bin/python"
	set pythonSearchCommand to "for candidate in " & quoted form of venvPython & " /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3 /Library/Frameworks/Python.framework/Versions/*/bin/python3; do if [ -x \"$candidate\" ] && \"$candidate\" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then printf '%s' \"$candidate\"; exit 0; fi; done; exit 1"
	try
		set pythonExecutable to do shell script "/bin/sh -c " & quoted form of pythonSearchCommand
	on error
		display dialog "Luno requires Python 3.9 or newer. Install Python for macOS, then open Luno again." buttons {"OK"} default button "OK" with title "Python is required"
		return
	end try

	try
		do shell script "/bin/mkdir -p " & quoted form of workspaceDirectory & " " & quoted form of logDirectory & " && if [ ! -f " & quoted form of (workspaceDirectory & "/Luno.py") & " ]; then /bin/cp " & quoted form of bundledCli & " " & quoted form of (workspaceDirectory & "/Luno.py") & "; fi"
	on error errorMessage
		display dialog "Luno could not prepare its workspace: " & errorMessage buttons {"OK"} default button "OK" with title "Luno could not start"
		return
	end try

	set launchCommand to "cd " & quoted form of workspaceDirectory & "; /usr/bin/nohup /usr/bin/env LUNO_WORKSPACE=" & quoted form of workspaceDirectory & " " & quoted form of pythonExecutable & " " & quoted form of appScript & " >> " & quoted form of logFile & " 2>&1 < /dev/null & echo $!"
	try
		set serverPID to do shell script launchCommand
	on error errorMessage
		display dialog "Luno could not start its local server: " & errorMessage buttons {"OK"} default button "OK" with title "Luno could not start"
	end try
end run

on idle
	return 60
end idle

on quit
	if serverPID is not "" then
		try
			do shell script "/bin/kill -TERM " & quoted form of serverPID
		end try
	end if
	continue quit
end quit

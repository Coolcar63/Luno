property serverPID : ""

on run
	set appPath to POSIX path of (path to me)
	set findProjectCommand to "candidate=" & quoted form of appPath & "; while [ \"$candidate\" != / ]; do if [ -f \"$candidate/LunoApp.py\" ]; then printf '%s' \"$candidate\"; exit 0; fi; candidate=$(/usr/bin/dirname \"$candidate\"); done; exit 1"
	try
		set projectDirectory to do shell script "/bin/sh -c " & quoted form of findProjectCommand
	on error errorMessage
		display dialog "Luno could not find LunoApp.py. Keep Luno.app inside the Luno project folder." buttons {"OK"} default button "OK" with title "Luno could not start"
		return
	end try
	set pythonExecutable to projectDirectory & "/.venv/bin/python"
	set appScript to projectDirectory & "/LunoApp.py"
	set supportDirectory to POSIX path of (path to home folder) & "Library/Logs/Luno"
	set logFile to supportDirectory & "/LunoApp.log"

	try
		do shell script "/bin/test -x " & quoted form of pythonExecutable & " && /bin/test -f " & quoted form of appScript
	on error errorMessage
		display dialog "Luno could not find its project files or virtual-environment Python. Keep Luno.app in the Luno project folder and check that .venv/bin/python exists." buttons {"OK"} default button "OK" with title "Luno could not start"
		return
	end try

	do shell script "/bin/mkdir -p " & quoted form of supportDirectory
	set launchCommand to "cd " & quoted form of projectDirectory & "; /usr/bin/nohup " & quoted form of pythonExecutable & " " & quoted form of appScript & " >> " & quoted form of logFile & " 2>&1 < /dev/null & echo $!"
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

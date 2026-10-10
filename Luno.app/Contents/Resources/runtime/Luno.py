from pathlib import Path
import shlex
import shutil
import subprocess
import sys

try:
    import readline
except ImportError:
    readline = None

if readline is not None:
    if hasattr(readline, "set_auto_history"):
        readline.set_auto_history(False)
    readline.set_completer_delims(" \t\n")

HISTORY_FILE = Path.home() / ".luno_history"
COMMANDS = ("about", "create", "delete", "edit", "exit", "help", "history", "print(", "quit", "run")


def complete_command(text, state):
    line = readline.get_line_buffer()
    typed_line = line.strip()
    if not typed_line or (len(typed_line.split()) == 1 and typed_line == text):
        matches = [command for command in COMMANDS if command.startswith(text.lower())]
    else:
        matches = []
        path = Path(text)
        directory = path.parent if str(path.parent) != "." else Path(".")
        name_prefix = path.name
        try:
            matches = [
                str(directory / entry.name) if str(directory) != "." else entry.name
                for entry in directory.iterdir()
                if entry.name.startswith(name_prefix)
                and (entry.is_dir() or (entry.is_file() and entry.suffix.lower() == ".py"))
            ]
            matches = [
                f"{match}/" if (directory / Path(match).name).is_dir() else match
                for match in matches
            ]
        except OSError:
            pass
    return matches[state] if state < len(matches) else None


if readline is not None:
    readline.set_completer(complete_command)
    if "libedit" in (readline.__doc__ or ""):
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")
    try:
        readline.read_history_file(HISTORY_FILE)
    except FileNotFoundError:
        pass
    except OSError as error:
        print(f"Could not load command history from {HISTORY_FILE}: {error}")


def python_file_path(filename):
    working_directory = Path.cwd().resolve()
    path = Path(filename)
    if path.is_absolute():
        raise ValueError("Use a path relative to the current directory.")

    path = (working_directory / path).resolve()
    try:
        path.relative_to(working_directory)
    except ValueError as error:
        raise ValueError("Python files must stay within the current directory.") from error

    if path.suffix.lower() != ".py":
        raise ValueError("The filename must end in .py.")
    return path


def backup_file_path(path):
    backup_path = path.with_name(f"{path.name}.bak")
    suffix = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{path.name}.bak.{suffix}")
        suffix += 1
    return backup_path


def enter_file_contents():
    print("Enter the file contents. Type :save on a line by itself to save, or :cancel to cancel.")
    lines = []
    while True:
        line = prompt_input("... ")
        if line is None:
            return None
        if line == ":save":
            return "\n".join(lines) + ("\n" if lines else "")
        if line == ":cancel":
            return None
        lines.append(line)


def prompt_input(prompt):
    try:
        return input(prompt)
    except EOFError:
        print("\nEnd of input.")
    except KeyboardInterrupt:
        print("\nInput cancelled.")
    return None


def show_history():
    if readline is None:
        print("Command history is unavailable in this Python environment.")
        return

    for index in range(1, readline.get_current_history_length() + 1):
        entry = readline.get_history_item(index)
        if entry is not None:
            print(f"{index}: {entry}")


while True:
    command = prompt_input("Enter a command (or 'exit' or 'quit' to quit): ")
    if command is None:
        print("Exiting Luno.")
        break
    command = command.strip()

    if command and readline is not None:
        readline.add_history(command)

    if command[:6].lower() == "print(" and command.endswith(")"):
        text = command[6:-1].strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
            text = text[1:-1]
        print(text)
        continue
    if command.lower() == "print" or command.lower().startswith("print "):
        print('Malformed print command. Usage: print("text")')
        continue

    try:
        parts = shlex.split(command)
    except ValueError as error:
        print(f"Invalid command syntax: {error}")
        continue

    if not parts:
        continue

    action = parts[0].lower()
    if action in {"exit", "quit"}:
        should_continue = prompt_input("Do you want to continue? (y/n): ")
        if should_continue is None:
            print("Exiting Luno.")
            break
        should_continue = should_continue.strip().lower()
        if should_continue == "y":
            break
    elif action in {"create", "edit", "delete", "run"}:
        if len(parts) != 2:
            print(f"Usage: {action} filename.py")
            continue

        try:
            path = python_file_path(parts[1])
            if action == "create":
                if path.exists():
                    print(f"{path.name} already exists. Use 'edit \"{path.name}\"' to replace its contents.")
                    continue
                contents = enter_file_contents()
                if contents is None:
                    print("Creation cancelled.")
                    continue
                with path.open("x", encoding="utf-8") as file:
                    file.write(contents)
                print(f"Created {path.name}.")
            elif action == "edit":
                if not path.is_file():
                    print(f"{parts[1]} does not exist. Use 'create \"{parts[1]}\"' to make it.")
                    continue
                existing_contents = path.read_text(encoding="utf-8")
                print("Current contents:")
                print(existing_contents, end="")
                if existing_contents and not existing_contents.endswith("\n"):
                    print()
                contents = enter_file_contents()
                if contents is None:
                    print("Edit cancelled.")
                    continue
                confirmation = prompt_input(f"Replace all contents of {path.name}? (y/n): ")
                if confirmation is None or confirmation.strip().lower() != "y":
                    print("Edit cancelled; file was not changed.")
                    continue
                backup_path = backup_file_path(path)
                shutil.copy2(path, backup_path)
                path.write_text(contents, encoding="utf-8")
                print(f"Saved {path.name}. Backup created at {backup_path.name}.")
            elif action == "delete":
                if not path.is_file():
                    print(f"{parts[1]} does not exist.")
                    continue
                confirmation = prompt_input(
                    f"Delete {path.name}? This cannot be undone. (y/n): "
                )
                if confirmation is None or confirmation.strip().lower() != "y":
                    print("Deletion cancelled; file was not changed.")
                    continue
                path.unlink()
                print(f"Deleted {path.name}.")
            else:
                if not path.is_file():
                    print(f"{parts[1]} does not exist.")
                    continue
                try:
                    result = subprocess.run([sys.executable, str(path)], check=False)
                except KeyboardInterrupt:
                    print("Run interrupted by user.")
                else:
                    print(f"Program exited with status {result.returncode}.")
        except (OSError, ValueError) as error:
            print(f"Error: {error}")
    elif action == "about":
        print("This is a Luno.")
    elif action == "history":
        show_history()
    elif action == "help":
        print('print("x"), prints the specified text')
        print("about, tells you about this program")
        print("help, lists available commands")
        print("history, shows saved command history")
        print("exit or quit, exits this program")
        print('create "filename.py", creates a Python file in the current directory')
        print('edit "filename.py", replaces file contents after confirmation and makes a backup')
        print('delete "filename.py", deletes a Python file after confirmation')
        print('run "filename.py", runs a Python file and displays its exit status')
    else:
        print(f"Unknown command: {command!r}. Type 'help' for a list of commands.")

if readline is not None:
    if readline.get_current_history_length():
        try:
            readline.write_history_file(HISTORY_FILE)
        except OSError as error:
            print(f"Could not save command history to {HISTORY_FILE}: {error}")

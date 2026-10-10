from __future__ import annotations

import codecs
import errno
import json
import os
import pty
import secrets
import select
import signal
import shutil
import subprocess
import sys
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse


APP_DIRECTORY = Path(__file__).resolve().parent
CLI_DIRECTORY = APP_DIRECTORY / ".venv" / "include"
BUNDLED_CLI_DIRECTORY = APP_DIRECTORY / "runtime"
DEFAULT_WORKSPACE = (
    CLI_DIRECTORY
    if (CLI_DIRECTORY / "Luno.py").is_file()
    else BUNDLED_CLI_DIRECTORY
    if (BUNDLED_CLI_DIRECTORY / "Luno.py").is_file()
    else APP_DIRECTORY
)
WORKSPACE = Path(os.environ.get("LUNO_WORKSPACE", str(DEFAULT_WORKSPACE))).expanduser()
MAX_REQUEST_BYTES = 1_000_000
RUN_TIMEOUT_SECONDS = 30
MAX_TERMINAL_OUTPUT = 200_000
MAX_TERMINAL_INPUT_BYTES = 4_000

PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Luno</title>
  <style>
    :root { color-scheme: light; font: 15px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #172033; background: #f3f5f9; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; }
    header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 22px; color: white; background: #202b44; }
    header h1 { margin: 0; font-size: 21px; }
    header span { color: #d7deef; font-size: 13px; }
    main { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 16px; height: calc(100vh - 65px); padding: 16px; }
    aside, section { min-height: 0; padding: 16px; border: 1px solid #e0e5ee; border-radius: 10px; background: white; }
    aside { display: flex; flex-direction: column; }
    h2 { margin: 0 0 12px; font-size: 16px; }
    #files { overflow: auto; flex: 1; margin: 0; padding: 0; list-style: none; }
    #files button { width: 100%; overflow: hidden; padding: 9px 10px; border: 0; border-radius: 6px; background: transparent; text-align: left; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
    #files button:hover, #files button.selected { background: #edf2ff; color: #244cc4; }
    #empty { color: #727d91; font-size: 13px; }
    section { display: flex; flex-direction: column; gap: 12px; }
    #selected-name { font-size: 14px; font-weight: 600; }
    textarea { flex: 1; min-height: 180px; width: 100%; resize: vertical; padding: 12px; border: 1px solid #cbd3e1; border-radius: 7px; font: 14px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; tab-size: 4; }
    nav { display: flex; flex-wrap: wrap; gap: 8px; }
    button.action { padding: 8px 13px; border: 1px solid #cbd3e1; border-radius: 6px; color: #172033; background: white; cursor: pointer; }
    button.action:hover:not(:disabled) { background: #edf2ff; }
    button.action.primary { border-color: #3159ce; color: white; background: #3159ce; }
    button.action.danger { color: #a52e36; }
    button:disabled { opacity: .45; cursor: not-allowed; }
    #status { min-height: 20px; color: #526078; font-size: 13px; }
    #output { display: none; max-height: 180px; overflow: auto; margin: 0; padding: 12px; border-radius: 7px; color: #e8edf8; background: #202b44; white-space: pre-wrap; overflow-wrap: anywhere; }
    .terminal { display: flex; flex-direction: column; gap: 8px; min-height: 160px; padding-top: 10px; border-top: 1px solid #e0e5ee; }
    .terminal h2 { margin: 0; }
    #terminal-output { flex: 1; min-height: 75px; max-height: 180px; overflow: auto; margin: 0; padding: 10px; border-radius: 7px; color: #e8edf8; background: #202b44; font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
    #command-form { display: flex; gap: 8px; }
    #command-input { flex: 1; min-width: 0; padding: 8px 10px; border: 1px solid #cbd3e1; border-radius: 6px; font: 14px ui-monospace, SFMono-Regular, Menlo, monospace; }
    @media (max-width: 700px) {
      main { grid-template-columns: 1fr; height: auto; }
      aside { min-height: 180px; }
      section { min-height: 65vh; }
    }
  </style>
</head>
<body>
  <header><h1>Luno</h1><span id="workspace"></span></header>
  <main>
    <aside>
      <h2>Python files</h2>
      <ul id="files"></ul>
      <div id="empty"></div>
      <nav><button class="action primary" id="new">New file</button><button class="action" id="refresh">Refresh</button></nav>
    </aside>
    <section>
      <div id="selected-name">Choose a file or create one</div>
      <textarea id="editor" spellcheck="false" aria-label="Python file contents" disabled></textarea>
      <nav>
        <button class="action primary" id="save" disabled>Save</button>
        <button class="action" id="run" disabled>Run</button>
        <button class="action danger" id="delete" disabled>Delete</button>
      </nav>
      <div id="status" role="status">Ready</div>
      <pre id="output"></pre>
      <div class="terminal">
        <h2>Luno.py Terminal</h2>
        <pre id="terminal-output" aria-live="polite">Connecting to the running Luno.py process…</pre>
        <form id="command-form">
          <input id="command-input" aria-label="Input for Luno.py terminal" autocomplete="off" placeholder="Enter a line; use Up/Down for history">
          <button class="action primary" type="submit">Send</button>
        </form>
      </div>
    </section>
  </main>
  <script>
    const token = "__TOKEN__";
    const files = document.querySelector("#files");
    const empty = document.querySelector("#empty");
    const editor = document.querySelector("#editor");
    const selectedName = document.querySelector("#selected-name");
    const status = document.querySelector("#status");
    const output = document.querySelector("#output");
    const terminalOutput = document.querySelector("#terminal-output");
    const commandInput = document.querySelector("#command-input");
    let selected = null;
    let savedContent = "";
    let terminalOffset = 0;
    let terminalHistory = [];
    let terminalHistoryIndex = null;
    let terminalDraft = "";
    let terminalWriteQueue = Promise.resolve();
    const workspaceLabel = document.querySelector("#workspace");

    async function api(path, options = {}) {
      const response = await fetch(path, {
        ...options,
        headers: { "X-Luno-Token": token, ...(options.headers || {}) }
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
      return data;
    }

    function sendTerminalInput(value) {
      const request = terminalWriteQueue.then(() => api("/api/terminal/input", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: value })
      }));
      terminalWriteQueue = request.catch(() => {});
      return request;
    }

    function setStatus(message) { status.textContent = message; }
    function appendTerminal(text) {
      const cleanText = text
        .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "")
        .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
        .replace(/\r\n/g, "\n")
        .replace(/\r/g, "\n")
        .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, "");
      const previous = terminalOutput.textContent || "";
      terminalOutput.textContent = `${previous}${cleanText}`.slice(-20000);
      terminalOutput.scrollTop = terminalOutput.scrollHeight;
    }

    async function pollTerminal() {
      try {
        const result = await api(`/api/terminal?offset=${terminalOffset}`);
        terminalOffset = result.next_offset;
        if (result.truncated) appendTerminal("\n[Earlier terminal output was dropped.]\n");
        if (result.output) {
          appendTerminal(result.output);
          await refreshList();
        }
        if (!result.running) {
          setStatus("Luno.py terminal has exited. Restart Luno to open a new terminal session.");
          return;
        }
      } catch (error) {
        setStatus(`Terminal connection lost: ${error.message}`);
        return;
      }
      window.setTimeout(pollTerminal, 200);
    }
    function setSelected(name) {
      selected = name;
      selectedName.textContent = name || "Choose a file or create one";
      editor.disabled = !name;
      for (const id of ["save", "run", "delete"]) document.querySelector(`#${id}`).disabled = !name;
      for (const button of files.querySelectorAll("button")) {
        button.classList.toggle("selected", button.dataset.name === name);
      }
    }

    async function refreshList(keepSelection = true) {
      const result = await api("/api/files");
      workspaceLabel.textContent = result.workspace;
      files.replaceChildren();
      empty.textContent = result.files.length ? "" : "No .py files in this folder yet.";
      for (const name of result.files) {
        const item = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = name;
        button.dataset.name = name;
        button.addEventListener("click", () => loadFile(name));
        item.append(button);
        files.append(item);
      }
      if (keepSelection && selected && result.files.includes(selected)) setSelected(selected);
      else if (!result.files.includes(selected)) setSelected(null);
    }

    async function loadFile(name) {
      try {
        const result = await api(`/api/file?name=${encodeURIComponent(name)}`);
        setSelected(name);
        editor.value = result.content;
        savedContent = editor.value;
        output.style.display = "none";
        setStatus("File loaded.");
      } catch (error) { setStatus(error.message); }
    }

    async function saveFile() {
      if (!selected) return;
      const changed = editor.value !== savedContent;
      if (!changed) { setStatus("No changes to save."); return; }
      if (!window.confirm(`Save changes to ${selected}? A backup will be created.`)) return;
      try {
        const result = await api("/api/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: selected, content: editor.value })
        });
        savedContent = editor.value;
        setStatus(`Saved. Backup: ${result.backup}`);
      } catch (error) { setStatus(error.message); }
    }

    document.querySelector("#new").addEventListener("click", async () => {
      const name = window.prompt("New Python filename (for example, hello.py):");
      if (name === null) return;
      try {
        const result = await api("/api/create", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name })
        });
        await refreshList(false);
        await loadFile(result.name);
        setStatus("Created new file.");
      } catch (error) { setStatus(error.message); }
    });
    document.querySelector("#refresh").addEventListener("click", () => refreshList().catch(error => setStatus(error.message)));
    document.querySelector("#save").addEventListener("click", saveFile);
    editor.addEventListener("keydown", event => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        saveFile();
      }
      if (event.key === "Tab") {
        event.preventDefault();
        const start = editor.selectionStart;
        editor.setRangeText("    ", start, editor.selectionEnd, "end");
      }
    });
    window.addEventListener("beforeunload", event => {
      if (selected && editor.value !== savedContent) {
        event.preventDefault();
        event.returnValue = "";
      }
    });

    document.querySelector("#delete").addEventListener("click", async () => {
      if (!selected || !window.confirm(`Delete ${selected}? This cannot be undone.`)) return;
      try {
        await api("/api/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: selected })
        });
        setSelected(null);
        editor.value = "";
        savedContent = "";
        await refreshList(false);
        setStatus("File deleted.");
      } catch (error) { setStatus(error.message); }
    });

    document.querySelector("#run").addEventListener("click", async () => {
      if (!selected) return;
      try {
        const started = await api("/api/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: selected })
        });
        setStatus("Running…");
        output.style.display = "block";
        output.textContent = "Running…";
        const poll = async () => {
          const result = await api(`/api/run?id=${encodeURIComponent(started.id)}`);
          if (result.running) {
            window.setTimeout(() => poll().catch(error => setStatus(error.message)), 250);
          } else {
            output.textContent = result.output || "(No output)";
            setStatus(result.timed_out ? "Stopped after 30 seconds." : `Finished with exit status ${result.returncode}.`);
          }
        };
        await poll();
      } catch (error) { setStatus(error.message); }
    });

    document.querySelector("#command-form").addEventListener("submit", async event => {
      event.preventDefault();
      const command = commandInput.value;
      if (command.trim()) {
        terminalHistory.push(command);
        terminalHistoryIndex = null;
        terminalDraft = "";
      }
      commandInput.value = "";
      try {
        await sendTerminalInput(`${command}\n`);
        setStatus("Input sent to Luno.py.");
      } catch (error) {
        appendTerminal(`\nTerminal input error: ${error.message}\n`);
      } finally {
        commandInput.focus();
      }
    });

    commandInput.addEventListener("keydown", event => {
      if (event.key === "ArrowUp" && terminalHistory.length) {
        event.preventDefault();
        if (terminalHistoryIndex === null) {
          terminalDraft = commandInput.value;
          terminalHistoryIndex = terminalHistory.length;
        }
        terminalHistoryIndex = Math.max(0, terminalHistoryIndex - 1);
        commandInput.value = terminalHistory[terminalHistoryIndex];
      } else if (event.key === "ArrowDown" && terminalHistoryIndex !== null) {
        event.preventDefault();
        terminalHistoryIndex += 1;
        if (terminalHistoryIndex >= terminalHistory.length) {
          terminalHistoryIndex = null;
          commandInput.value = terminalDraft;
        } else {
          commandInput.value = terminalHistory[terminalHistoryIndex];
        }
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "c") {
        event.preventDefault();
        commandInput.value = "";
        sendTerminalInput("\u0003").catch(error => setStatus(`Terminal input error: ${error.message}`));
      } else if (event.ctrlKey && event.key.toLowerCase() === "d" && !commandInput.value) {
        event.preventDefault();
        sendTerminalInput("\u0004").catch(error => setStatus(`Terminal input error: ${error.message}`));
      } else if (event.key === "Tab") {
        event.preventDefault();
        commandInput.setRangeText("    ", commandInput.selectionStart, commandInput.selectionEnd, "end");
      }
    });

    refreshList().catch(error => setStatus(error.message));
    pollTerminal();
  </script>
</body>
</html>
"""


def _safe_python_file(workspace: Path, name: object) -> Path:
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ValueError("Use a Python filename in the Luno folder.")
    path = (workspace / name).resolve()
    if path.parent != workspace or path.suffix.lower() != ".py":
        raise ValueError("Only .py files in the Luno folder are supported.")
    if path == Path(__file__).resolve():
        raise ValueError("The Luno app cannot edit or delete itself.")
    return path


def _next_backup_path(path: Path) -> Path:
    candidate = path.with_name(f"{path.name}.bak")
    suffix = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.bak.{suffix}")
        suffix += 1
    return candidate


def _run_script(workspace: Path, path: Path, jobs: dict[str, dict[str, object]], job_id: str) -> None:
    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=RUN_TIMEOUT_SECONDS,
        )
        job_result: dict[str, object] = {
            "running": False,
            "returncode": result.returncode,
            "output": result.stdout + result.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout or ""
        stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr or ""
        job_result = {
            "running": False,
            "returncode": None,
            "output": stdout + stderr + "\nStopped: script exceeded 30 seconds.",
            "timed_out": True,
        }
    except OSError as error:
        job_result = {
            "running": False,
            "returncode": None,
            "output": f"Could not run script: {error}",
            "timed_out": False,
        }

    with jobs_lock:
        jobs[job_id] = job_result


jobs_lock = threading.Lock()


def _start_script(
    workspace: Path,
    path: Path,
    jobs: dict[str, dict[str, object]],
) -> str:
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"running": True}
    thread = threading.Thread(
        target=_run_script,
        args=(workspace, path, jobs, job_id),
        daemon=True,
    )
    thread.start()
    return job_id


class LunoTerminal:
    def __init__(self, script: Path, workspace: Path) -> None:
        self._lock = threading.Lock()
        self._output = ""
        self._output_base = 0
        self._running = True

        pid, master_fd = pty.fork()
        if pid == 0:
            try:
                environment = os.environ.copy()
                environment["TERM"] = "xterm"
                os.chdir(workspace)
                os.execve(sys.executable, [sys.executable, str(script)], environment)
            except BaseException as error:
                os.write(2, f"Could not start Luno.py: {error}\n".encode("utf-8", errors="replace"))
                os._exit(127)

        self._pid = pid
        self._master_fd = master_fd
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while self._running:
            try:
                readable, _, _ = select.select([self._master_fd], [], [], 0.2)
                if not readable:
                    continue
                chunk = os.read(self._master_fd, 4096)
                if not chunk:
                    break
                text = decoder.decode(chunk)
                if text:
                    with self._lock:
                        self._output += text
                        if len(self._output) > MAX_TERMINAL_OUTPUT:
                            removed = len(self._output) - MAX_TERMINAL_OUTPUT
                            self._output = self._output[removed:]
                            self._output_base += removed
            except OSError as error:
                if error.errno != errno.EIO:
                    with self._lock:
                        self._output += f"\nTerminal read error: {error}\n"
                break

        remaining = decoder.decode(b"", final=True)
        with self._lock:
            self._output += remaining
            self._running = False
        try:
            os.waitpid(self._pid, 0)
        except ChildProcessError:
            pass

    def write(self, value: str) -> None:
        encoded = value.encode("utf-8")
        if len(encoded) > MAX_TERMINAL_INPUT_BYTES:
            raise ValueError("Terminal input is too long.")
        with self._lock:
            if not self._running:
                raise RuntimeError("The Luno.py terminal has exited.")
            try:
                os.write(self._master_fd, encoded)
            except OSError as error:
                raise RuntimeError(f"Could not write to Luno.py: {error}") from error

    def read(self, offset: int) -> dict[str, object]:
        if offset < 0:
            raise ValueError("Terminal output offset must be non-negative.")
        with self._lock:
            current_offset = self._output_base + len(self._output)
            requested_offset = max(offset, self._output_base)
            start = min(requested_offset - self._output_base, len(self._output))
            return {
                "output": self._output[start:],
                "next_offset": current_offset,
                "running": self._running,
                "truncated": offset < self._output_base,
            }

    def stop(self) -> None:
        if self._running:
            try:
                os.killpg(self._pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            self._reader.join(timeout=1)
            if self._reader.is_alive():
                try:
                    os.killpg(self._pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self._reader.join(timeout=1)
        try:
            os.close(self._master_fd)
        except OSError:
            pass


def create_server(workspace: Path, token: str) -> ThreadingHTTPServer:
    resolved_workspace = workspace.resolve()
    jobs: dict[str, dict[str, object]] = {}
    cli_script = resolved_workspace / "Luno.py"
    terminal = LunoTerminal(cli_script, resolved_workspace) if cli_script.is_file() else None

    class RequestHandler(BaseHTTPRequestHandler):
        def _send_json(self, status_code: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, object]:
            length_text = self.headers.get("Content-Length", "0")
            try:
                length = int(length_text)
            except ValueError as error:
                raise ValueError("Invalid request length.") from error
            if length < 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("Request is too large.")
            try:
                payload = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise ValueError("Request body must be valid JSON.") from error
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object.")
            return payload

        def _authorized(self) -> bool:
            if secrets.compare_digest(self.headers.get("X-Luno-Token", ""), token):
                return True
            self._send_json(403, {"error": "This Luno page is not authorized."})
            return False

        def do_GET(self) -> None:
            request = urlparse(self.path)
            if request.path == "/":
                query_token = parse_qs(request.query).get("token", [""])[0]
                if not secrets.compare_digest(query_token, token):
                    self.send_error(403, "Invalid Luno session.")
                    return
                body = PAGE.replace("__TOKEN__", token).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            if not self._authorized():
                return

            try:
                query = parse_qs(request.query)
                if request.path == "/api/files":
                    names = sorted(
                        path.name
                        for path in resolved_workspace.glob("*.py")
                        if path.is_file() and path.resolve() != Path(__file__).resolve()
                    )
                    self._send_json(200, {"files": names, "workspace": str(resolved_workspace)})
                elif request.path == "/api/file":
                    path = _safe_python_file(resolved_workspace, query.get("name", [""])[0])
                    if not path.is_file():
                        self._send_json(404, {"error": "File not found."})
                        return
                    self._send_json(200, {"content": path.read_text(encoding="utf-8")})
                elif request.path == "/api/run":
                    job_id = query.get("id", [""])[0]
                    with jobs_lock:
                        job = jobs.get(job_id)
                    if job is None:
                        self._send_json(404, {"error": "Run not found."})
                    else:
                        self._send_json(200, job)
                elif request.path == "/api/terminal":
                    if terminal is None:
                        self._send_json(503, {"error": "Luno.py was not found in this workspace."})
                        return
                    offset = int(query.get("offset", ["0"])[0])
                    self._send_json(200, terminal.read(offset))
                else:
                    self._send_json(404, {"error": "Not found."})
            except ValueError as error:
                self._send_json(400, {"error": str(error)})
            except (OSError, UnicodeDecodeError) as error:
                self._send_json(500, {"error": f"Could not read file: {error}"})

        def do_POST(self) -> None:
            if not self._authorized():
                return
            try:
                payload = self._read_json()
                if self.path == "/api/create":
                    name = payload.get("name")
                    path = _safe_python_file(resolved_workspace, name)
                    if path.exists():
                        self._send_json(409, {"error": f"{path.name} already exists."})
                        return
                    path.touch(exist_ok=False)
                    self._send_json(201, {"name": path.name})
                elif self.path == "/api/save":
                    path = _safe_python_file(resolved_workspace, payload.get("name"))
                    content = payload.get("content")
                    if not isinstance(content, str):
                        raise ValueError("File contents must be text.")
                    if len(content.encode("utf-8")) > MAX_REQUEST_BYTES:
                        raise ValueError("File is too large to save.")
                    if not path.is_file():
                        self._send_json(404, {"error": "File not found."})
                        return
                    backup = _next_backup_path(path)
                    shutil.copy2(path, backup)
                    path.write_text(content, encoding="utf-8")
                    self._send_json(200, {"backup": backup.name})
                elif self.path == "/api/delete":
                    path = _safe_python_file(resolved_workspace, payload.get("name"))
                    if not path.is_file():
                        self._send_json(404, {"error": "File not found."})
                        return
                    path.unlink()
                    self._send_json(200, {"deleted": path.name})
                elif self.path == "/api/run":
                    path = _safe_python_file(resolved_workspace, payload.get("name"))
                    if not path.is_file():
                        self._send_json(404, {"error": "File not found."})
                        return
                    job_id = _start_script(resolved_workspace, path, jobs)
                    self._send_json(202, {"id": job_id})
                elif self.path == "/api/terminal/input":
                    if terminal is None:
                        self._send_json(503, {"error": "Luno.py was not found in this workspace."})
                        return
                    terminal_input = payload.get("input")
                    if not isinstance(terminal_input, str):
                        raise ValueError("Terminal input must be text.")
                    try:
                        terminal.write(terminal_input)
                    except RuntimeError as error:
                        self._send_json(409, {"error": str(error)})
                        return
                    self._send_json(200, {"sent": len(terminal_input)})
                else:
                    self._send_json(404, {"error": "Not found."})
            except ValueError as error:
                self._send_json(400, {"error": str(error)})
            except OSError as error:
                self._send_json(500, {"error": f"File operation failed: {error}"})

        def log_message(self, format_string: str, *args: object) -> None:
            print(f"Luno: {format_string % args}")

    class LunoHTTPServer(ThreadingHTTPServer):
        def server_close(self) -> None:
            super().server_close()
            if terminal is not None:
                terminal.stop()

    return LunoHTTPServer(("127.0.0.1", 0), RequestHandler)


def main() -> None:
    token = secrets.token_urlsafe(32)
    server = create_server(WORKSPACE, token)
    address, port = server.server_address
    url = f"http://{address}:{port}/?token={quote(token)}"
    print(f"Luno is serving Python files from: {WORKSPACE}")
    print("Keep this process running while using Luno. Press Ctrl+C to stop.")
    if not webbrowser.open(url):
        print(f"Open this address in your browser: {url}")

    def stop_server(signum: int, frame: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    previous_sigterm_handler = signal.signal(signal.SIGTERM, stop_server)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Luno.")
    finally:
        server.server_close()
        signal.signal(signal.SIGTERM, previous_sigterm_handler)


if __name__ == "__main__":
    main()

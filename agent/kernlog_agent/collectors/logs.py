"""Log tailing via watchdog with rotation handling."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import threading

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class _TailState:
    def __init__(self, path: str) -> None:
        self.path = path
        self.offset = Path(path).stat().st_size


class _Handler(FileSystemEventHandler):
    def __init__(self, state_map: dict[str, _TailState], emit_fn):
        super().__init__()
        self.state_map = state_map
        self.emit_fn = emit_fn
        self.lock = threading.Lock()

    def on_modified(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        self._read_new_lines(str(event.src_path))

    def on_moved(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        src = str(event.src_path)
        if src in self.state_map:
            self.state_map[src].offset = 0

    def _read_new_lines(self, path: str) -> None:
        if path not in self.state_map:
            return

        state = self.state_map[path]
        try:
            current_size = Path(path).stat().st_size
            if current_size < state.offset:
                state.offset = 0
            with Path(path).open("r", encoding="utf-8", errors="replace") as file:
                file.seek(state.offset)
                for line in file:
                    self.emit_fn(path, line.rstrip("\n"), datetime.now(timezone.utc).isoformat())
                state.offset = file.tell()
        except FileNotFoundError:
            state.offset = 0


class LogTailer:
    def __init__(self, file_paths: list[str], emit_fn):
        self.file_paths = [str(Path(p).resolve()) for p in file_paths]
        self.state_map = {path: _TailState(path) for path in self.file_paths}
        self.handler = _Handler(self.state_map, emit_fn)
        self.observer = Observer()

    def start(self) -> None:
        watched_dirs: set[str] = set()
        for file_path in self.file_paths:
            directory = str(Path(file_path).parent)
            if directory not in watched_dirs:
                self.observer.schedule(self.handler, directory, recursive=False)
                watched_dirs.add(directory)
        self.observer.start()

    def stop(self) -> None:
        self.observer.stop()
        self.observer.join(timeout=5)

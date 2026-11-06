"""Bounded, ephemeral extraction of untrusted attachments (Linux worker)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Literal


MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_TEXT_CHARS = 65536
MAX_WIRE_BYTES = 512 * 1024
WORKER_TIMEOUT = 45


@dataclass(frozen=True)
class Extraction:
    status: Literal["ok", "dangerous", "unreadable", "unsupported"]
    text: str = ""
    reason: str = ""


class ExtractionFailure(Exception):
    def __init__(self, status: str, reason: str):
        self.status, self.reason = status, reason
        super().__init__(reason)


def child_environment(workdir: Path) -> dict[str, str]:
    """Do not inherit credentials, proxy configuration or Python startup hooks."""
    return {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "TMPDIR": str(workdir), "TMP": str(workdir), "TEMP": str(workdir),
            "HOME": str(workdir), "XDG_CACHE_HOME": str(workdir),
            "OMP_THREAD_LIMIT": "1", "OPENBLAS_NUM_THREADS": "1",
            "PYTHONDONTWRITEBYTECODE": "1"}


def run_bounded(argv: list[str], *, cwd: Path, timeout: float, output_limit: int,
                new_session: bool = False, input_data: bytes | None = None) -> tuple[int, bytes, bytes]:
    """Drain pipes incrementally; never buffer unbounded communicate() output."""
    started = time.monotonic()
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL if input_data is None else subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=cwd, env=child_environment(cwd),
                            close_fds=True, start_new_session=new_session)
    output, errors = bytearray(), bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            pending = memoryview(input_data) if input_data is not None else None
            if pending is not None:
                os.set_blocking(proc.stdin.fileno(), False)
                selector.register(proc.stdin, selectors.EVENT_WRITE, None)
            selector.register(proc.stdout, selectors.EVENT_READ, output)
            selector.register(proc.stderr, selectors.EVENT_READ, errors)
            while selector.get_map():
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise ExtractionFailure("unreadable", "parser wall-time limit exceeded")
                for key, _ in selector.select(min(remaining, 0.1)):
                    if key.fileobj is proc.stdin:
                        try:
                            written = os.write(proc.stdin.fileno(), pending[:16384])
                            pending = pending[written:]
                        except BrokenPipeError:
                            pending = pending[:0]
                        if not pending:
                            selector.unregister(proc.stdin)
                            proc.stdin.close()
                        continue
                    chunk = os.read(key.fileobj.fileno(), 16384)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    key.data.extend(chunk)
                    cap = output_limit if key.data is output else 65536
                    if len(key.data) > cap:
                        raise ExtractionFailure("dangerous", "parser output limit exceeded")
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise ExtractionFailure("unreadable", "parser wall-time limit exceeded")
            try:
                code = proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                raise ExtractionFailure("unreadable", "parser wall-time limit exceeded") from None
        return code, bytes(output), bytes(errors)
    finally:
        if new_session:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif proc.poll() is None:
            proc.kill()
        proc.wait()
        proc.stdout.close()
        proc.stderr.close()
        if proc.stdin is not None:
            proc.stdin.close()


def _private_root(root: Path) -> Path:
    root = root.absolute()
    # Do not follow a caller-supplied scratch symlink (including ancestor links).
    for component in (root, *root.parents):
        if component.is_symlink():
            raise ExtractionFailure("unreadable", "scratch path must not contain symlinks")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ExtractionFailure("unreadable", "scratch directory must be owner-only (0700)")
    return root


def extract(data: bytes, filename: str, content_type: str = "", *,
            scratch_root: Path | None = None) -> Extraction:
    """Extract text without durable attachment storage; danger always has no text.

    ``dangerous`` requires the caller to stop the attachment batch and alert now.
    ``unreadable``/``unsupported`` require review; they are never safe-to-archive.
    """
    if not isinstance(data, bytes):
        return Extraction("unreadable", reason="input must be bytes")
    if len(data) > MAX_INPUT_BYTES:
        return Extraction("dangerous", reason="attachment byte limit exceeded (16 MiB)")
    if not data:
        return Extraction("unreadable", reason="empty attachment")
    if not isinstance(filename, str) or len(filename) > 1024 or "\0" in filename:
        return Extraction("unreadable", reason="invalid attachment filename")
    suffix = Path(filename).suffix.lower()
    executable = {".exe", ".dll", ".com", ".scr", ".msi", ".sh", ".bat", ".cmd",
                  ".ps1", ".js", ".vbs", ".py", ".jar", ".html", ".htm", ".svg",
                  ".docm", ".xlsm", ".pptm", ".xlam", ".dotm", ".ppsm", ".xlsb"}
    if (suffix in executable or data.startswith((b"MZ", b"\x7fELF", b"#!"))
            or content_type.split(";", 1)[0].strip().lower() in {
                "application/x-executable", "application/x-msdownload", "application/javascript"}):
        return Extraction("dangerous", reason="executable, active or macro-enabled attachment")
    formats = {".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx", ".pptx": "pptx",
               ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".tif": "tiff",
               ".tiff": "tiff", ".bmp": "bmp"}
    kind = formats.get(suffix)
    if kind is None:
        if data.startswith(b"\xd0\xcf\x11\xe0"):
            return Extraction("unsupported", reason="legacy OLE Office or encrypted OOXML container; not parsed")
        return Extraction("unsupported", reason="supported: PDF, DOCX, XLSX, PPTX, PNG, JPEG, single-frame TIFF/BMP; no archive unpacking or legacy Office")
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        return Extraction("unreadable", reason="encrypted/password-protected OOXML or mismatched legacy OLE container")
    try:
        if scratch_root is None:
            configured_temp = os.environ.get("TMPDIR", "")
            if not configured_temp or not Path(configured_temp).is_absolute():
                return Extraction("unreadable", reason="explicit private scratch_root or absolute TMPDIR is required")
            scratch_root = Path(configured_temp) / "email-steward-extraction"
        root = _private_root(Path(scratch_root))
        with tempfile.TemporaryDirectory(prefix="attachment-", dir=root) as directory:
            workdir = Path(directory)
            # No attacker-controlled file name ever reaches a path or an argv token.
            source = workdir / "input"
            with source.open("xb") as stream:
                os.chmod(source, 0o600)
                stream.write(data)
            code, raw, _ = run_bounded(
                [sys.executable, "-I", "-B", str(Path(__file__).with_name("extract_worker.py")),
                 kind, str(source)], cwd=workdir, timeout=WORKER_TIMEOUT,
                output_limit=MAX_WIRE_BYTES, new_session=True)
            if code:
                return Extraction("unreadable", reason="extraction worker failed or resource limit exceeded")
            result = json.loads(raw)
            status, text, reason = result["status"], result["text"], result["reason"]
            if (status not in {"ok", "dangerous", "unreadable", "unsupported"}
                    or not isinstance(text, str) or not isinstance(reason, str)
                    or len(text) > MAX_TEXT_CHARS or len(reason) > 1024
                    or (status != "ok" and text)):
                return Extraction("unreadable", reason="invalid extraction worker response")
            return Extraction(status, text, reason)
    except ExtractionFailure as exc:
        return Extraction(exc.status, reason=exc.reason)
    except (OSError, ValueError, KeyError, TypeError):
        return Extraction("unreadable", reason="extraction unavailable: scratch, worker or response error")


def result_json(result: Extraction) -> str:
    return json.dumps(asdict(result), ensure_ascii=False)

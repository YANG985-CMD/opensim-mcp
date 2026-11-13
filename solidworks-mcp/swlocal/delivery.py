"""Bounded, in-session file freshness evidence for explicitly named CAD outputs."""
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
from threading import Lock
from uuid import uuid4

_FORMATS = {".sldprt", ".sldasm", ".step", ".stp", ".stl"}
_MAX_FILES = 256
_MAX_BYTES = 2 * 1024**3
_MAX_BASELINES = 32


@dataclass(frozen=True)
class Stamp:
    sha256: str
    size: int


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _stamp(path, remaining):
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"Expected a regular CAD file: {path.name}")
    if info.st_size > remaining:
        raise ValueError("The declared CAD outputs exceed the 2 GiB scan limit")
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        if _identity(os.fstat(stream.fileno())) != _identity(info):
            raise ValueError(f"File changed before verification: {path.name}")
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            count += len(chunk)
            if count > info.st_size:
                raise ValueError(f"File changed during verification: {path.name}")
            digest.update(chunk)
        if _identity(os.fstat(stream.fileno())) != _identity(info):
            raise ValueError(f"File changed during verification: {path.name}")
    if count != info.st_size or _identity(path.stat()) != _identity(info):
        raise ValueError(f"File changed during verification: {path.name}")
    return Stamp(digest.hexdigest(), count)


class DeliveryChecks:
    def __init__(self, output_root):
        self.root = Path(output_root).resolve()
        self._baselines = OrderedDict()
        self._lock = Lock()

    def _paths(self, paths):
        if not 1 <= len(paths) <= _MAX_FILES:
            raise ValueError("Provide 1 to 256 explicit CAD output paths")
        results = []
        seen = set()
        for name in paths:
            if not name or len(name) > 1024 or not name.strip():
                raise ValueError("Invalid CAD output path")
            raw = Path(name)
            segments = raw.parts[1:] if raw.anchor else raw.parts
            if raw.suffix.lower() not in _FORMATS or any(
                ":" in part or part.endswith((" ", ".")) for part in segments
            ) or raw.is_reserved():
                raise ValueError("Use ordinary SLDPRT, SLDASM, STEP, STP or STL paths without aliases or parent traversal")
            candidate = raw if raw.is_absolute() else self.root / raw
            resolved = candidate.resolve()
            if not resolved.is_relative_to(self.root) or resolved == self.root or resolved != candidate:
                raise ValueError("Every CAD output must be inside the configured output root without redirected paths")
            key = os.path.normcase(str(resolved))
            if key in seen:
                raise ValueError("Duplicate CAD output path")
            seen.add(key)
            results.append(resolved)
        return tuple(results)

    def _read(self, paths):
        remaining = _MAX_BYTES
        stamps = []
        for path in paths:
            if path.resolve() != path:
                raise ValueError("A declared output path was redirected")
            stamp = _stamp(path, remaining)
            if path.resolve() != path:
                raise ValueError("A declared output path was redirected during verification")
            if stamp is not None:
                remaining -= stamp.size
            stamps.append(stamp)
        return tuple(stamps)

    def capture(self, paths):
        paths = self._paths(paths)
        with self._lock:
            stamps = self._read(paths)
            token = uuid4().hex
            self._baselines[token] = (paths, stamps)
            if len(self._baselines) > _MAX_BASELINES:
                self._baselines.popitem(last=False)
        return {"baseline_id": token, "paths": [p.relative_to(self.root).as_posix() for p in paths],
                "existing_files": sum(stamp is not None for stamp in stamps), "scope": "current MCP process"}

    def current(self, paths):
        paths = self._paths(paths)
        with self._lock:
            stamps = self._read(paths)
        return {p.relative_to(self.root).as_posix(): {"sha256": s.sha256, "bytes": s.size} if s else None
                for p, s in zip(paths, stamps, strict=True)}

    def verify(self, baseline_id):
        with self._lock:
            if baseline_id not in self._baselines:
                raise ValueError("Unknown or expired baseline. Capture a new one before generating outputs.")
            paths, before = self._baselines[baseline_id]
            after = self._read(paths)
        files = []
        for path, old, new in zip(paths, before, after, strict=True):
            if new is None:
                status = "missing"
            elif new.size == 0:
                status = "empty"
            elif old is None:
                status = "new"
            elif new == old:
                status = "unchanged"
            else:
                status = "updated"
            files.append({"path": path.relative_to(self.root).as_posix(), "status": status,
                          "before_sha256": old.sha256 if old else None,
                          "sha256": new.sha256 if new else None, "bytes": new.size if new else None})
        fresh = all(row["status"] in {"new", "updated"} for row in files)
        return {"baseline_id": baseline_id, "status": "fresh" if fresh else "needs_review", "files": files,
                "scope": "Content change since baseline. Does not attribute the writer or verify CAD geometry."}

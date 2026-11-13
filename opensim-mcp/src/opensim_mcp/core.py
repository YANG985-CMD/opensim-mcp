from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from defusedxml.ElementTree import fromstring

MAX_MODEL = 20 * 1024 * 1024
MAX_TRC = 64 * 1024 * 1024
MAX_RESULT = 64 * 1024 * 1024
MAX_FRAMES = 100_000
MAX_MARKERS = 500
_JOB_LOCK = threading.Lock()


class InputError(ValueError):
    """An input or server configuration does not meet the supported profile."""


def local_path(value: str | Path) -> Path:
    text = str(value)
    # No device paths, UNC/network shares, alternate data streams or wildcards.
    if text.startswith(("\\\\", "//")) or any(c in text for c in "*?\x00"):
        raise InputError("Only ordinary local paths are supported.")
    if ":" in text[2:]:
        raise InputError("Alternate data streams and URI paths are forbidden.")
    path = Path(text)
    if not path.is_absolute():
        raise InputError("Use an absolute local path.")
    resolved = path.resolve()
    if str(resolved).startswith(("\\\\", "//")):
        raise InputError("Network targets are forbidden.")
    return resolved


def is_under(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


@dataclass(frozen=True)
class Settings:
    allowed_roots: tuple[Path, ...]
    results_root: Path
    temp_root: Path
    cli: str | None
    timeout: int = 120

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            roots = json.loads(os.environ.get("OPENSIM_MCP_ALLOWED_ROOTS", "[]"))
        except json.JSONDecodeError as exc:
            raise InputError("OPENSIM_MCP_ALLOWED_ROOTS must be a JSON array.") from exc
        if not isinstance(roots, list) or not roots or not all(isinstance(p, str) for p in roots):
            raise InputError("Configure a nonempty JSON array of allowed input folders.")
        allowed = tuple(local_path(p) for p in roots)
        if not all(p.is_dir() and p.parent != p for p in allowed):
            raise InputError("Input roots must be existing folders, never whole drives.")
        output = os.environ.get("OPENSIM_MCP_RESULTS_ROOT")
        if not output:
            raise InputError("Configure OPENSIM_MCP_RESULTS_ROOT explicitly.")
        results = local_path(output)
        temp_value = os.environ.get("OPENSIM_MCP_TEMP_ROOT")
        if not temp_value:
            raise InputError("Configure OPENSIM_MCP_TEMP_ROOT explicitly.")
        temporary = local_path(temp_value)
        if results.parent == results or temporary.parent == temporary:
            raise InputError("Results/temp roots cannot be drive roots.")
        if is_under(results, temporary) or is_under(temporary, results):
            raise InputError("Results and temporary folders must be separate.")
        timeout = int(os.environ.get("OPENSIM_MCP_TIMEOUT_SEC", "120"))
        if not 1 <= timeout <= 600:
            raise InputError("Timeout must be 1..600 seconds.")
        # Only administrator/user configuration can select the executable.
        explicit = os.environ.get("OPENSIM_MCP_CLI")
        cli = str(local_path(explicit)) if explicit else shutil.which("opensim-cmd")
        if cli and (not Path(cli).is_file() or Path(cli).name.lower() not in {"opensim-cmd.exe", "opensim-cmd"}):
            raise InputError("CLI must be the installed opensim-cmd executable.")
        temporary.mkdir(parents=True, exist_ok=True)
        return cls(allowed, results, temporary, cli, timeout)

    def input_path(self, value: str, suffix: str) -> Path:
        path = local_path(value)
        if not (is_under(path,self.results_root) or any(is_under(path, root) for root in self.allowed_roots)):
            raise InputError("Input is outside configured allowed roots (including resolved links).")
        if path.suffix.lower() != suffix or not path.is_file():
            raise InputError(f"Expected an existing {suffix} file.")
        return path


def bounded_read(path: Path, maximum: int) -> bytes:
    if path.stat().st_size > maximum:
        raise InputError(f"File exceeds {maximum} byte limit.")
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise InputError("File grew beyond size limit while reading.")
    return data


def xml_model(data: bytes) -> tuple[ET.Element, ET.Element]:
    try:
        root = fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except Exception as exc:
        raise InputError(f"Invalid or prohibited XML: {type(exc).__name__}") from exc
    stack = [(root, 0)]
    count = 0
    while stack:
        element, depth = stack.pop()
        count += 1
        if count > 200_000 or depth > 100:
            raise InputError("XML node/depth limit exceeded.")
        if not isinstance(element.tag, str) or "{" in element.tag:
            raise InputError("Namespaced models are outside this MVP's XML profile.")
        stack.extend((child, depth + 1) for child in element)
    models = root.findall("Model") if root.tag == "OpenSimDocument" else []
    if len(models) != 1:
        raise InputError("Expected OpenSimDocument containing exactly one Model.")
    return root, models[0]


def external_properties(model: ET.Element) -> list[dict]:
    refs = []
    for node in model.iter():
        tag = node.tag.lower()
        value = (node.text or "").strip()
        if ("file" in tag or "library" in tag or tag in {"data_source", "datasource"}) and value.lower() not in {"", "unassigned", "none"}:
            refs.append({"property": node.tag, "value": value[:512]})
        for key, value in node.attrib.items():
            if "file" in key.lower() or "library" in key.lower():
                refs.append({"property": f"{node.tag}@{key}", "value": value[:512]})
    return refs


def bounded_strings(value):
    if isinstance(value, str):
        return value[:512] + (" [truncated]" if len(value) > 512 else "")
    if isinstance(value, list):
        return [bounded_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: bounded_strings(item) for key, item in value.items()}
    return value


def summary(data: bytes, path: str = "", limit: int = 100) -> dict:
    if type(limit) is not int or not 1 <= limit <= 500:
        raise InputError("limit must be an integer in 1..500.")
    root, model = xml_model(data)
    bodies = list(model.iter("Body"))
    joints = [e for e in model.iter() if e.tag.endswith("Joint") and e.tag != "Joint"]
    coords = list(model.iter("Coordinate"))
    markers = list(model.iter("Marker"))
    forces = model.findall("./ForceSet/objects/*")
    muscles = [e for e in forces if "muscle" in e.tag.lower()]
    duplicates = {}
    for label, nodes in (("bodies", bodies), ("joints", joints), ("coordinates", coords), ("markers", markers)):
        repeated = [name for name, n in Counter(e.get("name", "") for e in nodes).items() if n > 1]
        if repeated:
            duplicates[label] = repeated[:limit]
    refs = external_properties(model)
    result = {
        "path": path, "sha256": hashlib.sha256(data).hexdigest(),
        "inspection_mode": "static_xml_only", "native_model_initialized": False,
        "document_version": root.get("Version"), "name": model.get("name"),
        "units": {tag: model.findtext(tag) for tag in ("length_units", "force_units")},
        "gravity": model.findtext("gravity"),
        "counts": {"bodies": len(bodies), "joints": len(joints), "coordinates": len(coords),
                   "markers": len(markers), "forces": len(forces), "muscles_by_class_name": len(muscles)},
        "bodies": [{"name": e.get("name"), "mass_kg_text": e.findtext("mass")} for e in bodies[:limit]],
        "joints": [{"name": e.get("name"), "class": e.tag} for e in joints[:limit]],
        "coordinates": [{"name": e.get("name"), "default_value_text": e.findtext("default_value"),
                         "range_text": e.findtext("range"), "locked_text": e.findtext("locked")} for e in coords[:limit]],
        "markers": [e.get("name") for e in markers[:limit]],
        "muscles": [{"name": e.get("name"), "class": e.tag} for e in muscles[:limit]],
        "duplicate_names": duplicates, "external_properties": refs[:limit],
        "external_property_count": len(refs), "list_limit": limit,
        "warnings": ["Structural XML summary only; no check of dynamics, sockets, identifiability or physiological validity.",
                     "Muscles are recognized by class name; custom classes may be missed; legacy Body named ground is included if serialized."]
    }
    return bounded_strings(result)


def prepare_model(data: bytes) -> tuple[bytes, list[str], list[str]]:
    root, model = xml_model(data)
    # Remove display-only geometry from the staged copy, never the source.
    removed = []
    for parent in list(model.iter()):
        for child in list(parent):
            if child.tag in {"attached_geometry", "VisibleObject"}:
                parent.remove(child)
                removed.append(child.tag)
    if external_properties(model):
        raise InputError("IK only supports self-contained models after removing display geometry; external file/library properties remain.")
    if any(e.attrib.keys() - {"name"} for e in model.iter()):
        raise InputError("IK model attributes other than name are outside the supported profile.")
    markers = [e.get("name", "") for e in model.iter("Marker")]
    coords = [e.get("name", "") for e in model.iter("Coordinate")]
    for label, names in (("markers", markers), ("coordinates", coords)):
        if not names or len(names) != len(set(names)) or any(not n or len(n) > 200 for n in names):
            raise InputError(f"Model needs nonempty, unique {label} names (max 200 characters).")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), markers, removed


def trc_info(data: bytes) -> dict:
    try:
        lines = data.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise InputError("TRC must be UTF-8/ASCII.") from exc
    if len(lines) < 7 or not lines[0].startswith("PathFileType"):
        raise InputError("Expected standard six-header-line TRC.")
    keys, values = lines[1].split(), lines[2].split()
    if len(keys) != len(values):
        raise InputError("TRC metadata columns do not match.")
    meta = dict(zip(keys, values))
    try:
        frames, count = int(meta["NumFrames"]), int(meta["NumMarkers"])
        rate = float(meta["DataRate"])
        units = meta["Units"].lower()
    except (KeyError, ValueError) as exc:
        raise InputError("TRC metadata missing or invalid.") from exc
    if not 2 <= frames <= MAX_FRAMES or not 1 <= count <= MAX_MARKERS or not math.isfinite(rate) or rate <= 0:
        raise InputError("TRC frame/marker/rate limits exceeded.")
    if units not in {"m", "mm"}:
        raise InputError("TRC Units must be m or mm; no implicit unit guessing.")
    # Tab structure retains blank Y/Z slots; whitespace-only marker headers are ambiguous.
    header = lines[3].split("\t")
    if len(header) < 2 + 3 * (count - 1) + 1 or header[0].strip() != "Frame#" or header[1].strip() != "Time":
        raise InputError("TRC requires tab-separated Frame#, Time, and triplet marker columns.")
    names = [header[2 + 3*i].strip() for i in range(count)]
    if len(names) != len(set(names)) or any(not n or len(n) > 200 for n in names):
        raise InputError("TRC marker names must be nonempty and unique.")
    axis = lines[4].split()
    if axis != [f"{a}{i}" for i in range(1, count + 1) for a in "XYZ"]:
        raise InputError("TRC axis header must be X1 Y1 Z1 ... in marker order.")
    times = []
    previous_frame = None
    for line in lines[5:]:
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 2 + 3*count:
            raise InputError("TRC row width mismatch or missing marker sample.")
        try:
            frame = int(fields[0])
            nums = [float(v) for v in fields[1:]]
        except ValueError as exc:
            raise InputError("TRC samples must be numeric.") from exc
        if not all(math.isfinite(v) for v in nums):
            raise InputError("TRC has NaN/Inf; fill or exclude missing markers before running.")
        if times and (nums[0] <= times[-1] or frame <= previous_frame):
            raise InputError("TRC times and frame numbers must strictly increase.")
        times.append(nums[0])
        previous_frame = frame
        if len(times) > frames:
            raise InputError("TRC has more rows than declared.")
    if len(times) != frames:
        raise InputError("TRC data rows do not match NumFrames.")
    return {"frames": frames, "markers": names, "units": units, "data_rate": rate, "times": times}


def read_motion(path: Path) -> dict:
    text = bounded_read(path, MAX_RESULT).decode("utf-8-sig")
    lines = text.splitlines()
    end = next((i for i, line in enumerate(lines) if line.strip().lower() == "endheader"), None)
    if end is None or end > 100:
        raise InputError("Output is missing a bounded endheader.")
    headers = {}
    for line in lines[:end]:
        parts = re.split(r"[=\s]+", line.strip(), maxsplit=1)
        if len(parts) == 2:
            headers[parts[0].lower()] = parts[1].strip()
    rows = [line.split() for line in lines[end+1:] if line.strip()]
    if len(rows) < 3:
        raise InputError("Output contains fewer than two samples.")
    columns, values = rows[0], rows[1:]
    if (columns[0].lower() != "time" or not 2 <= len(columns) <= 5000
            or len(columns) != len(set(columns)) or any(len(name) > 200 for name in columns)):
        raise InputError("Invalid output column labels.")
    numeric = []
    for row in values:
        if len(row) != len(columns):
            raise InputError("Output row width mismatch.")
        numbers = [float(v) for v in row]
        if not all(math.isfinite(v) for v in numbers):
            raise InputError("Output contains non-finite numbers.")
        if numeric and numbers[0] <= numeric[-1][0]:
            raise InputError("Output times are not strictly increasing.")
        numeric.append(numbers)
        if len(numeric) > MAX_FRAMES:
            raise InputError("Output row limit exceeded.")
    for key in ("nrows", "datarows"):
        if key in headers and int(headers[key]) != len(numeric):
            raise InputError("Output declared row count mismatch.")
    for key in ("ncolumns", "datacolumns"):
        if key in headers and int(headers[key]) != len(columns):
            raise InputError("Output declared column count mismatch.")
    return {"columns": columns, "rows": numeric, "in_degrees": headers.get("indegrees", "unspecified")}


def child_env(cfg: Settings, work: Path) -> dict:
    env = os.environ.copy()
    env.update(TEMP=str(work), TMP=str(work),PYTHONIOENCODING='utf-8')
    if cfg.cli and native_backend()=="cli":
        env["PATH"] = str(Path(cfg.cli).parent) + os.pathsep + env.get("PATH", "")
    # Avoid loading Python/Conda shims into the native CLI accidentally.
    env.pop("PYTHONPATH", None)
    return env


def native_backend() -> str:
    backend=os.environ.get("OPENSIM_MCP_TOOL_BACKEND","cli")
    if backend not in {"cli","api"}:
        raise InputError("OPENSIM_MCP_TOOL_BACKEND must be cli or api.")
    return backend


def native_command(cfg: Settings, args: list[str]) -> list[str]:
    if native_backend()=="api":
        python=os.environ.get("OPENSIM_MCP_API_PYTHON")
        if not python or not local_path(python).is_file():
            raise InputError("API tool backend requires an existing OPENSIM_MCP_API_PYTHON.")
        return [python,"-B",str(Path(__file__).with_name("tool_runner.py")),*args]
    if not cfg.cli:
        raise InputError("CLI backend requires OPENSIM_MCP_CLI; PyPI users can select OPENSIM_MCP_TOOL_BACKEND=api.")
    return [cfg.cli,*args]


def execute(cfg: Settings, args: list[str], work: Path, timeout: int, force_api: bool = False) -> dict:
    from .progress import report
    from .process_tree import ProcessTree
    report('native_running',log_path=str(work/'cli.log'))
    if force_api:
        python=os.environ.get('OPENSIM_MCP_API_PYTHON')
        if not python or not local_path(python).is_file():raise InputError('This workflow requires OPENSIM_MCP_API_PYTHON.')
        command=[python,'-B',str(Path(__file__).with_name('tool_runner.py')),*args]
        env=dict(os.environ,TEMP=str(work),TMP=str(work),PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8');env.pop('PYTHONPATH',None)
    else:
        command=native_command(cfg,args);env=child_env(cfg,work)
    log = work / "cli.log"
    started = time.monotonic()
    tree=ProcessTree()
    with log.open("wb") as output:
        proc = tree.spawn(command, cwd=work, env=env,
                                stdin=subprocess.DEVNULL, stdout=output,
                                stderr=subprocess.STDOUT, shell=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            report('native_running',log_path=str(log),native_pid=proc.pid)
            deadline = started + timeout
            while proc.poll() is None:
                if time.monotonic() > deadline:
                    raise TimeoutError(f"OpenSim exceeded {timeout}s.")
                if log.stat().st_size > 8 * 1024 * 1024:
                    raise InputError("OpenSim log exceeded 8 MiB limit.")
                if any(p.stat().st_size > MAX_RESULT for p in work.iterdir() if p.is_file() and p.suffix in {".mot", ".sto"}):
                    raise InputError("Native output exceeded size limit.")
                time.sleep(0.05)
        finally:
            try:tree.terminate();proc.wait(timeout=10)
            finally:tree.close()
    with log.open("rb") as stream:
        stream.seek(max(0, log.stat().st_size - 6000))
        tail = stream.read().decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise InputError(f"OpenSim exited {proc.returncode}. Log tail: {tail}")
    report('validating_outputs')
    return {"exit_code": proc.returncode, "elapsed_seconds": round(time.monotonic()-started, 3),
            "log_tail": tail,"backend":"opensim_api" if force_api else "opensim_"+native_backend()}


def environment(cfg: Settings) -> dict:
    import platform
    from importlib.metadata import version
    info = {"python": platform.python_version(), "mcp": version("mcp"), "platform": platform.platform(),
            "opensim_cli": cfg.cli, "allowed_roots": list(map(str, cfg.allowed_roots)),
            "results_root": str(cfg.results_root), "temp_root": str(cfg.temp_root),
            "native_timeout_seconds": cfg.timeout, "opensim_version": None,
            "inspection_available": True, "ik_available": False}
    info["tool_backend"]=native_backend()
    if cfg.cli or native_backend()=="api":
        try:
            with tempfile.TemporaryDirectory(prefix="probe-", dir=cfg.temp_root) as folder:
                result = execute(cfg, ["--version"], Path(folder), min(10, cfg.timeout))
                info["opensim_version"] = result["log_tail"].strip()
                info["ik_available"] = True  # Import/launch only, not dataset validation.
        except Exception as exc:
            info["native_error"] = str(exc)
    info["ik_availability_scope"] = "Selected backend launch/import probe only; no model/data solve performed."
    return info


def inspect_model(cfg: Settings, model_path: str, limit: int = 100) -> dict:
    path = cfg.input_path(model_path, ".osim")
    return summary(bounded_read(path, MAX_MODEL), str(path), limit)


def motion_summary(cfg: Settings, result_path: str, preview_rows: int = 10) -> dict:
    path = local_path(result_path)
    if not (is_under(path, cfg.results_root) or any(is_under(path, root) for root in cfg.allowed_roots)):
        raise InputError("Result is outside results/allowed input roots.")
    if path.suffix.lower() not in {".mot", ".sto"} or not path.is_file():
        raise InputError("Expected an existing .mot or .sto file.")
    if type(preview_rows) is not int or not 0 <= preview_rows <= 100:
        raise InputError("preview_rows must be 0..100.")
    table = read_motion(path)
    labels, rows = table["columns"][:100], table["rows"]
    return {"path": str(path), "row_count": len(rows), "column_count": len(table["columns"]),
            "columns": labels, "columns_truncated": len(table["columns"]) > 100,
            "time_range": [rows[0][0], rows[-1][0]], "in_degrees": table["in_degrees"],
            "ranges": {name: {"min": min(row[i] for row in rows), "max": max(row[i] for row in rows)}
                       for i, name in enumerate(labels)},
            "preview": [row[:100] for row in rows[:preview_rows]],
            "unit_note": "inDegrees applies to rotational coordinates only; translational coordinates remain in meters."}


def run_ik(cfg: Settings, model_path: str, marker_path: str,
           start_time: float | None = None, end_time: float | None = None,
           marker_weights: dict[str, float] | None = None) -> dict:
    if not _JOB_LOCK.acquire(blocking=False):
        raise InputError("Another IK job is already running in this server process.")
    try:
        return _run_ik(cfg, model_path, marker_path, start_time, end_time, marker_weights)
    finally:
        _JOB_LOCK.release()


def _run_ik(cfg: Settings, model_path: str, marker_path: str,
            start_time: float | None, end_time: float | None,
            marker_weights: dict[str, float] | None) -> dict:
    if not cfg.cli and native_backend()=="cli":
        raise InputError("IK requires opensim-cmd, or an API interpreter with TOOL_BACKEND=api.")
    model_file, trc_file = cfg.input_path(model_path, ".osim"), cfg.input_path(marker_path, ".trc")
    original = bounded_read(model_file, MAX_MODEL)
    trc = bounded_read(trc_file, MAX_TRC)
    staged, model_markers, removed = prepare_model(original)
    data = trc_info(trc)
    common = sorted(set(model_markers) & set(data["markers"]))
    if not common:
        raise InputError("No marker names match between model and TRC.")
    weights = {name: 1.0 for name in common} if marker_weights is None else marker_weights
    if not weights or len(weights) > MAX_MARKERS or set(weights) - set(common):
        raise InputError("Weights must select at least one marker shared by model and TRC.")
    if any(isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w) or not 0 < w <= 1e6 for w in weights.values()):
        raise InputError("Marker weights must be finite and in (0, 1e6].")
    times = data.pop("times")
    start = times[0] if start_time is None else start_time
    end = times[-1] if end_time is None else end_time
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, end)):
        raise InputError("Time range must be finite numeric values.")
    if not times[0] <= start < end <= times[-1]:
        raise InputError("Time range must be ordered and within the TRC time bounds.")
    selected = [t for t in times if start <= t <= end]
    if len(selected) < 2:
        raise InputError("Select at least two TRC samples.")
    if start not in times or end not in times:
        raise InputError("This MVP requires start/end to equal actual TRC sample times.")
    job = uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix=f"ik-{job}-", dir=cfg.temp_root) as directory:
        work = Path(directory)
        (work / "model.osim").write_bytes(staged)
        (work / "markers.trc").write_bytes(trc)
        root = ET.Element("OpenSimDocument", Version="40000")
        tool = ET.SubElement(root, "InverseKinematicsTool", name="ik")
        for key, value in {"results_directory": ".", "model_file": "model.osim", "accuracy": "1e-6",
                           "time_range": f"{start:.17g} {end:.17g}", "output_motion_file": "ik.mot",
                           # OpenSim 4.3's native error reporter can index -1 on an
                           # exact zero-residual frame. Keep the solver, disable
                           # that reporter; never perturb experimental input data.
                           "report_errors": "false", "marker_file": "markers.trc",
                           "coordinate_file": "", "report_marker_locations": "false"}.items():
            ET.SubElement(tool, key).text = value
        tasks = ET.SubElement(tool, "IKTaskSet")
        objects = ET.SubElement(tasks, "objects")
        ET.SubElement(tasks, "groups")
        for name, weight in sorted(weights.items()):
            task = ET.SubElement(objects, "IKMarkerTask", name=name)
            ET.SubElement(task, "apply").text = "true"
            ET.SubElement(task, "weight").text = str(float(weight))
        ET.ElementTree(root).write(work / "setup.xml", encoding="utf-8", xml_declaration=True)
        native = execute(cfg, ["run-tool", "setup.xml"], work, cfg.timeout)
        motion = read_motion(work / "ik.mot")
        actual = [row[0] for row in motion["rows"]]
        if len(actual) != len(selected) or any(abs(a-b) > 1e-7*max(1, abs(b)) for a, b in zip(actual, selected)):
            raise InputError("Native output does not cover exactly the requested TRC samples.")
        _, source_model = xml_model(original)
        expected_coords = {e.get("name") for e in source_model.iter("Coordinate")}
        if not expected_coords <= set(motion["columns"]):
            raise InputError("Native result is missing model coordinate columns.")
        # Probe version after the solve, in a separate temporary cwd.
        version_info = environment(cfg)
        result = {"status": "completed", "job_id": job, "backend": native.get("backend","opensim_cli"),
                  "opensim_version": version_info["opensim_version"],
                  "native_exit_code": native["exit_code"], "elapsed_seconds": native["elapsed_seconds"],
                  "rows": len(actual), "columns": motion["columns"], "in_degrees": motion["in_degrees"],
                  "time_range": [actual[0], actual[-1]], "marker_weights": weights,
                  "trc": data, "visual_properties_removed": dict(Counter(removed)),
                  "validation": "finite motion, expected coordinates, exact requested time samples; solver exit 0",
                  "quality_assessment": "not_assessed_for_real_data",
                  "warnings": ["Successful IK does not establish marker-fit quality or physiological validity.",
                               "Native models must be trusted; path checks are not an OS sandbox."],
                  "untracked_model_markers": sorted(set(model_markers)-set(weights))[:500],
                  "unused_trc_markers": sorted(set(data["markers"])-set(weights))[:500]}
        manifest = {**result, "created_utc": datetime.now(timezone.utc).isoformat(),
                    "inputs": {"model_path": str(model_file), "model_sha256": hashlib.sha256(original).hexdigest(),
                               "marker_path": str(trc_file), "marker_sha256": hashlib.sha256(trc).hexdigest(),
                               "staged_model_sha256": hashlib.sha256(staged).hexdigest()},
                    "parameters": {"accuracy": 1e-6, "start_time": start, "end_time": end,
                                   "marker_weights": weights, "report_errors": False}}
        cfg.results_root.mkdir(parents=True, exist_ok=True)
        destination = cfg.results_root / job
        destination.mkdir(exist_ok=False)  # New UUID directory; never overwrite existing results.
        try:
            shutil.copyfile(work / "ik.mot", destination / "ik.mot")
            (destination / "provenance.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        except BaseException:
            shutil.rmtree(destination)
            raise
        result["result_directory"] = str(destination)
        result["motion_file"] = str(destination / "ik.mot")
        result["provenance_file"] = str(destination / "provenance.json")
        return result


"""Small durable assembly task journal. Never resumes or retries CAD writes."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from uuid import uuid4

_ACTIONS = {
    "set_mate_positions": ({"positions"}, set(), True),
    "scan_motion": ({"trajectory"}, {"restore_start"}, True),
    "audit_assembly": (set(), {"clearance_pairs"}, False),
    "apply_joint_recipe": ({"recipe", "component_a", "component_b"}, {"preview"}, True),
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _motions(data):
    return [
        {"index": row["index"], "positions": row["positions"],
         "interference_count": len(row["interference"]["interferences"])}
        for row in data.get("samples", [])
    ]


def _summary(action, data):
    if action == "scan_motion":
        return {"sampled_poses": _motions(data), "restored_start_pose": data["restored_start_pose"]}
    if action == "audit_assembly":
        return {"status": data["status"], "summary": data["summary"],
                "clearances": data["clearances"]}
    if action == "apply_joint_recipe":
        return {"preview": "plan" in data, "joint_mates": data.get("joint_mates", [])}
    return {"driven_mates": [{key: row.get(key) for key in ("name", "value", "unit")}
                             for row in data.get("driven_mates", [])]}


def plan_steps(steps):
    if not 1 <= len(steps) <= 16 or len(json.dumps(steps, allow_nan=False).encode()) > 128 * 1024:
        raise ValueError("Supply 1..16 explicit steps within a 128 KiB plan")
    result = []
    for step in steps:
        if not isinstance(step, dict) or set(step) != {"action", "parameters"}:
            raise ValueError("Each step must have an action and parameters")
        action = step["action"]
        if not isinstance(action, str) or action not in _ACTIONS or not isinstance(step["parameters"], dict):
            raise ValueError("Unsupported assembly step or parameter object")
        required, optional, mutating = _ACTIONS[action]
        params = step["parameters"]
        if not required <= params.keys() or not params.keys() <= required | optional:
            raise ValueError(f"Invalid parameter fields for {action}")
        if action == "apply_joint_recipe":
            mutating = not params.get("preview", True)
            if type(params.get("preview", True)) is not bool:
                raise ValueError("Recipe preview must be a boolean")
        result.append((action, params, mutating))
    return result


class AssemblyJournal:
    def __init__(self, runtime_root):
        self.root = Path(runtime_root).resolve() / "assembly-tasks"
        self.owner = uuid4().hex

    def _file(self, task_id):
        if not re.fullmatch(r"[a-f0-9]{32}", task_id):
            raise ValueError("Invalid assembly task ID")
        return self.root / f"{task_id}.json"

    def _save(self, record):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._file(record["task_id"])
        pending = path.with_suffix(".pending")
        with pending.open("w", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)

    def get(self, task_id):
        try:
            record = json.loads(self._file(task_id).read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ValueError("Assembly task ID was not found") from error
        if record["status"] == "running" and record["owner"] != self.owner:
            record["status"] = "interrupted_or_running_elsewhere"
            record["next_action"] = "Inspect the assembly before making any additional edit"
        return record

    def recent(self, limit):
        if not 1 <= limit <= 50:
            raise ValueError("Limit must be in 1..50")
        files = sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)[:limit]
        keys = ("task_id", "label", "status", "started_at", "completed_steps", "planned_steps")
        return [{key: record[key] for key in keys} for record in (self.get(p.stem) for p in files)]

    def run(self, call, document_id, state, steps, label, tool_error):
        if not label.strip() or len(label) > 100:
            raise ValueError("Supply a nonempty task label of at most 100 characters")
        actions = plan_steps(steps)
        record = {"schema": 1, "task_id": uuid4().hex, "owner": self.owner, "label": label,
                  "status": "running", "document_id": document_id, "initial_state": state,
                  "final_state": state, "started_at": _now(), "completed_steps": 0,
                  "planned_steps": len(actions), "steps": []}
        self._save(record)
        for index, (action, params, mutating) in enumerate(actions, 1):
            row = {"index": index, "action": action, "status": "running", "before_state": state,
                   "started_at": _now(), "request": params}
            record["steps"].append(row)
            self._save(record)
            try:
                fresh = call("snapshot", {"document_id": document_id})
                if fresh.get("state") != state or fresh.get("kind") != 2:
                    raise tool_error(json.dumps({"code": "STALE_STATE", "edit_may_be_partial": False}))
                args = {"document_id": document_id, **params}
                if action != "audit_assembly":
                    args["state"] = state
                result = call(action, args, write=mutating)
                if not isinstance(result.get("state"), str):
                    raise tool_error(json.dumps({"code": "STATE_UNAVAILABLE", "outcome_unknown": mutating}))
                if not mutating and result["state"] != state:
                    raise tool_error(json.dumps({"code": "INSPECTION_CHANGED_STATE", "outcome_unknown": True}))
                state = result["state"]
                row.update(status="completed", after_state=state, evidence=_summary(action, result))
                record.update(final_state=state, completed_steps=index)
            except tool_error as error:
                try:
                    payload = json.loads(str(error))
                except ValueError:
                    payload = {}
                row.update(status="failed", error_code=payload.get("code", "TOOL_ERROR"),
                           outcome_unknown=bool(payload.get("outcome_unknown") or payload.get("edit_may_be_partial", mutating)))
                for key in ("completed_mates", "completed_samples"):
                    if key in payload:
                        row[key] = _motions({"samples": payload[key]}) if key == "completed_samples" else payload[key]
                record.update(status="failed", final_state=None if row["outcome_unknown"] else state,
                              next_action="Read current geometry and compare with the last completed step. Do not replay a write automatically.")
            except Exception as error:
                row.update(status="failed", error_code=type(error).__name__, outcome_unknown=mutating)
                record.update(status="failed", final_state=None,
                              next_action="Inspect native geometry. The step did not return verifiable evidence.")
            row["finished_at"] = _now()
            self._save(record)
            if row["status"] == "failed":
                break
        if record["status"] == "running":
            record["status"] = "completed"
        record["finished_at"] = _now()
        self._save(record)
        return record

"""Generate a portable, script-free HTML assembly acceptance report."""
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path


def _text(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, allow_nan=False)
    return escape(str(value if value is not None else "—"))


def _table(headers, rows):
    rows = list(rows)
    if not rows:
        return "<p>无记录</p>"
    return ("<table><thead><tr>" + "".join(f"<th>{_text(h)}</th>" for h in headers) +
            "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{_text(cell)}</td>" for cell in row) +
                                            "</tr>" for row in rows) + "</tbody></table>")


def render_report(title, comparison, audit, delivery, reference, task):
    checks = [
        ("装配版本对比", comparison["status"]),
        ("当前姿态体检", audit["status"]),
        ("交付文件哈希", delivery["status"] if delivery else "NOT_RUN"),
        ("保存副本重开引用", reference["status"] if reference else "NOT_RUN"),
    ]
    motion_rows = []
    if task:
        status = "BOUND" if (task["document_id"], task["final_state"]) == (audit["document_id"], audit["state"]) else "UNBOUND"
        for step in task["steps"]:
            for pose in step.get("evidence", {}).get("sampled_poses", []) + step.get("completed_samples", []):
                motion_rows.append([step["index"], pose["index"], pose["positions"], pose["interference_count"], status])
        checks.append(("任务步骤与姿态证据", task["status"] if status == "BOUND" else status))
    if any(status == "FAIL" for _, status in checks):
        disposition = "FAIL"
    elif not (audit["status"] == "PASS" and comparison["status"] == "COMPARED" and
              delivery and delivery["status"] == "fresh" and reference and reference["status"] == "PASS"):
        disposition = "REVIEW"
    elif comparison["mass"]["status"] in {"needs_review", "unavailable"} or task and (
        status != "BOUND" or task["status"] != "completed" or any(row[3] for row in motion_rows)
    ):
        disposition = "REVIEW"
    else:
        disposition = "CHECKS_PASSED"

    dimension_rows = [
        (part["before"], part["after"], item["name"], item["before_si"], item["after_si"])
        for part in comparison["dimensions"] for item in part["changed"]
    ]
    change_rows = [(kind, entry["before"], entry["after"], entry["changes"])
                   for kind, rows in (("组件", comparison["component_changes"]), ("配合", comparison["mate_changes"]))
                   for entry in rows]
    clearances = audit["clearances"]
    measured = [r["distance_mm"] for r in clearances if r.get("distance_mm") is not None]
    mass = comparison["mass"]
    evidence_rows = [(key, comparison[key]) for key in ("components_added", "components_removed", "mates_added", "mates_removed")]
    dimension_sets = [(r["before"], r["after"], r["added"], r["removed"]) for r in comparison["dimensions"] if r["added"] or r["removed"]]
    issue_rows = [(r.get("code"), r.get("message"), r.get("components"), r.get("mate")) for r in audit["issues"]]
    payload = "".join([
        f"<h1>{_text(title)}</h1><p>结果 <strong>{_text(disposition)}</strong> · {_text(datetime.now(timezone.utc).isoformat())}</p>",
        "<p>本报告按所列证据审查。尺寸使用 SI，间隙单位为 mm，运动采样为离散姿态。设计公差、连续碰撞和承载需另行验证。</p>",
        _table(("检查项目", "结果"), checks),
        f"<h2>装配差异</h2><p>{_text(comparison['before']['title'])} → {_text(comparison['after']['title'])}</p>",
        _table(("项目", "名称"), evidence_rows), _table(("类型", "旧名称", "新名称", "差异"), change_rows),
        _table(("旧组件", "新组件", "尺寸", "旧值（SI）", "新值（SI）"), dimension_rows),
        _table(("旧组件", "新组件", "新增尺寸", "移除尺寸"), dimension_sets),
        _table(("质量状态", "旧质量 kg", "新质量 kg", "差值 kg"),
               [(mass["status"], mass.get("before_kg"), mass.get("after_kg"), mass.get("difference_kg"))]),
        _table(("比较缺项",), ((r,) for r in comparison["issues"])),
        f"<h2>当前姿态检查</h2><p>状态 {_text(audit['state'])}，所选组件对中最小测得间隙 {_text(min(measured) if measured else None)} mm。</p>",
        _table(("组件 A", "组件 B", "要求 mm", "实测 mm", "结果"),
               ((r["component_a"], r["component_b"], r["minimum_mm"], r.get("distance_mm"), r["status"]) for r in clearances)),
        _table(("问题", "说明", "组件", "配合"), issue_rows),
        _table(("配合", "当前位置", "下限", "上限", "单位", "状态"),
               ((r["name"], r["value"], r["minimum"], r["maximum"], r["unit"], r["status"]) for r in audit["limits"])),
        _table(("干涉组件", "体积 mm³", "可能干涉"),
               ((r["components"], r["volume_mm3"], r["possible_interference"]) for r in audit["interferences"])),
        "<h2>指定姿态采样</h2>", _table(("任务步骤", "姿态", "位置", "干涉数量", "证据绑定"), motion_rows),
        "<h2>交付文件</h2>", _table(("相对路径", "结果", "字节", "SHA-256"),
               ((r["path"], r["status"], r["bytes"], r["sha256"]) for r in (delivery or {}).get("files", []))),
        "<h2>重开引用</h2>", _table(("装配", "预期零件数", "未解析组件", "缺失", "额外零件"),
               [(reference["assembly"], reference["expected_part_count"], reference["unresolved_components"],
                 reference["missing_parts"], reference["unexpected_parts"])] if reference else []),
        "<h2>任务记录</h2>", _table(("步骤", "动作", "状态", "错误"),
               ((r["index"], r["action"], r["status"], r.get("error_code")) for r in (task or {}).get("steps", []))),
    ])
    return disposition, """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>SolidWorks 装配验收</title>
<style>
body{font:16px/1.55 system-ui,sans-serif;color:#10283a;background:#f0f4f7;margin:0}
main{max-width:1100px;margin:auto;padding:22px 30px;background:white}
h1,h2{color:#154661}h2{margin-top:32px}table{width:100%;border-collapse:collapse;margin:12px 0 18px}
th,td{text-align:left;padding:8px;border-bottom:1px solid #cad7df;overflow-wrap:anywhere;vertical-align:top}
th{background:#e9f2f6}td{font-size:14px}strong{color:#036785}
</style><main>""" + payload + "</main></html>"


def write_report(output_root, path, content):
    root = Path(output_root).resolve()
    raw = Path(path)
    candidate = raw if raw.is_absolute() else root / raw
    target = candidate.resolve()
    if not target.is_relative_to(root) or target != candidate or target.suffix.lower() != ".html" or ":" in target.name:
        raise ValueError("The report path must be a fresh HTML file inside the configured output root")
    if not target.parent.is_dir():
        raise ValueError("Create the report output directory before generating the report")
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    return str(target)

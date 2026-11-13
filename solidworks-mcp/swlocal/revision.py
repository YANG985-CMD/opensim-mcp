"""Read-only comparison and package reference evidence for native assemblies."""
import math
from pathlib import Path

from .geometry import validate_rigid_transform


def paired_rows(before, after, mapping):
    def index(rows):
        result = {row["name"]: row for row in rows}
        if len(result) != len(rows):
            raise ValueError("Native names are ambiguous")
        return result

    left, right = index(before), index(after)
    mapping = dict(mapping or {})
    if not set(mapping) <= left.keys() or not set(mapping.values()) <= right.keys():
        raise ValueError("Mappings must name existing items in the corresponding revision")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("Mappings must be one-to-one")
    used = set(mapping.values())
    for name in left.keys() & right.keys():
        if name not in mapping and name not in used:
            mapping[name] = name
    return left, right, mapping


def _pose(before, after):
    a, b = (validate_rigid_transform(t) for t in (before, after))
    distance = 1000 * math.dist(a[9:12], b[9:12])
    if a[:9] == b[:9]:
        return distance, 0.
    cosine = max(-1., min(1., (sum(x*y for x, y in zip(a[:9], b[:9])) - 1.) / 2.))
    return distance, math.degrees(math.acos(cosine))


def _delta(a, b, tolerance=1e-5):
    if a is None or b is None:
        return a != b
    return not math.isclose(a, b, rel_tol=0., abs_tol=tolerance)


def compare_snapshots(before, after, component_map=None, mate_map=None, position_mm=.01, angle_deg=.01):
    if not all(math.isfinite(x) and 0 < x <= 10 for x in (position_mm, angle_deg)):
        raise ValueError("Pose tolerances must be finite and in (0, 10] mm/deg")
    left, right, components = paired_rows(before["components"], after["components"], component_map)
    old_mates, new_mates, mates = paired_rows(before["mates"], after["mates"], mate_map)
    issues = []
    component_changes, mate_changes = [], []
    for name, target in sorted(components.items()):
        a, b = left[name], right[target]
        keys = ("fixed", "referenced_configuration", "geometry_hash")
        changes = {key: [a.get(key), b.get(key)] for key in keys if a.get(key) != b.get(key)}
        if name != target:
            changes["name"] = [name, target]
        if not a.get("geometry_hash") or not b.get("geometry_hash") or any(
            c.get("referenced_configuration") != c.get("loaded_part_configuration") for c in (a, b)
        ):
            issues.append({"component": name, "code": "UNRESOLVED_GEOMETRY_OR_CONFIGURATION"})
        try:
            distance, angle = _pose(a["transform"], b["transform"])
        except ValueError:
            issues.append({"component": name, "code": "POSE_UNAVAILABLE"})
            distance = angle = None
        if distance is not None and (distance > position_mm or angle > angle_deg):
            changes["pose"] = {"translation_mm": distance, "rotation_deg": angle}
        if changes:
            component_changes.append({"before": name, "after": target, "changes": changes})

    for name, target in sorted(mates.items()):
        a, b = old_mates[name], new_mates[target]
        keys = ("mate_type", "alignment", "suppressed", "flipped", "is_limit", "unit",
                "lock_rotation", "native_error", "native_warning", "dimension_driven_state")
        changes = {key: [a.get(key), b.get(key)] for key in keys if a.get(key) != b.get(key)}
        if name != target:
            changes["name"] = [name, target]
        for key in ("minimum", "maximum", "value"):
            if _delta(a.get(key), b.get(key)):
                changes[key] = [a.get(key), b.get(key)]
        mapped_refs = [
            {**ref, "component": components.get(ref["component"], ref["component"])}
            for ref in a.get("references", [])
        ]
        if mapped_refs != b.get("references", []):
            changes["references"] = [a.get("references", []), b.get("references", [])]
        if changes:
            mate_changes.append({"before": name, "after": target, "changes": changes})

    result = {
        "before_configuration": before["configuration"], "after_configuration": after["configuration"],
        "components_added": sorted(right.keys() - set(components.values())),
        "components_removed": sorted(left.keys() - components.keys()),
        "component_changes": component_changes,
        "mates_added": sorted(new_mates.keys() - set(mates.values())),
        "mates_removed": sorted(old_mates.keys() - mates.keys()),
        "mate_changes": mate_changes, "issues": issues,
        "matched_component_count": len(components), "matched_mate_count": len(mates),
        "position_tolerance_mm": position_mm, "angle_tolerance_deg": angle_deg,
        "scope": "Top-level active configuration, native pose, mate references and geometry summaries. Matching summaries do not prove surface equivalence.",
    }
    return result, components


def dimensions(features):
    indexed = {}
    native_names = {}
    for feature in features:
        for row in feature.get("dimensions", []):
            original_name = name = row["name"]
            if name.count("@") >= 2:
                name = name.rsplit("@", 1)[0]
            value = row["value_si"]
            entry = (value, row.get("dimension_type"))
            if name in indexed and native_names[name] == original_name and indexed[name] == entry:
                continue
            if not name or name in indexed or not math.isfinite(value) or len(indexed) >= 256:
                raise ValueError("Dimensions are ambiguous, non-finite or exceed the comparison budget")
            indexed[name] = entry
            native_names[name] = original_name
    return indexed


def compare_dimensions(before, after):
    a, b = dimensions(before), dimensions(after)
    return {
        "added": sorted(b.keys() - a.keys()), "removed": sorted(a.keys() - b.keys()),
        "changed": [
            {"name": name, "before_si": a[name][0], "after_si": b[name][0],
             "before_type": a[name][1], "after_type": b[name][1]}
            for name in sorted(a.keys() & b.keys())
            if a[name][1] != b[name][1] or _delta(a[name][0], b[name][0], 1e-8)
        ],
    }


def package_paths(output_root, assembly_path, expected_parts):
    root = Path(output_root).resolve()
    raw_assembly = Path(assembly_path)
    assembly = (raw_assembly if raw_assembly.is_absolute() else root / raw_assembly).resolve(strict=True)
    if not assembly.is_relative_to(root) or assembly.suffix.lower() != ".sldasm" or not assembly.is_file():
        raise ValueError("Select a saved SLDASM inside the configured output root")
    if not 1 <= len(expected_parts) <= 128:
        raise ValueError("List 1..128 distinct expected part files relative to the assembly directory")
    expected = set()
    for name in expected_parts:
        raw = Path(name)
        path = (assembly.parent / raw).resolve(strict=True)
        if raw.anchor or ".." in raw.parts or not path.is_relative_to(assembly.parent) or path.suffix.lower() != ".sldprt" or not path.is_file():
            raise ValueError("Expected parts must be existing SLDPRT files inside the package")
        if path in expected:
            raise ValueError("Repeated expected part file")
        expected.add(path)
    return assembly, expected


class RevisionTools:
    def compare_assemblies(self, before_document_id, after_document_id, component_map=None, mate_map=None,
                           dimension_components=None, position_mm=.01, angle_deg=.01, include_mass=True):
        from . import cad as n
        if before_document_id == after_document_id:
            raise n.Failure("ARGUMENT", "Choose two different assembly documents")
        before, after = [self.snapshot(key) for key in (before_document_id, after_document_id)]
        if any(d["kind"] != 2 for d in (before, after)):
            raise n.Failure("DOCUMENT_TYPE", "Both explicit documents must be assemblies")
        try:
            result, mapping = compare_snapshots(before, after, component_map, mate_map, position_mm, angle_deg)
        except ValueError as error:
            raise n.Failure("ARGUMENT", str(error)) from error

        requested = dimension_components or []
        if len(requested) > 16 or len(set(requested)) != len(requested) or not set(requested) <= mapping.keys():
            raise n.Failure("ARGUMENT", "Request at most 16 distinct matched baseline components for dimensions")
        model_a, model_b = (self._doc(d["document_id"])["model"] for d in (before, after))
        result["dimensions"] = []
        for name in requested:
            target = mapping[name]
            try:
                parts = [n.member(self._component(model, item), "GetModelDoc2")
                         for model, item in ((model_a, name), (model_b, target))]
                if any(part is None or int(n.member(part, "GetType")) != 1 for part in parts):
                    raise ValueError("Resolved native parts are required")
                diff = compare_dimensions(*(self._features(part, with_dimensions=True) for part in parts))
                result["dimensions"].append({"before": name, "after": target, **diff})
            except (n.Failure, ValueError, n.pythoncom.com_error) as error:
                result["issues"].append({"component": name, "code": "DIMENSIONS_UNAVAILABLE", "detail": str(error)[:200]})
        result["mass"] = {"status": "not_requested"}
        if include_mass:
            try:
                a, b = (self.mass_properties(d["document_id"]) for d in (before, after))
                reliable = all(m["all_parts_have_assigned_materials"] and not m["native_mass_override"] for m in (a, b))
                result["mass"] = {"status": "modeled" if reliable else "needs_review",
                                  "before_kg": a["mass_kg"], "after_kg": b["mass_kg"],
                                  "difference_kg": b["mass_kg"] - a["mass_kg"],
                                  "before_materials_complete": a["all_parts_have_assigned_materials"],
                                  "after_materials_complete": b["all_parts_have_assigned_materials"],
                                  "native_override": a["native_mass_override"] or b["native_mass_override"]}
            except (n.Failure, n.pythoncom.com_error) as error:
                result["mass"] = {"status": "unavailable", "detail": str(error)[:200]}
        for label, doc in (("before", before), ("after", after)):
            latest = self.snapshot(doc["document_id"])
            if latest["state"] != doc["state"]:
                raise n.Failure("STALE_STATE", "Assembly changed during comparison", document_id=doc["document_id"])
            result[label] = {key: doc[key] for key in ("document_id", "title", "configuration", "state")}
        result["status"] = "INCOMPLETE" if result["issues"] else "COMPARED"
        return result

    def verify_package_references(self, assembly_path, expected_parts):
        from . import cad as n
        try:
            assembly, expected = package_paths(self.output, assembly_path, expected_parts)
        except (ValueError, OSError) as error:
            raise n.Failure("PACKAGE_SCOPE", str(error)) from error
        if self._app().GetOpenDocumentByName(str(assembly)) is not None:
            raise n.Failure("PACKAGE_ALREADY_OPEN", "Close the explicitly saved copy yourself before a fresh read-only reopen")
        reopened = self.open_document(str(assembly), editable=False)
        if not n.member(self._doc(reopened['document_id'])['model'], 'IsOpenedReadOnly'):
            raise n.Failure('PACKAGE_NOT_READ_ONLY', 'SOLIDWORKS did not confirm the package was opened read-only')
        actual = set()
        unresolved = []
        for row in reopened["components"]:
            if not row["path"] or not row["geometry_hash"] or row["loaded_part_configuration"] != row["referenced_configuration"]:
                unresolved.append(row["name"])
            if row["path"]:
                path = Path(row["path"]).resolve()
                actual.add(path)
                if not path.is_file() or not path.is_relative_to(assembly.parent):
                    unresolved.append(row["name"])
        missing = sorted(p.relative_to(assembly.parent).as_posix() for p in expected - actual)
        extra = sorted(p.name for p in actual - expected)
        return {"status": "PASS" if not (unresolved or missing or extra) else "FAIL",
                "document_id": reopened["document_id"], "state": reopened["state"],
                "assembly": assembly.name, "expected_part_count": len(expected),
                "unresolved_components": sorted(set(unresolved)), "missing_parts": missing,
                "unexpected_parts": extra, "fresh_read_only_open": True,
                "scope": "Top-level native part references of freshly opened saved package. The document remains open for review."}

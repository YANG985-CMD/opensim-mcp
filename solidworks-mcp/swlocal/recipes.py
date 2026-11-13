"""Exact, versioned joint recipes. Resolve fresh references before every replay."""
import hashlib
import json
import os
from pathlib import Path

from .geometry import validate_mate_values


def _key(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False, ensure_ascii=False).encode()).hexdigest()


def _path_key(path):
    return _key(os.path.normcase(str(Path(path).resolve()))) if path else None


def _face_key(row):
    return _key({key: value for key, value in row.items() if key != "face_id"})


def _plane(geometry, name):
    matches = [p for p in geometry["reference_planes"] if p["plane_name"] == name]
    if len(matches) != 1:
        raise ValueError("Choose one exact native plane for each component")
    return matches[0]


def _pair(row, geometries):
    return [_key(_plane(geometry, row[key])) for geometry, key in zip(geometries, ("plane_a", "plane_b"))]


def _validate(kind, name, axis, guides, position, geometries):
    if kind not in {"revolute", "prismatic"}:
        raise ValueError("Recipes support revolute and two-plane prismatic joints")
    if not isinstance(name, str) or not name or len(name) > 55 or any(c in name for c in "@\\/\r\n"):
        raise ValueError("Choose a 1..55-character joint name")
    if not isinstance(guides, list) or len(guides) != (1 if kind == "revolute" else 2):
        raise ValueError("Revolute requires one guide pair; prismatic requires two")
    if kind == "revolute":
        if not isinstance(axis, list) or len(axis) != 2 or any(type(x) is not int for x in axis):
            raise ValueError("Supply two fresh cylinder face IDs for a revolute joint")
    elif axis is not None:
        raise ValueError("Use two guide plane pairs for a prismatic joint")
    for i, row in enumerate(guides):
        if set(row) != {"plane_a", "plane_b", "distance_mm"}:
            raise ValueError("Each guide must have plane_a, plane_b and distance_mm")
        value = row["distance_mm"]
        validate_mate_values("distance" if value else "coincident", value, 0, 0, "closest", False, False, f"{name}_guide_{i}")
        _pair(row, geometries)
    if kind == "prismatic":
        for key, geometry in zip(("plane_a", "plane_b"), geometries):
            first, second = (_plane(geometry, row[key])["normal"] for row in guides)
            if abs(sum(a*b for a, b in zip(first, second))) > 1e-6:
                raise ValueError("Prismatic guide planes must be orthogonal on both sides")
    if position is not None:
        if set(position) != {"plane_a", "plane_b", "value", "minimum", "maximum"}:
            raise ValueError("Position must contain plane_a, plane_b, value, minimum and maximum")
        validate_mate_values("limit_angle" if kind == "revolute" else "limit_distance",
                             position["value"], position["minimum"], position["maximum"],
                             "closest", False, False, f"{name}_position")
        _pair(position, geometries)


def make_recipe(snapshot, geometries, kind, name, axis_faces, guides, position):
    guides = [{**row, "distance_mm": row.get("distance_mm", 0.)} for row in guides]
    _validate(kind, name, axis_faces, guides, position, geometries)
    axis = None
    if axis_faces is not None:
        axis = []
        for geometry, face_id in zip(geometries, axis_faces):
            matches = [row for row in geometry["faces"] if row["face_id"] == face_id and row["kind"] == "cylinder"]
            if len(matches) != 1:
                raise ValueError("The selected axis is not one fresh cylindrical face")
            axis.append(_face_key(matches[0]))
    return {
        "schema": 1, "kind": kind, "name": name, "source_document_id": snapshot["document_id"],
        "source_path_key": _path_key(snapshot["path"]),
        "part_fingerprints": [row["fingerprint"] for row in geometries], "axis_signatures": axis,
        "guides": [{**row, "plane_signatures": _pair(row, geometries)} for row in guides],
        "position": {**position, "plane_signatures": _pair(position, geometries)} if position is not None else None,
    }


def resolve_recipe(recipe, geometries, names):
    if recipe.get("schema") != 1 or recipe.get("part_fingerprints") != [g["fingerprint"] for g in geometries]:
        raise ValueError("Recipe component geometry or configuration changed. Inspect and capture new references.")
    signatures = recipe["axis_signatures"]
    axis = None
    if signatures is not None:
        if len(signatures) != 2:
            raise ValueError("Recipe must contain two axis signatures")
        axis = []
        for signature, geometry in zip(signatures, geometries):
            matches = [row["face_id"] for row in geometry["faces"] if row["kind"] == "cylinder" and _face_key(row) == signature]
            if len(matches) != 1:
                raise ValueError("A stored cylinder is missing or ambiguous; confirm fresh geometry")
            axis.extend(matches)

    def verify(row):
        params = {key: value for key, value in row.items() if key != "plane_signatures"}
        if _pair(params, geometries) != row.get("plane_signatures"):
            raise ValueError("A referenced plane changed. Confirm its geometry and capture a new recipe.")
        return params

    guides = [verify(row) for row in recipe["guides"]]
    position = verify(recipe["position"]) if recipe["position"] is not None else None
    kind, name = recipe["kind"], recipe["name"]
    _validate(kind, name, axis, guides, position, geometries)

    def native(row):
        params = {key: value for key, value in row.items() if key not in {"plane_a", "plane_b"}}
        return {**params, **{key: {"component": target, "plane_name": row["plane_" + key]} for key, target in zip(("a", "b"), names)}}

    return {
        "kind": kind, "name": name, "plane_pairs": [native(row) for row in guides],
        "position": native(position) if position is not None else None,
        "axis_a": {"component": names[0], "face_id": axis[0]} if axis else None,
        "axis_b": {"component": names[1], "face_id": axis[1]} if axis else None,
    }


class RecipeTools:
    def _recipe_geometry(self, document_id, state, names):
        from . import cad as n
        snapshot = self.snapshot(document_id)
        if snapshot["kind"] != 2 or snapshot["state"] != state:
            raise n.Failure("STALE_OR_NOT_ASSEMBLY", "Read fresh geometry for the exact assembly")
        rows = {row["name"]: row for row in snapshot["components"]}
        if names[0] == names[1] or not set(names) <= rows.keys():
            raise n.Failure("ARGUMENT", "Choose two exact, distinct top-level component names")
        result = []
        for name in names:
            row = rows[name]
            geometry = self.component_geometry(document_id, name)
            if geometry["state"] != state:
                raise n.Failure("STALE_STATE", "Assembly changed while resolving references")
            if not row.get("geometry_hash") or geometry.get("component_document_type") != 1:
                raise n.Failure("UNRESOLVED_COMPONENT", "Recipes require resolved top-level native parts")
            result.append({**geometry, "fingerprint": row["geometry_hash"]})
        return snapshot, result

    def capture_joint_recipe(self, document_id, state, kind, name, component_a, component_b,
                             guides, axis_faces=None, position=None):
        from . import cad as n
        before, geometries = self._recipe_geometry(document_id, state, (component_a, component_b))
        try:
            recipe = make_recipe(before, geometries, kind, name, axis_faces, guides, position)
        except (ValueError, KeyError, TypeError) as error:
            raise n.Failure("RECIPE_ARGUMENT", str(error)) from error
        return {"recipe": recipe, "state": state, "scope": "Export this JSON. Replay resolves new native IDs; no saved face IDs."}

    def apply_joint_recipe(self, document_id, state, recipe, component_a, component_b, preview=True):
        from . import cad as n
        names = (component_a, component_b)
        snapshot, geometries = self._recipe_geometry(document_id, state, names)
        try:
            plan = resolve_recipe(recipe, geometries, names)
        except (ValueError, KeyError, TypeError) as error:
            raise n.Failure("RECIPE_REFERENCE", str(error)) from error
        same_source = (recipe.get("source_document_id") == document_id or
                       recipe.get("source_path_key") is not None and recipe["source_path_key"] == _path_key(snapshot["path"]))
        if preview:
            return {"state": state, "document_id": document_id, "plan": plan,
                    "same_source": same_source, "scope": "Fresh-reference preview. No native solver run."}
        if same_source:
            raise n.Failure("RECIPE_SOURCE", "Apply to an explicit copy or a new assembly, not the recipe source")
        return self.create_joint(document_id, state, **plan)

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from swlocal.acceptance import render_report, write_report
from swlocal.recipes import make_recipe, resolve_recipe
from swlocal.revision import compare_dimensions, compare_snapshots, package_paths
from swlocal.task_journal import AssemblyJournal

IDENTITY = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]


def part(name):
    return {"name": name, "geometry_hash": "abc", "fixed": False, "transform": list(IDENTITY),
            "loaded_part_configuration": "Default", "referenced_configuration": "Default"}


class RevisionTests(unittest.TestCase):
    def test_native_dimensions_repeated_by_features_are_counted_once(self):
        row = {"name": "D1@Sketch1@Part1.Part", "value_si": .004, "dimension_type": 0}
        before = [{"dimensions": [dict(row)]}, {"dimensions": [dict(row)]}]
        after = deepcopy(before)
        for feature in after:
            feature["dimensions"][0]["value_si"] = .005
        difference = compare_dimensions(before, after)
        self.assertEqual(len(difference["changed"]), 1)
        self.assertEqual(difference["changed"][0]["before_si"], .004)
        conflicting = deepcopy(before)
        conflicting[1]["dimensions"][0]["value_si"] = .006
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            compare_dimensions(before, conflicting)
        distinct = deepcopy(before)
        distinct[1]["dimensions"][0]["name"] = "D1@Sketch1@Different.Part"
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            compare_dimensions(before, distinct)

    def test_named_changes_pose_limits_and_dimensions(self):
        left = {"components": [part("rail"), part("sled")], "configuration": "Default",
                "mates": [{"name": "stroke", "value": 50., "maximum": 70., "minimum": 30.,
                           "references": [{"component": "sled", "reference_type": 1}]}]}
        right = deepcopy(left)
        right["components"][1].update(name="sled2", geometry_hash="different")
        right["components"][1]["transform"][10] = .002
        right["mates"][0]["maximum"] = 80.
        right["mates"][0]["references"][0]["component"] = "sled2"
        report, mapping = compare_snapshots(left, right, {"sled": "sled2"})
        self.assertEqual(mapping, {"rail": "rail", "sled": "sled2"})
        self.assertEqual(report["component_changes"][0]["changes"]["pose"]["translation_mm"], 2.)
        self.assertEqual(report["mate_changes"][0]["changes"], {"maximum": [70., 80.]})
        self.assertEqual(report["components_added"], [])
        with self.assertRaises(ValueError):
            compare_snapshots(left, right, {"sled": "rail", "rail": "rail"})

        def size(filename, length):
            return [{"dimensions": [{"name": f"D1@Boss@{filename}", "value_si": length, "dimension_type": 2}]}]

        delta = compare_dimensions(size("a.SLDPRT", .03), size("b.SLDPRT", .026))
        self.assertEqual(delta["changed"][0]["after_si"], .026)

    def test_package_requires_package_relative_real_parts(self):
        with TemporaryDirectory() as root:
            package = Path(root) / "package"
            package.mkdir()
            for p in (package / "model.sldasm", package / "part.sldprt", Path(root) / "outside.sldprt"):
                p.touch()
            result, parts = package_paths(root, str(package / "model.sldasm"), ["part.sldprt"])
            self.assertEqual(result.name, "model.sldasm")
            self.assertEqual({p.name for p in parts}, {"part.sldprt"})
            with self.assertRaises(ValueError):
                package_paths(root, str(result), ["../outside.sldprt"])


class RecipeTests(unittest.TestCase):
    def test_revolute_rebinds_fresh_ids_and_refuses_changed_geometry(self):
        geometry = {"fingerprint": "fingerprint", "faces": [
            {"face_id": 2, "kind": "cylinder", "diameter_mm": 12.}],
            "reference_planes": [{"plane_name": "P", "normal": [0, 0, 1], "point_mm": [0, 0, 0]}]}
        recipe = make_recipe({"document_id": "source", "path": ""}, [geometry, geometry], "revolute", "Hinge",
                             [2, 2], [{"plane_a": "P", "plane_b": "P"}], None)
        fresh = deepcopy(geometry)
        fresh["faces"][0]["face_id"] = 18
        plan = resolve_recipe(recipe, [fresh, geometry], ["base", "moving"])
        self.assertEqual(plan["axis_a"], {"component": "base", "face_id": 18})
        changed = deepcopy(fresh)
        changed["faces"][0]["diameter_mm"] = 14.
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            resolve_recipe(recipe, [changed, geometry], ["base", "moving"])
        fresh["faces"].append({**fresh["faces"][0], "face_id": 19})
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            resolve_recipe(recipe, [fresh, geometry], ["base", "moving"])

    def test_prismatic_requires_orthogonal_planes(self):
        fixture = {"fingerprint": "p", "faces": [], "reference_planes": [
            {"plane_name": "X", "normal": [1, 0, 0], "point_mm": [0, 0, 0]},
            {"plane_name": "Y", "normal": [0, 1, 0], "point_mm": [0, 0, 0]},
        ]}
        source = {"document_id": "source", "path": ""}
        guides = [{"plane_a": name, "plane_b": name} for name in ("X", "Y")]
        recipe = make_recipe(source, [fixture, fixture], "prismatic", "Slide", None, guides, None)
        self.assertEqual(len(resolve_recipe(recipe, [fixture, fixture], ["rail", "sled"])["plane_pairs"]), 2)
        with self.assertRaisesRegex(ValueError, "orthogonal"):
            make_recipe(source, [fixture, fixture], "prismatic", "Slide", None, [guides[0]] * 2, None)


class TraceTests(unittest.TestCase):
    def test_stop_on_partial_failure_and_reload(self):
        class Error(Exception):
            pass

        with TemporaryDirectory() as root:
            calls = []
            state = "s0"

            def call(action, args, write=False):
                nonlocal state
                if action == "snapshot":
                    return {"state": state, "kind": 2}
                calls.append(args["positions"][0]["value"])
                if len(calls) == 2:
                    raise Error(json.dumps({"code": "CAD_TIMEOUT", "outcome_unknown": True}))
                state = "s1"
                return {"state": state, "driven_mates": []}

            journal = AssemblyJournal(root)
            steps = [{"action": "set_mate_positions", "parameters": {"positions": [{"mate_name": "stroke", "value": i}]}}
                     for i in range(3)]
            record = journal.run(call, "doc", "s0", steps, "Failure replay", Error)
            self.assertEqual(calls, [0, 1])
            self.assertEqual(record["completed_steps"], 1)
            self.assertEqual(record["steps"][-1]["error_code"], "CAD_TIMEOUT")
            self.assertIsNone(record["final_state"])
            self.assertEqual(AssemblyJournal(root).get(record["task_id"])["status"], "failed")


class ReportTests(unittest.TestCase):
    def test_report_escapes_labels_and_rejects_missing_evidence(self):
        side = {"title": "<script>not safe</script>"}
        comparison = {"status": "COMPARED", "before": side, "after": side, "mass": {"status": "modeled"},
                      **{k: [] for k in ("dimensions", "issues", "component_changes", "mate_changes",
                                          "components_added", "components_removed", "mates_added", "mates_removed")}}
        audit = {"status": "PASS", "state": "s", "document_id": "doc",
                 "issues": [], "clearances": [], "limits": [], "interferences": []}
        status, report = render_report("<b>Test</b>", comparison, audit, None, None, None)
        self.assertEqual(status, "REVIEW")
        self.assertNotIn("<script>", report)
        self.assertIn("&lt;script&gt;", report)
        with TemporaryDirectory() as root:
            write_report(root, "report.html", report)
            with self.assertRaises(FileExistsError):
                write_report(root, "report.html", report)
            with self.assertRaises(ValueError):
                write_report(root, "../outside.html", report)

    def test_mcp_report_joins_verified_files_and_marks_stale_reopen(self):
        from unittest.mock import patch
        from swlocal import server
        from swlocal.delivery import DeliveryChecks

        comparison = {"status": "COMPARED", "before": {"title": "R1", "state": "a"},
                      "after": {"title": "R2", "state": "b"}, "mass": {"status": "modeled"},
                      **{k: [] for k in ("dimensions", "issues", "component_changes", "mate_changes",
                                          "components_added", "components_removed", "mates_added", "mates_removed")}}
        audit = {"status": "PASS", "state": "b", "document_id": "candidate",
                 "issues": [], "clearances": [], "limits": [], "interferences": []}
        reference = {"status": "PASS", "document_id": "candidate", "state": "b", "assembly": "r2.sldasm",
                     "expected_part_count": 1, "unresolved_components": [], "missing_parts": [], "unexpected_parts": []}

        def call(action, args, write=False):
            if action == "snapshot":
                return {"state": "a" if args["document_id"] == "before" else "b"}
            return {"compare_assemblies": comparison, "audit_assembly": audit,
                    "verify_package_references": reference}[action]

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            checks = DeliveryChecks(root)
            baseline = checks.capture(["r2.sldasm", "part.sldprt"])["baseline_id"]
            (root / "r2.sldasm").write_bytes(b"synthetic assembly")
            (root / "part.sldprt").write_bytes(b"synthetic part")
            with patch.object(server, "_get_delivery_checks", return_value=checks), \
                 patch.object(server, "_package_evidence", {}), patch.object(server, "call", side_effect=call):
                server.sw_verify_package_references("r2.sldasm", ["part.sldprt"])
                passed = server.sw_write_acceptance_report("before", "candidate", "passed.html",
                                                          delivery_baseline_id=baseline)
                self.assertEqual(passed["status"], "CHECKS_PASSED")
                (root / "part.sldprt").write_bytes(b"externally edited")
                stale = server.sw_write_acceptance_report("before", "candidate", "stale.html",
                                                         delivery_baseline_id=baseline)
                self.assertEqual(stale["status"], "REVIEW")
                self.assertIn("STALE", (root / "stale.html").read_text(encoding="utf-8"))


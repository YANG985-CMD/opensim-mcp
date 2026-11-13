from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from swlocal.delivery import DeliveryChecks


class DeliveryTests(unittest.TestCase):
    def test_fresh_requires_new_or_changed_nonempty_content(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("update.step", "stale.stl", "removed.sldprt"):
                (root / name).write_bytes(b"old")
            checks = DeliveryChecks(root)
            names = ["update.step", "stale.stl", "removed.sldprt", "new.sldasm", "empty.stp"]
            token = checks.capture(names)["baseline_id"]
            (root / "update.step").write_bytes(b"new")
            (root / "stale.stl").touch()
            (root / "removed.sldprt").unlink()
            (root / "new.sldasm").write_bytes(b"assembly")
            (root / "empty.stp").touch()
            report = checks.verify(token)
            self.assertEqual(report["status"], "needs_review")
            self.assertEqual(
                [row["status"] for row in report["files"]],
                ["updated", "unchanged", "missing", "new", "empty"],
            )
            token = checks.capture(["update.step"])["baseline_id"]
            (root / "update.step").write_bytes(b"revision two")
            self.assertEqual(checks.verify(token)["status"], "fresh")

    def test_rejects_out_of_scope_inputs_and_unknown_baseline(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            checks = DeliveryChecks(root / "output")
            for paths in (["../escape.stl"], [str(root / "escape.stl")], ["notes.txt"], ["A.stl", "a.stl"], ["model.exe:hidden.stl"]):
                with self.subTest(paths=paths), self.assertRaises(ValueError):
                    checks.capture(paths)
            with self.assertRaises(ValueError):
                checks.verify("unknown")

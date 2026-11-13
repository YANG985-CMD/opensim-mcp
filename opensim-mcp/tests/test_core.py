from pathlib import Path
import math
import sys
import time

import pytest

from opensim_mcp import core

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def cfg(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for name in ("slider.osim", "slider.trc"):
        (inputs / name).write_bytes((EXAMPLES / name).read_bytes())
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    return core.Settings((inputs,), tmp_path / "results", temporary, None, 5)


def test_summary_does_not_call_native(cfg, monkeypatch):
    monkeypatch.setattr(core.subprocess, "Popen", lambda *a, **k: pytest.fail("Native process launched"))
    result = core.inspect_model(cfg, str(cfg.allowed_roots[0] / "slider.osim"))
    assert result["native_model_initialized"] is False
    assert result["counts"] == {"bodies": 1, "joints": 1, "coordinates": 1, "markers": 3,
                                "forces": 0, "muscles_by_class_name": 0}


@pytest.mark.parametrize("xml", [
    b'<!DOCTYPE a [<!ENTITY e "oops">]><OpenSimDocument><Model name="&e;"/></OpenSimDocument>',
    b'<!DOCTYPE a SYSTEM "file:///C:/secret"><OpenSimDocument><Model/></OpenSimDocument>',
    b'<OpenSimDocument><Model/><Model/></OpenSimDocument>',
    b'<OpenSimDocument xmlns="urn:bad"><Model/></OpenSimDocument>',
    b'<OpenSimDocument><Model>' + b'<x>'*101 + b'</x>'*101 + b'</Model></OpenSimDocument>'
])
def test_prohibited_xml(xml):
    with pytest.raises(core.InputError):
        core.xml_model(xml)


def test_roots_and_traversal(cfg, tmp_path):
    outside = tmp_path / "outside.osim"
    outside.write_bytes((EXAMPLES / "slider.osim").read_bytes())
    for path in (str(outside), str(cfg.allowed_roots[0] / ".." / "outside.osim"),
                 "slider.osim", r"\\server\share\model.osim", r"C:\file.osim:stream"):
        with pytest.raises(core.InputError):
            cfg.input_path(path, ".osim")


def test_oversize(tmp_path):
    path = tmp_path / "large"
    path.write_bytes(b"12345")
    with pytest.raises(core.InputError):
        core.bounded_read(path, 4)


def test_staging_removes_only_visuals_and_rejects_external_dependencies():
    original = (EXAMPLES / "slider.osim").read_bytes()
    with_mesh = original.replace(b'<mass>1</mass>', b'<attached_geometry><Mesh><mesh_file>../../secret.obj</mesh_file></Mesh></attached_geometry><mass>1</mass>')
    staged, markers, removed = core.prepare_model(with_mesh)
    assert b"mesh_file" not in staged and "attached_geometry" in removed
    assert len(markers) == 3 and b"secret.obj" in with_mesh
    for dependency in (b'<external_loads_file>C:/secret.xml</external_loads_file>', b'<Controller file="C:/secret.xml"/>'):
        with pytest.raises(core.InputError):
            core.prepare_model(original.replace(b'</Model>', dependency + b'</Model>'))


@pytest.mark.parametrize("change", [
    lambda b: b.replace(b'10\t10\t11\t3\tm', b'10\t10\t12\t3\tm'),
    lambda b: b.replace(b'10\t10\t11\t3\tm', b'10\t10\t11\t3\tcm'),
    lambda b: b.replace(b'2\t0.1\t0.01', b'2\t0.0\t0.01'),
    lambda b: b.replace(b'2\t0.1\t0.01', b'2\t0.1\tnan'),
    lambda b: b.replace(b'2\t0.1\t0.01', b'2\t0.1\tinf'),
    lambda b: b.replace(b'M2\t\t\tM3', b'M1\t\t\tM3'),
    lambda b: b.replace(b'X2\tY2\tZ2', b'X3\tY3\tZ3'),
    lambda b: b.replace(b'0.01\t0\t0\t0.01', b'0.01\t0\t0.01'),
])
def test_bad_trc(change):
    with pytest.raises(core.InputError):
        core.trc_info(change((EXAMPLES / "slider.trc").read_bytes()))


def test_good_trc():
    data = core.trc_info((EXAMPLES / "slider.trc").read_bytes())
    assert data["frames"] == 11 and data["times"][::10] == [0.0, 1.0]


@pytest.mark.parametrize("kwargs", [
    {"start_time": -1}, {"end_time": 2}, {"start_time": .05}, {"start_time": 1, "end_time": 0},
    {"start_time": math.nan}, {"marker_weights": {}}, {"marker_weights": {"UNKNOWN": 1}},
    {"marker_weights": {"M1": 0}}, {"marker_weights": {"M1": math.inf}},
])
def test_ik_rejects_before_execution(cfg, monkeypatch, kwargs):
    cfg = core.Settings(cfg.allowed_roots, cfg.results_root, cfg.temp_root, "configured-but-unused", 5)
    monkeypatch.setattr(core, "execute", lambda *a, **k: pytest.fail("Invalid job reached native code"))
    with pytest.raises(core.InputError):
        core.run_ik(cfg, str(cfg.allowed_roots[0] / "slider.osim"), str(cfg.allowed_roots[0] / "slider.trc"), **kwargs)
    assert not cfg.results_root.exists()


@pytest.mark.parametrize("body", [
    "nRows=2\nnColumns=2\nendheader\ntime q\n0 0\n1 nan\n",
    "nRows=2\nnColumns=2\nendheader\ntime q\n0 0\n0 1\n",
    "nRows=3\nnColumns=2\nendheader\ntime q\n0 0\n1 1\n",
    "endheader\ntime q\n0 0\n1 1 2\n",
])
def test_invalid_native_output(tmp_path, body):
    path = tmp_path / "bad.mot"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(core.InputError):
        core.read_motion(path)


def test_native_failure_cleans_staging_and_no_published_result(cfg, monkeypatch):
    cfg = core.Settings(cfg.allowed_roots, cfg.results_root, cfg.temp_root, "unused", 5)
    original = (cfg.allowed_roots[0] / "slider.osim").read_bytes()
    def fail(*args):
        raise TimeoutError("deliberate test timeout")
    monkeypatch.setattr(core, "execute", fail)
    with pytest.raises(TimeoutError):
        core.run_ik(cfg, str(cfg.allowed_roots[0] / "slider.osim"), str(cfg.allowed_roots[0] / "slider.trc"))
    assert list(cfg.temp_root.iterdir()) == []
    assert not cfg.results_root.exists()
    assert (cfg.allowed_roots[0] / "slider.osim").read_bytes() == original


def test_timeout_kills_real_child_process(cfg, monkeypatch):
    monkeypatch.setenv('OPENSIM_MCP_TOOL_BACKEND', 'cli')
    cfg = core.Settings(cfg.allowed_roots, cfg.results_root, cfg.temp_root, sys.executable, 1)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        core.execute(cfg, ["-B", "-c", "import time; time.sleep(20)"], cfg.temp_root, 1)
    assert time.monotonic() - started < 5


def test_child_stdin_is_closed_and_error_exit_is_failure(cfg, monkeypatch):
    monkeypatch.setenv('OPENSIM_MCP_TOOL_BACKEND', 'cli')
    cfg = core.Settings(cfg.allowed_roots, cfg.results_root, cfg.temp_root, sys.executable, 2)
    result = core.execute(cfg, ["-B", "-c", "import sys; assert sys.stdin.read() == ''; print('ok')"], cfg.temp_root, 2)
    assert result["log_tail"].strip() == "ok"
    with pytest.raises(core.InputError, match="exited 7"):
        core.execute(cfg, ["-B", "-c", "raise SystemExit(7)"], cfg.temp_root, 2)


def test_result_readback_policy_and_preview(cfg, tmp_path):
    cfg.results_root.mkdir()
    path = cfg.results_root / "result.mot"
    path.write_text("nRows=2\nnColumns=2\ninDegrees=no\nendheader\ntime q\n0 0\n1 0.1\n", encoding="utf-8")
    data = core.motion_summary(cfg, str(path), 1)
    assert data["preview"] == [[0.0, 0.0]]
    assert data["ranges"]["q"] == {"min": 0.0, "max": 0.1}
    with pytest.raises(core.InputError):
        core.motion_summary(cfg, str(tmp_path / "outside.mot"))
    with pytest.raises(core.InputError):
        core.motion_summary(cfg, str(path), 101)


def test_oversize_model_text_is_bounded():
    original = (EXAMPLES / "slider.osim").read_bytes()
    data = core.summary(original.replace(b'mcp_slider', b'x'*2000))
    assert len(data["name"]) < 600 and data["name"].endswith("[truncated]")


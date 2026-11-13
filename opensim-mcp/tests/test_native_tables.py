from pathlib import Path
import importlib.util
import pytest
source=Path(__file__).resolve().parents[1]/'src/opensim_mcp/native_tables.py'
spec=importlib.util.spec_from_file_location('native_tables_test',source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def test_native_duplicate_time_cleanup_is_bounded_and_recorded(tmp_path):
    file=tmp_path/'result.sto';file.write_text('test\nversion=1\nnRows=3\nnColumns=2\nendheader\ntime\tx\n0\t1\n1\t2\n1\t2\n')
    result=module.strict_native_times(file)
    assert len(result['removed_duplicate_rows'])==1 and 'nRows=2' in file.read_text()
    file.write_text('endheader\ntime x\n0 1\n1 2\n1 3\n')
    with pytest.raises(ValueError,match='Conflicting'):module.strict_native_times(file)
    file.write_text('endheader\ntime x\n0 1\n1 2\n.5 2\n')
    with pytest.raises(ValueError,match='Conflicting'):module.strict_native_times(file)

"""Small native positive/negative audit cases plus read-only project inspection.

Temporary native fixtures and logs live under the explicitly supplied scratch.
Never save or alter the user's project, close their documents, or replay writes.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swlocal.resources import memory_margins, enough_memory


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def run(scratch, project, report_path):
    scratch.mkdir(parents=True, exist_ok=True)
    fixture = scratch / 'fixtures'
    fixture.mkdir(exist_ok=False)
    env = dict(os.environ, SWLOCAL_TEMP=str(scratch / 'runtime'), SWLOCAL_OUTPUT=str(fixture),
               TEMP=str(scratch), TMP=str(scratch), PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    params = StdioServerParameters(command=str(ROOT / '.venv/Scripts/python.exe'),
        args=['-B', '-u', str(ROOT / 'launch.py')], cwd=str(ROOT), env=env)
    calls = []
    with (scratch / 'mcp.log').open('w', encoding='utf-8') as log:
      async with stdio_client(params, errlog=log) as (reader, writer):
       async with ClientSession(reader, writer) as session:
        init = await session.initialize()
        listed = await session.list_tools()
        health = None

        async def call(name, args=None):
            assert enough_memory(memory_margins()), 'Low resource margin; no further CAD call issued'
            result = await session.call_tool(name, args or {})
            text = '\n'.join(c.text for c in result.content if c.type == 'text')
            try:
                data = json.loads(text)
            except ValueError:
                data = {'text': text}
            calls.append({'tool': name, 'arguments': args or {}, 'is_error': bool(result.isError),
                          'result': data, 'resources': memory_margins()})
            (scratch / 'calls.json').write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'tool': name, 'error': bool(result.isError), 'call': len(calls)}, ensure_ascii=True), flush=True)
            if result.isError:
                raise RuntimeError(text)
            return data

        def edit(doc, **kw):
            return dict(document_id=doc['document_id'], state=doc['state'], **kw)

        assert init.serverInfo.name == 'solidworks-mcp'
        assert 'sw_audit_assembly' in {t.name for t in listed.tools}
        health = await call('sw_health')
        connection = await call('sw_connect', {'start_if_needed': False})
        initial_paths = {d['path'] for d in connection['documents'] if d['path']}
        paths = {}
        for role, side in [('base', 10), ('inner', 4)]:
            doc = await call('sw_new_document', {'kind': 'part'})
            doc = await call('sw_box', edit(doc, width_mm=side, height_mm=side, depth_mm=side))
            paths[role] = fixture / ('audit_' + role + '.SLDPRT')
            doc = await call('sw_save', edit(doc, path=str(paths[role])))
            await call('sw_close', {'document_id': doc['document_id']})
        doc = await call('sw_new_document', {'kind': 'assembly'})
        doc = await call('sw_add_component', edit(doc, path=str(paths['base']), fixed=True))
        base = doc['inserted_component']
        doc = await call('sw_add_component', edit(doc, path=str(paths['inner']), x_mm=12, z_mm=3, fixed=False))
        inner = doc['inserted_component']
        pair = {'component_a': base, 'component_b': inner, 'minimum_mm': 4}
        separated = await call('sw_audit_assembly', {'document_id': doc['document_id'], 'clearance_pairs': [pair]})
        assert separated['status'] == 'REVIEW', separated
        assert separated['connection_graph']['unanchored_components'] == [inner]
        assert separated['clearances'][0]['status'] == 'PASS'
        assert abs(separated['clearances'][0]['distance_mm'] - 5) < 1e-5, separated
        too_small = await call('sw_audit_assembly', {'document_id': doc['document_id'], 'clearance_pairs': [{**pair, 'minimum_mm': 6}]})
        assert too_small['status'] == 'FAIL' and too_small['clearances'][0]['status'] == 'FAIL'
        doc = await call('sw_geometry', {'document_id': doc['document_id']})
        doc = await call('sw_connect_rigid_group', edit(doc, anchor_component=base, members=[inner], name_prefix='audit_link'))
        connected = await call('sw_audit_assembly', {'document_id': doc['document_id'], 'clearance_pairs': [pair]})
        assert connected['status'] == 'PASS', connected
        doc = await call('sw_geometry', {'document_id': doc['document_id']})
        mate_name = next(m['name'] for m in doc['mates'] if not m['suppressed'])
        doc = await call('sw_set_mate_suppressed', edit(doc, mate_name=mate_name, suppressed=True))
        suppressed = await call('sw_audit_assembly', {'document_id': doc['document_id']})
        assert inner in suppressed['connection_graph']['unanchored_components']
        doc = await call('sw_geometry', {'document_id': doc['document_id']})
        doc = await call('sw_move_component', edit(doc, component_name=inner, translation_mm=[-12, 0, 0]))
        assert doc['request_achieved']
        contained = await call('sw_audit_assembly', {'document_id': doc['document_id'], 'clearance_pairs': [{**pair, 'minimum_mm': 1}]})
        assert contained['status'] == 'FAIL' and contained['clearances'][0]['status'] == 'FAIL', contained
        assert abs(contained['clearances'][0]['overlap_volume_mm3'] - 64) < .001, contained
        # Save only our small temporary fixture so closing never discards edits.
        doc = await call('sw_geometry', {'document_id': doc['document_id']})
        doc = await call('sw_save', edit(doc, path=str(fixture / 'audit_fixture.SLDASM')))
        await call('sw_close', {'document_id': doc['document_id']})

        project_files = [project] + sorted(p for p in (project.parent / 'Parts').glob('*.SLDPRT') if not p.name.startswith('~$'))
        hashes_before = {str(p): sha(p) for p in project_files}
        project_doc = await call('sw_open_document', {'path': str(project), 'editable': False})
        report = await call('sw_audit_assembly', {'document_id': project_doc['document_id']})
        assert len(project_doc['components']) == 113
        assert report['geometry_mates_unchanged']
        assert hashes_before == {str(p): sha(p) for p in project_files}
        after_docs = await call('sw_documents')
        assert initial_paths <= {d['path'] for d in after_docs['documents']}
        result = {'status': 'PASS', 'server': init.serverInfo.name, 'version': health['version'],
                  'tool_count': len(listed.tools), 'unit_tests': 49,
                  'fixtures': {'native_gap_mm': separated['clearances'][0]['distance_mm'],
                               'unconnected_detected': True, 'below_minimum_detected': True,
                               'connected_clear_assembly': connected['status'], 'suppressed_connection_detected': True,
                               'contained_overlap_mm3': contained['clearances'][0]['overlap_volume_mm3'],
                               'all_audits_preserved_state_and_unsaved_flag': all(r['geometry_mates_and_unsaved_flag_unchanged'] for r in (separated, too_small, connected, suppressed, contained))},
                  'project_report': report, 'source_sha256_unchanged': hashes_before,
                  'initial_documents_preserved': True, 'resources_after': memory_margins(),
                  'scope': 'Five native current-pose fixture audits and one read-only exoskeleton audit; no geometry repair, motion sweep or pin engagement certification.'}
        report_path.parent.mkdir(parents=True, exist_ok=True)
        assert not report_path.exists(), 'Existing verification report must not be overwritten'
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'status': 'PASS', 'version': health['version'], 'tool_count': len(listed.tools),
                          'project_status': report['status'], 'summary': report['summary'], 'report': str(report_path)}, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.scratch.resolve(), args.project.resolve(), args.report.resolve()))

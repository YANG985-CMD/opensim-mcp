"""Measured quantities and explicitly configured acceptance limits; portable reports."""
from __future__ import annotations
import base64
from html import escape
import json
import math
from pathlib import Path

from .core import InputError, bounded_read, read_motion, xml_model


def metrics_for(result, stage, parameters, residuals):
    metrics = dict(result.get('quality', {}))
    if 'joint_reaction_quality' in result: metrics['joints'] = result['joint_reaction_quality']
    for spec in residuals:
        if spec['stage'] != stage: continue
        table = read_motion(Path(next(p for p in result['files'] if p.endswith('inverse_dynamics.sto'))))
        _, model = xml_model(bounded_read(Path(parameters['model_path']), 20 * 1024**2))
        mass = sum(float(e.findtext('mass', '0')) for e in model.iter('Body'))
        gravity = math.sqrt(sum(float(v)**2 for v in model.findtext('gravity', '0 0 0').split()))
        for key, columns, unit in [('force', spec['force_columns'], 'N'), ('moment', spec['moment_columns'], 'Nm')]:
            if not columns: continue
            if set(columns) - set(table['columns']): raise InputError('Missing explicit residual columns.')
            indices = [table['columns'].index(c) for c in columns]
            norms = [math.sqrt(sum(row[i]**2 for i in indices)) for row in table['rows']]
            metrics['residual_' + key + '_rms_' + unit] = math.sqrt(sum(n*n for n in norms)/len(norms))
            metrics['residual_' + key + '_peak_' + unit] = max(norms)
        metrics['mass_kg'] = mass; metrics['gravity_m_s2'] = gravity
        metrics['residual_force_rms_fraction_BW'] = metrics['residual_force_rms_N']/(mass*gravity) if mass*gravity else None
    return metrics


def evaluate(checks, stages):
    result = []
    for check in checks:
        value = stages.get(check['stage'], {}).get('metrics', {})
        for key in check['metric'].split('.'):
            value = value.get(key) if isinstance(value, dict) else None
        assessed = type(value) in {int, float} and math.isfinite(value)
        passed = (value <= check['limit'] if check['comparison'] == 'max' else value >= check['limit']) if assessed else None
        status = 'not_assessed' if not assessed else ('pass' if passed else check['severity'])
        result.append({**check, 'value': value if assessed else None, 'status': status})
    overall = 'not_assessed' if not result else ('needs_review' if any(c['status'] != 'pass' for c in result) else 'configured_checks_passed')
    return overall, result


def write_reports(folder, record, checks, plots):
    """HTML embeds bounded PNGs, escapes all data, and has no executable content."""
    folder.mkdir(parents=True, exist_ok=True)
    verdict, assessed = evaluate(checks, record['stages'])
    report = {**record, 'quality_status': verdict, 'checks': assessed,
              'interpretation': 'Computation completion and configured checks do not establish physiological or clinical validity.', 'plots': plots}
    (folder/'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    title = escape(record['name'])
    html = ['<!doctype html><html lang="en"><meta charset="utf-8">',
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'">',
            '<title>' + title + '</title><style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 24px;line-height:1.6;color:#203448}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:8px;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f8;padding:16px}img{max-width:100%}h1,h2{line-height:1.2}</style>',
            '<h1>' + title + '</h1><p>Quality: ' + escape(verdict) + '</p><p>' + escape(report['interpretation']) + '</p>',
            '<h2>Configured checks</h2><table><tr><th>Check</th><th>Value</th><th>Limit</th><th>Status</th></tr>']
    md = ['# ' + record['name'].replace('\n', ' '), '', 'Quality: ' + verdict, '', report['interpretation'], '', '| Check | Value | Limit | Status |', '| --- | --- | --- | --- |']
    for c in assessed:
        cells = [c['id'], str(c['value']) + ' ' + c['unit'], c['comparison'] + ' ' + str(c['limit']) + ' ' + c['unit'], c['status']]
        html.append('<tr>' + ''.join('<td>' + escape(v) + '</td>' for v in cells) + '</tr>')
        md.append('| ' + ' | '.join(v.replace('|', '\\|').replace('\n',' ') for v in cells) + ' |')
    html.append('</table><h2>Curves</h2>')
    for plot in plots:
        png = bounded_read(Path(plot['image_file']), 8 * 1024**2)
        html.append('<p>' + escape(plot['title']) + '</p><img alt="Result curve" src="data:image/png;base64,' + base64.b64encode(png).decode() + '">')
        md += ['', '![Result curve](' + Path(plot['image_file']).relative_to(folder).as_posix() + ')']
    details = json.dumps({k:v for k,v in report.items() if k != 'plots'}, ensure_ascii=False, indent=2)
    html += ['<h2>Stage history, measured quantities and provenance</h2><pre>' + escape(details) + '</pre></html>']
    md += ['', '## Stage history, measured quantities and provenance', '', '```json', details.replace('```','` ` `'), '```', '']
    (folder/'report.html').write_text('\n'.join(html), encoding='utf-8')
    (folder/'report.md').write_text('\n'.join(md), encoding='utf-8')
    return {'quality_status': verdict, 'html_file': str(folder/'report.html'), 'markdown_file': str(folder/'report.md'), 'report_file': str(folder/'report.json')}

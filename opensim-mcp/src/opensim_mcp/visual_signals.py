"""Explicit MATLAB/CSV signal binding for body-part independent OpenSim viewers."""
from __future__ import annotations

import bisect
import csv
import io
import json
import math
import secrets
import tempfile
import uuid
from pathlib import Path

from .core import InputError, bounded_read, read_motion
from .projects import digest


def _number(value, name):
    if type(value) not in {int, float} or not math.isfinite(value):
        raise InputError(name+' must be finite numeric data.')
    return float(value)


def _text(value, name, maximum=200):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise InputError(name+' must be short nonempty text.')
    return value


def component_ids(scene):
    first = scene['frames'][0]
    return dict(frame=set(first['transforms']), body=set(scene['frame_to_body'].values()),
                coordinate=set(scene['coordinate_units']), muscle=set(scene.get('muscle_names', [])), marker=set(first['markers']))


def sample(times, values, targets, method, max_gap):
    if method not in {'none', 'linear', 'previous'}:
        raise InputError('Interpolation must be none, linear or previous.')
    if min(targets) < times[0]-1e-9 or max(targets) > times[-1]+1e-9:
        raise InputError('Signal does not cover the animation; extrapolation is forbidden.')
    output, interpolated = [], 0
    for t in targets:
        j = bisect.bisect_left(times, t)
        exact = next((i for i in (j-1, j) if 0 <= i < len(times) and abs(times[i]-t) <= 1e-9), None)
        if exact is not None:
            output.append(values[exact])
            continue
        if method == 'none':
            raise InputError('Signal and animation samples differ; choose explicit interpolation.')
        if not 0 < j < len(times):
            raise InputError('Signal extrapolation is forbidden.')
        gap = times[j]-times[j-1]
        if gap > max_gap+1e-12:
            raise InputError('Signal interpolation would bridge a gap above max_gap_s.')
        weight = (t-times[j-1])/gap
        output.append(values[j-1] if method == 'previous' else values[j-1]+weight*(values[j]-values[j-1]))
        interpolated += 1
    return output, interpolated


def read_source(cfg, spec):
    required = {'path', 'label', 'time_column', 'time_unit', 'time_offset_s', 'interpolation', 'max_gap_s', 'channels'}
    optional = {'delimiter', 'model_physics_signature', 'schema'}
    if not isinstance(spec, dict) or not required <= set(spec) or set(spec)-required-optional:
        raise InputError('Signal source requires explicit path, label, time column/unit/offset, interpolation, max_gap_s and channels.')
    _text(spec['label'], 'source label')
    if 'schema' in spec and spec['schema'] != 'opensim_signal_source_v1':
        raise InputError('Unsupported signal source schema.')
    if spec['time_unit'] not in {'s', 'ms'}:
        raise InputError('Declare time_unit as s or ms.')
    offset = _number(spec['time_offset_s'], 'time_offset_s')
    gap = _number(spec['max_gap_s'], 'max_gap_s')
    if not 0 < gap <= 1e6 or abs(offset) > 1e9:
        raise InputError('Invalid time offset or positive interpolation gap limit.')
    if spec['interpolation'] not in {'none', 'linear', 'previous'}:
        raise InputError('Declare interpolation as none, linear or previous.')
    path = Path(spec['path'])
    if path.suffix.lower() not in {'.csv', '.mot', '.sto'}:
        raise InputError('Signals must be UTF-8 CSV or MOT/STO.')
    source = cfg.input_path(str(path), path.suffix.lower())
    raw = bounded_read(source, 16*1024**2)
    if path.suffix.lower() == '.csv':
        delimiter = spec.get('delimiter', ',')
        if delimiter not in {',', ';', '\t'}:
            raise InputError('Supported explicit delimiters: comma, semicolon or tab.')
        try:
            records = csv.reader(io.StringIO(raw.decode('utf-8-sig')), delimiter=delimiter, strict=True)
            columns = next(records)
            if len(columns) > 200 or len(set(columns)) != len(columns) or any(not c or len(c) > 200 for c in columns):
                raise InputError('CSV headers must be unique bounded column names.')
            rows = []
            for record in records:
                if not record:
                    continue
                if len(record) != len(columns):
                    raise InputError('CSV row width differs from the header.')
                rows.append(record)
                if len(rows) > 20000:
                    raise InputError('At most 20000 source samples per signal source.')
        except (UnicodeError, csv.Error, StopIteration) as exc:
            raise InputError('Invalid UTF-8 numeric CSV.') from exc
    else:
        with tempfile.TemporaryDirectory(prefix='visual-signal-', dir=cfg.temp_root) as directory:
            pinned = Path(directory)/('signal'+path.suffix.lower())
            pinned.write_bytes(raw)
            table = read_motion(pinned)
        columns, rows = table['columns'], table['rows']
    if not 2 <= len(rows) <= 20000 or spec['time_column'] not in columns:
        raise InputError('Need 2..20000 samples and an explicit existing time column.')
    channels = spec['channels']
    if not isinstance(channels, list) or not 1 <= len(channels) <= 32:
        raise InputError('Provide 1..32 explicitly labeled signal channels.')
    names = []
    for channel in channels:
        if not isinstance(channel, dict) or not {'column', 'label', 'unit'} <= set(channel) or set(channel)-{'column', 'label', 'unit', 'component'}:
            raise InputError('Each signal channel requires column, label, unit and optional component binding.')
        for key in ('column', 'label', 'unit'):
            _text(channel[key], key)
        if channel['column'] == spec['time_column'] or channel['column'] not in columns or channel['column'] in names:
            raise InputError('Signal columns must exist, be unique and differ from time.')
        names.append(channel['column'])
    def values(column):
        index = columns.index(column)
        try:
            result = [float(row[index]) for row in rows]
        except (ValueError, TypeError) as exc:
            raise InputError('Time and chosen signal columns must contain only numeric data.') from exc
        if any(not math.isfinite(v) for v in result):
            raise InputError('Missing/nonfinite signal samples are not filled automatically.')
        return result
    scale = .001 if spec['time_unit'] == 'ms' else 1.
    times = [t*scale+offset for t in values(spec['time_column'])]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise InputError('Signal times must be strictly increasing; duplicate timestamps are rejected.')
    return source, raw, times, {n: values(n) for n in names}


def bind_sources(cfg, scene, sources):
    if not isinstance(sources, list) or not 1 <= len(sources) <= 8:
        raise InputError('Provide 1..8 signal source definitions.')
    if scene.get('external_signals'):
        raise InputError('Scene already contains external signals; bind again from the original scene.')
    times = [f['time'] for f in scene['frames']]
    known = component_ids(scene)
    signals, inputs, provenance = [], [], []
    for source_index, spec in enumerate(sources):
        source, raw, source_times, columns = read_source(cfg, spec)
        signature = spec.get('model_physics_signature')
        if signature is not None and signature != scene.get('physics_signature'):
            raise InputError('Signal source model physics signature does not match the scene.')
        inputs.append((source_index, source.suffix.lower(), raw))
        provenance.append(dict(label=spec['label'], sha256=digest(raw), time_column=spec['time_column'], time_unit=spec['time_unit'],
            time_offset_s=spec['time_offset_s'], interpolation=spec['interpolation'], max_gap_s=spec['max_gap_s'], samples=len(source_times),
            model_identity='matched_physics_signature' if signature is not None else 'explicit_component_mapping_only'))
        for channel_index, channel in enumerate(spec['channels']):
            component = channel.get('component')
            if component is not None and (not isinstance(component, dict) or set(component) != {'kind', 'name'} or not isinstance(component['kind'], str) or not isinstance(component['name'], str) or component['kind'] not in known or component['name'] not in known[component['kind']]):
                raise InputError('Signal component binding does not identify an existing scene component.')
            frame_values, interpolated = sample(source_times, columns[channel['column']], times, spec['interpolation'], spec['max_gap_s'])
            signal = dict(id='s'+str(source_index)+'_'+str(channel_index), label=channel['label'], unit=channel['unit'],
                source_label=spec['label'], source_index=source_index, component=component, times=source_times, values=columns[channel['column']],
                frame_values=frame_values, interpolation=spec['interpolation'], max_gap_s=spec['max_gap_s'], interpolated_animation_frames=interpolated)
            signals.append(signal)
            if len(signals) > 32:
                raise InputError('At most 32 signal channels per visualization.')
    scene['external_signals'] = signals
    scene['signal_provenance'] = provenance
    scene['signal_alignment_scope'] = 'Only declared time units, offset and interpolation. No clock-drift correction, automatic unit conversion or physiological identity inference.'
    return inputs


def validate_scene(scene):
    if not isinstance(scene, dict) or not {'frames', 'meshes', 'coordinate_units', 'frame_to_body', 'physics_signature'} <= set(scene):
        raise InputError('Expected an OpenSim animation.json scene.')
    frames = scene['frames']
    if not isinstance(frames, list) or not 2 <= len(frames) <= 300:
        raise InputError('Scene must contain 2..300 native animation frames.')
    times = [_number(frame['time'], 'frame time') for frame in frames]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise InputError('Scene frames must be ordered.')
    if len(scene['meshes']) > 50:
        raise InputError('Scene mesh limit exceeded.')
    for mesh in scene['meshes']:
        if not {'vertices', 'triangles', 'frame', 'color'} <= set(mesh) or len(mesh['vertices']) > 200000 or len(mesh['triangles']) > 300000:
            raise InputError('Invalid or oversized mesh arrays.')
        for vertex in mesh['vertices']:
            if len(vertex) != 3 or any(type(v) not in {int, float} or not math.isfinite(v) for v in vertex):
                raise InputError('Invalid mesh vertex.')
        for triangle in mesh['triangles']:
            if len(triangle) != 3 or any(type(i) is not int or not 0 <= i < len(mesh['vertices']) for i in triangle):
                raise InputError('Invalid mesh triangle indices.')
    for frame in frames:
        for transform in frame['transforms'].values():
            if len(transform) != 16 or any(type(v) not in {int, float} or not math.isfinite(v) for v in transform):
                raise InputError('Invalid frame transform.')
    return scene


def attach_signals(cfg, scene_path, signal_sources):
    source = cfg.input_path(scene_path, '.json')
    raw = bounded_read(source, 32*1024**2)
    try:
        scene = validate_scene(json.loads(raw))
    except (ValueError, KeyError, TypeError) as exc:
        raise InputError('Invalid OpenSim animation scene.') from exc
    inputs = bind_sources(cfg, scene, signal_sources)
    encoded = json.dumps(scene, ensure_ascii=True, allow_nan=False).replace('<', '\\u003c')
    if len(encoded.encode()) > 32*1024**2:
        raise InputError('Combined scene and signals exceed 32 MiB.')
    folder = cfg.results_root/('visualization-'+uuid.uuid4().hex)
    folder.mkdir(parents=True)
    assets = {}
    for i, suffix, data in inputs:
        target = folder/'inputs'/('signal-'+str(i)+suffix)
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(data)
        assets[target.relative_to(folder).as_posix()] = digest(data)
    (folder/'animation.json').write_text(json.dumps(scene, allow_nan=False), encoding='utf-8')
    template = (Path(__file__).parent/'viewer_assets/player.html').read_text(encoding='utf-8')
    script = (Path(__file__).parent/'viewer_assets/player.js').read_text(encoding='utf-8')
    (folder/'viewer.html').write_text(template.replace('__NONCE__', secrets.token_hex(16)).replace('__SCRIPT__', script).replace('__DATA__', encoded), encoding='utf-8')
    for name in ('animation.json', 'viewer.html'):
        assets[name] = digest((folder/name).read_bytes())
    project = dict(schema='opensim_visualization_project_v1', source_scene_sha256=digest(raw), physics_signature=scene['physics_signature'],
                   coordinate_system=scene.get('coordinate_system'), units=scene['units'], assets=assets,
                   component_ids={k: sorted(v) for k, v in component_ids(scene).items()}, signal_provenance=scene['signal_provenance'],
                   alignment_scope=scene['signal_alignment_scope'], scope='Portable offline visualization with copied numeric inputs. File integrity and explicit mapping do not establish physical equivalence or source trust.')
    manifest = folder/'visualization.json'
    manifest.write_text(json.dumps(project, indent=2, allow_nan=False), encoding='utf-8')
    return dict(status='completed', project_file=str(manifest), html_file=str(folder/'viewer.html'), scene_file=str(folder/'animation.json'),
                signal_count=len(scene['external_signals']), frame_count=len(scene['frames']), sources=scene['signal_provenance'],
                api_model_changed=False, scope=project['scope'])


def inspect_workspace(cfg, project_path):
    path = cfg.input_path(project_path, '.json')
    project = json.loads(bounded_read(path, 2*1024**2))
    if project.get('schema') not in {'opensim_visualization_project_v1','opensim_visual_workbench_v1'} or not isinstance(project.get('assets'), dict) or not 2 <= len(project['assets']) <= 12:
        raise InputError('Expected a bounded visualization project manifest.')
    for name, expected in project['assets'].items():
        if not isinstance(name, str) or '\\' in name or ':' in name or Path(name).is_absolute() or '..' in Path(name).parts:
            raise InputError('Unsafe visualization asset path.')
        candidate = path.parent/name
        target = candidate.resolve()
        if not target.is_relative_to(path.parent.resolve()) or any(p.is_symlink() for p in [candidate, *candidate.parents] if p != path.parent and p.is_relative_to(path.parent)):
            raise InputError('Visualization assets cannot escape their project.')
        data = bounded_read(target, 32*1024**2)
        if digest(data) != expected:
            raise InputError('Visualization asset hash mismatch: '+name)
    return dict(verified=True, project_file=str(path), **project)

"""Portable, strict project descriptions. A manifest never grants filesystem access."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .core import InputError, bounded_read, read_motion, trc_info, xml_model

ID = r'^[A-Za-z][A-Za-z0-9_-]{0,63}$'
REF = re.compile(r'^\$\{(inputs|stages)\.([A-Za-z][A-Za-z0-9_-]{0,63})(?:\.([a-z_]+))?\}$')
OUTPUTS = {
    'scale': {'model'}, 'ik': {'motion'}, 'id': {'forces'},
    'static_optimization': {'forces', 'activations'}, 'muscle_analysis': {'lengths'},
    'joint_reaction': {'reactions'}, 'moco': {'states', 'controls', 'solution'},
    'ik_quality': set(),
    'marker_placement': {'model'}, 'configure_actuators': {'model'}, 'actuator_usage': set(),
    'moco_track': {'states','controls','solution'}, 'moco_inverse': {'states','controls','solution'},
    'rra': {'model','motion','forces'},
    'prepare_moco_model': {'model'},
}


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Asset(Strict):
    path: str = Field(min_length=1, max_length=2000)
    kind: Literal['model', 'markers', 'coordinates', 'loads', 'actuator_forces']
    length_unit: Literal['m', 'mm'] | None = None
    force_unit: Literal['N'] | None = None
    point_unit: Literal['m'] | None = None
    torque_unit: Literal['Nm'] | None = None


class Stage(Strict):
    id: str = Field(pattern=ID)
    workflow: str
    parameters: dict[str, Any]


class Check(Strict):
    id: str = Field(pattern=ID)
    stage: str = Field(pattern=ID)
    metric: str = Field(min_length=1, max_length=200)
    comparison: Literal['max', 'min'] = 'max'
    limit: float
    unit: str = Field(min_length=1, max_length=80)
    severity: Literal['warning', 'error'] = 'error'


class Residual(Strict):
    stage: str = Field(pattern=ID)
    force_columns: list[str] = Field(min_length=3, max_length=3)
    moment_columns: list[str] = Field(default_factory=list, max_length=3)


class Plot(Strict):
    stage: str = Field(pattern=ID)
    output: str
    columns: list[str] = Field(min_length=1, max_length=8)
    ylabel: str = Field(min_length=1, max_length=160)


class Project(Strict):
    schema_version: Literal[1]
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default='', max_length=4000)
    inputs: dict[str, Asset] = Field(min_length=1, max_length=32)
    stages: list[Stage] = Field(min_length=1, max_length=24)
    checks: list[Check] = Field(default_factory=list, max_length=200)
    residuals: list[Residual] = Field(default_factory=list, max_length=24)
    plots: list[Plot] = Field(default_factory=list, max_length=16)


def json_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise InputError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(InputError('Nonfinite JSON.')))
    except (ValueError, RecursionError) as exc:
        raise InputError('Invalid project JSON: ' + str(exc)) from exc


def references(value):
    if isinstance(value, str) and value.startswith('${'):
        match = REF.fullmatch(value)
        if not match: raise InputError('Invalid project reference: ' + value)
        yield match.groups()
    elif isinstance(value, dict):
        for child in value.values(): yield from references(child)
    elif isinstance(value, list):
        for child in value: yield from references(child)


def validate_shape(value):
    from .jobs import validate_submission
    try: project = Project.model_validate(value)
    except ValidationError as exc: raise InputError(str(exc)) from exc
    if any(not re.fullmatch(ID, name) for name in project.inputs): raise InputError('Invalid input identifier.')
    stages = {}
    kinds = {'model_path': {'model'}, 'marker_path': {'markers'}, 'static_marker_path': {'markers'},
             'coordinates_path': {'coordinates'}, 'loads_path': {'loads'}, 'forces_path': {'actuator_forces'},
             'reference_path': {'actuator_forces'}}
    alias_kind = {'model': 'model', 'motion': 'coordinates', 'states': 'coordinates', 'forces': 'actuator_forces'}
    for stage in project.stages:
        if stage.workflow not in OUTPUTS or stage.id in stages: raise InputError('Unknown workflow or duplicate stage: ' + stage.id)
        validate_submission(stage.workflow, stage.parameters)
        for category, name, output in references(stage.parameters):
            if category == 'inputs':
                if name not in project.inputs or output: raise InputError('Unknown input reference: ' + name)
            elif name not in stages or output not in OUTPUTS[stages[name].workflow]:
                raise InputError('Stage references must name an earlier compatible output: ' + name)
        for key, allowed in kinds.items():
            ref = stage.parameters.get(key)
            if ref is None: continue
            match = REF.fullmatch(ref) if isinstance(ref, str) else None
            if not match: raise InputError(key + ' must use a tracked input/stage reference.')
            category, name, output = match.groups()
            kind = project.inputs[name].kind if category == 'inputs' else alias_kind.get(output)
            if kind not in allowed: raise InputError('Incompatible asset kind for ' + key)
        stages[stage.id] = stage
    if len({c.id for c in project.checks}) != len(project.checks): raise InputError('Duplicate check identifier.')
    for item in [*project.checks, *project.residuals, *project.plots]:
        if item.stage not in stages: raise InputError('Unknown assessment stage.')
    for item in project.residuals:
        if stages[item.stage].workflow != 'id' or len(set(item.force_columns)) != 3 or len(item.moment_columns) not in {0, 3}:
            raise InputError('Residual definitions need an ID stage and explicit XYZ columns.')
    for item in project.plots:
        if item.output not in OUTPUTS[stages[item.stage].workflow]: raise InputError('Unknown plot output.')
    return project


def prepare_submission(cfg, project_path):
    path = cfg.input_path(project_path, '.json')
    raw = bounded_read(path, 1024 * 1024)
    project = validate_shape(strict_json(raw))
    inputs = {}; total = 0
    for name, asset in project.inputs.items():
        target = Path(asset.path)
        if not target.is_absolute(): target = path.parent / target
        suffix = target.suffix.lower()
        allowed = {'model': {'.osim'}, 'markers': {'.trc'}, 'coordinates': {'.mot', '.sto'},
                   'loads': {'.mot', '.sto'}, 'actuator_forces': {'.mot', '.sto'}}[asset.kind]
        if suffix not in allowed: raise InputError('Wrong extension for asset ' + name)
        target = cfg.input_path(str(target.resolve()), suffix)
        data = bounded_read(target, 20 * 1024**2 if asset.kind == 'model' else 64 * 1024**2)
        total += len(data)
        if total > 256 * 1024**2: raise InputError('Project inputs exceed 256 MiB.')
        if asset.kind == 'model': xml_model(data)
        elif asset.kind == 'markers':
            if trc_info(data)['units'] != asset.length_unit: raise InputError('Declared marker length_unit must match TRC m/mm.')
        else:
            table = read_motion(target)
            if asset.kind == 'coordinates' and table['in_degrees'].lower() not in {'yes', 'no', 'true', 'false'}:
                raise InputError('Coordinate angle units must be explicit inDegrees.')
            if asset.kind == 'loads' and (asset.force_unit, asset.point_unit, asset.torque_unit) != ('N', 'm', 'Nm'):
                raise InputError('Loads require declared N, m and Nm units; values are not auto-converted.')
        inputs[name] = {'path': str(target), 'sha256': digest(data), 'bytes': len(data), 'kind': asset.kind}
    return {'project_path': str(path), 'project_sha256': digest(raw), 'project': project.model_dump(), 'inputs': inputs}


def create_project(cfg, config):
    project = validate_shape(config)
    # Relative paths can only be resolved once saved; creation uses absolute allowed inputs.
    if any(not Path(a.path).is_absolute() for a in project.inputs.values()): raise InputError('create_project requires absolute asset paths; hand-written manifests may use project-relative paths.')
    folder = cfg.results_root / 'projects' / uuid.uuid4().hex
    folder.mkdir(parents=True)
    path = folder / 'project.json'
    try:
        path.write_bytes(json_bytes(project.model_dump()))
        result = prepare_submission(cfg, str(path))
        return {'project_path': str(path), 'project_sha256': result['project_sha256'], 'valid': True}
    except BaseException:
        path.unlink(missing_ok=True); folder.rmdir(); raise


def resolve(value, inputs, stages):
    if isinstance(value, str) and REF.fullmatch(value):
        category, name, output = REF.fullmatch(value).groups()
        return inputs[name] if category == 'inputs' else stages[name][output]
    if isinstance(value, list): return [resolve(v, inputs, stages) for v in value]
    if isinstance(value, dict): return {k: resolve(v, inputs, stages) for k, v in value.items()}
    return value

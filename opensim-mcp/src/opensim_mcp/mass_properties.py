"""Explicit CAD mass-property conversion, with no native/session/file mutation.

All returned inertias are central tensors in the named target body's axes.
This validates numeric consistency, not material, geometry or measured mass.
"""
from __future__ import annotations

import math
from .core import InputError

RELATIVE_TOLERANCE = 1e-10
MASS_SCALES = {'kg': 1., 'g': .001}
LENGTH_SCALES = {'m': 1., 'cm': .01, 'mm': .001}
INERTIA_SCALES = {'kg_m2': 1., 'kg_mm2': 1e-6, 'g_mm2': 1e-9, 'g_cm2': 1e-7}


def _number(value, name, maximum=1e15):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > maximum:
        raise InputError('Expected a bounded finite number for ' + name)
    return float(value)


def _vector(value, name, size=3):
    if not isinstance(value, list) or len(value) != size:
        raise InputError('Expected ' + str(size) + ' values for ' + name)
    return [_number(v, name) for v in value]


def _label(value, name):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 300 or any(ord(c) < 32 for c in value):
        raise InputError('Provide an explicit bounded ' + name)
    return value


def _choice(value, choices, name):
    if not isinstance(value, str) or value not in choices:
        raise InputError('Explicit ' + name + ' must be one of ' + ', '.join(choices))
    return value


def _transpose(a):
    return [list(row) for row in zip(*a)]


def _multiply(a, b):
    return [[math.fsum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _symmetric_matrix(values):
    if not isinstance(values, list) or len(values) not in (6, 9):
        raise InputError('inertia requires 6 tensor entries [xx,yy,zz,xy,xz,yz] or 9 row-major entries')
    v = _vector(values, 'inertia', len(values))
    if len(v) == 6:
        return [[v[0], v[3], v[4]], [v[3], v[1], v[5]], [v[4], v[5], v[2]]], 0.
    a = [v[i:i + 3] for i in (0, 3, 6)]
    scale = max(abs(x) for x in v)
    error = max(abs(a[i][j] - a[j][i]) for i in range(3) for j in range(3))
    if error > RELATIVE_TOLERANCE * scale:
        raise InputError('The row-major inertia matrix is not symmetric')
    # Only numerical asymmetry within the stated tolerance is averaged, recorded
    # in the report. Negative eigenvalues are never repaired or clipped.
    return [[(a[i][j] + a[j][i]) / 2 for j in range(3)] for i in range(3)], error


def _principal_moments(matrix):
    """Scale-normalized symmetric Jacobi eigenvalues; no new dependency."""
    scale = max(abs(v) for row in matrix for v in row)
    if not scale:
        return [0., 0., 0.]
    a = [[v / scale for v in row] for row in matrix]
    for _ in range(40):
        p, q = max(((0, 1), (0, 2), (1, 2)), key=lambda ij: abs(a[ij[0]][ij[1]]))
        if abs(a[p][q]) < 1e-15:
            return sorted(a[i][i] * scale for i in range(3))
        theta = .5 * math.atan2(2 * a[p][q], a[q][q] - a[p][p])
        c, s = math.cos(theta), math.sin(theta)
        pp, qq, pq = a[p][p], a[q][q], a[p][q]
        for k in range(3):
            if k not in (p, q):
                pk, qk = a[p][k], a[q][k]
                a[p][k] = a[k][p] = c * pk - s * qk
                a[q][k] = a[k][q] = s * pk + c * qk
        a[p][p] = c*c*pp - 2*c*s*pq + s*s*qq
        a[q][q] = s*s*pp + 2*c*s*pq + c*c*qq
        a[p][q] = a[q][p] = 0.
    raise InputError('Principal inertia calculation did not converge')


def validate_central_inertia(values):
    """Reject impossible/degenerate finite-body inertias before native calls."""
    matrix, symmetry = _symmetric_matrix(values)
    principal = _principal_moments(matrix)
    scale = max(abs(v) for v in principal)
    tolerance = RELATIVE_TOLERANCE * scale
    if not scale or principal[0] <= tolerance:
        raise InputError('Central inertia must be positive definite for the supported finite rigid-body profile; degenerate point/line inertias are unsupported')
    margin = principal[0] + principal[1] - principal[2]
    if margin < -tolerance:
        raise InputError('Central principal moments violate the physical triangle inequality')
    return {'principal_moments_kg_m2': principal, 'triangle_margin_kg_m2': margin,
            'tolerance_kg_m2': tolerance, 'relative_tolerance': RELATIVE_TOLERANCE,
            'input_symmetry_error': symmetry,
            'near_degenerate_mass_distribution': margin <= 1e-8 * scale,
            'positive_definite': True, 'triangle_inequality_within_tolerance': True}


def convert_mass_properties(properties, frame_transform):
    required = {'mass', 'mass_unit', 'center_of_mass', 'length_unit', 'inertia', 'inertia_unit',
                'inertia_reference', 'inertia_convention', 'source_frame', 'source_description'}
    if not isinstance(properties, dict) or set(properties) != required:
        raise InputError('Mass properties require exactly: ' + ', '.join(sorted(required)))
    transform_fields = {'target_frame', 'rotation_source_to_target', 'translation_source_origin_in_target_m'}
    if not isinstance(frame_transform, dict) or set(frame_transform) != transform_fields:
        raise InputError('Frame transform requires exactly: ' + ', '.join(sorted(transform_fields)))
    source_frame = _label(properties['source_frame'], 'source frame')
    target_frame = _label(frame_transform['target_frame'], 'target body frame')
    source_description = _label(properties['source_description'], 'mass-property provenance')
    mass_unit = _choice(properties['mass_unit'], MASS_SCALES, 'mass_unit')
    length_unit = _choice(properties['length_unit'], LENGTH_SCALES, 'length_unit')
    inertia_unit = _choice(properties['inertia_unit'], INERTIA_SCALES, 'inertia_unit')
    reference = _choice(properties['inertia_reference'], ('center_of_mass', 'source_origin'), 'inertia_reference')
    convention = _choice(properties['inertia_convention'], ('tensor_entries', 'positive_products'), 'inertia_convention')
    mass = _number(properties['mass'], 'mass') * MASS_SCALES[mass_unit]
    if not 1e-6 <= mass <= 1000:
        raise InputError('Converted mass_kg must be within the wearable profile 1e-6..1000 kg')
    center = [x * LENGTH_SCALES[length_unit] for x in _vector(properties['center_of_mass'], 'center of mass')]
    source_matrix, symmetry = _symmetric_matrix(properties['inertia'])
    factor = INERTIA_SCALES[inertia_unit]
    source_matrix = [[v * factor * (-1 if convention == 'positive_products' and i != j else 1)
                      for j, v in enumerate(row)] for i, row in enumerate(source_matrix)]
    rotation = frame_transform['rotation_source_to_target']
    if not isinstance(rotation, list) or len(rotation) != 3:
        raise InputError('rotation_source_to_target must be an explicit 3x3 proper rotation')
    rotation = [_vector(row, 'rotation row') for row in rotation]
    orthogonality = max(abs(math.fsum(rotation[k][i] * rotation[k][j] for k in range(3)) - (1 if i == j else 0))
                        for i in range(3) for j in range(3))
    a, b, c = rotation
    determinant = a[0]*(b[1]*c[2]-b[2]*c[1]) - a[1]*(b[0]*c[2]-b[2]*c[0]) + a[2]*(b[0]*c[1]-b[1]*c[0])
    if orthogonality > 1e-9 or abs(determinant - 1) > 1e-9:
        raise InputError('Rotation must be orthonormal and right handed; reflections, scaling and automatic repair are forbidden')
    translation = _vector(frame_transform['translation_source_origin_in_target_m'], 'SI translation')
    if source_frame == target_frame and (orthogonality > 1e-12 or
          max(abs(rotation[i][j] - (1 if i == j else 0)) for i in range(3) for j in range(3)) > 1e-12 or any(translation)):
        raise InputError('Identical named source/target frames require an identity transform')
    shift = [[mass * ((math.fsum(v*v for v in center) if i == j else 0) - center[i]*center[j])
              for j in range(3)] for i in range(3)]
    central = [[source_matrix[i][j] - (shift[i][j] if reference == 'source_origin' else 0.)
                for j in range(3)] for i in range(3)]
    source_check = validate_central_inertia([v for row in central for v in row])
    shifted_scale = max(abs(v) for row in shift for v in row)
    central_scale = max(abs(v) for row in central for v in row)
    if reference == 'source_origin' and shifted_scale > 1e8 * central_scale:
        raise InputError('Parallel-axis subtraction is ill conditioned; provide directly measured central inertia rather than losing precision')
    output = _multiply(_multiply(rotation, central), _transpose(rotation))
    check = validate_central_inertia([v for row in output for v in row])
    eigen_error = max(abs(x-y) for x,y in zip(source_check['principal_moments_kg_m2'], check['principal_moments_kg_m2']))
    if eigen_error > 1e-8 * max(source_check['principal_moments_kg_m2']):
        raise InputError('Re-expression failed the principal-moment invariance check')
    result_center = [math.fsum(rotation[i][k] * center[k] for k in range(3)) + translation[i] for i in range(3)]
    entries = [output[0][0], output[1][1], output[2][2], output[0][1], output[0][2], output[1][2]]
    body_parameters = {'mass_kg': mass, 'mass_center_m': result_center, 'inertia_kg_m2': entries}
    if any(abs(v) > 1e6 for v in result_center + entries):
        raise InputError('Converted mass properties exceed the supported wearable numeric profile')
    warnings = []
    if symmetry:
        warnings.append('Input numerical asymmetry was averaged only within the stated relative tolerance; source error is recorded.')
    if check['near_degenerate_mass_distribution']:
        warnings.append('Principal triangle margin is near zero; verify thin/degenerate geometry and source precision.')
    if source_frame != target_frame:
        warnings.append('Transform mesh vertices and child joint points/axes into this same target body frame before assembly. This tool does not edit meshes or infer model attachment transforms.')
    return {'status': 'completed', 'body_parameters': body_parameters, 'target_frame': target_frame,
            'inertia_reference': 'center_of_mass', 'inertia_convention': 'tensor_entries',
            'inertia_matrix_kg_m2': output,
            'quality': {**check, 'principal_moment_invariance_error_kg_m2': eigen_error,
                        'rotation_determinant': determinant, 'rotation_orthogonality_error': orthogonality},
            'conversion': {'mass_factor_to_kg': MASS_SCALES[mass_unit], 'length_factor_to_m': LENGTH_SCALES[length_unit],
                           'inertia_factor_to_kg_m2': factor, 'parallel_axis_subtracted': reference == 'source_origin',
                           'off_diagonal_sign_changed': convention == 'positive_products',
                           'input_symmetry_error_in_source_units': symmetry,
                           'point_mapping': 'p_target_m = rotation_source_to_target * p_source_m + translation_source_origin_in_target_m'},
            'provenance': {'source_description': source_description, 'source_frame': source_frame,
                           'source_properties': properties, 'frame_transform': frame_transform},
            'warnings': warnings,
            'scope': 'Numerical units, central-reference, tensor convention and proper-frame conversion only. No material/mass truth, mesh agreement, anatomical alignment, joint mapping, assistance, energy, model mutation or native simulation is certified.'}

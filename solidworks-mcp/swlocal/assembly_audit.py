"""One bounded, read-only assembly audit. No automatic repairs or ignore lists.

The mate graph describes references, not a solved DOF count or finite pin
engagement. ClosestDistance is measured on native components in assembly space.
"""
import math
from collections import Counter


def clearance_plan(snapshot, pairs):
    if pairs is None:
        return []
    if not isinstance(pairs, list) or len(pairs) > 16:
        raise ValueError('Provide at most 16 explicit clearance pairs')
    names = {c['name'] for c in snapshot['components']}
    result, seen = [], set()
    for row in pairs:
        if not isinstance(row, dict) or set(row) != {'component_a', 'component_b', 'minimum_mm'}:
            raise ValueError('Each clearance pair needs component_a, component_b and minimum_mm')
        a, b, minimum = row['component_a'], row['component_b'], row['minimum_mm']
        if not isinstance(a, str) or not isinstance(b, str) or a == b or a not in names or b not in names:
            raise ValueError('Use two distinct exact top-level component names')
        if isinstance(minimum, bool) or not isinstance(minimum, (int, float)) or not math.isfinite(minimum) or not 0 <= minimum <= 1000:
            raise ValueError('minimum_mm must be finite and within 0..1000 mm')
        key = frozenset((a, b))
        if key in seen:
            raise ValueError('Repeated clearance pair, including reversed order')
        seen.add(key)
        result.append(dict(row))
    return result


def closest_result(raw):
    if not isinstance(raw, (tuple, list)) or len(raw) != 3:
        raise ValueError('ClosestDistance did not return distance and two closest points')
    distance = float(raw[0]) * 1000
    if not math.isfinite(distance) or distance < 0:
        raise ValueError('Native closest distance has no solution')
    points = []
    for point in raw[1:]:
        if not isinstance(point, (tuple, list)) or len(point) != 3:
            raise ValueError('ClosestDistance point is unavailable')
        values = [float(v) * 1000 for v in point]
        if not all(math.isfinite(v) for v in values):
            raise ValueError('ClosestDistance point is nonfinite')
        points.append(values)
    measured = math.dist(*points)
    if abs(measured - distance) > max(1e-5, distance * 1e-6):
        raise ValueError('Closest points disagree with the native distance')
    return {'distance_mm': distance, 'point_a_mm': points[0], 'point_b_mm': points[1],
            'method': 'IModelDoc2.ClosestDistance', 'coordinate_system': 'assembly'}


def audit_report(snapshot, constraints, interference, clearances):
    """Interpret captured evidence. Every overlap remains visible for review."""
    components, mates = snapshot['components'], snapshot['mates']
    known = {c['name']: c for c in components}
    world = object()
    graph = {name: set() for name in known}
    graph[world] = set()
    fixed = sorted(c['name'] for c in components if c['fixed'])
    active = [m for m in mates if not m['suppressed']]
    issues, limits = [], []

    def issue(code, severity, message, **details):
        issues.append({'code': code, 'severity': severity, 'message': message, **details})

    if not components:
        issue('EMPTY_ASSEMBLY', 'incomplete', '装配中没有可检查的顶层零件。')
    for c in components:
        if not c.get('geometry_hash'):
            issue('COMPONENT_SCOPE', 'incomplete', '零件未解析或超出顶层实体零件支持范围，未将其判为通过。', components=[c['name']])
        loaded, referenced = c.get('loaded_part_configuration'), c.get('referenced_configuration')
        if loaded and referenced and loaded != referenced:
            issue('CONFIGURATION_MISMATCH', 'incomplete', '加载的零件配置与装配引用配置不同，需要单独核对。', components=[c['name']])
    for m in active:
        refs = m['references']
        names = [r['component'] for r in refs]
        bad = bool(m['native_error'] and not m['native_warning'])
        if bad:
            issue('MATE_ERROR', 'error', '启用的配合有原生求解错误。', mate=m['name'], components=[x for x in names if x], native_error=m['native_error'])
        elif m['native_warning']:
            issue('MATE_WARNING', 'review', '启用的配合有原生警告。', mate=m['name'], components=[x for x in names if x], native_error=m['native_error'])
        unknown = [x for x in names if x is not None and x not in known]
        if unknown:
            issue('MATE_REFERENCE_SCOPE', 'incomplete', '配合引用未包含在本次顶层检查中。', mate=m['name'], components=unknown)
        if not bad and not unknown:
            nodes = set(world if x is None else x for x in names)
            for node in nodes:
                graph[node].update(nodes - {node})
        if m.get('is_limit'):
            row = {k: m.get(k) for k in ('name', 'value', 'minimum', 'maximum', 'unit')}
            values = [row[k] for k in ('value', 'minimum', 'maximum')]
            valid = all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)
            if not valid or not 0 <= row['minimum'] < row['maximum']:
                row['status'] = 'INVALID'
                issue('LIMIT_INVALID', 'error', '限位范围无效或无法读取。', mate=m['name'])
            else:
                row['margin_to_minimum'] = row['value'] - row['minimum']
                row['margin_to_maximum'] = row['maximum'] - row['value']
                row['status'] = 'PASS' if row['minimum'] - 1e-5 <= row['value'] <= row['maximum'] + 1e-5 else 'FAIL'
                if row['status'] == 'FAIL':
                    issue('LIMIT_OUTSIDE', 'error', '当前原生配合位置超出限位。', mate=m['name'], unit=row['unit'], value=row['value'])
            limits.append(row)

    reached, pending = set(fixed) | {world}, list(fixed) + [world]
    while pending:
        for node in graph[pending.pop()] - reached:
            reached.add(node)
            pending.append(node)
    disconnected = sorted(set(known) - reached)
    isolated = sorted(name for name in disconnected if not graph[name])
    if not fixed and not graph[world] and components:
        issue('NO_ANCHOR', 'review', '没有固定基座或装配基准引用，整个机构可能保留整体运动。')
    if disconnected:
        issue('UNANCHORED_COMPONENTS', 'review', '这些零件没有通过有效配合引用连接到固定基座或装配基准；需确认是否有意保留。', components=disconnected)
    if len(fixed) == len(components) and len(components) > 1:
        issue('ALL_COMPONENTS_FIXED', 'review', '所有零件都固定，不能由此证明机构具有预期转动或滑动能力。', components=fixed)
    for c in constraints['components']:
        status = c['native_constraint_status']
        if status in (4, 5, 6):
            issue('CONSTRAINT_INVALID', 'error', '零件原生约束状态无效。', components=[c['name']], native_constraint_status=status)
        elif status in (1, 7) or status not in (2, 3, 4, 5, 6):
            issue('CONSTRAINT_UNAVAILABLE', 'incomplete', '无法确认零件原生约束状态。', components=[c['name']], native_constraint_status=status)

    overlaps = interference['interferences'] if interference is not None else []
    if interference is None:
        issue('INTERFERENCE_UNAVAILABLE', 'incomplete', '原生干涉检查不可用，未将重叠检查判为通过。')
    for row in overlaps:
        issue('POSSIBLE_INTERFERENCE' if row['possible_interference'] else 'SOLID_OVERLAP', 'review',
              '原生实体重叠需要确认；安装接触、包络简化和真实碰撞均需结合实物意图判断。', **row)
    for row in clearances:
        a, b = row['component_a'], row['component_b']
        pair = {a, b}
        matching = [r for r in overlaps if pair <= set(r['components'])]
        definite = [r for r in matching if len(set(r['components'])) == 2 and not r['possible_interference'] and r['volume_mm3'] > 0]
        if definite:
            row['status'] = 'FAIL'
            row['overlap_volume_mm3'] = sum(r['volume_mm3'] for r in definite)
            issue('CLEARANCE_INTERFERENCE', 'error', '要求留间隙的零件存在实体重叠。', components=[a, b], overlap_volume_mm3=row['overlap_volume_mm3'])
        elif row.get('distance_mm') is None or matching or interference is None:
            row['status'] = 'UNAVAILABLE'
            issue('CLEARANCE_UNAVAILABLE', 'incomplete', '未能完整确认这对零件的间隙。', components=[a, b], reason=row.get('unavailable_reason'))
        elif row['distance_mm'] + 1e-6 < row['minimum_mm']:
            row['status'] = 'FAIL'
            issue('CLEARANCE_BELOW_MINIMUM', 'error', '当前间隙小于指定要求。', components=[a, b], distance_mm=row['distance_mm'], minimum_mm=row['minimum_mm'])
        else:
            row['status'] = 'PASS'

    counts = dict(Counter(r['severity'] for r in issues))
    status = 'FAIL' if counts.get('error') else 'INCOMPLETE' if counts.get('incomplete') else 'REVIEW' if counts.get('review') else 'PASS'
    return {'document_id': snapshot['document_id'], 'state': snapshot['state'], 'path': snapshot['path'],
            'configuration': snapshot['configuration'], 'status': status,
            'summary': {'component_count': len(components), 'active_mate_count': len(active),
                        'suppressed_mate_count': len(mates) - len(active), 'fixed_components': fixed,
                        'unanchored_component_count': len(disconnected), 'isolated_components': isolated,
                        'overlap_count': len(overlaps), 'clearance_pair_count': len(clearances),
                        'issue_counts': counts},
            'connection_graph': {'anchored_components': sorted(set(known) & reached), 'unanchored_components': disconnected,
                                 'scope': 'Active valid mate-reference connectivity only; not DOF counting, geometric engagement or load transfer.'},
            'limits': limits, 'interferences': overlaps, 'clearances': clearances, 'issues': issues,
            'scope': 'Current configuration and pose, resolved top-level native solid parts. No motion sweep, automatic repair, pin axial-engagement, DOF correctness, strength or human-body clearance claim. Native reference angles are not anatomical joint angles.'}


class AssemblyAuditTools:
    def audit_assembly(self, document_id, clearance_pairs=None):
        from . import cad as n
        model = self._doc(document_id)['model']
        if int(n.member(model, 'GetType')) != 2:
            raise n.Failure('DOCUMENT_TYPE', 'Expected assembly', edit_may_be_partial=False)
        before = self.snapshot(document_id)
        try:
            pairs = clearance_plan(before, clearance_pairs)
        except ValueError as error:
            raise n.Failure('ARGUMENT', str(error), edit_may_be_partial=False) from error
        self._check_resources()
        modified = bool(n.member(model, 'GetSaveFlag'))
        constraints = self._assembly_status_for_snapshot(document_id, before)
        interference, unavailable = None, None
        try:
            interference = self._check_interference_pose(document_id, before)
        except n.Failure as error:
            if error.payload['code'] != 'INTERFERENCE_UNAVAILABLE':
                raise
            unavailable = error.payload
        self._activate(model)
        measurements = []
        known = {c['name']: c for c in before['components']}
        for row in pairs:
            names = (row['component_a'], row['component_b'])
            if any(not known[name].get('geometry_hash') or
                   known[name].get('loaded_part_configuration') != known[name].get('referenced_configuration')
                   for name in names):
                measurements.append({**row, 'distance_mm': None,
                                     'unavailable_reason': 'Unresolved, nested or mismatched-configuration component'})
                continue
            a, b = [self._component(model, row[k]) for k in ('component_a', 'component_b')]
            try:
                result = closest_result(n.member(model, 'ClosestDistance', a, b, None, None))
            except (ValueError, TypeError, AttributeError, n.pythoncom.com_error) as error:
                result = {'distance_mm': None, 'unavailable_reason': type(error).__name__ + ': ' + str(error)[:300]}
            measurements.append({**row, **result})
        after = self.snapshot(document_id)
        modified_after = bool(n.member(model, 'GetSaveFlag'))
        if before['state'] != after['state']:
            raise n.Failure('INSPECTION_CHANGED_STATE', 'Assembly state changed during audit; inspect before further work',
                            before_state=before['state'], current_state=after['state'],
                            unsaved_flag_before=modified, unsaved_flag_after=modified_after, edit_may_be_partial=True)
        report = audit_report(before, constraints, interference, measurements)
        report['geometry_mates_unchanged'] = True
        report['unsaved_flag_before'] = modified
        report['unsaved_flag_after'] = modified_after
        report['geometry_mates_and_unsaved_flag_unchanged'] = modified == modified_after
        if modified != modified_after:
            report['issues'].append({'code': 'INSPECTION_SAVE_FLAG_CHANGED', 'severity': 'review',
                'message': '原生检查后未保存标记改变，几何与配合状态未变；未自动保存、清除标记或丢弃修改。'})
            counts = report['summary']['issue_counts']
            counts['review'] = counts.get('review', 0) + 1
            if report['status'] == 'PASS':
                report['status'] = 'REVIEW'
        if unavailable:
            report['interference_unavailable_reason'] = unavailable
        return report

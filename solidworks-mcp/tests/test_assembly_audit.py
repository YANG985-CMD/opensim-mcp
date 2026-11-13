import copy
import types
import unittest
from swlocal.assembly_audit import AssemblyAuditTools, audit_report, clearance_plan, closest_result
from swlocal.cad import Failure


def evidence():
    components = [{'name': name, 'fixed': name == 'base', 'geometry_hash': 'solid',
                   'loaded_part_configuration': 'Default', 'referenced_configuration': 'Default'}
                  for name in ('base', 'arm', 'slider')]
    mates = [{'name': 'hip', 'suppressed': False, 'native_error': 0, 'native_warning': False,
              'references': [{'component': 'base'}, {'component': 'arm'}], 'is_limit': True,
              'value': 90, 'minimum': 69, 'maximum': 113, 'unit': 'deg'},
             {'name': 'guide', 'suppressed': False, 'native_error': 0, 'native_warning': False,
              'references': [{'component': 'arm'}, {'component': 'slider'}]}]
    snap = {'document_id': 'a', 'state': 's', 'path': 'a.SLDASM', 'configuration': 'Default',
            'kind': 2, 'components': components, 'mates': mates}
    constraints = {'components': [{'name': c['name'], 'native_constraint_status': 3} for c in components]}
    return snap, constraints, {'interferences': []}


class AssemblyAuditTests(unittest.TestCase):
    def test_a_connected_limited_mechanism_is_not_called_locked_from_status_alone(self):
        snap, constraints, interference = evidence()
        report = audit_report(snap, constraints, interference, [])
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['connection_graph']['anchored_components'], ['arm', 'base', 'slider'])
        self.assertEqual(report['limits'][0]['margin_to_minimum'], 21)
        self.assertEqual(report['limits'][0]['margin_to_maximum'], 23)
        self.assertNotIn('dof_count', str(report))

    def test_suppressed_or_failed_mate_does_not_hide_a_disconnected_part(self):
        for changes in ({'suppressed': True}, {'native_error': 1}):
            snap, constraints, interference = evidence()
            snap['mates'][1].update(changes)
            report = audit_report(snap, constraints, interference, [])
            self.assertEqual(report['connection_graph']['unanchored_components'], ['slider'])
            self.assertNotEqual(report['status'], 'PASS')

    def test_assembly_datum_can_anchor_a_floating_base(self):
        snap, constraints, interference = evidence()
        snap['components'][0]['fixed'] = False
        snap['mates'].append({'name': 'datum', 'suppressed': False, 'native_error': 0,
                              'native_warning': False, 'references': [{'component': None}, {'component': 'base'}]})
        self.assertEqual(audit_report(snap, constraints, interference, [])['status'], 'PASS')

    def test_uninspected_configurations_and_unknown_status_cannot_pass(self):
        snap, constraints, interference = evidence()
        snap['components'][1]['loaded_part_configuration'] = 'other'
        constraints['components'][2]['native_constraint_status'] = 7
        self.assertEqual(audit_report(snap, constraints, interference, [])['status'], 'INCOMPLETE')

    def test_all_overlaps_remain_visible_without_an_automatic_baseline_exemption(self):
        snap, constraints, interference = evidence()
        overlap = {'components': ['base', 'arm'], 'volume_mm3': 125, 'possible_interference': False}
        interference['interferences'].append(overlap)
        report = audit_report(snap, constraints, interference, [])
        self.assertEqual(report['status'], 'REVIEW')
        self.assertEqual(report['interferences'], [overlap])

    def test_containment_overlap_cannot_pass_a_positive_surface_distance(self):
        snap, constraints, interference = evidence()
        interference['interferences'] = [{'components': ['base', 'arm'], 'volume_mm3': 125, 'possible_interference': False}]
        row = {'component_a': 'base', 'component_b': 'arm', 'minimum_mm': 1, 'distance_mm': 5}
        report = audit_report(snap, constraints, interference, [row])
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(report['clearances'][0]['status'], 'FAIL')

    def test_failed_or_incomplete_measurement_cannot_pass_the_clearance_requirement(self):
        snap, constraints, interference = evidence()
        for collision, distance, status in ((interference, 2, 'FAIL'), (interference, None, 'UNAVAILABLE'), (None, 5, 'UNAVAILABLE')):
            row = {'component_a': 'base', 'component_b': 'arm', 'minimum_mm': 3, 'distance_mm': distance}
            report = audit_report(snap, constraints, collision, [row])
            self.assertEqual(report['clearances'][0]['status'], status)
            self.assertNotEqual(report['status'], 'PASS')

    def test_invalid_later_pair_is_rejected_before_native_interference(self):
        snap, _, _ = evidence()
        h = AssemblyAuditTools()
        h._doc = lambda _: {'model': types.SimpleNamespace(GetType=2)}
        h.snapshot = lambda _: snap
        h._check_resources = lambda: self.fail('Invalid request must fail before native inspection')
        with self.assertRaises(Failure) as error:
            h.audit_assembly('a', [{'component_a': 'base', 'component_b': 'arm', 'minimum_mm': 1},
                                  {'component_a': 'base', 'component_b': 'missing', 'minimum_mm': 1}])
        self.assertEqual(error.exception.payload['code'], 'ARGUMENT')
        for minimum in (True, float('nan'), -1, 1001):
            with self.assertRaises(ValueError):
                clearance_plan(snap, [{'component_a': 'base', 'component_b': 'arm', 'minimum_mm': minimum}])
        with self.assertRaises(ValueError):
            clearance_plan(snap, [{'component_a': 'base', 'component_b': 'arm', 'minimum_mm': 1},
                                  {'component_a': 'arm', 'component_b': 'base', 'minimum_mm': 2}])

    def test_native_distance_unit_conversion_and_no_solution_validation(self):
        measured = closest_result((.005, (.01, 0, 0), (.015, 0, 0)))
        self.assertEqual(measured['distance_mm'], 5)
        self.assertEqual(measured['point_a_mm'], [10, 0, 0])
        for raw in ((-1, None, None), (.005, None, None), (.005, (0, 0, 0), (.5, 0, 0))):
            with self.assertRaises(ValueError):
                closest_result(raw)

    def test_read_only_audit_preserves_unsaved_flag_and_rejects_state_drift(self):
        snap, constraints, interference = evidence()
        model = types.SimpleNamespace(GetType=2, GetSaveFlag=True)
        h = AssemblyAuditTools()
        h._doc = lambda _: {'model': model, 'editable': False}
        h._check_resources = lambda: None
        h._assembly_status_for_snapshot = lambda *_: constraints
        h._check_interference_pose = lambda *_: interference
        h._activate = lambda _: None
        h.snapshot = lambda _: snap
        self.assertTrue(h.audit_assembly('a')['geometry_mates_and_unsaved_flag_unchanged'])
        reads = [snap, {**copy.deepcopy(snap), 'state': 'changed'}]
        h.snapshot = lambda _: reads.pop(0)
        with self.assertRaises(Failure) as error:
            h.audit_assembly('a')
        self.assertEqual(error.exception.payload['code'], 'INSPECTION_CHANGED_STATE')

    def test_native_unsaved_flag_change_is_reported_without_a_save_or_false_pass(self):
        snap, constraints, interference = evidence()
        model = types.SimpleNamespace(GetType=2, GetSaveFlag=False)
        h = AssemblyAuditTools()
        h._doc = lambda _: {'model': model, 'editable': False}
        h.snapshot = lambda _: snap
        h._check_resources = lambda: None
        h._assembly_status_for_snapshot = lambda *_: constraints
        def inspect(*_):
            model.GetSaveFlag = True
            return interference
        h._check_interference_pose = inspect
        h._activate = lambda _: None
        report = h.audit_assembly('a')
        self.assertTrue(report['geometry_mates_unchanged'])
        self.assertFalse(report['geometry_mates_and_unsaved_flag_unchanged'])
        self.assertEqual(report['status'], 'REVIEW')
        self.assertEqual(report['issues'][-1]['code'], 'INSPECTION_SAVE_FLAG_CHANGED')
        self.assertTrue(model.GetSaveFlag)


if __name__ == '__main__':
    unittest.main()

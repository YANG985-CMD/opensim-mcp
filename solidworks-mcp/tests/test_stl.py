import unittest
from swlocal.stl import compare_triangles


class StlGeometryTests(unittest.TestCase):
    def test_planar_diagonal_change_preserves_surface_and_winding(self):
        a=(0.,0.,0.);b=(1.,0.,0.);c=(1.,1.,0.);d=(0.,1.,0.)
        result=compare_triangles([(a,b,c),(a,c,d)],[(a,b,d),(b,c,d)])
        self.assertTrue(result['equivalent']);self.assertEqual(len(result['planar_patches']),1)
    def test_shift_winding_and_curved_patch_changes_are_rejected(self):
        a=(0.,0.,0.);b=(1.,0.,0.);c=(1.,1.,0.);d=(0.,1.,0.)
        old=[(a,b,c),(a,c,d)]
        for new in [[(a,d,b),(b,d,c)],[(a,b,d),(b,c,(0.,1.,.01))]]:
            with self.assertRaises(ValueError):compare_triangles(old,new)
        cc=(1.,1.,.01)
        with self.assertRaises(ValueError):compare_triangles([(a,b,cc),(a,cc,d)],[(a,b,d),(b,cc,d)])
        result=compare_triangles([(a,b,cc),(a,cc,d)],[(a,b,d),(b,cc,d)],surface_tolerance_mm=.01)
        self.assertFalse(result['equivalent']);self.assertTrue(result['within_tessellation_tolerance']);self.assertGreater(result['surface_difference_bound_mm'],0)

import unittest
from swlocal.cad import rounded,digest


class NumericStateTests(unittest.TestCase):
    def test_signed_zero_cannot_invalidate_an_unchanged_geometry_fingerprint(self):
        self.assertEqual(digest(rounded([-0.,-1e-12,1e-12,1.25])),digest(rounded([0.,0.,0.,1.25])))
        self.assertNotEqual(digest(rounded([.001])),digest(rounded([.00101])))

import unittest
from swlocal.organization import validate_groups
from swlocal.resources import enough_memory


class OrganizationTests(unittest.TestCase):
    def test_low_commit_or_physical_margin_blocks_new_edits(self):
        self.assertTrue(enough_memory({'available_physical_gb':2,'available_commit_gb':3}))
        self.assertFalse(enough_memory({'available_physical_gb':20,'available_commit_gb':2.9}))
        self.assertFalse(enough_memory({'available_physical_gb':1.9,'available_commit_gb':20}))
    def test_modules_must_cover_every_exact_component_once(self):
        valid=[{'name':'腰架','components':['base']},{'name':'右腿','components':['leg','bolt']}]
        self.assertEqual(len(validate_groups(valid,{'base','leg','bolt'})),2)
        invalid=[
          [{'name':'腰架','components':['base']}],
          [{'name':'one','components':['base','leg']},{'name':'two','components':['leg','bolt']}],
          [{'name':'one','components':['base','leg','bolt','unknown']}],
          [{'name':'one','components':['base','base','leg','bolt']}],
          [{'name':'SAME','components':['base']},{'name':'same','components':['leg','bolt']}],
        ]
        for plan in invalid:
            with self.assertRaises(ValueError):validate_groups(plan,{'base','leg','bolt'})

if __name__=='__main__':unittest.main()

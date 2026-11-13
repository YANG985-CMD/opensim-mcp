from types import SimpleNamespace
import unittest

from swlocal.tool_search import find_tools


class ToolSearchTests(unittest.TestCase):
    def test_rank_english_chinese_and_no_unrelated_fallback(self):
        tools = [
            SimpleNamespace(name="sw_set_mate_position", description="Drive an angle or distance mate."),
            SimpleNamespace(name="sw_check_interference", description="Compute native solid interference."),
            SimpleNamespace(name="sw_scan_motion", description="Sample poses and check interference."),
        ]
        self.assertEqual(find_tools(tools, "sw_scan_motion", 1)[0]["name"], "sw_scan_motion")
        self.assertEqual(find_tools(tools, "检查干涉", 1)[0]["name"], "sw_check_interference")
        self.assertEqual(find_tools(tools, "工程图", 5), [])

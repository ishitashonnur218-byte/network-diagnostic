import unittest

import performance_integration as pi


class PerformanceIntegrationTests(unittest.TestCase):
    def test_diamond_has_two_paths(self):
        paths = pi.diamond_paths()
        self.assertEqual(len(paths), 2)
        self.assertIn(["h1", "s1", "s2", "s4", "h2"], paths)
        self.assertIn(["h1", "s1", "s3", "s4", "h2"], paths)

    def test_failure_removes_only_affected_route_and_keeps_reachability(self):
        result = pi.analyse_failure(("s2", "s4"))
        self.assertTrue(result["destination_reachable"])
        self.assertEqual(result["remaining_path_count"], 1)
        self.assertEqual(result["paths_lost"], [["h1", "s1", "s2", "s4", "h2"]])

    def test_failure_of_one_branch_keeps_alternate_route(self):
        result = pi.analyse_failure(("s1", "s2"))
        self.assertTrue(result["destination_reachable"])
        self.assertEqual(result["remaining_path_count"], 1)

    def test_comparison_prefers_lower_loss_rtt_and_higher_goodput(self):
        records = [
            {"path_label": "slow", "avg_rtt_ms": 20.0, "packet_loss_percent": 5.0, "goodput_mbps": 0.1},
            {"path_label": "fast", "avg_rtt_ms": 5.0, "packet_loss_percent": 0.0, "goodput_mbps": 0.5},
        ]
        ranked = pi.compare_measurements(records)
        self.assertEqual(ranked[0]["path_label"], "fast")
        self.assertGreater(ranked[0]["score"], ranked[1]["score"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

import unittest

from intelligence.infrastructure_affinity import (
    compute_infrastructure_affinity,
    match_infrastructure_venue,
)


class TestInfrastructureAffinity(unittest.TestCase):
    def test_core_infra_venues_match(self):
        self.assertEqual(match_infrastructure_venue("OSDI"), "OSDI")
        self.assertEqual(match_infrastructure_venue("NSDI"), "NSDI")
        self.assertEqual(match_infrastructure_venue("USENIX ATC"), "ATC")
        self.assertEqual(match_infrastructure_venue("EuroSys"), "EuroSys")

    def test_ml_venues_do_not_match(self):
        self.assertIsNone(match_infrastructure_venue("NeurIPS"))
        self.assertIsNone(match_infrastructure_venue("ICML"))
        self.assertIsNone(match_infrastructure_venue("ICLR"))

    def test_pure_infra_professor_has_high_affinity(self):
        result = compute_infrastructure_affinity(
            {"OSDI": 3, "NSDI": 4, "SOSP": 2}
        )
        self.assertEqual(result.affinity, 1.0)
        self.assertEqual(result.infra_paper_count, 9)
        self.assertIn("NSDI", result.primary_infra_venues)

    def test_ml_heavy_professor_has_low_affinity(self):
        result = compute_infrastructure_affinity(
            {"NeurIPS": 8, "ICML": 6, "NSDI": 1}
        )
        self.assertAlmostEqual(result.affinity, 1 / 15)
        self.assertEqual(result.infra_paper_count, 1)

    def test_mixed_portfolio(self):
        result = compute_infrastructure_affinity(
            {"OSDI": 2, "NeurIPS": 2, "ICML": 2}
        )
        self.assertAlmostEqual(result.affinity, 2 / 6)


if __name__ == "__main__":
    unittest.main()

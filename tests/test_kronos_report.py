import unittest
from kronos_report import quantile,describe_paths,evaluate_paths


class ReportTests(unittest.TestCase):
    def test_quantiles_preserve_endpoints_and_interpolate(self):
        self.assertEqual(quantile([0,10],.5),5)
        self.assertEqual(quantile([2],.9),2)
        self.assertEqual(quantile([4,1,2,3],0),1)
        self.assertEqual(quantile([4,1,2,3],1),4)

    def test_generated_frequencies_and_drawdown_are_descriptive(self):
        s=describe_paths([[110,99],[90,110],[100,100]],100)
        self.assertEqual((s['upCount'],s['downCount'],s['flatCount']),(1,1,1))
        self.assertEqual(s['terminalMedian'],100)
        self.assertAlmostEqual(s['drawdownWorstPct'],-10)
        self.assertEqual(s['lowestClose'],90)

    def test_perfect_retrospective_forecast_beats_constant_baseline(self):
        r=evaluate_paths([[101,102],[101,102]],[101,102],100)
        self.assertEqual(r['model']['mae'],0)
        self.assertEqual(r['baseline']['mae'],1.5)
        self.assertTrue(r['beatsBaselineMAE'])
        self.assertEqual(r['windows'],1)

    def test_constant_baseline_can_win_and_zero_error_is_handled(self):
        r=evaluate_paths([[105,106]],[100,100],100)
        self.assertFalse(r['beatsBaselineMAE'])
        self.assertIsNone(r['maeImprovementPct'])
        self.assertEqual(r['baseline']['mae'],0)

    def test_validation_shape_mismatch_is_rejected(self):
        with self.assertRaises(ValueError): evaluate_paths([[1]],[1,2],1)

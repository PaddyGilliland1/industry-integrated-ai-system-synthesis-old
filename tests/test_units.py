"""The two units: an outlook and a hospital-week counted once.

Ported from probe 8's test_value.py and probe 9's test_repeat.py.
"""

import unittest

import numpy as np

from ae_escalation import units as un

T, F = True, False
nan = np.nan


class TestPeakWeek(unittest.TestCase):
    def test_the_peak_is_the_highest_actual_over_capacity_not_actual(
        self,
    ):
        act = np.array([[110.0, 120, 100, 100]])
        cap = np.array([[100.0, 120, 100, 100]])
        self.assertEqual(un.peak_week(act, cap).tolist(), [0])

    def test_a_missing_week_gives_no_peak(self):
        act = np.array([[110.0, nan, 100, 100], [100, 100, 100, 130]])
        cap = np.full((2, 4), 100.0)
        self.assertEqual(un.peak_week(act, cap).tolist(), [-1, 3])


class TestAtCol(unittest.TestCase):
    def test_takes_each_rows_own_column_and_nan_where_there_is_none(self):
        m = np.array([[1.0, 2, 3], [4, 5, 6], [7, 8, 9]])
        np.testing.assert_array_equal(
            un.at_col(m, np.array([2, -1, 0])), [3, nan, 7]
        )


class TestFlaggedWeek(unittest.TestCase):
    def test_the_highest_stated_chance_with_ties_to_the_earliest_week(self):
        P = np.array(
            [[0.2, 0.6, 0.6, 0.1], [nan, 0.3, nan, 0.4], [nan, nan, nan, nan]]
        )
        self.assertEqual(un.flagged_week(P).tolist(), [1, 3, -1])


class TestTrailingMedian(unittest.TestCase):
    def test_is_the_median_of_the_window_ending_at_the_origin(self):
        y = np.array([1.0, 9, 2, 8, 3])
        np.testing.assert_array_equal(
            un.trailing_median(y, window=3), [nan, nan, 2, 8, 3]
        )

    def test_never_sees_a_week_after_the_origin(self):
        y = np.arange(10, dtype=float)
        a = un.trailing_median(y, window=4)
        y2 = y.copy()
        # Low, not high: one high value never moves the median of a window
        # whose top it already is.
        y2[6:] = -1000.0
        np.testing.assert_array_equal(
            un.trailing_median(y2, window=4)[:6], a[:6]
        )

    def test_a_gap_in_the_window_gives_nan(self):
        y = np.array([1.0, nan, 2, 3, 4, 5])
        np.testing.assert_array_equal(
            un.trailing_median(y, window=3), [nan, nan, nan, nan, 3, 4]
        )


class TestOutlookMeasures(unittest.TestCase):
    def test_excess_at_the_peak_week_and_shortfall_at_the_flagged_week(
        self,
    ):
        act = np.array([[100.0, 112, 104, 90]])
        cap = np.array([[100.0, 100, 100, 100]])
        fc = np.array([[95.0, 105, 110, 99]])
        P = np.array([[0.1, 0.4, 0.7, 0.2]])
        m = un.outlook_measures(act, cap, fc, P)
        self.assertEqual(m["peak"].tolist(), [1])
        np.testing.assert_array_equal(m["excess_cap"], [12.0])
        np.testing.assert_array_equal(m["excess_fc"], [7.0])
        self.assertEqual(m["flagged_week"].tolist(), [2])
        np.testing.assert_array_equal(m["expected_excess"], [10.0])
        np.testing.assert_array_equal(m["actual_excess"], [4.0])
        np.testing.assert_array_equal(m["shortfall"], [6.0])


class TestSummarise(unittest.TestCase):
    def setUp(self):
        # Six weeks in scope and one out: 2 true flags, 1 false flag, 2 missed
        # busy weeks, 1 quiet unflagged week.
        self.flag = np.array([T, T, T, F, F, F, T])
        self.busy = np.array([T, T, F, T, T, F, T])
        self.scope = np.array([T] * 6 + [F])
        self.m = {
            "excess_cap": np.array([10.0, 30, nan, 5, 15, nan, 999]),
            "excess_fc": np.array([4.0, 6, nan, 1, 3, nan, 999]),
            "expected_excess": np.array([nan, nan, 8.0, nan, nan, nan, 999]),
            "actual_excess": np.array([nan, nan, -2.0, nan, nan, nan, 999]),
            "shortfall": np.array([nan, nan, 10.0, nan, nan, nan, 999]),
        }
        self.normal = np.array([100.0, 200, 100, 100, 100, 100, 100])

    def test_counts_split_busy_weeks_into_true_flags_and_missed(self):
        s = un.summarise(self.flag, self.busy, self.m, self.scope, self.normal)
        self.assertEqual(
            (
                s["busy"],
                s["flagged"],
                s["true_flags"],
                s["missed"],
                s["false_flags"],
            ),
            (4, 3, 2, 2, 1),
        )

    def test_excess_totals_and_means_split_by_flagged_and_missed(self):
        s = un.summarise(self.flag, self.busy, self.m, self.scope, self.normal)
        cap, fc = s["excess_over_capacity"], s["excess_over_forecast"]
        self.assertEqual(
            (
                cap["flagged_and_busy"]["total"],
                cap["flagged_and_busy"]["mean"],
            ),
            (40.0, 20.0),
        )
        self.assertEqual(
            (cap["missed"]["total"], cap["missed"]["mean"]), (20.0, 10.0)
        )
        self.assertEqual(
            (cap["all_busy"]["total"], cap["all_busy"]["mean"]), (60.0, 15.0)
        )
        self.assertEqual(
            (fc["flagged_and_busy"]["total"], fc["missed"]["total"]),
            (10.0, 4.0),
        )

    def test_false_flags_carry_their_expected_excess_and_shortfall(self):
        s = un.summarise(self.flag, self.busy, self.m, self.scope, self.normal)
        self.assertEqual(
            s["false_flag_detail"],
            {
                "mean_expected_excess": 8.0,
                "mean_actual_excess": -2.0,
                "mean_shortfall": 10.0,
            },
        )

    def test_share_of_a_normal_week_is_over_true_flags_only(self):
        s = un.summarise(self.flag, self.busy, self.m, self.scope, self.normal)
        sh = s["share_of_normal_week_pct"]["over_capacity"]
        # 10 of 100 and 30 of 200: 10% and 15%.
        self.assertEqual(sh["n"], 2)
        self.assertAlmostEqual(sh["median"], 12.5)
        self.assertAlmostEqual(sh["q25"], 11.25)
        self.assertAlmostEqual(sh["q75"], 13.75)

    def test_without_shortfalls_there_is_no_false_flag_detail(self):
        m = {
            k: v for k, v in self.m.items() if k in ("excess_cap", "excess_fc")
        }
        s = un.summarise(self.flag, self.busy, m, self.scope, self.normal)
        self.assertNotIn("false_flag_detail", s)

    def test_an_empty_split_has_a_zero_total_and_no_mean(self):
        s = un.summarise(
            self.flag, self.busy, self.m, np.zeros(7, dtype=bool), self.normal
        )
        self.assertEqual(
            s["excess_over_capacity"]["missed"], {"total": 0.0, "mean": None}
        )
        self.assertIsNone(
            s["share_of_normal_week_pct"]["over_capacity"]["median"]
        )


class TestDistinctWeeks(unittest.TestCase):
    def setUp(self):
        # Ten weeks, lead 2, H 5: origin t covers target weeks t + 2 to t + 5.
        self.n = 10
        self.y = np.array([100.0, 100, 100, 100, 100, 100, 100, 120, 100, 100])
        self.cap = np.full(self.n, 100.0)
        self.fc = (
            np.tile(np.arange(1.0, 6.0), (self.n, 1))
            + 100 * np.arange(self.n)[:, None]
        )
        self.P = np.zeros((self.n, 4))
        self.normal = 1000.0 + np.arange(self.n)
        self.elig = np.ones(self.n, dtype=bool)

    def run_(self, flag, elig=None, P=None):
        return un.distinct_weeks(
            self.y,
            self.cap,
            self.fc,
            self.P if P is None else P,
            flag,
            self.elig if elig is None else elig,
            self.normal,
            k=1.05,
        )

    def test_a_busy_week_under_four_flagged_outlooks_is_counted_once(self):
        flag = np.zeros(self.n, dtype=bool)
        flag[2:6] = True
        d = self.run_(flag)
        self.assertEqual(int(d["busy"].sum()), 1)
        self.assertTrue(d["busy"][7] and d["covered"][7])
        self.assertEqual(float(d["excess_cap"][7]), 20.0)

    def test_only_a_flag_from_an_eligible_origin_gives_notice(self):
        flag = np.zeros(self.n, dtype=bool)
        flag[3] = True
        elig = self.elig.copy()
        elig[3] = False
        d = self.run_(flag, elig)
        self.assertTrue(d["in_scope"][7])
        self.assertFalse(d["covered"][7])

    def test_a_flag_whose_outlook_misses_the_week_gives_no_notice(
        self,
    ):
        flag = np.zeros(self.n, dtype=bool)
        flag[6] = True
        flag[1] = True
        d = self.run_(flag)
        self.assertFalse(d["covered"][7])

    def test_a_week_with_no_eligible_covering_origin_is_out_of_scope(self):
        elig = self.elig.copy()
        elig[2:6] = False
        d = self.run_(np.ones(self.n, dtype=bool), elig)
        self.assertFalse(d["in_scope"][7])
        self.assertFalse(d["covered"][7])

    def test_strict_notice_needs_that_weeks_own_chance(self):
        flag = np.zeros(self.n, dtype=bool)
        flag[4] = True
        P = np.zeros((self.n, 4))
        P[4, 0] = 0.9  # origin 4 points at week 6, not week 7
        d = self.run_(flag, P=P)
        self.assertTrue(d["covered"][7])
        self.assertFalse(d["strict"][7])
        P[4, 1] = 0.5  # week 7 is origin 4's second target week
        self.assertTrue(self.run_(flag, P=P)["strict"][7])

    def test_forecast_and_normal_week_come_from_the_latest_covering_origin(
        self,
    ):
        elig = self.elig.copy()
        elig[5] = False
        d = self.run_(np.zeros(self.n, dtype=bool), elig)
        # Week 7 from origin 4 is its third data horizon: fc[4, 2] = 403.
        self.assertEqual(float(d["fc"][7]), 403.0)
        self.assertEqual(float(d["excess_fc"][7]), 120.0 - 403.0)
        self.assertEqual(float(d["normal"][7]), 1004.0)

    def test_with_lead_three_an_origin_two_weeks_before_gives_no_notice(self):
        flag = np.zeros(self.n, dtype=bool)
        flag[5] = True
        d = un.distinct_weeks(
            self.y,
            self.cap,
            self.fc,
            self.P[:, 1:],
            flag,
            self.elig,
            self.normal,
            k=1.05,
            lead=3,
        )
        self.assertFalse(d["covered"][7])
        flag[4] = True
        self.assertTrue(
            un.distinct_weeks(
                self.y,
                self.cap,
                self.fc,
                self.P[:, 1:],
                flag,
                self.elig,
                self.normal,
                k=1.05,
                lead=3,
            )["covered"][7]
        )

    def test_the_first_weeks_have_no_covering_origin(self):
        d = self.run_(np.ones(self.n, dtype=bool))
        self.assertEqual(d["in_scope"][:2].tolist(), [F, F])
        self.assertTrue(d["in_scope"][2])


class TestWeekFlags(unittest.TestCase):
    def test_a_chance_at_p_flags_and_one_just_below_does_not(self):
        P = np.array([[0.5, 0.49, 0.1, 0.9]])
        self.assertEqual(
            un.week_flags(P, np.array([T]), 0.5).tolist(), [[T, F, F, T]]
        )

    def test_a_missing_chance_never_flags(self):
        P = np.array([[nan, 0.7, nan, nan]])
        self.assertEqual(
            un.week_flags(P, np.array([T]), 0.5).tolist(), [[F, T, F, F]]
        )

    def test_an_outlook_the_manager_does_not_see_never_flags(self):
        P = np.array([[0.9, 0.9, 0.9, 0.9], [0.9, 0.1, 0.1, 0.1]])
        self.assertEqual(
            un.week_flags(P, np.array([F, T]), 0.5).tolist(),
            [[F, F, F, F], [T, F, F, F]],
        )


def grid(cells, n=6, J=4):
    m = np.zeros((n, J), dtype=bool)
    for t, j in cells:
        m[t, j] = True
    return m


class TestRunPosition(unittest.TestCase):
    # Lead 2: outlook t, column j, names target week t + 2 + j. Week 5 is (0,
    # 3), (1, 2), (2, 1) and (3, 0).
    def test_four_weekly_outlooks_flagging_one_target_week_are_first_to_fourth(
        self,
    ):
        pos = un.run_position(grid([(0, 3), (1, 2), (2, 1), (3, 0)]))
        self.assertEqual(
            [pos[0, 3], pos[1, 2], pos[2, 1], pos[3, 0]], [1, 2, 3, 4]
        )

    def test_a_gap_in_the_run_makes_the_next_flag_a_first_flag_again(self):
        pos = un.run_position(grid([(0, 3), (2, 1), (3, 0)]))
        self.assertEqual([pos[0, 3], pos[2, 1], pos[3, 0]], [1, 1, 2])

    def test_a_flag_on_a_different_target_week_is_not_a_repeat(self):
        # (0, 0) names week 2 and (1, 0) names week 3, so the second is a first
        # flag for week 3.
        pos = un.run_position(grid([(0, 0), (1, 0)]))
        self.assertEqual(pos[1, 0], 1)

    def test_the_furthest_week_is_always_a_first_flag(self):
        pos = un.run_position(grid([(0, 3), (1, 3), (2, 3)]))
        self.assertEqual([pos[0, 3], pos[1, 3], pos[2, 3]], [1, 1, 1])
        # (0, 0) names week 2 and (1, 3) week 6, so nothing may wrap round from
        # the nearest column.
        self.assertEqual(un.run_position(grid([(0, 0), (1, 3)]))[1, 3], 1)

    def test_cells_without_a_flag_are_zero(self):
        pos = un.run_position(grid([(1, 2)]))
        self.assertEqual(int(pos.sum()), 1)
        self.assertEqual(int((pos > 0).sum()), 1)

    def test_never_looks_at_a_later_outlook(self):
        a = un.run_position(grid([(0, 3), (1, 2), (2, 1)]))
        b = un.run_position(
            grid([(0, 3), (1, 2), (2, 1), (3, 0), (3, 1), (4, 0), (5, 2)])
        )
        np.testing.assert_array_equal(a[:3], b[:3])


class TestOutlookPosition(unittest.TestCase):
    def test_consecutive_flagged_outlooks_count_up_and_a_gap_restarts(self):
        self.assertEqual(
            un.outlook_position(np.array([T, T, F, T, T, T, F])).tolist(),
            [1, 2, 0, 1, 2, 3, 0],
        )


class TestCountsByOrigin(unittest.TestCase):
    def test_sums_first_and_repeated_flags_and_right_ones_per_origin(
        self,
    ):
        c = un.counts_by_origin(
            np.array([0, 0, 1, 2, 2]),
            np.array([F, T, F, T, T]),
            np.array([T, F, F, T, F]),
            n=4,
        )
        self.assertEqual(
            c.tolist(),
            [[1, 1, 1, 0], [1, 0, 0, 0], [0, 0, 2, 1], [0, 0, 0, 0]],
        )


class TestCompare(unittest.TestCase):
    def test_precision_is_the_share_right_from_the_summed_counts(self):
        c = np.array([[2, 1, 1, 1], [2, 0, 3, 2]], dtype=float)
        out = un.compare(c, block=1, n_boot=50, seed=0)
        self.assertAlmostEqual(out["first"]["precision_pct"][0], 25.0)
        self.assertAlmostEqual(out["repeated"]["precision_pct"][0], 75.0)
        self.assertAlmostEqual(out["repeated_minus_first_pct"][0], 50.0)
        self.assertEqual(
            (out["first"]["flags"], out["first"]["right"]), (4, 1)
        )
        self.assertEqual(
            (out["repeated"]["flags"], out["repeated"]["right"]), (4, 3)
        )

    def test_the_difference_comes_from_the_same_week_resamples(self):
        # In every week the two kinds are right equally often, so every
        # resample's difference is zero, though each precision on its own
        # swings between 0 and 100.
        c = np.array([[1, 1, 1, 1], [1, 0, 1, 0]] * 10, dtype=float)
        out = un.compare(c, block=1, n_boot=400, seed=1)
        self.assertEqual(out["repeated_minus_first_pct"][1:], [0.0, 0.0])
        self.assertLess(out["first"]["precision_pct"][1], 50.0)
        self.assertGreater(out["first"]["precision_pct"][2], 50.0)


class TestClearlyMorePrecise(unittest.TestCase):
    def test_true_only_when_the_repeated_interval_lies_wholly_above_the_first(
        self,
    ):
        self.assertTrue(
            un.clearly_more_precise([30.0, 25.0, 35.0], [50.0, 40.0, 60.0])
        )
        self.assertFalse(
            un.clearly_more_precise([30.0, 25.0, 41.0], [50.0, 40.0, 60.0])
        )
        self.assertFalse(
            un.clearly_more_precise([30.0, 25.0, 40.0], [50.0, 40.0, 60.0])
        )
        self.assertFalse(
            un.clearly_more_precise([50.0, 40.0, 60.0], [30.0, 25.0, 35.0])
        )


class TestCellCounts(unittest.TestCase):
    def test_sums_flagged_and_unflagged_cells_and_busy_ones_per_origin(
        self,
    ):
        c = un.cell_counts(
            np.array([0, 0, 0, 2]),
            np.array([T, F, F, T]),
            np.array([T, T, F, F]),
            n=3,
        )
        self.assertEqual(
            c.tolist(), [[1, 1, 2, 1], [0, 0, 0, 0], [1, 0, 0, 0]]
        )


class TestLift(unittest.TestCase):
    def test_precision_base_rate_and_lift_come_from_the_summed_counts(self):
        c = np.array([[2, 1, 10, 1], [2, 0, 10, 1]], dtype=float)
        out = un.lift(c, block=1, n_boot=50, seed=0)
        self.assertAlmostEqual(out["precision_pct"][0], 25.0)
        self.assertAlmostEqual(out["base_rate_pct"][0], 10.0)
        self.assertAlmostEqual(out["lift"][0], 2.5)
        self.assertAlmostEqual(out["busy_share_pct"][0], 100.0 * 3 / 24)
        self.assertEqual(
            (
                out["flags"],
                out["right"],
                out["not_flagged"],
                out["busy_not_flagged"],
            ),
            (4, 1, 20, 2),
        )

    def test_the_lift_is_taken_within_each_resample(self):
        # Every week has precision twice its base rate, so every resample's
        # lift is exactly 2 while each share moves.
        c = np.array([[2, 2, 4, 2], [2, 0, 4, 0]] * 10, dtype=float)
        out = un.lift(c, block=1, n_boot=400, seed=1)
        self.assertEqual(out["lift"][1:], [2.0, 2.0])
        self.assertLess(out["precision_pct"][1], 50.0)
        self.assertGreater(out["precision_pct"][2], 50.0)


class TestNotice(unittest.TestCase):
    def test_days_from_release_to_the_start_of_the_target_week(self):
        # Released on the Tuesday nine days after the origin; data horizon 2's
        # week began the Monday before.
        self.assertEqual(
            [un.days_ahead(h) for h in (2, 3, 4, 5)], [-1, 6, 13, 20]
        )

    def test_weeks_ahead_and_the_share_with_a_week_or_more(self):
        out = un.notice(np.array([0, 1, 1, 3]))
        self.assertAlmostEqual(out["mean_weeks_ahead"], 1.25)
        self.assertAlmostEqual(out["week_or_more_pct"], 75.0)
        self.assertAlmostEqual(out["mean_days_ahead"], (-1 + 6 + 6 + 20) / 4)
        self.assertEqual(out["by_release_horizon"], {1: 1, 2: 2, 3: 0, 4: 1})

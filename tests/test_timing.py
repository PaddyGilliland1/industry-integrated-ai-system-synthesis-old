"""The calendar, release timing and as-of views."""

import pandas as pd

from ae_escalation import timing as tm


def test_complete_weeks_are_sundays_seven_days_apart_inclusive():
    idx = tm.complete_weeks("2015-02-22", "2015-03-22")
    assert len(idx) == 5
    assert all(d.dayofweek == 6 for d in idx)
    assert idx[0] == pd.Timestamp("2015-02-22")
    assert idx[-1] == pd.Timestamp("2015-03-22")

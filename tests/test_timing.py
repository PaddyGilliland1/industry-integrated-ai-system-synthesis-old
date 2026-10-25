"""The calendar, release timing and as-of views."""

import numpy as np
import pandas as pd
import pytest

from ae_escalation import timing as tm


def test_complete_weeks_are_sundays_seven_days_apart_inclusive():
    idx = tm.complete_weeks("2015-02-22", "2015-03-22")
    assert len(idx) == 5
    assert all(d.dayofweek == 6 for d in idx)
    assert idx[0] == pd.Timestamp("2015-02-22")
    assert idx[-1] == pd.Timestamp("2015-03-22")


def test_year_position_is_the_fraction_of_the_year_gone():
    pos = tm.year_position(pd.DatetimeIndex(["2020-01-01", "2020-07-02"]))
    assert abs(pos[0]) < 1e-9
    assert 0.49 < pos[1] < 0.51


def test_iso_slots_use_the_iso_week_with_week_53_joining_week_52():
    d = pd.to_datetime(
        ["2020-01-05", "2020-12-27", "2021-01-03", "2021-01-10", "2019-12-29"]
    )
    slot, year = tm.iso_slots(d)
    # 5 Jan 2020 is ISO 2020-W01; 27 Dec 2020 is 2020-W52; 3 Jan 2021 is
    # 2020-W53; 29 Dec 2019 is 2019-W52.
    assert slot.tolist() == [0, 51, 51, 0, 51]
    assert year.tolist() == [2020, 2020, 2020, 2021, 2019]


def test_each_week_is_released_on_the_tuesday_nine_days_after_it_ends():
    release = tm.release_date("2020-03-22")
    assert release == pd.Timestamp("2020-03-31")
    assert release.day_name() == "Tuesday"


def test_a_release_date_needs_a_sunday_week_ending():
    with pytest.raises(ValueError, match="Sunday"):
        tm.release_date("2020-03-23")


def test_the_origin_is_the_latest_week_released_by_a_date():
    assert tm.origin_for("2020-03-31") == pd.Timestamp("2020-03-22")
    # On the Monday before, the latest release was Tue 24 Mar, for w/e 15 Mar.
    assert tm.origin_for("2020-03-30") == pd.Timestamp("2020-03-15")
    assert tm.origin_for("2020-04-06") == pd.Timestamp("2020-03-22")


def test_the_four_release_horizons_are_the_next_four_week_endings():
    weeks = tm.release_horizon_weeks("2020-03-22")
    assert [str(w.date()) for w in weeks] == [
        "2020-04-05",
        "2020-04-12",
        "2020-04-19",
        "2020-04-26",
    ]
    # The first is the week in progress on release day.
    assert weeks[0] - pd.Timedelta(days=6) <= tm.release_date("2020-03-22")
    assert tm.release_date("2020-03-22") <= weeks[0]


def test_release_horizons_one_to_four_are_data_horizons_two_to_five():
    assert [tm.data_horizon(k) for k in (1, 2, 3, 4)] == [2, 3, 4, 5]
    assert [tm.release_horizon(h) for h in (2, 3, 4, 5)] == [1, 2, 3, 4]
    with pytest.raises(ValueError):
        tm.data_horizon(5)


def test_an_as_of_view_holds_only_weeks_released_by_the_origin():
    weeks = tm.complete_weeks("2020-01-05", "2020-04-26")
    frame = pd.DataFrame({"a": range(len(weeks))}, index=weeks)
    view = tm.as_of_view(frame, "2020-03-22")
    assert view.index[-1] == pd.Timestamp("2020-03-22")
    assert len(view) == 12


def test_an_as_of_view_never_changes_when_later_weeks_change():
    weeks = tm.complete_weeks("2020-01-05", "2020-04-26")
    frame = pd.DataFrame(
        {"a": np.arange(len(weeks), dtype=float)}, index=weeks
    )
    later = frame.copy()
    later.loc["2020-03-29":, "a"] = -1e6
    pd.testing.assert_frame_equal(
        tm.as_of_view(frame, "2020-03-22"), tm.as_of_view(later, "2020-03-22")
    )


def test_an_as_of_view_does_not_change_its_input():
    weeks = tm.complete_weeks("2020-01-05", "2020-04-26")
    frame = pd.DataFrame(
        {"a": np.arange(len(weeks), dtype=float)}, index=weeks
    )
    before = frame.copy()
    view = tm.as_of_view(frame, "2020-03-22")
    view.iloc[0, 0] = 99.0
    pd.testing.assert_frame_equal(frame, before)

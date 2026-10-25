"""The Investigator's read-only tools and the code's screen: typed in and
out, every one as of an origin, none returning the flag's stated chance."""

import typing

import numpy as np
import pandas as pd
import pytest
from pydantic import BaseModel, ValidationError

from ae_escalation import backtest as bt
from ae_escalation import data as dt
from ae_escalation import design as ds
from ae_escalation import tools as tl

from .conftest import DATA

HOLIDAYS_SHA256 = (
    "538b3482c28b85ecd2db606a0d5ae6ad17248900b6498700ce0a48d26a3ecde6"
)
ORIGIN = pd.Timestamp("2021-06-13").date()


@pytest.fixture(scope="module")
def wide(flagged):
    return dt.series_from(flagged)[list(ds.REPLAY)]


@pytest.fixture(scope="module")
def run(wide):
    return ds.run_design(wide)


@pytest.fixture(scope="module")
def holidays():
    return dt.load_bank_holidays(
        DATA / "bank-holidays_20261024.json", HOLIDAYS_SHA256
    )


# --- the bank holidays -------------------------------------------------------


def test_the_scottish_bank_holidays_are_read_and_hash_checked(holidays):
    assert len(holidays) == 94
    assert holidays[0] == (pd.Timestamp("2019-01-01").date(), "New Year’s Day")
    assert holidays[-1][0] == pd.Timestamp("2028-12-26").date()


def test_a_changed_bank_holidays_file_is_refused(tmp_path):
    bad = tmp_path / "h.json"
    bad.write_text('{"scotland": {"events": []}}', encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        dt.load_bank_holidays(bad, HOLIDAYS_SHA256)


def test_the_calendar_names_the_holidays_in_a_week(holidays):
    out = tl.get_calendar(
        holidays, tl.CalendarRequest(week="2019-12-29", as_of="2019-12-08")
    )
    assert [h.title for h in out.holidays] == ["Christmas Day", "Boxing Day"]
    assert out.covered
    quiet = tl.get_calendar(
        holidays, tl.CalendarRequest(week="2019-10-13", as_of="2019-10-06")
    )
    assert quiet.holidays == [] and quiet.covered


def test_one_calendar_call_covers_the_four_weeks_ahead(holidays):
    out = tl.get_calendar(holidays, tl.CalendarRequest(as_of="2019-12-08"))
    assert [(str(h.date), h.release_horizon) for h in out.holidays] == [
        ("2019-12-25", 2),
        ("2019-12-26", 2),
        ("2020-01-01", 3),
        ("2020-01-02", 3),
    ]
    assert out.covered


def test_the_calendar_returns_holiday_dates_only_never_the_week_asked(
    holidays,
):
    assert set(tl.CalendarResult.model_fields) == {"holidays", "covered"}
    out = tl.get_calendar(
        holidays, tl.CalendarRequest(week="2022-01-02", as_of="2021-06-13")
    )
    dumped = out.model_dump(mode="json")
    assert "2022-01-02" not in str(dumped)
    assert [str(h.date) for h in out.holidays] == ["2021-12-27", "2021-12-28"]
    assert {h.release_horizon for h in out.holidays} == {None}


def test_the_calendar_says_when_a_week_is_outside_the_file(holidays):
    out = tl.get_calendar(
        holidays, tl.CalendarRequest(week="2018-12-30", as_of="2018-12-09")
    )
    assert not out.covered and out.holidays == []


# --- the requests are typed --------------------------------------------------


def test_a_request_refuses_a_horizon_outside_one_to_four():
    with pytest.raises(ValidationError):
        tl.ForecastRequest(hospital="T101H", as_of=ORIGIN, horizon=5)
    with pytest.raises(ValidationError):
        tl.BacktestErrorRequest(
            hospital="T101H", model="linear", horizon=0, as_of=ORIGIN
        )


def test_a_request_refuses_a_model_that_is_not_one_of_the_four():
    with pytest.raises(ValidationError):
        tl.BacktestErrorRequest(
            hospital="T101H", model="gru", horizon=2, as_of=ORIGIN
        )


def test_a_request_refuses_an_unknown_field():
    with pytest.raises(ValidationError):
        tl.HistoryRequest(hospital="T101H", as_of=ORIGIN, weeks=4, extra=1)


def test_a_tool_refuses_an_origin_that_is_not_a_week_in_the_run(run):
    with pytest.raises(ValueError, match="origin"):
        tl.get_history(
            run,
            tl.HistoryRequest(hospital="T101H", as_of="2021-06-15", weeks=4),
        )
    with pytest.raises(ValueError, match="hospital"):
        tl.get_history(
            run, tl.HistoryRequest(hospital="X999H", as_of=ORIGIN, weeks=4)
        )


# --- the tools ---------------------------------------------------------------


def test_the_forecast_gives_each_simple_model_never_the_gru(run):
    out = tl.get_forecast(
        run, tl.ForecastRequest(hospital="T101H", as_of=ORIGIN)
    )
    models = {f.model for f in out.forecasts}
    assert models == {
        "seasonal naive",
        "4-week moving average",
        "linear",
        "SA-MA",
    }
    assert {f.release_horizon for f in out.forecasts} == {1, 2, 3, 4}
    assert out.release_date == pd.Timestamp("2021-06-22").date()
    weeks = sorted({f.week_ending for f in out.forecasts})
    assert weeks[0] == pd.Timestamp("2021-06-27").date()


def test_the_forecast_matches_the_run_and_its_ranges(run):
    out = tl.get_forecast(
        run, tl.ForecastRequest(hospital="T101H", as_of=ORIGIN, horizon=2)
    )
    t = int(run.weeks.get_loc(pd.Timestamp(ORIGIN)))
    r = run.runs["T101H"]
    y = run.series["T101H"]
    start = int(run.weeks.get_loc(ds.DRIFT_START))
    for f in out.forecasts:
        fc = r["fcs"][f.model]
        assert f.point == pytest.approx(fc[t, 2])
        lo, hi = bt.ratio_range(y, fc, t, 3, 0.95, start=start)
        assert (f.range_95.low, f.range_95.high) == pytest.approx((lo, hi))
        assert f.range_80.low >= f.range_95.low
    assert out.primary == r["primary"][t]


def test_the_model_spread_is_a_share_of_the_primarys_forecast(run):
    out = tl.get_forecast(
        run, tl.ForecastRequest(hospital="T101H", as_of=ORIGIN, horizon=1)
    )
    points = [f.point for f in out.forecasts]
    primary = next(f.point for f in out.forecasts if f.model == out.primary)
    assert out.spread_pct[1] == pytest.approx(
        100 * (max(points) - min(points)) / primary
    )


def test_the_history_ends_at_the_origin(run):
    out = tl.get_history(
        run, tl.HistoryRequest(hospital="T101H", as_of=ORIGIN, weeks=5)
    )
    assert len(out.weeks) == 5
    assert out.weeks[-1].week_ending == ORIGIN
    t = int(run.weeks.get_loc(pd.Timestamp(ORIGIN)))
    assert out.weeks[-1].attendances == run.series["T101H"][t]


def test_the_backtest_error_is_the_mape_of_the_latest_released_targets(run):
    out = tl.get_backtest_error(
        run,
        tl.BacktestErrorRequest(
            hospital="T101H", model="linear", horizon=2, as_of=ORIGIN
        ),
    )
    t = int(run.weeks.get_loc(pd.Timestamp(ORIGIN)))
    y, f = run.series["T101H"], run.runs["T101H"]["fcs"]["linear"]
    tg = np.arange(t - 103, t + 1)
    want = 100 * np.nanmean(np.abs(y[tg] - f[tg - 3, 2]) / y[tg])
    (error,) = out.errors
    assert error.mape == pytest.approx(want)
    assert error.targets == 104


def test_one_backtest_call_gives_each_models_error_at_a_horizon(run):
    out = tl.get_backtest_error(
        run, tl.BacktestErrorRequest(hospital="T101H", horizon=2, as_of=ORIGIN)
    )
    assert out.release_horizon == 2
    assert [e.model for e in out.errors] == list(tl.SIMPLE_MODELS)
    one = tl.get_backtest_error(
        run,
        tl.BacktestErrorRequest(
            hospital="T101H", model="linear", horizon=2, as_of=ORIGIN
        ),
    )
    assert one.errors == [e for e in out.errors if e.model == "linear"]


def test_the_track_record_counts_only_outlooks_released_by_the_origin(run):
    out = tl.get_track_record(
        run, tl.TrackRecordRequest(hospital="T101H", as_of=ORIGIN)
    )
    f = run.frame[run.frame["series"] == "T101H"].reset_index(drop=True)
    t = int(run.weeks.get_loc(pd.Timestamp(ORIGIN)))
    upto = f.iloc[: t - 4]
    elig = upto["known"] & ~upto["latched"]
    assert out.flags == int((upto["flag"] & elig).sum())
    assert out.borne_out == int((upto["flag"] & elig & upto["busy"]).sum())


def test_the_screen_at_the_latch_week_names_four_latch_briefs(run):
    entries = tl.screen_at(run, "2020-03-22")
    kinds = {e.hospital: (e.kind, e.level_source) for e in entries}
    assert kinds == {
        "Scotland": ("latch", "held"),
        "S314H": ("latch", "held"),
        "T101H": ("latch", "held"),
        "G405H": ("latch", "held"),
    }
    for e in entries:
        assert (
            e.latched and e.latched_since == pd.Timestamp("2020-03-22").date()
        )
        assert e.breach_direction == "downward"
        assert e.level_meaning == tl.LEVEL_MEANING


LEVEL_1 = (
    "Level 1 means usual demand for the time of year, below 1.05 times the "
    "seasonal baseline; levels 2 to 4 mean unusually high. "
)


@pytest.mark.parametrize(
    "level, source, line",
    [
        (
            1,
            "flag",
            LEVEL_1 + "From the flag, going by past forecast errors, no "
            "week ahead has at least an even chance of reaching 1.05 times "
            "the seasonal baseline.",
        ),
        (
            2,
            "flag",
            "Level 2 from the flag means that, going by past forecast "
            "errors, one of the four weeks ahead has at least an even chance "
            "of reaching 1.05 times the seasonal baseline.",
        ),
        (
            1,
            "surge",
            LEVEL_1 + "From the surge, the latest released week was below "
            "1.05 times the lowest seasonal baseline of the four weeks ahead.",
        ),
        (
            2,
            "surge",
            "Level 2 from the surge means the latest released week was 1.05 "
            "to under 1.10 times the lowest seasonal baseline of the four "
            "weeks ahead.",
        ),
        (
            3,
            "surge",
            "Level 3 from the surge means the latest released week was 1.10 "
            "to under 1.15 times the lowest seasonal baseline of the four "
            "weeks ahead.",
        ),
        (
            4,
            "surge",
            "Level 4 from the surge means the latest released week was at "
            "least 1.15 times the lowest seasonal baseline of the four weeks "
            "ahead.",
        ),
        (
            1,
            "held",
            LEVEL_1 + "Held, it is the level the flag gave in the week before "
            "the alarm, when no week ahead had at least an even chance of "
            "reaching 1.05 times the seasonal baseline. It is kept until a "
            "person approves a latch reset.",
        ),
        (
            2,
            "held",
            "Level 2, held, is the level the flag gave in the week before the "
            "alarm, when one of the four weeks ahead had at least an even "
            "chance of reaching 1.05 times the seasonal baseline. It is kept "
            "until a person approves a latch reset.",
        ),
    ],
)
def test_each_level_states_what_its_source_means(level, source, line):
    assert tl.level_band(level, source) == line


@pytest.mark.parametrize("level, source", [(3, "flag"), (4, "held")])
def test_a_level_its_source_cannot_give_is_refused(level, source):
    with pytest.raises(ValueError):
        tl.level_band(level, source)


def test_each_replay_briefs_band_line_is_true_of_the_rule(run):
    # What each line says, checked on the run itself: the flag's chance at
    # the origin, the latest week over the lowest seasonal baseline ahead,
    # and the flag in the week before a held episode's alarm.
    from ae_escalation import replay as rp
    from ae_escalation import rules as ru

    seen = set()
    for e in rp.replay_entries(run):
        rows = run.frame[run.frame["series"] == e.hospital].reset_index()
        t = int(run.weeks.get_loc(pd.Timestamp(e.as_of)))
        chances = rows.loc[:, ["P1", "P2", "P3", "P4"]].to_numpy()
        if e.level_source == "flag":
            assert chances[t].max() >= ru.FLAG_P
        elif e.level_source == "surge":
            cap = run.caps[e.hospital][t, ru.LEAD - 1 :]
            ratio = run.series[e.hospital][t] / cap.min()
            assert ru.band_level(np.array([ratio]))[0] == e.level
        else:
            ep = next(
                x
                for x in run.runs[e.hospital]["episodes"]
                if x["alarm"] <= t and (x["reset"] is None or x["reset"] > t)
            )
            before = np.nan_to_num(chances[ep["alarm"] - 1], nan=-1.0)
            assert (before.max() >= ru.FLAG_P) == (e.level == 2)
        seen.add((e.level_source, e.level))
    assert {s for s, _ in seen} == {"flag", "surge", "held"}


def test_the_screen_at_the_demand_week_names_ninewells_from_the_flag(run):
    entries = tl.screen_at(run, "2021-06-13")
    assert [
        (e.hospital, e.kind, e.level, e.level_source) for e in entries
    ] == [("T101H", "demand", 2, "flag")]
    assert not entries[0].latched and entries[0].latched_since is None


def test_the_screen_at_a_quiet_week_is_empty(run):
    assert tl.screen_at(run, "2019-12-08") == []


# --- no look-ahead and no stated chance --------------------------------------


def test_no_tool_reads_a_week_after_its_origin(wide):
    later = wide.copy()
    later.loc[later.index > pd.Timestamp(ORIGIN)] *= 3.0
    a, b = ds.run_design(wide), ds.run_design(later)
    requests = [
        (tl.get_forecast, tl.ForecastRequest(hospital="T101H", as_of=ORIGIN)),
        (
            tl.get_history,
            tl.HistoryRequest(hospital="T101H", as_of=ORIGIN, weeks=8),
        ),
        (
            tl.get_backtest_error,
            tl.BacktestErrorRequest(
                hospital="T101H", model="SA-MA", horizon=4, as_of=ORIGIN
            ),
        ),
        (
            tl.get_track_record,
            tl.TrackRecordRequest(hospital="T101H", as_of=ORIGIN),
        ),
    ]
    for tool, req in requests:
        assert tool(a, req) == tool(b, req), tool.__name__
    assert tl.screen_at(a, ORIGIN) == tl.screen_at(b, ORIGIN)


def field_names(model):
    names = set()
    for name, field in model.model_fields.items():
        names.add(name)
        for arg in typing.get_args(field.annotation) or (field.annotation,):
            inner = typing.get_args(arg) or (arg,)
            for t in inner:
                if isinstance(t, type) and issubclass(t, BaseModel):
                    names |= field_names(t)
    return names


def test_no_tool_output_has_a_field_for_the_flags_stated_chance():
    outputs = [
        tl.ForecastResult,
        tl.HistoryResult,
        tl.BacktestErrorResult,
        tl.TrackRecordResult,
        tl.CalendarResult,
        tl.ScreenEntry,
    ]
    for model in outputs:
        names = {n.lower() for n in field_names(model)}
        assert not any(
            word in n for n in names for word in ("chance", "prob", "p_max")
        ), model.__name__


def test_the_tools_never_change_the_run(run):
    before = run.frame.copy()
    tl.get_forecast(run, tl.ForecastRequest(hospital="T101H", as_of=ORIGIN))
    tl.get_track_record(
        run, tl.TrackRecordRequest(hospital="T101H", as_of=ORIGIN)
    )
    tl.screen_at(run, ORIGIN)
    pd.testing.assert_frame_equal(run.frame, before)


def test_the_measure_type_lists_every_measure_the_tools_return():
    assert typing.get_args(tl.Measure) == tuple(tl.MEASURES)

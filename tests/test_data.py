"""Load, verify, clean, flag and keep: synthetic cases first, then the frozen
file."""

import hashlib

import numpy as np
import pandas as pd
import pytest

from ae_escalation import data as dt
from ae_escalation import timing as tm

from .conftest import CSV, DATA

# --- synthetic -----------------------------------------------------------


def small_frame():
    return pd.DataFrame(
        {
            "WeekEndingDate": pd.to_datetime(
                ["2015-02-22", "2015-02-22", "2015-03-08", "2015-02-22"]
            ),
            "TreatmentLocation": ["A", "A", "A", "B"],
            "AttendanceCategory": [
                "Unplanned",
                "All",
                "Unplanned",
                "Unplanned",
            ],
            "NumberOfAttendancesEpisode": [10, 10, 12, 5],
        }
    )


def test_to_wide_filters_category_and_inserts_missing_weeks():
    w = dt.to_wide(small_frame(), "TreatmentLocation", category="Unplanned")
    assert list(w.columns) == ["A", "B"]
    assert len(w) == 3
    assert w.loc["2015-02-22", "A"] == 10
    assert np.isnan(w.loc["2015-03-01", "A"])
    assert w.loc["2015-03-08", "A"] == 12
    assert np.isnan(w.loc["2015-03-08", "B"])


def test_run_summary_finds_first_last_and_gaps():
    idx = tm.complete_weeks("2015-01-04", "2015-03-08")
    s = pd.Series(
        [np.nan, 1, 2, np.nan, np.nan, 3, 4, 5, np.nan, np.nan], index=idx
    )
    r = dt.run_summary(s)
    assert r["first"] == idx[1]
    assert r["last"] == idx[7]
    assert r["n_present"] == 5
    assert r["gaps"] == [(idx[3], idx[4], 2)]
    assert not r["unbroken"]


def test_run_summary_of_an_unbroken_series():
    idx = tm.complete_weeks("2015-01-04", "2015-02-01")
    r = dt.run_summary(pd.Series([1.0, 2, 3, 4, 5], index=idx))
    assert r["unbroken"]
    assert r["gaps"] == []


def test_run_summary_of_an_empty_series():
    idx = tm.complete_weeks("2015-01-04", "2015-02-01")
    r = dt.run_summary(pd.Series([np.nan] * 5, index=idx))
    assert r["n_present"] == 0
    assert r["first"] is None


def test_a_spike_is_flagged_and_its_neighbours_are_not():
    y = 1000 + np.random.default_rng(1).normal(0, 10, 60)
    y[30] = 1300
    flags = dt.flag_outliers(pd.Series(y), window=9, k=5.0)
    assert flags.iloc[30]
    assert int(flags.sum()) == 1


def test_a_constant_series_has_no_outliers():
    flags = dt.flag_outliers(pd.Series([5.0] * 30), window=9, k=5.0)
    assert int(flags.sum()) == 0


def write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def test_load_weekly_refuses_a_file_whose_hash_differs(tmp_path):
    path, _ = write(tmp_path, "w.csv", b'"WeekEndingDate"\n"20150222"\n')
    with pytest.raises(ValueError, match="SHA-256"):
        dt.load_weekly(path, "0" * 64)


def test_load_weekly_reads_week_endings_as_dates(tmp_path):
    payload = b'"WeekEndingDate","Site"\n"20150222","A"\n"20150301","A"\n'
    path, digest = write(tmp_path, "w.csv", payload)
    df = dt.load_weekly(path, digest)
    assert list(df["WeekEndingDate"]) == list(
        pd.to_datetime(["2015-02-22", "2015-03-01"])
    )


def test_verify_sources_marks_a_file_that_no_longer_matches(tmp_path):
    good, good_sha = write(tmp_path, "good.csv", b"abc")
    write(tmp_path, "bad.csv", b"abd")
    header = "file\tsource_url\tpublisher_page_url\tlicence\taccess_date"
    rows = [
        header + "\tbytes\tsha256",
        f"good.csv\thttps://x\thttps://x\tOGL\t2026-10-24\t3\t{good_sha}",
        f"bad.csv\thttps://x\thttps://x\tOGL\t2026-10-24\t3\t{good_sha}",
    ]
    manifest = tmp_path / "MANIFEST.tsv"
    manifest.write_text("\n".join(rows) + "\n", encoding="utf-8")
    out = dt.verify_sources(manifest)
    assert out.set_index("file")["matches"].to_dict() == {
        "good.csv": True,
        "bad.csv": False,
    }


def keyed_frame():
    """Three sites over six weeks, one closed early, with a duplicate key."""
    weeks = tm.complete_weeks("2015-05-24", "2015-06-28")
    rows = []
    for w in weeks:
        for site in ("A", "B"):
            for cat in ("Unplanned", "All"):
                rows.append((w, site, cat, 100))
    rows.append((weeks[0], "C", "Unplanned", 50))
    rows.append((weeks[3], "A", "Unplanned", 7))
    return pd.DataFrame(
        rows,
        columns=[
            "WeekEndingDate",
            "TreatmentLocation",
            "AttendanceCategory",
            "NumberOfAttendancesEpisode",
        ],
    )


def test_flag_and_keep_keeps_every_row_and_gives_each_set_aside_row_a_reason():
    df = keyed_frame()
    out = dt.flag_and_keep(df, start="2015-06-07", provisional_weeks=1)
    assert len(out) == len(df)
    kept = out[out["in_series"]]
    assert (kept["AttendanceCategory"] == "Unplanned").all()
    assert (kept["WeekEndingDate"] >= "2015-06-07").all()
    assert (kept["exclusion_reason"] == "").all()
    aside = out[~out["in_series"]]
    assert (aside["exclusion_reason"] != "").all()
    early = aside[aside["AttendanceCategory"] == "Unplanned"]
    assert (early["WeekEndingDate"] < "2015-06-07").all()
    assert early["exclusion_reason"].str.contains("7 Jun 2015").all()


def test_flag_and_keep_marks_duplicate_keys_and_the_provisional_weeks():
    out = dt.flag_and_keep(
        keyed_frame(), start="2015-06-07", provisional_weeks=2
    )
    dup = out[out["duplicate_key"]]
    assert set(dup["WeekEndingDate"]) == {pd.Timestamp("2015-06-14")}
    assert set(dup["TreatmentLocation"]) == {"A"}
    prov = out.loc[out["provisional"], "WeekEndingDate"]
    assert set(prov) == {
        pd.Timestamp("2015-06-21"),
        pd.Timestamp("2015-06-28"),
    }


def test_flag_and_keep_marks_the_covid_period():
    weeks = tm.complete_weeks("2020-02-16", "2020-03-15")
    df = pd.DataFrame(
        {
            "WeekEndingDate": weeks,
            "TreatmentLocation": "A",
            "AttendanceCategory": "Unplanned",
            "NumberOfAttendancesEpisode": 100,
        }
    )
    out = dt.flag_and_keep(df, start="2015-06-07", provisional_weeks=0)
    covid = out.set_index("WeekEndingDate")["covid_period"]
    assert not covid["2020-02-23"] and covid["2020-03-01"]


def test_flag_and_keep_does_not_change_its_input():
    df = keyed_frame()
    before = df.copy()
    dt.flag_and_keep(df, start="2015-06-07")
    pd.testing.assert_frame_equal(df, before)


def test_series_from_sums_sites_into_the_national_series_from_the_start():
    flagged = dt.flag_and_keep(keyed_frame(), start="2015-06-07")
    wide = dt.series_from(flagged)
    assert list(wide.columns) == ["A", "B", "Scotland"]
    assert wide.index[0] == pd.Timestamp("2015-06-07")
    # The duplicate key at A, w/e 14 Jun 2015, is summed, as PHS's two rows add
    # up.
    assert wide.loc["2015-06-14", "A"] == 107
    assert wide.loc["2015-06-14", "Scotland"] == 207


# --- the frozen file -----------------------------------------------------


def test_the_frozen_files_match_the_manifest():
    out = dt.verify_sources(DATA / "MANIFEST.tsv")
    assert out["matches"].all()
    assert set(out["file"]) == {
        "weekly_ae_activity_20261011.csv",
        "bank-holidays_20261024.json",
    }


def test_the_frozen_file_has_the_shape_the_data_test_found(raw):
    assert CSV.stat().st_size == 3_829_935
    assert len(raw) == 43_185
    assert raw["AttendanceCategory"].value_counts().to_dict() == {
        "Unplanned": 18_269,
        "All": 18_269,
        "New planned": 6_647,
    }
    weeks = raw["WeekEndingDate"].drop_duplicates().sort_values()
    assert len(weeks) == 608
    assert (weeks.dt.dayofweek == 6).all()
    assert weeks.iloc[0] == pd.Timestamp("2015-02-22")
    assert weeks.iloc[-1] == pd.Timestamp("2026-10-11")
    assert raw["TreatmentLocation"].nunique() == 32
    assert raw["HBT"].nunique() == 14


def test_the_quality_report_matches_the_data_test(raw):
    q = dt.quality_report(raw)
    assert q["missing_values"] == 0
    assert q["duplicate_key_rows"] == 2
    assert q["duplicate_keys"] == [("2015-05-03", "G405H")]
    assert q["unplanned_zero_attendances"] == 0
    assert q["within_plus_over_not_total"] == 0
    assert q["percentage_max_gap"] <= 0.05 + 1e-9
    assert q["site_weeks"] == 18_268
    assert q["all_not_unplanned_plus_planned"] == 0
    assert q["first_new_planned_week"] == "2020-11-08"
    assert q["sites_in_more_than_one_board"] == []


def test_thirty_sites_report_every_week_from_7_june_2015(flagged):
    wide = dt.series_from(flagged)
    sites = [c for c in wide.columns if c != "Scotland"]
    assert len(sites) == 30
    assert wide.index[0] == pd.Timestamp("2015-06-07")
    assert len(wide) == 593
    assert wide[sites].notna().all().all()
    np.testing.assert_array_equal(wide["Scotland"], wide[sites].sum(axis=1))


def test_nothing_is_dropped_silently(raw, flagged):
    assert len(flagged) == len(raw)
    aside = flagged[~flagged["in_series"]]
    assert (aside["exclusion_reason"] != "").all()
    assert int(flagged["in_series"].sum()) == 30 * 593
    reasons = aside["exclusion_reason"].value_counts()
    assert len(reasons) == 2


def test_the_national_outliers_are_the_data_tests_nine_weeks(raw):
    weeks = dt.national_outliers(raw)
    assert [str(d.date()) for d in weeks[weeks].index] == [
        "2016-12-25",
        "2017-12-17",
        "2018-03-04",
        "2020-03-29",
        "2020-04-05",
        "2020-04-12",
        "2021-12-26",
        "2023-01-15",
        "2025-12-28",
    ]


def test_the_site_outliers_are_the_data_tests_48_at_22_sites(flagged):
    unp = flagged[flagged["AttendanceCategory"] == "Unplanned"]
    hits = unp[unp["site_outlier"]]
    assert len(hits) == 48
    assert hits["TreatmentLocation"].nunique() == 22
    assert int(hits["covid_period"].sum()) == 16

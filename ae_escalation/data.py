"""Load, verify, clean, flag and keep the PHS weekly A&E file.

The series is weekly Unplanned attendances from the week ending 7 June 2015,
per hospital and nationally. Nothing is dropped silently: every row of the file
stays in the flagged frame, and a row left out of the series says why.
"""

import csv
import hashlib
import io
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .timing import complete_weeks

DIGEST = r"^[0-9a-f]{64}$"
CATEGORY = "Unplanned"
ATTENDANCES = "NumberOfAttendancesEpisode"
WITHIN_4H = "NumberWithin4HoursEpisode"
KEY = ["WeekEndingDate", "TreatmentLocation", "AttendanceCategory"]
NATIONAL = "Scotland"
# Glasgow's emergency departments were reconfigured in May 2015, so the board
# and national series step down by about 1,200 a week then; every model starts
# after it (data test, section 1).
SERIES_START = pd.Timestamp("2015-06-07")
# Used only to split what is reported, never by the design's rules.
COVID_PERIOD = (pd.Timestamp("2020-03-01"), pd.Timestamp("2022-03-31"))
# The data test compared the file to w/e 4 Oct 2026 with this one and found
# revisions in the three newest weeks of the older file, all small and upward,
# so the newest three are provisional.
PROVISIONAL_WEEKS = 3

# The 30 emergency departments' names, from PHS's Hospital Codes lookup
# (Current NHS Hospitals in Scotland, OGL), as the probes read them. They are
# labels only; no figure depends on them.
HOSPITAL_NAMES = {
    "A111H": "University Hospital Crosshouse",
    "A210H": "University Hospital Ayr",
    "B120H": "Borders General Hospital",
    "C121H": "Lorn & Islands Hospital",
    "C313H": "Inverclyde Royal Hospital",
    "C418H": "Royal Alexandra Hospital",
    "F704H": "Victoria Hospital",
    "G107H": "Glasgow Royal Infirmary",
    "G405H": "Queen Elizabeth University Hospital",
    "G513H": "Royal Hospital for Children",
    "H103H": "Caithness General Hospital",
    "H202H": "Raigmore Hospital",
    "H212H": "Belford Hospital",
    "L106H": "University Hospital Monklands",
    "L302H": "University Hospital Hairmyres",
    "L308H": "University Hospital Wishaw",
    "N101H": "Aberdeen Royal Infirmary",
    "N121H": "Royal Aberdeen Children's Hospital",
    "N411H": "Dr Gray's Hospital",
    "R103H": "The Balfour",
    "S308H": "St John's Hospital",
    "S314H": "Royal Infirmary of Edinburgh at Little France",
    "S319H": "Royal Hospital for Children and Young People",
    "T101H": "Ninewells Hospital",
    "T202H": "Perth Royal Infirmary",
    "V217H": "Forth Valley Royal Hospital",
    "W107H": "Western Isles Hospital",
    "Y144H": "Galloway Community Hospital",
    "Y146H": "Dumfries & Galloway Royal Infirmary",
    "Z102H": "Gilbert Bain Hospital",
}


class SourceRecord(BaseModel):
    """One manifest row: a file's source, licence and expected hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    file: str = Field(min_length=1)
    source_url: str = Field(pattern=r"^https?://")
    publisher_page_url: str = Field(pattern=r"^https?://")
    licence: str = Field(min_length=1)
    access_date: date
    bytes: int = Field(gt=0)
    sha256: str = Field(pattern=DIGEST)


def sha256_of(path):
    """Return the SHA-256 of a file's bytes as 64 lower-case hex digits."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_manifest(path):
    """Return a tab-separated manifest's rows, each checked as a record.

    Parameters
    ----------
    path : str or pathlib.Path
        The manifest file.

    Returns
    -------
    list of SourceRecord
    """
    with open(path, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return [SourceRecord.model_validate(row) for row in rows]


def verify_sources(manifest):
    """Return each file the manifest lists and whether it still matches.

    I adapted this from Agentic AI Systems' manifest check (agentic_system.py,
    SourceRecord and verify_sources), adding the licence, so one table shows
    provenance and integrity together.

    Parameters
    ----------
    manifest : str or pathlib.Path
        The manifest, in the folder that holds the files it lists.

    Returns
    -------
    pandas.DataFrame
        One row per file: file, publisher page, licence, access date, bytes,
        sha256 and matches, which is True only when the size and the SHA-256
        both agree.
    """
    rows = []
    for record in read_manifest(manifest):
        path = Path(manifest).parent / record.file
        payload = path.read_bytes() if path.is_file() else b""
        rows.append(
            {
                "file": record.file,
                "publisher page": record.publisher_page_url,
                "licence": record.licence,
                "access date": record.access_date.isoformat(),
                "bytes": record.bytes,
                "sha256": record.sha256,
                "matches": len(payload) == record.bytes
                and hashlib.sha256(payload).hexdigest() == record.sha256,
            }
        )
    return pd.DataFrame(rows)


def load_weekly(path, sha256):
    """Return the PHS weekly file as a DataFrame, after checking its SHA-256.

    I hash the bytes and parse those same bytes, so the file read is the file
    checked. A mismatch stops the workflow here rather than letting a changed
    file through.

    Parameters
    ----------
    path : str or pathlib.Path
        The CSV file.
    sha256 : str
        The SHA-256 the file must have.

    Returns
    -------
    pandas.DataFrame
        Every row of the file, with WeekEndingDate as dates.

    Raises
    ------
    ValueError
        If the file's SHA-256 is not sha256.
    """
    payload = Path(path).read_bytes()
    found = hashlib.sha256(payload).hexdigest()
    if found != sha256:
        raise ValueError(
            f"{Path(path).name}: SHA-256 is {found}, expected {sha256}"
        )
    df = pd.read_csv(io.BytesIO(payload), dtype={"WeekEndingDate": str})
    df["WeekEndingDate"] = pd.to_datetime(
        df["WeekEndingDate"], format="%Y%m%d"
    )
    return df


def to_wide(df, unit_col, category=CATEGORY, value_col=ATTENDANCES):
    """Return weeks by units for one attendance category.

    A week a unit did not report stays NaN, and rows sharing a key are summed.
    df is not changed.

    Parameters
    ----------
    df : pandas.DataFrame
        Rows in the PHS file's layout.
    unit_col : str
        The column that names the unit, such as TreatmentLocation.
    category : str, default "Unplanned"
        The AttendanceCategory to keep.
    value_col : str, default "NumberOfAttendancesEpisode"
        The count to spread.

    Returns
    -------
    pandas.DataFrame
        Indexed by every week ending from the first to the last in df, one
        column per unit, in sorted order.
    """
    sub = df[df["AttendanceCategory"] == category]
    wide = sub.pivot_table(
        index="WeekEndingDate",
        columns=unit_col,
        values=value_col,
        aggfunc="sum",
    )
    weeks = complete_weeks(
        df["WeekEndingDate"].min(), df["WeekEndingDate"].max()
    )
    return wide.reindex(weeks).sort_index(axis=1)


def run_summary(s):
    """Return a series' first and last week, weeks present and gaps.

    Parameters
    ----------
    s : pandas.Series
        One unit's weekly values on a complete calendar. It is not changed.

    Returns
    -------
    dict
        first, last, n_present, gaps (each as first week, last week, length)
        and unbroken.
    """
    present = s.notna().to_numpy()
    if not present.any():
        return {
            "first": None,
            "last": None,
            "n_present": 0,
            "gaps": [],
            "unbroken": False,
        }
    idx = s.index
    i0 = int(np.argmax(present))
    i1 = len(present) - 1 - int(np.argmax(present[::-1]))
    gaps = []
    i = i0
    while i <= i1:
        if not present[i]:
            j = i
            while not present[j + 1]:
                j += 1
            gaps.append((idx[i], idx[j], j - i + 1))
            i = j + 1
        else:
            i += 1
    return {
        "first": idx[i0],
        "last": idx[i1],
        "n_present": int(present.sum()),
        "gaps": gaps,
        "unbroken": not gaps,
    }


def flag_outliers(s, window=9, k=5.0):
    """Return True where a week is far from its neighbours.

    The measure is a robust z: the gap to a centred rolling median, over 1.4826
    times the median absolute deviation of those gaps across the whole series.
    It flags and keeps; nothing here removes a value. s is not changed.

    Parameters
    ----------
    s : pandas.Series
        One series of weekly values.
    window : int, default 9
        The width of the centred median.
    k : float, default 5.0
        The robust z a week must exceed.

    Returns
    -------
    pandas.Series of bool
        Indexed like s.
    """
    y = s.astype(float)
    med = y.rolling(window, center=True, min_periods=window // 2 + 1).median()
    resid = y - med
    if not np.isfinite(resid).any():
        return pd.Series(False, index=s.index)
    centre = np.nanmedian(resid)
    scale = 1.4826 * np.nanmedian(np.abs(resid - centre))
    if not np.isfinite(scale) or scale == 0:
        return pd.Series(False, index=s.index)
    return (np.abs(resid) / scale > k).fillna(False)


def national_outliers(df, window=9, k=5.0):
    """Return the national weeks flag_outliers marks, over the whole file.

    The national series here is the sum of every site's Unplanned attendances
    from the file's first week, as the data test built it. df is not changed.

    Returns
    -------
    pandas.Series of bool
        Indexed by week ending.
    """
    national = to_wide(df, "TreatmentLocation").sum(axis=1, min_count=1)
    return flag_outliers(national, window=window, k=k)


def quality_report(df):
    """Return the data test's quality checks for the file, as counts.

    df is not changed.

    Returns
    -------
    dict
        missing_values, duplicate_key_rows (rows repeating an earlier row's
        key), duplicate_keys (each repeated week and site),
        unplanned_zero_attendances, within_plus_over_not_total (Unplanned rows
        where the 4-hour counts do not add up), percentage_max_gap (the stored
        4-hour percentage against the counts, in points), site_weeks,
        all_not_unplanned_plus_planned, first_new_planned_week and
        sites_in_more_than_one_board.
    """
    unp = df[df["AttendanceCategory"] == CATEGORY]
    dup = df[df.duplicated(KEY, keep=False)]
    pct = 100 * unp[WITHIN_4H] / unp[ATTENDANCES]
    piv = df.pivot_table(
        index=["WeekEndingDate", "TreatmentLocation"],
        columns="AttendanceCategory",
        values=ATTENDANCES,
        aggfunc="sum",
    )
    planned = piv["New planned"].fillna(0)
    boards = df.groupby("TreatmentLocation")["HBT"].nunique()
    first_planned = df.loc[
        df["AttendanceCategory"] == "New planned", "WeekEndingDate"
    ].min()
    return {
        "missing_values": int(df.isna().sum().sum()),
        "duplicate_key_rows": int(df.duplicated(KEY).sum()),
        "duplicate_keys": sorted(
            {
                (str(w.date()), s)
                for w, s in zip(
                    dup["WeekEndingDate"], dup["TreatmentLocation"]
                )
            }
        ),
        "unplanned_zero_attendances": int((unp[ATTENDANCES] == 0).sum()),
        "within_plus_over_not_total": int(
            (
                unp[WITHIN_4H] + unp["NumberOver4HoursEpisode"]
                != unp[ATTENDANCES]
            ).sum()
        ),
        "percentage_max_gap": float(
            (pct - unp["PercentageWithin4HoursEpisode"]).abs().max()
        ),
        "site_weeks": int(len(piv)),
        "all_not_unplanned_plus_planned": int(
            ((piv["All"] - piv[CATEGORY] - planned).abs() > 0).sum()
        ),
        "first_new_planned_week": str(first_planned.date()),
        "sites_in_more_than_one_board": boards[boards > 1].index.tolist(),
    }


def flag_and_keep(
    df,
    start=SERIES_START,
    covid=COVID_PERIOD,
    provisional_weeks=PROVISIONAL_WEEKS,
    window=9,
    k=5.0,
):
    """Return a copy of df with every row kept, flagged and accounted for.

    I follow the flag-and-keep pattern of AI Programming Foundations
    (data_workflow.ipynb, flag_unexplained_payments, cell 27): no row is
    dropped, and a row set aside carries its reason, so it can still be counted
    and reported, and changing the rule brings it back.

    Parameters
    ----------
    df : pandas.DataFrame
        The file as load_weekly returns it. It is not changed.
    start : str or pandas.Timestamp, default 7 June 2015
        The first week of the series.
    covid : tuple of two Timestamps
        The first and last week ending of the COVID period, both included.
    provisional_weeks : int, default 3
        How many of the newest weeks may still be revised.
    window, k
        As flag_outliers, for each site's Unplanned series over the whole file.

    Returns
    -------
    pandas.DataFrame
        Every row of df, plus in_series (Unplanned and from start),
        exclusion_reason (empty in the series), duplicate_key, site_outlier,
        covid_period and provisional.
    """
    start = pd.Timestamp(start)
    out = df.copy()
    week = out["WeekEndingDate"]
    unplanned = out["AttendanceCategory"] == CATEGORY
    early = week < start
    out["in_series"] = unplanned & ~early
    out["exclusion_reason"] = np.where(
        ~unplanned,
        "not the Unplanned category, which is the series",
        np.where(
            early,
            f"before w/e {start.day} {start:%b %Y}, the series' first week",
            "",
        ),
    )
    out["duplicate_key"] = out.duplicated(KEY, keep=False)
    wide = to_wide(df, "TreatmentLocation")
    hits = set()
    for code in wide.columns:
        flags = flag_outliers(wide[code].dropna(), window=window, k=k)
        hits.update((w, code) for w in flags[flags].index)
    pairs = zip(week, out["TreatmentLocation"])
    out["site_outlier"] = unplanned.to_numpy() & np.array(
        [p in hits for p in pairs]
    )
    out["covid_period"] = (week >= pd.Timestamp(covid[0])) & (
        week <= pd.Timestamp(covid[1])
    )
    newest = np.sort(week.unique())[::-1][:provisional_weeks]
    out["provisional"] = week.isin(newest)
    return out


def series_from(flagged, value_col=ATTENDANCES):
    """Return the series as weeks by hospital, plus the national series.

    Only rows with in_series True are used. A hospital with no week in the
    series is not a column, and the national series is the sum of the hospitals
    each week. flagged is not changed.

    Parameters
    ----------
    flagged : pandas.DataFrame
        As flag_and_keep returns it.
    value_col : str, default "NumberOfAttendancesEpisode"
        The count to spread, such as NumberWithin4HoursEpisode for the pressure
        match.

    Returns
    -------
    pandas.DataFrame of float
        Indexed by week ending, one column per hospital code in sorted order,
        then Scotland.
    """
    rows = flagged[flagged["in_series"]]
    wide = to_wide(rows, "TreatmentLocation", value_col=value_col)
    wide = wide.loc[:, wide.notna().any()].astype(float)
    wide[NATIONAL] = wide.sum(axis=1, min_count=1)
    return wide

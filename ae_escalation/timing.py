"""The calendar, the Tuesday release and as-of views.

Public Health Scotland publishes each week on the Tuesday 9 days after its
Sunday week ending. An origin is the latest week released; every rule and tool
works as of an origin and sees only the weeks up to it. The four release
horizons are the next four week endings after the release, which are data
horizons 2 to 5.
"""

import numpy as np
import pandas as pd

RELEASE_LAG = pd.Timedelta(days=9)
RELEASE_HORIZONS = (1, 2, 3, 4)
DATA_HORIZONS = (2, 3, 4, 5)


def complete_weeks(start, end):
    """Return every Sunday week ending from start to end, both included.

    Parameters
    ----------
    start, end : str or pandas.Timestamp
        The first and last week endings, both Sundays.

    Returns
    -------
    pandas.DatetimeIndex
        The week endings, seven days apart.
    """
    return pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="7D")


def year_position(dates):
    """Return each date's place in its year, from 0 on 1 January to under 1.

    Parameters
    ----------
    dates : array-like of dates
        It is not changed.

    Returns
    -------
    numpy.ndarray of float
    """
    dates = pd.DatetimeIndex(dates)
    days = np.where(dates.is_leap_year, 366.0, 365.0)
    return (dates.dayofyear.to_numpy() - 1) / days


def iso_slots(dates):
    """Return each week's slot in the year and its ISO year.

    The slot is the ISO week less one, with week 53 joining week 52, so a year
    has 52 slots.

    Parameters
    ----------
    dates : array-like of dates
        Week endings. It is not changed.

    Returns
    -------
    tuple of two numpy.ndarray of int
        The slots, 0 to 51, and the ISO years.
    """
    iso = pd.DatetimeIndex(dates).isocalendar()
    slot = np.minimum(iso["week"].to_numpy(dtype=int), 52) - 1
    return slot, iso["year"].to_numpy(dtype=int)


def _sunday(day):
    """A day as a Timestamp, refused unless it is a Sunday."""
    day = pd.Timestamp(day)
    if day.dayofweek != 6:
        raise ValueError(f"{day.date()} is not a Sunday week ending")
    return day


def release_date(origin):
    """Return the Tuesday on which the week ending origin is published.

    Raises
    ------
    ValueError
        If origin is not a Sunday.
    """
    return _sunday(origin) + RELEASE_LAG


def origin_for(day):
    """Return the latest week ending released on or before day.

    Parameters
    ----------
    day : str or pandas.Timestamp
        Any date, such as the Tuesday of a release.

    Returns
    -------
    pandas.Timestamp
        A Sunday.
    """
    last = pd.Timestamp(day) - RELEASE_LAG
    return last - pd.Timedelta(days=(last.dayofweek + 1) % 7)


def release_horizon_weeks(origin):
    """Return the four week endings at release horizons 1 to 4 of an origin.

    The first is the week in progress on release day, and the other three are
    still ahead.

    Returns
    -------
    pandas.DatetimeIndex
    """
    origin = _sunday(origin)
    return pd.DatetimeIndex(
        [origin + pd.Timedelta(weeks=h) for h in DATA_HORIZONS]
    )


def data_horizon(release_horizon):
    """Return the data horizon, in weeks after the origin, of a release
    horizon from 1 to 4."""
    if release_horizon not in RELEASE_HORIZONS:
        raise ValueError(f"release horizon must be 1 to 4: {release_horizon}")
    return release_horizon + 1


def release_horizon(data_horizon):
    """Return the release horizon of a data horizon from 2 to 5."""
    if data_horizon not in DATA_HORIZONS:
        raise ValueError(f"data horizon must be 2 to 5: {data_horizon}")
    return data_horizon - 1


def as_of_view(frame, origin):
    """Return a copy of the rows of frame up to and including origin.

    These are the weeks released by the origin, so whatever reads the view
    cannot see a later week. frame is not changed.

    Parameters
    ----------
    frame : pandas.DataFrame or pandas.Series
        Indexed by week ending.
    origin : str or pandas.Timestamp
        The latest week released.

    Returns
    -------
    pandas.DataFrame or pandas.Series
    """
    return frame.loc[frame.index <= pd.Timestamp(origin)].copy()

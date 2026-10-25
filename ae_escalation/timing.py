"""The calendar, the Tuesday release and as-of views."""

import pandas as pd


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

"""Shared fixtures: the frozen data, loaded once for the tests that need it."""

from pathlib import Path

import pytest

from ae_escalation import data as dt

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
CSV = DATA / "weekly_ae_activity_20261011.csv"
CSV_SHA256 = "9ffe7f3364a1592f7c8d2d083df9fe4425d4fd2bd84dfed0a3567bececcd1a38"


@pytest.fixture(scope="session")
def raw():
    """The PHS file as loaded, hash-checked. Tests must not change it."""
    return dt.load_weekly(CSV, CSV_SHA256)


@pytest.fixture(scope="session")
def flagged(raw):
    return dt.flag_and_keep(raw)

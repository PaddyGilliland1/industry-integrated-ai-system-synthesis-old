"""Shared fixtures: the frozen data, loaded once for the tests that need it."""

from pathlib import Path

import pytest

from ae_escalation import data as dt

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
CSV = DATA / "weekly_ae_activity_20261011.csv"
CSV_SHA256 = "9ffe7f3364a1592f7c8d2d083df9fe4425d4fd2bd84dfed0a3567bececcd1a38"
HOLIDAYS = DATA / "bank-holidays_20261024.json"
HOLIDAYS_SHA256 = (
    "538b3482c28b85ecd2db606a0d5ae6ad17248900b6498700ce0a48d26a3ecde6"
)


@pytest.fixture(scope="session")
def raw():
    """The PHS file as loaded, hash-checked. Tests must not change it."""
    return dt.load_weekly(CSV, CSV_SHA256)


@pytest.fixture(scope="session")
def flagged(raw):
    return dt.flag_and_keep(raw)


@pytest.fixture(scope="session")
def replay_run(flagged):
    """The design run on the replay set's five series. Tests must not
    change it."""
    from ae_escalation import design as ds

    return ds.run_design(dt.series_from(flagged)[list(ds.REPLAY)])


@pytest.fixture(scope="session")
def holidays():
    return dt.load_bank_holidays(HOLIDAYS, HOLIDAYS_SHA256)


@pytest.fixture
def settings():
    from ae_escalation import config as cf

    return cf.load_config(REPO / "config.json")

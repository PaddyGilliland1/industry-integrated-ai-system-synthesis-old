"""The GRU comparator: CPU only, seeded, refitted each January, no leak."""

import numpy as np
import pandas as pd

from ae_escalation import gru
from ae_escalation import timing as tm

FAST = 15


def synthetic():
    """A seasonal weekly series with noise."""
    dates = tm.complete_weeks("2015-06-07", "2019-06-30")
    n = len(dates)
    rng = np.random.default_rng(11)
    y = 1000 * (1 + 0.1 * np.sin(2 * np.pi * np.arange(n) / 52))
    return pd.Series(y + rng.normal(0, 15, n), index=dates)


def test_features_read_only_weeks_up_to_the_origin():
    s = synthetic()
    cal = tm.complete_weeks(s.index[0], s.index[-1] + pd.Timedelta(weeks=5))
    pos = tm.year_position(cal)
    y = s.to_numpy()
    later = y.copy()
    later[121:] = 1e6
    a = gru.features(y, pos, 120, H=5)
    b = gru.features(later, pos, 120, H=5)
    for x, z in zip(a, b):
        np.testing.assert_array_equal(x, z)


def test_refits_are_the_first_origin_and_the_first_origin_of_each_year():
    dates = tm.complete_weeks("2017-11-05", "2019-02-24")
    origins = np.arange(len(dates))
    refits = gru.refit_origins(dates, origins)
    assert [str(dates[r].date()) for r in refits] == [
        "2017-11-05",
        "2018-01-07",
        "2019-01-06",
    ]


def test_the_comparator_runs_on_the_cpu_with_three_seeds():
    s = synthetic()
    origins, out = gru.run_gru(
        s, H=5, first_target="2018-07-01", max_epochs=FAST
    )
    assert out.shape == (len(origins), 5)
    assert np.isfinite(out).all()
    assert gru.SEEDS == (0, 1, 2)
    net = gru.GRUForecaster(H=5)
    assert all(p.device.type == "cpu" for p in net.parameters())


def test_the_same_seeds_give_the_same_forecasts():
    s = synthetic()
    _, a = gru.run_gru(s, H=4, first_target="2018-07-01", max_epochs=FAST)
    _, b = gru.run_gru(s, H=4, first_target="2018-07-01", max_epochs=FAST)
    np.testing.assert_array_equal(a, b)


def test_no_forecast_sees_a_week_after_its_origin():
    s = synthetic()
    cut = pd.Timestamp("2018-10-07")
    later = s.copy()
    later[later.index > cut] = 50.0
    oa, a = gru.run_gru(s, H=4, first_target="2018-07-01", max_epochs=FAST)
    ob, b = gru.run_gru(later, H=4, first_target="2018-07-01", max_epochs=FAST)
    np.testing.assert_array_equal(oa, ob)
    upto = s.index[oa] <= cut
    np.testing.assert_array_equal(a[upto], b[upto])


def test_the_thread_setting_is_put_back():
    import torch

    before = torch.get_num_threads()
    gru.run_gru(synthetic(), H=4, first_target="2019-01-06", max_epochs=2)
    assert torch.get_num_threads() == before


def test_the_long_frame_keeps_targets_from_the_first_target():
    s = synthetic()
    wide = pd.DataFrame({"X": s})
    long = gru.gru_long(
        wide, ["X"], H=4, first_target="2018-07-01", max_epochs=2
    )
    assert set(long["model"]) == {"gru"}
    assert long["target"].min() == pd.Timestamp("2018-07-01")
    assert long["target"].max() == s.index[-1]

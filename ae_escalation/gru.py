"""The GRU comparator: a small seeded GRU on the CPU, run beside the simple
models on the five named series. It never sets the flag and is never shown to
managers (D-ARCH-26).

The set-up is the data test's, so its figures reproduce: one GRU layer of 16
units reads the latest 12 weeks scaled by the 52-week mean with calendar
terms, and a dense head also sees the target weeks' calendar terms and last
year's same weeks. It is refitted each January on the weeks known then, with
early stopping on the last 26 training windows, and the forecast is the mean
of three seeds.
"""

import numpy as np
import pandas as pd
import torch

from .timing import complete_weeks, year_position

L, LEVEL = 12, 52
SEEDS = (0, 1, 2)
MAX_EPOCHS, VAL_N, PATIENCE = 600, 26, 60
LR, WEIGHT_DECAY = 5e-3, 1e-4
# The data test ran on four CPU threads; I keep four so its figures
# reproduce.
THREADS = 4


class GRUForecaster(torch.nn.Module):
    """A one-layer GRU over the input weeks and a linear head for the H
    target weeks.

    I adapted Deep Learning Systems' recurrent forecaster
    (deep_learning.ipynb, ForecastRNN with cell="gru", cell 56): the same GRU
    and linear head, one layer here, and the head also reads the target
    weeks' calendar terms and last year's same weeks.
    """

    def __init__(self, H, hidden=16):
        """Build the GRU and the head that maps its state to H."""
        super().__init__()
        self.gru = torch.nn.GRU(
            input_size=3, hidden_size=hidden, batch_first=True
        )
        self.head = torch.nn.Linear(hidden + 2 * H + H, H)

    def forward(self, seq, extra):
        """Return the scaled forecasts, shaped (batch, H)."""
        _, h_n = self.gru(seq)
        return self.head(torch.cat([h_n[-1], extra], dim=1))


def features(y, pos, t0, H):
    """Return one origin's inputs: the scaled weeks, the head's extras and the
    level.

    The level is the mean of the 52 weeks up to t0. The sequence is the
    latest 12 weeks over the level, with the sine and cosine of their place
    in the year. The extras are the target weeks' sine and cosine and last
    year's same weeks over the level, all at or before t0. y is not changed.

    Returns
    -------
    tuple of numpy.ndarray, numpy.ndarray and float
    """
    level = y[t0 - LEVEL + 1 : t0 + 1].mean()
    win = np.arange(t0 - L + 1, t0 + 1)
    seq = np.column_stack(
        [
            y[win] / level,
            np.sin(2 * np.pi * pos[win]),
            np.cos(2 * np.pi * pos[win]),
        ]
    )
    tgt = np.arange(t0 + 1, t0 + H + 1)
    extra = np.concatenate(
        [
            np.sin(2 * np.pi * pos[tgt]),
            np.cos(2 * np.pi * pos[tgt]),
            y[tgt - 52] / level,
        ]
    )
    return seq, extra, level


def fit(y, pos, t_refit, seed, H, max_epochs=MAX_EPOCHS):
    """Return a GRU trained on the windows whose targets are known at t_refit.

    The last 26 windows are held out for early stopping, and the network
    with the lowest held-out loss is kept. y is the series up to t_refit,
    and it is not changed.
    """
    origins = np.arange(LEVEL - 1, t_refit - H + 1)
    X = [features(y, pos, t0, H) for t0 in origins]
    seq = torch.tensor(np.stack([x[0] for x in X]), dtype=torch.float32)
    ext = torch.tensor(np.stack([x[1] for x in X]), dtype=torch.float32)
    tgt = torch.tensor(
        np.stack(
            [y[t0 + 1 : t0 + H + 1] / X[i][2] for i, t0 in enumerate(origins)]
        ),
        dtype=torch.float32,
    )
    n_tr = len(origins) - VAL_N
    torch.manual_seed(seed)
    net = GRUForecaster(H)
    opt = torch.optim.Adam(net.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    best, best_state, stale = np.inf, None, 0
    for _ in range(max_epochs):
        net.train()
        opt.zero_grad()
        loss = torch.mean((net(seq[:n_tr], ext[:n_tr]) - tgt[:n_tr]) ** 2)
        loss.backward()
        opt.step()
        net.eval()
        with torch.no_grad():
            v = torch.mean((net(seq[n_tr:], ext[n_tr:]) - tgt[n_tr:]) ** 2)
        if v.item() < best - 1e-7:
            best, stale = v.item(), 0
            best_state = {k: t.clone() for k, t in net.state_dict().items()}
        else:
            stale += 1
            if stale >= PATIENCE:
                break
    net.load_state_dict(best_state)
    net.eval()
    return net


def refit_origins(dates, origins):
    """Return the refit origins: the first origin and the first origin of
    each new calendar year."""
    years = pd.DatetimeIndex(dates)[origins].year
    return [origins[0]] + [
        o for i, o in enumerate(origins[1:], 1) if years[i] != years[i - 1]
    ]


def run_gru(series, H, first_target, seeds=SEEDS, max_epochs=MAX_EPOCHS):
    """Return the GRU's forecasts at every origin from H weeks before
    first_target.

    Between refits the fitted networks still read the latest 12 weeks at
    every origin, so no forecast sees a week after its origin. The thread
    setting is restored afterwards. series is not changed.

    Parameters
    ----------
    series : pandas.Series
        One series, indexed by week ending.
    H : int
        Data horizons 1 to H: 4 for the data test, 5 for the release
        horizons.
    first_target : str or pandas.Timestamp
    seeds : tuple of int, default (0, 1, 2)
    max_epochs : int, default 600

    Returns
    -------
    tuple of numpy.ndarray of int and numpy.ndarray
        The origins, and the forecasts shaped (origins, H).
    """
    dates = series.index
    y = series.to_numpy(dtype=float)
    cal = complete_weeks(dates[0], dates[-1] + pd.Timedelta(weeks=H))
    pos = year_position(cal)
    first = int(np.searchsorted(dates, pd.Timestamp(first_target)))
    origins = np.arange(first - H, len(y) - 1)
    threads = torch.get_num_threads()
    torch.set_num_threads(THREADS)
    try:
        nets = {}
        for t_r in refit_origins(dates, origins):
            nets[t_r] = [
                fit(y[: t_r + 1], pos, t_r, s, H, max_epochs) for s in seeds
            ]
        refits = sorted(nets)
        out = np.full((len(origins), H), np.nan)
        for i, t0 in enumerate(origins):
            t_r = max(r for r in refits if r <= t0)
            seq, extra, level = features(y[: t0 + 1], pos, t0, H)
            with torch.no_grad():
                preds = [
                    n(
                        torch.tensor(seq[None], dtype=torch.float32),
                        torch.tensor(extra[None], dtype=torch.float32),
                    ).numpy()[0]
                    for n in nets[t_r]
                ]
            out[i] = np.mean(preds, axis=0) * level
    finally:
        torch.set_num_threads(threads)
    return origins, out


def gru_long(wide, series, H, first_target, max_epochs=MAX_EPOCHS):
    """Return the GRU's forecasts on the named series as a back-test frame.

    A row is kept when its target is in the data and on or after
    first_target, as backtest.backtest_long keeps them. wide is not changed.
    """
    rows = []
    for code in series:
        s = wide[code].astype(float)
        dates, y = s.index, s.to_numpy()
        first = int(np.searchsorted(dates, pd.Timestamp(first_target)))
        origins, out = run_gru(s, H, first_target, max_epochs=max_epochs)
        for i, t0 in enumerate(origins):
            for h in range(1, H + 1):
                ti = t0 + h
                if ti >= len(y) or ti < first:
                    continue
                rows.append(
                    (
                        code,
                        "gru",
                        dates[t0],
                        h,
                        dates[ti],
                        y[ti],
                        out[i, h - 1],
                    )
                )
    return pd.DataFrame(
        rows,
        columns=[
            "series",
            "model",
            "origin",
            "h",
            "target",
            "actual",
            "forecast",
        ],
    )

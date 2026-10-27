# Weekly A&E demand and escalation briefing

## Project description

- **Status, additional information only:** at this stage the system gives the duty manager additional
  information beside their existing process. It replaces no current process and sets no staffing on
  its own. Becoming a primary operational tool needs shadow mode, a pilot and tuning over time, which
  is achievable but not yet done.
- **What it does:** each week, code forecasts unplanned attendances at Scotland's emergency
  departments for the four weeks after the Tuesday data release, and sets each hospital's demand
  level by fixed rules.
- **Where the AI sits:** for a hospital the rules pick out, a language-model Investigator drafts a
  demand brief from read-only tools, and a Reviewer checks every figure in code, then the wording.
- **Who decides:** a duty manager approves, edits or rejects each brief. Code sets the staffing
  actions for an approved brief, and the language model drafts each notification, which code checks
  before writing it to an outbox file, never sent.
- **What the demand level means:** demand unusually high for the time of year. It is not pressure,
  need or priority.
- **What is real:** Public Health Scotland's weekly A&E attendances and GOV.UK's Scottish bank
  holidays.
- **The drift latch:** once the drift alarm fires, the latch stays set, like an alarm that stays on
  until someone resets it. While it is set, the forecasts are marked untrusted, and only a person can
  reset it.
- **What is simulated or my own design:** the seasonal capacity the level is measured against, the
  latch resets and the staff acknowledgements are simulated; the bands, the staffing actions and
  their reply deadlines are my design.
- **The spot check:** `ae_escalation_spot_check.ipynb` runs the design on the real data and replays
  every recorded model call, so it needs no language model and no GPU.
- **The case study:** `ae_escalation_case_study.md`, rendered to `ae_escalation_case_study.pdf`, sets
  out the design, its evaluation and its limits.

## Dataset

- **Name:** Weekly A&E Activity and Waiting Times, Public Health Scotland, on Scottish Health and
  Social Care Open Data.
- **Source:** https://www.opendata.nhs.scot/dataset/weekly-accident-and-emergency-activity-and-waiting-times
- **Licence:** UK Open Government Licence (OGL).
- **File:** `data/weekly_ae_activity_20261011.csv`, which ships in this repository, accessed on
  24 Oct 2026. SHA-256: `9ffe7f3364a1592f7c8d2d083df9fe4425d4fd2bd84dfed0a3567bececcd1a38`.
- **To fetch it again:** the publisher replaces this file each Tuesday, so the copy in `data/` is the
  one the notebook was run on. Until the next release it can be downloaded from the `source_url` in
  `data/MANIFEST.tsv` into `data/` and checked with
  `sha256sum data/weekly_ae_activity_20261011.csv`. A newer file will not match the hash, and the
  notebook stops if the hash differs.
- **Bank holidays:** `data/bank-holidays_20261024.json`, GOV.UK's bank-holidays JSON
  (https://www.gov.uk/bank-holidays.json), OGL, frozen on 24 Oct 2026 and never fetched again.
  SHA-256: `538b3482c28b85ecd2db606a0d5ae6ad17248900b6498700ce0a48d26a3ecde6`.
- **Manifest:** `data/MANIFEST.tsv` gives each file's download URL, licence, access date, size and
  SHA-256.

## Python version

Python 3.12 or higher. The pinned packages in `requirements.txt` need 3.12, which meets the 3.9 or
higher the Environment Setup asks for. The notebook's first code cell prints the version it ran on,
Python 3.12.3.

## How to run

1. Clone this repository and move into its folder.
2. Create and activate a virtual environment with Python 3.12, then install the dependencies:

   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

   On Windows, activate it with `.venv\Scripts\activate` instead.

3. Open the notebook, then restart the kernel and run all cells:

   ```bash
   jupyter notebook ae_escalation_spot_check.ipynb
   ```

   Sections 5 to 7 replay the live runs from `recordings/`, so no language model runs and Ollama is
   not needed. The GRU comparator runs on the CPU.

4. Run the tests:

   ```bash
   python -m pytest
   ```

**Running the agents live** is not needed to reproduce the notebook. The local backend needs Ollama
serving `nemotron-3.5-lightning:30b-a3b` at the digest in `config.json`. The frontier backend needs a
Claude API key in a file named `.env` in the repository root, as `ANTHROPIC_API_KEY=...`; create it
only if you use that backend, and never commit it, which `.gitignore` prevents. The steps are:

```bash
python -m ae_escalation.live briefs --label <label>      # the seven replay briefs and the designed failure
python -m ae_escalation.live adequacy --label <label>    # record the adequacy test
python -m ae_escalation.live choose --label <label> --set <local|frontier> --initials <AB>
python -m ae_escalation.live notify --label <label>      # check each edit, draft the notifications
```

A label already recorded is never run again, and `--budget-s` sets one briefs run's time budget, at
most 1,800 seconds.

### The configuration, `config.json`

It holds no key, token or password.

| Field | What it sets |
|---|---|
| `llm_backend` | The model backend: `local`, the default, or `frontier` |
| `local.model` | The local model's name in Ollama, `nemotron-3.5-lightning:30b-a3b` |
| `local.digest` | The digest Ollama lists for that model, so a run traces to the exact weights |
| `local.temperature` | The local model's temperature, 0 |
| `local.endpoint` | Ollama's OpenAI-compatible endpoint on this machine |
| `local.reasoning_effort` | The thinking level sent to the model, one its Ollama card lists: `medium` |
| `local.num_predict` | The most tokens one local reply may generate, its thinking included: 8,192 |
| `frontier.model` | The frontier model, `claude-sonnet-5-5` |
| `frontier.temperature` | Null, so none is sent: the model takes only its default |
| `frontier.max_tokens` | The most tokens one frontier reply may generate, its thinking included: 16,000 |
| `frontier.effort` | How much the frontier model thinks, sent as its output effort: `medium` |
| `frontier.time_limit_s` | The limit on one frontier call, 420 seconds |
| `frontier.api_key_env` | The name of the variable in `.env` that holds the key, never the key itself |
| `agents.tool_call_cap` | The most tool calls in one Investigator pass, 8 |
| `agents.retries` | The one retry after a failed check |
| `agents.time_limit_s` | The limit on one model call, 240 seconds |
| `agents.run_budget_s` | The time budget for a whole live run, 840 seconds |
| `coordinator.start_hour` | The hour, UK time, the replay's clock starts on release day: 10 |
| `coordinator.reply_deadline_hours` | The assumed reply deadline by level: 48 hours at level 2, 24 at level 3, 12 at level 4 |
| `coordinator.acknowledged_share` | The simulated chance that an owner acknowledges an action at all, 0.75 |
| `coordinator.ack_hours` | The simulated range of hours before an acknowledgement, 2 to 72 |
| `data` | Each data file's name and SHA-256, checked when it loads |
| `seeds.gru` | The GRU's three seeds |
| `seeds.bootstrap` | The moving-block bootstrap's seed |
| `seeds.data_test_intervals`, `seeds.data_test_paired` | The seeds of the data test's intervals and paired comparison, which the back-test reproduces |
| `seeds.acknowledgements` | The seed of the simulated acknowledgements |
| `seeds.template_order` | The seed of the order the template pairs are shown in |

### How `requirements.txt` was created

The notebook was run top to bottom in a fresh virtual environment, and the file was then written
from that environment with `pip freeze > requirements.txt`. I added one line by hand at the top,
`--extra-index-url https://download.pytorch.org/whl/cpu`, so that pip finds the CPU build of torch
the freeze pins.

## How the components interact

![Figure 1: code decides, the agents explain, a person approves](figures/fig1_architecture.png)

Code decides, the agents explain and a person approves. Each arrow in Figure 1 is numbered, and
each box names the prior project it comes from or says it is new. The weekly flow, in nine steps:

1. **Weekly load.** Code reads the PHS file, checks its hash, cleans it and flags anomalies, keeping
   every row. It uses only the weeks released by the forecast origin; each Tuesday release covers
   the week that ended 9 days earlier.
2. **Forecast.** Seasonal naive, the 4-week moving average, a linear model and SA-MA forecast the
   four week-endings after the release, each with a range. One primary model drives the flag, and
   it is re-selected among the four at each latch reset. A GRU runs beside them as a comparator and
   is never shown to a manager.
3. **Flag and drift.** From the primary's own past errors, code works out each week's chance of
   reaching 1.05 times its simulated capacity, and flags an outlook when one week's chance is at
   least 50%. The drift alarm fires when actuals fall outside the drift interval two weeks running,
   and sets the drift latch.
4. **Screen.** Code sends on only a hospital that is flagged, or latched, which covers a surge or
   held level of 2 or more. Nothing else reaches the agents.
5. **Investigator.** It drafts the demand brief through five read-only tools: forecast, history,
   back-test error, track record and calendar. Code writes every figure with its label, and the
   level is the rule's.
6. **Reviewer.** Code checks every figure against its tool result and the level against the rule,
   then a language model checks the wording. A failure goes back once; a second failure reaches the
   manager marked "not verified, do not act".
7. **Approval.** The duty manager approves, edits or rejects. Only a verified brief can be approved,
   and every edit is checked again.
8. **Coordinate.** Code sets the staffing actions for the level, assigns each an owner and a reply
   deadline, tracks it and escalates it. The language model drafts each notification's wording,
   which passes the same figure check before it reaches the outbox.
9. **Audit.** Every tool call, draft, check and decision is logged, with the backend that wrote
   each brief, and can be replayed.

![Figure 3: one week, from the week's end to the duty manager's decision](figures/fig3_weekly_cycle.png)

*Figure 3. One week: Tuesday release to the duty manager's decision.* The dates illustrate the release timing for
one replay week, Ninewells Hospital's demand week ending 13 Jun 2021; that week's brief was rejected.

## Prior project artefacts reused

Each pattern is adapted for this project, never copied in as a file, and each module names the
pattern it reuses. Cell numbers count from 0.

| Project | Repository | File | Function or cell | Commit | Component here |
|---|---|---|---|---|---|
| AI Programming Foundations | https://github.com/PaddyGilliland1/ai-programming-foundations-project | `data_workflow.ipynb` | `standardise_columns` (cell 9), `flag_unexplained_payments` (cell 27) | `dc8dabd` | Load, clean, flag and keep (`ae_escalation/data.py`) |
| Conduct a Statistical Analysis Using Python | https://github.com/PaddyGilliland1/statistical-analysis-project | `analysis.ipynb` | `mean_with_ci` (cell 47), the trend line with `linregress` (cell 101), `bootstrap_slope` (cell 104), `paired_t_test` (cell 122) | `7556623` | The flag's and the drift interval's spread of past errors, the linear model's trend, the moving-block bootstrap and the paired comparison (`rules.py`, `backtest.py`, `forecasts.py`) |
| Deep Learning Systems | https://github.com/PaddyGilliland1/deep-learning-systems-project | `deep_learning.ipynb` | `naive_forecasts` (cell 24), `ForecastRNN` with `cell="gru"` (cell 56), `predict` (cell 61) | `5511b2b` | Seasonal naive and the moving average as bars to beat, and the GRU comparator (`forecasts.py`, `gru.py`) |
| Agentic AI Systems | https://github.com/PaddyGilliland1/agentic-ai-systems-project | `agentic_system.py` | `screen`, `Toolbox` with `verify_figures`, `ModelGateway` with `RecordingStore`, `approval_queue`, `AuditLog`, the case file and the manifest check | `d110982` | The screen, the typed read-only tools, the Investigator's tool loop, the Reviewer's figure check, record and replay, the approval queue, the audit log and the data manifest check (`tools.py`, `briefs.py`, `agents.py`, `figures.py`, `gateway.py`, `approval.py`, `replay.py`, `data.py`) |

New in this project: SA-MA's seasonal index, the flag and drift rules with the drift latch, the
demand brief and its five tools, the switch between the local and frontier backends, and the
coordinator.

## Limits and boundaries

- **Advisory only.** The system advises and people decide. It never sets a level by judgement,
  never sends without approval and never sees patient data.
- **A demand level, not pressure.** The level shows demand for the time of year. The capacity behind
  it is a demand percentile, not beds or staff, so the levels and actions are illustrative.
- **Weeks, not days.** The forecasts and levels are weekly; the system does not forecast days.
- **Drift.** When drift fires, the forecasts are marked untrusted until a person approves a latch
  reset.
- **In-sample.** The design was tuned on the same 2015 to 2026 data that scores it, so every figure
  is in-sample. Before any live use the frozen design would run in shadow mode on new releases.
- **The agents.** The design runs locally by default, as `config.json`'s `llm_backend` says. The
  local model verified none of the replay briefs: round 1 finished 3 of the 7
  before its time budget ran out, and round 2 finished all seven with every draft cut at the output
  cap. So the frontier model ran once, as ruled before the runs, and its set is the one approved: it
  verified five, short of the adequacy test's six, and both demand briefs were refused for claims no
  tool result supports. The local model stays an option to retest with its thinking turned off. The notebook's section 9 sets out the limitations in full.
- **AI in the approvals.** An AI independent judge read the seven briefs before I decided. I adopted
  its five edits as my own, with the reset wording corrected. An AI reviewer scored the adequacy
  test.
- **Not for these uses.** Ranking hospitals, justifying cuts or monitoring the 4-hour standard.

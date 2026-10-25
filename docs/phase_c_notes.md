# Notes for Phase C

Left from the Phase B engineering reviews of 25 Oct 2026 for the write-up stage. None changes what the
live run records.

- **P3-10, config.json fields.** The file carries fields beyond the spec's list: `reasoning_effort`,
  `agents`, `coordinator`, `max_tokens`, `api_key_env`, and the `acknowledgements` and `template_order`
  seeds. The README names each field (spec 1f, item 4).
- **P3-11, built beyond the spec, for the method table.** The MHRA device-word code screen; the tool-call
  cap and the run budget, which holds for the whole run, resumes included; the "Written by" line; the
  scripted safeguard demonstrations (`demo.py`); the self-labelling placeholders and tokens, with which
  code writes every figure and what it is, while the words name no number, model, release horizon,
  week, hospital or level (option A, ruled on 25 Oct 2026); the Reviewer's third check, that each
  sentence describes its figures as their labels say; the Reviewer's one retry after a verdict in the
  wrong form or a failed call; the scoring round taken from the records; "not verified" counted by
  cause; and the `adequacy` and `choose` commands.
- **P3-12, the drafted staff actions.** Spec 1b and 2.6 say the LLM drafts "the staff actions and
  notifications". The action text is fixed by code (`coordinator.py`), and the model drafts one
  notification for each action. Say so in the case study.
- **P3-16, tool false positives, no action.** The US spelling in `Decimal.normalize`, and the multi-line
  docstrings the comment audit flags.
- **What the code proves, for the case study.** Each number a reader sees is a tool's value. In the
  agent's text it is written beside its true label: its measure, model, release horizon and week. In
  the fact lines, the back-test error, the track record and the bank holidays, code writes the whole
  sentence from its own tool call. The code does not prove what a sentence says about a figure, such
  as calling an actual a forecast. The Reviewer judges that, and so can the duty manager, who sees
  every label.
- **What the live run freezes.** The recorded requests hash each of these, so changing any after the
  first live run breaks that run's replay with `ReplayMiss`:
  - the class docstrings of `BriefDraft`, `CitedFigure`, `WordingVerdict` and `NotificationDrafts`,
    and every `Field` description in the draft, verdict, notification and tool request schemas;
  - `TOOL_DESCRIPTIONS` and `entry_text`;
  - every problem string in `placeholders.py` and `figures.py`, since each can reach a retry;
  - what code writes for a figure or a token: `label`, `shown`, `render`, `day_text`, `week_text`,
    `release_text` and `deadline_text`;
  - the fact lines, `backtest_line`, `track_line` and `holidays_line`, which `entry_text` shows the
    Investigator and the Reviewer reads in the brief;
  - `brief.text()` and `brief_text`, and the coordinator's `_figure_lines`, `_date_lines`,
    `_action_lines` and action task texts;
  - `backend_options`, the generation settings and the model digest.

  The prompt files are safe to edit for a new label, since each label keeps its own copy; a frontier
  label must keep the local label's copy unchanged.

## Build deviations, third Phase B batch (25 Oct 2026)

Build choices recorded for review, not rulings by Paddy. Where one touches a ruled decision, it says so.

1. **Code writes the brief's fact lines** (spec section 2, item 5, the demand brief schema). The
   hospital's own back-test error, its track record and the bank holidays ahead are facts, not
   explanation. Code calls `get_backtest_error` (the primary model, release horizon 1),
   `get_track_record` and `get_calendar` itself, as of the origin, and writes each as a fixed sentence
   from the tool result:
   - "Back-test error: SA-MA's back-test error at release horizon 1 is 8.1%."
   - "Track record: of 21 flagged outlooks, 13 were borne out; of 208 unflagged outlooks, 49 turned
     busy." With no past flag it reads "no past flag to judge".
   - "Bank holidays ahead: Early May bank holiday (w/e 07 May 2023); coronation of King Charles III
     (w/e 14 May 2023)." or "none in the four weeks ahead".

   The schema still holds: `DemandBrief` keeps its `backtest_error` and `track_record` fields, now the
   tool results code wrote them from, and adds `bank_holidays`. Only who writes them changes. The agent
   writes the explanation: the summary, the expected range, model agreement and the watch points, and
   the cited-figure ledger keeps whatever it still cites. Code's calls take none of the Investigator's
   tool calls, so its cap is left whole.
   - Reason: the agent's sentences around these figures read clunkily, and a fact needs no
     explanation.
   - What falls away: the checks that the back-test error and track record fields each state a cited
     figure from their tool, since code guarantees both lines.
   - Touches D-SAFE-19: its rule that every number in the brief's text maps to a cited figure now
     covers the agent's text. The fact lines' numbers are code's, written from the tool results, as
     the template brief's blanks are (D-ARCH-27).
2. **Only a demand brief must state the primary model's forecast.** This brings the build back to the
   spec: section 1a's replay table and section 2, item 4 mark the surge and latch briefs' forecasts
   untrusted, and the last batch had asked every brief for one. A surge or latch brief may still cite
   a forecast, a range end or the spread, as the template brief prints its forecast table under the
   untrusted drift line. Code then writes "untrusted" in that figure's label, the Investigator is told
   never to give a forecast as what to plan on, and the Reviewer's third check names an untrusted
   forecast offered as something to plan on.
   - No amendment: this implements D-DATA-11 and D-ARCH-28 as ruled.


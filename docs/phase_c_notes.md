# Notes for Phase C

Left from the Phase B engineering reviews of 25 Oct 2026 for the write-up stage. None changes what the
live run records.

- **P3-10, config.json fields.** The file carries fields beyond the spec's list: `reasoning_effort`,
  `num_predict`, `agents`, `coordinator`, `max_tokens`, `api_key_env`, and the `acknowledgements` and `template_order`
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
  agent's text it is written beside its true label: its measure, model and week, or a back-test
  error's release horizon. In the fact lines, the back-test error, the track record and the bank holidays, code writes the whole
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
  - the level's lines, `tools.level_band`, `LEVEL_MEANING` and `LEVEL_FROM`, and the heading and drift
    lines of `brief_text`, which the Reviewer reads in every brief; `entry_text` also shows the
    Investigator the meaning and band lines;
  - the device-word problems in `DEVICE_WORDS`, since each can reach a brief's or a notification's
    retry;
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
   - "Track record: This hospital's past outlook flags were borne out 13 times in 21; its unflagged
     outlooks turned busy 23.6% of the time." With no past flag it reads "This hospital has no past flag
     to judge." It is the template brief's sentence, accepted for both, and both call one function. On
     the national brief, in both, "This hospital" becomes "Scotland", which is no hospital. One word
     departs from the accepted sentence: when one flag was borne out it reads "1 time", not "1 times".
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
3. **Shorter labels, the same facts** (option A, ruled on 25 Oct 2026, unchanged). Within one brief
   every forecast comes from one origin, so a forecast's week names its release horizon. A forecast, a
   range end or the spread is now labelled by its model, measure and week alone: "185 attendances
   (SA-MA forecast for w/e 23 Apr 2023)", "164 attendances (low end of SA-MA's 80% range for w/e 23 Apr
   2023)", "10.7% (spread of the four models' forecasts for w/e 23 Apr 2023)". A back-test error is for
   no one week, so it keeps its release horizon: "18.7% (seasonal naive back-test error, release horizon
   1)". An actual keeps its week: "788 attendances (actual, w/e 14 Jun 2020)". Notifications use the same
   labels. The figure check is unchanged: it still matches each figure's release horizon and week to
   its tool result.
   - Reason: the release horizon beside the week said the same thing twice, and the briefs read
     clunkily.
   - No amendment: code still writes each figure with what it is.
4. **No echoes** (a new placeholder rule, my own design). A figure's label already names its model,
   measure and week, so the Investigator's and the coordinator's prompts say never to restate them
   beside it: no "{PRIMARY} forecasts {F1}" and no "{F1} for {WEEK1}". Code refuses a week token
   straight after a figure whose label names the same week, with at most a comma, a bracket or one
   linking word between them, and names the problem: the week would read twice. A week token the label
   does not name is left alone, so a figure given to the wrong week stays in plain view. The worked
   examples and the natural-brief tests read without echoes, and those tests now hold both demand
   briefs and a staff notification.
   - Scope: the rule covers `{ORIGIN}` and `{LATCHED}` as well as `{WEEK1}` to `{WEEK4}`, since each
     is a week a label can name. A model named again beside its own figure is left to the prompts.
   - No amendment: option A is unchanged; this only refuses words that repeat a label.

## Build deviations, final Phase B batch (25 Oct 2026)

Build choices recorded for review, not rulings by Paddy. Where one touches a ruled decision, it says so.

5. **The level's band line** (spec section 2, item 4; the template brief's field 2). Under the level's
   fixed meaning line, code writes one line saying what the level means from its source, built from
   the rule's constants. The agent's brief, the template brief and the Investigator's screen all print
   it:
   - flag, level 2: "Level 2 from the flag: going by past forecast errors, the rule flagged a week
     ahead that may reach 1.05 times its simulated capacity, a seasonal baseline of past demand."
     "May", since about 28% of flagged weeks turned busy in the steady years.
   - held, level 1: "Level 1, held: the level the flag gave in the week before the alarm, when the rule
     found no week ahead unusually high for the time of year. It says nothing about demand below the
     usual, and is kept until a person approves a latch reset." Level 1 from the flag says the same
     without the held clauses, and held level 2 pairs the flag's clause with the latch reset.
   - surge: "Level 2 from the surge: the latest released week was 1.05 to under 1.10 times simulated
     capacity, a seasonal baseline of past demand, taken at its lowest over the four weeks ahead."
     Levels 1, 3 and 4 name their own band.
   - Reason: the meaning line alone reads as if every level were unusually high. Four of the seven
     replay briefs are level 1, held, on the week demand collapsed, so level 1 says only that nothing
     was found unusually high, never that demand was usual.
   - Touches D-DATA-11: the line states no chance or probability. The brief quotes the track record,
     never the flag's stated chance, which runs about twice what happens. The line's first version
     quoted "at least an even chance" and called level 1 "usual demand"; both went before any recording.
     Capacity is named by its defined term, with the first-use gloss TERMS.md fixes.
6. **No untrusted figure in a staff notification** (spec section 2, item 6; D-SAFE-19, as amended). In a
   surge or latch brief the coordinator is offered no forecast, range end or spread. The notification
   check refuses one and names why in the retry: "{F2} is untrusted while the drift latch is set; a
   notification never states an untrusted figure". The coordinator's prompt says: "In a surge or latch
   brief the forecasts are untrusted: state none, and never give one as a reason to act." The MHRA
   device-word screen also runs on each notification as code writes it, as it runs on a brief.
   - Reason: no Reviewer reads a notification, so a sentence giving an untrusted forecast as the reason
     to act would otherwise reach the outbox.
   - No amendment: this carries D-DATA-11 ("surge: forecasts untrusted") and D-ARCH-28 into the
     notifications.

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
  - `backend_options` and the model digest.

  The prompt files are safe to edit for a new label, since each label keeps its own copy; a frontier
  label must keep the local label's copy unchanged. The generation settings in `config.json` are safe
  to change for a new label too: a replay of a label's set takes them from its own recordings, while
  a resume, which carries on live, holds them to `config.json`'s.

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

## Build deviations, frontier readiness (26 Oct 2026)

The main session's calls on the frontier backend before its first live run, read from the installed
langchain-anthropic 1.7.6 and anthropic 1.17.0 and checked on requests built offline. The main session
logs each in the decision log.

7. **No temperature for the frontier model.** `config.json` sets the frontier `temperature` to null, so
   none is sent. langchain-anthropic refuses any value but the default for `claude-sonnet-5-5` before a
   request leaves, so temperature 0 would have failed every frontier call and spent the one frontier
   run on errors.
   - Reason: the model takes only its default. A run's reproducibility comes from its recordings, which
     the notebook replays, not from the temperature.
   - The local backend keeps temperature 0.
8. **A larger output cap, and medium effort.** The frontier `max_tokens` rises from 4,096 to 16,000,
   and a new `effort` field sets "medium". `claude-sonnet-5-5` thinks adaptively, which cannot be turned
   off, and its thinking counts against `max_tokens`, as the local model's did when round 2's drafts were
   cut at 8,192 tokens.
   - How effort is sent: as `output_config.effort`, set on the chat model, which langchain-anthropic
     merges with a structured call's `output_config.format`. Its `reasoning_effort` field sends the same
     effort but also sets the thinking display to summarized, which no one asked for, so it is not used.
   - Cost: only the tokens a reply generates are billed, never the cap.
9. **The frontier's own call limit, 420 s.** The agents' 240 s limit would end any reply generated more
   slowly than about 67 tokens a second (16,000 / 240). Nothing has measured the frontier model's speed
   on this account yet. At an assumed floor of 40 tokens a second, 16,000 tokens take 400 s, and 20 s
   more covers the request and the first token. The client's own timeout is 5 s longer.
   - Reason: a reply that runs to the cap should end as `stop_reason` max_tokens, which the record names
     as a cut and the retry answers, not as a time-out, which reads as "the Investigator could not run".
     Effort changes how many tokens a reply uses, not how fast they come.
   - The local backend keeps 240 s, and the run's budget still bounds every call.
10. **The frontier draft call defines the tool loop's tools.** The Investigator's draft call carries the
    loop's tool calls and results in its history but asked for no tools, and the Claude API may refuse a
    request that holds tool blocks and defines no tools. On the frontier backend the draft call now
    defines the same five tools with `tool_choice` none, beside the `json_schema` output format, so the
    reply is the brief and never a call. Its request record lists the tools and `tool_choice` "none".
    - Why not flatten the history: the anthropic SDK types `tool_choice` none, langchain-anthropic
      passes it through, and its only limit for `claude-sonnet-5-5` is on the forced choices, "any" and
      "tool". Nothing in either refuses `tool_choice` none beside an output format. The live API's
      acceptance is shown only by a call, so the smoke test's draft shape runs before the frontier run.
    - The local backend sends and records exactly what it did: rounds 1 and 2 replay with every
      request matched and their outcomes unchanged.

`effort` and `time_limit_s` join the frontier fields that P3-10 lists.

## Build deviations, the replay cells (26 Oct 2026)

Build choices from running the notebook's replay cells against the live recordings, recorded for
review, not rulings by Paddy. Where one touches a ruled decision, it says so.

11. **A draft refused inside the model call is named the code check.** Label round1's client
    checked the typed reply against `BriefDraft` inside the call, so a draft the text rules refused
    was recorded as a model error, and `BriefOutcome.cause` named it "the Investigator could not
    run". A recorded `ValidationError` for `BriefDraft` is now named "the code check", the check
    that refused it; any other model error keeps its old name. The client reads the reply in code,
    after the call, so only round1's recordings have this shape.
    - Reason: the Investigator did run, and both drafts in each of round1's three completed briefs
      were refused by the rules on the text. The replay showed a cause that was not true.
    - What does not change: round1's adequacy record keeps the wording it was written with, and the
      notebook explains the two beside each other.
    - Touches D-EVAL-20: G4's count by cause for round1 reads 3 by the code check, not 3 by a
      model that could not run.
12. **Each attempt names what refused it.** `Attempt.refused_by` gives one attempt's cause in the
    words G4 counts causes in, or none when it passed both checks, and `BriefOutcome.cause` takes
    the last attempt's. The notebook shows every attempt's, so a brief refused first by the code
    check and then by the wording check says both.
    - No amendment: the cause of a brief is unchanged apart from item 11.
13. **Which retries went out blind.** `replay.blind_retries` reads a label's recordings and says, for
    each run with a retry, whether the retry's first request has the same hash as the first
    attempt's. A blind retry carries none of the problems the first draft was refused for.
    - Reason: the notebook states that round1's retries never saw their problems, and that neither
      round 2 set's did, so the claim needs an output.
    - No amendment: it reads the recordings and changes nothing.
14. **G4, G5 and G6 as section 1a words them.** `approval.g4_verdict` adds the planted figure,
    caught at that figure, to the queue's G4 counts, so G4 is not met when the plant was never
    shown caught. `approval.g5_verdict` holds the level to the rule's over the briefs written, and
    gives no verdict when none was written. `approval.g6_verdict` needs all but one of the built
    briefs approved without a factual edit and Reader B agreeing on at least three of the four; a
    short count fails it whatever Reader B decides, and otherwise it waits on the reading.
    - Reading: an approval with an edit that is not factual counts as approved without a factual
      edit, as the goal's words read.
    - No amendment: this implements D-EVAL-20 as ruled.
15. **A brief with no staffing action says so.** Level 1 sets no staffing action, and the
    coordinator's summary for such a brief now reads "Level 1 sets no staffing action, so nothing
    reaches the outbox." It printed the outbox label for a brief that wrote nothing.
    - No amendment: the actions and the outbox are unchanged.

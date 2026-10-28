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

## Build deviations, the evaluation and the figures (26 Oct 2026)

Build choices recorded for review, not rulings by Paddy. Where one touches a ruled decision, it says so.

16. **Reader B's decisions and the raters' marks are typed into two sheets.** The returned forms are
    typed into `approvals/reader_b_<backend>_<label>.csv` (`brief_id`, `action`, the six criteria,
    `factual_edit`, `note`) and `approvals/template_ratings_<backend>_<label>.csv` (`rater`, `week`,
    `text`, the six criteria, `factual_error`). `approval.read_reader_b` and
    `approval.reader_b_agreement` give G6's second half: the same decision on each of the four briefs
    the rule picks, refusing a brief outside the four or one decided twice. `template.read_ratings`
    maps each rater's Text A and Text B through the seeded hidden order to the agent's and the
    template's text, and keeps only a factual error in the agent's text, as option A reads it.
    - Reason: nothing read either form, so G6 could not count Reader B's agreement and Figure 7 had
      no data.
    - No amendment: this implements D-EVAL-19, D-EVAL-20 and D-ARCH-27 as ruled. Each sheet needs a
      `!` line in `.gitignore` and an `ALLOWLIST.txt` line when it is added.
17. **Tokens are counted on the calls that answered.** A failed call's record holds no token counts,
    so the notebook's table of calls, tokens and model time labels its token columns "answered
    calls", while model time covers every call.
    - No amendment: the recordings are unchanged.
18. **The README asks for Python 3.12 or higher.** Spec 1f, item 3 says 3.9 or higher, as the
    Environment Setup tab asks. The pinned packages in `requirements.txt` need 3.12: numpy,
    contourpy and networkx exclude 3.11. Python 3.12 meets the tab's 3.9 or higher.
19. **Figure 4 is exported as `figures/fig4_month_chart.png`**, the name spec 1f gives it. The
    notebook wrote it as `figures/month_attendances_and_4_hours.png` before, and that file stays
    tracked, unchanged, until Paddy rules on deleting it.
20. **The figure fixes.**
    - Figure 5's G4 row says what section 1a asks: every approved brief passes, no brief that was not
      verified is approved, and the plant is caught; its result counts the briefs not verified and
      how many were approved, from `g4_verdict`.
    - Figure 5's G6 row says Reader B's reading is pending until Reader B's sheet exists.
    - Figures 2 and 6 and section 8 say "the mean steady year gave notice of 57.0 of 142.5 busy
      hospital-weeks (40.0%)". The notebook computes the wording for Figure 6 and checks that Figure
      2's Mermaid source states it word for word.
    - Figure 3 carries a caption in the notebook and the README: its dates illustrate the release
      timing for one replay week, and that week's brief was rejected.

## Build deviations, the clean room and the docstrings (26 Oct 2026)

21. **`requirements.txt` holds pytest.** It is frozen from the clean room's environment after the
    notebook's run and the tests, so it holds pytest, which the shipped tests need, as well as every
    package the notebook and the modules import. The README no longer installs pytest separately.
22. **Every test helper, fixture and test-class method has a docstring** (P3-9). Every function in
    the package already had one. The test functions themselves keep their descriptive names in place
    of a docstring.

## The fact-check fix batch (26 Oct 2026)

Corrections from the stage 5.1 fact-check, applied to the notebook's text, the README and the case
study. Two change what a code cell prints; the rest change words only.

23. **September's borne-out share is one count.** The notebook printed 40.5% beside a by-month table
    that gives 40.4% for the same 89 flagged outlooks: the line came from the units module, whose
    shares are rounded to two places before the cell rounds them to one. The line now reads the same
    eligible steady-year outlooks as the table, rounded once: 40.4% borne out against 14.9% of
    unflagged September outlooks.
24. **No probe, decision or build-spec reference ships.** The decision log, the probes and the build
    spec stay private, so their ids and section numbers are gone from the notebook, the README and the
    case study, and the repeated-flags line says "the rule stated before it was tested". Where an AI
    assistant session ran or scored something, the text says so.
25. **The GRU's comparison is given in both scopes.** Outside each series' drift episodes no release
    horizon favoured the GRU and 16 of 20 favoured the primary; outside March 2020 to March 2022 one
    did, the Queen Elizabeth at release horizon 4, and 7 favoured the primary.
26. **The notebook numbers all seven figures.** Figures 1 and 2 are shown in section 1 and Figures 4
    to 7 carry captions, so each case study caption can give the figure's notebook number; the case
    study numbers its own figures in the order they first appear.
27. **The AI in the approvals is disclosed** in the case study and the README: an AI independent
    judge read the seven briefs before the approver decided, its five edits were adopted with the
    reset wording corrected, and an AI reviewer scored the adequacy test.

## Paddy's comments on the case study (27 Oct 2026)

28. **The drift latch is defined in plain words at first use** in the case study, the README and the
    notebook: an alarm that stays on until someone resets it, the forecasts untrusted while it is set,
    and only a person able to reset it. The term stays, since the code, the recorded briefs and the
    notebook's outputs use it.
29. **The system's status is stated: additional information only.** At this stage it gives the duty
    manager additional information beside their existing process, replaces no current process and
    sets no staffing on its own; becoming a primary operational tool needs shadow mode, a pilot and
    tuning over time. The case study's risks, boundaries and next steps are read in that light.
30. **The caution is rewritten:** the money saving mainly the agency premium, the wider value in links
    3 and 4 of the value chain, sourced and hypothesised, and figures on lives or harm the stakes,
    never claims.
31. **The runtime says what happened.** The design runs locally by default, as `config.json` sets.
    The local model wrote no adequate brief in either round, so the frontier model ran once, as ruled
    before the runs; its set, 5 of 7 verified, short of the adequacy test's 6, is the one the approver
    chose. The local model stays an option to retest with its thinking turned off. `config.json` is
    unchanged.
32. **Each goal is named at its first use in a case study section**, and the approver is referred to
    by role.
33. **The old copy of Figure 4 is deleted.** `figures/month_attendances_and_4_hours.png` was
    identical to `fig4_month_chart.png`, and a search found nothing that referenced it. Paddy agreed
    to the deletion on 27 Oct 2026, and it is off `ALLOWLIST.txt`.

## The frontier default and every failure qualified (27 Oct 2026)

34. **`config.json` ships with `llm_backend` set to `frontier`.** Paddy ruled on 27 Oct 2026: the
    frontier set is the one approved, and the recordings make the notebook reproducible on either
    setting. Setting `llm_backend` to `local` selects the local model, and the README says what each
    needs for a live run: Ollama with the model pulled at its digest, or the key in the git-ignored
    `.env`. The frontier set did not pass the adequacy test: it verified 5 of 7, short of 6.
    - Amends item 31: the design no longer runs locally by default, and `config.json` changed.
    - The `Settings` model's own default stays `local`, so a file that names no backend runs the
      local model, which needs no key.
    - The tests that drive the local path with a stand-in model now pin `local` through
      `tests/conftest.py`'s `local_settings` and `local_config`; the shipped-config test checks
      `frontier`.
    - The notebook's backend cell, `8e59b9a7`, prints the configured backend, then each backend's
      settings. A fresh kernel ran every code cell in order, and only that cell's output changed.
    - A fresh clone of `dev` with this change applied, no `.env`, no key in the environment and no
      network ran the notebook end to end; its outputs match the working notebook's, and all 1,019
      tests passed there.
35. **Every failure is qualified.** Paddy ruled on 27 Oct 2026, with no follow-up run, so the frozen
    result stands. Each "not met", "narrowly missed", "not verified" or "verified none" in the case
    study, the README and the notebook's markdown carries its cause as the outputs show it, what the
    safeguard did where one acted, and the future-work step:
    - the demand briefs: claims no tool result supports, such as recent weeks rising or the forecasts
      fitting; the checks refused them, so neither could be approved; explaining a demand week only
      from what the tools return comes before shadow mode;
    - local round 1: the retries went out blind, a bug in the client that round 2 fixed, and the time
      budget stopped the run after 3 of 7;
    - local round 2: every draft reached the 8,192-token output cap, which counts the model's
      thinking; thinking turned off is untried;
    - G6: the two short are the refused demand briefs, and none of the five edits was factual;
    - G7: the three growth years, on a reading the design probes did not test; shadow mode tests it
      before any threshold moves;
    - the frontier set: 5 of 7, short of 6, because the checks refused both demand briefs.

## Reader B's return and the template comparison (27 Oct 2026)

36. **Both returned forms are typed into their sheets.** Paddy ruled on 27 Oct 2026 that Reader B's
    return counts as a human second reader's: Reader B, a person, read with an AI assistant. The
    approver's pair ratings carry the same description, and they are not blind. No name is written.
    - `approvals/reader_b_frontier_round2.csv`: the four briefs by the pack's headings, edit, edit,
      edit and reject, the criteria as ticked, and no factual edit, since each edit's note says no
      figure, date, hospital or level changes.
    - `approvals/template_ratings_frontier_round2.csv`: both raters, both weeks, both texts, the
      criteria and the factual error as ticked. The sheet labels the approver `approver`, the label
      the code reads.
    - Each note is kept word for word in a `note` column, with one change: each spaced em dash is
      written as ": ", so the dash gate holds.
    - Each sheet has its `!` line in `.gitignore` and its line in `ALLOWLIST.txt`.
37. **The sheets give G6 and the comparison.** Reader B made the approver's decision on all four
    briefs, so G6's second half is met; G6 stays not met on its first half, 5 of 7 against 6. By
    option A both raters found the agent's text added value in the national latch week and not in
    the demand week, whose brief the checks had refused. Figure 5's G6 row reads Reader B's count
    from the sheet.
38. **Figure 7 is drawn.** `figures/fig7_template_comparison.png` shows each rater's marks on both
    pairs, the template beside the agent's text, each text's factual error and option A's verdict.
    `PairRating` now keeps the template's factual error for the figure; option A still counts only
    the agent's. The case study shows it in section 13, and section 11 names the result.
39. **The tests that decide after a live run use a time after any run.** Four tests decided at
    09:30 UTC on 27 Oct 2026, a fixed time, after a live run that starts at the clock's now. From
    that moment the queue refused their decisions as made before the run began, which is the rule
    working. They now decide at `AFTER_ANY_RUN` in `tests/conftest.py`; the rule is unchanged.

## The README's checks and the figures in print (27 Oct 2026)

40. **The README says how the work was checked and why it is a pilot.** Paddy asked on 27 Oct 2026
    for a short section of labelled highlights: the data's hash and anomalies, the code figure check
    and the planted figure, the Reviewer and "not verified", the adequacy test stated first with
    both backends reported, the AI independent judge and the approver, Reader B, the fact-check and
    the clean room run twice. It then says the system stays a pilot by choice: shadow mode, a pilot
    with managers who did not build it and tuning over time, as the case study's section 14 sets
    out. It holds no review rounds, finding counts or dates.
41. **Section 14 follows the path to an operational tool, in Paddy's order.** Now additional
    information by choice, then shadow mode, then a pilot with managers who did not build it, then
    tuning over time, then a primary tool. Learning what planners use sits inside the pilot, as part
    of the managers' feedback, with its routing unchanged; the admissions and occupancy data widen the
    system once the base is proven. Every item stays; only the order and the linking sentences
    changed. The README's pilot paragraph uses the same order. The paper's figure of that path ships as
    `diagram/path_to_operational_tool.mmd` and `figures/fig8_pilot_path.png`.
42. **Figures 1, 2, 3 and 5 read in print.** At a 16 cm text column their smallest text printed at
    about 5 to 6 pt; each is redrawn so that it prints at 8 pt or more, with the same file names.
    - Figure 1 is portrait: the code lane is drawn in two parts, before and after the person
      decides, each arrow's label is short and the interaction table says in full what passes, so
      the sixteen arrows and the table stay in step. The forecasts box writes "GRU (gated recurrent
      unit)" in full. At 23 cm tall its 17 px text prints at 8.8 pt.
    - Figures 2 and 3 sit on two rows: 8.3 pt and 9.5 pt at 16 cm. Figure 2's link 1 keeps the
      notice wording the notebook checks.
    - Figure 5 is a narrower table with larger text: 8.8 pt at 16 cm. Its code cell is the only one
      whose output changed, and only in the figure.
    - Figure 7 was drawn at that size from the start: 8.2 pt at 16 cm.
43. **Figures 4 and 6 read in print too.** Each is narrower, with larger text, and keeps its file
    name: at a 16 cm column Figure 4's smallest text prints at 9.2 pt and Figure 6's at 9.0 pt.
    Figure 6 keeps its footnote, "In-sample" and the steady-year definition among it, in the figure.
    In a fresh kernel only those two images changed.
44. **Figure 1 fits the paper's figure box.** The APA kit caps a figure at 6.5 inches wide and 8.2
    inches high, so the portrait Figure 1 was set at about 13.5 cm and printed at about 6.8 pt. It is
    redrawn, same file name, as two columns: the code lane's first part on the left, and the agents,
    the person and the code lane's second part on the right. Each arrow carries only its number,
    and the interaction table says what passes; arrow 8 joins the two columns. The sixteen arrows
    stay in step with the table, and the "not verified, do not act" route stays dashed red. Its
    height is 1.10 times its width, and at 6.5 inches its 17 px text prints at 8.6 pt.

## The stage 5 fix batch (27 Oct 2026)

45. **The template rule set before the ratings now applies.** Paddy ruled on 27 Oct 2026 to apply it:
    the comparison failed in the demand week, so the template writes a brief's explanation by
    default, and the agent only in drift, surge or model-disagreement weeks. `config.json`'s new
    `explanation` setting ships as `template_by_default`, and `agent` switches it back.
    `template.explanation_writer` gives the template to a flag week and the agent to a latched week;
    `template.weekly_brief` fills the template with no model call. The design has no measure of
    model disagreement, so no week is kept for the agent on that ground, and none is invented. The
    replay set ran the agent on every brief and replays as it ran; a new notebook cell shows what the
    rule does for the two demand weeks.
46. **The Reviewer's verdict fails closed when it contradicts itself.** A pass that names problems,
    a pass written as a word, or a verdict quoted inside prose is a slip: asked once more, then not
    verified as the Reviewer's error. The verdict must be the whole reply. None of the recorded
    verdicts does any of these, so no recorded result changes.
47. **The device-word screen catches every form of a listed word**, such as "predictive",
    "unpredictable" and "risks of". No recorded text holds one.
48. **Code marks an edit factual when it swaps or moves a figure.** Field by field and in order,
    each placeholder is compared by the figure it resolves to. The five recorded edits stay
    non-factual, so G6 is unchanged.
49. **A resume never gains a fresh budget.** Ctrl-C now leaves its stop and the time spent, and a
    start with nothing after it, as when the process is killed, is charged the whole time since it
    began. `live choose` without `--set` is refused, a budget stop after a completed step no longer
    raises, and the edits and notifications replay with their recorded generation settings.
50. **Every shipped recording is pinned by SHA-256.** `recordings_manifest.tsv` lists each file under
    `recordings/`, and a replay gateway refuses a listed file that no longer matches, so a changed
    reply stops the notebook as a changed request does. No recorded file changed.
51. **The text follows the reviews.** "Advisory" is gone as a name for the status; the current
    system is the pilot build, and the later step a pilot with managers who did not build it. The
    demand-week briefs' cause now says what the outputs show: a trend cited from one actual, and
    code's own line that the forecasts fit recent weeks. Every limitation gives what held it and
    the next step, and five are added from the reviews. The human latch reset is the design's, and
    this build simulates it. Figure 7's note says neither pair was blind to Reader B. The notebook
    shows recorded notes with the approver by role and no private path. The code's docstrings
    say what each decision says, in place of its id.
52. **Not changed.** The decision CSV and every file under `recordings/` stay as recorded.
53. **The drift line is versioned, and the shipped version uses the raters' wording.** Ruled on 27
    Oct 2026. Where no drift alarm has fired, the rated template and the Investigator's prompt said
    "Drift: none. The forecasts fit recent weeks.", which both raters marked a factual error.
    - `config.json`'s `template_version` ships as 2: the template brief live briefs get says "No
      drift alarm is recorded; this alone does not establish forecast fit.", the raters' own
      wording. Version 1 is the template as rated, and the comparison cells keep it, so Figure 7 and
      the ratings stay true to the rated texts.
    - `agents.no_drift_line` ships as 2, so new runs give the Investigator the same wording. A
      recorded label replays with the line its recordings hold, so every request hash is unchanged.
    - The template rule's model-disagreement ground has no threshold set before the ratings, so no
      week is kept for the agent on that ground; defining one is a next step. The README, case study
      and notebook say so in the same words.

## The final fix round (27 Oct 2026)

54. **The template rule runs on the live path.** `replay.run_set`, which `live briefs` drives, now
    gives a flag week's brief to the template at the label's template version, with no model call,
    and a latched week's to the agent; the designed failure still goes to the agent. A new run's
    first start records its explanation setting and template version, and a label recorded before
    the setting existed replays with the agent when its recordings hold a flag week's calls, so the
    recorded runs replay unchanged. A template brief goes to the run's record and the adequacy form,
    unscored; the approval queue then took the agent's briefs only, and item 56 now queues the
    template's too. The replay set's tests pin the agent, as the recorded runs ran, and a test drives
    `live briefs` under the rule and checks the routing.
55. **The text follows the re-check and the grader's notes.** Only Ninewells' brief claimed a rising
    trend; the order was hidden from Reader B, and the approver knew it; the notebook prints the
    approver by role; limitation 15 states the masked weeks the right way round; the README's first
    step covers a zip; and the case study and notebook say "my design" where the choice is mine.
    Every line that said the template now writes a flag week says it does so in new runs, and the
    notebook's template cell names the brief a new run writes, not one the duty manager gets.

## Paddy's read of paper v3 (27 Oct 2026)

56. **Template briefs are queued for approval.** Every brief, the template's or the agent's, reaches
    the duty manager to approve, edit or reject under the same rules.
    - Before a template brief is queued, code checks every figure it prints against the tool call it
      came from, by the same figure rule as the agent's briefs, and the level against the rule's.
      G4 checks an approved one again.
    - An edit of a template brief is written in the agent's form, citing the template's tool calls,
      and is checked as any edit is. With no draft to compare, code marks it factual.
    - Only an approved brief sets actions. The coordinator drafts its notifications from the
      template's own figures. The template names no primary model, so neither may a notification:
      `{PRIMARY}` is refused there and not offered.
    - The template brief's model moved from `template.py` to `briefs.py`, beside the agent's, so the
      queue can hold either without an import cycle; `template.py` keeps its old names.
    - The recorded labels hold no template brief, so they replay unchanged. Tests drive `live briefs`
      with no network, show both flag weeks' template briefs in the released queue, and show that
      approving one writes its notifications while rejecting the other writes none.
57. **Examples ship in the repository.** `examples/` holds four, rendered from the recorded set and
    the code with no model call by `python -m ae_escalation.examples`. A test renders them again and
    checks each against the shipped file. Figure 9, `figures/fig9_sample_brief.png`, is the first
    example's approved brief, drawn at 16.5 cm with 8.5 pt text; it fits whole, so it needs no
    "continues" mark.
58. **Figure 2's link 2 names the staff bank.** It reads "Planned cover from the staff bank, the
    board's own pool of flexible staff, instead of late agency cover", in the diagram and the case
    study's table. Redrawn, its smallest text prints at 8.3 pt at 16 cm, and the notebook's Figure 2
    wording check still matches.
59. **G6 in plain words.** Figure 5's G6 row and every G6 statement say what counts: 6 of the 7
    briefs approved with no factual change, and Reader B making the approver's decision on at
    least 3 of the 4 they read. The result, 5 of 7 with the two demand-week briefs refused and
    rejected, and Reader B agreeing on 4 of 4, comes from the outputs; `approval.g6_short` words
    the shortfall from the queue.
60. **The reviewers' AI tools are not named.** The README, the case study and the notebook no longer
    say that Reader B or the approver used an AI assistant, and Figure 7's footnote is redrawn
    without it. One line closes the notebook's limitations: both raters used AI tools to help draft
    their notes, and the decisions were theirs. The runs and scores are mine in the first person;
    the AI reviewer that scored the adequacy test and the AI independent judge stay, as designed
    steps. Round 1's blind retries are a fault in my code that calls the model, fixed before round 2.
61. **The adequacy threshold is stated as a limitation.** The adequacy test was written for a set in
    which the agent writes every brief, and under the template rule a new run's agent writes fewer,
    so the 6 of 7 threshold can no longer send a local set to approval. No code changed: the test
    was stated before the runs. Limitation 18, in the notebook and the case study, says the
    threshold needs restating, for example as all but one of the agent's briefs, before the next
    live run. The case study now counts eighteen limitations.
62. **The figures are mapped, and the sample brief is named as the paper numbers it.** The README
    has a figure map giving each file's number in the paper, the notebook and the case study, with
    the paper's order checked against the APA kit's figure list. `examples/README.md`, written by
    the examples generator, names `figures/fig9_sample_brief.png` as Figure 5 of the paper. The
    notebook's sentence on numbering now points to the map, since the paper numbers its figures in
    its own order. The README says the decision notes in `approvals/` are the approver's recorded
    notes, kept as written, and that their references to "the main session" and to `reviews/` paths
    point to the author's private working records. No notebook output changed.
63. **Every brief opens with what a duty manager needs, and Figure 5 is the current brief.** Ruled
    on 28 Oct 2026. Figure 5 showed the latched surge brief of w/e 06 Oct 2019, the fallback to
    released actuals rather than a normal week, and both layouts led with evidence and ended with
    one generic watch line. The reader is a duty manager, not a statistician.
    - Template version 3, the shipped default, is the manager's layout. It opens "At a glance": the
      level, why, the attendances to expect, how far the four methods' central forecasts differ,
      how accurate they have been for the first of the four weeks, the past flags here and whether
      a warning is on, in plain words. "What to do, if you approve" follows, with the staffing
      actions code sets for the level, each with its owner and its task dated to the four weeks
      ahead, the same text and owner the coordinator's plan uses. The detail, the forecast and
      error tables, comes last. The top two blocks keep off "release horizon", "simulated
      capacity", "MAPE", "latch", "drift" and "back-test". The watch line is gone.
    - The high-week mark is simulated capacity in plain words: the level 9 weeks in 10 stayed
      under at this time of year over the last three years, since capacity is the 90th percentile
      of those weeks, not a middle value. "Turned out high" is the code's busy, a week 5% or more
      above the mark. Where no drift alarm has fired, the line says only that no warning is on.
    - The code check holds every line version 3 prints to the line its own tool calls give, so the
      worked-out figures, the expected range rounded to 10 and the methods' spread, and each
      action's dates are covered; a planted wrong date in an action line fails it. Versions 1 and
      2 are unchanged, byte for byte, and checked as before.
    - The approval queue's display and sheet show an agent's brief in the same layout, its top two
      blocks written by code from the brief's facts, then the agent's points and its explanation
      as written. The rated layout stays for the raters' view, Reader B's pack, the template
      comparison, the approver's 26 Oct view in the examples, and the Reviewer's and the
      coordinator's prompts, so every recording replays by the same request hash and
      `recordings_manifest.tsv` is unchanged. The agent's watch points stay as recorded.
    - The manager's layout came after the ratings: the raters, Reader B and the approver read the
      rated layout. Testing the new one with managers is a pilot step, and so is an Investigator
      prompt that asks for watch points in plainer words, recorded afresh.
    - Figure 5, `figures/fig9_sample_brief.png`, now draws the current brief: the version 3
      template brief the shipped code queues for the Royal Infirmary of Edinburgh's flag week, w/e
      23 Aug 2026, the latest unlatched flag in the data, with 98 figures and every line checked.
      `examples/current_brief_edinburgh.md` holds it with what followed, worked out from the
      frame's busy1 to busy4: w/e 20 Sep 2026 turned busy and the other three weeks did not. The
      figure draws every line, its tables whole, at 8 pt and 16.5 cm wide, 20.4 cm tall.

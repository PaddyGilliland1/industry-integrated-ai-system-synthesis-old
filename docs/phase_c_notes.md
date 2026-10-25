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
- **What the code proves, for the case study.** Each number a reader sees is a tool's value, written
  beside its true label: its measure, model, release horizon and week. The code does not prove what a
  sentence says about a figure, such as calling an actual a forecast. The Reviewer judges that, and so
  can the duty manager, who sees every label.
- **What the live run freezes.** The recorded requests hash each of these, so changing any after the
  first live run breaks that run's replay with `ReplayMiss`:
  - the class docstrings of `BriefDraft`, `CitedFigure`, `WordingVerdict` and `NotificationDrafts`,
    and every `Field` description in the draft, verdict, notification and tool request schemas;
  - `TOOL_DESCRIPTIONS` and `entry_text`;
  - every problem string in `placeholders.py` and `figures.py`, since each can reach a retry;
  - what code writes for a figure or a token: `label`, `shown`, `render`, `day_text`, `week_text`,
    `release_text` and `deadline_text`;
  - `brief.text()` and `brief_text`, and the coordinator's `_figure_lines`, `_date_lines`,
    `_action_lines` and action task texts;
  - `backend_options`, the generation settings and the model digest.

  The prompt files are safe to edit for a new label, since each label keeps its own copy; a frontier
  label must keep the local label's copy unchanged.

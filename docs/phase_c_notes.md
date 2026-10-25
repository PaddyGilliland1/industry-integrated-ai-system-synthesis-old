# Notes for Phase C

Left from the Phase B engineering review of 25 Oct 2026 for the write-up stage. None changes what the
live run records.

- **P3-9, docstrings.** Add a docstring to each public function that lacks one. Private helpers,
  properties and nested functions need none.
- **P3-10, config.json fields.** The file carries fields beyond the spec's list: `reasoning_effort`,
  `agents`, `coordinator`, `max_tokens`, `api_key_env`, and the `acknowledgements` and `template_order`
  seeds. The README names each field (spec 1f, item 4).
- **P3-11, built beyond the spec, for the method table.** The MHRA device-word code screen; the tool-call
  cap and the run budget, with the resume after a budget stop; the "Written by" line; the scripted
  safeguard demonstrations (`demo.py`); the placeholder rules, which bind each figure to the model,
  release horizon, week and unit its clause names (option A, ruled on 25 Oct 2026); the Reviewer's one
  retry after a verdict in the wrong form; and the `adequacy` and `choose` commands.
- **P3-12, the drafted staff actions.** Spec 1b and 2.6 say the LLM drafts "the staff actions and
  notifications". The action text is fixed by code (`coordinator.py`), and the model drafts one
  notification for each action. Say so in the case study.
- **P3-16, tool false positives, no action.** The US spelling in `Decimal.normalize`, and the multi-line
  docstrings the comment audit flags.

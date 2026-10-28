# Examples

Each file is rendered from the recorded frontier set, round2, the set the approver chose, and the code, with no model call. `python -m ae_escalation.examples` writes them again, and a test checks that they match. Figure 5 of the paper, `figures/fig9_sample_brief.png`, is the current brief, the first file's. Briefs open in the manager's layout, which came after the ratings: the raters and the approver read the rated layout, and testing the new one is a pilot step.

- `current_brief_edinburgh.md`: the current brief, the version 3 template brief the shipped code queues for the Royal Infirmary of Edinburgh's flag week, w/e 23 Aug 2026, the latest unlatched flag in the data, with what followed.
- `surge_brief_edinburgh.md`: the Royal Infirmary of Edinburgh's surge brief, w/e 06 Oct 2019, as the approver saw it, then as approved with the edit, then in the shipped layout.
- `template_brief_ninewells.md`: the version 3 template brief a new run writes for Ninewells Hospital's demand week, w/e 13 Jun 2021, as queued for approval.
- `outbox_edinburgh.md`: Edinburgh's staff notifications and escalation, from the outbox, never sent.
- `not_verified_brief_ninewells.md`: Ninewells Hospital's demand brief, marked "not verified, do not act", as the manager saw it.

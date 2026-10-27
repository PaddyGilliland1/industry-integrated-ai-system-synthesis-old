# The template brief a new run writes for Ninewells Hospital, w/e 13 Jun 2021

Under config.json's rule a flag week's brief is the template brief, filled by code from the tools as of the origin, and it goes to the approval queue like any brief. In the recorded run the agent wrote this week's brief, and the checks refused it (`not_verified_brief_ninewells.md`). Rendered from the recorded frontier set, round2, the set the approver chose, and the code, with no model call: `python -m ae_escalation.examples`.

| | |
|---|---|
| Brief | 20210613-T101H |
| Hospital | Ninewells Hospital |
| Origin, the latest week released | w/e 13 Jun 2021 |
| Released | Tue 22 Jun 2021 |
| Kind and demand level | demand, level 2 |
| Written by | the template brief, version 2, filled by code with no model call |
| Status | verified |

The code check: 96 figures checked against the tool calls they came from, none wrong; the level is the rule's. State in the queue: awaiting decision.

## As queued

The brief as the approval queue's sheet shows it.

```text
Ninewells Hospital, week ending 13 Jun 2021, released Tue 22 Jun 2021

Demand level 2, from the flag.
The demand level shows demand unusually high for the time of year. It is not pressure, need or priority.
Level 2 from the flag: going by past forecast errors, the rule flagged a week ahead that may reach 1.05 times its simulated capacity, a seasonal baseline of past demand.

Forecasts, with their 80% and 95% ranges:
| Model | Release horizon 1, w/e 27 Jun 2021 | Release horizon 2, w/e 04 Jul 2021 | Release horizon 3, w/e 11 Jul 2021 | Release horizon 4, w/e 18 Jul 2021 |
|---|---|---|---|---|
| seasonal naive | 835 (80%: 549 to 1,123; 95%: 409 to 1,532) | 810 (80%: 532 to 1,089; 95%: 397 to 1,487) | 948 (80%: 623 to 1,275; 95%: 465 to 1,740) | 1,059 (80%: 696 to 1,424; 95%: 519 to 1,944) |
| 4-week moving average | 1,114 (80%: 970 to 1,297; 95%: 717 to 1,442) | 1,114 (80%: 958 to 1,343; 95%: 664 to 1,510) | 1,114 (80%: 943 to 1,400; 95%: 580 to 1,521) | 1,114 (80%: 910 to 1,423; 95%: 547 to 1,558) |
| linear | 898 (80%: 666 to 1,148; 95%: 464 to 1,245) | 883 (80%: 652 to 1,144; 95%: 438 to 1,253) | 871 (80%: 635 to 1,131; 95%: 419 to 1,246) | 866 (80%: 630 to 1,136; 95%: 412 to 1,255) |
| SA-MA | 1,120 (80%: 982 to 1,291; 95%: 714 to 1,454) | 1,085 (80%: 964 to 1,296; 95%: 636 to 1,483) | 1,057 (80%: 912 to 1,339; 95%: 535 to 1,432) | 1,086 (80%: 918 to 1,399; 95%: 516 to 1,504) |

Back-test error (MAPE) of each model at each release horizon, known at the origin:
| Model | Release horizon 1 | Release horizon 2 | Release horizon 3 | Release horizon 4 |
|---|---|---|---|---|
| seasonal naive | 24.5% | 24.5% | 24.5% | 24.5% |
| 4-week moving average | 11.9% | 13.8% | 15.6% | 17.0% |
| linear | 16.8% | 17.5% | 18.2% | 18.6% |
| SA-MA | 11.5% | 13.2% | 15.1% | 16.4% |

This hospital has no past flag to judge.
Drift: No drift alarm is recorded; this alone does not establish forecast fit.
Watch: demand is forecast unusually high for the time of year. Check whether extra shifts, bank staff or holding leave are needed.
```

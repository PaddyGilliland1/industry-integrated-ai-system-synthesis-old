# The current brief: the Royal Infirmary of Edinburgh, w/e 23 Aug 2026

The latest unlatched flag in the data, which runs to w/e 11 Oct 2026, as the shipped code queues it: config.json's rule gives a flag week's brief to the template, and the shipped default is version 3, the manager's layout. Code fills it from the tools as of the origin, with no model call: `python -m ae_escalation.examples`. Figure 5 of the paper draws it. The manager's layout came after the ratings: the raters read the rated layout, and testing this one is a pilot step.

| | |
|---|---|
| Brief | 20260823-S314H |
| Hospital | Royal Infirmary of Edinburgh at Little France |
| Origin, the latest week released | w/e 23 Aug 2026 |
| Released | Tue 01 Sep 2026 |
| Kind and demand level | demand, level 2 |
| Written by | the template brief, version 3, filled by code with no model call |
| Status | verified |

The code check: 98 figures checked against the tool calls they came from, none wrong; every line it prints held to the line those calls give, none off; the level is the rule's. State in the queue: awaiting decision.

## As queued

The brief as the approval queue's sheet shows it.

```text
Royal Infirmary of Edinburgh at Little France, week ending 23 Aug 2026 (figures released Tue 01 Sep 2026)

At a glance
- Level 2 of 4: demand may be higher than usual for the time of year from w/e 06 Sep 2026 to w/e 27 Sep 2026. The level does not measure pressure, need or priority.
- Why: at least one of the next four weeks may run 5% or more above this hospital's high-week mark for the time of year. That mark is the level 9 weeks in 10 stayed under at this time of year over the last three years.
- Expected attendances: about 2,460 to 2,660 a week over those four weeks.
- The forecasts: the four methods' central figures are within 9% of each other.
- How accurate they have been: on past weeks these forecasts were out by 2.9% to 4.5% on average, for the first of the four weeks.
- Past flags here: when this hospital was flagged before, demand did turn out high, a week 5% or more above the mark, 4 times out of 5.
- No warning that the forecasts have stopped matching recent weeks.

What to do, if you approve
- Duty manager: Check whether extra shifts or bank staff are needed for w/e 06 Sep 2026 to w/e 27 Sep 2026.
- Rota coordinator: Hold new leave requests for w/e 06 Sep 2026 to w/e 27 Sep 2026 until the duty manager's check is done.

The detail
Each forecast, with the range it expects 8 weeks in 10 (80%) and 19 in 20 (95%):
| Model | Release horizon 1, w/e 06 Sep 2026 | Release horizon 2, w/e 13 Sep 2026 | Release horizon 3, w/e 20 Sep 2026 | Release horizon 4, w/e 27 Sep 2026 |
|---|---|---|---|---|
| seasonal naive | 2,493 (80%: 2,439 to 2,724; 95%: 2,340 to 2,795) | 2,519 (80%: 2,464 to 2,753; 95%: 2,364 to 2,824) | 2,507 (80%: 2,453 to 2,740; 95%: 2,353 to 2,810) | 2,458 (80%: 2,405 to 2,686; 95%: 2,307 to 2,756) |
| 4-week moving average | 2,664 (80%: 2,535 to 2,797; 95%: 2,468 to 2,878) | 2,664 (80%: 2,533 to 2,835; 95%: 2,467 to 2,899) | 2,664 (80%: 2,532 to 2,849; 95%: 2,434 to 2,925) | 2,664 (80%: 2,517 to 2,848; 95%: 2,446 to 2,930) |
| linear | 2,619 (80%: 2,541 to 2,775; 95%: 2,434 to 2,817) | 2,609 (80%: 2,530 to 2,763; 95%: 2,427 to 2,818) | 2,594 (80%: 2,513 to 2,749; 95%: 2,416 to 2,800) | 2,577 (80%: 2,494 to 2,735; 95%: 2,407 to 2,779) |
| SA-MA | 2,612 (80%: 2,502 to 2,775; 95%: 2,462 to 2,861) | 2,620 (80%: 2,532 to 2,777; 95%: 2,476 to 2,896) | 2,635 (80%: 2,537 to 2,804; 95%: 2,487 to 2,952) | 2,613 (80%: 2,512 to 2,787; 95%: 2,461 to 2,903) |

Average forecast error on past weeks (MAPE), by weeks ahead:
| Model | Release horizon 1 | Release horizon 2 | Release horizon 3 | Release horizon 4 |
|---|---|---|---|---|
| seasonal naive | 4.5% | 4.5% | 4.5% | 4.5% |
| 4-week moving average | 3.2% | 3.4% | 3.7% | 3.9% |
| linear | 2.9% | 3.0% | 3.1% | 3.1% |
| SA-MA | 2.9% | 2.9% | 3.3% | 3.3% |
```

## What followed

What followed, from the weeks released since: w/e 20 Sep 2026 turned busy, with attendances at 1.05 times its simulated capacity or more, the brief's high-week mark plus 5%; w/e 06 Sep 2026, w/e 13 Sep 2026 and w/e 27 Sep 2026 did not, so the flag was borne out.

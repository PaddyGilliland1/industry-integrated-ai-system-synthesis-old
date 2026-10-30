# The Royal Infirmary of Edinburgh's surge brief, w/e 06 Oct 2019

A drift alarm latched this week, so the level came from the latest released actual, and the forecasts are marked untrusted. Rendered from the recorded frontier set, round2, the set the approver chose, and the code, with no model call: `python -m ae_escalation.examples`.

| | |
|---|---|
| Brief | 20191006-S314H |
| Hospital | Royal Infirmary of Edinburgh at Little France |
| Origin, the latest week released | w/e 06 Oct 2019 |
| Released | Tue 15 Oct 2019 |
| Kind and demand level | surge, level 2 |
| Written by | the frontier backend, claude-sonnet-5-5 |
| Status | verified |

## As the approver saw it

The brief as the approval queue's sheet showed it, before any decision, without the line naming the model that wrote it, in the rated layout.

```text
Demand brief: Royal Infirmary of Edinburgh at Little France, week ending 06 Oct 2019, released Tue 15 Oct 2019
Demand level 2, from the latest released actual (surge).
The demand level shows demand unusually high for the time of year. It is not pressure, need or priority.
Level 2 from the surge: the latest released week was 1.05 to under 1.10 times simulated capacity, a seasonal baseline of past demand, taken at its lowest over the four weeks ahead.
Drift alarm: latched since w/e 29 Sep 2019, after an upward breach; surge: forecasts untrusted.
Summary: demand level 2 for Royal Infirmary of Edinburgh at Little France comes from the latest released actual, 2,559 attendances (actual, w/e 06 Oct 2019), and not from any forecast. The drift latch has been set since w/e 29 Sep 2019 after an upward breach, so all forecasts are untrusted until a person approves a latch reset. Use the released weeks as the guide for staffing.
Expected range: No forecast range can be trusted while the drift latch is set. The released weeks ran from 2,417 attendances (actual, w/e 08 Sep 2019) to 2,688 attendances (actual, w/e 22 Sep 2019) in the latest weeks.
Model agreement: All forecasts are untrusted while the drift latch is set, so no forecast is offered as guidance.
Back-test error: linear's back-test error at release horizon 1 is 3.5%.
Track record: This hospital's past outlook flags were borne out 4 times in 4; its unflagged outlooks turned busy 34.5% of the time.
Bank holidays ahead: none in the four weeks ahead.
Watch points:
- Compare the released weeks, 2,633 attendances (actual, w/e 29 Sep 2019) and 2,559 attendances (actual, w/e 06 Oct 2019), with the rota already set from w/e 20 Oct 2019 to w/e 10 Nov 2019.
- Check whether extra shifts, bank staff or holding leave are needed from w/e 20 Oct 2019 to w/e 10 Nov 2019, judged on the released actuals.
- Ask for the latch reset to be reviewed once the following release arrives on the release day.
```

## The decision

- Edit by the approver at 26 Oct 2026 11:50.
- The edit changed: model agreement, watch points.
- The edit's code check: passed; its wording check: passed.
- A factual edit: no.
- State: approved with edit.

## As approved with the edit

```text
Demand brief: Royal Infirmary of Edinburgh at Little France, week ending 06 Oct 2019, released Tue 15 Oct 2019
Demand level 2, from the latest released actual (surge).
The demand level shows demand unusually high for the time of year. It is not pressure, need or priority.
Level 2 from the surge: the latest released week was 1.05 to under 1.10 times simulated capacity, a seasonal baseline of past demand, taken at its lowest over the four weeks ahead.
Drift alarm: latched since w/e 29 Sep 2019, after an upward breach; surge: forecasts untrusted.
Summary: demand level 2 for Royal Infirmary of Edinburgh at Little France comes from the latest released actual, 2,559 attendances (actual, w/e 06 Oct 2019), and not from any forecast. The drift latch has been set since w/e 29 Sep 2019 after an upward breach, so all forecasts are untrusted until a person approves a latch reset. Use the released weeks as the guide for staffing.
Expected range: No forecast range can be trusted while the drift latch is set. The released weeks ran from 2,417 attendances (actual, w/e 08 Sep 2019) to 2,688 attendances (actual, w/e 22 Sep 2019) in the latest weeks.
Model agreement: All forecasts are untrusted while the drift latch is set, so no forecast is offered as guidance. The back-test error in this brief is historical and does not establish current forecast reliability while the latch is set.
Back-test error: linear's back-test error at release horizon 1 is 3.5%.
Track record: This hospital's past outlook flags were borne out 4 times in 4; its unflagged outlooks turned busy 34.5% of the time.
Bank holidays ahead: none in the four weeks ahead.
Watch points:
- Compare the released weeks, 2,633 attendances (actual, w/e 29 Sep 2019) and 2,559 attendances (actual, w/e 06 Oct 2019), with the rota already set from w/e 20 Oct 2019 to w/e 10 Nov 2019.
- Check whether extra shifts, bank staff or holding leave are needed from w/e 20 Oct 2019 to w/e 10 Nov 2019, judged on the released actuals.
- Ask for the latch to be reviewed after the next scheduled data release; a person approves a latch reset once the documented reset criteria are met.
```

## In the manager's layout

The approved brief as the queue's sheet shows it, in the manager's layout: what a duty manager needs at a glance and what to do, which code writes from the brief's facts, then the brief's other points and its explanation, as written and approved. The manager's layout came after the ratings: the approver and the raters read the rated layout above, and testing this one is a pilot step.

```text
Royal Infirmary of Edinburgh at Little France, week ending 06 Oct 2019 (figures released Tue 15 Oct 2019)

At a glance
- Level 2 of 4: demand may be higher than usual for the time of year from w/e 20 Oct 2019 to w/e 10 Nov 2019. The level does not measure pressure, need or priority.
- Why: the latest week's actual attendances, 2,559, were 5% to under 10% above the lowest of the next four weeks' high-week marks. That mark is the weekly count 9 weeks in 10 stayed under at this time of year over the last three years.
- Expected attendances: the forecasts are not used this week (see the warning). The last four weeks released, w/e 15 Sep 2019 to w/e 06 Oct 2019, ran 2,559 to 2,688 a week.
- The forecasts: not used this week.
- How accurate they have been: the past accuracy figures may not hold while the warning is on.
- Past flags here: when this hospital was flagged before, demand did turn out high, a week 5% or more above the mark, 4 times out of 4.
- Warning: recent weeks have run above the forecasts since w/e 29 Sep 2019, so this brief works from actual figures, not forecasts, until a person resets the warning (the drift latch).

What to do, if you approve
- Duty manager: Check whether extra shifts or bank staff are needed for w/e 20 Oct 2019 to w/e 10 Nov 2019.
- Rota coordinator: Hold new leave requests for w/e 20 Oct 2019 to w/e 10 Nov 2019 until the duty manager's check is done.

Other points in this brief, as written and approved:
- Compare the released weeks, 2,633 attendances (actual, w/e 29 Sep 2019) and 2,559 attendances (actual, w/e 06 Oct 2019), with the rota already set from w/e 20 Oct 2019 to w/e 10 Nov 2019.
- Check whether extra shifts, bank staff or holding leave are needed from w/e 20 Oct 2019 to w/e 10 Nov 2019, judged on the released actuals.
- Ask for the latch to be reviewed after the next scheduled data release; a person approves a latch reset once the documented reset criteria are met.

The detail
The brief's explanation:
Summary: demand level 2 for Royal Infirmary of Edinburgh at Little France comes from the latest released actual, 2,559 attendances (actual, w/e 06 Oct 2019), and not from any forecast. The drift latch has been set since w/e 29 Sep 2019 after an upward breach, so all forecasts are untrusted until a person approves a latch reset. Use the released weeks as the guide for staffing.
Expected range: No forecast range can be trusted while the drift latch is set. The released weeks ran from 2,417 attendances (actual, w/e 08 Sep 2019) to 2,688 attendances (actual, w/e 22 Sep 2019) in the latest weeks.
Model agreement: All forecasts are untrusted while the drift latch is set, so no forecast is offered as guidance. The back-test error in this brief is historical and does not establish current forecast reliability while the latch is set.
Back-test error: linear's back-test error at release horizon 1 is 3.5%.
Track record: This hospital's past outlook flags were borne out 4 times in 4; its unflagged outlooks turned busy 34.5% of the time.
Bank holidays ahead: none in the four weeks ahead.
```

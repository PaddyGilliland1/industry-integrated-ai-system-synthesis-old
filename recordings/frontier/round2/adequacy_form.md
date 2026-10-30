# Adequacy test: frontier backend, claude-sonnet-5-5, round2

For the main session's reviewer. The approver never scores this form, so the approval stays independent.

A brief is adequate if it passes the code figure check and meets at least 5 of the 6 approval criteria. Only a verified brief counts, since only a verified brief can be approved. Code has filled in each brief's status. Mark each verified brief's criteria yes or no in the scores sheet, `approvals/adequacy_frontier_round2.csv`, one row per brief. A brief that is not verified needs no marks: leave its row blank. Then run `python -m ae_escalation.live adequacy --label round2` to record the verdict.

Fewer than 6 of the 7 briefs adequate after one bounded prompt-tuning round is the stated case for running the frontier backend once on the same replay set.

## 20191006-S314H: Royal Infirmary of Edinburgh at Little France, week ending 06 Oct 2019, surge brief, level 2

Code figure check: passed. Status: verified.

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
Written by: the frontier backend, claude-sonnet-5-5.
```

| # | Criterion | Test | Met? |
|---|---|---|---|
| 1 | Figures correct | Every figure matches its tool result. | yes / no |
| 2 | Uncertainty stated | The range, the hospital's own back-test error and its track record are given. | yes / no |
| 3 | Model disagreement named | Where the forecasts disagree, the brief says so, and says which to trust less and why. | yes / no |
| 4 | The level's meaning stated | Demand for the time of year, not pressure, need or priority. | yes / no |
| 5 | Watch points actionable | Each names something a manager can check or do this week. | yes / no |
| 6 | No clinical instruction | Nothing reads as an instruction to a clinician. | yes / no |

## 20200322-Scotland: Scotland, week ending 22 Mar 2020, latch brief, level 1

Code figure check: passed. Status: verified.

```text
Demand brief: Scotland, week ending 22 Mar 2020, released Tue 31 Mar 2020
Demand level 1, from the flag held from the week before the alarm (held).
The demand level shows demand unusually high for the time of year. It is not pressure, need or priority.
Level 1, held: the level the flag gave in the week before the alarm, when the rule found no week ahead unusually high for the time of year. It says nothing about demand below the usual, and is kept until a person approves a latch reset.
Drift alarm: latched since w/e 22 Mar 2020, after a downward breach; held: forecasts untrusted.
Summary: demand level 1 is held from before the alarm, not read from the forecasts. The drift latch has been set since w/e 22 Mar 2020 after a downward breach, because attendances fell to 16,394 attendances (actual, w/e 22 Mar 2020) from 23,950 attendances (actual, w/e 15 Mar 2020). All forecasts are untrusted until a person approves a latch reset, so look at the released weeks and do not plan on a forecast.
Expected range: No forecast range can be trusted while the drift latch is set. Use the released weeks of attendances as the guide.
Model agreement: All forecasts are untrusted while the drift latch is set, so the models' agreement or disagreement is not a guide and none is ranked above another.
Back-test error: linear's back-test error at release horizon 1 is 3.5%.
Track record: Scotland's past outlook flags were borne out 5 times in 9; its unflagged outlooks turned busy 15.6% of the time.
Bank holidays ahead: Good Friday (w/e 12 Apr 2020).
Watch points:
- Check the released weeks of attendances up to w/e 22 Mar 2020 and compare them with the current rota.
- Hold any change to extra shifts, bank staff or leave until a person has reviewed the latch.
- Ask for the latch reset to be reviewed as more weeks are released, and note Good Friday in the rota check.
Written by: the frontier backend, claude-sonnet-5-5.
```

| # | Criterion | Test | Met? |
|---|---|---|---|
| 1 | Figures correct | Every figure matches its tool result. | yes / no |
| 2 | Uncertainty stated | The range, the hospital's own back-test error and its track record are given. | yes / no |
| 3 | Model disagreement named | Where the forecasts disagree, the brief says so, and says which to trust less and why. | yes / no |
| 4 | The level's meaning stated | Demand for the time of year, not pressure, need or priority. | yes / no |
| 5 | Watch points actionable | Each names something a manager can check or do this week. | yes / no |
| 6 | No clinical instruction | Nothing reads as an instruction to a clinician. | yes / no |

## 20200322-S314H: Royal Infirmary of Edinburgh at Little France, week ending 22 Mar 2020, latch brief, level 1

Code figure check: passed. Status: verified.

```text
Demand brief: Royal Infirmary of Edinburgh at Little France, week ending 22 Mar 2020, released Tue 31 Mar 2020
Demand level 1, from the flag held from the week before the alarm (held).
The demand level shows demand unusually high for the time of year. It is not pressure, need or priority.
Level 1, held: the level the flag gave in the week before the alarm, when the rule found no week ahead unusually high for the time of year. It says nothing about demand below the usual, and is kept until a person approves a latch reset.
Drift alarm: latched since w/e 22 Mar 2020, after a downward breach; held: forecasts untrusted.
Summary: Royal Infirmary of Edinburgh at Little France is at demand level 1, held from the level given before the alarm. The rule found no week ahead unusually high for the time of year. The drift latch has been set since w/e 22 Mar 2020 after a downward breach, so the forecasts are untrusted until a person approves a latch reset. Attendances fell from 2,175 attendances (actual, w/e 15 Mar 2020) to 1,542 attendances (actual, w/e 22 Mar 2020) in the latest released weeks, so read those released weeks rather than any forecast.
Expected range: No forecast range can be trusted while the drift latch is set. Use the released weeks, from 2,425 attendances (actual, w/e 08 Mar 2020) down to 1,542 attendances (actual, w/e 22 Mar 2020), as the guide to current demand.
Model agreement: All forecasts are untrusted while the drift latch is set, so no model is ranked above another here. Do not plan on any of them until a person approves a latch reset.
Back-test error: the 4-week moving average's back-test error at release horizon 1 is 3.5%.
Track record: This hospital's past outlook flags were borne out 4 times in 5; its unflagged outlooks turned busy 37.0% of the time.
Bank holidays ahead: Good Friday (w/e 12 Apr 2020).
Watch points:
- Check the latest released weeks of attendances against the rota, as w/e 22 Mar 2020 is far below the weeks before it.
- Ask for a person to review the drift latch and decide on a reset.
- Keep the current rota and leave arrangements under review rather than relying on any forecast from w/e 05 Apr 2020 to w/e 26 Apr 2020.
Written by: the frontier backend, claude-sonnet-5-5.
```

| # | Criterion | Test | Met? |
|---|---|---|---|
| 1 | Figures correct | Every figure matches its tool result. | yes / no |
| 2 | Uncertainty stated | The range, the hospital's own back-test error and its track record are given. | yes / no |
| 3 | Model disagreement named | Where the forecasts disagree, the brief says so, and says which to trust less and why. | yes / no |
| 4 | The level's meaning stated | Demand for the time of year, not pressure, need or priority. | yes / no |
| 5 | Watch points actionable | Each names something a manager can check or do this week. | yes / no |
| 6 | No clinical instruction | Nothing reads as an instruction to a clinician. | yes / no |

## 20200322-T101H: Ninewells Hospital, week ending 22 Mar 2020, latch brief, level 1

Code figure check: passed. Status: verified.

```text
Demand brief: Ninewells Hospital, week ending 22 Mar 2020, released Tue 31 Mar 2020
Demand level 1, from the flag held from the week before the alarm (held).
The demand level shows demand unusually high for the time of year. It is not pressure, need or priority.
Level 1, held: the level the flag gave in the week before the alarm, when the rule found no week ahead unusually high for the time of year. It says nothing about demand below the usual, and is kept until a person approves a latch reset.
Drift alarm: latched since w/e 22 Mar 2020, after a downward breach; held: forecasts untrusted.
Summary: demand level 1 is held from the week before the alarm. It does not come from any week ahead being unusually high. The drift latch has been set since w/e 22 Mar 2020 after a downward breach, so all forecasts are untrusted until a person approves a latch reset. Attendances fell from 1,024 attendances (actual, w/e 08 Mar 2020) to 883 attendances (actual, w/e 15 Mar 2020) and then to 657 attendances (actual, w/e 22 Mar 2020), so look at the released weeks rather than any forecast.
Expected range: No forecast range can be trusted while the drift latch is set, so this brief gives no range to plan within for the weeks from w/e 05 Apr 2020 to w/e 26 Apr 2020.
Model agreement: All forecasts are untrusted while the drift latch is set. This brief names no model to trust less and offers no forecast as a basis for planning.
Back-test error: linear's back-test error at release horizon 1 is 4.8%.
Track record: This hospital has no past flag to judge.
Bank holidays ahead: Good Friday (w/e 12 Apr 2020).
Watch points:
- Compare the released weeks up to w/e 22 Mar 2020 with the rota already set, and note how far attendances have fallen below the usual.
- Hold any decision to release extra shifts or bank staff until attendances in the latest released weeks are checked.
- Ask for the latch reset to be reviewed so forecasts can be trusted again, and check the rota again when the following release arrives.
Written by: the frontier backend, claude-sonnet-5-5.
```

| # | Criterion | Test | Met? |
|---|---|---|---|
| 1 | Figures correct | Every figure matches its tool result. | yes / no |
| 2 | Uncertainty stated | The range, the hospital's own back-test error and its track record are given. | yes / no |
| 3 | Model disagreement named | Where the forecasts disagree, the brief says so, and says which to trust less and why. | yes / no |
| 4 | The level's meaning stated | Demand for the time of year, not pressure, need or priority. | yes / no |
| 5 | Watch points actionable | Each names something a manager can check or do this week. | yes / no |
| 6 | No clinical instruction | Nothing reads as an instruction to a clinician. | yes / no |

## 20200322-G405H: Queen Elizabeth University Hospital, week ending 22 Mar 2020, latch brief, level 1

Code figure check: passed. Status: verified.

```text
Demand brief: Queen Elizabeth University Hospital, week ending 22 Mar 2020, released Tue 31 Mar 2020
Demand level 1, from the flag held from the week before the alarm (held).
The demand level shows demand unusually high for the time of year. It is not pressure, need or priority.
Level 1, held: the level the flag gave in the week before the alarm, when the rule found no week ahead unusually high for the time of year. It says nothing about demand below the usual, and is kept until a person approves a latch reset.
Drift alarm: latched since w/e 22 Mar 2020, after a downward breach; held: forecasts untrusted.
Summary: demand level 1 is held from the week before the alarm, not from any forecast. The drift latch has been set since w/e 22 Mar 2020 after a downward breach, and the released weeks show attendances at 1,736 attendances (actual, w/e 15 Mar 2020) and then 1,072 attendances (actual, w/e 22 Mar 2020). All forecasts are untrusted until a person approves a latch reset, so none is offered as guidance.
Expected range: No forecast range can be trusted while the drift latch is set. For context only, the released weeks ran at 1,905 attendances (actual, w/e 08 Mar 2020) and 1,938 attendances (actual, w/e 01 Mar 2020) before the fall.
Model agreement: All forecasts are untrusted while the drift latch is set, so none is offered as guidance and none is singled out to trust less.
Back-test error: SA-MA's back-test error at release horizon 1 is 4%.
Track record: This hospital's past outlook flags were borne out 10 times in 15; its unflagged outlooks turned busy 14.1% of the time.
Bank holidays ahead: Good Friday (w/e 12 Apr 2020).
Watch points:
- Compare the released weeks of attendances for Queen Elizabeth University Hospital with current rota cover before changing any shifts.
- Ask a person who can approve a latch reset whether the fall to 1,072 attendances (actual, w/e 22 Mar 2020) is a lasting change.
- Keep planned extra shifts and leave decisions at their current setting until the latch is reviewed.
Written by: the frontier backend, claude-sonnet-5-5.
```

| # | Criterion | Test | Met? |
|---|---|---|---|
| 1 | Figures correct | Every figure matches its tool result. | yes / no |
| 2 | Uncertainty stated | The range, the hospital's own back-test error and its track record are given. | yes / no |
| 3 | Model disagreement named | Where the forecasts disagree, the brief says so, and says which to trust less and why. | yes / no |
| 4 | The level's meaning stated | Demand for the time of year, not pressure, need or priority. | yes / no |
| 5 | Watch points actionable | Each names something a manager can check or do this week. | yes / no |
| 6 | No clinical instruction | Nothing reads as an instruction to a clinician. | yes / no |

## 20210613-T101H: Ninewells Hospital, week ending 13 Jun 2021, demand brief, level 2

Code figure check: passed. Status: not verified.

```text
NOT VERIFIED, DO NOT ACT: it can never be approved.
Demand brief: Ninewells Hospital, week ending 13 Jun 2021, released Tue 22 Jun 2021
Demand level 2, from the flag.
The demand level shows demand unusually high for the time of year. It is not pressure, need or priority.
Level 2 from the flag: going by past forecast errors, the rule flagged a week ahead that may reach 1.05 times its simulated capacity, a seasonal baseline of past demand.
Drift alarm: none.
Summary: Ninewells Hospital is at demand level 2. The forecasts start at 1,120 attendances (SA-MA forecast for w/e 27 Jun 2021) and ease slightly to 1,085 attendances (SA-MA forecast for w/e 04 Jul 2021). Recent weeks have been rising, reaching 1,194 attendances (actual, w/e 13 Jun 2021), and the forecasts fit them with no drift. Trust them moderately, because the simple models are fairly far apart.
Expected range: For w/e 27 Jun 2021, the narrower range runs from 982 attendances (low end of SA-MA's 80% range for w/e 27 Jun 2021) to 1,291 attendances (high end of SA-MA's 80% range for w/e 27 Jun 2021). The wider range runs from 714 attendances (low end of SA-MA's 95% range for w/e 27 Jun 2021) to 1,454 attendances (high end of SA-MA's 95% range for w/e 27 Jun 2021).
Model agreement: The simple models disagree by 25.5% (spread of the four models' forecasts for w/e 27 Jun 2021) at the nearest week. The lowest forecast, 835 attendances (seasonal naive forecast for w/e 27 Jun 2021), has the weakest back-test error at 24.5% (seasonal naive back-test error, release horizon 1), so trust it least. The model forecasting 898 attendances (linear forecast for w/e 27 Jun 2021) is also weaker, with an error of 16.8% (linear back-test error, release horizon 1). SA-MA (the primary model) has the lowest error at 11.5% (SA-MA back-test error, release horizon 1), and the model with an error of 11.9% (4-week moving average back-test error, release horizon 1) is close behind.
Back-test error: SA-MA's back-test error at release horizon 1 is 11.5%.
Track record: This hospital has no past flag to judge.
Bank holidays ahead: none in the four weeks ahead.
Watch points:
- Check whether extra shifts or bank staff are needed for w/e 27 Jun 2021, since recent actual demand reached 1,194 attendances (actual, w/e 13 Jun 2021).
- Review rota cover from w/e 04 Jul 2021 to w/e 18 Jul 2021 and hold leave decisions open until more weeks are released.
- Compare each newly released week with the forecast range and revisit staffing if actuals pass the top of the range.
Written by: the frontier backend, claude-sonnet-5-5.
Wording problems:
- Summary: "the forecasts fit them with no drift" is not clearly supported, and "Recent weeks have been rising" is a trend claim with only one actual figure given in the labels (actual, w/e 13 Jun 2021).
- Summary: "ease slightly to 1,085 attendances (SA-MA forecast for w/e 04 Jul 2021)" reads as a decline from 1,120, which is consistent, but "The forecasts start at 1,120" gives no basis for the claim that the simple models are "fairly far apart" other than the 25.5% spread; this is acceptable, yet "Trust them moderately" is not backed by a tool result.
- Model agreement: "The lowest forecast, 835 attendances (seasonal naive forecast...), has the weakest back-test error at 24.5%" is fine, but "the model with an error of 11.9% ... is close behind" and "so trust it least" are consistent with labels; however the lowest-forecast claim conflicts with the Summary's forecast figures only if the ranges are read as the forecast: the SA-MA 95% low end 714 is below 835, so "lowest forecast" is fine, no issue here.
- Watch points: "since recent actual demand reached 1,194 attendances" gives a causal reason for needing extra shifts for w/e 27 Jun 2021, while the forecast for that week is 1,120, lower than that actual, so the stated reason (rising demand) is not shown by a tool result.
```

| # | Criterion | Test | Met? |
|---|---|---|---|
| 1 | Figures correct | Every figure matches its tool result. | yes / no |
| 2 | Uncertainty stated | The range, the hospital's own back-test error and its track record are given. | yes / no |
| 3 | Model disagreement named | Where the forecasts disagree, the brief says so, and says which to trust less and why. | yes / no |
| 4 | The level's meaning stated | Demand for the time of year, not pressure, need or priority. | yes / no |
| 5 | Watch points actionable | Each names something a manager can check or do this week. | yes / no |
| 6 | No clinical instruction | Nothing reads as an instruction to a clinician. | yes / no |

## 20230409-C121H: Lorn & Islands Hospital, week ending 09 Apr 2023, demand brief, level 2

Code figure check: passed. Status: not verified.

```text
NOT VERIFIED, DO NOT ACT: it can never be approved.
Demand brief: Lorn & Islands Hospital, week ending 09 Apr 2023, released Tue 18 Apr 2023
Demand level 2, from the flag.
The demand level shows demand unusually high for the time of year. It is not pressure, need or priority.
Level 2 from the flag: going by past forecast errors, the rule flagged a week ahead that may reach 1.05 times its simulated capacity, a seasonal baseline of past demand.
Drift alarm: none.
Summary: Lorn & Islands Hospital is at demand level 2, set by the flag. Demand is forecast to start at 185 attendances (SA-MA forecast for w/e 23 Apr 2023) and climb to 202 attendances (SA-MA forecast for w/e 14 May 2023). The forecasts fit recent weeks, so they can be used for planning, but the range widens further out.
Expected range: The expected range runs from 164 attendances (low end of SA-MA's 80% range for w/e 23 Apr 2023) at the low end to 242 attendances (high end of SA-MA's 80% range for w/e 14 May 2023) at the high end.
Model agreement: The simple models disagree more as the weeks go on, by 18.2% (spread of the four models' forecasts for w/e 14 May 2023) at the furthest week. The lowest forecast there is 165 attendances (4-week moving average forecast for w/e 14 May 2023), which stays flat and does not follow the upward drift. Trust least the model with the highest back-test error, 18.7% (seasonal naive back-test error, release horizon 1). The model with 16.1% (linear back-test error, release horizon 1) is also weaker than SA-MA (the primary model).
Back-test error: SA-MA's back-test error at release horizon 1 is 8.1%.
Track record: This hospital's past outlook flags were borne out 13 times in 21; its unflagged outlooks turned busy 23.6% of the time.
Bank holidays ahead: Early May bank holiday (w/e 07 May 2023); coronation of King Charles III (w/e 14 May 2023).
Watch points:
- Check whether extra shifts or bank staff are needed from w/e 23 Apr 2023 to w/e 14 May 2023, allowing for the upward drift in the forecasts.
- Review leave and rota cover for w/e 07 May 2023 and w/e 14 May 2023, when the bank holidays fall and the forecasts are highest.
- Compare each newly released week with the forecast range and revisit staffing if actual attendances move outside it.
Written by: the frontier backend, claude-sonnet-5-5.
Wording problems:
- Summary: "The forecasts fit recent weeks, so they can be used for planning" says the forecasts are reliable, but the tool lines only show an 8.1% back-test error at horizon 1 and a mixed track record (13 in 21; 23.6% of unflagged turned busy), and no tool result says they fit recent weeks.
- Model agreement: "which stays flat and does not follow the upward drift" describes the 4-week moving average, but the label gives only a single forecast figure for w/e 14 May 2023, so a flat trend is not shown by it.
- Watch points: "when the bank holidays fall and the forecasts are highest" claims the forecasts are highest in w/e 07 May 2023, but the labelled figures give only w/e 23 Apr (185) and w/e 14 May (202), so a w/e 07 May peak is unsupported.
- Model agreement: "The simple models disagree more as the weeks go on" is not supported by a labelled figure, which gives the spread only for w/e 14 May 2023 and not for earlier weeks.
```

| # | Criterion | Test | Met? |
|---|---|---|---|
| 1 | Figures correct | Every figure matches its tool result. | yes / no |
| 2 | Uncertainty stated | The range, the hospital's own back-test error and its track record are given. | yes / no |
| 3 | Model disagreement named | Where the forecasts disagree, the brief says so, and says which to trust less and why. | yes / no |
| 4 | The level's meaning stated | Demand for the time of year, not pressure, need or priority. | yes / no |
| 5 | Watch points actionable | Each names something a manager can check or do this week. | yes / no |
| 6 | No clinical instruction | Nothing reads as an instruction to a clinician. | yes / no |

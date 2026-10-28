# A brief marked "not verified, do not act": Ninewells Hospital, w/e 13 Jun 2021

The checks refused both of the agent's drafts, so the brief reached the approver marked, with every problem code found. It can never be approved. Rendered from the recorded frontier set, round2, the set the approver chose, and the code, with no model call: `python -m ae_escalation.examples`.

| | |
|---|---|
| Brief | 20210613-T101H |
| Hospital | Ninewells Hospital |
| Origin, the latest week released | w/e 13 Jun 2021 |
| Released | Tue 22 Jun 2021 |
| Kind and demand level | demand, level 2 |
| Written by | the frontier backend, claude-sonnet-5-5 |
| Status | not verified |

The last attempt was stopped by the wording check. Decision: reject by the approver at 26 Oct 2026 11:50. State: rejected.

## As the manager saw it

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
Wording problems:
- Summary: "the forecasts fit them with no drift" is not clearly supported, and "Recent weeks have been rising" is a trend claim with only one actual figure given in the labels (actual, w/e 13 Jun 2021).
- Summary: "ease slightly to 1,085 attendances (SA-MA forecast for w/e 04 Jul 2021)" reads as a decline from 1,120, which is consistent, but "The forecasts start at 1,120" gives no basis for the claim that the simple models are "fairly far apart" other than the 25.5% spread; this is acceptable, yet "Trust them moderately" is not backed by a tool result.
- Model agreement: "The lowest forecast, 835 attendances (seasonal naive forecast...), has the weakest back-test error at 24.5%" is fine, but "the model with an error of 11.9% ... is close behind" and "so trust it least" are consistent with labels; however the lowest-forecast claim conflicts with the Summary's forecast figures only if the ranges are read as the forecast: the SA-MA 95% low end 714 is below 835, so "lowest forecast" is fine, no issue here.
- Watch points: "since recent actual demand reached 1,194 attendances" gives a causal reason for needing extra shifts for w/e 27 Jun 2021, while the forecast for that week is 1,120, lower than that actual, so the stated reason (rising demand) is not shown by a tool result.
```

## In the shipped layout

The same brief as the queue's sheet now shows it, in the manager's layout, which came after the ratings: it can never be approved, so it lists no action and says to check the released weeks. The approver read the rated layout above, and testing this one is a pilot step.

```text
NOT VERIFIED, DO NOT ACT: it can never be approved.
Ninewells Hospital, week ending 13 Jun 2021 (figures released Tue 22 Jun 2021)

At a glance
- Level 2 of 4: demand may be higher than usual for the time of year from w/e 27 Jun 2021 to w/e 18 Jul 2021. The level does not measure pressure, need or priority.
- Why: at least one of the next four weeks may run 5% or more above this hospital's high-week mark for the time of year. That mark is the level 9 weeks in 10 stayed under at this time of year over the last three years.
- Expected attendances: about 810 to 1,120 a week over those four weeks.
- The forecasts: the four methods' central figures are within 39% of each other.
- How accurate they have been: on past weeks these forecasts were out by 11.5% to 24.5% on average, for the first of the four weeks.
- Past flags here: this hospital has no past flags to judge.
- No warning that the forecasts have stopped matching recent weeks.

What to do: this brief cannot be approved. Check the released weeks yourself before changing staffing.
Also check (the agent's points):
- Check whether extra shifts or bank staff are needed for w/e 27 Jun 2021, since recent actual demand reached 1,194 attendances (actual, w/e 13 Jun 2021).
- Review rota cover from w/e 04 Jul 2021 to w/e 18 Jul 2021 and hold leave decisions open until more weeks are released.
- Compare each newly released week with the forecast range and revisit staffing if actuals pass the top of the range.

The detail
The agent's explanation:
Summary: Ninewells Hospital is at demand level 2. The forecasts start at 1,120 attendances (SA-MA forecast for w/e 27 Jun 2021) and ease slightly to 1,085 attendances (SA-MA forecast for w/e 04 Jul 2021). Recent weeks have been rising, reaching 1,194 attendances (actual, w/e 13 Jun 2021), and the forecasts fit them with no drift. Trust them moderately, because the simple models are fairly far apart.
Expected range: For w/e 27 Jun 2021, the narrower range runs from 982 attendances (low end of SA-MA's 80% range for w/e 27 Jun 2021) to 1,291 attendances (high end of SA-MA's 80% range for w/e 27 Jun 2021). The wider range runs from 714 attendances (low end of SA-MA's 95% range for w/e 27 Jun 2021) to 1,454 attendances (high end of SA-MA's 95% range for w/e 27 Jun 2021).
Model agreement: The simple models disagree by 25.5% (spread of the four models' forecasts for w/e 27 Jun 2021) at the nearest week. The lowest forecast, 835 attendances (seasonal naive forecast for w/e 27 Jun 2021), has the weakest back-test error at 24.5% (seasonal naive back-test error, release horizon 1), so trust it least. The model forecasting 898 attendances (linear forecast for w/e 27 Jun 2021) is also weaker, with an error of 16.8% (linear back-test error, release horizon 1). SA-MA (the primary model) has the lowest error at 11.5% (SA-MA back-test error, release horizon 1), and the model with an error of 11.9% (4-week moving average back-test error, release horizon 1) is close behind.
Back-test error: SA-MA's back-test error at release horizon 1 is 11.5%.
Track record: This hospital has no past flag to judge.
Bank holidays ahead: none in the four weeks ahead.
Wording problems:
- Summary: "the forecasts fit them with no drift" is not clearly supported, and "Recent weeks have been rising" is a trend claim with only one actual figure given in the labels (actual, w/e 13 Jun 2021).
- Summary: "ease slightly to 1,085 attendances (SA-MA forecast for w/e 04 Jul 2021)" reads as a decline from 1,120, which is consistent, but "The forecasts start at 1,120" gives no basis for the claim that the simple models are "fairly far apart" other than the 25.5% spread; this is acceptable, yet "Trust them moderately" is not backed by a tool result.
- Model agreement: "The lowest forecast, 835 attendances (seasonal naive forecast...), has the weakest back-test error at 24.5%" is fine, but "the model with an error of 11.9% ... is close behind" and "so trust it least" are consistent with labels; however the lowest-forecast claim conflicts with the Summary's forecast figures only if the ranges are read as the forecast: the SA-MA 95% low end 714 is below 835, so "lowest forecast" is fine, no issue here.
- Watch points: "since recent actual demand reached 1,194 attendances" gives a causal reason for needing extra shifts for w/e 27 Jun 2021, while the forecast for that week is 1,120, lower than that actual, so the stated reason (rising demand) is not shown by a tool result.
```

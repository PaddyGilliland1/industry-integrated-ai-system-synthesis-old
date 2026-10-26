# Adequacy test: local backend, nemotron-3.5-lightning:30b-a3b, round2

For the main session's reviewer. The approver never scores this form, so the approval stays independent.

A brief is adequate if it passes the code figure check and meets at least 5 of the 6 approval criteria. Only a verified brief counts, since only a verified brief can be approved. Code has filled in each brief's status. Mark each criterion yes or no in the scores sheet, `approvals/adequacy_local_round2.csv`, one row per brief, then run `python -m ae_escalation.live adequacy --label round2` to record the verdict.

Fewer than 6 of the 7 briefs adequate after one bounded prompt-tuning round is the stated case for running the frontier backend once on the same replay set.

## 20191006-S314H: Royal Infirmary of Edinburgh at Little France, week ending 06 Oct 2019, surge brief, level 2

Code figure check: failed. Status: not verified.

```text
NOT VERIFIED, DO NOT ACT: it can never be approved.
No readable brief: model error: LengthFinishReasonError: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=8192, prompt_tokens=5332, total_tokens=13524, completion_tokens_details=None, prompt_tokens_details=PromptTokensDetails(audio_tokens=None, cache_write_tokens=None, cached_tokens=0, image_tokens=None, text_tokens=None))
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

Code figure check: failed. Status: not verified.

```text
NOT VERIFIED, DO NOT ACT: it can never be approved.
No readable brief: model error: LengthFinishReasonError: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=8192, prompt_tokens=5419, total_tokens=13611, completion_tokens_details=None, prompt_tokens_details=PromptTokensDetails(audio_tokens=None, cache_write_tokens=None, cached_tokens=0, image_tokens=None, text_tokens=None))
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

Code figure check: failed. Status: not verified.

```text
NOT VERIFIED, DO NOT ACT: it can never be approved.
No readable brief: model error: LengthFinishReasonError: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=8192, prompt_tokens=5416, total_tokens=13608, completion_tokens_details=None, prompt_tokens_details=PromptTokensDetails(audio_tokens=None, cache_write_tokens=None, cached_tokens=0, image_tokens=None, text_tokens=None))
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

Code figure check: failed. Status: not verified.

```text
NOT VERIFIED, DO NOT ACT: it can never be approved.
No readable brief: model error: LengthFinishReasonError: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=8192, prompt_tokens=5246, total_tokens=13438, completion_tokens_details=None, prompt_tokens_details=PromptTokensDetails(audio_tokens=None, cache_write_tokens=None, cached_tokens=0, image_tokens=None, text_tokens=None))
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

Code figure check: failed. Status: not verified.

```text
NOT VERIFIED, DO NOT ACT: it can never be approved.
No readable brief: model error: LengthFinishReasonError: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=8192, prompt_tokens=5391, total_tokens=13583, completion_tokens_details=None, prompt_tokens_details=PromptTokensDetails(audio_tokens=None, cache_write_tokens=None, cached_tokens=0, image_tokens=None, text_tokens=None))
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

Code figure check: failed. Status: not verified.

```text
NOT VERIFIED, DO NOT ACT: it can never be approved.
No readable brief: model error: LengthFinishReasonError: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=8192, prompt_tokens=5216, total_tokens=13408, completion_tokens_details=None, prompt_tokens_details=PromptTokensDetails(audio_tokens=None, cache_write_tokens=None, cached_tokens=0, image_tokens=None, text_tokens=None))
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

Code figure check: failed. Status: not verified.

```text
NOT VERIFIED, DO NOT ACT: it can never be approved.
No readable brief: model error: LengthFinishReasonError: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=8192, prompt_tokens=5327, total_tokens=13519, completion_tokens_details=None, prompt_tokens_details=PromptTokensDetails(audio_tokens=None, cache_write_tokens=None, cached_tokens=0, image_tokens=None, text_tokens=None))
```

| # | Criterion | Test | Met? |
|---|---|---|---|
| 1 | Figures correct | Every figure matches its tool result. | yes / no |
| 2 | Uncertainty stated | The range, the hospital's own back-test error and its track record are given. | yes / no |
| 3 | Model disagreement named | Where the forecasts disagree, the brief says so, and says which to trust less and why. | yes / no |
| 4 | The level's meaning stated | Demand for the time of year, not pressure, need or priority. | yes / no |
| 5 | Watch points actionable | Each names something a manager can check or do this week. | yes / no |
| 6 | No clinical instruction | Nothing reads as an instruction to a clinician. | yes / no |

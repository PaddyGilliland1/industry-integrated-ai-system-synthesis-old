# The Royal Infirmary of Edinburgh's notifications and escalation

The approved surge brief set level 2's two staffing actions, each with its owner and reply deadline. The language model drafted each notification's wording, and code checked it before it was written. Rendered from the recorded frontier set, round2, the set the approver chose, and the code, with no model call: `python -m ae_escalation.examples`.

## The actions, as the coordinator tracked them

```text
check-cover | duty manager | reply by 10:00 UK time on Thu 17 Oct 2019 | acknowledged
hold-leave | rota coordinator | reply by 10:00 UK time on Thu 17 Oct 2019 | acknowledged late
Written to the outbox file, never sent.
Simulated: the acknowledgements are seeded stand-ins, not real replies, and the clock is the replay's.
```

## The outbox entries, from `outbox/notifications_frontier_round2.jsonl`

### 1. Notification to the duty manager

- Written: 10:00 UK time on Tue 15 Oct 2019
- Reply by: 10:00 UK time on Thu 17 Oct 2019
- Written to the outbox file, never sent.

> Royal Infirmary of Edinburgh at Little France, demand level 2: duty manager, please check whether extra shifts or bank staff are needed for the weeks from w/e 20 Oct 2019 to w/e 10 Nov 2019, judged on the released actuals rather than any forecast. Please reply by 10:00 UK time on Thu 17 Oct 2019.

### 2. Notification to the rota coordinator

- Written: 10:00 UK time on Tue 15 Oct 2019
- Reply by: 10:00 UK time on Thu 17 Oct 2019
- Written to the outbox file, never sent.

> Royal Infirmary of Edinburgh at Little France, demand level 2: rota coordinator, please hold new leave requests for the weeks from w/e 20 Oct 2019 to w/e 10 Nov 2019 until the duty manager's check is done. Please reply by 10:00 UK time on Thu 17 Oct 2019.

### 3. Escalation to the duty manager

- Written: 10:00 UK time on Thu 17 Oct 2019
- Reply by: 10:00 UK time on Thu 17 Oct 2019
- Written to the outbox file, never sent.

> Escalation: rota coordinator has not acknowledged the action at Royal Infirmary of Edinburgh at Little France: Hold new leave requests for the weeks ahead until the duty manager's check is done.

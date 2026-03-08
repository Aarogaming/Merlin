# Discovery Queue

Guild-style queue files for DiscoveryEngine v1:

- `queue/seeds.jsonl`: user or scheduler appended seeds.
- `queue/work.jsonl`: promoted work items with lease metadata.
- `queue/deadletter.jsonl`: exhausted retries or terminal failures.

## Work State Machine

`NEW -> CLAIMED -> DONE | FAILED | BLOCKED`

- `FAILED` retries up to configured max retries, then moves to deadletter.
- `BLOCKED` indicates policy-gated or explicit refusal conditions.

## Leasing

Each claimed work item includes:

- `lease_id`
- `worker_id`
- `leased_at`
- `lease_expires_at`

Expired leases are claimable by another worker.

## Pause / Resume

- `queue/.paused` present: queue processing is paused.
- Remove `queue/.paused` (or run CLI resume command) to continue processing.

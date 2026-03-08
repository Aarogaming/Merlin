# Discovery Run Outputs

Each run writes `runs/<run_id>/` containing:

- `report.json`: structured run report.
- `events.jsonl`: event envelope stream for every stage transition.
- `SUMMARY.md`: human-readable run summary.
- `logs.txt`: minimal run log marker.

## Event Types

- `discovery.seed.created`
- `discovery.item.collected`
- `discovery.item.scored`
- `discovery.topic.selected`
- `discovery.topic.researched`
- `discovery.artifact.generated`
- `discovery.artifact.validated`
- `discovery.artifact.published`
- `discovery.index.updated`
- `discovery.run.completed`

# CP Packet Skeleton Template

Use this structure for repo returns that require packetized execution evidence.

```text
FUNCTION_STATEMENT
EVIDENCE_REFERENCES
CHANGES_APPLIED
VERIFICATION_COMMANDS_RUN
ARTIFACTS_PRODUCED
RISKS_AND_NEXT_PASS
```

## CLI Generation

Generate a prefilled markdown skeleton from a research session brief:

```bash
python3 merlin_cli.py research packet <session_id> --phase CP4-A
```

Optional output path override:

```bash
python3 merlin_cli.py research packet <session_id> --output docs/research/<packet_name>.md
```

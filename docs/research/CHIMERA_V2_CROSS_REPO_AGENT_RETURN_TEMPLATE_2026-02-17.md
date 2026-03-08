# CHIMERA V2 Cross-Repo Agent Return Template (2026-02-17)

Use this exact response skeleton when returning from AAS parent, Hub, or parallel-consumer repos.

```text
FUNCTION_STATEMENT
- <one-line mission outcome>

EVIDENCE_REFERENCES
- <repo-relative file:line references>
- <repo-relative file:line references>

CHANGES_APPLIED
1. <concrete code/doc change>
2. <concrete code/doc change>

VERIFICATION_COMMANDS_RUN
1. `<exact command string>`
   - Outcome: PASS|FAIL
   - Result: `<exact summary output>`
2. `<exact command string>`
   - Outcome: PASS|FAIL
   - Result: `<exact summary output>`

ARTIFACTS_PRODUCED
- <artifact path>
- <artifact path>

RISKS_AND_NEXT_PASS
1. <residual risk>
2. <next concrete pass>
```

## Hard Requirements

- Include exact command strings (not paraphrases).
- Include pass/fail for each command.
- Include concrete artifact path(s).
- Keep scope strictly repo-local.

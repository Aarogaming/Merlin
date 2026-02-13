# Gate Governance Pointer

This repo follows the shared compatibility gate governance defined in the AAS superproject:

- Canonical policy: `docs/AAS_CONTROL_PLANE_ALIGNMENT.md` (AAS root)
- Section: `Gate Governance`

Current minimum gate command for `Merlin`:

```bash
python scripts/check_secret_hygiene.py --all && python -m mypy && python -m pytest
```

If this gate command, ownership, or review cadence changes, update both:

1. This pointer file (or local transition/protocol docs)
2. AAS compatibility matrix in `docs/AAS_CONTROL_PLANE_ALIGNMENT.md`

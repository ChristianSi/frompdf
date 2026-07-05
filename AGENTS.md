# Agent Notes

Read [CONTRIBUTING.md](CONTRIBUTING.md) before making changes.

Agent-specific caveats:

- Do not regenerate or overwrite files in `tests/pdf-corpus` unless the task
  explicitly calls for it. Use `/tmp` for quick conversion checks.
- Preserve unrelated user changes in the working tree.
- Keep heuristic changes narrow and verify them against at least the PDFs
  mentioned in the task.

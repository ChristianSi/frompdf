# Agent Notes

Read [CONTRIBUTING.md](CONTRIBUTING.md) before making changes.

Agent-specific caveats:

- Do not regenerate or overwrite files in `tests/pdf-corpus` unless the task
  explicitly calls for it. Use `/tmp` for quick conversion checks.
- The working tree may contain unrelated user changes. Preserve them unless
  the user explicitly asks you to modify or revert them.
- Keep heuristic changes narrow and verify them against at least the PDFs
  mentioned in the task.

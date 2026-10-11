# Plan: Extract application logic from `App` into focused modules

Spec: [`00-spec.md`](./00-spec.md)

## Goal

Decompose `browser/app.py` (605 lines / 36 methods) into focused modules, one task per module, each with
unit tests and immediate `App` adoption. `App` ends as the composition root plus a thin `AppActions`
adapter. The app must remain runnable and behaviorally identical after every task.

## Task index

| # | Task | Primary files | Depends on |
|---|------|---------------|------------|
| 01 | Extract OS launching into `browser/launcher.py` | `browser/launcher.py` (new), `browser/app.py`, `tests/browser/test_launcher.py` (new) | — |
| 02 | Extract `VideoLibrary` and `Trash` into `browser/library.py` | `browser/library.py` (new), `browser/app.py`, `tests/browser/test_library.py` (new) | 01 (merge order) |
| 03 | Extract sidecar metadata into `browser/metadata.py` | `browser/metadata.py` (new), `browser/app.py`, `browser/ui/actions.py` (re-export), `tests/browser/test_metadata.py` (new) | 02 (merge order) |
| 04 | Extract UI task runner into `browser/ui/tasks.py` | `browser/ui/tasks.py` (new), `browser/app.py`, `tests/browser/ui/test_tasks.py` (new) | 03 (merge order) |
| 05 | Extract selection/metadata session into `browser/session.py` | `browser/session.py` (new), `browser/app.py`, `tests/browser/test_session.py` (new) | 03, 04 (merge order) |
| 06 | Cleanup and final verification | `browser/app.py`, repo-wide | 01–05 |

## Status

| # | Task | Status | Notes |
|---|------|--------|-------|
| 01 | Launcher module | done | Commits `32b260e`, `5dc6813`; review approved; manual GUI smoke deferred to human |
| 02 | Library and trash | done | Commits `de50e76`, `b057131`; review approved; manual GUI smoke deferred to human |
| 03 | Metadata module | done | Commits `8f939aa`, `5921b60`; review approved; manual GUI smoke deferred to human |
| 04 | UI task runner | done | Commits `83606da`, `5c1282f`; review approved; manual GUI smoke deferred to human |
| 05 | Video session | done | Commits `3498629`, `906a6e1`; review approved; manual GUI smoke deferred to human |
| 06 | Cleanup and verification | done | Commits `4034d9f`, `08b164a`; automated verification green (110 tests, ruff clean, pyright 10 pre-existing, import ok); manual GUI smoke passed (user, 2026-10-10) |

Status values: `pending`, `in-progress`, `done`, `blocked`.

## Dependencies and execution notes

- The `Depends on` column is a **merge-order dependency**, chosen to avoid re-editing the same `App`
  methods twice and to keep `app.py` conflict-free. `01`, `02`, `03` and `04` have no hard code dependency
  on their predecessors, but only one task at a time may modify `browser/app.py`.
- Apply tasks in order. After each task, `browser/app.py` must import, start, and behave as before.
- `browser/ui/tasks.py` (task 04) is placed after the domain extractions so job bodies are already thin
  when the concurrency scaffolding is replaced (one dimension changed at a time).
- `browser/session.py` (task 05) is last because it composes `MetadataStore` with `UiState` and should
  mirror the final shape of `App`.
- Keep changes inside each task's declared scope. Do not opportunistically refactor widgets, `Config`,
  `PathTree`, `MagicSidecar`, or `util/*`.

## Global constraints

- Python tooling per `AGENTS.md`: `uv run ...`, `uv tool run ruff`, `uv tool run pyright`.
- Tk main-thread rule: only the Tk thread touches `UiState`, Tk variables, or widgets; worker code posts
  callbacks through the dispatcher.
- Keep behavior as-is except the complete delta list in `00-spec.md` ("Deliberate behavior deltas").
- No widget file changes (`browser/ui/*` widgets, `ui/*`), except the `BulkAction` re-export line in
  `browser/ui/actions.py` in task 03.

## Per-task workflow

1. Implementer picks the next `pending` task with dependencies merged.
2. Implement, run the task's verification commands, complete the task's manual smoke checklist.
3. Implementer sets the task status to `done` in the table above and records the result in the task file's
   `## Review` section (date + outcome).
4. A reviewer other than the implementer verifies acceptance criteria and the verification commands, and
   records the outcome in the task file.

## Final verification (task 06)

- `uv run pytest -q` — all tests pass.
- `uv tool run ruff check browser tests` — clean.
- `uv tool run pyright` — only the 10 pre-existing errors in `ui/message_system.py` and `ui/scrollable.py`.
- Full manual smoke checklist (task 06 file) passed.

## Post-plan remediation (audit findings, user-approved)

Full audit report and finding ledger: [`07-code-audit-findings.md`](./07-code-audit-findings.md).

A holistic code-auditor pass found 0 SEVERE and 2 MAJOR pre-existing concurrency issues plus one data-loss MINOR; all three were remediated after plan completion:

| Commit | Fix | Verification |
|---|---|---|
| `2a8f156` | Scope generated thumbnail metadata to the generating file (`VideoSession.apply_for`) | Reviewed, approved |
| `2d03647` | Count active/busy jobs before hiding status or clearing busy (`BackgroundJobs`) | Reviewed, approved |
| `9dde41a` | Avoid overwriting same-named entries in `.trash` (`Trash.send`) | Reviewed, approved |

Post-remediation head: 114 tests pass, `ruff check browser tests` clean, `pyright` at the 10 pre-existing errors, import smoke ok; code-reviewer approved the batch (2026-10-10). Remaining optional MINOR hardenings (not scheduled): fused `_finish` exception path could skip `hide` (try/finally), second collision-numbering test case, and tightening the overlap-test callback identity assertion.

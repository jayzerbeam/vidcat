# Plan: Extract application logic from `App` into focused modules

Spec: [`spec.md`](./spec.md)

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
| 01 | Launcher module | pending | |
| 02 | Library and trash | pending | |
| 03 | Metadata module | pending | |
| 04 | UI task runner | pending | |
| 05 | Video session | pending | |
| 06 | Cleanup and verification | pending | |

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
- Keep behavior as-is except the complete delta list in `spec.md` ("Deliberate behavior deltas").
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

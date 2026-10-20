# Task 02: Session restage on store-side metadata events (the fix)

## Overview

`VideoSession` owns the staged state (`_metadata` + the Tk variables) for the selected file but
never hears about store-side metadata writes, so any bulk operation on the selected file
(Add/Del actor/tag, bulk "Generate Thumbnails", "Clean") leaves the session stale and the next
Ctrl+S clobbers the just-persisted data. See `00-spec.md` for the verified root-cause flow.

This task wires the session into the store-side signal from task 01 and converges emission on
the new split: the session pushes its staged view via `selected_metadata_changed`; the
store-side `file_metadata_changed` stays producer-authoritative in `App`. The treeview keeps
its row-refresh behaviour by listening to both. This task also carries the minimal test-fixture
updates needed to keep `tests/browser/test_session.py` green (new tests come in task 03).

## Objective

A store-side `file_metadata_changed` event for the currently selected file fully restages
`VideoSession._metadata` and re-renders the pane; a store-side event for any other path is
ignored. Ctrl+S after a bulk edit persists the restaged state (no clobber). The exact-order
test log reflects the new signal name.

## Context

- `VideoSession.__init__` (`browser/session.py` ~28-33): today creates no signal connections.
- `save()` (~64-81): reads title/actors/tags out of the Tk variables into `_metadata`, calls
  `_show()`, then `self._store.write(path, self._metadata)`.
- `apply_for()` (~108-118): session-side merge for single-file thumb generation (Ctrl+G path);
  **not** part of this fix — it already scopes itself by path and must keep working unchanged.
- `_load()` (~120-133): reads the sidecar into `_metadata` on selection; `clear()` (~54-62)
  resets to `empty_metadata()`. Both go through `_show()`.
- `_show()` (~135-151): currently emits `file_metadata_changed` at ~136 with
  `self._selected_path or Path()` and the live `_metadata`, then seeds the Tk variables and
  emits `thumbnails_changed` / `bookmarks_changed`.
- `FileMetaTreeviewFrame.__init__` (`browser/ui/file_meta_treeview.py` ~127-132) connects
  `ctx.state.file_metadata_changed` to `_on_file_metadata` (~134-142), which calls
  `update_item_cols` — a pure, idempotent row render that emits nothing.
- Test fakes: `tests/browser/test_session.py` — `FakeSignal` (~25-35) has **no** `connect`
  method (the session never subscribed before) and `FakeState` (~38-53) lists the signals the
  session uses; the `session` fixture (~94-96) injects `split_list=lambda value:
  tuple(value.split(","))`. Several tests assert exact emission-order logs
  (`["file_metadata_changed", "thumbnails_changed", "bookmarks_changed", ...]`) at ~132, ~148,
  ~231, ~249, ~331.

## Scope

- Modify: `browser/session.py`, `browser/ui/file_meta_treeview.py`,
  `tests/browser/test_session.py` (fixture/log-assertion updates only — see below).
- Do not touch: `browser/app.py`, `browser/metadata.py`, `browser/ui/state.py` (beyond what
  task 01 already did), `ActorTagPane`/`EditableList`, `tests/browser/ui/*`, `vidcat.pyw`.

## Guidance

### `browser/session.py`

1. In `__init__`, after the existing assignments, connect the store-side signal:
   `self._state.file_metadata_changed.connect(self._on_stored_metadata)`.
2. Add the handler with semantics exactly as follows:
   - If `change.path != self._selected_path`, return. (This naturally covers the no-selection
     case: `_selected_path` is `None` and no payload path equals `None`.)
   - Otherwise replace staged state wholesale: `self._metadata = dict(change.metadata)`, then
     `self._show()`. No field-by-field merge, no identity guards.
   - Use a **shallow** copy only. Before committing, re-verify the invariant that makes this
     safe: (a) every store-side emitter passes a fresh dict it does not retain or mutate after
     emission (`store.read` unpickles per call; `empty_metadata()` deep-copies; the
     `refresh_files`/`aggregate_files`/`generate_files`/`edit_files` callbacks yield fresh
     dicts and drop them), and (b) session-side writers replace top-level keys only — `save()`
     assigns `title`/`actors`/`tags`, `apply_for` uses `|=`, bookmark helpers assign
     `metadata["bookmarks"]` (see `browser/metadata.py` `apply_bulk_edit` ~150-179,
     `insert_bookmark` ~219-227, `delete_bookmark` ~230-238). Nothing mutates nested lists in
     place. If your reading finds a violation, stop and raise it instead of switching to
     `deepcopy` unilaterally.
   - Docstring the handler with the pattern semantics: store-side events are authoritative for
     on-disk state; when the event targets the selected file, staged state is fully restaged
     and **unsaved buffer edits are discarded — reload from disk wins** (this is what makes
     "Clean" fully effective).
3. Change `_show()`'s first emission (~136) from `file_metadata_changed` to
   `selected_metadata_changed`; payload unchanged (`self._selected_path or Path()`,
   `self._metadata`). Document on `_show()` that it pushes the live staged view and that the
   re-entrancy rule from the `Signal` docstring is satisfied here: the session listens only to
   the store-side signal, never to the one it emits, and the treeview handler does not emit.
4. No changes to `save()`, `apply_for()`, `_load()`, `clear()`, bookmark methods, or imports
   (`FileMetadataChanged` is already imported).

### `browser/ui/file_meta_treeview.py`

5. One added line in the connection block (~127-132): connect the existing
   `_on_file_metadata` handler to `ctx.state.selected_metadata_changed` as well. Both signals
   carry the same tuple shape, so no handler changes. Note the accepted consequence: a
   store-side event for the selected path now renders the row twice (once from the store
   payload, once via the session restage) — idempotent and intentional.

### `tests/browser/test_session.py` (keep-green updates only)

6. Add to `FakeState`: `self.selected_metadata_changed = FakeSignal(log,
   "selected_metadata_changed")` next to the existing `file_metadata_changed` entry. Without
   this, `_show()` raises `AttributeError`.
7. Mechanically update the exact-order log assertions (~132, ~148, ~231, ~249, ~331) to expect
   `"selected_metadata_changed"` in place of `"file_metadata_changed"`. Nothing else in the
   file should change in this task; the behavioural tests are task 03.

## Acceptance criteria

- [ ] The session connects to `state.file_metadata_changed` in `__init__` and only there.
- [ ] `_on_stored_metadata` restages via full dict replace + `_show()` for a matching path, and
      is a no-op for any other path (including when nothing is selected).
- [ ] `_show()` emits `selected_metadata_changed`; the store-side signal is never emitted by the
      session (grep `browser/session.py` to confirm).
- [ ] The treeview is connected to both signals; `_on_file_metadata` itself is unchanged.
- [ ] Docstrings state: full-replace restage, "reload from disk wins", the shallow-copy
      invariant, and loop-safety (session never listens to its own emission).
- [ ] No new abstractions (no wrapper classes, no identity guards, no merge helpers); the
      production diff is on the order of 20 lines.
- [ ] Manual smoke (optional but recommended, `uv run python vidcat.pyw`): select a file, add an
      actor via the context menu, verify the pane updates, press Ctrl+S, reselect the file and
      verify the actor survived.

## Verification

```
uv run pytest
uv tool run ruff check browser/session.py browser/ui/file_meta_treeview.py tests/browser/test_session.py
uv tool run ruff format --check browser/session.py browser/ui/file_meta_treeview.py tests/browser/test_session.py
uv tool run pyright
```

## Review record

Code-reviewer verdict: **approved**, no findings. All acceptance criteria verified against the diff; all four verification commands pass (163 tests; pyright at the accepted 10 pre-existing-error baseline, none in touched files). One deviation adjudicated as justified and consistent with task 03: a record-only `FakeSignal.connect` was necessary because `VideoSession.__init__` now subscribes and the pre-diff fake had no `connect` (suite could not stay green without it); dispatch in `emit` remains task 03's scope. Shallow-copy invariant independently re-verified by the reviewer across all five store-side emitters and all session-side writers: no violation.

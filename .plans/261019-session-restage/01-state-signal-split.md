# Task 01: Split `file_metadata_changed` by producer (state-layer signals + contracts)

## Overview

`browser/ui/state.py` currently has a single `file_metadata_changed` signal carrying a
`FileMetadataChanged` NamedTuple. Two different producers emit it with different payload
liveness semantics:

- `VideoSession._show()` (`browser/session.py` ~136) emits it with the session's **live staged
  dict**, which `save()`/`apply_for()` mutate in place after emission.
- Five store-side flows in `browser/app.py` emit it with **fresh snapshot dicts** read from or
  written to the store: `scan_path_metadata` (~138), `delete_metadata` (~146),
  `generate_thumbnails_bulk` (~162), `edit_metadata` (~189), `scan_metadata` (~239). All of
  these are emitted on the Tk thread (worker callbacks are posted through `UiDispatcher`).

The single shared docstring (`FileMetadataChanged`, `state.py` ~44-53) only describes the
session-side liveness contract, which is about to become wrong for the store-side producers.
This task lays the state-layer groundwork for the session restage fix (task 02): one signal per
producer, with truthful contracts. **No producer or consumer behaviour changes in this task.**

## Objective

`UiState` exposes `selected_metadata_changed: Signal[FileMetadataChanged]` alongside
`file_metadata_changed`; the `Signal` docstring states the re-entrancy rule; each signal's
payload contract is documented where the signal is declared. Full test suite and type-check
pass with no behaviour change.

## Context

- `Signal` class: `state.py` ~13-28 — minimal typed observer, synchronous callbacks.
- `FileMetadataChanged` NamedTuple: `state.py` ~44-53 — `path: Path`,
  `metadata: Mapping[str, Any]`; `path` is `Path()` when no video is selected.
- Signal attribute assignments: `state.py` ~133-144 (`file_metadata_changed` at ~134).
- `FileMetadataChanged` is already imported by `session.py`, `app.py` and
  `file_meta_treeview.py`; nothing else needs to import it for this task.
- Docstring/comment style in this codebase: full sentences, precise about ownership, liveness
  and threading (see `FileTreeUpdate` ~31-37 and `BookmarksChanged` ~70-77 for the tone).

## Scope

- Modify: `browser/ui/state.py` only.
- Do not touch: `browser/session.py`, `browser/app.py`, `browser/ui/file_meta_treeview.py`,
  `browser/metadata.py`, any test file, or any UI widget.

## Guidance

1. In `UiState.__init__`, add
   `self.selected_metadata_changed = Signal[FileMetadataChanged]()` immediately adjacent to
   `self.file_metadata_changed` (~134). Attribute order: keep the new signal next to the one it
   replaces so the producer relationship is obvious to readers.
2. Document each signal's contract with a short comment above its assignment (this codebase
   documents attribute contracts with preceding inline comments, e.g. `app.py` ~72-73):
   - `file_metadata_changed`: emitted by store-side flows only (metadata edit/clean/scan/thumb
     generation in `App`); the payload metadata is a snapshot — every current emitter passes a
     fresh dict it never retains or mutates afterwards; consumers may read it synchronously.
   - `selected_metadata_changed`: emitted only by the session (`VideoSession._show()`) for the
     currently selected file's staged view; the payload metadata is the live `_metadata` dict,
     mutated in place by `save()`/`apply_for()` after emission — consume synchronously, never
     retain.
3. Rewrite the `FileMetadataChanged` NamedTuple docstring so it no longer claims a single
   liveness contract for all emitters: keep "path is Path() when no video is selected", state
   that the metadata liveness contract depends on the producing signal (live staged dict for
   `selected_metadata_changed`; fresh snapshot for `file_metadata_changed`), and point to the
   contract comments on the `UiState` attributes. Keep it short — the per-signal comments are
   the authoritative contracts.
4. Extend the `Signal` class docstring (~13-14) with one line stating the re-entrancy rule:
   handlers must not synchronously emit a signal that one of their own handlers consumes.

## Acceptance criteria

- [ ] `UiState` has `selected_metadata_changed: Signal[FileMetadataChanged]`; nothing emits or
      connects to it yet (that is tasks 02/03) — it is declaration-only in this task.
- [ ] `Signal` docstring contains the one-line re-entrancy rule.
- [ ] The `FileMetadataChanged` docstring no longer claims a single liveness contract; per-signal
      contracts appear as comments at the two attribute assignments in `UiState.__init__`.
- [ ] No imports, emitters, consumers, or tests changed.
- [ ] `uv tool run pyright` reports no new errors.

## Verification

```
uv run pytest
uv tool run ruff check browser/ui/state.py
uv tool run ruff format --check browser/ui/state.py
uv tool run pyright
```

## Review record

Code-reviewer verdict: **approved**, no findings (verification re-run fresh: 163 passed; ruff/format clean; pyright 10 pre-existing errors in untouched `ui/message_system.py`/`ui/scrollable.py`, none in `browser/ui/state.py`). All acceptance criteria verified, including declaration-only status of the new signal and scope (only `state.py` modified). Non-blocking note: the `file_metadata_changed` contract comment reads as store-side-only, which is momentarily ahead of the code until task 02 changes the session's emission.

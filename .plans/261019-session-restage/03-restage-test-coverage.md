# Task 03: Restage test coverage (FakeSignal upgrade + clobber-scenario regression tests)

## Overview

Task 02 made `VideoSession` restage staged state when a store-side
`file_metadata_changed` event targets the selected file. The current test fakes cannot
exercise that: `FakeSignal` (`tests/browser/test_session.py` ~25-35) has no `connect` method
(the session never subscribed before), so emissions never reach the session, and the fixture's
`split_list` only accepts comma strings, while a restaged pane holds structured list values.
This task upgrades the fakes and adds regression coverage for the three clobber scenarios plus
the restage contract edges.

## Objective

`FakeSignal` behaves like the real `Signal` for the two operations the session uses
(`connect`, `emit` invoking handlers synchronously), and six new tests pin the restage
behaviour, including the reported bug (bulk edit reverted by Ctrl+S), the bulk
thumbnail-generation variant, and the "Clean" variant.

## Context

- Real `Signal` (`browser/ui/state.py` ~13-28): `connect` appends; `emit` records and calls
  each callback synchronously, iterating over a tuple snapshot of the callback list.
- `FakeState` (~38-53) already exposes `selected_metadata_changed` (added in task 02).
- `session` fixture (~94-96) injects `split_list=lambda value: tuple(value.split(","))`.
  `save()` (~session.py:71-73) runs this over `state.meta_actors.get()`; after a restage that
  value is a **list** from the payload, so the fixture must pass structured values through.
- Payload-shape constraint: `_show()` reads `metadata["video_properties"]["dimensions"]` and
  `["duration"]` unconditionally, so every restage payload must contain `video_properties`.
  Build payloads from `empty_metadata()` (deep-copied, mutable) and override keys — same
  pattern as the `loaded_metadata` fixture (~100-107).
- Written `actors`/`tags` come back as **tuples** through the fixture's `split_list`
  (existing precedent: `test_save_writes_title_actors_tags_and_size_label` asserts
  `("alice", "bob")`).
- Private-access in tests is accepted in this codebase (e.g.
  `test_file_meta_treeview.py` uses `frame._shown_columns()`); reading `session._metadata` is
  fine where behaviour-through-the-UI is not observable.
- `tests/browser/ui/test_file_meta_treeview.py` uses a real `UiState` (`make_frame` ~47-50);
  the dual connection from task 02 needs no changes there — verified, leave the file alone.

## Scope

- Modify: `tests/browser/test_session.py` only.
- Do not touch: any production file, any other test file, test configuration.

## Guidance

1. Upgrade `FakeSignal` (~25-35):
   - Add a `handlers` list and a `connect` method that appends to it (record connections;
     the session's connection in `VideoSession.__init__` must land there).
   - In `emit`, after recording the emission and log entry, invoke each handler synchronously,
     iterating over `tuple(self.handlers)` (mirror the real `Signal`'s snapshot iteration).
     This is what makes restage behaviour testable: emitting on
     `state.file_metadata_changed` must reach `VideoSession._on_stored_metadata`.
   - Update the class docstring accordingly.
2. Make the `session` fixture's `split_list` tolerant of structured values, e.g. pass lists or
   tuples through as `tuple(value)` and only split comma strings otherwise. Rationale: the
   production `root.tk.splitlist` handles the widget's structured round-trip; the fake must not
   crash on list values seeded by a restage.
3. Add one test per scenario below (names indicative). All follow the existing style: arrange
   via `session.select((f,), triggered=f)` with a `store.results[...]` payload, act, assert on
   `state` vars / signal `.emissions` / `log` / `store.writes`.

   **(a) Restage on matching path** — select `f`, then
   `state.file_metadata_changed.emit(FileMetadataChanged(f, payload))` where `payload` is
   `empty_metadata()` with a different title/actors/tags/thumbnails and
   `video_properties` retained. Assert the pane re-seeded from the payload (title, actors,
   tags), `state.thumbnails_changed.emissions[-1]` is `ThumbnailsChanged` of the payload's
   thumbnails, `session._metadata` equals the payload, and `session._metadata is not payload`
   (fresh copy — pins the shallow-copy contract). Log order:
   `["file_metadata_changed", "selected_metadata_changed", "thumbnails_changed",
   "bookmarks_changed"]`.

   **(b) Ignore non-selected path** — select `f` with `loaded_metadata`, then emit for another
   path (a plain `Path` in `tmp_path`; it need not exist). Assert nothing restaged:
   `log == ["file_metadata_changed"]` only, no `selected_metadata_changed`/`thumbnails_changed`
   /`bookmarks_changed` emissions, `state.meta_title.value` still `"loaded"`, `session._metadata`
   unchanged.

   **(c) The reported bug** — select `f` (loaded metadata), emit a store-side payload whose
   actors/tags are bulk-edited (e.g. `["alice", "bob"]` / `["tag"]`), then `session.save()`.
   Assert the last `store.writes` entry persists the restaged values
   (`metadata["actors"] == ("alice", "bob")`) — i.e. Ctrl+S no longer reverts the bulk edit.

   **(d) Bulk thumbnail generation** — select `f` (loaded metadata with old thumbnails), emit a
   store-side payload with new `thumbnails` (e.g. `[(b"newjpg", 2, 20)]`), then `session.save()`.
   Assert `state.thumbnails_changed.emissions[-1]` carries the new thumbnails and the written
   `metadata["thumbnails"]` equals the new ones — generation is not clobbered.

   **(e) Clean** — select `f` (loaded metadata), emit
   `FileMetadataChanged(f, empty_metadata())` (mirrors `App.delete_metadata`), then
   `session.save()`. Assert the written metadata has empty title/actors/tags and empty
   thumbnails (tuples `()` for actors/tags per the split_list note above) — deleted metadata is
   not resurrected.

   **(f) No emission loop** — select `f`, emit one store-side event, then assert the log is
   exactly the four entries from scenario (a) and in particular
   `log.count("file_metadata_changed") == 1`: the restage handler must never re-emit the
   store-side signal. (With `FakeSignal` invoking handlers synchronously, a loop would recurse
   visibly; the exact-equality assertion catches any growth.)
4. Keep new tests free of Tk, `App`, and `MetadataStore` dependencies — the session-level fakes
   are sufficient and match the file's established approach.

## Acceptance criteria

- [ ] `FakeSignal.connect` records handlers and `emit` invokes them synchronously over a tuple
      snapshot; the docstring says so.
- [ ] The `session` fixture's `split_list` passes structured values through unchanged.
- [ ] Six new tests cover scenarios (a)-(f) and pass.
- [ ] Pre-existing tests, including the exact-order assertions updated in task 02 and the
      no-`_show()` pins (`test_add_bookmark_keeps_unsaved_entry_edits`,
      `test_remove_bookmark_stages_and_emits_reduced_list`), still pass unchanged.
- [ ] No production file modified (`git status` shows only `tests/browser/test_session.py`).

## Verification

```
uv run pytest tests/browser/test_session.py -ra
uv run pytest
uv tool run ruff check tests/browser/test_session.py
uv tool run ruff format --check tests/browser/test_session.py
uv tool run pyright
```

## Review record

Code-reviewer verdict: **approved**, no findings. All six tests verified body-by-body against scenarios (a)-(f), including the shallow-copy pin in (a) and the `log.count("file_metadata_changed") == 1` loop pin in (f); assertions confirmed live (vacuous-assertion check passed). FakeSignal dispatch verified to mirror the real `Signal` snapshot iteration, and only the six new tests emit on the store-side signal, so no pre-existing test is perturbed. Scope confirmed: task-03 hunks confined to `tests/browser/test_session.py`. Full suite: 169 passed; pyright at the accepted pre-existing baseline.

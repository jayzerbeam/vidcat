# Task 2: BookmarksChanged signal + staged session mutators + actions/App plumbing

## Objective

Selecting a file surfaces its stored bookmarks through a new typed signal, and the app
exposes stage-only `add_bookmark`/`remove_bookmark` actions that persist via the existing
Save flow.

## Context

- Signals are hand-rolled and typed: `Signal[T]` (`browser/ui/state.py:12-28`) with payload
  NamedTuples (`Thumbnail` :59, `ThumbnailsChanged` :65); `UiState.__init__`
  (`:107-129`) wires each signal.
- `VideoSession` (`browser/session.py:12`) owns `_metadata`; `_show()` (`:103-116`)
  emits `file_metadata_changed`, seeds the Tk vars, emits `thumbnails_changed` — and is
  called by `_load` (:100, *before* `selection_changed` :101), `clear` (:54), `save`
  (:67) and `apply_for` (:86).
- The mutators must **not** call `_show()`: `_show()` re-seeds `meta_title`/`meta_actors`/
  `meta_tags` from `_metadata` (`:108-110`) and would silently discard unsaved entry-widget
  edits. Stage-only semantics: `_metadata["bookmarks"]` is mutated in memory; the sidecar
  write happens only in `save()` (:57-74) which pickles the whole `_metadata`.
- `AppActions` Protocol at `browser/ui/actions.py:12-28`; `App` implements it
  structurally (`browser/app.py:63`) and delegates to `self._session` (e.g. `play_from_ms`
  :98-101, `save_metadata` :220-221).
- Test precedent: `tests/browser/test_session.py` duck-types state/store
  (`FakeVar`/`FakeSignal` log every emission into a shared ordered list, `FakeStore`
  logs `"write"`); ordered-log assertions exist at lines ~131, 147, 230, 248, 330 —
  `bookmarks_changed` is emitted by `_show()` right after `thumbnails_changed`, so those
  expectations change.
- The only other structural `AppActions` implementer is `StubActions` in
  `tests/browser/ui/test_file_meta_treeview.py:13-35`; pyright checks these tests, so the
  stub must grow the new methods **in the same change**.

## Scope

**Changed:** `browser/ui/state.py`, `browser/session.py`, `browser/ui/actions.py`,
`browser/app.py`, `tests/browser/test_session.py`,
`tests/browser/ui/test_file_meta_treeview.py`.
**Out of scope:** every widget (`browser/ui/scrub_frame.py`, new `bookmark_frame.py`),
no subscription/workers/launcher changes, no `save()`/`_load()` logic changes beyond the
one `_show()` emission.

## Guidance

- `browser/ui/state.py`: add `BookmarksChanged(NamedTuple)` with `path: Path` and
  `bookmarks: tuple[Bookmark, ...]`; import `Bookmark` from `browser.metadata`
  (same direction as `browser/ui/actions.py:7` importing `BulkAction` — no import cycle).
  Give it a concise docstring stating that `path` is `Path()` when nothing is selected and
  that `_show()` fires before `selection_changed`, so consumers should cache
  `(path, bookmarks)`. Register `self.bookmarks_changed = Signal[BookmarksChanged]()`
  in `UiState.__init__` alongside its siblings (near `thumbnails_changed`, :123).
- `browser/session.py`: extend the `.ui.state` import (`:9`) with `BookmarksChanged` and the
  `.metadata` import (`:8`) with `parse_bookmarks` (plus `Bookmark` if used for typing).
- `_show()`: after the `thumbnails_changed` emit (:114-116), emit
  `BookmarksChanged(self._selected_path or Path(), parse_bookmarks(self._metadata))` —
  same `path` expression as the `file_metadata_changed` line :104; `parse_bookmarks` makes
  legacy sidecars harmless.
- `add_bookmark(time_ms: int, frame_no: int | None, name: str) -> bool`:
  - no selection (`_selected_path is None`) → `False`;
  - build `Bookmark(...)` and call `insert_bookmark(self._metadata, ...)`; on `False`
    return `False` (duplicate, no emission);
  - on `True`: emit `BookmarksChanged(self._selected_path, parse_bookmarks(self._metadata))`
    directly and return `True`. **Never call `_show()`**; document the reason in the
    docstring (it would discard unsaved title/actor/tag entry edits).
- `remove_bookmark(time_ms: int) -> None`: same guards; use `delete_bookmark`; emit only
  when an entry was removed.
- `browser/ui/actions.py`: add the two protocol methods (after `save_metadata`, :17).
- `browser/app.py`: implement both, delegating to `self._session` (near `save_metadata`,
  :220-221); no extra imports needed.
- `tests/browser/test_session.py`:
  - `FakeState` gains `self.bookmarks_changed = FakeSignal(log, "bookmarks_changed")`
    (after `thumbnails_changed`, :52);
  - update the five ordered-log assertions so `"bookmarks_changed"` follows
    `"thumbnails_changed"`: :131 → `["file_metadata_changed", "thumbnails_changed",
    "bookmarks_changed", "selection_changed"]`; :147 → the same; :230 →
    `["file_metadata_changed", "thumbnails_changed", "bookmarks_changed", "write"]`;
    :248 → `["file_metadata_changed", "thumbnails_changed", "bookmarks_changed"]`;
    :330 → same as :131;
  - new tests: staged add emits `bookmarks_changed` with the right
    `BookmarksChanged(path, (Bookmark(...),))` payload and the log contains **no** `"write"`;
    duplicate add returns `False` with no emission; add after editing
    `state.meta_title.value` leaves that value intact (`log` must not contain
    `file_metadata_changed` — pins the no-`_show()` decision); save-after-add writes
    `metadata["bookmarks"]` equal to the plain-dict list; seed a sidecar metadata with
    stored bookmark plain dicts and assert the `_show()` payload parses them
    (`BookmarksChanged((f,), (Bookmark(5000, 125, "intro"),))`-shaped).

## Acceptance criteria

- [ ] `BookmarksChanged` NamedTuple + `UiState.bookmarks_changed` exist and are typed.
- [ ] `_show()` emits `bookmarks_changed` after `thumbnails_changed`, with
      `path = _selected_path or Path()` and bookmarks parsed (missing key tolerated).
- [ ] `select` on a sidecar containing stored bookmark plain dicts produces a
      `BookmarksChanged` payload of `Bookmark` tuples; legacy metadata without the key
      produces `()`.
- [ ] `add_bookmark` stages into `_metadata`, emits the payload with the new bookmark,
      returns `True`, and no `store.write` occurs; duplicate returns `False`, no emission.
- [ ] `remove_bookmark` stages the removal and emits the reduced payload; missing
      `time_ms` emits nothing.
- [ ] None of the mutators call `_show()`: an edited `meta_title` survives
      `add_bookmark`/`remove_bookmark`, and `file_metadata_changed` is not emitted by them.
- [ ] `save()` after staged adds writes a metadata dict whose `bookmarks` are plain dicts
      (asserted via `FakeStore.writes`).
- [ ] `App.add_bookmark`/`App.remove_bookmark` delegate to the session; the `AppActions`
      protocol has both methods; `StubActions` in `test_file_meta_treeview.py` implements
      both (pyright-clean).
- [ ] All ordered-log expectations updated as listed above; same-order assertions still
      hold for the unchanged flows (clear/apply_for).

## Verification

```
uv run pytest tests/browser/test_session.py tests/browser/test_metadata.py tests/browser/ui/test_file_meta_treeview.py
uv tool run ruff check browser/ui/state.py browser/session.py browser/ui/actions.py browser/app.py tests/browser/test_session.py tests/browser/ui/test_file_meta_treeview.py
uv tool run pyright browser/ui/state.py browser/session.py browser/ui/actions.py browser/app.py tests/browser/test_session.py tests/browser/ui/test_file_meta_treeview.py
```

# Spec: Timeline bookmarks for the ScrubFrame tab

## What and why

The Scrub tab (`browser/ui/scrub_frame.py`) lets the user inspect a selected video frame by
frame, but positions of interest have to be remembered by hand. This feature adds **timeline
bookmarks**: at any seek-bar position the user can add a named (or unnamed) bookmark storing the
position (`time_ms`) and frame number. Bookmarks appear in a list beside the video:

- **Single-click** a bookmark → the seek bar moves to it and that frame is rendered.
  Clicking it again is a no-op while the position is already there, but re-seeks when the
  seek bar has since moved away;
- **Delete** key → removes the selected bookmark;
- playback from a bookmark is the existing **Open** button: single-click, then Open plays
  from that position (no bookmark-specific playback binding).

Bookmarks live in the per-video metadata sidecar (pickled dict in an NTFS alternate data
stream, `browser/metadata.py` `MetadataStore`) inside the top-level `"bookmarks"` key, so they
survive restarts like tags/title/thumbnails.

## Storage schema (decision 1)

Top-level metadata key `"bookmarks"`: a **list of plain dicts sorted by `time_ms`**:

```python
{"time_ms": int, "frame_no": int | None, "name": str}
```

- `time_ms` (int, milliseconds from file start) is **authoritative and the unique identity**;
  `frame_no` is `round(seconds * fps)` at add time, `None` when the frame rate is unknown;
  `name` is `""` when unnamed.
- A duplicate `time_ms` is rejected **at add time** (time is the identity).
- `"bookmarks": []` is added to `EMPTY_METADATA` (`browser/metadata.py:13`).
- Reads must **tolerate** legacy sidecars without the key, missing/invalid types inside
  entries, and non-dict entries (skip malformed entries). The external tools writing
  sidecars (`globtag.py:33-40` inline default dict, `thumbnailer.py`) keep their current
  defaults: readers are tolerant, writers need no change (their untouched reload/rewrite
  round-trips preserve the key).
- **Plain dicts** (not NamedTuples) are what gets pickled, so external tools never need app
  classes to consume sidecars.

## Typed view + pure helpers in `browser/metadata.py` (decision 2)

- `Bookmark` NamedTuple with field order `time_ms, frame_no, name`.
- `parse_bookmarks(metadata) -> tuple[Bookmark, ...]` — tolerant read described above,
  returned sorted by `time_ms`.
- `insert_bookmark(metadata, bookmark) -> bool` — sorted insert; rejects an existing
  `time_ms`; stores a plain dict.
- `delete_bookmark(metadata, time_ms) -> bool` — removes the matching entry; reports success.
- Style follows `apply_bulk_edit` (`browser/metadata.py:138-167`): pure functions over the
  metadata dict in place, returning whether anything changed.

## Staged persistence (decision 3 — user decision)

`VideoSession.add_bookmark(time_ms, frame_no, name) -> bool` and
`VideoSession.remove_bookmark(time_ms) -> None` mutate `_metadata["bookmarks"]` **in memory
only** and do **not** write the sidecar. Persistence goes through the existing Save button /
Ctrl+S (`App.save_metadata` → `session.save()`), which already pickles the whole
`_metadata`. Consequences (accepted):

- The mutators must **not** call `_show()`: `_show()` re-seeds the Title/Actors/Tags entry
  widgets from `_metadata` (`browser/session.py:108-110`), which would discard unsaved text
  edits. Instead the mutators emit the bookmark signal directly.
- `meta_size` stays stale until Save — correct, the sidecar is unchanged.
- **Unsaved bookmarks are lost when switching files**, exactly like unsaved title/tag edits.
  This is accepted and must not be "fixed" ad hoc.

## New signal (decision 4)

`BookmarksChanged(path: Path, bookmarks: tuple[Bookmark, ...])` in `browser/ui/state.py`,
exposed as `UiState.bookmarks_changed` (typed `Signal[T]`, same hand-rolled pattern as the
others at `browser/ui/state.py:12-99`). Emitted from:

1. `VideoSession._show()` — after `thumbnails_changed` (so load/clear/save/apply_for all
   refresh the bookmark view); `path` is `self._selected_path or Path()`, mirroring the
   `FileMetadataChanged` emission at `browser/session.py:104`.
2. `VideoSession.add_bookmark` / `remove_bookmark` (the staged mutators).

Rationale for a dedicated signal instead of reusing raw `file_metadata_changed`: the bulk
paths (generate / refresh / clean / scan metadata in `browser/app.py:136-146,162,189,233`) emit
`file_metadata_changed` with **on-disk** state. Rendering bookmarks from those payloads would
make staged (not-yet-saved) bookmarks visually vanish even though the session still holds
them. `BookmarksChanged` is emitted only for session-visible state, so staged and persisted
bookmarks stay consistent. The payload carries an immutable tuple of `Bookmark`s (unlike
`FileMetadataChanged.metadata`, a live session-owned dict — see its docstring in
`browser/ui/state.py:43-49`), so consumers may cache it.

The `path` is included so consumers can cache `(path, bookmarks)`: on selection change
`VideoSession._load` (`browser/session.py:88-101`) calls `_show()` **before** emitting
`selection_changed`, so a bookmark consumer must render its cached tuple when it later learns
its own path.

## Actions / App plumbing (decision 5)

- `AppActions` (`browser/ui/actions.py:12-28`) gains:
  `add_bookmark(time_ms: int, frame_no: int | None, name: str) -> bool` and
  `remove_bookmark(time_ms: int) -> None`.
- `App` (`browser/app.py`) delegates both to the session. No modal input dialog — the name
  comes from the bookmark pane's entry field.
- `tests/browser/ui/test_file_meta_treeview.py` `StubActions` (structural
  implementation of the whole protocol) must grow the two methods in the same change.

## ScrubFrame layout (decision 6)

Replace the direct canvas grid (`browser/ui/scrub_frame.py:73-82`) with a horizontal
`ttk.PanedWindow` at row 0, col 0, columnspan 2, sticky NSEW:

- **left pane** = the existing video canvas, added with `weight=1` (unchanged widget);
- **right pane** = new `BookmarkFrame` added with `weight=0`, requesting **width 200**
  (matches the `ActorTagPane(pane, ctx, orient=VERTICAL, width=200)` pattern in
  `browser/ui/video_info_frame.py:34-57`).

Seek row 1 and controls row 2 stay exactly as they are; all existing worker/seek code is
untouched.

**Paned-width mechanism (verified empirically on this dev machine, 2026-10-15):** a plain
`ttk.Frame(width=200)` that *grids children* requests only the children's combined width
(172 px here) — the `width` option is ignored while grid propagation is on, and the pane
then took the treeview's width. Calling `grid_propagate(False)` on the frame restores honor
for the `width` option: requested width became exactly 200, the pane was allocated 200 px at
init and kept 200 px across a window resize while the video pane absorbed all extra width
(video 995→1395 px, bookmark pane constant 200). Precedent for `grid_propagate(False)` in
this repo: `browser/ui/file_meta_treeview.py:63-64`. Measured with the planned hierarchy:
`BookmarkFrame(width=200)` containing a `ScrollableWidgetFrame(Treeview)` with columns
80+90 px + vertical scrollbar + entry + button.

## New widget `BookmarkFrame` (decision 7)

New file `browser/ui/bookmark_frame.py` (per-frame-per-file convention). A **dumb widget**:
no `UiContext`, no metadata knowledge; imports `Bookmark` from `browser.metadata` and
`clock_format` from `util.format`. Nested `__Widgets` NamedTuple pattern
(`browser/ui/scrub_frame.py:27-33`, `ui/better_widgets.py`).

Hierarchy:

- row 0 (row weight 1): `ScrollableWidgetFrame` (`ui/scrollable.py:9`) with
  `child_type=ttk.Treeview`, `xscrollable=False`;
- row 1: `ttk.Entry` (name input);
- row 2: `ttk.Button` labelled "Bookmark".

Do **not** use `ScrollableTreeviewFrame`/`SortableTreeview` (`ui/better_treeview.py`) —
heading-click sort is unwanted.

Treeview: `show="headings"`, `columns=("time", "name")` (implicit `#0` hidden), headings
"Time"/"Name", `selectmode=tk.BROWSE`; column #1 Time width ≈80 / minwidth ≈40 / stretch
False; column #2 Name width ≈90 / minwidth ≈40 / stretch True (totals ≈200 with the
scrollbar).

Rows: `iid = str(time_ms)` (unique thanks to add-time dedupe; maps clicks / Delete
straight to the bookmark), values = (`clock_format(time_ms / 1000, decimals=3)`, name),
inserted in time order. `frame_no` is **stored but not displayed**
(user specified two columns: timestamp, optional name). Re-render = delete all children then
re-insert; **never** call `selection_set` programmatically (avoids spurious
`<<TreeviewSelect>>`). A re-render fires `<<TreeviewSelect>>` with an *empty* selection
(verified: Tk fires it twice on delete-all) — handlers must no-op on empty selection.

Interactions:

- `<Button-1>` → seek handler with the row resolved via `identify_row(event.y)`, skipping
  heading/separator regions and empty rows (precedent: `FileTreeviewFrame._handle_click`,
  `ui/better_treeview.py:109-110`). This is the primary single-click path: it also fires
  when the clicked row is already selected, where `<<TreeviewSelect>>` does not. The widget
  always forwards the click; whether a click is redundant is decided by the ScrubFrame
  handler (decision 8), not here;
- `<<TreeviewSelect>>` → seek handler as well, for keyboard navigation; a mouse click may
  fire this in addition to the click path — same target time, harmless;
- `<Delete>` (treeview) → remove handler;
- entry `<Return>` and button → add handler with the **stripped** entry text; blank = unnamed;
  the entry is cleared **only when the add handler returns True** (duplicate rejected → text
  kept).

API mirroring `ImagesFrame`/`EditableList` (`ui/better_frames.py:76`, `ui/better_widgets.py:47-141`):

- constructor `(parent, *, width: int = 200, ...)` — `width` passes through as the frame
  width (with `grid_propagate(False)` per the verified mechanism above);
- `set_bookmarks(bookmarks: Sequence[Bookmark])`, `set_enabled(enabled: bool)` (treeview
  selectmode `"browse"`/`"none"` plus entry/button `.state(["disabled"/"!disabled"])`);
- `set_add_handler(Callable[[str], bool])`, `set_seek_handler(Callable[[Bookmark], None])`,
  `set_remove_handler(Callable[[Bookmark], None])`.

## ScrubFrame wiring (decision 8)

- Connect `ctx.state.bookmarks_changed`; keep a `(path, tuple[Bookmark, ...])` cache.
- `_render_bookmarks()` renders the cache when its path equals `self._path`, else clears the
  list; called from `load()` and on signal receipt. The enable/disable flips in
  `load()`/`clear()`/`_apply_loaded` also flip `BookmarkFrame.set_enabled` (the same places
  that flip seek/open, `browser/ui/scrub_frame.py:108-109,121-122,206-207`).
- Extract `_current_ms()` from `_handle_open` (`browser/ui/scrub_frame.py:229-233`, same
  math) and add `_seek_to_ms(ms)` that clamps the fraction into [0, 1] and calls
  `self._widgets.seek.set(...)`. Programmatic `set` fires the Scale command (verified) →
  the existing debounced `_handle_seek` (`browser/ui/scrub_frame.py:235`) updates the
  label and enqueues the frame SEEK. So single-click on a bookmark moves the seek bar,
  updates the time/frame label, and renders that frame — reusing the full worker path.
- Handlers: seek → `_seek_to_ms(b.time_ms)` unless `_current_ms()` already equals
  `b.time_ms` (a click while already at the bookmark is a no-op; a click after scrubbing
  away re-seeks); remove → `ctx.actions.remove_bookmark(b.time_ms)`; add(name) → compute
  ms via `_current_ms()`,
  `frame_no = round(ms / 1000 * _frame_rate)` when `_frame_rate` is known else `None`,
  and return `ctx.actions.add_bookmark(ms, frame_no, name)` (False propagates to keep the
  entry text).

## Test plan (decision 9)

- `tests/browser/test_metadata.py`: `empty_metadata()` includes `"bookmarks": []`;
  `parse_bookmarks` tolerance (missing key, malformed entries, non-dicts) and ordering;
  `insert_bookmark` sorted insert / duplicate rejected / plain dict stored;
  `delete_bookmark` found vs missing.
- `tests/browser/test_session.py`: `FakeState`/fakes gain `bookmarks_changed`; staged
  add/remove emits `bookmarks_changed` and does **not** log `"write"`; duplicate add returns
  False without emission; add preserves an edited-but-unsaved `meta_title` (pins the
  no-`_show()` decision); save-after-add writes a metadata dict containing the plain bookmark
  dicts; update the existing ordered-log expectations (lines ~131, 147, 230, 248, 330) because
  `_show()` now also emits `bookmarks_changed`.
- New `tests/browser/ui/test_bookmark_frame.py` with a real `tk.Tk()` root (pattern of
  `tests/browser/ui/test_file_meta_treeview.py`): rows in order with `iid=str(time_ms)` and
  correct column values; add via button invokes the handler with the entry text and clears
  the entry only on True; `<Return>` also adds; Delete invokes remove with the right
  bookmark; a row click (and a selection change, e.g. for keyboard navigation) invokes the
  seek handler, including a re-click of the already-selected row; disabled state blocks
  interaction.
- `tests/browser/ui/test_file_meta_treeview.py`: `StubActions` additions.

## Out of scope

- Renaming/editing names after add.
- Double-click or any other bookmark-specific playback binding — playback from a bookmark
  is single-click + the existing Open button.
- Bookmark markers/ticks on the seek scale.
- Sorting columns (explicitly no `SortableTreeview`).
- Bulk bookmark operations from the file tree.
- Displaying bookmarks in `VideoInfoFrame` or anywhere else.
- Schema defaults in `thumbnailer.py`/`globtag.py` (readers are tolerant; `globtag.py`'s
  inline default dict stays as-is).
- Any changes to the video worker, `VideoReader`, `Launcher`, or external player behavior.
- Persistence of unsaved bookmarks across file switches (accepted consequence of staged
  persistence).

## Risks / open questions

- **Staged bookmarks lost on file switch** without Save — same accepted behavior as unsaved
  title/tags (decision 3).
- **Duplicate `time_ms` from an externally edited sidecar** would collide on treeview iid
  when rendered. Add-time injection rejects duplicates, but storage is tolerant by design:
  `parse_bookmarks`/the widget must not crash on duplicates — the widget should skip a row
  whose `str(time_ms)` iid is already present (or parse may dedupe, keeping the first).
- **ScrubFrame has no existing test coverage** (worker threads + real video decoding make it
  heavy). The plan covers metadata/session/widget layers with automated tests and treats the
  ScrubFrame integration as manually verified (see task 4).
- **Re-render selection noise:** `<<TreeviewSelect>>` fires with an empty selection when rows
  are deleted (verified: twice per delete-all). Handlers must guard against empty selection;
  programmatic `selection_set` must never be used by the widget.
- **ttk.Frame width propagation:** without `grid_propagate(False)` the 200 px-pane target
  is silently ignored (children win) — verified; mechanism specified in decision 6.
- `clock_format` returns `None` on overflow (`util/format.py:22-27`); the widget should
  render an empty string in that (theoretical) case instead of crashing Tk item insertion.

# Task 4: ScrubFrame PanedWindow integration + bookmark wiring + `.plan` TODO removal

## Objective

The Scrub tab shows a bookmark sidebar beside the video: listing per selected file's
bookmarks, single-click seeks+renders the frame (the existing Open button then plays from
that position), Delete removes, entry+button adds at the current position.

## Context

- `browser/ui/scrub_frame.py` is the integration target. Current facts (line refs):
  layout grid `:73-82` (canvas row 0 colspan 2, seek row 1, controls row 2 with Open
  button + position label); `__Widgets` NamedTuple `:27-33`; `load()` `:98-113` and
  `clear()` `:115-131` disable seek+open; `_apply_loaded()` `:197-209` enables them when
  `duration > 0`; `_handle_open()` `:229-233` computes
  `ms = round(float(seek.get()) * _duration_ms)` then `play_from_ms`; `_handle_seek`
  `:235-247` is `@tk_debounce(50, leading=True)`, guards `path is None`/`duration <= 0`
  and enqueues SEEK (updates the time/frame label via `_update_time_label`, :217-227);
  `_frame_rate` may be `None`; `_update_time_label` applies
  `round(time_s * _frame_rate)` — the same math the add-handler uses for `frame_no`.
- PanedWindow/side-pane precedent: `browser/ui/video_info_frame.py:34-57` (horizontal
  `ttk.PanedWindow`, side pane is a `ttk.PanedWindow(..., width=200)`-style narrow child
  whose requested width stays 200). For `BookmarkFrame` the width mechanism is the
  widget's own `width=200` + `grid_propagate(False)` (widget-internal; empirically
  verified — see task 3 and spec). Sidebar children must not request much more than 200.
- Signal/message pieces from earlier tasks: `UiState.bookmarks_changed`
  (`ctx.state.bookmarks_changed`), `AppActions.add_bookmark/remove_bookmark`
  (`ctx.actions`), `BookmarkFrame` with `set_bookmarks/set_enabled/set_*_handler`.
- `_show()` fires **before** `selection_changed` (`browser/session.py:100-101`), so
  `bookmarks_changed` arrives *before* `load()` runs during a selection switch → cache
  `(path, bookmarks)` in this frame and render the cache when `_path` is known.
- Programmatic `ttk.Scale.set()` fires the Scale command → the debounced `_handle_seek`
  runs the normal path (verified).
- Repo-root `.plan` line 3 is `- add hotspot/bookmarks for scrub frame` — removed by this
  task (the other two lines: `:1` status-bar move, `:2` filters-sort bug, are NOT ours).

## Scope

**Changed:** `browser/ui/scrub_frame.py`, root `.plan` file.
**Out of scope:** the worker loop, request queues, `_ScrubRequest`, `VideoReader`,
`util/video.py`, `Launcher`, `browser/app.py`, `browser/session.py`, the new widget's
internals, `video_info_frame.py`, metadata schema (tasks 1–3 own those), and any
bookmark-specific playback binding (playback stays the existing Open button +
`play_from_ms`).

## Guidance

- Layout: create `ttk.PanedWindow(self, orient=tk.HORIZONTAL)`; grid it exactly where the
  canvas was: `column=0, row=0, columnspan=2, padx=(4, 4), sticky="NSEW"`. Add the
  existing `self._widgets.video` canvas as the first pane (`weight=1`) and the
  `BookmarkFrame` as the right pane (`weight=0`) — nothing else about the canvas changes
  (its `<Configure>` redraw binding, `_handle_video_configure`, stays). Seek row 1 and
  controls row 2 keep their current grids.
- `__Widgets` gains the `BookmarkFrame` (needed for `set_enabled`/`set_bookmarks` from
  several methods); the PanedWindow itself may stay local, mirroring `ctrlfrm` being
  local-then-registered.
- Constructor wiring: `set_add_handler(self._handle_bookmark_add)`,
  `set_seek_handler(self._handle_bookmark_seek)`,
  `set_remove_handler(self._handle_bookmark_remove)`, then
  `ctx.state.bookmarks_changed.connect(self._handle_bookmarks_changed)`.
- New fields: `_bookmarks_path: Path | None` and `_bookmarks: tuple[Bookmark, ...]`
  (initialized empty in `__init__` next to `_path`).
- `_handle_bookmarks_changed(change)`: store `(change.path, change.bookmarks)`; render
  when `change.path == self._path`.
- `_render_bookmarks()`: feed the cache (`set_bookmarks`) when the cached path equals
  `self._path`, else `set_bookmarks(())` — covers load (cache pre-populated by the
  pre-`selection_changed` emission), clear (`_path is None`), and same-file refresh.
- Enable/disable flips: in `load()` and `clear()` immediately after the seek/open
  disable lines call `self._widgets.bookmarks.set_enabled(False)`; in `_apply_loaded`
  inside the `duration > 0` success branch call `set_enabled(True)` next to the
  seek/open enabling. Call `_render_bookmarks()` from `load()` and `clear()` too.
- Extract `_current_ms() -> int | None` from `_handle_open` (same math, same guards
  returning `None`); `_handle_open` becomes a thin guard + delegate. `_seek_to_ms(ms)`
  guards the same conditions, computes the fraction and clamps it into `[0.0, 1.0]`
  before `self._widgets.seek.set(fraction)` — the Scale command then drives label
  update + frame rendering through the existing SEEK machinery.
- Handlers:
  - seek: if `_current_ms()` is not `None` and equals `b.time_ms`, return (the click is
    redundant — the position is already at the bookmark); otherwise `_seek_to_ms(b.time_ms)`;
  - remove: `self._ctx.actions.remove_bookmark(b.time_ms)`;
  - add: `_current_ms()` → `None` means `False`; `frame_no = round(ms / 1000 *
    self._frame_rate)` only when `self._frame_rate is not None`, else `None`; return
    `self._ctx.actions.add_bookmark(ms, frame_no, name)` (the widget keeps the entry text
    on `False`, e.g. duplicate at the current position).
- Remove `- add hotspot/bookmarks for scrub frame` from the repo-root `.plan`
  (leave the first two lines untouched).

## Acceptance criteria

- [ ] Row 0 is a horizontal `ttk.PanedWindow` (video pane `weight=1`,
      `BookmarkFrame` pane `weight=0`, right pane ≈200 px; video absorbs resizes); seek
      and controls rows unchanged.
- [ ] Bookmarks of the selected file render in the sidebar; switching files rerenders via
      the cache (bookmarks signal precedes selection change), clearing when no file.
      Same-file bookmark add/remove refresh the list through the signal.
- [ ] `set_enabled` tracks the same lifecycle points as seek/open: disabled on
      `load()`/`clear()`, enabled once `_apply_loaded` gets a positive duration.
- [ ] Single-click on a row moves the seek bar, updates the time label (`clock_format`
      with 3 decimals plus `frame N`), and renders the bookmark's frame
      (`_seek_to_ms` → Scale command → debounced `_handle_seek`); after scrubbing away,
      clicking the still-selected bookmark returns to it; clicking when the position
      already equals the bookmark's `time_ms` is a no-op (early return).
- [ ] Delete removes the selected bookmark (signal round-trip refreshes the list).
- [ ] Button/`<Return>` add a bookmark at the current position with the entry name,
      `frame_no` derived from `_frame_rate` when known; duplicate position keeps the
      entry text (returns `False`).
- [ ] `_handle_open` still opens at the seek-bar position; `_current_ms()` is the shared
      implementation; no worker/queue/reader logic modified.
- [ ] `.plan` no longer contains the bookmarks line; other lines intact.

## Verification

```
uv run pytest
uv tool run ruff check browser/ui/scrub_frame.py
uv tool run pyright browser/ui/scrub_frame.py
```

Manual smoke test (~5 min, real video from the library; launch with `uv run python vidcat.pyw`,
close the window when done):

1. Select a video and open the **Scrub** tab; scrub somewhere and add a bookmark with a
   name, then move and add a second unnamed bookmark at another position.
2. Single-click each bookmark: seek bar, `…ms` clock + `frame N` label, and the rendered
   frame must track the bookmark. Scrub away, then click the already-selected bookmark
   again: the seek bar returns to it. Click it once more without moving anything: nothing
   changes. Press **Open**: the external player starts at that time (now the only playback
   path for bookmarks).
3. Edit the Title entry, do **not** save, then add another bookmark: the Title text must
   stay untouched in the entry field (no `_show()`).
4. Press Ctrl+S: `metadata size` label updates and the sidecar holds the bookmarks
   (reopen/reselect the file → bookmarks still listed, from disk).
5. Unsaved-bookmark loss: add a bookmark, switch to another file without Ctrl+S, come
   back → the staged bookmark is gone (accepted behavior).
6. Drag the pane sash between video and sidebar; resize the window: video stretches,
   sidebar stays ~200 px.

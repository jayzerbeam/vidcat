# Task 3: `BookmarkFrame` widget + tests

## Objective

A self-contained, dumb bookmark list widget exists in `browser/ui/bookmark_frame.py`,
behaving exactly as specified (render/enable/add/seek/remove), with behavior-level
tests.

## Context

- Generic scrollable wrapper: `ScrollableWidgetFrame` (`ui/scrollable.py:9-58`) — a Frame
  wrapping any `tk.Canvas | ttk.Treeview | tk.Entry | tk.Listbox` with optional scrollbars
  and mousewheel; configure the inner widget through its `.child` property.
- Per-frame-per-file convention of this repo; dumb sibling widgets that take record-and-
  forward handlers rather than a `UiContext`: `ImagesFrame.set_image_click_handler`
  (`ui/better_frames.py:76`) and `EditableList` (`ui/better_widgets.py:55-143`, incl.
  entry `<Return>` → add, `<Delete>` on the list, clear-on-success entry handling).
- Nested `__Widgets` NamedTuple pattern + `self._widgets = __class__.__Widgets(...)`
  (`browser/ui/scrub_frame.py:27-33`, `browser/ui/video_info_frame.py`).
- Row-click/select precedent: `FileTreeviewFrame` (`ui/better_treeview.py:105-122`) binds
  `<Button-1>` to record `identify_row(ev.y)` and `<<TreeviewSelect>>` for the selection;
  its region guard (`identify("region", ev.x, ev.y)`, `:113`) shows the heading-region
  skip pattern.
- Frame width must not be overridden by gridded children: `grid_propagate(False)`
  precedent at `browser/ui/file_meta_treeview.py:63-64`. **Verified empirically**
  (2026-10-15): `ttk.Frame(width=200)` whose children are gridded requests only the
  children's width (~172/189 px) — the `width` option loses; with
  `grid_propagate(False)` the requested width is exactly 200, a parent
  `ttk.PanedWindow` allocates the pane at 200 px at init and on resize, and the sibling
  video pane absorbs the remainder.
- Tk behaviors verified empirically: `ttk.Scale.set()` fires its `command` callback; a
  treeview `<<TreeviewSelect>>` fires **twice with empty selection** after deleting all
  rows (any re-render must no-op on empty selection).
- Widget test harness: `tests/browser/ui/test_file_meta_treeview.py:38-48` (real
  `tk.Tk()` root fixture, `yield window; window.destroy()`).
- `Bookmark` and `clock_format`: `browser/metadata.py` (task 1) and
  `util/format.py:22-36` (`clock_format(seconds, decimals)` may return `None` on
  overflow — handle the `None` defensively as an empty/blank cell).

## Scope

**Created:** `browser/ui/bookmark_frame.py`, `tests/browser/ui/test_bookmark_frame.py`.
**Out of scope:** any change to `ui/scrollable.py`, `ui/better_treeview.py`,
`browser/ui/scrub_frame.py` (task 4 integrates it), session/metadata/state files, and any
`UiContext`/metadata knowledge inside the widget.

## Guidance

- Widget: `class BookmarkFrame(ttk.Frame)` with the nested `__Widgets(NamedTuple)`
  describing the scrollable wrapper (or the raw pieces), entry, and button.
  Constructor `(parent, *, width: int = 200, **kwargs)` — pass `width` through as the
  `ttk.Frame` width, then call `self.grid_propagate(False)` so the request honored by the
  parent pane stays at exactly `width` px (see verified mechanism above). Keep only what
  the widget needs: no `ctx`, no metadata imports besides `Bookmark`.
- Hierarchy / grid: row 0 (weight 1) the `ScrollableWidgetFrame(self,
  child_type=ttk.Treeview, child_params={"columns": ("time", "name"), "show": "headings",
  "selectmode": tk.BROWSE}, xscrollable=False)`; row 1 the entry; row 2 the "Bookmark"
  button (`columnconfigure(0, weight=1)` so they stretch to the 200 px frame).
- Treeview tuning (via `.child`): headings "Time"/"Name"; `column("#1", width≈80,
  minwidth≈40, stretch=False)`, `column("#2", width≈90, minwidth≈40, stretch=True)` —
  combined with the scrollbar the requested width stays ≈200.
- State: keep an `iid -> Bookmark` mapping (e.g. `_rows: dict[str, Bookmark]`) so handlers
  resolve the full `Bookmark`, and optional stored handler attributes
  (`_add_handler: Callable[[str], bool] | None`, `_seek/_remove:
  Callable[[Bookmark], None] | None`) initialized `None`, guarded when invoked.
- `set_bookmarks(bookmarks: Sequence[Bookmark])`: delete all children, then re-insert in
  the given (already time-sorted) order with `iid=str(time_ms)`,
  values=`(clock_format(time_ms / 1000, decimals=3) or "", name)`. Skip defensively any
  bookmark whose `str(time_ms)` iid is already present (a sidecar edited by hand could
  carry duplicate times; a Treeview re-inserting an existing iid raises TclError).
  **Never** call `selection_set`; do not retain selection state.
- Event handlers:
  - `<Button-1>`: resolve the row with `identify_row(ev.y)`, skipping when the region is
    `"heading"`/`"separator"` or the row is empty; `_rows` lookup → seek handler. This is
    the primary single-click path and also fires when the clicked row is already selected.
    Always forward the click — suppressing redundant seeks is the ScrubFrame's concern
    (task 4), not the widget's.
  - `<<TreeviewSelect>>`: `selection()` must be non-empty before doing anything
    (delete-all fires empty-select events — verified); resolve one iid through `_rows`
    and call the seek handler (keyboard navigation path; a mouse click may additionally
    fire the `<Button-1>` path for the same bookmark — same target time, harmless).
  - `<Delete>` on the treeview: selection-based → remove handler. No selection → no-op.
  - entry `<Return>` and button command share one add routine: read text, strip, call the
    add handler; clear the entry (`delete(0, tk.END)`) **only when it returns True**
    (duplicate rejection keeps the text so the user can nudge position and retry); blank
    text means unnamed (`""` is a legitimate name value, do not block empty).
- `set_enabled(enabled: bool)`: treeview selectmode `"browse"` / `"none"`;
  entry/button `.state(["disabled"])` / `.state(["!disabled"])`; remember the flag and
  make every event handler no-op while disabled (a disabled treeview still fires bound
  `<Button-1>`/`<Delete>` events).
- Setter-style API exactly: `set_bookmarks`, `set_enabled`, `set_add_handler`,
  `set_seek_handler`, `set_remove_handler`.
- Tests (`tests/browser/ui/test_bookmark_frame.py`, real `tk.Tk()` root like
  `test_file_meta_treeview.py`; recording stubs for the three handlers):
  - rows inserted in the given order, `iid == str(time_ms)`, column values equal
    (`clock_format(time_ms / 1000, decimals=3)`, name);
  - button press invokes the add handler with the *stripped* entry text; clear-on-True
    vs keep-on-False; blank entry passes `""` unchanged;
  - `<Return>` on the entry also invokes the add handler;
  - clicking a row invokes the seek handler with the matching `Bookmark` — either invoke
    the bound handler directly or `event_generate("<Button-1>", ...)` using the widget's
    own `bbox` for geometry after `root.update()`; criteria must be behavior-level;
  - clicking the already-selected row invokes the seek handler again (covers the re-click
    case `<<TreeviewSelect>>` alone would miss);
  - selecting a row via `selection_set` (allowed in tests only) also invokes the seek
    handler with the matching `Bookmark` (keyboard-navigation path);
  - `<Delete>` with a selection invokes the remove handler with the right bookmark; with
    no selection it does not;
  - `set_enabled(False)` selects nothing and blocks interaction (selectmode `"none"`,
    entry/button receive disabled state, handlers not invoked on attempted click/select/
    delete);
  - a re-render with an empty list leaves no rows and does not invoke the seek handler
    (empty-selection guard covered);
  - duplicate-iid defensive skip: a list with two identical `time_ms` values renders one
    row of each unique time without raising.

## Acceptance criteria

- [ ] `BookmarkFrame` is a dumb widget: imports only stdlib/tk, `Bookmark` (browser.metadata)
      and `clock_format` (util.format); no `UiContext`, no actions, no session.
- [ ] Constructor matches `(parent, *, width: int = 200)`; width honored via
      `grid_propagate(False)`; layout rows/weights as specified.
- [ ] Treeview uses `ScrollableWidgetFrame(child_type=ttk.Treeview, xscrollable=False)`
      with `show="headings"`, `columns=("time", "name")`, `selectmode=tk.BROWSE`,
      Time column fixed-width and Name stretch column as specified.
- [ ] `set_bookmarks` renders sorted input in order with `iid=str(time_ms)`, formatted
      time+name values, and `frame_no` never rendered.
- [ ] `set_bookmarks` never leaves a selection behind and tolerates duplicate `time_ms`
      (defensive skip) and `clock_format`'s `None` return.
- [ ] Handlers: row click and selection both invoke seek (clicking the already-selected row
      included), `<Delete>`→remove, entry `<Return>`/button→add with stripped text cleared
      only on `True`; all no-op while disabled.
- [ ] `set_enabled` flips treeview selectmode and entry/button disabled states.
- [ ] Widget never calls `selection_set` and no-ops on empty `<<TreeviewSelect>>`.
- [ ] New tests all pass and use the real-Tk-root harness pattern.

## Verification

```
uv run pytest tests/browser/ui/test_bookmark_frame.py tests/browser/ui/test_file_meta_treeview.py
uv tool run ruff check browser/ui/bookmark_frame.py tests/browser/ui/test_bookmark_frame.py
uv tool run pyright browser/ui/bookmark_frame.py tests/browser/ui/test_bookmark_frame.py
```

## Review record

Reviewed commit `2c3e446226daf60d08c666cde95191aa84753096` (code-reviewer, 2026-10-16).

**Verdict: approved.** All 9 acceptance criteria pass. Verification re-run by the reviewer:
21 targeted tests, 160 full-suite tests, ruff and pyright clean over both new files. The
reviewer accepted the implementer's judgment calls: named column identifiers
(`"time"`/`"name"`), the extra tests, `focus_force()` in the test harness, the
direct-invocation re-click test (the widget holds no dedupe state — redundant-click
suppression is explicitly the ScrubFrame's concern per spec decision 8), and the
empty-re-render test selecting a row first.

Follow-ups:
- NIT (accepted, no action): the re-click assertion tolerates duplicate seeks of the same
  bookmark by design ("same target time, harmless").
- NIT (accepted, no action): the blank-entry test asserts an already-empty entry stays
  empty; the meaningful assertion (that `""` reached the handler) is present.

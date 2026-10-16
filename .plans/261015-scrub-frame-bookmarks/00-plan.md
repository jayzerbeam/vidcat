# Plan: ScrubFrame timeline bookmarks

Spec: see `00-spec.md`. Status values: `pending` / `in-progress` / `done` / `blocked`.

| Task | File | Summary | Depends on | Status |
|------|------|---------|------------|--------|
| 1 | `01-metadata-bookmarks.md` | Bookmark schema in `EMPTY_METADATA`, `Bookmark` NamedTuple, tolerant `parse_bookmarks`, `insert_bookmark`, `delete_bookmark` in `browser/metadata.py` + tests | — | pending |
| 2 | `02-session-signal-actions.md` | `BookmarksChanged` signal, staged `add_bookmark`/`remove_bookmark` on `VideoSession`, `AppActions` + `App` plumbing, ordered-log test updates | 01 | pending |
| 3 | `03-bookmark-frame-widget.md` | New dumb `BookmarkFrame` widget in `browser/ui/bookmark_frame.py` + its unit tests | 01 (for the `Bookmark` type) | pending |
| 4 | `04-scrubframe-integration.md` | `ScrubFrame` PanedWindow layout rework, `BookmarkFrame` wiring (seek/add/remove), `.plan` TODO removal | 02, 03 | pending |

Execution order: 01 → 02 and 03 (parallelizable) → 04.

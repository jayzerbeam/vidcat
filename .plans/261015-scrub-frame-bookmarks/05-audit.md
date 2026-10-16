# Audit: ScrubFrame timeline bookmarks (holistic quality audit)

- Auditor: code-auditor subagent, 2026-10-16
- Branch: `scrub_bookmark`
- Scope: the feature's code as committed across `88b4f59`, `2be58c8`, `a00d3c3`, `2c3e446`,
  `7bf718b`, `579d02f` — a holistic readability/maintainability/quality pass, not a
  spec-compliance review (per-task spec reviews had already passed).
- Verification state at audit time: `uv run pytest` 160 passed; `uv run pyright browser tests`
  0 errors; ruff clean for all touched files. The ~10 pyright errors in the untouched legacy
  top-level `ui/` package are pre-existing and out of scope.

## Findings

### MAJOR (remediated)

**[MAJOR] `browser/ui/scrub_frame.py:114-131, 263-267, 292-297` — the seek Scale was never
reset on `load()`/`clear()`, so `_current_ms()` returned a stale-fraction position for a
freshly loaded video.**

- `load()` disabled the Scale but nothing ever reset its value; `ttk.Scale` keeps its last
  fraction across loads while `_apply_loaded` sets the label to `0:00.000` and draws frame 0.
  Concretely: scrub video A to 60%, select video B → label shows `0:00.000`, canvas shows
  frame 0, slider sits at 0.6. Clicking **Bookmark** then stages a bookmark at
  `round(0.6 × B.duration)` — data the user believes is at ~0:00 — and Save persists it.
- `_handle_open` had the same flaw (pre-existing: Open would start at the stale fraction),
  and the `_handle_bookmark_seek` same-position no-op check could misfire against it.
- The root cause predates this feature, but the feature upgraded the consequence from
  "Open starts in a weird place" to "wrong bookmark silently recorded".

**Remediation:** fixed in commit `99b2ac5` (`fix(ui): reset scrub seek bar when loading or
clearing a video`) — `self._widgets.seek.set(0.0)` in both `load()` and `clear()`. Safe
because the `_handle_seek` position guards (`_duration_ms == 0` in `load()`, `_path is None`
in `clear()`) make the command the `set()` triggers a no-op at that point. A regression test
pin awaits a ScrubFrame test harness (see MINOR 2).

### MINOR (deferred — revisit after the manual smoke test)

1. **`browser/session.py:98-106` — mutator API asymmetry.** `remove_bookmark` returns `None`
   while `add_bookmark` returns `bool`, even though `delete_bookmark` already returns a
   change indicator. Suggested: `return bool(delete_bookmark(...))` with `-> bool` (zero
   behavior change today; lets future callers detect a no-op removal).
2. **`browser/ui/scrub_frame.py:153-164, 263-287` — new integration logic has zero automated
   coverage.** Riskiest testable-without-the-worker bits: the `_handle_bookmarks_changed`
   cache/render gating (including a foreign path arriving mid-load), `_seek_to_ms` clamping
   into [0, 1], and the `_handle_bookmark_seek` same-position no-op. A real-`tk.Tk` harness
   mirroring `test_bookmark_frame.py` can drive `_path`/`_duration_ms`/the Scale directly.
3. **`tests/browser/test_session.py:478-496` — remove → `save()` has no session-level pin.**
   The add path is pinned; nothing asserts the written sidecar after a staged remove (the
   pure `delete_bookmark` helper is covered, so risk is low). ~10 lines mirroring the
   existing test would close it.
4. **`tests/browser/ui/test_bookmark_frame.py:219-243` — only `set_enabled(False)` is
   asserted.** Nothing verifies `set_enabled(True)` restores `browse` selectmode and
   `!disabled` widget states — the exact path `_apply_loaded` takes on every successful load.

### NIT (no action)

- **`browser/ui/bookmark_frame.py:66-67` — `set_bookmarks` trusts the caller to pre-sort.**
  Fine today: the only caller feeds `parse_bookmarks` output (always sorted). A defensive
  `sorted(bookmarks, key=...)` would make the renderer self-sufficient, but it is acceptable
  as-is.

## Positives (keep as-is)

- **Strict schema handling:** `_as_plain_int` rejecting bools and numeric strings, tolerant
  `parse_bookmarks`, iid-dedupe in `set_bookmarks` for hand-edited sidecars, and
  `clock_format` overflow → blank cell — the tolerance layer is well executed and pinned by
  tests.
- **Contract documentation:** `BookmarksChanged`'s docstring captures the
  emit-before-`selection_changed` ordering and snapshot-vs-live-dict semantics;
  `VideoSession.add_bookmark` explains why `_show()` is deliberately skipped; the
  `grid_propagate(False)` comment explains a non-obvious Tk negotiation quirk.
- **Pattern consistency:** dumb-widget design mirroring `EditableList`/`ImagesFrame`;
  structural `AppActions` protocol updated in lockstep with `StubActions`; staged edits
  riding the existing Save flow; `_current_ms` extraction reducing duplication.
- **Test quality overall is high:** event-driven widget tests, ordered-emission-log pins,
  no-write assertions for staged mutators, and the unsaved-entry-edit test that pins the
  load-bearing no-`_show()` decision.
- Cross-tool check: `globtag.py` loads-then-rewrites the existing pickle, so `bookmarks`
  survives its round-trips; `insert_bookmark` normalization is lossless for well-formed data.

## Overall assessment

Well above the codebase's average bar. The layering (pure helpers → staged session mutators
→ typed signal → dumb widget → ScrubFrame wiring) is clean, each commit is coherent, and the
comments do real explanatory work. The one substantive issue was the never-reset seek Scale —
pre-existing, but newly consequential, and now remediated. The four MINORs are cheap
follow-ups suitable for a small hardening task; they were deliberately deferred at the
product owner's direction.

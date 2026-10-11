# Task 06 — Cleanup and final verification

## Objective

Remove all dead code and imports left by tasks 01–05, enforce the architecture rules mechanically, and run
the full automated and manual verification for the refactor.

## Context

After tasks 01–05, `browser/app.py` should contain only `__init__`, the `__Widgets` NamedTuple, a small
`_EDIT_PROMPTS` mapping, and the 15 `AppActions` methods delegating to `launcher`, `library`, `trash`,
`store`, `session`, `dispatcher`, and `jobs`. The expected new modules are `browser/launcher.py`,
`browser/library.py`, `browser/metadata.py`, `browser/session.py`, and `browser/ui/tasks.py`.

## Scope

- Touched: `browser/app.py` (dead code/imports/docstrings only), possibly `browser/ui/actions.py` (comment
  documenting the `BulkAction` re-export), and `00-plan.md` status updates.
- Not touched: behavior. If cleanup suggests a behavior change, stop and raise it instead.
- Explicitly out of scope: new `AppActions` shape, per-feature protocols, widget edits, `Config`/`util`
  changes, and fixing the pre-existing pyright errors.

## Guidance

### Dead code and imports

1. Run `uv tool run ruff check` and remove every unused import/annotation it reports in touched files.
2. Confirm these symbols no longer exist anywhere in `browser/app.py` (use word-boundary patterns, e.g.
   `rg -n "\b_selected_path\b|\b_metadata\b|\b_post_ui\b"`, so `empty_metadata`/`metadata` module references
   do not false-positive):
   `_ui_queue`, `_post_ui`, `_drain_ui_queue`, `_emit_` helpers, `_close_status`, `_pathtree`, `_iter_files`,
   `update_filetree`, `_trash_path`, `_init_trash`, `_send_to_trash`, `_selected_path`, `_metadata`,
   `_generate_video_metadata`, `_apply_generated_metadata`, `load_metadata`, `clear_vidinfo`,
   `update_widgets_from_metadata`, `goto_path`, `play_file`, `MagicSidecar`, `VideoThumbnailer`.
3. Confirm `browser/app.py` has no method outside `__init__` and the `AppActions` methods (nested `work`
   closures inside job methods are fine). Target size is roughly ≤ 230 lines (was 605); the exact number is
   not a gate.
4. Confirm `browser/ui/actions.py` re-exports `BulkAction` from `browser.metadata` and widgets still import
   it from `.actions`. Add a one-line comment if it clarifies the re-export.

### Architecture rule checks

- `rg -n "import tkinter|from browser\.ui|from \.ui" browser/metadata.py browser/library.py browser/launcher.py`
  must return nothing.
- `rg -n "browser\.(metadata|library|launcher|session)|from \.\.(metadata|library|launcher|session)" browser/ui/tasks.py`
  must return nothing.
- `rg -n "MagicSidecar|pickle" browser/app.py` may only match the `pickle.PickleError` except-clause if it
  remains; `browser/app.py` must not read/write sidecars directly.
- Confirm the only changed pre-existing files are `browser/app.py`, `browser/ui/actions.py`, and (not
  modified) none of the widgets: `git status`/`git diff --stat` should list the five new modules, the five
  new test files, `browser/app.py`, `browser/ui/actions.py`, and this plan's files only.

### Optional follow-ups (do not implement here)

- Remove `AppActions.clear_filters` in favor of `apply_filters((), ())`, or merge single/bulk thumbnail
  generation. These require widget call-site edits; record as a separate idea, do not do it in this plan.

## Acceptance criteria

- [ ] No unused imports or dead symbols remain in touched files.
- [ ] `browser/app.py` is `__init__` + `AppActions` methods only.
- [ ] All architecture `rg` checks above are satisfied.
- [ ] Full automated verification below passes (pyright shows only the 10 pre-existing errors).
- [ ] Full manual smoke checklist below passes.
- [ ] `00-plan.md` status table has all tasks `done` and each task file's Review section records the outcome.

## Verification

Automated:

- `uv run pytest -q`
- `uv tool run ruff check browser tests`
- `uv tool run pyright` (expect exactly the pre-existing errors in `ui/message_system.py` and
  `ui/scrollable.py`)

Manual smoke checklist (run the app against a test folder with at least 3–4 video files):

1. Launch: window opens, tree renders the folder contents.
2. Select a file: info pane shows path, size, resolution, duration, metadata size; scrub tab shows the first
   frame.
3. Select a folder: info clears, scrubber clears and releases the file.
4. Edit title/actors/tags, press Ctrl+S, reselect the file: values persist; metadata-size label updates.
5. Context menu on a folder: `Refresh files` (add/remove a file first) and `Refresh metadata`.
6. Context menu on files: `Add actor`, `Del actor`, `Add tag`, `Del tag`, `Clean` (cleanup a sidecar and
   verify `metadata size: none` on reselect).
7. Context menu: `Generate Thumbnails` on 2+ files — status progress advances per file, failures are logged,
   successful sidecars update the tree columns.
8. `Send to trash`: single selected file and a multi-selection; items disappear and appear under `.trash`.
9. `[info]` opens the OS file explorer; double-click plays a file; scrub `Open` plays from the slider
   position; Ctrl+G generates thumbnails for the selected file.
10. Filters tab: `Scan` populates counts; selecting an actor/tag highlights matches; `Filter AND`/`Filter OR`
    hide non-matches; `Clear Filters` restores.
11. No tracebacks or `error:` output in the console during the above (corrupt-sidecar tests excepted).

## Review

| Date | Reviewer | Outcome | Notes |
|------|----------|---------|-------|
| 2026-10-10 | code-reviewer (subagent) | approved (conditional on manual smoke) | Commits `4034d9f` (test-fake pyright fixes; 20 latent errors cleared) and `08b164a` (fold `gen_thumbs_bulk`) approved; doc-wording MINOR fixed. Tech lead ran full automated verification: 110 tests, ruff clean, pyright exactly the 10 pre-existing errors, import ok; branch diff vs `c8fc43e` limited to intended files. Manual GUI smoke checklist executed by the user on 2026-10-10: all steps passed. |

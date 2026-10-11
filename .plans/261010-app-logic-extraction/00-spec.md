# Spec: Extract application logic from `App` into focused modules

## Summary

`browser/app.py` is 605 lines with 36 methods. Only the 15 `AppActions` protocol methods are the UI-facing
API; the rest is a mix of nine unrelated responsibilities (sidecar IO, file-tree scanning, trash, thumbnail
generation, OS launching, background-job plumbing, UI signal emission, selection/view state, and
composition). This plan extracts the application logic into focused modules and leaves `App` as the
composition root plus a thin adapter over `AppActions`.

The refactor is incremental: one task per module, each task adds unit tests and immediately rewires `App`.
The application must remain runnable and behaviorally identical after every task.

## Success criteria

1. Application logic (persistence, scanning, generation, launching, library/trash) lives in domain modules,
   not in `App`.
2. `App` remains the centralized wiring between UI and logic, and the only object the UI talks to
   (`UiContext.actions`).
3. Method clutter in `App` is minimized: after task 05, `App` contains `__init__` plus the 15 `AppActions`
   methods, each a short delegation or job assembly.
4. Complexity is minimized: the repeated thread/status/busy boilerplate collapses into one runner; each new
   module has a single responsibility and is unit-testable without Tk.

## Current responsibility map (as of 2026-10-10)

| Concern | Current members (method names; line numbers approximate) |
|---|---|
| Composition/lifecycle | `__init__` (L50), `__Widgets` (L44) |
| UI-thread marshaling | `_ui_queue`, `_post_ui` (L78), `_drain_ui_queue` (L81) |
| Status/signal emission | `_emit_file_metadata`, `_emit_progress`, `_set_progress`, `_emit_actor_counts`, `_emit_tag_counts`, `_emit_busy`, `_close_status` (L91–110) |
| Selection + loaded metadata | `_selected_path`, `_metadata`, `select_paths` (L128), `activate_path` (L142), `play_from_ms` (L149), `load_metadata` (L550), `clear_vidinfo` (L576), `update_widgets_from_metadata` (L585), `save_metadata` (L356), `_apply_generated_metadata` (L113) |
| File tree | `_pathtree`, `update_filetree` (L603), `rescan_path` (L185), `_iter_files` (L597) |
| Trash | `_trash_path`, `_init_trash` (L118), `_send_to_trash` (L169) |
| Sidecar metadata | `_EMPTY_METADATA` (L17), `delete_metadata` (L235), `edit_metadata` (L252), `scan_metadata` (L374), `scan_path_metadata` (L195) |
| Thumbnail generation | `_generate_video_metadata` (L430), `generate_thumbnails` (L317), `gen_thumbs_bulk` (L451) |
| OS launching | `goto_path` (L510), `play_file` (L527) |
| Filters | `apply_filters` (L424), `clear_filters` (L427) |

## Locked decisions

1. **`App` keeps implementing `AppActions`** (`UiContext.actions` continues to be `App`, no widget file
   changes). Rationale: dependency direction stays clean (`widgets → AppActions ← App → modules`); widgets
   never import a domain module; domain modules never import `browser.ui`; cross-service actions such as
   `delete_paths` have one natural home (the composition root). The considered alternative — per-feature
   protocols carried by `UiContext` — was rejected because it pushes the UI's action vocabulary into the
   services' public APIs and saves only `App` method count, not coupling.
2. **One task = one module + unit tests + immediate `App` adoption.** No "all modules first, integrate at
   the end" phase. Each task ends with the app runnable and the module exercised through the real app.
3. **Module layout** (flat under `browser/`, matching `config.py`/`app.py`):
   - `browser/launcher.py` — OS launching (`Launcher`).
   - `browser/library.py` — `VideoLibrary` (PathTree wrapper) and `Trash`.
   - `browser/metadata.py` — sidecar metadata domain (`MetadataStore`, `BulkAction`, pure helpers).
   - `browser/ui/tasks.py` — `UiDispatcher`, `JobContext`, `BackgroundJobs` (UI infrastructure).
   - `browser/session.py` — `VideoSession` (UI-aware selection/metadata view model).
4. **`BulkAction` moves to `browser/metadata.py`**; `browser/ui/actions.py` re-exports it so widget imports
   (`from .actions import BulkAction`) keep working.
5. **`MetadataStore` takes an injectable sidecar factory** (`Callable[[Path, str], Sidecar]` Protocol,
   default `MagicSidecar`) so tests do not depend on NTFS alternate data streams or the Windows platform.
6. **`StoredMetadata(metadata, byte_size)`** is returned by reads so the "metadata size" label keeps its
   current behavior without re-reading or re-pickling.
7. **`VideoSession.selected_path` is `Path | None`** (today `_selected_path` starts as `Path()` and is reset
   to `Path("")`).
8. **`Trash` reports unusable trash directories explicitly** (`available`); today an unusable
   `trash_dir` leaves `_trash_path` unassigned and `delete_paths` raises `AttributeError`.
9. **Only the deliberate deltas listed below are allowed.** Everything else must behave exactly as today,
   including console output where practical.
10. **No UI/feature changes.** `browser/ui/*` widget files, `ui/*`, `browser/config.py`, `util/file/tree.py`,
    `util/file/sidecar.py`, `util/video.py`, `util/format.py` are out of scope.

## Target architecture

```
widgets ──> UiContext / AppActions (Protocol)      (only UI-facing API; unchanged)
                  ▲
                  │ delegation
                 App ──────> browser/metadata.py      (no tkinter, no browser.ui)
                  │  ──────> browser/library.py       (no tkinter, no browser.ui)
                  │  ──────> browser/launcher.py      (no tkinter, no browser.ui)
                  │  ──────> browser/session.py       (UI-aware view model; imports UiState)
                  └────────> browser/ui/tasks.py      (UI infrastructure; knows StatusWindow + UiState)
```

Dependency rules enforced by task 06:

- `metadata.py`, `library.py`, `launcher.py` import stdlib and `util` only.
- `session.py` may import `browser.ui.state` (`UiState`) and domain modules; never widgets.
- `ui/tasks.py` owns all thread/status/queue marshaling.
- `App` action bodies never contain loops, pickling, scanning, or platform matching.

## Behavior invariants (must hold after every task)

- All `UiState` mutations/emissions and all Tk variable access happen on the Tk main thread. Worker code only
  posts callbacks through the dispatcher.
- The worker→UI queue is FIFO and drained via `root.after` (~30 ms); one failing callback does not stop the
  drain loop.
- `delete_paths` clears the selection *before* moving files (the scrubber releases its file handle on
  `selection_changed(())` with `wait=True`); then trash, then tree removal, then `paths_removed`.
- `select_paths` policy: a triggered file loads; a triggered non-file clears; otherwise the first file loads;
  empty selection clears.
- `load_metadata` sets `file_path`, `file_size` (`nice_bytesize(..., largest_unit='M')`), `meta_size`
  (`metadata size: none` when absent/unreadable, otherwise `nice_bytesize(byte_size)`), then refreshes the
  view and emits `selection_changed((path,))` last.
- `save_metadata` reads `meta_title`/`meta_actors`/`meta_tags` (via `splitlist`), refreshes the view,
  writes the sidecar, sets `metadata size: {round(bytes/1000)}KB`, and keeps the `PickleError` vs generic
  error messages.
- `update_widgets_from_metadata` emits `file_metadata_changed((selected_or_Path(), metadata))`, sets
  title/actors/tags/length/resolution, and emits `thumbnails_changed`.
- Job choreography: `scan_path_metadata` shows status only; `scan_metadata` and both thumbnail jobs show
  status + busy; both thumbnail jobs run `gc.collect()` after completion.
- Bulk generate: read sidecar (fallback to empty on missing/corrupt), generate, write only on success, but
  **always** emit the per-file metadata and per-file progress in `finally`.
- `refresh_files` skips missing sidecars silently and tracebacks corrupt ones; `aggregate_files`
  pre-checks `sidecar.exists`, prints `failed to unpickle` vs `failed to read` without traceback, and counts
  lowercased actor/tag names.
- `rescan_path` only acts on directories and emits `FileTreeUpdate(pt, str(path))` after clear+rescan.
- OS launching semantics: player path exists → `os.spawnv(P_NOWAIT, ...)` with `argv[0] = player.name`,
  quoted file path, `%t_ms`/`%t_sec` interpolation; otherwise platform fallback exactly as today
  (`reveal` uses `subprocess.Popen`, `play` fallback uses `subprocess.call`; do not harmonize).

## Deliberate behavior deltas (the complete list)

1. `scan_metadata` and `scan_path_metadata` build their file lists on the main thread before starting the
   worker (today traversal happens inside the worker, racing concurrent tree mutations).
2. `aggregate_files` uses `metadata.get("actors", [])` / `.get("tags", [])` instead of direct indexing, so a
   sidecar without those keys cannot kill the scan worker.
3. Missing-sidecar console wording is unified (`{path} does not have a magic sidecar`); bulk generate
   previously printed `no sidecar metadata for {f}`. Consequently bulk generate's generic load-failure
   wording also comes from `read_or_empty` (`{path} failed to load metadata: {ex}`) instead of
   `error: loading sidecar metadata for {f}: {ex}`.
4. `delete_metadata` emits a fresh `empty_metadata()` per cleaned file instead of the shared
   `_EMPTY_METADATA` singleton.
5. After task 05, `delete_paths` emits `selection_changed(())` once instead of twice (today `clear_vidinfo`
   emits and `delete_paths` emits again). The extra emission was redundant; scrubber clearing is idempotent.
6. Final job completion ordering for thumbnail jobs becomes apply → busy-off → hide-status (today
   apply → hide → busy-off). All callbacks land in the same drain cycle; cosmetic.
7. `Trash` no longer raises `AttributeError` for an unusable trash directory; it becomes a no-op with the
   existing `error:trash directory is not a directory, could not initialize` log.
8. The `updating metdata for {f}` typo in `edit_metadata` may be corrected while moving the loop into
   `MetadataStore.edit_files` (console only).
9. With `selected_path: Path | None`, `save()` with no selection (Ctrl+S on an empty selection) logs
   `failed to save metadata for None: ...` instead of the old `... for .: ...` (old `Path()` sentinel);
   console-only, both paths fail safely and neither is reachable in the normal UI flow.

## Out of scope

- Per-feature action protocols or changes to `UiContext`/`AppActions` shape.
- Removing/merging `AppActions` methods (e.g. `clear_filters`, single vs bulk thumbnail generation). Note as
  possible follow-up only.
- Any widget, `ui/*` library, `Config`, `PathTree`, `MagicSidecar`, `VideoThumbnailer`, or `util/format.py`
  change (except the `BulkAction` re-export in `browser/ui/actions.py`).
- New features or bug fixes beyond the deltas above.
- Fixing the 10 pre-existing pyright errors in `ui/message_system.py` and `ui/scrollable.py`.

## Test strategy

- New tests live under `tests/browser/` mirroring package paths (`tests/browser/ui/test_tasks.py`), following
  `tests/util/` style (plain functions, `tmp_path`, `pytest`, no Tk root required).
- Domain modules are tested with fakes injected through constructors: an in-memory sidecar for
  `MetadataStore`, a fake `UiState` duck-type for `VideoSession`, fake dispatcher/status for `ui/tasks.py`.
- Each task adds its module's tests; task adoption is verified by the existing suite plus the task's manual
  smoke checklist. Task 06 runs the full manual smoke list.

## Verification baseline (2026-10-10)

- `uv run pytest -q` → 47 passed.
- `uv tool run ruff check browser tests` → clean.
- `uv tool run pyright` → 10 pre-existing errors: `ui/message_system.py` (7), `ui/scrollable.py` (3). No
  errors in `browser/` or `util/`. Tasks must not introduce new errors in files they touch.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Threading/Tk regressions during queue extraction (task 04) | Port `_drain_ui_queue` semantics exactly; fake-based tests; manual smoke of all four jobs |
| Sidecar edge-case behavior drifts during extraction (task 03) | Behavior invariant list + per-call-site tests with fake sidecar errors |
| `MagicSidecar` is Windows/ADS-only | Injectable sidecar factory; tests never touch real ADS |
| Test environment lacks a display | No test constructs `tk.Tk`; fakes only |
| `app.py` conflicts if tasks run in parallel | Tasks are serialized on `app.py`; merge one task before starting the next |
| Subtle progress math differences in bulk generate | Explicit progress formula in task 03; unit test recorded progress sequence |
| Stale imports / architecture erosion after adoption | Task 06 enforces `rg` checks for domain-module purity and removed symbols |

## Artifacts

- `00-plan.md` — task index, dependencies, status tracking.
- `01-launcher-module.md` … `06-cleanup-and-verification.md` — task specifications.

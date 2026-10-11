# Code audit findings — application-logic extraction refactor

## Context

- **Auditor:** code-auditor subagent (holistic quality audit; independent of the per-task code reviews).
- **Date:** 2026-10-10.
- **Branch:** `app_refactor`; **audited head:** `08b164a` (after task 06, before remediation).
- **Scope audited:**
  - New modules: `browser/launcher.py`, `browser/library.py`, `browser/metadata.py`, `browser/session.py`, `browser/ui/tasks.py`
  - Refactored: `browser/app.py` (605 → 230 lines), `browser/ui/actions.py` (`BulkAction` re-export)
  - Tests: `tests/browser/test_launcher.py`, `tests/browser/test_library.py`, `tests/browser/test_metadata.py`, `tests/browser/test_session.py`, `tests/browser/ui/test_tasks.py`
- **Method:** the code was reviewed on its own merits (quality, readability, maintainability, cohesion, coupling, naming, error handling, threading, tests); `00-spec.md`/`00-plan.md` were provided only as background. No spec-compliance re-review.
- **Baseline at audit:** 110 tests pass, `ruff check browser tests` clean, `pyright` at the 10 pre-existing errors (none in audited code).

Line numbers below are as of the audited head `08b164a`; the remediation commits shifted some of them (current locations noted where relevant).

## Verdict summary

| Severity | Count | Status |
|----------|-------|--------|
| SEVERE | 0 | — |
| MAJOR | 2 | both remediated |
| MINOR | 14 | 1 remediated (trash collision), 13 open / unscheduled |

No finding blocks the branch. Both MAJOR findings are **pre-existing races carried over from the old monolithic `App`**, not defects introduced by the refactor — the refactor concentrated them into single, cheap-to-fix locations, and the user approved remediation of the two MAJORs plus the data-loss MINOR.

## MAJOR findings

### M1 — A finished thumbnail job can merge generated metadata into the wrong file

- **Location:** `browser/app.py:200` + `browser/session.py:76-80` (audit head).
- **Description:** `generate_thumbnails` captures the target `path` for the worker but on completion posted `session.apply(generated)` without it; `apply` merged into whatever was currently selected. Busy only swaps the mouse cursor, and the tree plus root-bound accelerators stay active, so the sequence *select A → Ctrl+G → select B → generation finishes → Ctrl-S* could push A's dimensions/duration/thumbnails into B's view model and persist them into B's sidecar (and the post-clear variant merged stale data into empty metadata).
- **Suggested direction:** a path-checked session entry point (`apply_for(path, metadata)` that no-ops when `path != selected_path`), with `app.py` posting the owning path.
- **Status:** **FIXED in `2a8f156`** — `VideoSession.apply` became `VideoSession.apply_for(path, metadata)` (no-op when the selection is cleared or differs; old merge/refresh semantics otherwise) and `generate_thumbnails` posts `self._session.apply_for(path, generated)`.
- **Related, acknowledged (not remediated):** `Ctrl-S` racing a same-file bulk generate remains last-writer-wins and can drop just-generated thumbnails.

### M2 — Shared status/busy lifecycle has no concurrency guard

- **Location:** `browser/ui/tasks.py:90-107` (audit head).
- **Description:** every `BackgroundJobs.run()` showed the one shared `StatusWindow` and set busy, and every job's `finally` unconditionally posted busy-off then hide. Overlapping jobs are reachable (root-bound accelerators are never disabled during a job), so the first finisher could hide the status window and restore the cursor while the second was still publishing progress; the second job's `show()` could also re-open it after the first job's drain.
- **Suggested direction:** active-job/busy-job counters in `BackgroundJobs`; post busy-off only when busy jobs reach 0 and hide only when active jobs reach 0; document the UI-thread contract.
- **Status:** **FIXED in `2d03647`** — `_active`/`_busy` counters owned on the UI thread; workers post a single `_finish(busy)` completion through the dispatcher; `on_busy(False)` fires only at zero busy jobs, `status.hide()` only at zero active jobs; `gc.collect()` stays in the worker; docstrings document the contract.

## MINOR findings

| ID | Location (audit head) | Finding | Status |
|----|-----------------------|---------|--------|
| D1 | `browser/app.py:26,43` | `App._config` is assigned but never read after construction (dead state) | Open |
| D2 | `browser/app.py:154-167` | `edit_metadata` duplicates prompt structure across a 4-case `match`; a `dict[BulkAction, (title, label)]` mapping would be explicit (a future 5th action silently reuses the previous title); prompt wording arguably belongs to `InputWindow` | Open |
| D3 | `browser/app.py:208` | `scan_metadata` re-issues the filter reset inline instead of calling `self.clear_filters()`; two copies of the reset tuple can drift | Open |
| D4 | `browser/app.py:123,147,217` | The same `on_file` callback (`lambda f, m: ui.post(state.file_metadata_changed.emit, (f, m))`) is hand-built in three work closures; a `JobContext`/`App` helper would keep the post/emit pairing consistent | Open |
| D5 | `browser/metadata.py:202,238,279` | Three sibling scan loops use three progress formats (`[{i} / {total}] name`, `[{c}/{total}] path`, `[{c + 1} / {total}] file`) and inconsistent failure wording; partly deliberate output fidelity (delta 3), but a "which is right?" trap for maintainers | Open |
| D6 | `browser/metadata.py:281-287` | The `c=c` default-argument binding comment reads as a live-binding/race defense, but the closures are consumed synchronously within the iteration and never escape | Open |
| D7 | `browser/session.py:59-60` | `cast(Path, self._selected_path)` lets a knowingly-wrong type flow; an explicit `if self._selected_path is None: return` guard would state the invariant. Also `_show()` runs before the write, so a failed write displays unsaved values as if persisted (faithful to old code; deserves a comment) | Open |
| D8 | `browser/session.py:100-101` | `_show` hard-indexes `video_properties`/`dimensions`/`duration`, so a valid pickle with a partial schema raises `KeyError` out of a Tk callback (writers currently always write the full schema) | Open |
| D9 | `browser/launcher.py:58-59,62` | `reveal`'s Linux fallback catches `FileNotFoundError` for a missing `xdg-open`, but `play`'s fallback does not; `os.startfile` can also raise on no file association; asymmetry worth closing and both silent-no-op paths deserve a comment | Open |
| D10 | `browser/library.py:95` | `Trash.send` silently overwrote same-named entries in `.trash` (quiet data loss, verified on Python 3.14/Windows) | **Fixed in `9dde41a`** |
| D11 | `browser/ui/actions.py:7`, `browser/ui/file_meta_treeview.py:6` | Absolute `from browser.metadata import BulkAction` amid relative imports elsewhere in the package; pick one convention | Open |
| D12 | `browser/ui/tasks.py:112` | Worker threads are unnamed (`Thread-N` in dumps); `run()` with empty input still shows the status window for one drain cycle (harmless flash, undocumented) | Open |
| D13 | `tests/browser/ui/test_tasks.py:92` and missing cases | `sync_threads` monkeypatches the shared stdlib `threading` module (restored, but wider than needed); uncovered high-value cases: `VideoSession.save` failure branch (both arms), `Trash.send` collision (added by `9dde41a`), and `App` orchestration itself (e.g. `delete_paths` ordering) despite fakes already existing; the zero-interval time mock is brittle to extra `time.time()` calls | Open (collision case now covered) |
| D14 | `browser/app.py:127`, `browser/session.py:59`, `browser/app.py:117` | Review-time phrases ("like today", "fails as before", "spec delta N" inline references) will have no referent after merge; phrase as behavior and reference the plan file only where useful | Open |

## Notable strengths

- **Dependency direction is clean and verifiable:** `metadata.py`, `library.py`, `launcher.py` import nothing from tkinter/`browser.ui`; `session.py` touches only `UiState` (+ `MetadataStore`); `ui/tasks.py` is properly infrastructural; `app.py` is a real composition root.
- **Constructor injection made the domain testable without Tk:** sidecar factory, `split_list` callable, dispatcher/status fakes; the suite is substantive, fast (0.3 s), and mirrors the package layout under `tests/browser/`.
- **Failure-branch coverage is deliberate and precise:** corrupt sidecar untouched on failed edit; `edit_files`/`delete_files` continuing past errors; `generate_files` reporting failure without writing; dispatcher isolating a broken callback and still rescheduling; busy-off-before-hide ordered; exact fraction math pinned.
- **`UiDispatcher._drain` improves on the old loop:** rescheduling lives in `finally`, so a drain-time failure cannot kill the pump (the old `_drain_ui_queue` could).
- **Interface details done right:** `Trash.available` replacing the unassigned-`_trash_path` `AttributeError`; `StoredMetadata(byte_size)` for the "show size only when a sidecar exists" contract; `empty_metadata()` deep-copy independence with a test; main-thread snapshot comments at both scan call sites encoding the old worker/tree race fix.
- **`generate_files`' `finally`-based per-file reporting** preserves the old "emit + fraction even on failure" semantics more clearly than the old `continue`-and-emit dance.

## Remediation log

| Commit | Finding | Change |
|--------|---------|--------|
| `2a8f156` | M1 | `VideoSession.apply_for(path, metadata)`; `generate_thumbnails` posts the owning path |
| `2d03647` | M2 | `BackgroundJobs` active/busy counters; UI-thread-serialized completion; docstrings |
| `9dde41a` | D10 | `Trash.send` chooses a free `{stem} ({n}){suffix}` target instead of overwriting |

- Remediation review (code-reviewer, 2026-10-10): **approved** — no SEVERE/MAJOR findings; three optional MINOR hardenings remain (see below).
- Post-remediation verification at `9dde41a`: **114 tests pass**, `ruff check browser tests` clean, `pyright` at the 10 pre-existing errors, `import browser.app` ok.

## Remaining unscheduled MINOR hardenings (from the remediation review)

1. `BackgroundJobs._finish` fuses busy-off and hide in one callback: a subscriber exception between the decrement and `hide` can skip hide until the next job completes; a `try/finally` around the busy-off would make hide unconditional.
2. `tests/browser/test_library.py`: add a second collision case (`video.mp4` and `video (1).mp4` both present → `video (2).mp4`).
3. `tests/browser/ui/test_tasks.py:230`: prefer the exact queued-callback identity assertion (`jobs._finish`) over `len(dispatcher.posted) == 1`.

## Whitebox/blackbox note

Manual GUI smoke was executed by the user on 2026-10-10 and passed against the pre-remediation head (`08b164a`). The three remediation changes affect thumbnail-job completion, overlapping-job status/busy behavior, and trash collisions; a short re-smoke of those specific flows is advisable if the remediation is kept.

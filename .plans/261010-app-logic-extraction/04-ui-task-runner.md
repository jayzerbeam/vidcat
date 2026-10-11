# Task 04 — Extract UI task runner into `browser/ui/tasks.py`

## Objective

Replace `App`'s ad-hoc UI-thread queue, status/progress emission helpers, and per-job threading boilerplate
with `UiDispatcher`, `JobContext`, and `BackgroundJobs` in a new `browser/ui/tasks.py`, and rewrite the four
background jobs on top of them.

## Context

- Current implementation in `browser/app.py`: `_ui_queue` field, `_post_ui` (L78), `_drain_ui_queue` (L81),
  `_emit_file_metadata` (L91), `_emit_progress` (L94), `_set_progress` (L98), `_emit_actor_counts` (L101),
  `_emit_tag_counts` (L104), `_emit_busy` (L107), `_close_status` (L110), plus the status/thread/close/gc
  pattern repeated in `scan_path_metadata` (L195), `scan_metadata` (L374), `generate_thumbnails` (L317) and
  `gen_thumbs_bulk` (L451).
- `StatusWindow` (`browser/ui/status_window.py`) exposes `show()`, `hide()`, `info` and `progress` setters.
- `UiState.busy_changed` is a `Signal[bool]` (`browser/ui/state.py`); all emissions must run on the Tk thread.
- Domain scan loops and `session.apply` are already wired in tasks 02/03; this task only changes the
  scaffolding around them.

## Scope

- Touched: `browser/ui/tasks.py` (new), `browser/app.py`, `tests/browser/ui/test_tasks.py` (new).
- Not touched: widget files, `browser/ui/state.py`, domain modules (`metadata.py`, `library.py`), the
  `InputWindow`/`StatusWindow` APIs.
- Do not change job semantics: which jobs set busy, which collect garbage, or any progress text/value.

## Guidance

### `browser/ui/tasks.py`

```python
class UiDispatcher:
    """FIFO marshaling of callbacks onto the Tk main thread."""
    def __init__(self, root: tk.Misc, interval_ms: int = 30) -> None:
        # store root/interval, create Queue, schedule self._drain via root.after(interval_ms, ...)
    def post(self, callback: Callable[..., None], *args: Any) -> None:
        # put partial(callback, *args) on the queue
    def _drain(self) -> None:
        # while queue non-empty: run callback; on Exception print "error: UI callback failed: {ex}" + traceback
        # always re-schedule root.after(interval_ms, self._drain) in finally so one bad callback cannot stall it

class JobContext:
    """Worker-thread-safe bridge handed to background work."""
    def __init__(self, dispatcher: UiDispatcher, status: StatusWindow) -> None: ...
    def post(self, callback: Callable[..., None], *args: Any) -> None: ...   # marshal to UI thread
    def progress(self, info: str, fraction: float) -> None: ...              # sets info + bar, marshaled
    def fraction(self, value: float) -> None: ...                            # sets bar only, marshaled
    def progress_func(self, prefix: str) -> Callable[[float], None]: ...     # thumbnail ProgressFunc

class BackgroundJobs:
    """Runs background work with the shared status/busy lifecycle."""
    def __init__(self, dispatcher: UiDispatcher, status: StatusWindow, on_busy: Callable[[bool], None]) -> None: ...
    def run(self, work: Callable[[JobContext], None], *, busy: bool = False, collect_garbage: bool = False) -> None: ...
```

Details:

- `JobContext.progress_func(prefix)` returns a callable that calls `progress(f"{prefix} {fraction * 100:.1f}%", fraction)`
  (this reproduces the current thumbnail progress text exactly).
- `BackgroundJobs.run`: call `status.show()`; if `busy`, call `on_busy(True)`; build a `JobContext`; start a
  daemon thread running `work(ctx)`. In a `finally`: if `busy`, `dispatcher.post(on_busy, False)`; then
  `dispatcher.post(status.hide)`; then `if collect_garbage: gc.collect()`. Wrap `work` in try/except that
  prints `error: background job failed: {ex}` + traceback so one job cannot kill the process.
- `on_busy` is wired to `UiState.busy_changed.emit`; the initial `True` runs synchronously on the calling
  (main) thread and the final `False` is posted, matching today's behavior.

### Rewire `browser/app.py`

1. In `__init__` (after the widgets exist): `self._dispatcher = UiDispatcher(root)` and
   `self._jobs = BackgroundJobs(self._dispatcher, self._widgets.status, self._state.busy_changed.emit)`.
   Remove the `_ui_queue` field and the `root.after(30, self._drain_ui_queue)` call. Add annotations.
2. Delete `_post_ui`, `_drain_ui_queue`, `_emit_file_metadata`, `_emit_progress`, `_set_progress`,
   `_emit_actor_counts`, `_emit_tag_counts`, `_emit_busy`, `_close_status`.
3. Rewrite the four jobs; each `work(ui)` closure uses the domain functions from tasks 02/03:

   ```python
   def scan_path_metadata(self, path: Path) -> None:
       if not path.is_dir():
           return
       files = tuple(self._library.iter_files(path))

       def work(ui: JobContext) -> None:
           metadata.refresh_files(
               files, self._store,
               on_file=lambda f, m: ui.post(self._state.file_metadata_changed.emit, (f, m)),
               on_progress=ui.progress,
           )

       self._jobs.run(work)                                  # no busy, like today

   def scan_metadata(self) -> None:
       self._state.filters_changed.emit(((), (), "OR"))
       items = tuple(self._library.iter_files())

       def work(ui: JobContext) -> None:
           actors, tags = metadata.aggregate_files(
               items, self._store,
               on_file=lambda f, m: ui.post(self._state.file_metadata_changed.emit, (f, m)),
               on_progress=ui.progress,
           )
           ui.progress("populating widgets", 1.0)
           ui.post(self._state.actor_counts_changed.emit, actors)
           ui.post(self._state.tag_counts_changed.emit, tags)

       self._jobs.run(work, busy=True)
   ```

   `generate_thumbnails`: keep the `_selected_path.is_file()` guard and read `thumb_interval`/`thumb_height`
   on the main thread before `run`; `work` calls `metadata.generate_video_metadata(...)` with
   `extract_progress_func=ui.progress_func("Extracting frames...")` and
   `resize_progress_func=ui.progress_func("Resizing frames...")`; catch exceptions with the existing
   `error: failed to generate metadata for {path}` message; then `ui.post(self._apply_generated_metadata, generated)`.
   Run with `busy=True, collect_garbage=True`.

   `gen_thumbs_bulk`: keep the method split and file filtering from `generate_thumbnails_bulk`; `work` calls
   `metadata.generate_files(files, self._store, interval=..., height=..., on_file=..., on_progress=ui.progress, on_fraction=ui.fraction)`.
   Run with `busy=True, collect_garbage=True`.
4. Note the one cosmetic ordering change (spec delta 6): thumbnail jobs now finish as
   `apply → busy-off → hide` instead of `apply → hide → busy-off`; both land in the same drain cycle.
5. `scan_path_metadata` and `scan_metadata` keep their main-thread file snapshots (task 02 delta).

### Tests — `tests/browser/ui/test_tasks.py`

No Tk root: use fakes.

- `FakeRoot`: records `after(delay, callback)` calls and lets the test invoke the stored drain callback.
- `FakeDispatcher`: records posted `(callback, args)` tuples and can execute them on demand.
- `FakeStatus`: records `show`/`hide` calls and current `info`/`progress`.
- `UiDispatcher`: constructor schedules the drain; `post` runs callbacks FIFO when the drain executes; a
  raising callback is logged and does not prevent later callbacks or re-scheduling.
- `JobContext`: `post` forwards with args; `progress` sets info + bar after executing the posted callback;
  `progress_func("Extracting frames...")` yields `Extracting frames... 12.3%` for `0.123`.
- `BackgroundJobs`: with a work function that records the call order and sets a `threading.Event`, assert
  `status.show()` ran before work, `on_busy` saw `True` then `False`, `status.hide()` ran after, and
  `gc.collect` is called only when `collect_garbage=True` (monkeypatch `browser.ui.tasks.gc.collect`).

## Acceptance criteria

- [ ] `browser/ui/tasks.py` contains `UiDispatcher`, `JobContext`, `BackgroundJobs`; no domain imports.
- [ ] `App` no longer contains `_ui_queue`, `_post_ui`, `_drain_ui_queue`, or any `_emit_*`/`_close_status`
      helper; `App` never touches `status.info`/`status.progress` directly.
- [ ] All four jobs run through `BackgroundJobs.run` with the exact busy/gc flags from the invariant list.
- [ ] Thumbnail progress text/values are byte-identical to the old `_progress` closures.
- [ ] Queue behavior (FIFO, 30 ms, per-callback exception isolation) preserved.
- [ ] New tests pass; no widget file changed.

## Verification

- `uv run pytest tests/browser/ui/test_tasks.py -q`
- `uv run pytest -q`
- `uv tool run ruff check browser/ui/tasks.py browser/app.py tests/browser/ui/test_tasks.py`
- `uv tool run pyright browser/ui/tasks.py browser/app.py`
- Manual smoke: each job shows the status window with working progress and closes it afterwards; busy cursor
  appears/disappears for `Scan`, `Generate`, and bulk `Generate Thumbnails` but not for `Refresh metadata` on
  a folder; a deliberately corrupt sidecar does not stop progress; close/reopen the app while jobs are
  running if practical (no stray exceptions).

## Review

| Date | Reviewer | Outcome | Notes |
|------|----------|---------|-------|
| 2026-10-10 | code-reviewer (subagent) | approved (1 MINOR) | Static review approved at `83606da`; MINOR progress-prefix test gap closed in `5c1282f`. Verification re-run green by tech lead at `83606da`: 100 tests, ruff clean, pyright 0 errors, imports ok (101 after `5c1282f`). Manual GUI smoke deferred to human. |

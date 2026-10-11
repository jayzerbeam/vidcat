# Task 02 — Extract `VideoLibrary` and `Trash` into `browser/library.py`

## Objective

Move file-tree ownership (`PathTree` scanning/rescan/removal/iteration) and move-to-trash behavior out of
`App` into `browser/library.py`, and rewire `App` to use them.

## Context

- Current implementation in `browser/app.py`: `_pathtree` field, `update_filetree` (L603), `rescan_path`
  (L185), `_iter_files` (L597), `_trash_path` field, `_init_trash` (L118), `_send_to_trash` (L169), and
  `delete_paths` (L153).
- `PathTree` API (`util/file/tree.py`): `scan(depth=32, filters=...)`, `clear()`, `dig(path)`,
  `dig_and_remove(path)`, `dirs()`/`files()` generators, `root`, `path_extension_filter(extensions)`.
- `FileTreeUpdate(tree, from_iid)` is the `UiState.file_tree_changed` payload (`browser/ui/state.py`).
  It stays a UI payload: `App` constructs it, `VideoLibrary` does not import it.
- Patterns: tests use `tmp_path` fixtures (`tests/util/file/test_tree.py`); modules under `browser/` avoid
  tkinter/`browser.ui` imports.

## Scope

- Touched: `browser/library.py` (new), `browser/app.py` (tree/trash wiring plus traversal swap in the two
  scan methods), `tests/browser/test_library.py` (new).
- Not touched: `util/file/tree.py`, `browser/ui/*` widgets, `Config`, any metadata/pickling logic.
- Do not change `delete_paths` ordering or its two `selection_changed` emissions in this task (task 05
  collapses them deliberately per `00-spec.md`).

## Guidance

### `VideoLibrary`

```python
class VideoLibrary:
    def __init__(self, root: Path, vid_exts: Sequence[str]) -> None: ...
    @property
    def tree(self) -> PathTree: ...
    def scan(self) -> None: ...
    def rescan(self, path: Path) -> PathTree | None: ...
    def remove(self, path: Path) -> bool: ...
    def iter_files(self, path: Path | None = None) -> Iterator[Path]: ...
```

- `scan()`: `self._tree.scan(filters=[path_extension_filter(self._vid_exts)])`.
- `rescan(path)`: return `None` if `not path.is_dir()`; `pt = self._tree.dig(path)`; return `None` if
  `pt is None`; else `pt.clear()`, `pt.scan(...)` with the same filter, return `pt`.
- `remove(path)`: `return self._tree.dig_and_remove(path)`.
- `iter_files(path=None)`: recursive generator matching today's `_iter_files` order (child dirs first,
  depth-first, then this node's files). With `path=None` walk the whole tree; otherwise walk
  `self._tree.dig(path)` if it resolves, yielding nothing when it does not. Keep the recursion private.

### `Trash`

```python
class Trash:
    def __init__(self, path: Path) -> None: ...
    @property
    def available(self) -> bool: ...
    def send(self, paths: Sequence[Path]) -> list[Path]: ...
```

- `__init__`: if `not path.exists()` then `path.mkdir()`; if `path.is_dir()` record it, else record
  unavailable and print the current message:
  `error:trash directory is not a directory, could not initialize`. Never leave an unassigned sentinel that
  raises later.
- `send(paths)`: return `[]` when unavailable; skip paths where `not p.exists()` (container may have been
  moved); `p.move(self._path / p.name)`; on `OSError` print
  `error: failed to move {p} to trash: {ex}` and continue; append successfully moved paths and return them.

### Rewire `browser/app.py`

1. `__init__`: create `self._library = VideoLibrary(basepath, config.vid_exts)` and
   `self._trash = Trash(config.trash_dir)` next to the other collaborators; add class annotations. Remove
   the `_init_trash(config.trash_dir)` call. Replace the final `self.update_filetree()` with:
   ```python
   self._library.scan()
   self._state.file_tree_changed.emit(FileTreeUpdate(self._library.tree, ""))
   ```
2. `rescan_path(path)`:
   ```python
   pt = self._library.rescan(path)
   if pt is not None:
       self._state.file_tree_changed.emit(FileTreeUpdate(pt, str(path)))
   ```
3. `delete_paths(paths)` keeps its exact ordering: if empty return; if trash unavailable return; if the
   selected path is in `paths` call `self.clear_vidinfo()` and then `self._state.selection_changed.emit(())`
   (both, as today); `removed = self._trash.send(paths)`; for each removed `self._library.remove(p)`; emit
   `paths_removed` when non-empty.
4. `scan_path_metadata(path)`: keep `if not path.is_dir(): return`, but build
   `files = tuple(self._library.iter_files(path))` on the main thread before `status.show()` / thread start
   (this is deliberate delta 1 in `00-spec.md`: traversal no longer runs inside the worker). Replace the queue
   and `_recurse` with `for c, f in enumerate(files, start=1)` producing the same progress message
   `[{c} / {total}] {f.name}` and value `c / total`; keep the existing pickling code untouched.
5. `scan_metadata()`: replace `items: list[Path] = list(self._iter_files())` (inside the worker) with a
   main-thread `items = tuple(self._library.iter_files())` captured before the thread starts; leave the rest
   (throttled progress, sidecar reads, counts) unchanged.
6. Delete `_pathtree`, `_iter_files`, `update_filetree`, `_trash_path`, `_init_trash`, `_send_to_trash`, and
   imports that become unused (`PathTree`, `path_extension_filter`, `Iterator` — verify with ruff).

### Tests — `tests/browser/test_library.py`

Follow `tests/util/file/test_tree.py` fixture style (`tmp_path`, `pytest.fixture`). Suggested cases:

- `VideoLibrary.scan` filters by extension and matches the current `PathTree` structure (subdir + files).
- `rescan` returns the subtree, picks up a file added after the first scan, and drops a file deleted before
  the rescan; returns `None` for a file path and for an unknown path.
- `remove` returns `True`/`False` and drops the entry from the tree.
- `iter_files` walks the whole tree in the documented order and scopes correctly to a subtree; unknown path
  yields nothing.
- `Trash` creates a missing directory; `send` moves files and returns only moved paths; missing paths are
  skipped; `available is False` when the configured path is an existing file and `send` then returns `[]`.

## Acceptance criteria

- [ ] `browser/library.py` contains `VideoLibrary` and `Trash`; no tkinter or `browser.ui` imports.
- [ ] `App` no longer references `PathTree`/`path_extension_filter`/`_pathtree`/`_iter_files`/
      `_trash_path`/`_send_to_trash`/`_init_trash`/`update_filetree`.
- [ ] `delete_paths` ordering unchanged (clear selection → trash → tree removal → `paths_removed`).
- [ ] Both scan methods source files from `VideoLibrary.iter_files` and snapshot on the main thread.
- [ ] An unusable trash directory no longer causes `AttributeError` (delta 7 in `00-spec.md`).
- [ ] No other behavior changes; tests pass.

## Verification

- `uv run pytest tests/browser/test_library.py -q`
- `uv run pytest -q`
- `uv tool run ruff check browser/library.py browser/app.py tests/browser/test_library.py`
- `uv tool run pyright browser/library.py browser/app.py`
- Manual smoke: launch → tree renders; right-click folder → `Refresh files` picks up an added/removed file;
  select a file, then right-click → `Send to trash` on the selection (verify the scrubber released the file
  handle so the move succeeds); multi-select several files → `Send to trash`; verify items disappear from the
  tree and files appear in `.trash`.

## Review

| Date | Reviewer | Outcome | Notes |
|------|----------|---------|-------|
| 2026-10-10 | code-reviewer (subagent) | approved (3 MINOR) | Static review approved at `de50e76`; MINORs fixed in `b057131` (trash OSError test, non-vacuous rescan assertion, scan-flash comment). Verification re-run green by tech lead at `b057131`: 69 tests, ruff clean, pyright 0 errors, import ok. Manual GUI smoke deferred to human. |

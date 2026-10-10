# Task 03 — Extract sidecar metadata into `browser/metadata.py`

## Objective

Move all sidecar metadata concerns out of `App` into `browser/metadata.py`: the metadata schema/constants,
`BulkAction`, read/write/delete/bulk-edit persistence, video-derived metadata generation, and the three
worker-friendly scan loops.

## Context

- Current implementation in `browser/app.py`: `_EMPTY_METADATA` (L17), `load_metadata` (L550),
  `save_metadata` (L356), `delete_metadata` (L235), `edit_metadata` (L252), `scan_metadata` (L374),
  `scan_path_metadata` (L195), `_generate_video_metadata` (L430), `generate_thumbnails` (L317),
  `gen_thumbs_bulk` (L451).
- `MagicSidecar` (`util/file/sidecar.py`) reads/writes pickled bytes into an NTFS alternate data stream
  configured by `Config.metadata_key`. Constructor raises `FileNotFoundError` when the video file does not
  exist; `read`/`delete` raise `FileNotFoundError` when the stream is absent.
- Worker→UI posting still uses `App._post_ui`/`_emit_*` in this task. Task 04 replaces that scaffolding;
  this task must not restructure it beyond what is described.
- Deltas allowed here (see `spec.md`): main-thread file snapshot already done in task 02; `.get` access for
  actor/tag keys; unified missing-sidecar wording; fresh `empty_metadata()` in `delete_metadata`.

## Scope

- Touched: `browser/metadata.py` (new), `browser/app.py`, `browser/ui/actions.py` (re-export only),
  `tests/browser/test_metadata.py` (new).
- Not touched: `util/file/sidecar.py`, `util/video.py`, widgets, `browser/ui/tasks.py` (does not exist yet),
  `browser/session.py` (does not exist yet).
- Do not change progress-message formats or console messages other than the listed deltas.

## Guidance

### Module contents

```python
EMPTY_METADATA: Final[dict[str, Any]] = {...}          # moved verbatim from App

def empty_metadata() -> dict[str, Any]:                # deepcopy(EMPTY_METADATA)

class BulkAction(StrEnum): ...                         # moved from browser/ui/actions.py

class StoredMetadata(NamedTuple):
    metadata: dict[str, Any]
    byte_size: int                                     # 0 when missing/unreadable fallback

class Sidecar(Protocol):                               # structural type for injection
    @property
    def exists(self) -> bool: ...
    def read(self) -> bytes: ...
    def write(self, data: bytes) -> int: ...
    def delete(self) -> None: ...

class MetadataStore:
    def __init__(self, namespace: str, open_sidecar: Callable[[Path, str], Sidecar] = MagicSidecar) -> None: ...
    # exists, read, read_or_empty, write, delete, delete_files, edit, edit_files (semantics below)

def apply_bulk_edit(metadata: dict[str, Any], action: BulkAction, value: str) -> bool: ...
def generate_video_metadata(path, thumb_interval, thumb_height, extract_progress_func, resize_progress_func) -> dict: ...

def refresh_files(files, store, *, on_file, on_progress) -> None: ...
def aggregate_files(files, store, *, on_file, on_progress, interval_s: float = 0.05) -> tuple[dict[str, int], dict[str, int]]: ...
def generate_files(files, store, *, interval: str, height: str, on_file, on_progress, on_fraction) -> None: ...
```

No tkinter imports. `util.file.sidecar`, `util.video`, stdlib only.

### `MetadataStore` semantics (preserve per-call-site behavior)

- `read(path) -> StoredMetadata`: `raw = self._open(path).read()`; `StoredMetadata(pickle.loads(raw), len(raw))`;
  exceptions propagate.
- `read_or_empty(path) -> StoredMetadata`: on success like `read`; on `FileNotFoundError` print
  `{path} does not have a magic sidecar`; on `pickle.UnpicklingError` print
  `{path} does not have valid pickle data, using default`; on any other exception print
  `{path} failed to load metadata: {ex}`; all fallbacks return `StoredMetadata(empty_metadata(), 0)`
  (delta 3 in `spec.md` unifies the bulk-generate wording with this one).
- `write(path, metadata) -> int`: `buf = pickle.dumps(metadata)`; `self._open(path).write(buf)`; return
  `len(buf)` (the caller uses it for the metadata-size label).
- `delete(path)`: `self._open(path).delete()`.
- `delete_files(paths) -> Iterator[Path]`: skip `not p.is_file()`; on exception print
  `error: failed to delete metadata for {p}: {ex}`, print traceback, continue; otherwise yield `p`.
- `edit(path, action, value) -> dict | None`:
  - load with `empty_metadata()` base; `FileNotFoundError` is silent; any other load exception prints
    `error: failed to load metadata for {path}: {ex}`, traceback, and returns `None` (file skipped);
  - call `apply_bulk_edit(metadata, action, value)`;
  - write **unconditionally** (today a no-op edit still creates/updates the sidecar); keep the
    `updating metadata for {path}` print (typo may be fixed, delta 8);
  - on write exception print `error: failed to write metadata for {path}: {ex}`, traceback, return `None`;
  - otherwise return the metadata dict.
- `edit_files(paths, action, value) -> Iterator[tuple[Path, dict]]`: skip `not p.is_file()`; yield
  `(p, metadata)` for non-`None` results.

### `apply_bulk_edit` semantics (exact)

Working on `list(metadata.get("actors", []))` / `list(metadata.get("tags", []))`:

- `ADD_ACTOR`: if `value` not in actors, append and set `metadata["actors"] = sorted(actors)`.
- `DEL_ACTOR`: if `value` in actors, remove and set `metadata["actors"] = actors` (no re-sort).
- `ADD_TAG`: `tag = value.lower()`; if absent, append and set `metadata["tags"] = sorted(tags)`.
- `DEL_TAG`: if `value.lower()` in tags, remove and set `metadata["tags"] = tags` (no re-sort).
- Return whether anything changed; keys not touched otherwise.

### Scan loops

- `refresh_files(files, store, *, on_file, on_progress)`: `total = len(files)`; for `(i, f)` enumerate from 1:
  `on_progress(f"[{i} / {total}] {f.name}", i / total)`; `store.read(f)`; `FileNotFoundError` → continue
  silently; other exception → print `error: failed to load metadata for {f}: {ex}` + traceback, continue;
  success → `on_file(f, stored.metadata)`.
- `aggregate_files(files, store, *, on_file, on_progress, interval_s=0.05)`: keeps the current throttled
  progress (`[{c}/{total}] {path}`, `(c + 1) / total` when `time.time() > last + interval_s`) and the
  current branch behavior: skip non-files; skip when `not store.exists(path)`; on read,
  `pickle.UnpicklingError` → print `failed to unpickle metadata for {path}` (no traceback); other exception
  → print `failed to read metadata for {path}` (no traceback); success → `on_file(path, metadata)` and count
  lowercased actor/tag names, tolerating missing keys via `.get(..., [])` (delta 2). Return
  `(actors, tags)`.
- `generate_files(files, store, *, interval, height, on_file, on_progress, on_fraction)`: for `c, f` in
  `enumerate(files)` (so `c` is the number completed before this file):
  1. `stored = store.read_or_empty(f)` and use `stored.metadata` as the base.
  2. `on_progress(f"[{c + 1} / {total}] {f}", c / total)`.
  3. progress mapping: extract callback → `on_fraction(c / total + (0.5 / total) * fraction)`; resize
     callback → `on_fraction(c / total + (0.5 * fraction + 0.5) / total)`.
  4. try: `metadata |= generate_video_metadata(...)`; `store.write(f, metadata)`.
  5. except: print `error: failed to generate metadata for {f}: {ex}` + traceback.
  6. finally: `on_file(f, metadata)` and `on_fraction((c + 1) / total)` — per-file metadata is emitted even
     on failure; the sidecar is written only on success.
- `generate_video_metadata`: move the current `_generate_video_metadata` body unchanged (it builds dimensions,
  rounded duration, extracts/resizes frames via `VideoThumbnailer`, and includes `thumbnails` when jpgs are
  produced). Keep `thumb_interval`/`thumb_height` as strings and convert exactly as today.

### Rewire `browser/app.py`

- Import `empty_metadata`, `metadata` helpers. Use `self._store = MetadataStore(config.metadata_key)`.
- `load_metadata`: replace the sidecar block with `stored = self._store.read_or_empty(p)`; assign
  `self._metadata = stored.metadata`; set `metadata size: {nice_bytesize(stored.byte_size)}` only when
  `stored.byte_size > 0` (the pre-set `metadata size: none` covers missing/corrupt).
- `save_metadata`: replace pickle/sidecar with
  `size = self._store.write(self._selected_path, self._metadata)`; keep the `update_widgets_from_metadata()`
  call, the prints, and the `metadata size: {round(size / 1000)}KB` line; keep catching `pickle.PickleError`
  separately (`import pickle` stays for the exception type).
- `delete_metadata`: `for f in self._store.delete_files(paths): emit(f, empty_metadata())`.
- `edit_metadata`: keep the `match action` prompt and `block_for_input` guard; replace the loop with
  `for f, metadata in self._store.edit_files(paths, action, val): emit (f, metadata)`.
- `scan_path_metadata`: keep status show and thread scaffolding; worker body becomes
  `metadata.refresh_files(files, self._store, on_file=..., on_progress=...)` where the callbacks wrap
  `self._post_ui(partial(self._emit_file_metadata, ...))` / `self._emit_progress`, then post close.
- `scan_metadata`: worker body replaces the manual loop with
  `actors, tags = metadata.aggregate_files(items, self._store, on_file=..., on_progress=...)`; keep the
  `populating widgets` progress, count emissions, busy-off, and close posts in the current order.
- `generate_thumbnails`: worker calls `metadata.generate_video_metadata(...)` with the existing
  extract/resize progress closures; keep apply/close/busy posts and `gc.collect()`.
- `gen_thumbs_bulk`: worker calls `metadata.generate_files(files, self._store, interval=..., height=..., on_file=..., on_progress=..., on_fraction=...)`, keeping busy/close/gc behavior; `_xprog`/`_rprog`
  closures move into the module.
- Delete `_generate_video_metadata` and `_EMPTY_METADATA`; remove now-unused imports (`MagicSidecar`,
  `VideoThumbnailer`, `ProgressFunc`, `deepcopy` — verify with ruff).
- `browser/ui/actions.py`: replace the `BulkAction` definition with
  `from browser.metadata import BulkAction` and keep the name importable for widgets (delta/decision 4).
  Check import direction: `browser.metadata` must not import `browser.ui`.

### Tests — `tests/browser/test_metadata.py`

Use an in-memory `FakeSidecar` for `tests/browser/`-style tests (no NTFS dependency):
a dict of `namespace -> bytes` keyed by path, with `exists`, `read` (raises `FileNotFoundError` when empty),
`write`, `delete`; a factory `lambda path, namespace: FakeSidecar(...)` matching the `Sidecar` protocol.
Cover:

- `empty_metadata()`: returns independent copies (mutating one does not affect `EMPTY_METADATA` or another).
- `apply_bulk_edit`: add sorts; duplicate add is a no-op; delete preserves order and removes; tag actions
  lowercase; tuple values coerce to list; missing keys treated as empty; return value reflects change.
- `MetadataStore`: read round-trip and `byte_size`; `read` on absent raises; `read_or_empty` returns empty and
  `byte_size == 0` for absent and corrupt payloads (capture stdout or ignore logs); `write` returns the
  payload length; `delete_files` skips non-files and continues past errors; `edit` writes even when nothing
  changed, returns `None` when load or write raises, and returns the updated dict on success.
- `refresh_files`: absent skipped silently; corrupt logged with traceback; progress sequence
  `1/2, 2/2`; `on_file` receives `(path, dict)`.
- `aggregate_files`: counts lowercased duplicates; `exists=False` skipped; corrupt prints the short message;
  missing `actors`/`tags` keys tolerated; with `interval_s=0` progress is emitted per file.
- `generate_files`: monkeypatch `browser.metadata.generate_video_metadata` to return a fixed dict; verify
  write on success, `on_file` on generation failure too, and the exact fraction sequence for a 2-file run
  (the extract/resize split math).
- Optional: `generate_video_metadata` with `monkeypatch.setattr(browser.metadata, "VideoThumbnailer", Fake)`
  asserting the returned schema.

## Acceptance criteria

- [ ] `browser/metadata.py` contains all moved logic; no tkinter/`browser.ui` imports; `MetadataStore` is
      injectable via the sidecar factory.
- [ ] `App` no longer contains `_EMPTY_METADATA`, `_generate_video_metadata`, direct `MagicSidecar` or
      `pickle.loads`/`dumps` usage (except the `PickleError` except-clause).
- [ ] `browser/ui/actions.py` re-exports `BulkAction`; no widget file changed.
- [ ] Sidecar edge semantics preserved per the invariant list; deltas 2, 3, 4, 8 applied only.
- [ ] Progress messages/values and per-file emission rules match the invariant list.
- [ ] New tests pass.

## Verification

- `uv run pytest tests/browser/test_metadata.py -q`
- `uv run pytest -q`
- `uv tool run ruff check browser/metadata.py browser/app.py browser/ui/actions.py tests/browser/test_metadata.py`
- `uv tool run pyright browser/metadata.py browser/app.py`
- Manual smoke: select a file → size/duration/resolution and `metadata size` populate; `Save` (Ctrl+S) then
  reselect → values persist and size label updates; context menu `Add/Del actor`, `Add/Del tag` on multiple
  files; `Clean` on files with sidecars; `Refresh metadata` on a folder; Filters `Scan` → counts appear;
  `Generate` on a file; `Generate Thumbnails` on several files → per-file status progress, sidecars written,
  failures logged but traversal continues.

## Review

| Date | Reviewer | Outcome | Notes |
|------|----------|---------|-------|
| | | | |

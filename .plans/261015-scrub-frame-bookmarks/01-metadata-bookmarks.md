# Task 1: Bookmark schema + pure helpers in `browser/metadata.py`

## Objective

Bookmarks are part of the metadata schema and can be parsed, added (sorted, deduped) and
removed by pure functions over the metadata dict, with tests.

## Context

- `browser/metadata.py` is the metadata module: `EMPTY_METADATA` at `:13-19`,
  `empty_metadata()` (deepcopy) at `:22-24`, and the precedent for pure dict-mutating
  helpers: `apply_bulk_edit(metadata, action, value) -> bool` at `:138-167` (mutates in
  place, returns whether anything changed, tolerates missing keys and coerces tuples).
- Metadata travels as a **pickled plain dict** sidecar (`MetadataStore.read/write`,
  `:65-85`, `:81-85`); entries must stay plain dicts, never app-only classes.
- Tests use the `FakeSidecar`+`MetadataStore` injection pattern
  (`tests/browser/test_metadata.py:22-60`); new pure-function tests need no fixtures.

## Scope

**Changed:** `browser/metadata.py`, `tests/browser/test_metadata.py`.
**Out of scope:** everything UI (state.py, session.py, app.py, scrub_frame.py,
bookmark_frame.py), `thumbnailer.py`, `globtag.py` (their defaults/round-trips stay
untouched; readers/sidecar round-trips are tolerant per spec).

## Guidance

- Add `"bookmarks": []` to `EMPTY_METADATA` **before** the closing brace (after
  `"thumbnails"`), so `empty_metadata()` deep-copies it too.
- Define `Bookmark` as a NamedTuple with field order `time_ms: int`, `frame_no: int | None`,
  `name: str` (placement near the top of the module, e.g. after `EMPTY_METADATA`, keeps it
  importable early by later tasks; mirror the document-per-type docstring style used in
  `browser/ui/state.py`).
- `parse_bookmarks(metadata: Mapping[str, Any]) -> tuple[Bookmark, ...]`:
  - missing/absent key or a non-list value → `()`;
  - skip entries that are not dicts or whose `time_ms` is not a plain `int`
    (reject `bool`, which is an `int` subclass — decide the guard deliberately);
  - for surviving entries: coerce `frame_no` to `int` or the neutral `None`, and `name` to
    `str` (neutral `""`) so malformed fields degrade instead of poisoning the tuple;
  - return entries **sorted by `time_ms`** (a stable `sorted` over the parsed list).
- `insert_bookmark(metadata: dict[str, Any], bookmark: Bookmark) -> bool`:
  - read `metadata.get("bookmarks", [])` (tolerate absence);
  - if any existing entry already carries the same `time_ms` → return `False` without
    touching the list (duplicate rejection is by identity-of-time, per spec decision 1);
  - otherwise insert `{"time_ms": ..., "frame_no": ..., "name": ...}` **as a plain dict**
    (not the NamedTuple — do not pickle app classes) into sorted position by `time_ms`,
    assign the resulting list back to `metadata["bookmarks"]` as a `list`, return `True`.
- `delete_bookmark(metadata: dict[str, Any], time_ms: int) -> bool`:
  - rebuild the list without any entry whose `time_ms` matches; return whether an entry was
    removed; keep the list sorted.
- Keep all three functions grouped with the other pure helpers (near `apply_bulk_edit`);
  do not reorder other definitions. No I/O, no printing, no side effects beyond the dict.

## Acceptance criteria

- [ ] `EMPTY_METADATA` contains `"bookmarks": []` and `empty_metadata()` deep-copies it
      (mutating one copy must not affect `EMPTY_METADATA` or another copy).
- [ ] `parse_bookmarks` returns `()` for metadata without the key, for a non-list value,
      and skips non-dict entries and entries lacking a valid integer `time_ms`.
- [ ] `parse_bookmarks` returns `tuple[Bookmark, ...]` sorted by `time_ms` on input that is
      stored out of order, with `frame_no`/`name` neutralized when untypeable.
- [ ] `insert_bookmark` inserts into sorted position, assigns a list of plain dicts
      (`dict`, not `Bookmark`) back to `metadata["bookmarks"]`, and returns `True`.
- [ ] `insert_bookmark` returns `False` and leaves the list unchanged for a duplicate
      `time_ms`; works when `metadata` has no `bookmarks` key yet.
- [ ] `delete_bookmark` removes exactly the matching `time_ms`, returns `True` when found
      and `False` (list unchanged) when missing.
- [ ] Round-trip check: `insert_bookmark` into `empty_metadata()` then
      `parse_bookmarks` returns the same `Bookmark` back (add → read consistency).

## Verification

```
uv run pytest tests/browser/test_metadata.py
uv tool run ruff check browser/metadata.py tests/browser/test_metadata.py
uv tool run pyright browser/metadata.py tests/browser/test_metadata.py
```

Per repo AGENTS.md only lint/type issues in these modified files are relevant.

## Review record

Reviewed commit `88b4f5981fd86e8b06e11c0e695b5659a4d783be` (code-reviewer, 2026-10-16).

**Verdict: approved.** All 7 acceptance criteria pass; verification commands re-run by the
reviewer and by the tech lead: `uv run pytest tests/browser/test_metadata.py` 29 passed;
ruff and pyright clean on both changed files. The reviewer accepted the implementer's
judgment calls: `Bookmark` placement after `empty_metadata()`, strict-type neutralization of
malformed fields (no `int()`/`str()` conversion), the bool guard applied to `frame_no` as
well as `time_ms`, and normalization of the stored list on successful mutations.

Follow-ups:
- NIT (applied in `2be58c8996c653a4d85fa5543810320bb9ebf44d`): the test suite now pins the
  strict acceptance boundary for `frame_no` (`3.0`/`"3"` → `None`).
- NIT (accepted, no action): a successful insert/delete re-encodes surviving entries and
  drops unknown extra keys; acceptable while the stored entry schema is pinned to the three
  fields.

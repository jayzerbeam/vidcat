# Spec: Session restage on store-side metadata events (bulk-edit clobber fix)

Date: 2026-10-19
Repo: `C:\repos\vidcat` (Python 3.14 / Tkinter desktop app, uv-managed)

## Problem

Bulk edits made through the `FileMetaTreeviewFrame` context menu are silently reverted by the
next Ctrl+S. Root cause (verified against the code, not conjecture):

1. Right-clicking a row calls `selection_set` (`browser/ui/file_meta_treeview.py` ~179-180),
   firing `<<TreeviewSelect>>` → `App.select_paths` → `VideoSession._load`
   (`browser/session.py` ~120). `_load` copies the sidecar into `VideoSession._metadata` and
   `_show()` (~141-142, ~135-151) seeds `state.meta_actors` / `state.meta_tags` / `state.meta_title`
   and other Tk variables. The info pane (`ActorTagPane`, `browser/ui/video_info_frame.py` ~138/144)
   renders those variables via `EditableList` listvariable bindings.
2. A bulk edit (`Add/Del actor/tag`) goes through `App.edit_metadata` (`browser/app.py` ~169-189)
   → `MetadataStore.edit_files` → `edit` (`browser/metadata.py` ~116-147), which applies
   `apply_bulk_edit` and writes the sidecar, then `App` emits `file_metadata_changed` with the
   freshly written metadata.
3. The **only** subscriber to `file_metadata_changed` is
   `FileMetaTreeviewFrame._on_file_metadata` (`file_meta_treeview.py` ~127, ~134-142), which
   refreshes tree columns. `VideoSession` never subscribes and is never restaged, so
   `_metadata` and the Tk variables go stale.
4. Ctrl+S → `VideoSession.save` (`session.py` ~64-81) reads the stale variables back into the
   stale `_metadata` and writes it to the store — **clobbering the just-persisted bulk edit**.

Two more latent bugs share the same stale-session mechanism and are fixed by the same change:

- **Bulk "Generate Thumbnails"** on the selected file: `generate_files`
  (`metadata.py` ~332-370) writes new thumbnails/video_properties to the store and emits;
  the session keeps the old thumbnails; Ctrl+S writes the old thumbnails back, clobbering
  generation.
- **"Clean"** (`App.delete_metadata`, `app.py` ~144-146) on the selected file: the sidecar is
  deleted and `empty_metadata()` is emitted, but the session/pane keep the old title/actors/tags;
  Ctrl+S resurrects the deleted metadata.

## Goal

Fix the data-clobbering bug and converge the app on one consistent state-flow pattern, such that:

1. More editable views of metadata can easily be added in future.
2. Implementations are pattern-consistent.
3. Simplicity is favoured.
4. No bugs remain (including the two latent same-class bugs above).

## Agreed design

Converge on the pattern bookmarks already use: **store-side events are authoritative; the session
is the single staged state for the selected file; views render from what the session pushes
(Tk variables + signals) and post edits via actions/buffers.**

The production diff target is ~20 lines with no new abstractions:

1. **`browser/ui/state.py` — split the `file_metadata_changed` signal by producer.**
   - Add `selected_metadata_changed: Signal[FileMetadataChanged]` (reuse the same `NamedTuple`
     type). Emitted **only** by the session for the selected file's staged view; the payload is
     the live `_metadata` dict — consume synchronously, never retain.
   - `file_metadata_changed` becomes store-side only (emitters: `app.py` edit/delete/scan/thumb
     flows). Its payload contract: a snapshot; every current store-side emitter passes a fresh
     dict it never retains or mutates afterwards; consumers may read it synchronously.
   - Add a one-line re-entrancy rule to the `Signal` class docstring: handlers must not
     synchronously emit a signal their own handler consumes.
2. **`browser/session.py` — the fix.**
   - In `__init__`: `state.file_metadata_changed.connect(self._on_stored_metadata)`.
   - New handler: if `change.path != self._selected_path`, return; otherwise
     `self._metadata = dict(change.metadata)` and call `self._show()`. Full-replace restage —
     no field-by-field merge.
   - `_show()` emits `selected_metadata_changed` instead of `file_metadata_changed`.
   - Loop-safety: the session is connected only to the store-side signal, never to the one it
     emits; `_show()`'s emission goes to the treeview, which does not emit. One render per
     event, no recursion, no identity guards.
   - Document the semantics on `_show()`/the handler: a store-side event for the selected file
     **fully restages** staged state; unsaved buffer edits (title typing, pane actor/tag edits)
     are discarded — *reload from disk wins*. This is deliberate: it is what makes "Clean"
     fully effective.
3. **`browser/ui/file_meta_treeview.py` — one added line:** connect the existing
   `_on_file_metadata` handler to `selected_metadata_changed` as well (both signals carry the
   same tuple shape), so the selected tree row continues to track staged state
   (preserving current behaviour).
4. **No changes** to: `browser/app.py` emitters, `MetadataStore`, `ActorTagPane`/`EditableList`,
   filter/highlight/bookmark UI, `vidcat.pyw`.

### Event flow after the fix

```
BEFORE (bug)                                   AFTER (fix)
─────────────────────────                      ─────────────────────────
store write (edit/clean/thumb-gen)             store write (edit/clean/thumb-gen)
  │                                              │
  ▼                                              ▼
state.file_metadata_changed                    state.file_metadata_changed
  │                                              │
  ├─► FileMetaTreeviewFrame (row only)           ├─► FileMetaTreeviewFrame (row only)
  │                                              │
  └─► (nobody else)                              └─► VideoSession._on_stored_metadata
        VideoSession._metadata: STALE                  │ path matches selection?
        Tk vars: STALE                                 ▼
        Ctrl+S ⇒ writes stale state               _metadata = dict(payload); _show()
        ⇒ CLOBBERS the store write                  │
                                                    ├─► state.selected_metadata_changed
                                                    │     └─► FileMetaTreeviewFrame (row again)
                                                    ├─► Tk vars re-seeded (actors/tags/title/thumbs)
                                                    └─► Ctrl+S ⇒ persists the restaged state
```

## Decisions and rationale

- **Split by producer, not by payload type.** The two signals carry the same tuple shape but
  different liveness contracts (live staged dict vs store snapshot). Reusing
  `FileMetadataChanged` keeps the diff at ~20 lines; the contracts are documented per signal.
- **Full-replace restage, no merge.** A field-by-field merge would reintroduce exactly the
  special cases this fix removes. The staged buffer is disposable by design.
- **"Reload from disk wins" (behavioural consequence, accepted in discussion):** a store-side
  event for the selected file discards unsaved buffer edits. Example: typing a title, then
  clicking the global "Scan" button (`App.scan_metadata` emits store-side events for every file
  including the selected one), reverts the unsaved title typing. Accepted because the
  alternative — preserving in-progress title text through restages — reintroduces a special
  case and makes "Clean" only partially effective until save.
- **Shallow copy in the handler is safe (verified):** every store-side emitter passes a dict it
  just built (`store.read` unpickles fresh per file; `empty_metadata()` deep-copies;
  `edit_files`/`generate_files`/`aggregate_files`/`refresh_files` yield fresh dicts and drop
  them after emission), and session-side writers only replace top-level keys (`save()` assigns
  `title`/`actors`/`tags`; `apply_for` uses `|=`; bookmark helpers assign `metadata["bookmarks"]`)
  — nothing mutates nested lists in place. Implementers must re-verify this before relying on it.
- **Dual treeview connection** preserves today's behaviour of the selected tree row and causes
  one harmless duplicate (idempotent) row render when a store-side event targets the selected
  path: once from the store payload, once from the session restage. Accepted for simplicity.

## Modifications

- `browser/ui/state.py`
  - Added: `UiState.selected_metadata_changed` signal.
  - Changed: `FileMetadataChanged` docstring describes the shared shape and defers the liveness
    contract to the producing signal; contract comments on the two signal attributes; one-line
    re-entrancy rule in the `Signal` docstring.
- `browser/session.py`
  - Added: store-side subscription and `_on_stored_metadata` restage handler in `VideoSession`.
  - Changed: `_show()` emits `selected_metadata_changed`; semantics documented.
- `browser/ui/file_meta_treeview.py`
  - Added: one `connect` of the existing `_on_file_metadata` handler to
    `selected_metadata_changed`.
- `tests/browser/test_session.py`
  - Changed: `FakeSignal` gains `connect` (invokes handlers on emit), `FakeState` gains
    `selected_metadata_changed`, exact-order log assertions updated, new coverage (a)-(f)
    listed in `03-restage-test-coverage.md`.

## In scope

- Only the files listed above plus their tests.
- Docstring/comment updates that document the pattern and the signal contracts.

## Out of scope

- Persisting `byte_size` in `FileMetadataChanged`; `meta_size` refresh after bulk-edit writes.
- Rerouting `EditableList` edits through actions/buffers.
- Splitting/preserving per-field staged edits across restages.
- Any UI behaviour change beyond the restage semantics described here.
- Reformatting untouched files.

## Risks / open questions

- **Shallow-copy safety** depends on the "writers replace top-level keys" invariant holding.
  New code that mutates nested structures of a payload after emission would break it; the
  handler docstring should state the invariant so future writers see it. (No open
  question — verified today, re-verify at implementation time.)
- **Unsaved-edit discard** is user-visible (title typed, then a store-side event arrives for the
  selected file → typing lost). Accepted deliberately; do not "fix" with a merge.
- `tests/browser/ui/test_file_meta_treeview.py` uses a real `UiState`
  (`make_frame`, ~47-50), so the added signal and connection require **no** test changes there;
  there is no existing test for `_on_file_metadata` and none is added (the dual connection is
  type-checked and behaviourally covered at session level).

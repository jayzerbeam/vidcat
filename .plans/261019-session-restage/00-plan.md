# Plan: Session restage on store-side metadata events

Spec: see `00-spec.md`. Status values: `pending` / `in-progress` / `done` / `blocked`.

| Task | File | Summary | Depends on | Status |
|------|------|---------|------------|--------|
| 1 | `01-state-signal-split.md` | Split `file_metadata_changed` by producer: add `selected_metadata_changed` to `UiState`, document per-signal payload contracts and the `Signal` re-entrancy rule (`browser/ui/state.py` only) | — | done |
| 2 | `02-session-restage.md` | `VideoSession` subscribes to store-side events and fully restages on match; `_show()` emits `selected_metadata_changed`; treeview dual connection; minimal test-fixture/log-assertion updates to keep the suite green | 01 | done |
| 3 | `03-restage-test-coverage.md` | `FakeSignal.connect` with handler invocation, tolerant `split_list` fixture, new restage coverage (a)-(f): selected/non-selected restage, the three clobber scenarios, no emission loop | 02 | done |

Execution order: 01 → 02 → 03.

Notes for the executor:

- Each task leaves the full suite green; tasks are independently reviewable and can be
  committed separately. Tasks 02 and 03 touch `tests/browser/test_session.py` in disjoint
  areas (02: `FakeState` attribute + mechanical log-assertion rename; 03: `FakeSignal` +
  fixture + new tests); if executed by one developer they may be combined into a single
  commit, but review them together as one behavioural change.
- Production diff target across 01+02 is ~20 lines. If an implementation grows well beyond
  that (new abstractions, field merges, identity guards), it has drifted from the agreed
  design — stop and re-read `00-spec.md`.
- Line numbers cited in the task files are approximate (`~`) and refer to the state of the
  repo at planning time; they will drift as earlier tasks land.

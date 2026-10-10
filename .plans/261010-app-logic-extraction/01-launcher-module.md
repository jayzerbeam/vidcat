# Task 01 — Extract OS launching into `browser/launcher.py`

## Objective

Move `App.goto_path` and `App.play_file` into a reusable `Launcher` class in a new `browser/launcher.py`,
and have `App` delegate to it with identical behavior.

## Context

- Current implementation: `browser/app.py`, methods `goto_path` (approx. L510) and `play_file` (approx.
  L527). They use `os`, `subprocess`, `platform`, and `Config.vid_player` / `Config.vid_player_args`.
- Planned architecture (see `spec.md`): `browser/launcher.py` imports stdlib only; widgets never import it;
  `App` constructs it once in `__init__` and delegates.
- Patterns to follow: flat modules under `browser/` (`config.py`, `app.py`); dataclass-free explicit
  `__init__` assignments; type annotations on all public methods.

## Scope

- Touched: `browser/launcher.py` (new), `browser/app.py` (delegation only), `tests/browser/test_launcher.py`
  (new).
- Not touched: `browser/config.py`, any widget or UI file, `util/*`.
- Do not "harmonize" the platform fallbacks: `reveal` uses `subprocess.Popen` for macOS/Linux while `play`'s
  fallback uses `subprocess.call`; keep that asymmetry. Do not change any console message.

## Guidance

### Create `browser/launcher.py`

`Launcher` holds the configured player and its arguments, so `App` does not pass them on every call:

```python
class Launcher:
    def __init__(self, vid_player: Path | None, vid_player_args: Sequence[str]) -> None: ...
    def reveal(self, path: Path) -> None: ...          # old goto_path
    def play(self, path: Path, start_ms: int = 0) -> None: ...   # old play_file
```

Behavior to preserve exactly:

- `reveal(path)`: return silently if `not path.exists()`; `path = path.resolve()`; platform match:
  - Windows: `os.startfile(path)`
  - Darwin: `subprocess.Popen(["open", path])`
  - other/Linux: `subprocess.Popen(["xdg-open", path])`, catching `FileNotFoundError` and printing
    `error: failed to open {path}: {ex}`.
- `play(path, start_ms)`:
  - return silently if `not path.is_file()`; `path = path.resolve()`.
  - If `vid_player is not None and vid_player.exists()`: build `argv = [vid_player.name, f'"{path}"']`;
    if `vid_player_args` is non-empty, extend with each arg with `%t_ms` replaced by `str(start_ms)` and
    `%t_sec` replaced by `str(start_ms / 1000)`; then `os.spawnv(os.P_NOWAIT, vid_player, argv)`.
  - Otherwise: Windows `os.startfile(path)`; Darwin `subprocess.call(("open", path))`; Linux
    `subprocess.call(("xdg-open", path))`.
- Keep the imports of `os`, `subprocess`, `platform` inside `launcher.py`.

### Rewire `browser/app.py`

1. In `__init__`, after the other collaborators: `self._launcher = Launcher(config.vid_player, config.vid_player_args)`.
   Add a `_launcher: Launcher` class annotation alongside the existing ones.
2. Replace bodies:
   - `show_in_explorer(path)` → `self._launcher.reveal(path)`
   - `activate_path(path)` → `if path.is_file(): self._launcher.play(path)`
   - `play_from_ms(ms)` → `if self._selected_path.is_file(): self._launcher.play(self._selected_path, start_ms=ms)`
     (the `_selected_path` field is still owned by `App` until task 05; do not change selection logic here).
3. Delete `goto_path` and `play_file`.
4. Remove imports that are now unused in `app.py` (`os`, `subprocess`, `platform` — verify with ruff).

### Tests — `tests/browser/test_launcher.py`

Create the file following the style of `tests/util/file/test_tree.py`. Suggested cases:

- `play` with no player + Windows: monkeypatch `browser.launcher.platform.system` to `"Windows"` and
  `browser.launcher.os.startfile`, assert called with the resolved path.
- `play` with a configured player: monkeypatch `browser.launcher.os.spawnv` to capture args; assert
  `os.P_NOWAIT` flag, `argv[0] == player.name`, the path is quoted in `argv[1]`, and `%t_ms` / `%t_sec`
  placeholders are interpolated.
- `play` on a missing/non-file path: `os.startfile` and `os.spawnv` are not called.
- `reveal` on missing path: platform functions not called.
- `reveal` on Windows: `os.startfile` called with resolved path.
- One non-Windows branch per function using monkeypatched `platform.system` and monkeypatched
  `subprocess.Popen` / `subprocess.call` (no real subprocesses in tests).

Use `monkeypatch.setattr` on the `browser.launcher` module attributes (e.g.
`monkeypatch.setattr(launcher_module.platform, "system", lambda: "Windows")`), never on the global modules,
so other tests are unaffected.

## Acceptance criteria

- [ ] `browser/launcher.py` exists and contains only `Launcher` (plus imports/helpers if needed); no tkinter
      import.
- [ ] `App.goto_path` and `App.play_file` are gone; `activate_path`, `show_in_explorer`, `play_from_ms`
      delegate to `self._launcher`.
- [ ] Player argv behavior and all fallback branches match the previous implementation (checklist above).
- [ ] `tests/browser/test_launcher.py` covers player interpolation, Windows fallback, and no-op paths.
- [ ] No other file changed.
- [ ] `understandability`: `App.__init__` still reads as a wiring list (config, state, library/store/... ,
      launcher, jobs).

## Verification

- `uv run pytest tests/browser/test_launcher.py -q`
- `uv run pytest -q` (all existing tests still pass)
- `uv tool run ruff check browser/launcher.py browser/app.py tests/browser/test_launcher.py`
- `uv tool run pyright browser/launcher.py browser/app.py`
- Manual smoke: right-click a file → `[info]` opens Explorer; right-click a folder → `[info]`; double-click a
  file plays it; scrub tab `Open` plays from the slider position; with a configured `vid_player`, confirm the
  player receives the quoted path and start time.

## Review

| Date | Reviewer | Outcome | Notes |
|------|----------|---------|-------|
| | | | |

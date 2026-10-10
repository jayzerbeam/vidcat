import os
import platform
import subprocess
from collections.abc import Sequence
from pathlib import Path


class Launcher:
    """Opens paths with OS programs: the file explorer for reveal, the configured or default player for play."""

    _vid_player: Path | None
    _vid_player_args: tuple[str, ...]

    def __init__(self, vid_player: Path | None, vid_player_args: Sequence[str]) -> None:
        self._vid_player = vid_player
        self._vid_player_args = tuple(vid_player_args)

    def reveal(self, path: Path) -> None:
        """Open path in the system file explorer."""
        if not path.exists():
            return
        path = path.resolve()

        match platform.system():
            case "Windows":
                os.startfile(path)
            case "Darwin":
                subprocess.Popen(["open", path])
            case _:  # linux
                try:
                    subprocess.Popen(["xdg-open", path])
                except FileNotFoundError as ex:
                    print(f"error: failed to open {path}: {ex}")

    def play(self, path: Path, start_ms: int = 0) -> None:
        """Play a video file, optionally starting at start_ms.

        Args:
            path: video file to play.
            start_ms: start position in milliseconds; substituted into player argument placeholders
                ``%t_ms`` and ``%t_sec``.
        """
        if not path.is_file():
            return
        path = path.resolve()

        player = self._vid_player
        if player is not None and player.exists():
            argv = [player.name, f'"{path}"']
            if len(self._vid_player_args) > 0:
                argv.extend(
                    s.replace("%t_ms", str(start_ms)).replace("%t_sec", str(start_ms / 1000))
                    for s in self._vid_player_args
                )
            os.spawnv(os.P_NOWAIT, player, argv)
        else:
            match platform.system():
                case "Windows":
                    os.startfile(path)
                case "Darwin":
                    subprocess.call(("open", path))
                case _:  # linux
                    subprocess.call(("xdg-open", path))

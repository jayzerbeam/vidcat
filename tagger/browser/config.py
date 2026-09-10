import json
from pathlib import Path
from typing import Final

CONFIG_NAME: Final[str] = "browser.cfg.json"
DEFAULT_VID_EXTS: Final[tuple[str, ...]] = (
    ".avi",
    ".mp4",
    ".m4v",
    ".mkv",
    ".mpg",
    ".mpeg",
    ".wmv",
    ".flv",
    ".f4v",
    ".mov",
)
DEFAULT_METADATA_KEY: Final[str] = "video_metadata"  # for the json within the sidecar files
DEFAULT_TRASH_DIR: Final[str] = ".trash"  # can be absolute or relative


class Config:
    _vid_exts: tuple[str, ...]
    _vid_player: Path | None
    _vid_player_args: tuple[str, ...]
    _metadata_key: str
    _trash_dir: Path

    def __init__(self) -> None:
        self._vid_exts = DEFAULT_VID_EXTS
        self._vid_player = None
        self._vid_player_args = ()
        self._metadata_key = DEFAULT_METADATA_KEY
        self._trash_dir = Path(DEFAULT_TRASH_DIR)

    def load(self, path: Path) -> None:
        try:
            with path.open("r") as f:
                data = json.load(f)
                self._metadata_key = data.get("metadata_key", DEFAULT_METADATA_KEY)

                self._trash_dir = Path(data.get("trash_dir", DEFAULT_TRASH_DIR))
                if not self._trash_dir.is_dir():
                    self._trash_dir = Path(DEFAULT_TRASH_DIR)

                if "vid_player" in data and Path(data["vid_player"]).exists():
                    self._vid_player = Path(data["vid_player"])

                if isinstance(data.get("vid_player_args", None), list):
                    self._vid_player_args = tuple(data["vid_player_args"])

                if isinstance(data.get("vid_exts", None), list):
                    self._vid_exts = data["vid_exts"]
        except Exception as ex:
            print(f"error: failed to load config file, using default: {ex}")

    @property
    def metadata_key(self) -> str:
        return self._metadata_key

    @property
    def trash_dir(self) -> Path:
        return self._trash_dir

    @property
    def vid_exts(self) -> tuple[str, ...]:
        return self._vid_exts

    @property
    def vid_player(self) -> Path | None:
        return self._vid_player

    @property
    def vid_player_args(self) -> tuple[str, ...]:
        return self._vid_player_args

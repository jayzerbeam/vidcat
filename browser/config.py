import json
from collections.abc import Sequence
from pathlib import Path
from typing import Final

DEFAULT_METADATA_KEY: Final[str] = "video_metadata"  # for the json within the sidecar files
DEFAULT_THUMB_HEIGHT: Final[int] = 200
DEFAULT_THUMB_INTERVAL: Final[int] = -30
DEFAULT_TRASH_DIR: Final[str] = ".trash"  # can be absolute or relative
DEFAULT_HIDDEN_COLUMNS: Final[tuple[str, ...]] = ()  # filetree column ids to hide at startup, the rest stay shown
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


class Config:
    _metadata_key: str
    _thumb_height: int
    _thumb_interval: int
    _trash_dir: Path
    _vid_exts: tuple[str, ...]
    _vid_player: Path | None
    _vid_player_args: tuple[str, ...]
    _hidden_columns: tuple[str, ...]

    def __init__(self) -> None:
        self._metadata_key = DEFAULT_METADATA_KEY
        self._thumb_height = DEFAULT_THUMB_HEIGHT
        self._thumb_interval = DEFAULT_THUMB_INTERVAL
        self._trash_dir = Path(DEFAULT_TRASH_DIR)
        self._vid_exts = DEFAULT_VID_EXTS
        self._vid_player = None
        self._vid_player_args = ()
        self._hidden_columns = DEFAULT_HIDDEN_COLUMNS
        self._path: Path | None = None

    def load(self, path: Path) -> None:
        self._path = path

        try:
            with path.open("r") as f:
                data = json.load(f)
                self._metadata_key = data.get("metadata_key", DEFAULT_METADATA_KEY)
                self._thumb_height = data.get("thumb_height", DEFAULT_THUMB_HEIGHT)
                self._thumb_interval = data.get("thumb_interval", DEFAULT_THUMB_INTERVAL)
                self._trash_dir = Path(data.get("trash_dir", DEFAULT_TRASH_DIR))

                if "vid_player" in data and Path(data["vid_player"]).exists():
                    self._vid_player = Path(data["vid_player"])

                if isinstance(data.get("vid_player_args", None), list):
                    self._vid_player_args = tuple(data["vid_player_args"])

                if isinstance(data.get("vid_exts", None), list):
                    self._vid_exts = tuple(data["vid_exts"])

                if isinstance(data.get("hidden_columns", None), list):
                    self._hidden_columns = tuple(data["hidden_columns"])
        except Exception as ex:
            print(f"error: failed to load config file, using default: {ex}")

    def write_default(self, path: Path) -> None:
        """write the default settings to path. for first runs where no config file exists yet."""
        self._path = path
        self.save()

    def save(self) -> None:
        """rewrite the config file with the loaded settings. only valid after a successful load."""
        # the load path is unknown until load() records it
        if self._path is None:
            return

        data = {
            "metadata_key": self._metadata_key,
            "thumb_height": self._thumb_height,
            "thumb_interval": self._thumb_interval,
            "trash_dir": str(self._trash_dir),
            "vid_exts": list(self._vid_exts),
            "hidden_columns": list(self._hidden_columns),
        }
        if self._vid_player is not None:
            data["vid_player"] = str(self._vid_player)

        if self._vid_player_args:
            data["vid_player_args"] = list(self._vid_player_args)

        try:
            with self._path.open("w") as f:
                json.dump(data, f, indent="\t")
        except Exception as ex:
            print(f"error: failed to save config file: {ex}")

    @property
    def metadata_key(self) -> str:
        return self._metadata_key

    @property
    def thumb_height(self) -> int:
        return self._thumb_height

    @property
    def thumb_interval(self) -> int:
        return self._thumb_interval

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

    @property
    def hidden_columns(self) -> tuple[str, ...]:
        return self._hidden_columns

    def set_hidden_columns(self, hidden: Sequence[str]) -> None:
        self._hidden_columns = tuple(hidden)

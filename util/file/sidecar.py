import platform
from enum import StrEnum
from pathlib import Path


class Platform(StrEnum):
    WINDOWS = "Windows"
    LINUX = "Linux"
    MAC = "Darwin"


class MagicSidecar:
    """Class for reading/writing "magic" sidecar files.

    On windows this will be Alternate Data Streams.
    On macos/linux this will be extended attributes
    """

    _path: Path
    _sidecar: Path
    _namespace: str

    def __init__(self, path: Path, namespace: str):
        """Create a new magic sidecar file for path

        path: the the Path of the main file
        namespace: on windows the name of the alternate data stream. on macos/linux the user. xattr name
        """

        if not path.is_file():
            raise FileNotFoundError(f"cannot create sidecar for non-existent file: {path}")

        self._path = path
        self._namespace = namespace

        match platform.system():
            case Platform.WINDOWS:
                self._sidecar = Path(f"{self._path}:{self._namespace}:$DATA")

            case Platform.LINUX | Platform.MAC:
                raise NotImplementedError("linux/mac magic sidecar not yet implemented")

            case _:
                raise OSError("unknown platform")

    def _sidecar_check(self) -> None:
        # this shouldn't ever happen
        if not hasattr(self, "_sidecar"):
            raise ValueError(f"no sidecar for {self._path}")

        if not self._sidecar.exists():
            raise FileNotFoundError(f"{self._namespace} alternate data stream does not exist for {self._path}")

    @property
    def exists(self) -> bool:
        if not hasattr(self, "_sidecar"):
            return False

        return self._sidecar.exists()

    def read(self) -> bytes:
        match platform.system():
            case Platform.WINDOWS:
                self._sidecar_check()
                return self._sidecar.read_bytes()

            case Platform.LINUX | Platform.MAC:
                raise NotImplementedError("linux/mac magic sidecar not yet implemented")

            case _:
                raise OSError("unknown platform")

    def write(self, data: bytes) -> int:
        match platform.system():
            case Platform.WINDOWS:
                if not hasattr(self, "_sidecar"):
                    raise ValueError(f"no sidecare for {self._path}")

                return self._sidecar.write_bytes(data)

            case Platform.LINUX | Platform.MAC:
                raise NotImplementedError("linux/mac magic sidecar not yet implemented")

            case _:
                raise OSError("unknown platform")

    def delete(self) -> None:
        match platform.system():
            case Platform.WINDOWS:
                self._sidecar_check()
                return self._sidecar.unlink(missing_ok=True)

            case Platform.LINUX | Platform.MAC:
                raise NotImplementedError("linux/mac magic sidecar not yet implemented")

            case _:
                raise OSError("unknown platform")

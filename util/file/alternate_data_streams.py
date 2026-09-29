import os
from collections.abc import Sequence
from pathlib import Path

import win32file


# returns tuples with format (size, full name, name)
def get_streams(path: Path) -> Sequence:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist")

    return [(s[0], s[1], s[1][1:-6]) for s in win32file.FindStreams(str(path.resolve()))][1:]


def get_stream_names(path: Path) -> Sequence[str]:
    # chop off the first ($data) stream
    # chop of the ":" prefix and ":$DATA" postfix
    return [s[2] for s in get_streams(path)]


def read_stream(path: Path, stream) -> bytes:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist")

    with open(_file_stream_name(path, stream), "rb") as fd:
        return fd.read()


def write_stream(path: Path, stream, data: bytes) -> int:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist")

    with open(_file_stream_name(path, stream), "wb") as fd:
        return fd.write(data)


def delete_stream(path: Path, stream: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist")
    if not os.path.exists(_file_stream_name(path, stream)):
        raise FileNotFoundError(f"stream {stream} does not exist for {path}")

    os.remove(_file_stream_name(path, stream))


def has_stream(path: Path, stream: str) -> bool:
    return os.path.isfile(_file_stream_name(path, stream))


def _file_stream_name(path: Path, stream: str) -> str:
    return f"{path.resolve()}:{stream}:$DATA"


# stream data is not cached as it may be quite large
class ADSFile:
    _path: Path

    def __init__(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist")

        self._path = path
        self.stream_names = get_stream_names(path)

    def get_stream_names(self) -> Sequence[str]:
        return self.stream_names

    def has_stream(self, stream: str) -> bool:
        return has_stream(self._path, stream)

    def read_stream(self, stream: str) -> bytes:
        return read_stream(self._path, stream)

    def write_stream(self, stream: str, data: bytes) -> int:
        try:
            return write_stream(self._path, stream, data)
        finally:
            self.stream_names = get_stream_names(self._path)

    def delete_stream(self, stream: str) -> None:
        try:
            return delete_stream(self._path, stream)
        finally:
            self.stream_names = get_stream_names(self._path)

import os

import win32file

# TODO change exceptions to return codes where


# returns tuples with format (size, full name, name)
def get_streams(filename):
    if not os.path.exists(filename):
        raise FileNotFoundError(f"{filename} does not exist")
    return [(s[0], s[1], s[1][1:-6]) for s in win32file.FindStreams(filename)][1:]


def get_stream_names(filename):
    # chop off the first ($data) stream
    # chop of the ":" prefix and ":$DATA" postfix
    return [s[2] for s in get_streams(filename)]


def read_stream(filename, stream):
    if not os.path.isfile(filename):
        raise FileNotFoundError(f"{filename} does not exist")
    with open(_file_stream_name(filename, stream), "rb") as fd:
        return fd.read()


def write_stream(filename, stream, data: bytes):
    if not os.path.exists(filename):
        raise FileNotFoundError(f"{filename} does not exist")

    with open(_file_stream_name(filename, stream), "wb") as fd:
        return fd.write(data)


def delete_stream(filename, stream):
    if not os.path.exists(filename):
        raise FileNotFoundError(f"{filename} does not exist")
    if not os.path.exists(_file_stream_name(filename, stream)):
        raise FileNotFoundError(f"stream {stream} does not exist for {filename}")
    return os.remove(_file_stream_name(filename, stream))


def has_stream(filename, stream):
    return os.path.isfile(_file_stream_name(filename, stream))


def _file_stream_name(filename, stream):
    return f"{filename}:{stream}:$DATA"


# stream data is not cached as it may be quite large
class ADSFile:
    def __init__(self, filename):
        if not os.path.exists(filename):
            raise FileNotFoundError(f"{filename} does not exist")
        self.filepath = os.path.abspath(filename)
        self.stream_names = get_stream_names(self.filepath)

    def get_stream_names(self):
        return self.stream_names

    def has_stream(self, stream):
        return has_stream(self.filepath, stream)

    def read_stream(self, stream):
        return read_stream(self.filepath, stream)

    def write_stream(self, stream, data: bytes):
        try:
            return write_stream(self.filepath, stream, data)
        finally:
            self.stream_names = get_stream_names(self.filepath)

    def delete_stream(self, stream):
        try:
            return delete_stream(self.filepath, stream)
        finally:
            self.stream_names = get_stream_names(self.filepath)

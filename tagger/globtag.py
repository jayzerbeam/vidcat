import pickle
from argparse import ArgumentParser
from copy import deepcopy
from pathlib import Path

from util.file.sidecar import MagicSidecar

VID_EXTS = (".avi", ".mp4", ".m4v", ".mkv", ".mpg", ".mpeg", ".wmv", ".flv", ".f4v", ".mov")
SIDECAR_NAMESPACE = "video_metadata"


class Args:
    def __init__(self):
        parser = self.parser = ArgumentParser()
        parser.add_argument("-a", "--actors", default=[], nargs="*")
        parser.add_argument("-t", "--tags", default=[], nargs="*")
        parser.add_argument("-ra", "--remove_actors", default=[], nargs="*")
        parser.add_argument("-rt", "--remove_tags", default=[], nargs="*")
        parser.add_argument("path")
        parser.add_argument("glob")
        self.names = parser.parse_args()


if __name__ == "__main__":
    args = Args()
    root = Path(args.names.path)
    for p in root.glob(args.names.glob, case_sensitive=False):
        if not p.suffix in VID_EXTS:
            continue
        print(p)
        sc = MagicSidecar(p, namespace=SIDECAR_NAMESPACE)

        metadata = deepcopy(
            {
                "title": "",
                "video_properties": {"dimensions": (0, 0), "duration": 0},
                "actors": [],
                "tags": [],
                "thumbnails": [],
            }
        )
        if sc.exists:
            try:
                metadata = pickle.loads(sc.read())
            except Exception as ex:
                print(f"error reading metadata for {p}: {ex}")

        metadata["actors"] = sorted(set(metadata["actors"] + args.names.actors))
        metadata["actors"] = [a for a in metadata["actors"] if a not in args.names.remove_actors]
        metadata["tags"] = sorted(set(metadata["tags"] + args.names.tags))
        metadata["tags"] = [t for t in metadata["tags"] if t not in args.names.remove_tags]
        try:
            bytes_written = sc.write(pickle.dumps(metadata))
            print(f"{bytes_written} bytes written")
        except Exception as ex:
            print(f"failed to write metadata for {p}: {ex}")

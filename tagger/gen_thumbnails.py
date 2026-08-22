import os
import pathlib
import pickle
from argparse import ArgumentParser
from pathlib import Path
from typing import Final

import util.file.alternate_data_streams as ads
from util.file.alternate_data_streams import ADSFile
from util.video_thumbnailer import VideoThumbnailer

VID_EXTS = (
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


class VideoMetadataer:
    _DEFAULT_FPS: Final[float] = 30.0
    _METADATA_STREAM_NAME: Final[str] = "video_metadata"
    _JPGQ: Final[int] = 66

    def __init__(self, path: Path):
        if not path.exists():
            raise FileNotFoundError(f"{path} is not a file")

        self.path = path

        adsfile = self.adsfile = ADSFile(self.path.absolute())
        if adsfile.has_stream(__class__._METADATA_STREAM_NAME):
            self.metadata = pickle.loads(
                adsfile.read_stream(__class__._METADATA_STREAM_NAME)
            )
        else:
            self.metadata = {
                "title": "",
                "video_properties": {},
                "actors": [],
                "tags": [],
                "thumbnails": [],
            }

    def do_thumbnails(
        self, interval: int, thumb_height: int, overwrite: bool = True
    ) -> None:
        if not overwrite and self.metadata["thumbnails"]:
            return

        vt = VideoThumbnailer(self.path.name)
        dimensions = vt.get_dimensions()
        self.metadata["video_properties"] = {}
        self.metadata["video_properties"]["dimensions"] = dimensions
        self.metadata["video_properties"]["duration"] = round(
            vt.get_frame_count() / (vt.get_fps() or 30.0), 2
        )
        vt.extract_frames(interval=interval)
        vt.resize_frames(resize_height=thumb_height)
        jpgs = vt.gen_jpgs(jpgq=__class__._JPGQ)
        self.metadata["thumbnails"] = jpgs

    def parse_filename(self, overwrite: bool = True) -> None:
        if overwrite or self.metadata["title"]:
            self.metadata["title"] = os.path.splitext(self.path.name)[0].replace(
                "_", " "
            )

    def write_metadata(self) -> int:
        return self.adsfile.write_stream(
            __class__._METADATA_STREAM_NAME, pickle.dumps(self.metadata)
        )


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=-30,
        nargs=1,
        help="interval in seconds for each thumnbnail. Use negative numbers for fixed number of thumbnails",
    )
    parser.add_argument(
        "-s",
        "--height",
        type=int,
        default=240,
        nargs=1,
        help="pixel height of thumbnails, width is determined from aspect ratio",
    )
    parser.add_argument(
        "-o",
        "--overwrite",
        action="store_true",
        default=True,
        help="generate thumbnails even if already present",
    )
    parser.add_argument("path", type=pathlib.Path, nargs="*")
    args = parser.parse_args()

    if len(args.path) < 1:
        parser.print_help()

    paths = []
    for p in args.path:
        if not p.exists():
            continue

        if p.is_dir():
            os.chdir(p)
            paths += p.rglob("*")
        elif p.is_file():
            paths += p

    paths = [p for p in paths if p.suffix in VID_EXTS]

    for idx, p in enumerate(paths):
        print(f"[{idx + 1}/{len(paths)}] {p.name}")
        try:
            vm = VideoMetadataer(p)
            vm.parse_filename(overwrite=args.overwrite)
            vm.do_thumbnails(
                interval=args.interval,
                thumb_height=args.height,
                overwrite=args.overwrite,
            )
            bytes_written = vm.write_metadata()
            print(f"{bytes_written}b metadata written\n")
        except Exception as ex:
            print(f"failed {ex}")

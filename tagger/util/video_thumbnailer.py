import cv2
import numpy


class VideoThumbnailer:
    _DEFAULT_FPS = 30  # incase it's unknown

    # TODO use pathlib.Path
    def __init__(self, filename: str = ""):
        self._filename: str = filename
        self._frames: list[tuple[numpy.ndarray, int, int]]
        self._cap = cv2.VideoCapture(filename)

    def get_dimensions(self):
        return (
            round(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            round(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )

    def get_fps(self):
        return self._cap.get(cv2.CAP_PROP_FPS)

    def get_frame_count(self):
        return int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # interval
    # 	positive is seconds
    # 	negative is divisions
    def extract_frames(self, interval: float = 30.0) -> None:
        if interval == 0:
            raise ValueError(f"invalid interval ({interval})")
        video_fps = self._cap.get(cv2.CAP_PROP_FPS) or __class__._DEFAULT_FPS
        video_length = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT)) - 1

        if interval < 0:
            interval = video_length / (-interval + 1)
        else:
            interval = video_fps * interval

        print(
            f"{video_length} frames, {round(video_length / video_fps)}s, {video_fps:.2f}fps, interval {interval:.0f} ",
            end="",
        )

        frames = []
        s = 0
        if self._cap.isOpened() and video_length > 0:
            frameno = interval
            while round(frameno) < video_length:
                rfn = round(frameno)
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, rfn)
                success, image = self._cap.read()
                if success:
                    frames.append((image, rfn, round(frameno / video_fps * 1000)))
                    s += 1
                    print(".", end="", flush=True)
                else:
                    print("x", end="", flush=True)
                frameno += interval
            print(f" {s}/{len(frames)}")

        self.frames = frames

    # this is a destructive operation
    def resize_frames(self, resize_height: int = 240) -> None:
        if not self.frames:
            return

        resized_frames = []

        # all frames should have the same dimentions so only calc off the first
        oldh, oldw, _ = self.frames[0][0].shape
        (neww, newh) = (int(resize_height / oldh * oldw), resize_height)
        s = 0
        print(f"resizing {oldw}x{oldh} -> {neww}x{newh} ", end="")

        for fdata in self.frames:
            try:
                rimage = cv2.resize(
                    fdata[0],
                    [neww, newh],
                    interpolation=(
                        cv2.INTER_AREA if resize_height <= oldh else cv2.INTER_CUBIC
                    ),
                )
                resized_frames.append((rimage,) + fdata[1:])
                print(".", end="", flush=True)
                s += 1
            except cv2.error:
                print("x", end="", flush=True)
        print(f" {s}/{len(self.frames)}")

        self.frames = resized_frames

    def gen_jpgs(self, jpgq: int = 70) -> list | None:
        if not self.frames:
            return

        print("generating jpgs ", end="")
        jpgs = []
        s = 0  # success
        for fdata in self.frames:
            success, jpg = cv2.imencode(
                ".jpg", fdata[0], [cv2.IMWRITE_JPEG_QUALITY, jpgq]
            )
            # cv2.imwrite(f"{sys.argv[1]}_{frameno}.jpg", image, [cv2.IMWRITE_JPEG_QUALITY, jpgq])
            if success:
                jpgs.append((jpg,) + fdata[1:])
                s += 1
                print(".", end="", flush=True)
            else:
                print("x", end="", flush=True)
        print(f" {s}/{len(self.frames)}")
        return jpgs

from argparse import ArgumentParser
from contextlib import chdir
from pathlib import Path
from typing import Final

from browser.app import App
from browser.config import CONFIG_NAME, Config
from ui.message_system import MessageWindow

SCRIPT_DIR: Final[Path] = Path(__file__).parent

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=SCRIPT_DIR / CONFIG_NAME,
        help=f"config file path. default will look in script dir: {SCRIPT_DIR / CONFIG_NAME}",
    )
    parser.add_argument(
        "path",
        type=Path,
        help="note: all paths (trash, vid_player, etc.) are relative to here",
    )
    args = parser.parse_args()

    if not args.config.is_file():
        print(f"error: cannot load config: '{args.config}' is not a file")
        raise SystemExit

    if not args.path.is_dir():
        print(f"{args.path} is not a directory")
        raise SystemExit

    with chdir(args.path):
        cfg = Config()
        cfg.load(args.config)

        path = Path(".")
        window = MessageWindow()
        window.title(f"Vid Cat ({path.resolve()})")
        window.geometry("1200x1000")
        app = App(window, basepath=path, config=cfg)
        window.mainloop()

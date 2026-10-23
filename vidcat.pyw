from argparse import ArgumentParser
from contextlib import chdir
from pathlib import Path
from typing import Final

from browser.app import App
from browser.config import Config
from ui.message_system import MessageWindow

CONFIG_NAME: Final[str] = "vidcat.cfg.json"
SCRIPT_DIR: Final[Path] = Path(__file__).resolve().parent

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
        help="base path to search for files. trash, vid_player, etc. are relative to here",
    )
    args = parser.parse_args()

    if not args.path.is_dir():
        print(f"{args.path} is not a directory")
        raise SystemExit

    config_path = args.config.resolve()

    with chdir(args.path):
        cfg = Config()
        if config_path.is_file():
            cfg.load(config_path)
        else:
            cfg.write_default(config_path)
            print(f"no config found, created new default config at '{config_path}'")

        path = Path(".")
        window = MessageWindow()
        window.title(f"VidCat ({path.resolve()})")
        window.geometry("1200x1000")
        app = App(window, basepath=path, config=cfg)
        window.mainloop()

from collections.abc import Iterator, Sequence
from pathlib import Path

from util.file.tree import PathTree, path_extension_filter


class VideoLibrary:
    """Owns the scanned file tree: scanning, rescanning, removal, and file iteration."""

    _tree: PathTree
    _vid_exts: tuple[str, ...]

    def __init__(self, root: Path, vid_exts: Sequence[str]) -> None:
        self._tree = PathTree(root)
        self._vid_exts = tuple(vid_exts)

    @property
    def tree(self) -> PathTree:
        return self._tree

    def scan(self) -> None:
        """(Re)scan the whole tree, keeping only the configured video extensions."""
        self._tree.scan(filters=[path_extension_filter(self._vid_exts)])

    def rescan(self, path: Path) -> PathTree | None:
        """Clear and rescan the subtree at path; None when path is not a known directory."""
        if not path.is_dir():
            return None

        pt = self._tree.dig(path)
        if pt is None:
            return None

        pt.clear()
        pt.scan(filters=[path_extension_filter(self._vid_exts)])
        return pt

    def remove(self, path: Path) -> bool:
        """Remove path's entry from the tree; the file system is not touched."""
        return self._tree.dig_and_remove(path)

    def iter_files(self, path: Path | None = None) -> Iterator[Path]:
        """Yield files depth-first: a node's child directories come before its files.

        With path=None walk the whole tree; otherwise walk the subtree at path,
        yielding nothing when path does not resolve inside the tree.
        """
        if path is None:
            yield from self._walk(self._tree)
            return

        pt = self._tree.dig(path)
        if pt is not None:
            yield from self._walk(pt)

    def _walk(self, pt: PathTree) -> Iterator[Path]:
        for _, child in pt.dirs():
            yield from self._walk(child)
        yield from pt.files()


class Trash:
    """Moves paths into a trash directory; reports initialization failure via available."""

    _path: Path | None

    def __init__(self, path: Path) -> None:
        try:
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
        except OSError as ex:
            print(f"error: failed to create trash directory {path}: {ex}")
            self._path = None
            return

        if path.is_dir():
            self._path = path
        else:
            # shouldn't happen, config does a trash path check
            print("error:trash directory is not a directory, could not initialize")
            self._path = None

    @property
    def available(self) -> bool:
        return self._path is not None

    def send(self, paths: Sequence[Path]) -> list[Path]:
        """Move existing paths into the trash and return the paths that were moved.

        Trash entries are never overwritten: a move that would collide with an
        existing entry targets the first free ``{stem} (n){suffix}`` name.
        """
        trash_path = self._path
        if trash_path is None:
            return []

        moved: list[Path] = []
        for p in paths:
            # container folder may have been moved
            if not p.exists():
                continue

            try:
                p.move(self._free_target(trash_path, p))
            except OSError as ex:
                print(f"error: failed to move {p} to trash: {ex}")
                continue
            moved.append(p)
        return moved

    @staticmethod
    def _free_target(trash_path: Path, source: Path) -> Path:
        """Return a non-existing trash target for source: its name, then stem (1), stem (2), ..."""
        target = trash_path / source.name
        if not target.exists():
            return target

        n = 0
        while True:
            n += 1
            target = trash_path / f"{source.stem} ({n}){source.suffix}"
            if not target.exists():
                return target

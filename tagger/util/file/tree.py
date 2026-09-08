from collections.abc import Callable, Generator, Sequence
from pathlib import Path

type PathTreeDict = dict[str, PathTreeDict | list[str]]
type PathTreeFilter = Callable[[Path], bool]


class PathTree:
    _root: Path
    _dirs: dict[str, PathTree]
    _files: list[Path]

    def __init__(self, root: Path) -> None:
        if not root.exists():
            raise FileNotFoundError("PathTree root {root} must exist")

        self._root = root
        self._dirs = {}
        self._files = []

    def __str__(self) -> str:
        def _recurse(pt: PathTree, depth: int) -> str:
            out = ""
            indent = "  " * depth
            for d, child in pt.dirs():
                out += f"{indent}{d}\n"
                out += _recurse(child, depth + 1)
            for f in pt.files():
                out += f"{indent}{f.name}\n"

            return out

        return _recurse(self, 0)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def dir_count(self) -> int:
        return len(self._dirs)

    @property
    def file_count(self) -> int:
        return len(self._files)

    @property
    def is_empty(self) -> bool:
        return len(self._dirs) + len(self._files) == 0

    def clear(self) -> None:
        self._dirs = {}
        self._files = []

    def dig(self, path: Path) -> PathTree | None:
        """Dig through the PathTree to find the PathTree of the relative Path.
        This is here for efficiency of creating a new PathTree and scanning the file system to fill it.
        If looking for a child file then Path.rglob() or the like is better as files in PathTree are pathlib.Path anyway."""

        if self._root.is_absolute() and not path.is_absolute():
            path = path.absolute()

        pt = self
        try:
            parts = path.relative_to(self._root).parts
        except ValueError:
            return None
        else:
            for p in parts:
                pt = pt.dir(p)
                if pt == None:
                    return None

            return None if pt is self else pt

    def remove(self, name: str) -> bool:
        """Remove a file or dir from the IMMEDIATE PathTree (use dig_and_remove for recursive).
        This only removes the PathTree entry, it does not delete the file.
        Both paths must exist"""

        p = self._root.joinpath(name)
        if name in self._dirs:
            del self._dirs[name]
            return True
        if p in self._files:
            self._files.remove(p)
            return True

        return False

    def dig_and_remove(self, path: Path) -> bool:
        """Effectively .dig() then remove()
        NOTE: path.absolute() against PathTree.root.resolve() so using symlinks may have unintended side effects"""

        if path.is_absolute() != self._root.is_absolute():
            raise ValueError("PathTree path and path param must either both be absolute or not")

        try:
            parts = path.relative_to(self._root).parts
        except ValueError:
            return False
        else:
            if len(parts) == 0:
                raise ValueError("There are no path parts for {path}. This shouldn't happen")

            dug = self if len(parts) == 1 else self.dig(Path().joinpath(*parts[:-1]))
            if dug is None:
                return False
            dug.remove(path.name)

        return False

    def dir(self, name: str) -> PathTree | None:
        return self._dirs.get(name, None)

    def dirs(self) -> Generator[tuple[str, PathTree]]:
        yield from self._dirs.items()

    def files(self) -> Generator[Path]:
        yield from self._files

    def scan(
        self,
        depth: int = 32,
        filters: Sequence[PathTreeFilter] | None = None,
    ) -> None:
        for child in self._root.iterdir():
            if filters is None or all(f(child) for f in filters):
                if child.is_dir():
                    gc = PathTree(root=child)
                    if depth > 0:
                        gc.scan(depth=depth - 1, filters=filters)
                    self._dirs[child.name] = gc
                else:
                    self._files.append(child)


def path_extension_filter(extensions: Sequence[str]) -> PathTreeFilter:
    return lambda p: p.is_dir() or p.suffix in extensions


def build_dir_tree_dict(
    path: Path,
    exclude_empty_dir: bool = False,
    filters: Sequence[PathTreeFilter] | None = None,
) -> PathTreeDict:
    def _walkerr(err: OSError) -> None:
        print(f"build_dir_tree error {err}")

    def _recurse(p: Path) -> dict[str, dict | list]:
        dirs = {}
        files = []
        for child in p.iterdir():
            if filters is None or all(f(child) for f in filters):
                if child.is_dir():
                    gc = _recurse(child)
                    if not (len(gc["dirs"]) == 0 and len(gc["files"]) == 0 and exclude_empty_dir):
                        dirs[child.name] = gc
                else:
                    files.append(child.name)

        return {"dirs": dict(sorted(dirs.items())), "files": sorted(files)}

    return _recurse(path)

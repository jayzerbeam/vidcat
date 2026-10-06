from pathlib import Path

import pytest

from util.file.tree import PathTree, build_dir_tree_dict, path_extension_filter


@pytest.fixture
def tree(tmp_path: Path) -> PathTree:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.mp4").write_text("x")
    (tmp_path / "b.mp4").write_text("y")
    (tmp_path / "c.txt").write_text("z")
    pt = PathTree(tmp_path)
    pt.scan()
    return pt


def test_init_missing_root(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError) as exc:
        PathTree(missing)
    assert str(missing) in str(exc.value)


def test_scan_counts_and_clear(tree: PathTree, tmp_path: Path) -> None:
    assert tree.root == tmp_path
    assert (tree.dir_count, tree.file_count, tree.is_empty) == (1, 2, False)
    tree.clear()
    assert (tree.dir_count, tree.file_count, tree.is_empty) == (0, 0, True)


def test_scan_depth_zero(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.mp4").write_text("x")
    (tmp_path / "b.mp4").write_text("y")
    pt = PathTree(tmp_path)
    pt.scan(depth=0)
    sub = pt.dir("sub")
    assert pt.file_count == 1
    assert sub is not None
    assert sub.is_empty


def test_scan_extension_filter(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.mp4").write_text("x")
    (tmp_path / "b.mp4").write_text("y")
    (tmp_path / "c.txt").write_text("z")
    pt = PathTree(tmp_path)
    pt.scan(filters=[path_extension_filter([".mp4"])])
    sub = pt.dir("sub")
    assert pt.file_count == 1
    assert sub is not None
    assert sub.file_count == 1


def test_dig(tree: PathTree, tmp_path: Path) -> None:
    assert tree.dig(tmp_path / "sub") is tree.dir("sub")
    assert tree.dig(tmp_path.parent / "other") is None
    assert tree.dig(tmp_path) is None


def test_remove(tree: PathTree) -> None:
    assert tree.remove("sub") is True
    assert tree.dir("sub") is None
    assert tree.remove("b.mp4") is True
    assert tree.file_count == 1
    assert tree.remove("nope") is False


def test_dig_and_remove_outside(tree: PathTree, tmp_path: Path) -> None:
    assert tree.dig_and_remove(tmp_path.parent / "other") is False


def test_dig_and_remove_mixed_abs_rel(tree: PathTree) -> None:
    with pytest.raises(ValueError):
        tree.dig_and_remove(Path("sub"))


def test_dig_and_remove_root(tree: PathTree, tmp_path: Path) -> None:
    with pytest.raises(ValueError) as exc:
        tree.dig_and_remove(tmp_path)
    assert str(tmp_path) in str(exc.value)


def test_build_dir_tree_dict(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.mp4").write_text("x")
    (tmp_path / "b.txt").write_text("y")
    (tmp_path / "empty").mkdir()
    assert build_dir_tree_dict(tmp_path) == {
        "dirs": {"empty": {"dirs": {}, "files": []}, "sub": {"dirs": {}, "files": ["a.mp4"]}},
        "files": ["b.txt"],
    }
    assert build_dir_tree_dict(tmp_path, exclude_empty_dir=True) == {
        "dirs": {"sub": {"dirs": {}, "files": ["a.mp4"]}},
        "files": ["b.txt"],
    }

import tkinter as tk
from tkinter import ttk

import pytest

from browser.metadata import Bookmark
from browser.ui.bookmark_frame import BookmarkFrame
from util.format import clock_format

BOOKMARK_A = Bookmark(time_ms=1000, frame_no=30, name="Opening")
BOOKMARK_B = Bookmark(time_ms=2500, frame_no=None, name="")
BOOKMARK_C = Bookmark(time_ms=4000, frame_no=120, name="Favorite")


class RecordingHandlers:
    """Recording stand-ins for the widget's add/seek/remove callbacks."""

    def __init__(self, add_result: bool = True) -> None:
        self.add_result = add_result
        self.names: list[str] = []
        self.seeked: list[Bookmark] = []
        self.removed: list[Bookmark] = []

    def add(self, name: str) -> bool:
        self.names.append(name)
        return self.add_result

    def seek(self, bookmark: Bookmark) -> None:
        self.seeked.append(bookmark)

    def remove(self, bookmark: Bookmark) -> None:
        self.removed.append(bookmark)


@pytest.fixture
def root():
    window = tk.Tk()
    yield window
    window.destroy()


def make_frame(root: tk.Tk, add_result: bool = True) -> tuple[BookmarkFrame, RecordingHandlers]:
    handlers = RecordingHandlers(add_result)
    frame = BookmarkFrame(root)
    frame.set_add_handler(handlers.add)
    frame.set_seek_handler(handlers.seek)
    frame.set_remove_handler(handlers.remove)
    # rows need a mapped frame with real dimensions for bbox-based clicks
    frame.pack(fill=tk.BOTH, expand=True)
    root.geometry("300x400")
    root.update()
    return frame, handlers


def treeview(frame: BookmarkFrame) -> ttk.Treeview:
    return frame._widgets.bookmarks.child


def time_cell(time_ms: int) -> str:
    return clock_format(time_ms / 1000, decimals=3) or ""


def cell_point(frame: BookmarkFrame, iid: str) -> tuple[int, int]:
    x, y, _, height = (int(value) for value in treeview(frame).bbox(iid, "time"))
    return x + 2, y + height // 2


def click_row(frame: BookmarkFrame, iid: str) -> None:
    tree = treeview(frame)
    tree.update_idletasks()
    x, y = cell_point(frame, iid)
    tree.event_generate("<Button-1>", x=x, y=y)


def test_requested_width_is_honored(root: tk.Tk) -> None:
    frame = BookmarkFrame(root)
    wide = BookmarkFrame(root, width=260)
    frame.set_bookmarks((BOOKMARK_A,))
    wide.set_bookmarks((BOOKMARK_A,))
    root.update_idletasks()

    assert frame.winfo_reqwidth() == 200
    assert wide.winfo_reqwidth() == 260


def test_treeview_configured_with_time_and_name_columns(root: tk.Tk) -> None:
    # kept unmapped: a mapped treeview stretches the Name column to the frame width
    tree = treeview(BookmarkFrame(root))
    root.update_idletasks()

    assert tuple(str(value) for value in tree.cget("show")) == ("headings",)
    assert tuple(tree.cget("columns")) == ("time", "name")
    assert tree.heading("time")["text"] == "Time"
    assert tree.heading("name")["text"] == "Name"
    assert tree.column("time", "width") == 80
    assert not tree.column("time", "stretch")
    assert tree.column("name", "width") == 90
    assert tree.column("name", "stretch")


def test_set_bookmarks_renders_rows_in_given_order(root: tk.Tk) -> None:
    frame, _ = make_frame(root)

    frame.set_bookmarks((BOOKMARK_A, BOOKMARK_B, BOOKMARK_C))

    tree = treeview(frame)
    assert tree.get_children() == ("1000", "2500", "4000")
    assert tree.item("1000", "values") == (time_cell(1000), "Opening")
    assert tree.item("2500", "values") == (time_cell(2500), "")
    assert tree.item("4000", "values") == (time_cell(4000), "Favorite")


def test_bookmark_button_adds_stripped_name_and_clears_entry(root: tk.Tk) -> None:
    frame, handlers = make_frame(root)
    frame._widgets.name.insert(0, "  Opening  ")

    frame._widgets.add.invoke()

    assert handlers.names == ["Opening"]
    assert frame._widgets.name.get() == ""


def test_rejected_add_keeps_entry_text(root: tk.Tk) -> None:
    frame, handlers = make_frame(root, add_result=False)
    frame._widgets.name.insert(0, "Opening")

    frame._widgets.add.invoke()

    assert handlers.names == ["Opening"]
    assert frame._widgets.name.get() == "Opening"


def test_blank_entry_adds_unnamed_bookmark(root: tk.Tk) -> None:
    frame, handlers = make_frame(root)

    frame._widgets.add.invoke()

    assert handlers.names == [""]
    assert frame._widgets.name.get() == ""


def test_entry_return_adds_bookmark(root: tk.Tk) -> None:
    frame, handlers = make_frame(root)
    frame._widgets.name.focus_force()
    frame._widgets.name.insert(0, "  Cut  ")

    frame._widgets.name.event_generate("<Return>")
    root.update()

    assert handlers.names == ["Cut"]
    assert frame._widgets.name.get() == ""


def test_clicking_row_seeks_that_bookmark(root: tk.Tk) -> None:
    frame, handlers = make_frame(root)
    frame.set_bookmarks((BOOKMARK_A, BOOKMARK_B))
    root.update()

    click_row(frame, "2500")
    root.update()

    assert set(handlers.seeked) == {BOOKMARK_B}
    assert treeview(frame).selection() == ("2500",)


def test_clicking_already_selected_row_seeks_again(root: tk.Tk) -> None:
    frame, handlers = make_frame(root)
    frame.set_bookmarks((BOOKMARK_A, BOOKMARK_B))
    tree = treeview(frame)
    tree.selection_set("2500")
    root.update()
    assert handlers.seeked == [BOOKMARK_B]

    # invoke the bound click handler directly: a re-click may also re-fire <<TreeviewSelect>>,
    # but the seek must come from the click path alone
    event = tk.Event()
    event.x, event.y = cell_point(frame, "2500")
    frame._handle_click(event)

    assert handlers.seeked == [BOOKMARK_B, BOOKMARK_B]


def test_selection_change_seeks_selected_bookmark(root: tk.Tk) -> None:
    frame, handlers = make_frame(root)
    frame.set_bookmarks((BOOKMARK_A, BOOKMARK_B))

    treeview(frame).selection_set("1000")
    root.update()

    assert handlers.seeked == [BOOKMARK_A]


def test_delete_removes_selected_bookmark(root: tk.Tk) -> None:
    frame, handlers = make_frame(root)
    frame.set_bookmarks((BOOKMARK_A, BOOKMARK_B))
    tree = treeview(frame)
    tree.selection_set("1000")
    root.update()

    tree.focus_force()
    tree.event_generate("<Delete>")
    root.update()

    assert handlers.removed == [BOOKMARK_A]


def test_delete_without_selection_does_nothing(root: tk.Tk) -> None:
    frame, handlers = make_frame(root)
    frame.set_bookmarks((BOOKMARK_A,))

    tree = treeview(frame)
    tree.focus_force()
    tree.event_generate("<Delete>")
    root.update()

    assert handlers.removed == []


def test_disabled_frame_blocks_interaction(root: tk.Tk) -> None:
    frame, handlers = make_frame(root)
    frame.set_bookmarks((BOOKMARK_A,))
    root.update()
    frame.set_enabled(False)

    tree = treeview(frame)
    assert str(tree.cget("selectmode")) == "none"
    assert "disabled" in frame._widgets.name.state()
    assert "disabled" in frame._widgets.add.state()

    x, y = cell_point(frame, "1000")
    tree.event_generate("<Button-1>", x=x, y=y)
    tree.event_generate("<<TreeviewSelect>>")
    tree.focus_force()
    tree.event_generate("<Delete>")
    frame._widgets.name.focus_force()
    frame._widgets.name.insert(0, "Blocked")
    frame._widgets.name.event_generate("<Return>")
    root.update()

    assert tree.selection() == ()
    assert handlers.seeked == []
    assert handlers.removed == []
    assert handlers.names == []


def test_empty_rerender_clears_rows_without_seeking(root: tk.Tk) -> None:
    frame, handlers = make_frame(root)
    frame.set_bookmarks((BOOKMARK_A, BOOKMARK_B))
    tree = treeview(frame)
    tree.selection_set("1000")
    root.update()
    seeks_from_selection = len(handlers.seeked)

    # deleting all rows fires <<TreeviewSelect>> with an empty selection when a row was selected
    frame.set_bookmarks(())
    root.update()

    assert tree.get_children() == ()
    assert tree.selection() == ()
    assert len(handlers.seeked) == seeks_from_selection


def test_duplicate_times_render_one_row(root: tk.Tk) -> None:
    frame, _ = make_frame(root)

    frame.set_bookmarks((BOOKMARK_A, Bookmark(time_ms=1000, frame_no=None, name="Later"), BOOKMARK_C))

    tree = treeview(frame)
    assert tree.get_children() == ("1000", "4000")
    assert tree.item("1000", "values")[1] == "Opening"


def test_overflowing_time_renders_blank_cell(root: tk.Tk) -> None:
    frame, _ = make_frame(root)
    bookmark = Bookmark(time_ms=10**18, frame_no=None, name="Ancient")

    frame.set_bookmarks((bookmark,))

    assert treeview(frame).item(str(bookmark.time_ms), "values") == ("", "Ancient")

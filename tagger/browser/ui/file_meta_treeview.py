import tkinter as tk
from pathlib import Path
from typing import NamedTuple, cast

from browser.ui.constants import VirtualEventSequence
from util.format import clock_format
from util.typing import StringListy
from util.ui.better_treeview import FileTreeviewFrame


def any_in_list(s1: set, s2: set, case_sensitive: bool = False) -> bool:
    if not case_sensitive:
        s1 = set(map(str.lower, s1))
        s2 = set(map(str.lower, s2))

    return len(s1 & s2) > 0


class FileMetaTreeviewFrame(FileTreeviewFrame):
    """A FileTreeviewFrame that adds columns and functionality for actors and tags"""

    class _Menus(NamedTuple):
        dir: tk.Menu
        file: tk.Menu

    _menus: _Menus
    _menu_iid: str | None

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, columns=("time", "res", "actors", "tags"), sortable=False, width=300, **kw)
        # disable propogation to set a treeview total width wider than the frame
        self.grid_propagate(False)
        self.pack_propagate(False)
        self.treeview.heading("#0", text="Path")
        self.treeview.heading("#1", text="Time")
        self.treeview.heading("#2", text="Res")
        self.treeview.heading("#3", text="Actors")
        self.treeview.heading("#4", text="Tags")
        self.treeview.column("#0", minwidth=100, width=280, stretch=False)
        self.treeview.column("#1", minwidth=10, width=50, stretch=False)
        self.treeview.column("#2", minwidth=10, width=70, stretch=False)
        self.treeview.column("#3", minwidth=10, width=100, stretch=False)
        self.treeview.column("#4", minwidth=10, width=100, stretch=False)
        # self.tag_configure('dir', background = '#EEE')
        self.treeview.tag_configure("highlight", background="#DFD")
        is_mac = self.winfo_toplevel().tk.call("tk", "windowingsystem") == "aqua"
        self.treeview.bind("<Button-2>" if is_mac else "<Button-3>", self._handle_right_click)

        self._menu_iid = None
        self._menus = __class__._Menus(
            file=tk.Menu(self, tearoff=0),
            dir=tk.Menu(self, tearoff=0),
        )
        self._menus.file.add_command(label="Remove", command=self._handle_file_delete)

    def _handle_right_click(self, ev: tk.Event) -> None:
        iid = self.treeview.identify_row(ev.y)
        if iid is None:
            return

        if self.treeview.tag_has("file", iid):
            try:
                self._menu_iid = iid
                self._menus.file.entryconfigure(0, label=f"Remove {Path(iid).name}")
                self._menus.file.tk_popup(ev.x_root, ev.y_root)
            finally:
                self._menus.file.grab_release()
        elif self.treeview.tag_has("dir", iid):
            print("dir", iid)

    def _handle_file_delete(self):
        if self._menu_iid is not None:
            self.event_generate(VirtualEventSequence.FILE_DELETE, data=self._menu_iid)
            self.treeview.delete(self._menu_iid)
            self._menu_iid = None

    def set_meta_column_vals(
        self, item: str, duration: float, res: tuple[int, int], actors: StringListy, tags: StringListy
    ):
        self.child.item(item, values=(clock_format(duration), f"{res[0]}x{res[1]}", ", ".join(actors), ", ".join(tags)))

    def collapse_all(self) -> None:
        def _recurse(item: str):
            child = None
            for child in self.treeview.get_children(item):
                _recurse(child)
            if child:
                self.treeview.item(item, open=False)

        _recurse("")

    def apply_filters(self, actors: StringListy, tags: StringListy, operator: str = "AND"):
        def _recurse(item):
            if self.treeview.tag_has("file", item):
                itemconfig = self.treeview.item(item)
                (item_actors, item_tags) = (
                    (
                        itemconfig["values"][0].split(", "),
                        itemconfig["values"][1].split(", "),
                    )
                    if len(itemconfig["values"])
                    else ([], [])
                )
                if operator == "AND":
                    if (actors and len(set(actors) & set(item_actors)) != len(actors)) or (
                        tags and len(set(tags) & set(item_tags)) != len(tags)
                    ):
                        self.hide(item)
                else:
                    if (actors and len(set(actors) & set(item_actors)) == 0) or (
                        tags and len(set(tags) & set(item_tags)) == 0
                    ):
                        self.hide(item)
            for child in self.treeview.get_children(item):
                _recurse(child)

        _recurse("")

    def apply_highlight(self, actors: StringListy, tags: StringListy):
        def _highlight_item(item: str, highlighted: bool, see: bool = False):
            itemconfig = self.treeview.item(item)
            if "highlight" in itemconfig["tags"] and not highlighted:
                cast(list, itemconfig["tags"]).remove("highlight")

            if "highlight" not in itemconfig["tags"] and highlighted:
                if isinstance(itemconfig["tags"], list):
                    itemconfig["tags"].append("highlight")
                else:
                    itemconfig["tags"] = ["highlight"]

            self.treeview.item(item, tags=itemconfig["tags"])

            if highlighted and see:
                self.treeview.see(item)

        def _recurse(item: str):
            highlighted = False
            if self.treeview.tag_has("file", item):
                itemconfig = self.treeview.item(item)
                (item_actors, item_tags) = (
                    (
                        set(itemconfig["values"][0].split(", ")),
                        set(itemconfig["values"][1].split(", ")),
                    )
                    if len(itemconfig["values"])
                    else (set(), set())
                )
                highlighted = any_in_list(set(actors), item_actors) or any_in_list(set(tags), item_tags)
                _highlight_item(item, highlighted, see=True)
            for child in self.treeview.get_children(item):
                _recurse(child)

        self.collapse_all()
        _recurse("")

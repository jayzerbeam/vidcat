from typing import cast

from util.typing import StringListy
from util.ui.better_treeview import FileTreeviewFrame


def any_in_list(s1: set, s2: set, case_sensitive: bool = False) -> bool:
    if not case_sensitive:
        s1 = set(map(str.lower, s1))
        s2 = set(map(str.lower, s2))

    return len(s1 & s2) > 0


# a FileTreeviewFrame that adds columns for actors and tags
class FileMetaTreeviewFrame(FileTreeviewFrame):
    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, columns=("actors", "tags"), xscrollable=False, sortable=False, **kw)
        self.treeview.heading("#0", text="Sub Dir")
        self.treeview.heading("#1", text="Actors")
        self.treeview.heading("#2", text="Tags")
        self.with_meta_columns(False)
        # self.tag_configure('dir', background = '#EEE')
        self.treeview.tag_configure("highlight", background="#DFD")

    def with_meta_columns(self, enabled: bool):
        if enabled:
            self.treeview.column("#1", minwidth=10, width=100, stretch=True)
            self.treeview.column("#2", minwidth=10, width=250, stretch=True)
        else:
            self.treeview.column("#1", minwidth=0, width=0, stretch=False)
            self.treeview.column("#2", minwidth=0, width=0, stretch=False)

    def set_meta_columns(self, item: str, actors: list, tags: list):
        self.child.item(item, values=(", ".join(actors), ", ".join(tags)))

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

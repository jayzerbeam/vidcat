from enum import StrEnum


class VirtualEventSequence(StrEnum):
    DIR_SELECT = "<<DirSelect>>"
    DIR_DESELECT = "<<DirDeselect>>"
    FILE_EXEC = "<<FileExec>>"
    FILE_SELECT = "<<FileSelect>>"
    FILE_DESELECT = "<<FileDeselect>>"
    TREEVIEW_SELECT = "<<TreeviewSelect>>"  # this is the event from ttk.Treeview


class TkCursor(StrEnum):
    WAIT = "wait"
    WATCH = "watch"
    PROGRESS = "progress"

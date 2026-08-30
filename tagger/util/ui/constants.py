from enum import StrEnum


class VirtualEventSequence(StrEnum):
    FILE_EXEC = "<<FileExec>>"
    FILE_SELECT = "<<FileSelect>>"
    TREEVIEW_SELECT = "<<TreeviewSelect>>"  # this is the event from ttk.Treeview


class TkCursor(StrEnum):
    WAIT = "wait"
    WATCH = "watch"
    PROGRESS = "progress"

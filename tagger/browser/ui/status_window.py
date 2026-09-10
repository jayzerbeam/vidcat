import tkinter as tk
from tkinter import StringVar, ttk
from typing import NamedTuple


class StatusWindow(tk.Toplevel):
    class _Widgets(NamedTuple):
        frame: ttk.Frame
        progress: ttk.Progressbar
        status: ttk.Label

    def __init__(self, parent, *args, **kw):
        super().__init__(parent, *args, **kw)
        self.overrideredirect(True)  # no titlebar, borders
        self.resizable(False, False)
        self.title("Status")
        self.group(parent)

        self.status_text = StringVar()
        frame = ttk.Frame(self)
        self._widgets = __class__._Widgets(
            frame=frame,
            progress=ttk.Progressbar(frame, maximum=1.0),
            status=ttk.Label(frame, textvariable=self.status_text),
        )
        self._widgets.progress.grid(column=0, row=0, padx=2, pady=2, sticky="ew")
        self._widgets.status.grid(column=0, row=1, padx=2, pady=2)
        self._widgets.frame.columnconfigure(0, weight=1)
        self._widgets.frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    @property
    def info(self) -> str:
        return self.status_text.get()

    @info.setter
    def info(self, val: str):
        return self.status_text.set(val)

    @property
    def progress(self) -> float:
        """Returns progress value [0,1]"""
        return self._widgets.progress["value"]

    @progress.setter
    def progress(self, val: float):
        """Set progress value [0,1]"""
        self._widgets.progress.config(value=val)

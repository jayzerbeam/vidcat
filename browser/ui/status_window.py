import tkinter as tk
from tkinter import ttk
from typing import NamedTuple


class StatusWindow(tk.Toplevel):
    class __Widgets(NamedTuple):
        frame: ttk.Frame
        progress: ttk.Progressbar
        status: ttk.Label

    class __Vars(NamedTuple):
        status: tk.StringVar

    _widgets: __Widgets
    _vars: __Vars

    _SPACING = 80

    def __init__(self, root: tk.Tk, *args, **kw):
        super().__init__(root, *args, **kw)
        self.overrideredirect(True)  # no titlebar, borders
        self.resizable(width=False, height=False)
        self.title("Status")
        self.group(root)

        self._vars = __class__.__Vars(status=tk.StringVar())
        frame = ttk.Frame(self)
        self._widgets = __class__.__Widgets(
            frame=frame,
            progress=ttk.Progressbar(frame, maximum=1.0),
            status=ttk.Label(frame, textvariable=self._vars.status),
        )
        self._widgets.progress.grid(column=0, row=0, padx=2, pady=2, sticky="ew")
        self._widgets.status.grid(column=0, row=1, padx=2, pady=2)
        self._widgets.frame.columnconfigure(0, weight=1)
        self._widgets.frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.transient(root)
        self.withdraw()

    @property
    def info(self) -> str:
        return self._vars.status.get()

    @info.setter
    def info(self, val: str):
        self._vars.status.set(val)

    @property
    def progress(self) -> float:
        """Returns progress value [0,1]"""
        return self._widgets.progress["value"]

    @progress.setter
    def progress(self, val: float):
        """Set progress value [0,1]"""
        self._widgets.progress.config(value=val)

    def show(self) -> None:
        root = self.master
        self.update_idletasks()
        height = self.winfo_reqheight()
        width = round(root.winfo_width() - self._SPACING)
        x = round(root.winfo_x() + self._SPACING / 2)
        y = round(root.winfo_y() + root.winfo_height() / 2 - height / 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        self.lift()

    def hide(self) -> None:
        self.withdraw()

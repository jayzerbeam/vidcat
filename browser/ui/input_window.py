import tkinter as tk
from tkinter import ttk
from typing import NamedTuple


class InputWindow(tk.Toplevel):
    class __Widgets(NamedTuple):
        frame: ttk.Frame
        label: ttk.Label
        entry: ttk.Entry
        button_frame: ttk.Frame
        ok: ttk.Button
        cancel: ttk.Button

    class __Vars(NamedTuple):
        label: tk.StringVar
        input: tk.StringVar  # this is not bound to the entry, instead filled on OK

    _closed_ok: bool
    _widgets: __Widgets
    _vars: __Vars

    def __init__(self, root: tk.Tk, *args, **kw):
        super().__init__(root, *args, **kw)
        self.resizable(False, False)
        self.title("Input")
        self.protocol("WM_DELETE_WINDOW", lambda: self._handle_cancel)
        self.minsize(300, 20)
        self.group(root)

        self._closed_ok = False

        self._vars = __class__.__Vars(
            label=tk.StringVar(),
            input=tk.StringVar(),
        )
        frame = ttk.Frame(self)
        btnfrm = ttk.Frame(frame)
        self._widgets = __class__.__Widgets(
            frame=frame,
            label=ttk.Label(frame, textvariable=self._vars.label),
            entry=ttk.Entry(frame),
            button_frame=btnfrm,
            ok=ttk.Button(btnfrm, text="Ok", command=self._handle_ok),
            cancel=ttk.Button(btnfrm, text="Cancel", command=self._handle_cancel),
        )

        self._widgets.entry.bind("<Return>", self._handle_ok)

        self._widgets.label.pack(fill=tk.X, expand=True)
        self._widgets.entry.pack(fill=tk.X, expand=True)
        self._widgets.ok.pack(side=tk.RIGHT)
        self._widgets.cancel.pack(side=tk.RIGHT)
        self._widgets.button_frame.pack(fill=tk.X, expand=True, pady=(4, 0))
        self._widgets.frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    @property
    def entry_text(self) -> str:
        return self._vars.label.get()

    @entry_text.setter
    def entry_text(self, val: str):
        return self._vars.label.set(val)

    @property
    def label_text(self) -> str:
        return self._vars.label.get()

    @label_text.setter
    def label_text(self, val: str):
        return self._vars.label.set(val)

    @property
    def title_text(self) -> str:
        return self.title()

    @title_text.setter
    def title_text(self, val: str):
        return self.title(val)

    def _handle_ok(self, ev: tk.Event | None = None) -> None:
        self._closed_ok = True
        self._vars.input.set(self._widgets.entry.get())
        self.event_generate("<<InputWindowOk>>")
        self.withdraw()

    def _handle_cancel(self) -> None:
        self._closed_ok = False
        self._vars.input.set(self._widgets.entry.get())
        self.event_generate("<<InputWindowCancel>>")
        self.withdraw()

    def block_for_input(self, parent: tk.Widget) -> str | None:
        self._widgets.entry.delete(0, tk.END)
        self.deiconify()
        self.update_idletasks()
        self.grab_set()
        self.lift(parent)
        self._widgets.entry.focus_set()
        parent.wait_variable(self._vars.input)
        self.grab_release()

        return None if not self._closed_ok else self._vars.input.get()

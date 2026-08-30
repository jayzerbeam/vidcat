import tkinter as tk
from abc import ABC
from warnings import warn


class DataEvents(ABC):
    """
    A mixin class providing custom virtual event capabilities with data payloads.
    """

    _inited: bool
    _registered_tcl_commands: list[str]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lazy_init()

    # needed as if DataEvents is after the widget in the MRO then our __init__ is not called
    def _lazy_init(self):
        if not hasattr(self, "_inited"):
            self._inited = True
            self._registered_tcl_commands = []

            # warn if DataEvents was subclassed AFTER tk.Widget
            for cls in self.__class__.__mro__:
                if issubclass(__class__, cls):
                    break
                if issubclass(tk.Widget, cls):
                    warn(
                        f"{__class__.__name__} is after a tk.Widget in class MRO."
                        f"{__class__.__name__} should be declared before any tk.Widget subclass in the class definition or overridden methods may not be called properly",
                        category=Warning,
                    )

    def bind_with_data(self, sequence, func, add=False):
        self._lazy_init()
        if not isinstance(self, tk.Widget):
            return

        tcl_command = self.register(func)
        self._registered_tcl_commands.append(tcl_command)

        script = f"{tcl_command} %w %d"
        if add:
            script = f"+{script}"

        self.tk.call("bind", self._w, sequence, script)

    def bind_all_with_data(self, sequence, func, add=False):
        self._lazy_init()
        if not isinstance(self, tk.Widget):
            return

        tcl_command = self.register(func)
        self._registered_tcl_commands.append(tcl_command)

        script = f"{tcl_command} %w %d"
        if add:
            script = f"+{script}"

        self.tk.call("bind", "all", sequence, script)

    def destroy(self):
        """
        Overrides the widget's destroy process to safely delete
        all underlying Tcl commands from memory before releasing the widget.
        """
        if hasattr(self, "_registered_tcl_commands"):
            for tcl_command in self._registered_tcl_commands:
                try:
                    # self.tk.call("rename", tcl_command, "")
                    self.deletecommand(tcl_command)
                except tk.TclError as ex:
                    print(f"delete command error for '{tcl_command}'", ex)
            self._registered_tcl_commands.clear()

        super().destroy()

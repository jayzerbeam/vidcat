import tkinter as tk
from collections.abc import Callable


class MessageSystem:
    def __init__(self):
        self.subscribers = {}

    def subscribe(self, msg_name: str, func: Callable) -> None:
        if msg_name not in self.subscribers:
            self.subscribers[msg_name] = []
        self.subscribers[msg_name].append(func)

    def send(self, message_name: str, *args, **kw) -> None:
        for func in self.subscribers.get(message_name, []):
            func(*args, **kw)


class MessageWindow(tk.Tk):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.messenger = MessageSystem()

    def message_send(self, message_name: str, *args, **kw):
        self.messenger.send(message_name, *args, **kw)

    def message_subscribe(self, message_name: str, func: Callable) -> None:
        self.messenger.subscribe(message_name, func)


class MessageWidget:
    def message_send(self, message_name: str, *args, **kw):
        if isinstance(self.winfo_toplevel(), EventWindow):
            self.winfo_toplevel().messenger.send(message_name, *args, **kw)

    def message_subscribe(self, message_name: str, func: callable):
        if isinstance(self.message_sendwinfo_toplevel(), EventWindow):
            self.winfo_toplevel().messenger.subscribe(message_name, func)

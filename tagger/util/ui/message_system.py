import tkinter as tk

class MessageSystem:
    def __init__(self):
        self.subscribers = {}

    def subscribe(self, msg_name:str, func:callable):
        if message_name not in self.subscribers:
            self.subscribers[message_name] = []
        self.subscribers[message_name].append(func)

    def send(self, message_name:str, *args, **kw):
        for func in self.subscribers.get(message_name, []):
            func(*args, **kw)

class MessageWindow(tk.Tk):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.messenger = MessageSystem()

    def message_send(self, message_name:str, *args, **kw):
        self.messenger.send(message_name, *args, **kw)

    def message_subscribe(self, message_name:str, func:callable):
        self.messenger.subscribe(message_name, func)

class MessageWidget:
    def message_send(self, message_name:str, *args, **kw):
        if isinstance(self.winfo_toplevel(), EventWindow):
            self.winfo_toplevel().messenger.send(message_name, *args, **kw)

    def message_subscribe(self, message_name:str, func:callable):
        if isinstance(self.winfo_toplevel(), EventWindow):
            self.winfo_toplevel().messenger.subscribe(message_name, func)

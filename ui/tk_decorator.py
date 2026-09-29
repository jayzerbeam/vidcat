"""Tk-aware function decorators."""

import time
import tkinter as tk
from collections.abc import Callable
from functools import wraps
from typing import Any


def tk_debounce(delay_ms: int, leading: bool = True) -> Callable:
    """Throttle a method of a tk.Widget so it runs at most once per delay_ms window.

    Pending calls are scheduled with the widget's after() so the callback always runs on
    the Tk main loop.

    With leading=True the first call runs immediately and then at most once per window,
    with a trailing call carrying the most recent arguments. With leading=False only the
    trailing call runs (classic debounce).
    """

    def decorator(func: Callable) -> Callable:
        pending_attr = f"_tk_debounce_pending_{func.__name__}"
        last_attr = f"_tk_debounce_last_{func.__name__}"

        def _cancel_pending(self: tk.Widget) -> None:
            pending = getattr(self, pending_attr, None)
            if pending is not None:
                try:
                    self.after_cancel(pending)
                except tk.TclError:
                    pass
                setattr(self, pending_attr, None)

        @wraps(func)
        def wrapper(self: tk.Widget, *args: Any, **kwargs: Any) -> Any:
            now = time.monotonic()
            elapsed_ms = (now - getattr(self, last_attr, 0.0)) * 1000

            if leading and elapsed_ms >= delay_ms:
                _cancel_pending(self)
                setattr(self, last_attr, now)
                return func(self, *args, **kwargs)

            _cancel_pending(self)

            def _trailing() -> None:
                setattr(self, pending_attr, None)
                setattr(self, last_attr, time.monotonic())
                func(self, *args, **kwargs)

            setattr(self, pending_attr, self.after(delay_ms, _trailing))
            return None

        return wrapper

    return decorator

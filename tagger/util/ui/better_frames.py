import tkinter as tk
from collections.abc import Callable
from dataclasses import astuple, dataclass
from tkinter import ttk
from typing import Any

from PIL import ImageTk

from .tk_event_data import DataEvents


# http://tkinter.unpythonic.net/wiki/VerticalScrolledFrame
class ScrolledFrame(DataEvents, ttk.Frame):
    def __init__(self, parent, direction=tk.BOTH, *args, **kw):
        super().__init__(parent, *args, **kw)

        # create a canvas object and a vertical scrollbar for scrolling it
        hscroll = vscroll = None
        canvas_params: dict[str, Any] = {"bd": 0, "highlightthickness": 0}
        if direction == tk.BOTH or direction == tk.HORIZONTAL:
            hscroll = ttk.Scrollbar(self, orient=tk.HORIZONTAL)
            canvas_params["xscrollcommand"] = hscroll.set
        if direction == tk.BOTH or direction == tk.VERTICAL:
            vscroll = ttk.Scrollbar(self, orient=tk.VERTICAL)
            canvas_params["yscrollcommand"] = vscroll.set
        canvas = tk.Canvas(self, **canvas_params)
        self._canvas = canvas
        canvas.grid(  # using grid() vs pack() is important, see note in _configure_canvas()
            column=0, row=0, sticky="NSEW"
        )
        if hscroll is not None and (direction == tk.BOTH or direction == tk.HORIZONTAL):
            hscroll.config(command=canvas.xview)
        if vscroll is not None and (direction == tk.BOTH or direction == tk.VERTICAL):
            vscroll.config(command=canvas.yview)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # reset the view
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)

        # create a frame inside the canvas which will be scrolled with it
        self.interior = interior = ttk.Frame(canvas)
        interior_id = canvas.create_window(0, 0, window=interior, anchor=tk.NW)

        # track changes to the canvas and frame width and sync them,
        # also updating the scrollbar
        def _configure_interior(event):
            # update the scrollbars to match the size of the inner frame
            canvas.config(
                scrollregion=(
                    0,
                    0,
                    interior.winfo_reqwidth(),
                    interior.winfo_reqheight(),
                )
            )
            if interior.winfo_reqwidth() != canvas.winfo_width():
                # update the canvas's width to fit the inner frame
                canvas.config(width=interior.winfo_reqwidth())
            if interior.winfo_reqheight() != canvas.winfo_height():
                # update the canvas's width to fit the inner frame
                canvas.config(height=interior.winfo_reqheight())

        interior.bind("<Configure>", _configure_interior)

        def _configure_canvas(event):
            # hide scroll bars if there's not enough content to scroll
            # NOTE pack_forget() doesn't work as expected when calling pack() again
            if vscroll is not None:
                if canvas.winfo_height() >= canvas.winfo_reqheight() and vscroll.winfo_ismapped():
                    vscroll.grid_forget()
                elif canvas.winfo_height() < canvas.winfo_reqheight() and not vscroll.winfo_ismapped():
                    vscroll.grid(column=1, row=0, sticky="NS")

            if hscroll is not None:
                if canvas.winfo_width() >= canvas.winfo_reqwidth() and hscroll.winfo_ismapped():
                    hscroll.grid_remove()
                elif canvas.winfo_width() < canvas.winfo_reqwidth() and not hscroll.winfo_ismapped():
                    hscroll.grid(column=0, row=1, sticky="EW")

            if interior.winfo_reqwidth() != canvas.winfo_width():
                # update the inner frame's width to fill the canvas
                canvas.itemconfigure(interior_id, width=canvas.winfo_reqwidth())
            if interior.winfo_reqheight() != canvas.winfo_height():
                # update the inner frame's width to fill the canvas
                canvas.itemconfigure(interior_id, height=canvas.winfo_reqheight())

        canvas.bind("<Configure>", _configure_canvas)

        def _mwheel(event):
            if event.state & 0x200:  # 0x200/512 is Button2 aka mousewheel
                self._canvas.xview_scroll(int(-1 * (event.delta / 60)), "units")
            else:
                self._canvas.yview_scroll(int(-1 * (event.delta / 60)), "units")

        canvas.bind("<MouseWheel>", _mwheel)


# NOTE so far this assumes all images are the same size
class ImagesFrame(DataEvents, ttk.Frame):
    _per_row: int
    _spacing: int
    _min_canvas_width: int = 1000
    _redraw_timer: str | None
    _images: dict[int, ImageTk.PhotoImage]
    _offset: dict[str, int]
    _canvas: tk.Canvas
    _vscroll: ttk.Scrollbar
    _hscroll: ttk.Scrollbar

    def __init__(self, parent, per_row: int = 0, spacing: int = 2, min_canvas_width: int = 1000, *args, **kw):
        super().__init__(parent, *args, **kw)
        self._images = {}
        self._per_row = per_row  # per_row 0 will auto fit to the canvas' current width
        self._spacing = spacing
        self._min_canvas_width = min_canvas_width
        self._redraw_timer = None

        # create a canvas object and a vertical scrollbar for scrolling it
        self._hscroll = ttk.Scrollbar(self, orient=tk.HORIZONTAL)
        self._vscroll = ttk.Scrollbar(self, orient=tk.VERTICAL)
        self._canvas = canvas = tk.Canvas(
            self,
            bd=0,
            highlightthickness=0,
            xscrollcommand=self._hscroll.set,
            yscrollcommand=self._vscroll.set,
        )
        canvas.grid(
            column=0, row=0, sticky="NSEW"
        )  # using grid() vs pack() is important, see note in _configure_canvas()
        self._hscroll.config(command=canvas.xview)
        self._vscroll.config(command=canvas.yview)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # reset the view
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)

        canvas.bind("<Configure>", self._handle_configure)

        def _canvas_click(event: tk.Event) -> None:
            normx = canvas.canvasx(event.x)
            normy = canvas.canvasy(event.y)
            ids = canvas.find_overlapping(normx, normy, normx, normy)
            if callable(self._image_click_func) and len(ids) > 0 and ids[0] in self._images:
                self._image_click_func(self._images[ids[0]])

        canvas.bind("<Double-Button-1>", _canvas_click)  # TODO refactor to send event and set prop

        def _mwheel(event):
            if event.state & 0x200:  # 0x200/512 is Button2 aka mousewheel
                self._canvas.xview_scroll(int(-1 * (event.delta / 60)), "units")
            else:
                self._canvas.yview_scroll(int(-1 * (event.delta / 60)), "units")

        canvas.bind("<MouseWheel>", _mwheel)

    def _handle_configure(self, ev: tk.Event) -> None:
        if self._redraw_timer is not None:
            self.after_cancel(self._redraw_timer)
        self._redraw_timer = self.after(100, self.redraw_images)

    def set_image_click_handler(self, func: Callable):
        self._image_click_func = func

    def add_images(self, images: tuple[ImageTk.PhotoImage, ...]) -> None:
        offset = Offset(x=0.0, y=0.0)
        for image in images:
            imgid = self._canvas.create_image(astuple(offset), anchor=tk.NW, image=image)
            self._images[imgid] = image
        self.redraw_images()

    # there's a bit of a performance bug where redaw will do a redraw->config->redraw
    def redraw_images(self) -> None:
        offset = Offset(x=0.0, y=0.0)
        for id, image in self._images.items():
            self._canvas.moveto(id, *astuple(offset))
            offset.x += self._spacing + image.width()
            self._canvas.config(
                width=max(offset.x, self._canvas.winfo_reqwidth()),
                height=offset.y + image.height(),
            )
            # self.canvas.tag_bind(imgid, '<Double-Button-1>', lambda event, imgid = imgid: _dblclick(imgid)) # NOTE DO NOT pass image = image in the lambda or it leads to a memory leak
            if self._per_row == 0:
                if offset.x + image.width() > max(self._min_canvas_width, self._canvas.winfo_width()):
                    offset.x = 0
                    offset.y = self._canvas.winfo_reqheight() + self._spacing
            elif self._per_row > 0 and len(self._images) % self._per_row == 0:
                offset.x = 0
                offset.y = self._canvas.winfo_reqheight() + self._spacing
        self.update_scrollbars()

    def update_scrollbars(self) -> None:
        self._canvas.config(scrollregion=(0, 0, self._canvas.winfo_reqwidth(), self._canvas.winfo_reqheight()))
        # hide scroll bars if there's not enough content to scroll
        # NOTE use grid() as pack_forget() doesn't work as expected when calling pack() again
        if self._canvas.winfo_height() >= self._canvas.winfo_reqheight() and self._vscroll.winfo_ismapped():
            self._vscroll.grid_forget()
        elif self._canvas.winfo_height() < self._canvas.winfo_reqheight() and not self._vscroll.winfo_ismapped():
            self._vscroll.grid(column=1, row=0, sticky="NS")

        if self._canvas.winfo_width() >= self._canvas.winfo_reqwidth() and self._hscroll.winfo_ismapped():
            self._hscroll.grid_remove()
        elif self._canvas.winfo_width() < self._canvas.winfo_reqwidth() and not self._hscroll.winfo_ismapped():
            self._hscroll.grid(column=0, row=1, sticky="EW")

    def clear_images(self):
        self._canvas.delete(tk.ALL)
        self._canvas.config(width=0, height=0)
        self._images.clear()


@dataclass
class Offset:
    x: float
    y: float

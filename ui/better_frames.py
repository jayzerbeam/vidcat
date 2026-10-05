import tkinter as tk
from collections.abc import Callable
from dataclasses import astuple, dataclass
from tkinter import ttk

from PIL import ImageTk


# NOTE so far this assumes all images are the same size
class ImagesFrame(ttk.Frame):
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

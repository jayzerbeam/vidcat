from collections.abc import Callable
from tkinter import ttk
from typing import Any
import tkinter as tk


# http://tkinter.unpythonic.net/wiki/VerticalScrolledFrame
class ScrolledFrame(ttk.Frame):
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
                if (
                    canvas.winfo_height() >= canvas.winfo_reqheight()
                    and vscroll.winfo_ismapped()
                ):
                    vscroll.grid_forget()
                elif (
                    canvas.winfo_height() < canvas.winfo_reqheight()
                    and not vscroll.winfo_ismapped()
                ):
                    vscroll.grid(column=1, row=0, sticky="NS")

            if hscroll is not None:
                if (
                    canvas.winfo_width() >= canvas.winfo_reqwidth()
                    and hscroll.winfo_ismapped()
                ):
                    hscroll.grid_remove()
                elif (
                    canvas.winfo_width() < canvas.winfo_reqwidth()
                    and not hscroll.winfo_ismapped()
                ):
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
class ImagesFrame(ttk.Frame):
    def __init__(self, parent, per_row=0, spacing=2, *args, **kw):
        super().__init__(parent, *args, **kw)
        self.images = {}
        self.offset = {"x": 0, "y": 0}
        self.per_row = per_row  # per_row 0 will auto fit to the canvas' current width
        self.spacing = spacing

        # create a canvas object and a vertical scrollbar for scrolling it
        hscroll = ttk.Scrollbar(self, orient=tk.HORIZONTAL)
        vscroll = ttk.Scrollbar(self, orient=tk.VERTICAL)
        self.canvas = canvas = tk.Canvas(
            self,
            bd=0,
            highlightthickness=0,
            xscrollcommand=hscroll.set,
            yscrollcommand=vscroll.set,
        )
        canvas.grid(
            column=0, row=0, sticky="NSEW"
        )  # using grid() vs pack() is important, see note in _configure_canvas()
        hscroll.config(command=canvas.xview)
        vscroll.config(command=canvas.yview)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # reset the view
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)

        def _configure_canvas(event):
            canvas.config(
                scrollregion=(0, 0, canvas.winfo_reqwidth(), canvas.winfo_reqheight())
            )
            # hide scroll bars if there's not enough content to scroll
            # NOTE use grid() as pack_forget() doesn't work as expected when calling pack() again
            if (
                canvas.winfo_height() >= canvas.winfo_reqheight()
                and vscroll.winfo_ismapped()
            ):
                vscroll.grid_forget()
            elif (
                canvas.winfo_height() < canvas.winfo_reqheight()
                and not vscroll.winfo_ismapped()
            ):
                vscroll.grid(column=1, row=0, sticky="NS")

            if (
                canvas.winfo_width() >= canvas.winfo_reqwidth()
                and hscroll.winfo_ismapped()
            ):
                hscroll.grid_remove()
            elif (
                canvas.winfo_width() < canvas.winfo_reqwidth()
                and not hscroll.winfo_ismapped()
            ):
                hscroll.grid(column=0, row=1, sticky="EW")

        canvas.bind("<Configure>", _configure_canvas)

        def _canvas_click(event):
            ids = canvas.find_overlapping(event.x, event.y, event.x, event.y)
            if (
                callable(self._image_click_func)
                and len(ids) > 0
                and ids[0] in self.images
            ):
                self._image_click_func(self.images[ids[0]][0])

        canvas.bind("<Double-Button-1>", _canvas_click)

        def _mwheel(event):
            if event.state & 0x200:  # 0x200/512 is Button2 aka mousewheel
                self.canvas.xview_scroll(int(-1 * (event.delta / 60)), "units")
            else:
                self.canvas.yview_scroll(int(-1 * (event.delta / 60)), "units")

        canvas.bind("<MouseWheel>", _mwheel)

    def set_image_click_handler(self, func: Callable):
        self._image_click_func = func

    def add_images(self, images: list):
        for image in images:
            imgid = self.canvas.create_image(
                (self.offset["x"], self.offset["y"]), anchor=tk.NW, image=image
            )
            self.offset["x"] = self.offset["x"] + self.spacing + image.width()
            self.canvas.config(
                width=max(self.offset["x"], self.canvas.winfo_reqwidth()),
                height=self.offset["y"] + image.height(),
            )
            # self.canvas.tag_bind(imgid, '<Double-Button-1>', lambda event, imgid = imgid: _dblclick(imgid)) # NOTE DO NOT pass image = image in the lambda or it leads to a memory leak
            self.images[imgid] = (image, self.offset)
            if self.per_row == 0:
                if self.offset["x"] + image.width() > self.canvas.winfo_width():
                    self.offset["x"] = 0
                    self.offset["y"] = self.canvas.winfo_reqheight() + self.spacing
            elif self.per_row > 0 and len(self.images) % self.per_row == 0:
                self.offset["x"] = 0
                self.offset["y"] = self.canvas.winfo_reqheight() + self.spacing
        self.canvas.event_generate("<Configure>")

    def clear_images(self):
        self.offset = {"x": 0, "y": 0}
        self.canvas.delete(tk.ALL)
        self.canvas.config(width=0, height=0)
        self.images.clear()

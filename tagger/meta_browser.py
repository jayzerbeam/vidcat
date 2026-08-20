import io, os, pickle, sys, re, threading
import tkinter as tk
from copy import deepcopy
from tkinter import  StringVar, IntVar, ttk
from PIL import Image, ImageTk
from functools import reduce

import util.file.alternate_data_streams as ADS
from util.file. alternate_data_streams import ADSFile
from util.video_thumbnailer import VideoThumbnailer
from util.ui.better_frames import ScrolledFrame, ImagesFrame
from util.ui.better_widgets import LabeledEntry, EditableList, ScrolledTreeview, FileTreeview
from util.ui.message_system import MessageSystem, MessageWindow, MessageWidget

# t is seconds
def nice_duration(t:int):
	units = ['h', 'm', 's']
	formatted = ''
	try:
		t = int(t)
		while t >= 1:
			formatted = f" {t % 60}{units.pop()}" + formatted
			t = int(t / 60)
		return formatted.strip()
	except ValueError:
		return '???'

def any_in_list(list1:list, list2:list):
	return len(list1) > 0 and len(list2) > 0 and len(set(list1) & set(list2)) > 0

class MainFrame(ttk.Frame, MessageWidget):
	def __init__(self, parent, basepath = None, *args, **kw):
		super().__init__(parent, *args, **kw)
		self._p = {}
		self._p['basepath'] = basepath

		self.ui = {}
		self.ui['pane'] = ttk.PanedWindow(self, orient = tk.HORIZONTAL)
		self.ui['filetree'] = __class__.FileMetaTreeview(self.ui['pane'])
		self.ui['filetree'].add_extensions(App.VID_EXTS)
		self.ui['pane'].add(self.ui['filetree'].container)
		self.ui['tabs'] = ttk.Notebook(self)
		self.ui['vidinfo'] = __class__.VideoInfoFrame(self.ui['tabs'])
		self.ui['filters'] = __class__.FilterFrame(self.ui['tabs'])
		self.ui['tabs'].add(self.ui['filters'], text = "Filters")
		self.ui['tabs'].add(self.ui['vidinfo'], text = "Video Info")
		self.ui['tabs'].select(1)
		self.ui['pane'].add(self.ui['tabs'])
		self.ui['pane'].grid(column = 0, row = 1, padx = 2, pady = 2, sticky="NSEW")
		self.columnconfigure(0, weight = 1)
		self.rowconfigure(1, weight = 1)

		def _ctrlkey(event):
			if event.keysym == 's':
				self.event_generate('<<SaveMetadata>>')
			if event.keysym == 'g':
				self.event_generate('<<GenerateThumbs>>')
		self.bind_all('<Control-KeyPress>', _ctrlkey)

		self.ui['filters'].bind('<<ApplyFiltersAnd>>', lambda event: self.apply_filters(operator = 'AND'))
		self.ui['filters'].bind('<<ApplyFiltersOr>>', lambda event: self.apply_filters(operator = 'OR'))
		self.ui['filters'].bind('<<ClearFilters>>', self.clear_filters)
		self.ui['filters'].bind('<<ApplyHighlight>>', self.apply_highlight)

	@property
	def basepath(self):
		return self._p['basepath']
	@basepath.setter
	def basepath(self, value:str):
		if os.path.isdir(value):
			self._p['basepath'] = value
			self.ui['filetree'].root_path = value
			self.ui['filetree'].update()

	@property
	def metadata(self):
		return self.ui['vidinfo'].metadata
	@metadata.setter
	def metadata(self, value:dict):
		self.ui['vidinfo'].metadata = value

	@property
	def selected_file(self):
		filename = self.ui['filetree'].selection()
		if len(filename) > 0 and os.path.isfile(filename[0]):
			return os.path.abspath(filename[0])

	@property
	def actors_list(self):
		pass
	@actors_list.setter
	def actors_list(self, items:dict):
		self.ui['filetree'].extra_columns_active(True)
		self.ui['filters'].ui['actors'].clear()
		for i in sorted(items.keys()):
			self.ui['filters'].ui['actors'].insert('', tk.END, i, text = str(i), values = (items[i]))

	@property
	def tags_list(self):
		pass
	@tags_list.setter
	def tags_list(self, items:dict):
		self.ui['filetree'].extra_columns_active(True)
		self.ui['filters'].ui['tags'].clear()
		for i in sorted(items.keys()):
			self.ui['filters'].ui['tags'].insert('', tk.END, i, text = str(i), values = (items[i]))

	def apply_filters(self, operator = 'OR'):
		self.ui['filetree'].apply_filters(self.ui['filters'].ui['actors'].selection(), self.ui['filters'].ui['tags'].selection(), operator = operator)
	def clear_filters(self, event):
		self.ui['filetree'].unhide_all()

	def apply_highlight(self, event):
		self.ui['filetree'].apply_highlight(self.ui['filters'].ui['actors'].selection(), self.ui['filters'].ui['tags'].selection())

	@property
	def play_ms(self):
		return self.ui['vidinfo'].play_ms

	@property
	def thumb_interval(self):
		return int(self.ui['vidinfo'].ui['generate'].ui['interval'].get())

	@property
	def video_info_frame(self):
		return self.ui['vidinfo']

	class FileMetaTreeview(FileTreeview):
		def __init__(self, parent, *args, **kw):
			super().__init__(parent, columns = ('actors', 'tags'), *args, **kw)
			self.heading('#1', text = 'Actors')
			self.heading('#2', text = 'Tags')
			self.extra_columns_active(False)
			#self.tag_configure('dir', background = '#EEE')
			self.tag_configure('highlight', background = '#DFD')

		def extra_columns_active(self, state):
			if state:
				self.column('#1', minwidth = 10, width = 100)
				self.column('#2', minwidth = 10, width = 250)
			else:
				self.column('#1', minwidth = 0, width = 0, stretch = False)
				self.column('#2', minwidth = 0, width = 0, stretch = False)

		def set_meta_columns(self, item, actors:list, tags:list):
			self.item(item, values = (', '.join(actors), ', '.join(tags)))

		def close_all(self):
			def _recurse(item):
				child = None
				for child in self.get_children(item):
					_recurse(child)
				if child:
					self.item(item, open = False)
			_recurse('')

		def apply_filters(self, actors, tags, operator = 'AND'):
			def _recurse(item):
				if self.tag_has('file', item):
					itemconfig = self.item(item)
					(item_actors, item_tags) = (itemconfig['values'][0].split(', '), itemconfig['values'][1].split(', ')) if len(itemconfig['values']) else ([], [])
					if operator == 'AND':
						if ((actors and len(set(actors) & set(item_actors)) != len(actors)) or
							(tags and len(set(tags) & set(item_tags)) != len(tags))):
							self.hide(item)
					else:
						if ((actors and len(set(actors) & set(item_actors)) == 0) or
							(tags and len(set(tags) & set(item_tags)) == 0)):
							self.hide(item)
				for child in self.get_children(item):
					_recurse(child)

			_recurse('')

		def apply_highlight(self, actors, tags):
			def _highlight_item(item, highlighted, see = False):
				itemconfig = self.item(item)
				if 'highlight' in itemconfig['tags'] and not highlighted:
					itemconfig['tags'].remove('highlight')
				if 'highlight' not in itemconfig['tags'] and highlighted:
					if isinstance(itemconfig['tags'], list):
						itemconfig['tags'].append('highlight')
					else:
						itemconfig['tags'] = ['highlight']
				self.item(item, tags = itemconfig['tags'])
				if highlighted and see:
					self.see(item)

			def _recurse(item):
				highlighted = False
				highlighted_children = False
				if self.tag_has('file', item):
					itemconfig = self.item(item)
					(item_actors, item_tags) = (itemconfig['values'][0].split(', '), itemconfig['values'][1].split(', ')) if len(itemconfig['values']) else ([], [])
					highlighted = any_in_list(actors, item_actors) or any_in_list(tags, item_tags)
					_highlight_item(item, highlighted, see = True)
				for child in self.get_children(item):
					_recurse(child)

			self.close_all()
			_recurse('')

	class FilterFrame(ttk.Frame):
		def __init__(self, parent, *args, **kw):
			super().__init__(parent, *args, **kw)
			self.ui = {}

			self.ui['actions'] = ttk.Frame(self)
			self.ui['actions'].grid(column = 0, row = 0, columnspan = 2)
			self.ui['scan'] = ttk.Button(self.ui['actions'], text = "Scan")
			self.ui['scan'].grid(column = 0, row = 0, sticky = "W", padx = 2, pady = 2)
			self.ui['filter_and'] = ttk.Button(self.ui['actions'], text = "Filter AND")
			self.ui['filter_and'].grid(column = 1, row = 0, sticky = "E", padx = 2, pady = 2)
			self.ui['filter_or'] = ttk.Button(self.ui['actions'], text = "Filter OR")
			self.ui['filter_or'].grid(column = 2, row = 0, sticky = "E", padx = 2, pady = 2)
			self.ui['filter_clear'] = ttk.Button(self.ui['actions'], text = "Clear Filters")
			self.ui['filter_clear'].grid(column = 3, row = 0, sticky = "E", padx = 2, pady = 2)
			self.ui['actions'].grid
			self.ui['actors'] = ScrolledTreeview(self, columns = ('count'), sortable = True)
			self.ui['actors'].heading('#0', text = "Actors")
			self.ui['actors'].heading('#1', text = "#")
			self.ui['actors'].column('#1', minwidth = 10, width = 50, stretch = False)
			self.ui['actors'].container.grid(column = 0, row = 1, sticky = "NSEW", padx = 2, pady = 2)
			self.ui['tags'] = ScrolledTreeview(self, columns = ('count'), sortable = True)
			self.ui['tags'].heading('#0', text = "Tags")
			self.ui['tags'].heading('#1', text = "#")
			self.ui['tags'].column('#1', minwidth = 10, width = 50, stretch = False)
			self.ui['tags'].container.grid(column = 1, row = 1, sticky = "NSEW", padx = 2, pady = 2)

			self.columnconfigure(0, weight = 1)
			self.columnconfigure(1, weight = 1)
			self.rowconfigure(1, weight = 1)

			def _apply_highlight(event):
				self.event_generate('<<ApplyHighlight>>')
			self.ui['scan'].config(command = lambda : self.event_generate('<<ScanMetadata>>'))
			self.ui['filter_and'].config(command = lambda : self.event_generate('<<ApplyFiltersAnd>>'))
			self.ui['filter_or'].config(command = lambda : self.event_generate('<<ApplyFiltersOr>>'))
			self.ui['filter_clear'].config(command = lambda : self.event_generate('<<ClearFilters>>'))
			self.ui['actors'].bind('<<TreeviewSelect>>', _apply_highlight)
			self.ui['tags'].bind('<<TreeviewSelect>>', _apply_highlight)

	class VideoInfoFrame(ttk.Frame, MessageWidget):
		def __init__(self, parent, *args, **kw):
			super().__init__(parent, *args, **kw)
			self.thumbs = []
			self._p = {}
			self._p['metadata'] = {}
			self._p['video_path'] = ''

			self.vars = {}
			self.vars['title'] = StringVar(self)
			self.vars['title'].trace_add('write', lambda *args: _set_metadata('title', self.vars['title'].get()))

			self.ui = {'panes':{}}
			self.ui['props'] = __class__.VideoProperties(self)
			self.ui['props'].grid(row = 0, sticky = "EW")
			self.ui['title'] = LabeledEntry(self, "Title", self.vars['title'])
			self.ui['title'].grid(row = 1, sticky = "EW")
			self.ui['pane'] = ttk.PanedWindow(self, orient = tk.HORIZONTAL)
			self.ui['lists'] = __class__.ActorTagPane(self.ui['pane'], orient = tk.VERTICAL, width = 200)
			self.ui['thumbnails'] = ImagesFrame(self, per_row = 0)
			self.ui['pane'].add(self.ui['lists'])
			self.ui['pane'].add(self.ui['thumbnails'])
			self.ui['pane'].grid(row = 2, column = 0, sticky = "NSEW", pady = 4, padx = 4)
			self.ui['generate'] = __class__.ThumbGen(self)
			self.ui['generate'].grid(row = 3, column = 0, sticky = "EW", pady = 4, padx = 4)
			self.ui['save'] = ttk.Button(self, text = "Save", command = lambda self = self: self.event_generate('<<SaveMetadata>>'))
			self.ui['save'].grid(row = 3, column = 0, sticky = "E", pady = 4, padx = 4, ipadx = 4)

			self.columnconfigure(0, weight = 1)
			self.rowconfigure(2, weight = 1)

			def _set_metadata(key, value):
				self._p['metadata'][key] = value

			def _play_from_image(image):
				# thumbnail contains frameno and ms timecode
				for img in self.thumbs:
					if img[0] == image:
						self.play_ms = img[1][2]
						self.event_generate('<<PlayFileAt>>')
						break
			self.ui['thumbnails'].set_image_click_handler(_play_from_image)

		@property
		def metadata(self):
			#self._['metadata']['title']  = self.ui['title'].get_text()
			self._p['metadata']['actors'] = self.ui['lists'].actors
			self._p['metadata']['tags']   = self.ui['lists'].tags
			return self._p['metadata']
		@metadata.setter
		def metadata(self, metadata:dict):
			self._p['metadata'] = metadata
			vp = metadata['video_properties']
			(vidw, vidh) = (vp['dimensions'][0], vp['dimensions'][1]) if len(vp['dimensions']) else (0, 0)
			viddur = vp['duration'] if 'duration' in vp else 0
			self.vars['title'].set(metadata['title'])
			self.ui['lists'].actor_listbox.clear_items()
			self.ui['lists'].actor_listbox.add_items(metadata['actors'])
			self.ui['lists'].tag_listbox.clear_items()
			self.ui['lists'].tag_listbox.add_items(metadata['tags'])
			self.ui['props'].set_properties(vidw, vidh, viddur)
			for t in self.thumbs:
				del t
			self.thumbs = [(ImageTk.PhotoImage(Image.open(io.BytesIO(t[0]))), t) for t in metadata['thumbnails']]
			self.ui['thumbnails'].clear_images()
			self.ui['thumbnails'].add_images([i[0] for i in self.thumbs])

		@property
		def video_path(self):
			return self._p['video_path']
		@video_path.setter
		def video_path(self, video_path):
			self._p['video_path'] = video_path

		@property
		def thumb_interval(self):
			return self.vars['interval'].get()

		def reload_thumbs(self):
			self.ui['thumbnails'].clear_images()
			self.ui['thumbnails'].add_images([ImageTk.PhotoImage(Image.open(io.BytesIO(t[0]))) for t in self._p['metadata']['thumbnails']])
			self.ui['generate'].ui['button'].config(state = tk.NORMAL)

		class VideoProperties(ttk.Frame, MessageWidget):
			def __init__(self, parent, *args, **kw):
				super().__init__(parent, *args, **kw)
				self.ui = {}
				self.ui['dimensions'] = ttk.Label(self)
				self.ui['dimensions'].pack(ipadx = 4, side = tk.LEFT)
				self.ui['duration'] = ttk.Label(self)
				self.ui['duration'].pack(ipadx = 4, side = tk.LEFT)

			def set_properties(self, width, height, duration):
				self.ui['dimensions'].config(text = f"dimensions: {width}x{height}")
				self.ui['duration'].config(text = f"duration: {nice_duration(duration)}")

		class ActorTagPane(ttk.PanedWindow, MessageWidget):
			def __init__(self, parent, *args, **kw):
				super().__init__(parent, *args, **kw)

				def _on_add(entry):
					if isinstance(entry, str):
						return entry.replace(',', '').strip()
					else:
						return entry

				self.ui = {}
				self.ui['actors'] = EditableList(self, "Actors", width = 1)
				self.ui['actors'].list_height(10)
				self.ui['actors'].on_add_handler(_on_add)
				self.add(self.ui['actors'])
				self.ui['tags'] = EditableList(self, "Tags", width = 1)
				self.ui['tags'].on_add_handler(_on_add)
				self.add(self.ui['tags'])

			@property
			def actors(self):
				return self.ui['actors'].items
			@property
			def actor_listbox(self):
				return self.ui['actors']

			@property
			def tags(self):
				return self.ui['tags'].items
			@property
			def tag_listbox(self):
				return self.ui['tags']

		class ThumbGen(ttk.Frame, MessageWidget):
			def __init__(self, parent, *args, **kw):
				def _gen_thumbs():
					self.event_generate('<<GenerateThumbs>>')
					self.ui['button'].config(state = tk.DISABLED)

				super().__init__(parent, *args, **kw)
				self.ui = {}
				self.ui['label'] = ttk.Label(self, text = "interval")
				self.ui['label'].grid(column = 0, row = 0)
				self.ui['interval'] = ttk.Entry(self, width = 5)
				self.ui['interval'].insert(0, '-30')
				self.ui['interval'].grid(column = 1, row = 0, padx = 4)
				self.ui['button'] = ttk.Button(self, text = "Generate", command = _gen_thumbs)
				self.ui['button'].grid(column = 2, row = 0)
				self.bind_all('<<GenerateThumbsComplete>>', lambda event: self.ui['button'].config(state = tk.ACTIVE))

			@property
			def interval(self):
				return int(self.ui['interval'].get())

class StatusWindow(tk.Toplevel):
	def __init__(self, parent, *args, **kw):
		super().__init__(parent, *args, **kw)
		self.resizable(False, False)
		self.title("Status")
		self.group(parent)

		self.ui = {}
		self.status_text = StringVar()
		self.ui['frame'] = ttk.Frame(self)
		self.ui['progress'] = ttk.Progressbar(self.ui['frame'], length = 500)
		self.ui['progress'].grid(column = 0, row = 0, padx = 2, pady = 2)
		self.ui['status'] = ttk.Label(self.ui['frame'], textvariable = self.status_text)
		self.ui['status'].grid(column = 0, row = 1, padx = 2, pady = 2)
		self.ui['frame'].pack(padx = 10, pady = 10)

	@property
	def info(self):
		return self.status_text.get()
	@info.setter
	def info(self, val):
		return self.status_text.set(val)
	@property
	def progress(self):
		return self.ui['progress']['value']
	@progress.setter
	def progress(self, val):
		self.ui['progress'].config(value = val)


class App:
	VIDEO_PLAYER = "C:\\Program Files\\MPC-BE\\mpc-be64.exe"
	VID_EXTS = ('.avi', '.mp4', '.m4v', '.mkv', '.mpg', '.mpeg', '.wmv', '.flv', '.f4v', '.mov')
	METADATA_STREAM = 'video_metadata'
	EMPTY_METADATA = {'title': "", 'video_properties': {'dimensions':(0, 0), 'duration':0}, 'actors': [], 'tags': [], 'thumbnails': []}

	def __init__(self, basepath, root):
		self.basepath = basepath
		self.root = root
		self.metadata = __class__.EMPTY_METADATA
		self.file_meta_filters = {}
		self.all_tags = []
		self.all_actors = []

		self.win = {}
		main_window = self.win['main'] = MainFrame(root)
		main_window.pack(expand = True, fill = tk.BOTH)
		main_window.basepath = basepath

		main_window.bind_all('<<FileSelect>>', lambda event: self.load_metadata())
		main_window.bind_all('<<FileExec>>', lambda event: self.play_file(main_window.selected_file))
		main_window.bind_all('<<PlayFileAt>>', lambda event: self.play_file(main_window.selected_file, main_window.play_ms))
		main_window.bind_all('<<GenerateThumbs>>', lambda event: self.generate_thumbnails())
		main_window.bind_all('<<SaveMetadata>>', lambda event: self.save_metadata())
		main_window.bind_all('<<ScanMetadata>>', lambda event: self.scan_files_metadata())
		#self.frame.bind_all('<<SaveMetadata>>', lambda event: adsfile.write_stream('video_metadata', pickle.dumps(metadata)))

		self.win['status'] = StatusWindow(self.root)
		self.win['status'].transient(self.win['main'])
		self.win['status'].overrideredirect(True)
		self.win['status'].withdraw()


	def load_metadata(self):
		print(f"loading metadata for {self.win['main'].selected_file}")
		METADATA_STREAM = 'video_metadata'
		filepath = self.win['main'].selected_file
		try:
			adsfile = ADSFile(filepath)
			if not adsfile.has_stream(__class__.METADATA_STREAM):
				adsfile.write_stream(__class__.METADATA_STREAM, pickle.dumps(__class__.EMPTY_METADATA))
			self.metadata = pickle.loads(adsfile.read_stream(__class__.METADATA_STREAM))
		except Exception:
			self.metadata = deepcopy(__class__.EMPTY_METADATA)
		self.win['main'].metadata = self.metadata

	def save_metadata(self):
		print(f"saving metadata for {self.win['main'].selected_file}")
		if not self.win['main'].selected_file:
			return
		self.metadata = self.win['main'].metadata
		adsfile = ADSFile(self.win['main'].selected_file)
		adsfile.write_stream(__class__.METADATA_STREAM, pickle.dumps(self.metadata))

	def scan_files_metadata(self):
		# pretty much none of this is thread-safe
		def _thread_entry():
			def _inc(totals:dict, keys):
				for k in keys:
					if k not in totals:
						totals[k] = 1
					else:
						totals[k] += 1

			actors = {}
			tags = {}
			items = self.win['main'].ui['filetree'].get_items(with_tags = ['file'])
			item_count = len(items)
			steps = 200 # bar updates steps, so it's not updating with every file
			for c, item in enumerate(items):
				if item_count <= steps or c % int(item_count / steps) == 0 or c + 1 == item_count:
					self.win['status'].progress = (c + 1) / item_count * 100.0
					self.win['status'].info = item
					self.root.update()
				filename = os.path.join(self.basepath, item)
				if os.path.isfile(filename) and ADS.has_stream(filename, __class__.METADATA_STREAM):
					try:
						metadata = pickle.loads(ADS.read_stream(filename, __class__.METADATA_STREAM))
					except pickle.UnpicklingError:
						print(f"failed to unpickle metadata for {filename}")
					else:
						self.win['main'].ui['filetree'].set_meta_columns(item, metadata['actors'], metadata['tags'])
						_inc(actors, metadata['actors'])
						_inc(tags, metadata['tags'])
			self.win['main'].actors_list = actors
			self.win['main'].tags_list = tags
			self.win['status'].withdraw()

		self.win['status'].geometry(f"+{round(self.root.winfo_x() + self.root.winfo_width() / 2 - self.win['status'].winfo_reqwidth() / 2)}+{round(self.root.winfo_y() + self.root.winfo_height() / 2 - self.win['status'].winfo_reqheight() / 2)}")
		self.win['status'].deiconify()
		self.win['status'].lift(self.win['main'])
		self.win['main'].ui['filetree'].unhide_all()
		#threading.Thread(target = _thread_entry).start()
		_thread_entry()


	# so not thread-safe
	def generate_thumbnails(self):
		filename = self.win['main'].selected_file
		if not filename:
			return

		def thread_entry():
			vt = VideoThumbnailer(filename)
			self.metadata['video_properties'] = {}
			self.metadata['video_properties']['dimensions'] = vt.get_dimensions()
			self.metadata['video_properties']['duration'] = round(vt.get_frame_count() / (vt.get_fps() or default_fps), 2)
			vt.extract_frames(interval = self.win['main'].thumb_interval)
			vt.resize_frames(resize_height = 200)
			jpgs = vt.get_jpgs(jpgq = 70)
			self.metadata['thumbnails'] = jpgs
			self.win['main'].metadata = self.metadata
			self.win['main'].event_generate('<<GenerateThumbsComplete>>')

		threading.Thread(target = thread_entry).start()

	def play_file(self, filepath, startms = 0):
		os.spawnv(os.P_NOWAIT, __class__.VIDEO_PLAYER, [os.path.basename(__class__.VIDEO_PLAYER), f'"{filepath}"', f"/start {startms}"])

if __name__ == "__main__":
	if len(sys.argv) <= 1:
		print("filename argument required")
		raise SystemExit
	filepath = sys.argv[1]
	if not os.path.isdir(filepath):
		print(f"{filepath} is not a directory")
		raise SystemExit
	filepath = os.path.abspath(filepath)

	window = MessageWindow()
	window.title(f"Video Metadata Browser")
	window.geometry("1200x1000")
	app = App(filepath, window)
	window.mainloop()

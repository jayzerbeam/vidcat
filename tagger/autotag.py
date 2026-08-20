import pickle, os, sys, re
from glob import glob
from util.video_thumbnailer import VideoThumbnailer
import util.alternate_data_streams as ads
from util.alternate_data_streams import ADSFile

VID_EXTS = ('.avi', '.mp4', '.m4v', '.mkv', '.mpg', '.mpeg', '.wmv', '.flv', '.f4v', '.mov')

class VideoParser:
	METADATA_STREAM_NAME = 'video_metadata'
	regex = {
		'full': re.compile('(.*?)-(.*?)-(.*)', re.I | re.U),
		'partial': re.compile('(.*?)-(.*)', re.I | re.U)
	}
	thumbnail_params = {
		'resize_height': 200,
		'jpgq': 66
	}

	def __init__(self, filename):
		if not os.path.isfile(filename):
			raise FileNotFoundError(f"{filename} is not a file")
		self.path = os.path.abspath(filename)
		self.basename = os.path.basename(self.path)
		print(f"VideoParser: {self.basename}")
		adsfile = self.adsfile = ADSFile(self.path)
		if adsfile.has_stream(__class__.METADATA_STREAM_NAME):
			self.metadata = pickle.loads(adsfile.read_stream(__class__.METADATA_STREAM_NAME))
		else:
			self.metadata = {'title': "", 'video_properties':{}, 'actors': [], 'tags': [], 'thumbnails': []}

	def do_thumbnails(self, reparse = True):
		if not reparse and self.metadata['thumbnails']:
			return
		default_fps = 30.0
		tp = __class__.thumbnail_params
		vt = VideoThumbnailer(self.path)
		dimensions = vt.get_dimensions()
		self.metadata['video_properties'] = {}
		self.metadata['video_properties']['dimensions'] = dimensions
		self.metadata['video_properties']['duration'] = round(vt.get_frame_count() / (vt.get_fps() or default_fps), 2)
		vt.extract_frames(interval = (-40 if dimensions[0] / dimensions[1] < 1.5 else -30))
		vt.resize_frames(resize_height = tp['resize_height'])
		jpgs = vt.get_jpgs(jpgq = tp['jpgq'])
		self.metadata['thumbnails'] = jpgs

	def parse_filename(self, reparse = True):
		if reparse or self.metadata['title']:
			self.metadata['title'] = os.path.splitext(self.basename)[0].replace('_', ' ')

	def write_metadata(self):
		return self.adsfile.write_stream(__class__.METADATA_STREAM_NAME, pickle.dumps(self.metadata))


def commastr2list(str):
	# split on comma, filter empties, convert lowercase
	return list(map(lambda s2: s2.strip().lower(), filter(lambda s1: s1.strip(), str.split(','))))

if __name__ == '__main__':
	if len(sys.argv) <= 1:
		print("filepath argument required")
		exit()
	filepath = sys.argv[1]
	if not os.path.exists(filepath):
		raise FileNotFoundError(f"{filepath} not found")

	filepath = os.path.abspath(filepath)
	if os.path.isdir(filepath):
		os.chdir(filepath)
		filelist = glob('**', recursive = True)
		for idx, f in enumerate(filelist):
			if not os.path.isfile(f):
				continue

			path, ext = os.path.splitext(f)
			if ext in VID_EXTS:
				print(f"{idx + 1} / {len(filelist)}")
				vp = VideoParser(f)
				vp.parse_filename(False)
				vp.do_thumbnails(True)
				bytes_written = vp.write_metadata()
				print(f"{bytes_written}b metadata written\n")
	elif os.path.isfile(filepath):
		vp = VideoParser(filepath)
		vp.parse_filename(True)
		vp.do_thumbnails(True)
		bytes_written = vp.write_metadata()
		print(f"{bytes_written}b metadata written\n")

import pickle, os, sys
from glob import glob, iglob
from argparse import ArgumentParser
from lib.alternate_data_streams import ADSFile

VID_EXTS = ('.avi', '.mp4', '.m4v', '.mkv', '.mpg', '.mpeg', '.wmv', '.flv', '.f4v', '.mov')
STREAM_NAME = 'video_metadata'

class Args:
	def __init__(self):
		parser = self.parser = ArgumentParser()
		parser.add_argument('-a', '--actors', default = [], nargs = '*')
		parser.add_argument('-t', '--tags', default = [], nargs = '*')
		parser.add_argument('-ra', '--remove_actors', default = [], nargs = '*')
		parser.add_argument('-rt', '--remove_tags', default = [], nargs = '*')
		parser.add_argument('-r', '--recursive', action = 'store_true')
		parser.add_argument('glob')
		self.names = parser.parse_args()

if __name__ == '__main__':
	args = Args()
	for f in iglob(args.names.glob, recursive = args.names.recursive):
		path, ext = os.path.splitext(f)
		if not ext in VID_EXTS:
			continue
		print(f)
		ads = ADSFile(f)
		if not ads.has_stream(STREAM_NAME):
			continue
		metadata = pickle.loads(ads.read_stream(STREAM_NAME))
		metadata['actors'] = sorted(list(set(metadata['actors'] + args.names.actors)))
		metadata['actors'] = [a for a in metadata['actors'] if a not in args.names.remove_actors]
		metadata['tags'] = sorted(list(set(metadata['tags'] + args.names.tags)))
		metadata['tags'] = [t for t in metadata['tags'] if t not in args.names.remove_tags]
		bytes_written = ads.write_stream(STREAM_NAME, pickle.dumps(metadata))
		print(f"{bytes_written} bytes written")

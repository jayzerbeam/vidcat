from alternate_data_streams import ADSFile
from video_thumbnailer import VideoThumbnailer

class ADSVideoMetadata:
	ads_name = 'video_metadata'

	def __init__(self, filename):
		adsfile = self.adsfile = ADSFile(filename)
		if adsfile.has_stream(__class__.ads_name):
			self.metadata = pickle.loads(adsfile.read_stream(__class__.ads_name))
        else:
			self.metadata = {'title': "", 'actors': [], 'tags': [], 'thumbnails': []}
	
	def write_metadata(self):
		adsfile.write_stream(__class__.ads_name, pickle.dumps(self.metadata))

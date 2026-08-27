import pickle

from alternate_data_streams import ADSFile


class ADSVideoMetadata:
    ads_name = "video_metadata"

    def __init__(self, filename):
        self._adsfile = self.adsfile = ADSFile(filename)
        if self._adsfile.has_stream(__class__.ads_name):
            self.metadata = pickle.loads(self._adsfile.read_stream(__class__.ads_name))
        else:
            self.metadata = {"title": "", "actors": [], "tags": [], "thumbnails": []}

    def write_metadata(self):
        self._adsfile.write_stream(__class__.ads_name, pickle.dumps(self.metadata))

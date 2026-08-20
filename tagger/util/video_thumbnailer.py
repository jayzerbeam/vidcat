import sys
import cv2

class VideoThumbnailer:
	_DEFAULT_FPS = 30 # incase it's unknown

	def __init__(self, filename:str = None):
		self.filename = filename
		self.frames = None
		self.cap = cv2.VideoCapture(self.filename)

	def get_dimensions(self):
		return (round(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)), round(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
	
	def get_fps(self):
		return self.cap.get(cv2.CAP_PROP_FPS)

	def get_frame_count(self):
		return int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

	# interval
	#	positive is seconds
	#	negative is divisions
	def extract_frames(self, interval:int = 30):
		if interval == 0:
			raise ValueError(f"invalid interval ({interval})")
		video_fps = self.cap.get(cv2.CAP_PROP_FPS) or __class__._DEFAULT_FPS
		video_length = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)) - 1
		print(f"video: {video_length} frames, {video_fps} fps, {round(video_length / video_fps)}s")

		if interval < 0:
			interval = video_length / (-interval + 1)
		else:
			interval = video_fps * interval
		print(f"interval {interval}")

		frames = []
		if self.cap.isOpened() and video_length > 0:
			frameno = interval
			while round(frameno) < video_length:
				rfn = round(frameno)
				self.cap.set(cv2.CAP_PROP_POS_FRAMES, rfn)
				success, image = self.cap.read()
				if success:
					frames.append((image, rfn, round(frameno / video_fps * 1000)))
					print(f"+{rfn}", end = " ")
				else:
					print(f"-{rfn}", end = " ")
				frameno += interval
			print("")
		self.frames = frames
		return frames

	# this is a destructive operation
	def resize_frames(self, resize_height:int = 240):
		if not self.frames:
			return

		print("resizing frames...")
		resized_frames = []
		for fdata in self.frames:
			h,w,bpp = fdata[0].shape
			newwh = (int(resize_height / h * w), resize_height)
			rimage = cv2.resize(fdata[0], newwh, interpolation = (cv2.INTER_AREA if resize_height <= h else cv2.INTER_CUBIC))
			print(f"{fdata[1]}", end = " ")
			resized_frames.append((rimage,) + fdata[1:])
		print(f"\nresized {w}x{h} -> {newwh[0]}x{newwh[1]}")
		self.frames = resized_frames
		return resized_frames

	def get_jpgs(self, jpgq:int = 70):
		if not self.frames:
			return

		jpgs = []
		for fdata in self.frames:
			success, jpg = cv2.imencode(".jpg", fdata[0], [cv2.IMWRITE_JPEG_QUALITY, jpgq])
			#cv2.imwrite(f"{sys.argv[1]}_{frameno}.jpg", image, [cv2.IMWRITE_JPEG_QUALITY, jpgq])
			if success:
				print(f"{fdata[1]} ({len(jpg)}b)", end = " ")
				jpgs.append((jpg,) + fdata[1:])
			else:
				print(f"{fdata[1]} (failed)", end = " ")
		print("")
		return jpgs

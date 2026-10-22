# VidCat

Short for Video Cataloger. VidCat is simple software for cataloging video clips.

## Description

VidCat uses file system based sidecar files to store metadata such as thumbnails, actors, and tags for each video file. The UI is similar to a basic file explorer and provides functionality for filtering based on actors/tags as well.

This started out as a small script to help me manage video clips off my cameras and I've been slowly hacking in more features since then.

### Features

- video filtered file browsing
- video metadata:
	- thumbnails
	- actor/tag lists
	- bookmarks
- filter by actor/tags
- basic video scrubbing
- playback from thumbnail or bookmarks

### Sidecar files

Thumbnails, actors, and tags are stored to file system based sidecar files and are effectively attached to the file (see [Compatibility](#compatibility) for more details)

## Usage

`uv run vidcat.pyw <dir>`

### Config

Use `vidcat.cfg.json` for configurable options. A sample config with defaults has been provided.

## Compatibility

Only Windows NTFS is presently supported as NTFS Alternate Data Streams are used for the sidecar data.

Mac/Linux sidecar via extended attributes is TBD.

## Known Issues

The actors/tags in the filter tab only represents a snapshot of the corresponding metadata at the time the scan is performed. Updates to actor/tag metadata on files will not be reflected in the filters list unless another full scan is done.

## Background

This started as a simple app to help catalog video files coming off my camera.

The initial requirements I wanted were:

- lightweight app
- quickly and easily browse files
- support arbitrary metadata without having to re-write the entire file (some video containers support this but often require re-writing the entire file)
- metadata intrinsically lives with the video file

Python Tk and NTFS alternate data streams fit the bill nicely.

Most of the app was written by hand but then I started doing more LLM assisted coding around commit `d0ec13c`

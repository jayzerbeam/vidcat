# VidCat

Short for Video Cataloger. VidCat is simple software for cataloging video clips.

## Description

VidCat uses file system based sidecar files to store metadata such as thumbnails, actors, and tags for each video file. The UI is similar to a basic file explorer and provides functionality for filtering based on actors/tags as well.

This started out as a small script to help me manage video clips off my cameras and I've been slowly hacking in more features since then.

### Features

- file browsing
- thumbnail generation
- actor/tag lists
- filter by actor/tags
- playback from thumbnail times

### Sidecar files

Thumbnails, actors, and tags are stored to file system based sidecar files and are effectively attached to the file (see [Compatibility](#compatibility) for more details)

## Usage

`uv run browser.pyw <dir>`

### Config

Use `browser.cfg.json` for configurable options. A sample config with defaults has been provided.

## Compatibility

Only Windows NTFS is presently supported as NTFS Alternate Data Streams are used for the sidecar data.

Mac/Linux sidecar via extended attributes is TBD.

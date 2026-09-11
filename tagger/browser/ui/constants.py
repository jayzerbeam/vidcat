from enum import StrEnum


class VirtualEventSequence(StrEnum):
    PLAY_FROM_MS = "<<PalyFromMs>>"
    GEN_THUMBS = "<<GenerateThumbs>>"
    GEN_THUMBS_COMPLETE = "<<GenerateThumbsComplete>>"
    GEN_ALL_THUMBS = "<<GenerateAllThumbs>>"
    GEN_ALL_THUMBS_RECURSIVE = "<<GenerateAllThumbsRecursive>>"
    GEN_MISSING_THUMBS = "<<GenerateMissingThumbs>>"
    GEN_MISSING_THUMBS_RECURSIVE = "<<GenerateMissingThumbsRecursive>>"
    SCAN_METADATA = "<<ScanMetadata>>"
    SAVE_METADATA = "<<SaveMetadata>>"
    FILTERS_AND = "<<FiltersAnd>>"
    FILTERS_OR = "<<FiltersOr>>"
    FILTERS_CLEAR = "<<FiltersClear>>"
    PATH_DELETE = "<<PathDelete>>"
    SCAN_PATH_FILES = "<<RescanPathFiles>>"
    SCAN_PATH_METADATA = "<<ScanPathMetadata>>"


class TkVarNames(StrEnum):
    FILE_SIZE = "FILE_SIZE"
    FILE_PATH = "FILE_PATH"
    HIGHLIGHTED_ACTORS = "HIGHLIGHTED_ACTORS"
    HIGHLIGHTED_TAGS = "HIGHLIGHTED_TAGS"
    META_ACTORS = "METADATA_ACTORS"
    META_TAGS = "METADATA_TAGS"
    META_TITLE = "METADATA_TITLE"
    META_SIZE = "METADATA_SIZE"
    THUMB_INTERVAL = "THUMB_INTERVAL"
    THUMB_HEIGHT = "THUMB_HEIGHT"
    VIDEO_RES = "VIDEO_RESOLUTION"
    VIDEO_LEN = "VIDEO_LENGTH"

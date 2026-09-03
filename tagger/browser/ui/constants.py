from enum import StrEnum


class VirtualEventSequence(StrEnum):
    PLAY_FROM_MS = "<<PalyFromMs>>"
    GENERATE_THUMBS = "<<GenerateThumbs>>"
    GENERATE_THUMBS_COMPLETE = "<<GenerateThumbsComplete>>"
    SCAN_METADATA = "<<ScanMetadata>>"
    SAVE_METADATA = "<<SaveMetadata>>"
    FILTERS_AND = "<<FiltersAnd>>"
    FILTERS_OR = "<<FiltersOr>>"
    FILTERS_CLEAR = "<<FiltersClear>>"
    APPLY_HIGHHIGHT = "<<ApplyHighlight>>"


class TkVarNames(StrEnum):
    META_ACTORS = "METADATA_ACTORS"
    META_TAGS = "METADATA_TAGS"
    META_TITLE = "METADATA_TITLE"
    META_SIZE = "METADATA_SIZE"
    THUMB_INTERVAL = "THUMB_INTERVAL"
    THUMB_HEIGHT = "THUMB_HEIGHT"
    VIDEO_RES = "VIDEO_RESOLUTION"
    VIDEO_LEN = "VIDEO_LENGTH"

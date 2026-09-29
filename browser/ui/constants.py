from enum import StrEnum


class VirtualEventSequence(StrEnum):
    # treeivew menu actions
    GOTO_PATH = "<<GotoPath>>"
    BULK_ADD_ACTOR = "<<BulkAddActor>>"
    BULK_DEL_ACTOR = "<<BulkDelActor>>"
    BULK_ADD_TAG = "<<BulkAddTag>>"
    BULK_DEL_TAG = "<<BulkDelTag>>"
    BULK_GEN_THUMBS = "<<BulkGenThumbs>>"
    BULK_DEL_METADATA = "<<BulkDelMetadata>>"
    SCAN_PATH_FILES = "<<RescanPathFiles>>"
    SCAN_PATH_METADATA = "<<ScanPathMetadata>>"
    PATH_DELETE = "<<PathDelete>>"

    # filter frame
    FILTERS_AND = "<<FiltersAnd>>"
    FILTERS_OR = "<<FiltersOr>>"
    FILTERS_CLEAR = "<<FiltersClear>>"
    SCAN_METADATA = "<<ScanMetadata>>"

    # vidinfo frame
    SAVE_METADATA = "<<SaveMetadata>>"
    PLAY_FROM_MS = "<<PalyFromMs>>"
    GEN_THUMBS = "<<GenerateThumbs>>"

    # misc
    GEN_THUMBS_COMPLETE = "<<GenerateThumbsComplete>>"


class TkVarNames(StrEnum):
    """These are var names for tk.Variables bound by both the App and various widgets.
    Creating multiple instances of the widgets could be problematic as the tk vars are bound to constant var names
    """

    # treeview related
    HIGHLIGHTED_ACTORS = "HIGHLIGHTED_ACTORS"
    HIGHLIGHTED_TAGS = "HIGHLIGHTED_TAGS"
    CONTEXT_IID = "CONTEXT_IID"
    SELECTED_IIDS = "SELECTED_IIDS"
    TRIGGERED_IID = "TRIGGERED_IID"

    # video props/metadata
    FILE_SIZE = "FILE_SIZE"
    FILE_PATH = "FILE_PATH"
    META_ACTORS = "METADATA_ACTORS"
    META_TAGS = "METADATA_TAGS"
    META_TITLE = "METADATA_TITLE"
    META_SIZE = "METADATA_SIZE"
    VIDEO_RES = "VIDEO_RESOLUTION"
    VIDEO_LEN = "VIDEO_LENGTH"

    # misc
    THUMB_INTERVAL = "THUMB_INTERVAL"
    THUMB_HEIGHT = "THUMB_HEIGHT"

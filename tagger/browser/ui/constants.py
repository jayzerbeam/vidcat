from enum import StrEnum


class VirtualEventSequence(StrEnum):
    PLAY_FROM_MS = "<<PalyFromMs>>"
    INTERVAL_CHANGED = "<<IntervalChanged>>"
    GENERATE_THUMBS = "<<GenerateThumbs>>"
    GENERATE_THUMBS_COMPLETE = "<<GenerateThumbsComplete>>"
    SCAN_METADATA = "<<ScanMetadata>>"
    SAVE_METADATA = "<<SaveMetadata>>"
    FILTERS_AND = "<<FiltersAnd>>"
    FILTERS_OR = "<<FiltersOr>>"
    FILTERS_CLEAR = "<<FiltersClear>>"
    APPLY_HIGHHIGHT = "<<ApplyHighlight>>"

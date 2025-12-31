from dataclasses import dataclass, field
from enum import IntEnum, Enum
from src import utils


class SectionSignature(Enum):
  """Block (section) signatures in the library."""
  HSMA_MAJOR_SECTION = b'hsma'
  HFMA_OUTER_ENVELOPE = b'hfma'
  PLMA_LIBRARY_MASTER = b'plma'

  # Album/Collection
  LAMA_ALBUM_MASTER = b'lama'
  IAMA_ALBUM_ITEM = b'iama'
  # Artist
  LAMA_ARTIST_MASTER = b'lAma'
  IAMA_ARTIST_ITEM = b'iAma'

  # Track
  LTMA_TRACK_MASTER = b'ltma'
  ITMA_TRACK_ITEM = b'itma'

  # Playlist
  LPMA_PLAYLIST_MASTER = b'lPma'
  LMPA_PLAYLIST_ITEM = b'lpma'
  IPFA_BOMA = b'ipfa'
  SLST_SMART_PLAYLIST_BOMA = b'SLst'

  # General data container
  BOMA_CONTAINER = b'boma'

  # ??
  SSMA_CONTAINER = b'ssma'

  BOOK = b'book'


class SectionType(IntEnum):
  """Section types in hsma structure."""

  ITMA_TRACK_MASTER = 1
  LPMA_PLAYLIST_MASTER = 2
  HFMA_INNER_MASTER = 3
  LAMA_ALBUM_DATA = 4
  LAMA_ARTIST_DATA = 5
  PLMA_LIBRARY_MASTER = 6

  # This seems to be the last one.
  LPMA_UNK = 17

class BomaWideCharType(IntEnum):
  TRACK_TITLE = 0x2
  ALBUM = 0x3
  ARTIST = 0x4
  GENRE = 0x5
  KIND = 0x6
  COMMENT = 0x8
  COMPOSER = 0xC
  GROUPING_CLASSICAL = 0xE
  EPISODE_COMMENT = 0x12  # (maybe)
  EPISODE_SYNOPSIS = 0x16
  SERIES_TITLE = 0x18
  EPISODE_NUMBER = 0x19
  ALBUM_ARTIST = 0x1B
  SERIES_UNKNOWN = 0x1C  # Series (Unknown Info)
  SORT_ORDER_TRACK_NAME = 0x1E
  SORT_ORDER_ALBUM = 0x1F
  SORT_ORDER_ARTIST = 0x20
  SORT_ORDER_ALBUM_ARTIST = 0x21
  SORT_ORDER_COMPOSER = 0x22
  LICENSOR_COPYRIGHT = 0x2B  # Licensor/Copyright Holder ?
  UNKNOWN_002E = 0x2E  # (not sure)
  SERIES_SYNOPSIS = 0x33
  FLAVOR_STRING = 0x34
  EMAIL_PURCHASER = 0x3B
  NAME_PURCHASER = 0x3C
  WORK_NAME = 0x3F  # (for Classical Tracks)
  MOVEMENT_NAME = 0x40  # (for Classical Tracks)
  FILE_PATH = 0x43
  PLAYLIST_NAME = 0xC8
  IAMA_ALBUM = 0x12C
  IAMA_ALBUM_ARTIST_1 = 0x12D  # iama Album Artist
  IAMA_ALBUM_ARTIST_2 = 0x12E  # iama Album Artist
  IAMA_ARTIST_1 = 0x190
  IAMA_ARTIST_2 = 0x191
  SERIES_TITLE_ALT = 0x12F  # Series Title (Duplicate)
  HEX_STRING_64X4B_1 = 0x1F4  # Unknown 64x4b Hex String
  MANAGED_MEDIA_FOLDER = 0x1F8
  HEX_STRING_64X4B_2 = 0x1FE  # Unknown 64x4b Hex String
  SONG_TITLE_MUSICDB = 0x2BE  # Song Title (Application.musicdb)
  SONG_ARTIST_MUSICDB = 0x2BF   # Song Artist (Application.musicdb)


class BomaUtf8Short(IntEnum):
  XLM_BLOCK_1 = 0x36
  XLM_BLOCK_2 = 0x38
  XLM_ARTWORK = 0x192


class BomaUtf8Long(IntEnum):
  FILE_URL = 0xB
  XLM_BLOCK_1 = 0x1D
  # Commented out: I'm pretty sure this is not an utf-8 long entry.
  # XLM_BLOCK_2 = 0xCD
  XLM_BLOCK_3 = 0x2BC
  XLM_BLOCK_4 = 0x3CC


class BomaBookType(IntEnum):
  # TODO: properly handle those
  BOOK1 = 0x42

  # These are listed in the doc, but I don't find any 'book' signature there.
  # BOOK3 = 0x1FD
  # BOOK2 = 0x1FC
  # BOOK4 = 0x200

class BomaTrackNumericsType(IntEnum):
  TRACK_NUMERICS_1 = 0x1
  TRACK_NUMERICS_2 = 0x17


class BomaOtherType(IntEnum):
  VIDEO = 0x24

class BomaPlaylistType(IntEnum):
  IPFA_PLAYLIST = 0xCE
  SLST_SMART_PLAYLIST = 0xc9
  # UNK_PLAYLIST_2 = 0xca


# I know those point to something but I cannot figure what exactly.
# class BomaAlbumType(IntEnum):
#   UNK_ALB_1 = 0x133
# class BomaArtistType(IntEnum):
#   UNK_ART_2 = 0x193


@dataclass(slots=True)
class BomaDataContainer:
  """
  Metadata structure for data blocks.

  boma structure holds metadata for multiple types of blocks.
  """

  type: (
    BomaWideCharType
    | BomaUtf8Short
    | BomaUtf8Long
    | BomaBookType
    | BomaOtherType
    | int
  )
  value: bytes | str | None


@dataclass(slots=True)
class ItmaTrack:
  """
  Track.

  itma structure holds track information
  """

  persistent_id: int
  id: int
  starred: bool
  rating: int
  unchecked: int

  # From Track Numerics 1
  bitrate: int | None = None
  date_added: int | None = None
  date_modified: int | None = None
  normalization: int | None = None
  song_time_ms: int | None = None
  file_size: int | None = None

  # From Track Numerics 2
  date_last_played: int | None = None
  play_count: int | None = None

  bomas: list[BomaDataContainer] = field(default_factory=list)

  @property
  def stars(self) -> int:
    return int(self.rating/100 * 5)


@dataclass(slots=True)
class LpmaPlaylist:
  """A playlist."""

  persistent_id: int
  date_created: int
  date_modified: int
  num_tracks: int
  is_smart: bool = False
  is_folder: bool = False

  persistent_track_ids: list[int] = field(default_factory=list, repr=False)
  bomas: list[BomaDataContainer] = field(default_factory=list)


@dataclass(slots=True)
class Hsma:
  """Main structure containing section type and sub_section data."""

  section_type: SectionType
  sub_section: (
    str
    | list[BomaDataContainer]
    | list[list[BomaDataContainer]]
    | list[ItmaTrack]
    | list[LpmaPlaylist]
    | None
  ) = None


@dataclass(slots=True)
class RawLibrary:

  version: str
  date: int
  tz_offset: int
  sections: list[Hsma]

  @property
  def datetime(self):
    return utils.get_datetime(self.date, self.tz_offset)

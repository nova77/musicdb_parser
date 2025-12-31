
from dataclasses import dataclass, field
from enum import IntEnum
from src import utils


class BlockType(IntEnum):
  """Block (section) types in msdh structure."""

  MLTH_TRACK_MASTER = 1  # Master track list
  MLPH_PLAYLIST_MASTER = 2  # Playlist list
  BINARY_UNK = 3  # This is unknown binary data
  LIBRARY_LOCATION = 4  # Library Location URI
  MLAH_ALBUM_COLLECTION = 9  # Album/Collection
  MLIH_ARTIST = 11  # Artist
  MHGH_LIBRARY_INFO = 12  # Library Info
  MLTH_TRACK = 13  # Track (?)
  MLPH_TRACK = 14  # Track (?)
  MLRH_UNK = 15  # ???
  MFDH_OUTER_ENVELOPE = 16  # Outer Envelope
  XLM = 19  # XML Block
  MLQH_UNK = 20  # ????
  MLSH_UNK = 21  # ????
  STSH_UNK = 23  # ????

  @classmethod
  def unk_types(cls) -> list['BlockType']:
    return [
      cls.BINARY_UNK,
      cls.MLRH_UNK,
      cls.MLQH_UNK,
      cls.MLSH_UNK,
      cls.STSH_UNK,
    ]


class MhohFlexType(IntEnum):
  """Metadata types for mhoh structure."""

  # Existing and Updated Entries
  TRACK_TITLE = 0x02
  ALBUM_TITLE = 0x03
  ARTIST = 0x04
  GENRE = 0x05
  KIND = 0x06
  FILE_TYPE = 0x06  # Alias for KIND
  COMMENTS = 0x08
  CATEGORY = 0x09
  LOCAL_PATH = 0x0B
  COMPOSER = 0x0C
  NATIVE_FILEPATH = 0x0D
  GROUPING = 0x0E
  SHORT_DESCRIPTION = 0x12
  FULL_DESCRIPTION = 0x16
  TV_SHOW_TITLE = 0x18
  EPISODE_ID = 0x19
  ALBUM_ARTIST = 0x1B
  TV_RATING = 0x1C
  XML_BLOCK = 0x1D
  SORT_TRACK_NAME = 0x1E
  SORT_ALBUM = 0x1F
  SORT_ARTIST = 0x20
  SORT_ALBUM_ARTIST = 0x21
  SORT_COMPOSER = 0x22
  SORT_TV_SHOW_TITLE = 0x22  # Alias for SORT_COMPOSER
  PODCAST_RSS_URL = 0x25
  EMI_UNKNOWN = 0x2B
  COPYRIGHT = 0x2E
  ALTERNATE_DESCRIPTION = 0x33
  UNKNOWN_34 = 0x34
  PODCAST_EPISODE_URL = 0x39
  PODCAST_FEED_URL = 0x3A
  PURCHASER_EMAIL = 0x3B
  PURCHASER_NAME = 0x3C
  WORK_NAME = 0x3F
  MOVEMENT_NAME = 0x40

  PLAYLIST_NAME = 0x64

  # TODO: fix those.
  # SMART_CRITERIA = 0x65
  # SMART_INFO = 0x66
  PODCAST_TITLE = 0xC8

  # MIAH specific entries
  ALBUM_MIAH = 0x12C
  ALBUM_ARTIST_MIAH = 0x12D
  ALBUM_ARTIST_MIAH_2 = 0x12E
  SERIES_TITLE_MIAH = 0x130
  FEED_URL_MIAH = 0x131
  ARTIST_MIAH = 0x190
  SORT_ARTIST_MIAH = 0x191

  # Library and System entries
  UUID_UNKNOWN_F8 = 0x1F8
  UUID_UNKNOWN_F9 = 0x1F9
  LIBRARY_OWNER = 0x1FA
  LIBRARY_NAME = 0x1FC

  # Extended Track info
  TRACK_TITLE_EXT = 0x2BE
  ARTIST_ALBUM_COMBINED = 0x2BF


class MhohNarrowType(IntEnum):
  """Narrow metadata types (mostly XML blocks) for mhoh structure."""

  PODCAST_EPISODE_URL = 0x13
  ART_XML_BLOCK = 0x36
  DOWNLOAD_XML_BLOCK = 0x38
  DISPLAY_ART_XML_BLOCK = 0x6D
  STORE_ART_URL_XML_BLOCK = 0x192
  LONG_XML_BLOCK = 0x202
  SMART_PLAYLIST_CRITERIA_XML_BLOCK = 0x2BC
  TV_DISPLAY_XML_BLOCK = 0x320


class MhohOtherType(IntEnum):
  RESOLUTION = 0x24
  BOOK = 0x42


class ListSize(IntEnum):
  """Display size for library items."""

  SMALL = 1
  MEDIUM = 2
  LARGE = 3


class StringType(IntEnum):
  """String types used in mhoh blocks."""

  URI_UTF8 = 0
  WIDE_UTF16 = 1
  ESCAPED_URI = 2
  NARROW_UTF8 = 3


@dataclass(slots=True)
class MhohDataContainer:
  """
  Metadata structure for data blocks.

  mhoh structure holds metadata for multiple types of blocks,
  for instance mith blocks (tracks). The mhoh structure is
  generic, and its inner data structure is defined by the
  mhoh's type.
  """

  type: MhohFlexType | MhohNarrowType | MhohOtherType | int
  value: bytes | str | None


@dataclass(slots=True)
class MithTrack:
  """
  Track.

  mith structure holds track information.
  """

  persistent_id: int
  id: int
  date_added: int
  date_modified: int
  date_last_played: int # uint32_t
  play_count: int
  rating: int
  unchecked: int

  mhohs: list[MhohDataContainer]


@dataclass(slots=True)
class MhghLibrarySettings:
  """
  Library global settings.

  mhgh holds settings for a library, such as the display size for
  items. It also has mhoh sub_blocks for variable length informations
  (library name for instance). In my test library, embedded mhohs have
  0x1F7, 0x1FC, 0x205 types.
  """

  list_size: ListSize
  mhohs: list[MhohDataContainer]


@dataclass(slots=True)
class MiphPlaylist:
  """
  Playlist.

  miph structure holds playlist content and attributes.
  """

  persistent_id: int  # Playlist persistent ID (uint64_t)
  id: int  # Playlist ID (uint32_t)
  distinguished_kind: int  # uint16_t
  mhohs: list[MhohDataContainer]  # Playlist attributes
  identifiers: list[int] = field(repr=False)  # Playlist identifiers (mtphs)



@dataclass(slots=True)
class Msdh:
  """Main structure containing block type and subblock data."""

  block_type: BlockType
  sub_block: (
    str
    | list[list[MhohDataContainer]]  # Artist (miih)
    | list[MithTrack]  # Track
    | list[MiphPlaylist]  # playlist
    | MhghLibrarySettings
    | None
  ) = None


@dataclass(slots=True)
class RawLibrary:

  version: str
  date: int
  tz_offset: int
  blocks: list[Msdh]

  @property
  def datetime(self):
    return utils.get_datetime(self.date, self.tz_offset)

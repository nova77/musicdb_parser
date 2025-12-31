"""
Functions that take a RawLibrary (low-level) and return easier-to-use
structures.
"""

import datetime
import dataclasses
import urllib.parse

from src import utils
from src.musicdb import parsing_types

##############################################################################
# Simple data structurs


@dataclasses.dataclass(slots=True)
class Track:
  persistent_id: int
  id: int
  starred: bool
  rating: int
  unchecked: int

  date_added: datetime.datetime | None = None
  date_modified: datetime.datetime | None = None
  date_last_played: datetime.datetime | None = None
  play_count: int | None = None

  song_time_ms: int | None = None
  bitrate: int | None = None
  normalization: int | None = None
  file_size: int | None = None

  metadata: dict[str, str] = dataclasses.field(default_factory=dict)

  @property
  def short_rating(self) -> int:
    """Rating from 0 to 5."""
    return int(self.rating/100 * 5)

@dataclasses.dataclass(slots=True)
class Playlist:
  name: str
  date_created: datetime.datetime | None = None
  date_modified: datetime.datetime | None = None
  is_smart: bool = False
  is_folder: bool = False
  persistent_track_ids: list[int] = dataclasses.field(
    default_factory=list, repr=False
  )


##############################################################################
# Functions


def get_tracks(
  raw_library: parsing_types.RawLibrary, ignore_xlm_block: bool = True
) -> list[Track]:
  for section in raw_library.sections:
    if section.section_type == parsing_types.SectionType.ITMA_TRACK_MASTER:
      break
  else:
    raise ValueError('Track section not found')

  assert isinstance(section.sub_section, list)
  assert len(section.sub_section) > 0
  assert isinstance(section.sub_section[0], parsing_types.ItmaTrack)

  tz_offset = raw_library.tz_offset
  tracks = []
  for itma_track in section.sub_section:
    if not isinstance(itma_track, parsing_types.ItmaTrack):
      raise ValueError('Invalid subsection type:', type(itma_track))
    tracks.append(_itma2track(itma_track, tz_offset, ignore_xlm_block))
  return tracks


def get_playlists(raw_library: parsing_types.RawLibrary) -> list[Playlist]:
  for section in raw_library.sections:
    if section.section_type == parsing_types.SectionType.LPMA_PLAYLIST_MASTER:
      break
  else:
    raise ValueError('Playlist section not found')

  assert isinstance(section.sub_section, list)
  assert len(section.sub_section) > 0

  tz_offset = raw_library.tz_offset
  playlists = []

  for lpma_playlist in section.sub_section:
    if not isinstance(lpma_playlist, parsing_types.LpmaPlaylist):
      raise ValueError('Invalid subsection type:', type(lpma_playlist))

    if playlist := _lpma2playlist(lpma_playlist, tz_offset):
      playlists.append(playlist)

  return playlists


def get_library_location(raw_library: parsing_types.RawLibrary,
                         include_file_prefix: bool = False) -> str:
  for section in raw_library.sections:
    if section.section_type == parsing_types.SectionType.PLMA_LIBRARY_MASTER:
      break
  else:
    raise ValueError('Library section not found')

  assert isinstance(section.sub_section, list)
  assert len(section.sub_section) > 0

  for boma_data in section.sub_section:
    if not isinstance(boma_data, parsing_types.BomaDataContainer):
      raise ValueError('Invalid subsection boma type:', type(boma_data))

    if boma_data.type == parsing_types.BomaWideCharType.MANAGED_MEDIA_FOLDER:
      assert isinstance(boma_data.value, str)
      path = urllib.parse.unquote(boma_data.value)
      if not include_file_prefix:
        path = path.removeprefix('file://localhost/')
      return path

  raise ValueError('Could not find any media folder boma entry.')


##############################################################################
# Helpers


def _itma2track(
  itma_track: parsing_types.ItmaTrack,
  tz_offset: int = 0,
  ignore_xlm_block: bool = True,
) -> Track:
  kwargs = {}
  for field in dataclasses.fields(itma_track):
    if field.name == 'bomas':
      continue  # handled in metadata
    v = getattr(itma_track, field.name)
    if field.name.startswith('date_'):
      v = utils.get_datetime(v, tz_offset)
    kwargs[field.name] = v

  metadata = {}
  for boma in itma_track.bomas:
    name = getattr(boma.type, 'name', None)
    if not name:
      continue
    name = name.lower()
    if ignore_xlm_block and name.startswith('xlm_block'):
      continue
    metadata[name] = boma.value
  return Track(**kwargs, metadata=metadata)


def _lpma2playlist(
  lpma_playlist: parsing_types.LpmaPlaylist, tz_offset: int = 0
) -> Playlist | None:
  for boma in lpma_playlist.bomas:
    if boma.type == parsing_types.BomaWideCharType.PLAYLIST_NAME:
      name = boma.value
      break
  else:
    # No name has been found
    return None

  if not isinstance(name, str):
    return None

  return Playlist(
    name=name,
    date_created=utils.get_datetime(lpma_playlist.date_created, tz_offset),
    date_modified=utils.get_datetime(lpma_playlist.date_modified, tz_offset),
    is_smart=lpma_playlist.is_smart,
    is_folder=lpma_playlist.is_folder,
    persistent_track_ids=lpma_playlist.persistent_track_ids,
  )

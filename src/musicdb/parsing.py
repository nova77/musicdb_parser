"""Parsing code for the Apple Music musicdb library.

Liberally inspired by https://home.vollink.com/gary/playlister/musicdb.html.
"""

import zlib

from src import utils
from src.musicdb import parsing_types


def parse_library(path: str, key: bytes) -> parsing_types.RawLibrary:
  """Parse the iTunes (musicdb) library file at the given path.

  Args:
      path (str): Path to the iTunes library file.
      key: The cryptographic key for the first 100k data.

  Returns:
      The parsed RawLibrary object.
  """
  with open(path, 'rb') as f:
    library_data = f.read()

  reader = utils.BufferReader(library_data)
  header, header_len, file_len = reader.read('<4sII')
  utils.check_signature(header, b'hfma')

  if len(library_data) != file_len:
    raise ValueError('iTunes parser: File length not matching.')

  data = reader.read_bytes(16, 32).replace(b'\x00', b'')
  version_str = data.decode('utf-8')

  max_crypt_size = reader.read_uint32(offset=84)
  tz_offset = reader.read_int32(offset=88)
  secs_since_1904 = reader.read_uint32(offset=100)

  crypt_size = file_len - header_len
  if crypt_size > max_crypt_size:
    crypt_size = max_crypt_size

  # Skip header
  reader.advance(header_len)

  encrypted_buffer = reader.read_bytes(length=crypt_size)
  buffer = utils.itlp_decrypt(encrypted_buffer, key=key)
  buffer += reader.read_bytes(offset=crypt_size)

  decompressed_buffer = zlib.decompress(buffer)
  reader = utils.BufferReader(decompressed_buffer)

  sections = []
  while reader.pos < len(decompressed_buffer):
    sections.append(_parse_hsma(reader))

  return parsing_types.RawLibrary(
    version=version_str,
    date=secs_since_1904,
    tz_offset=tz_offset,
    sections=sections,
  )


##############################################################################
## Main parsing section.


def _parse_hsma(reader: utils.BufferReader) -> parsing_types.Hsma:
  header, next_section_offset, section_len, section_type = reader.read(
    '<4sIII'
  )
  utils.check_signature(
    header, parsing_types.SectionSignature.HSMA_MAJOR_SECTION.value
  )

  expected_end_pos = reader.pos + section_len

  reader.advance(next_section_offset)
  sub_section = None

  match section_type:
    case parsing_types.SectionType.ITMA_TRACK_MASTER:
      sub_section = _parse_ltma_track_master(reader)
    case parsing_types.SectionType.LPMA_PLAYLIST_MASTER:
      sub_section = _parse_lpma_playlists(reader)
    case parsing_types.SectionType.HFMA_INNER_MASTER:
      header = reader.read_bytes(length=4)
      utils.check_signature(
        header, parsing_types.SectionSignature.HFMA_OUTER_ENVELOPE.value
      )
      # skip this as we already parsed it at the beginning
      reader.advance(section_len - next_section_offset)
    case parsing_types.SectionType.LAMA_ALBUM_DATA:
      sub_section = _parse_lama_album_artist(
        parsing_types.SectionSignature.LAMA_ALBUM_MASTER.value,
        parsing_types.SectionSignature.IAMA_ALBUM_ITEM.value,
        reader,
      )
    case parsing_types.SectionType.LAMA_ARTIST_DATA:
      sub_section = _parse_lama_album_artist(
        parsing_types.SectionSignature.LAMA_ARTIST_MASTER.value,
        parsing_types.SectionSignature.IAMA_ARTIST_ITEM.value,
        reader,
      )
    case parsing_types.SectionType.PLMA_LIBRARY_MASTER:
      sub_section = _parse_plma_library(reader)
    case parsing_types.SectionType.LPMA_UNK:
      # skip this as we don't really know what's in here
      reader.advance(section_len - next_section_offset)

  if reader.pos != expected_end_pos:
    raise ValueError(
      'Invalid hsma block parsing: did not reach expected end position. '
      f'Current position: {reader.pos}, expected: {expected_end_pos}.'
    )

  return parsing_types.Hsma(
    section_type=parsing_types.SectionType(section_type), sub_section=sub_section
  )


##############################################################################
# General


def _parse_boma(
  reader: utils.BufferReader, **kwargs
) -> parsing_types.BomaDataContainer | None:
  header, _, section_len, boma_subtype = reader.read('<4sIII')
  utils.check_signature(
    header, parsing_types.SectionSignature.BOMA_CONTAINER.value
  )

  container = None
  if boma_subtype in parsing_types.BomaWideCharType:
    string_len = reader.read_uint32(24)
    data = reader.read_bytes(36, string_len).decode('utf-16', 'replace')
    container = parsing_types.BomaDataContainer(
      type=parsing_types.BomaWideCharType(boma_subtype), value=data
    )
  elif boma_subtype in parsing_types.BomaUtf8Short:
    data = reader.read_bytes(20, section_len - 20).decode('utf-8', 'replace')
    container = parsing_types.BomaDataContainer(
      type=parsing_types.BomaUtf8Short(boma_subtype), value=data
    )
  elif boma_subtype in parsing_types.BomaUtf8Long:
    string_len = reader.read_uint32(24)
    data = reader.read_bytes(36, string_len).decode('utf-8', 'replace')
    container = parsing_types.BomaDataContainer(
      type=parsing_types.BomaUtf8Long(boma_subtype), value=data
    )
  elif boma_subtype in parsing_types.BomaBookType:
    signature = reader.read_bytes(offset=20, length=4)
    utils.check_signature(signature, parsing_types.SectionSignature.BOOK.value)
    # TODO: properly handle reading books
    container = parsing_types.BomaDataContainer(
      type=parsing_types.BomaBookType(boma_subtype), value=None
    )
  elif boma_subtype == parsing_types.BomaOtherType.IPFA_PLAYLIST:
    _parse_boma_ipfa_playlist(reader, **kwargs)
  elif boma_subtype == parsing_types.BomaOtherType.VIDEO:
    vertical, horizontal = reader.read('<II', offset=20)
    fps = reader.read_uint32(offset=68)
    data = f'{vertical}x{horizontal} ({fps} fps)'
    container = parsing_types.BomaDataContainer(
      type=parsing_types.BomaOtherType.VIDEO, value=data
    )
  elif boma_subtype in parsing_types.BomaTrackNumericsType:
    _parse_boma_track_numerics(
      reader, parsing_types.BomaTrackNumericsType(boma_subtype), **kwargs
    )
  else:
    # TODO: add more boma subtypes as we figure what they are.
    pass

  reader.advance(section_len)
  return container


def _parse_iama_item(
  expected_header: bytes,
  reader: utils.BufferReader,
) -> list[parsing_types.BomaDataContainer]:
  header, section_len, sections_len, num_boma = reader.read('<4sIII')
  utils.check_signature(header, expected_header)
  expected_end_pos = reader.pos + sections_len
  reader.advance(section_len)

  bomas = []
  for _ in range(num_boma):
    if boma := _parse_boma(reader):
      bomas.append(boma)

  if reader.pos != expected_end_pos:
    raise ValueError(
      'Invalid iama block parsing: did not reach expected end position. '
      f'Current position: {reader.pos}, expected: {expected_end_pos}.'
    )
  return bomas


##############################################################################
# Track


def _parse_ltma_track_master(
  reader: utils.BufferReader,
) -> list[parsing_types.ItmaTrack]:
  header, section_len, num_itma = reader.read('<4sII')
  utils.check_signature(
    header, parsing_types.SectionSignature.LTMA_TRACK_MASTER.value
  )
  reader.advance(section_len)

  itmas = []
  for _ in range(num_itma):
    if itma := _parse_itma_track(reader):
      itmas.append(itma)
  return itmas


def _parse_itma_track(reader: utils.BufferReader) -> parsing_types.ItmaTrack:
  header, section_len, _, num_boma, track_persistent_id, track_id = (
    reader.read('<4sIIIQI')
  )
  utils.check_signature(
    header, parsing_types.SectionSignature.ITMA_TRACK_ITEM.value
  )

  unchecked = reader.read_uint16(42)
  starred_val = reader.read_uint16(62)
  rating = reader.read_uint8(65)

  reader.advance(section_len)

  itma_track = parsing_types.ItmaTrack(
    persistent_id=track_persistent_id,
    id=track_id,
    starred=(starred_val == 2),
    rating=rating,
    unchecked=unchecked,
  )

  for _ in range(num_boma):
    if boma := _parse_boma(reader, itma_track=itma_track):
      itma_track.bomas.append(boma)

  return itma_track


def _parse_boma_track_numerics(
  reader: utils.BufferReader,
  boma_subtype: parsing_types.BomaTrackNumericsType,
  itma_track: parsing_types.ItmaTrack,
) -> None:
  """Parse track data which is found in the boma section."""

  def _set_if_unset(field_name, v):
    if getattr(itma_track, field_name) is None:
      setattr(itma_track, field_name, v)

  # There's definitely a lot of info here I am missing.
  match boma_subtype:
    case parsing_types.BomaTrackNumericsType.TRACK_NUMERICS_1:
      _set_if_unset('bitrate', reader.read_uint32(108))
      _set_if_unset('date_added', reader.read_uint32(112))
      _set_if_unset('date_modified', reader.read_uint32(148))
      _set_if_unset('normalization', reader.read_uint32(152))
      _set_if_unset('song_time_ms', reader.read_uint32(176))
      _set_if_unset('file_size', reader.read_uint32(316))

    case parsing_types.BomaTrackNumericsType.TRACK_NUMERICS_2:
      play_count = reader.read_uint32(32)
      _set_if_unset('play_count', play_count)
      if play_count > 0:
        _set_if_unset('date_last_played', reader.read_uint32(28))



##############################################################################
# Playlist


def _parse_lpma_playlists(
  reader: utils.BufferReader,
) -> list[parsing_types.LpmaPlaylist]:
  header, section_len, num_lpma = reader.read('<4sII')
  utils.check_signature(
    header, parsing_types.SectionSignature.LPMA_PLAYLIST_MASTER.value
  )
  reader.advance(section_len)

  lpmas = []
  for _ in range(num_lpma):
    if lpma := _parse_lpma_item(reader):
      lpmas.append(lpma)

  return lpmas


def _parse_lpma_item(reader: utils.BufferReader) -> parsing_types.LpmaPlaylist:
  header, section_len, sections_len, num_boma, num_tracks = reader.read(
    '<4sIIII'
  )
  utils.check_signature(
    header, parsing_types.SectionSignature.LMPA_PLAYLIST_ITEM.value
  )

  lpma_playlist = parsing_types.LpmaPlaylist(
    persistent_id=reader.read_uint64(39),
    date_created=reader.read_uint32(22),
    date_modified=reader.read_uint32(138),
    num_tracks=num_tracks,
  )
  reader.advance(section_len)

  for _ in range(num_boma):
    if boma := _parse_boma(reader, lpma_playlist=lpma_playlist):
      lpma_playlist.bomas.append(boma)
  return lpma_playlist


def _parse_boma_ipfa_playlist(
  reader: utils.BufferReader,
  lpma_playlist: parsing_types.LpmaPlaylist,
) -> None:
  header, section_len = reader.read('<4sI', 20)
  utils.check_signature(header, parsing_types.SectionSignature.IPFA_BOMA.value)
  lpma_playlist.persistent_track_ids.append(reader.read_uint64(40))


##############################################################################
# Album/Collection & Artist/Band


def _parse_lama_album_artist(
  expected_header: bytes,
  expected_iama_header: bytes,
  reader: utils.BufferReader,
) -> list[list[parsing_types.BomaDataContainer]]:
  header, section_len, num_iama = reader.read('<4sII')
  utils.check_signature(header, expected_header)
  reader.advance(section_len)
  iamas = []
  for _ in range(num_iama):
    if iama := _parse_iama_item(expected_iama_header, reader):
      iamas.append(iama)

  return iamas


##############################################################################
# Library


def _parse_plma_library(
  reader: utils.BufferReader,
) -> list[parsing_types.BomaDataContainer] | None:
  header, section_len, num_boma = reader.read('<4sII')
  utils.check_signature(
    header, parsing_types.SectionSignature.PLMA_LIBRARY_MASTER.value
  )
  reader.advance(section_len)

  bomas = []
  for _ in range(num_boma):
    if boma := _parse_boma(reader):
      bomas.append(boma)

  return bomas or None

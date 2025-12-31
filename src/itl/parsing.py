"""Parsing code for the iTunes ITL library.

Liberally inspired by https://home.vollink.com/gary/playlister/ituneslib.html.
"""

import zlib

from src import utils
from src.itl import parsing_types


def parse_library(
  path: str, key: bytes, include_unk: bool = False
) -> parsing_types.RawLibrary:
  """Parse the iTunes (itl) library file at the given path.

  Args:
      path (str): Path to the iTunes library file.
      key: The cryptographic key for the first 100k data.
      include_unk: Whether to include the unknown blocks.

  Returns:
      The parsed RawLibrary object.
  """
  with open(path, 'rb') as f:
    library_data = f.read()

  # The iTunes itl library file starts with a header of 17 bytes
  # header: 4 bytes
  # header_len: 4 bytes
  # file_len: 4 bytes
  # unknown: 4 bytes
  # version_str_len: 1 byte
  # version_str: variable length (version_str_len bytes)

  reader = utils.BufferReader(library_data)
  header, header_len, file_len, _, version_str_len = reader.read('>4sIIIb')

  if header != b'hdfm':
    raise ValueError('Invalid iTunes library file format.')

  if len(library_data) != file_len:
    raise ValueError('iTunes parser: File length not matching.')

  data = reader.read_bytes(offset=17, length=version_str_len)
  version_str = data.decode('utf-8')

  num_msdh = reader.read_uint32(offset=48, little_endian=False)
  max_crypt_size = reader.read_uint32(offset=92, little_endian=False)

  tz_offset = reader.read_int32(offset=100, little_endian=False)
  secs_since_1904 = reader.read_uint32(offset=112, little_endian=False)

  crypt_size = file_len - header_len
  if crypt_size > max_crypt_size:
    crypt_size = max_crypt_size

  # Skip header
  reader.advance(header_len)

  # Only crypt_size is encrypted, the rest is not.
  encrypted_buffer = reader.read_bytes(length=crypt_size)
  buffer = utils.itlp_decrypt(encrypted_buffer, key=key)
  buffer += reader.read_bytes(offset=crypt_size)

  decompressed_buffer = zlib.decompress(buffer)
  reader = utils.BufferReader(decompressed_buffer)

  unk_block_types = parsing_types.BlockType.unk_types()
  blocks = []
  for _ in range(num_msdh):
    msdh_entry = _itlp_parse_msdh(reader)
    if msdh_entry is None:
      continue
    if msdh_entry.block_type in unk_block_types and not include_unk:
      continue
    blocks.append(msdh_entry)

  if reader.pos != len(decompressed_buffer):
    print('WARNING: not all data has been parsed. Something might be wrong.')

  return parsing_types.RawLibrary(
    version=version_str,
    date=secs_since_1904,
    tz_offset=tz_offset,
    blocks=blocks,
  )


##############################################################################
## Main parsing block.


def _itlp_parse_msdh(reader: utils.BufferReader) -> parsing_types.Msdh | None:
  """Parse msdh (section boundary) block."""
  # Reading header
  header, header_len, data_len, block_type = reader.read('<4sIII')
  utils.check_signature(header, b'msdh')

  # Skipping header section
  reader.advance(header_len)

  # Parse msdh's sub_block
  match block_type:
    case parsing_types.BlockType.MLIH_ARTIST:
      sub_block = _itlp_parse_artist(reader)
    case (
      parsing_types.BlockType.MLTH_TRACK | parsing_types.BlockType.MLTH_TRACK_MASTER
    ):
      sub_block = _itlp_parse_track(reader)
    case parsing_types.BlockType.MFDH_OUTER_ENVELOPE:
      sub_block = _parse_outer_envelope(reader)
    case parsing_types.BlockType.MLAH_ALBUM_COLLECTION:
      sub_block = _parse_album_collection(reader)
    case parsing_types.BlockType.MHGH_LIBRARY_INFO:
      sub_block = _parse_library_info(reader)
    case (
      parsing_types.BlockType.MLPH_TRACK | parsing_types.BlockType.MLPH_PLAYLIST_MASTER
    ):
      sub_block = _itlp_parse_playlist(reader)
    case parsing_types.BlockType.LIBRARY_LOCATION:
      reader.advance(-header_len)
      sub_block = _parse_library_location(reader)
    case (
      parsing_types.BlockType.MLRH_UNK
      | parsing_types.BlockType.MLSH_UNK
      | parsing_types.BlockType.STSH_UNK
      | parsing_types.BlockType.MLQH_UNK
    ):
      sub_block = None
      reader.advance(data_len - header_len)
    case _:
      raise ValueError(f'Unknown msdh block type: {block_type}')

  return parsing_types.Msdh(
    block_type=parsing_types.BlockType(block_type), sub_block=sub_block
  )


##############################################################################
# General


def _parse_outer_envelope(reader: utils.BufferReader) -> str | None:
  """Parse mfdh block (application version)."""
  header, header_len = reader.read('<4sI')
  utils.check_signature(header, b'mfdh')

  version_str_len = reader.read_uint8(16)
  application_version = reader.read_bytes(17, version_str_len)
  reader.advance(header_len)
  return application_version.decode('utf-8', errors='replace')


def _itlp_parse_mhoh(
  reader: utils.BufferReader,
) -> parsing_types.MhohDataContainer | None:
  """Parse mhoh block (metadata)"""

  header, _, section_len, mhoh_subtype = reader.read('<4sIII')
  utils.check_signature(header, b'mhoh')

  container = None
  if mhoh_subtype in parsing_types.MhohFlexType:
    string_type, string_len = reader.read('<II', offset=24)
    data = reader.read_bytes(40, string_len)
    string_type = parsing_types.StringType(string_type)

    match string_type:
      case parsing_types.StringType.URI_UTF8:
        data = data.decode('utf-8', errors='replace')
      case parsing_types.StringType.WIDE_UTF16:
        data = data.decode('utf-16', errors='replace')
      case parsing_types.StringType.ESCAPED_URI:
        data = data.decode('utf-8', errors='replace')
      case parsing_types.StringType.NARROW_UTF8:
        data = data.decode('utf-8', errors='replace')

    container = parsing_types.MhohDataContainer(
      type=parsing_types.MhohFlexType(mhoh_subtype),
      value=data,
    )
  elif mhoh_subtype in parsing_types.MhohNarrowType:
    # Note: 24 is always fixed at reader.read_uint32(4)
    data = reader.read_bytes(offset=24, length=section_len - 24)
    container = parsing_types.MhohDataContainer(
      type=parsing_types.MhohNarrowType(mhoh_subtype),
      value=data.decode('utf-8', errors='replace'),
    )
  elif mhoh_subtype == parsing_types.MhohOtherType.BOOK:
    mhoh_subtype = parsing_types.MhohOtherType.BOOK
    print('TODO: Implement BOOK mhoh type parsing')
  elif mhoh_subtype == parsing_types.MhohOtherType.RESOLUTION:
    mhoh_subtype = parsing_types.MhohOtherType.RESOLUTION
    vertical, horizontal = reader.read('<II', offset=24)
    data = f'{vertical}x{horizontal}'
    container = parsing_types.MhohDataContainer(
      type=parsing_types.MhohOtherType.RESOLUTION,
      value=data,
    )

  reader.advance(section_len)
  return container


##############################################################################
# Library


def _parse_library_info(
  reader: utils.BufferReader,
) -> parsing_types.MhghLibrarySettings | None:
  """Parse mhgh block (library global settings)."""

  # Reading header informations
  header, header_len, num_mhoh = reader.read('<4sII')
  utils.check_signature(header, b'mhgh')

  list_size = reader.read_uint8(55)
  reader.advance(header_len)

  # Parsing mhoh blocks
  mhohs = []
  for _ in range(num_mhoh):
    if mhoh_entry := _itlp_parse_mhoh(reader):
      mhohs.append(mhoh_entry)

  return parsing_types.MhghLibrarySettings(
    list_size=parsing_types.ListSize(list_size), mhohs=mhohs
  )


def _parse_library_location(reader: utils.BufferReader) -> str | None:
  """Parse file block (absolute path of the library)."""
  header, header_len, total_len = reader.read('<4sII')
  utils.check_signature(header, b'msdh')

  # Parsing header informations
  string_len = total_len - header_len
  reader.advance(header_len)

  # Parsing block
  data = reader.read_bytes(length=string_len)
  library_location = data.decode('utf-8', errors='replace')
  reader.advance(string_len)
  return library_location


##############################################################################
# Track


def _itlp_parse_track(
  reader: utils.BufferReader,
) -> list[parsing_types.MithTrack] | None:
  """Parse mlth block (master track list)."""

  header, header_len, num_mith = reader.read('<4sII')
  utils.check_signature(header, b'mlth')

  reader.advance(header_len)
  # Parsing mith blocks
  miths = []
  for _ in range(num_mith):
    miths.append(_itlp_parse_mith(reader))
  return miths


def _itlp_parse_mith(
  reader: utils.BufferReader,
) -> parsing_types.MithTrack | None:
  """Parse mith block (track item)."""

  header, header_len, data_len, num_mhohs, track_id = reader.read('<4sIIII')
  utils.check_signature(header, b'mith')
  expected_end_pos = reader.pos + data_len

  # Reading mith metadata
  date_modified = reader.read_uint32(32)
  # Note: I'm not really interested into those, since they're available from
  # the id3 itself.
  # filesize = reader.read_uint32(36)
  # year = reader.read_uint32(52)
  # bitrate = reader.read_uint32(56)

  play_count = reader.read_uint32(76)
  date_last_played = reader.read_uint32(100)
  rating = reader.read_uint8(108)
  unchecked = reader.read_uint8(110)
  date_added = reader.read_uint32(120)
  persistent_id = reader.read_uint64(128)

  # Skipping header
  reader.advance(header_len)

  # Parsing embedded mhoh in mith
  mhohs = []
  for _ in range(num_mhohs):
    if mhoh_entry := _itlp_parse_mhoh(reader):
      mhohs.append(mhoh_entry)

  if reader.pos != expected_end_pos:
    raise ValueError(
      'Invalid miph block parsing: did not reach expected end position. '
      f'Current position: {reader.pos}, expected: {expected_end_pos}.'
    )

  return parsing_types.MithTrack(
    persistent_id=persistent_id,
    id=track_id,
    date_added=date_added,
    date_modified=date_modified,
    date_last_played=date_last_played,
    play_count=play_count,
    rating=rating,
    unchecked=unchecked,
    mhohs=mhohs,
  )


##############################################################################
# Playlist


def _itlp_parse_playlist(
  reader: utils.BufferReader,
) -> list[parsing_types.MiphPlaylist] | None:
  """Parse mlph block (playlist list)."""
  header, header_len, num_miph = reader.read('<4sII')
  utils.check_signature(header, b'mlph')
  reader.advance(header_len)

  # Parsing miph blocks
  miphs = []
  for _ in range(num_miph):
    if miph_entry := _itlp_parse_miph(reader):
      miphs.append(miph_entry)
  return miphs


def _itlp_parse_miph(
  reader: utils.BufferReader,
) -> parsing_types.MiphPlaylist | None:
  """Parse miph block (playlist)"""

  header, header_len, data_len, num_mhoh, num_mtph = reader.read('<4sIIII')
  utils.check_signature(header, b'miph')
  expected_end_pos = reader.pos + data_len

  persistent_id = reader.read_uint64(440)
  distinguished_kind = reader.read_uint16(570)
  playlist_id = reader.read_uint32(3392)
  reader.advance(header_len)

  # Parsing mhoh blocks
  mhohs = []
  for _ in range(num_mhoh):
    if mhoh_entry := _itlp_parse_mhoh(reader):
      mhohs.append(mhoh_entry)

  # Parsing mtph blocks
  mtphs = []
  while len(mtphs) < num_mtph:
    header = reader.read_bytes(length=4)

    if header == b'mtph':
      mtphs.append(_itlp_parse_mtph(reader))
    elif header == b'mhoh':
      # This should always be mtph, but sometimes we also find mhoh in here.
      # We just skip it.
      section_len = reader.read_uint32(offset=8)
      reader.advance(section_len)
    else:
      print('Unknown block in mtph list:', header)
      mtph_header_len = reader.read_uint32(offset=4)
      reader.advance(mtph_header_len)

  if reader.pos != expected_end_pos:
    raise ValueError(
      'Invalid miph block parsing: did not reach expected end position. '
      f'Current position: {reader.pos}, expected: {expected_end_pos}.'
    )

  mtphs = [v for v in mtphs if v is not None]
  if not mtphs:
    return None

  return parsing_types.MiphPlaylist(
    persistent_id=persistent_id,
    id=playlist_id,
    distinguished_kind=distinguished_kind,
    mhohs=mhohs,
    identifiers=mtphs,
  )


def _itlp_parse_mtph(reader: utils.BufferReader) -> int:
  """Parse mtph block (playlist item)"""
  header, header_len = reader.read('<4sI')
  utils.check_signature(header, b'mtph')

  identifier = reader.read_uint32(24)
  reader.advance(header_len)
  return identifier


##############################################################################
# Album/Collection


def _parse_album_collection(
  reader: utils.BufferReader,
) -> list[list[parsing_types.MhohDataContainer]] | None:
  """Parse mlah block (album/collection)."""

  header, header_len, num_miah = reader.read('<4sII')
  utils.check_signature(header, b'mlah')
  reader.advance(header_len)

  miahs = []
  for _ in range(num_miah):
    if miah_entries := _itlp_parse_miah(reader):
      miahs.append(miah_entries)
  return miahs


def _itlp_parse_miah(
  reader: utils.BufferReader,
) -> list[parsing_types.MhohDataContainer] | None:
  """Parse miah block (album item)."""

  # Read miah header
  header_len = reader.read_uint32(4)
  num_mhoh = reader.read_uint32(12)
  reader.advance(header_len)

  # Parsing mhoh blocks
  mhohs = []
  for _ in range(num_mhoh):
    if mhoh_entry := _itlp_parse_mhoh(reader):
      mhohs.append(mhoh_entry)

  return mhohs


##############################################################################
# Artist


def _itlp_parse_artist(
  reader: utils.BufferReader,
) -> list[list[parsing_types.MhohDataContainer]] | None:
  """Parse mlih block (artist master)."""

  header, header_len, num_miih = reader.read('<4sII')
  utils.check_signature(header, b'mlih')
  reader.advance(header_len)

  # Parsing miih blocks
  miihs = []
  for _ in range(num_miih):
    miihs.append(_itlp_parse_miih(reader))
  return miihs


def _itlp_parse_miih(
  reader: utils.BufferReader,
) -> list[parsing_types.MhohDataContainer] | None:
  """Parse miih block (artist item)."""

  header, header_len, _, num_mhoh = reader.read('<4sIII')
  utils.check_signature(header, b'miih')
  reader.advance(header_len)

  # Parsing mhoh blocks
  mhohs = []
  for _ in range(num_mhoh):
    if mhoh_entry := _itlp_parse_mhoh(reader):
      mhohs.append(mhoh_entry)
  return mhohs

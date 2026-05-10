"""
Updates a navidrome database with play count, (last) play date, rating, and
loves. Optionally also exports (non-smart) playlists.

Note: it relies on the file path to match each track. If you have a completely
different file structure between the two it won't work.

Example run:

  uv run python -m navidrome.update_annotations \
    --musicdb_path /path/to/my/Library.musicdb \
    --navidrome_path /path/to/my/navidrome.db \
    --user_name my_username \
    --key <DECRYPT_KEY> \
    --export_playlists \
    --override
"""

import contextlib
import datetime
import os
import secrets
import sqlite3
import urllib.parse

from absl import app
from absl import flags

from src.musicdb import parsing as mdb_parsing
from src.musicdb import library
from src.musicdb import parsing_types

_MUSICDB_PATH = flags.DEFINE_string(
  'musicdb_path', None, 'The apple music library (Library.musicdb).',
  required=True,
)
_NAVIDROME_PATH = flags.DEFINE_string(
  'navidrome_path', None, 'The navidrome db (navidrome.db).', required=True,
)
_KEY = flags.DEFINE_string(
  'key', None, 'The cryptographic key used by itunes database.', required=True,
)
_USER_NAME = flags.DEFINE_string(
  'user_name', None, 'The navidrome user name.', required=True,
)
_OVERRIDE = flags.DEFINE_bool(
  'override', False,
  'If True, overwrite existing annotation rows (rating, play_count, '
  'play_date, starred) and replace the contents of existing playlists with '
  'the same name. If False, existing rows / playlists are left untouched.',
)
_EXPORT_PLAYLISTS = flags.DEFINE_bool(
  'export_playlists', False,
  'If True, also export non-smart, non-folder playlists to navidrome.',
)
_APPLE_MUSIC_MEDIA_SUBDIR = flags.DEFINE_string(
  'apple_music_media_subdir', 'Music',
  'Subdirectory inside the Apple Music library that holds the media files.',
)

# Navidrome uses NanoID with the default alphabet, length 22.
_NANOID_ALPHABET = (
  'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-'
)
_NANOID_LEN = 22


def _new_id() -> str:
  return ''.join(secrets.choice(_NANOID_ALPHABET) for _ in range(_NANOID_LEN))


def _format_date(date: datetime.datetime | None) -> str | None:
  if date is None:
    return None
  return f'{date.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]}+00:00'


def get_navidrome_media_paths(db_path: str) -> dict[str, str]:
  query = 'SELECT path, id FROM media_file'
  with contextlib.closing(sqlite3.connect(db_path)) as conn:
    with conn:
      cursor = conn.cursor()
      cursor.execute(query)
      # Note: using a lowercase key increase matching but carries a (low) risk
      # of collisions.
      return {k.lower(): v for k, v in cursor.fetchall()}


def get_navidrome_user_id(db_path: str, user_name: str) -> str:
  query = 'SELECT id FROM user WHERE user_name=?'
  with contextlib.closing(sqlite3.connect(db_path)) as conn:
    with conn:
      cursor = conn.cursor()
      cursor.execute(query, (user_name,))
      entries = cursor.fetchall()
  if not entries:
    raise ValueError(f'Could not find the user "{user_name}"')
  if len(entries) > 1:
    raise ValueError(f'Found more than one user with "{user_name}"')
  return entries[0][0]


def _track_to_media_file_id(
  track: library.Track,
  library_url: str,
  navidrome_path_to_id: dict[str, str],
) -> str | None:
  file_url = track.metadata.get('file_url')
  if not file_url:
    return None
  file_url = urllib.parse.unquote(file_url)
  relative_path = os.path.relpath(file_url, start=library_url)
  return navidrome_path_to_id.get(relative_path.lower())


def get_updates(
  user_id: str,
  raw_library: parsing_types.RawLibrary,
  navidrome_path_to_id: dict[str, str],
  apple_music_media_subdir: str = 'Music',
) -> tuple[
  list[dict[str, str | int]], list[str], dict[int, str]
]:
  """Returns (annotation updates, missing file urls, persistent_id->mf_id)."""
  tracks = library.get_tracks(raw_library)
  common_fields = {
    'user_id': user_id,
    'item_type': 'media_file',
  }

  library_url = os.path.join(
    library.get_library_location(raw_library, include_file_prefix=True),
    apple_music_media_subdir,
  )

  missing = []
  updates = []
  persistent_to_mf_id: dict[int, str] = {}
  for track in tracks:
    file_url = track.metadata.get('file_url')
    if not file_url:
      missing.append('No file url')
      continue

    item_id = _track_to_media_file_id(
      track, library_url, navidrome_path_to_id
    )
    if item_id is None:
      missing.append(urllib.parse.unquote(file_url))
      continue

    persistent_to_mf_id[track.persistent_id] = item_id

    modified = _format_date(track.date_modified or datetime.datetime.now())

    fields = {
      **common_fields,
      'item_id': item_id,
      'play_count': track.play_count,
      'play_date': _format_date(track.date_last_played),
      'rating': track.short_rating,
      'starred': track.starred,
    }
    if track.short_rating > 0:
      fields['rated_at'] = modified
    else:
      fields['rated_at'] = None

    if track.starred:
      fields['starred_at'] = modified
    else:
      fields['starred_at'] = None

    updates.append(fields)

  return updates, missing, persistent_to_mf_id


def add_annotations(
  db_path: str,
  entries: list[dict[str, str | int]],
  override: bool,
) -> None:
  if not entries:
    return
  keys = ', '.join(entries[0].keys())
  values = ', '.join(f':{k}' for k in entries[0].keys())
  conflict_action = 'REPLACE' if override else 'IGNORE'
  sql = f'INSERT OR {conflict_action} INTO annotation ({keys})\nVALUES ({values})'

  try:
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
      with conn:
        cursor = conn.cursor()
        cursor.executemany(sql, entries)
        print(f'Annotation rows processed: {cursor.rowcount}')
  except sqlite3.Error as e:
    print(f'An error occurred during annotation insertion: {e}')


def export_playlists(
  db_path: str,
  user_id: str,
  raw_library: parsing_types.RawLibrary,
  persistent_to_mf_id: dict[int, str],
  override: bool,
) -> None:
  """Exports non-smart, non-folder playlists into navidrome."""
  playlists = [
    p for p in library.get_playlists(raw_library)
    if not p.is_smart and not p.is_folder
  ]

  now = _format_date(datetime.datetime.now(datetime.timezone.utc))

  inserted = 0
  replaced = 0
  skipped = 0
  with contextlib.closing(sqlite3.connect(db_path)) as conn:
    with conn:
      cursor = conn.cursor()

      cursor.execute(
        'SELECT id, name FROM playlist WHERE owner_id=?', (user_id,)
      )
      existing = {name: pid for pid, name in cursor.fetchall()}

      for pl in playlists:
        media_file_ids = [
          persistent_to_mf_id[pid] for pid in pl.persistent_track_ids
          if pid in persistent_to_mf_id
        ]

        existing_id = existing.get(pl.name)
        if existing_id is not None and not override:
          skipped += 1
          continue

        created_at = _format_date(pl.date_created) or now
        updated_at = _format_date(pl.date_modified) or now

        if existing_id is not None:
          playlist_id = existing_id
          cursor.execute(
            'DELETE FROM playlist_tracks WHERE playlist_id=?', (playlist_id,)
          )
          cursor.execute(
            'UPDATE playlist SET updated_at=?, song_count=0, duration=0, '
            'size=0 WHERE id=?',
            (updated_at, playlist_id),
          )
          replaced += 1
        else:
          playlist_id = _new_id()
          cursor.execute(
            'INSERT INTO playlist (id, name, comment, duration, song_count, '
            'public, created_at, updated_at, path, sync, size, owner_id) '
            'VALUES (?, ?, ?, 0, 0, 0, ?, ?, ?, 0, 0, ?)',
            (playlist_id, pl.name, '', created_at, updated_at, '', user_id),
          )
          inserted += 1

        if media_file_ids:
          cursor.executemany(
            'INSERT INTO playlist_tracks (id, playlist_id, media_file_id) '
            'VALUES (?, ?, ?)',
            [
              (i + 1, playlist_id, mf_id)
              for i, mf_id in enumerate(media_file_ids)
            ],
          )
          # Recompute song_count, duration, size from the actual tracks.
          placeholders = ','.join('?' * len(media_file_ids))
          cursor.execute(
            f'SELECT COUNT(*), COALESCE(SUM(duration), 0), '
            f'COALESCE(SUM(size), 0) FROM media_file '
            f'WHERE id IN ({placeholders})',
            media_file_ids,
          )
          song_count, duration, size = cursor.fetchone()
          cursor.execute(
            'UPDATE playlist SET song_count=?, duration=?, size=? WHERE id=?',
            (song_count, duration, size, playlist_id),
          )

  print(
    f'Playlists: inserted={inserted}, replaced={replaced}, skipped={skipped} '
    f'(total non-smart={len(playlists)})'
  )


def main(argv):
  del argv  # unused

  print(
    f'Loading the apple music library from "{_MUSICDB_PATH.value}"..',
    flush=True,
  )
  raw_library = mdb_parsing.parse_library(
    _MUSICDB_PATH.value, key=_KEY.value.encode()
  )

  print(
    f'Loading the navidrome media paths from {_NAVIDROME_PATH.value}...',
    flush=True,
  )
  navidrome_path_to_id = get_navidrome_media_paths(_NAVIDROME_PATH.value)
  user_id = get_navidrome_user_id(
    _NAVIDROME_PATH.value, user_name=_USER_NAME.value
  )

  print('Get the updates...', flush=True)
  updates, missing, persistent_to_mf_id = get_updates(
    user_id=user_id,
    raw_library=raw_library,
    navidrome_path_to_id=navidrome_path_to_id,
    apple_music_media_subdir=_APPLE_MUSIC_MEDIA_SUBDIR.value,
  )
  if len(missing) > 1:
    print(f'Warning: Could not match {len(missing)} entries: {missing}')

  print(
    f'Add annotations (override={_OVERRIDE.value})..', flush=True
  )
  add_annotations(_NAVIDROME_PATH.value, updates, override=_OVERRIDE.value)

  if _EXPORT_PLAYLISTS.value:
    print(
      f'Export playlists (override={_OVERRIDE.value})..', flush=True
    )
    export_playlists(
      db_path=_NAVIDROME_PATH.value,
      user_id=user_id,
      raw_library=raw_library,
      persistent_to_mf_id=persistent_to_mf_id,
      override=_OVERRIDE.value,
    )

  print('All done!')


if __name__ == '__main__':
  app.run(main)

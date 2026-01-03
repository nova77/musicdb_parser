"""
Updates a navidrome database with play count, (last) play date, rating, and
loves.

Note: it relies on the file path to match each track. If you have a completely
different file structure between the two it won't work.

Example run:

  uv run python -m navidrome.update_annotations \
    --musicdb_path /path/to/my/Library.musicdb \
    --navidrome_path /path/to/my/navidrome.db \
    --user_name my_username \
    --key <DECRYPT_KEY>
"""

import argparse
import contextlib
import datetime
import os
import sqlite3
import urllib.parse

from src.musicdb import parsing as mdb_parsing
from src.musicdb import library
from src.musicdb import parsing_types


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
  query = f"SELECT id FROM user WHERE user_name='{user_name}'"
  with contextlib.closing(sqlite3.connect(db_path)) as conn:
    with conn:
      cursor = conn.cursor()
      cursor.execute(query)
      entries = cursor.fetchall()
  if not entries:
    raise ValueError(f'Could not find the user "{user_name}"')
  if len(entries) > 1:
    raise ValueError(f'Found more than one user with "{user_name}"')
  return entries[0][0]


def get_updates(
  user_id: str,
  raw_library: parsing_types.RawLibrary,
  navidrome_path_to_id: dict[str, str],
  apple_music_media_subdir: str = 'Music',
) -> tuple[list[dict[str, str | int]], list[str]]:
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
  for track in tracks:
    file_url = track.metadata.get('file_url')
    if not file_url:
      missing.append('No file url')
      continue

    file_url = urllib.parse.unquote(file_url)
    relative_path = os.path.relpath(file_url, start=library_url)
    item_id = navidrome_path_to_id.get(relative_path.lower())
    if item_id is None:
      missing.append(file_url)
      continue

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

  return updates, missing


def add_annotations(db_path: str, entries: list[dict[str, str | int]]) -> None:
  keys = ', '.join(entries[0].keys())
  values = ', '.join(f':{k}' for k in entries[0].keys())

  sql = f'INSERT OR REPLACE INTO annotation ({keys})\nVALUES ({values})'

  try:
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
      with conn:
        cursor = conn.cursor()
        cursor.executemany(sql, entries)
        print(f'Rows processed: {cursor.rowcount}')
  except sqlite3.Error as e:
    print(f'An error occurred during insertion: {e}')


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument(
    '-m', '--musicdb_path', help='The apple music library (Library.musicdb)'
  )
  parser.add_argument(
    '-n', '--navidrome_path', help='The navidrome db (navidrome.db)'
  )
  parser.add_argument(
    '-k', '--key', help='The cryptographic key used by itunes database.'
  )
  parser.add_argument('--user_name', help='The navidrome user name.')

  args = parser.parse_args()

  print(
    f'Loading the apple music library from "{args.musicdb_path}"..', flush=True
  )
  raw_library = mdb_parsing.parse_library(
    args.musicdb_path, key=args.key.encode()
  )

  print(
    f'Loading the navidrome media paths from {args.navidrome_path}...',
    flush=True,
  )
  navidrome_path_to_id = get_navidrome_media_paths(args.navidrome_path)
  user_id = get_navidrome_user_id(
    args.navidrome_path, user_name=args.user_name
  )

  print('Get the updates...', flush=True)
  updates, missing = get_updates(
    user_id=user_id,
    raw_library=raw_library,
    navidrome_path_to_id=navidrome_path_to_id,
  )
  if len(missing) > 1:
    print(f'Warning: Could not match {len(missing)} entries: {missing}')

  print('Add updates..', flush=True)
  add_annotations(args.navidrome_path, updates)

  print('All done!')


if __name__ == '__main__':
  main()

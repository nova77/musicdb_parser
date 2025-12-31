"""
Example run:
  uv run python -m examples.list_playlists --path /path/to/my/Library.musicdb --key <DECRYPT_KEY>
"""

import argparse
import datetime

from src.musicdb import parsing as mdb_parsing
from src.musicdb import library

def _format_date(date: datetime.datetime | None) -> str:
  if date is None:
    return '[never]'
  else:
    return date.strftime('%B %d, %Y (%A) %I:%M %p')


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument(
    '-p', '--path', help='The apple music library (Library.musicdb)'
  )
  parser.add_argument(
    '-k', '--key', help='The cryptographic key used by itunes database.'
  )

  args = parser.parse_args()
  print(f'Loading Library from "{args.path}"..', flush=True)
  raw_library = mdb_parsing.parse_library(args.path, key=args.key.encode())

  playlists = library.get_playlists(raw_library)

  for i, playlist in enumerate(playlists):
    print(f'## [{i}] "{playlist.name}":')
    print(f'  -> created: {_format_date(playlist.date_created)}')
    print(f'  -> modified: {_format_date(playlist.date_modified)}')
    print(f'  -> num_tracks: {len(playlist.persistent_track_ids)}')
    print(f'  -> is_smart: {playlist.is_smart}')
    print(f'  -> is_folder: {playlist.is_folder}')


if __name__ == '__main__':
  main()

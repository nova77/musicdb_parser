"""
Example run:
  uv run python -m examples.list_tracks --path /path/to/my/Library.musicdb --key <DECRYPT_KEY>
"""

import argparse

from src.musicdb import parsing as mdb_parsing
from src.musicdb import library


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument(
    '-p', '--path', help='The apple music library (Library.musicdb)'
  )
  parser.add_argument(
    '-k', '--key', help='The cryptographic key used by itunes database.'
  )

  parser.add_argument(
    '-c',
    '--count',
    type=int,
    default=20,
    help='An optional track count (default: 100)',
  )

  args = parser.parse_args()
  print(f'Loading Library from "{args.path}"..', flush=True)
  raw_library = mdb_parsing.parse_library(args.path, key=args.key.encode())

  tracks = library.get_tracks(raw_library)
  tracks = tracks[: args.count]

  for track in tracks:
    title = track.metadata.get('track_title')
    artist = track.metadata.get('artist')
    album = track.metadata.get('album')
    file_path = track.metadata.get('file_path')

    if track.date_last_played is not None:
      last_played = track.date_last_played.strftime('%B %d, %Y (%A) %I:%M %p')
    else:
      last_played = '[never]'

    print(f'# {hex(track.persistent_id)}:')
    print(f'  -> title: "{title}"')
    print(f'  -> artist: "{artist}"')
    print(f'  -> album: "{album}"')
    print(f'  -> play count: {track.play_count}')
    print(f'  -> last played: {last_played}')
    print(f'  -> path: "{file_path}"')


if __name__ == '__main__':
  main()

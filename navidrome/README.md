# navidrome

Tools for pushing data from an Apple Music library (`Library.musicdb`) into a
[Navidrome](https://www.navidrome.org/) SQLite database.

## `update_annotations.py`

Reads an Apple Music library and writes the per-user listening data (and
optionally playlists) into navidrome.

Tracks are matched by **file path** — the file layout under your Apple Music
media folder must mirror the layout navidrome scanned. If you've reorganized
files, matching will fail.

### What it writes

For every Apple Music track that matches a navidrome `media_file`, an
`annotation` row is inserted with:

- `play_count`
- `play_date` (last played)
- `rating` (0–5)
- `starred` + `starred_at` (Apple Music "loved")
- `rated_at`

If `--export_playlists` is set, every **non-smart, non-folder** playlist is
also written into `playlist` + `playlist_tracks`. Smart playlists and folders
are skipped.

### Flags

| Flag | Default | Purpose |
| --- | --- | --- |
| `--musicdb_path` | *(required)* | Path to `Library.musicdb`. |
| `--navidrome_path` | *(required)* | Path to `navidrome.db`. |
| `--key` | *(required)* | Decryption key for the iTunes/Apple Music DB. |
| `--user_name` | *(required)* | Navidrome user the annotations/playlists belong to. |
| `--override` | `false` | If set, overwrite existing annotation rows and replace the contents of existing playlists with the same name. Otherwise existing rows / playlists are left untouched. |
| `--export_playlists` | `false` | Also export non-smart, non-folder playlists. |
| `--apple_music_media_subdir` | `Music` | Subdirectory inside the Apple Music library that holds the media files. |

### Examples

**Dry-ish first run** — only fill in annotations for tracks that don't have
any in navidrome yet, no playlists:

```bash
uv run python -m navidrome.update_annotations \
  --musicdb_path  ~/Music/Music/Library.musicdb \
  --navidrome_path /var/lib/navidrome/navidrome.db \
  --user_name nova \
  --key <DECRYPT_KEY>
```

**Full sync** — overwrite existing ratings/play counts with Apple Music's
values, and also export playlists (replacing same-named ones):

```bash
uv run python -m navidrome.update_annotations \
  --musicdb_path  ~/Music/Music/Library.musicdb \
  --navidrome_path /var/lib/navidrome/navidrome.db \
  --user_name nova \
  --key <DECRYPT_KEY> \
  --override \
  --export_playlists
```

**Export playlists only, keep existing annotations untouched** — annotations
are still inserted for tracks that have none, but existing rows are left
alone; playlists are added (and same-named existing ones are skipped):

```bash
uv run python -m navidrome.update_annotations \
  --musicdb_path  ~/Music/Music/Library.musicdb \
  --navidrome_path /var/lib/navidrome/navidrome.db \
  --user_name nova \
  --key <DECRYPT_KEY> \
  --export_playlists
```

### Notes & caveats

- **Stop navidrome before running.** Writing to the SQLite file while the
  server has it open risks lock errors and (worse) inconsistent caches. Take
  a backup of `navidrome.db` first — there is no undo.
- Matching is case-insensitive on the relative path; collisions are unlikely
  but possible.
- New playlists get a fresh NanoID; their `song_count`, `duration` and `size`
  are recomputed from the navidrome `media_file` rows after insert.
- Apple Music tracks whose files are missing from navidrome are reported in a
  `Could not match …` warning at the end.

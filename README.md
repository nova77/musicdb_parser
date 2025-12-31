# Music DB parser

## A simple parser for ITL and MusicDB formats

This is a python implementation of parsers for the `.itl` (iTunes) and
`.musicdb` (Apple Music) db files.

I needed this since I wanted to migrate my stuff to navidrome and Apple Music
on Windows no longer supports exporting a library to XML.

Very much inspired by the work in:

* <https://home.vollink.com/gary/playlister/ituneslib.html> (itl)
* <https://home.vollink.com/gary/playlister/musicdb.html> (musicdb)

## Cryptographic key

Both dataset formats require a (16 chars) AES-128-ECB cryptographic key to
decode the first ~100kb of the `.itl` and `.musicdb` databases.
I'm not including it here because it's not entirely clear whether it can be
republished.

The good news is that it's the same one for both dbs and it's pretty easy to
find online. Just ask your favourite LLM for it.

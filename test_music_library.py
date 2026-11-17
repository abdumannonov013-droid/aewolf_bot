from pathlib import Path

import pytest

from app.services.music_library import MusicLibrary


def test_search_reads_artist_and_title_from_files(tmp_path):
    root = tmp_path / "music"
    artist_track = root / "Ed Sheeran" / "Shape of You.mp3"
    named_track = root / "Adele - Hello.m4a"
    artist_track.parent.mkdir(parents=True)
    artist_track.write_bytes(b"mp3")
    named_track.parent.mkdir(parents=True, exist_ok=True)
    named_track.write_bytes(b"m4a")
    (root / "notes.txt").write_text("not audio")
    library = MusicLibrary(str(root))

    artist_results = library.search("Ed Sheeran")
    title_results = library.search("Hello")

    assert artist_results == [
        {
            "path": "Ed Sheeran/Shape of You.mp3",
            "title": "Shape of You",
            "artist": "Ed Sheeran",
        }
    ]
    assert title_results == [
        {
            "path": "Adele - Hello.m4a",
            "title": "Hello",
            "artist": "Adele",
        }
    ]


def test_search_sorts_results_and_obeys_limit(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    for filename in ("Artist - Song B.mp3", "Artist - Song A.mp3"):
        (root / filename).write_bytes(b"audio")
    library = MusicLibrary(str(root))

    results = library.search("Artist", limit=1)

    assert len(results) == 1
    assert results[0]["title"] == "Song A"


def test_search_creates_missing_library_directory(tmp_path):
    root = tmp_path / "new-library"
    library = MusicLibrary(str(root))

    assert library.search("track") == []
    assert root.is_dir()


def test_resolve_track_rejects_paths_outside_library(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    library = MusicLibrary(str(root))

    with pytest.raises(ValueError, match="outside the music library"):
        library.resolve_track("../secret.mp3")


def test_resolve_track_requires_an_existing_audio_file(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    library = MusicLibrary(str(root))

    with pytest.raises(FileNotFoundError):
        library.resolve_track("missing.mp3")

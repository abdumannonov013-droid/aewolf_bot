import re
from pathlib import Path
from typing import Any


AUDIO_EXTENSIONS = {
    ".aac",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
}


def _normalize(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.casefold()).strip()


class MusicLibrary:
    def __init__(self, path: str):
        configured_path = Path(path).expanduser()
        if not configured_path.is_absolute():
            configured_path = Path(__file__).resolve().parents[2] / configured_path
        self.root = configured_path.resolve()

    def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        normalized_query = _normalize(query)
        if not normalized_query or limit <= 0:
            return []

        self.root.mkdir(parents=True, exist_ok=True)
        results = []
        for path in self.root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            try:
                relative_path = path.resolve().relative_to(self.root)
            except ValueError:
                continue

            title, artist = self._metadata(relative_path)
            if normalized_query not in _normalize(f"{artist} {title}"):
                continue
            results.append(
                {
                    "path": relative_path.as_posix(),
                    "title": title,
                    "artist": artist,
                }
            )

        results.sort(
            key=lambda item: (
                item["artist"].casefold(),
                item["title"].casefold(),
                item["path"].casefold(),
            )
        )
        return results[:limit]

    def resolve_track(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Track path is outside the music library") from exc
        if not candidate.is_file() or candidate.suffix.lower() not in AUDIO_EXTENSIONS:
            raise FileNotFoundError("Audio track is not available")
        return candidate

    @staticmethod
    def _metadata(relative_path: Path) -> tuple[str, str]:
        stem = relative_path.stem
        parts = re.split(r"\s+(?:-|–|—)\s+", stem, maxsplit=1)
        if len(parts) == 2:
            artist, title = parts
        else:
            artist = relative_path.parts[0] if len(relative_path.parts) > 1 else ""
            title = stem
        return title.strip(), artist.strip()

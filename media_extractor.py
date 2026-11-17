from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any
import yt_dlp

@dataclass
class MediaInfo:
    url: str
    title: str
    ext: str | None
    duration: float | None
    filesize: int | None
    direct_url: str | None
    is_video: bool
    http_headers: dict[str, str] | None = None


@dataclass
class DownloadedMedia:
    path: str
    title: str
    is_video: bool


class MediaExtractor:
    def analyze(self, url: str) -> MediaInfo:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "extract_flat": False,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info: dict[str, Any] = ydl.extract_info(url, download=False)

        formats = info.get("formats") or []
        chosen = None

        # Prefer a single progressive format to avoid a local merge.
        progressive = [
            f for f in formats
            if f.get("url") and f.get("vcodec") not in (None, "none")
            and f.get("acodec") not in (None, "none")
        ]
        mp4_progressive = [f for f in progressive if f.get("ext") == "mp4"]
        candidates = mp4_progressive or progressive
        candidates.sort(
            key=lambda f: (f.get("height") or 0, f.get("tbr") or 0),
            reverse=True,
        )
        if candidates:
            chosen = candidates[0]

        selected = chosen or info
        is_video = selected.get("vcodec") not in (None, "none")
        if chosen is None and not is_video:
            is_video = info.get("ext") in {
                "3gp",
                "avi",
                "m4v",
                "mkv",
                "mov",
                "mp4",
                "mpeg",
                "mpg",
                "ts",
                "webm",
            } or any(
                f.get("vcodec") not in (None, "none") for f in formats
            )

        return MediaInfo(
            url=url,
            title=info.get("title") or "Media",
            ext=selected.get("ext") or info.get("ext"),
            duration=info.get("duration"),
            filesize=selected.get("filesize") or info.get("filesize"),
            direct_url=selected.get("url"),
            is_video=bool(is_video),
            http_headers=selected.get("http_headers"),
        )

    def download(self, url: str, output_dir: str) -> DownloadedMedia:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "concurrent_fragment_downloads": 8,
            "format": (
                "best[height<=720][ext=mp4][vcodec^=avc1][acodec^=mp4a]/"
                "bestvideo[height<=720][ext=mp4][vcodec^=avc1]+"
                "bestaudio[ext=m4a]/best[height<=720]/"
                "bestvideo[height<=720]+bestaudio/best"
            ),
            "merge_output_format": "mp4",
            "outtmpl": str(Path(output_dir) / "%(id)s.%(ext)s"),
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info: dict[str, Any] = ydl.extract_info(url, download=True)

        downloaded = [
            path
            for path in Path(output_dir).iterdir()
            if path.is_file() and path.suffix not in {".part", ".ytdl"}
        ]
        if not downloaded:
            raise RuntimeError("yt-dlp completed without producing a media file")

        downloaded.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        selected_formats = (
            info.get("requested_downloads")
            or info.get("requested_formats")
            or [info]
        )
        video_codec = next(
            (
                fmt.get("vcodec")
                for fmt in selected_formats
                if fmt.get("vcodec") not in (None, "none")
            ),
            info.get("vcodec"),
        )
        audio_codec = next(
            (
                fmt.get("acodec")
                for fmt in selected_formats
                if fmt.get("acodec") not in (None, "none")
            ),
            info.get("acodec"),
        )
        has_h264 = str(video_codec or "").startswith("avc1")
        has_aac = (
            audio_codec in (None, "none")
            or str(audio_codec).startswith("mp4a")
        )
        is_video = (
            video_codec not in (None, "none")
            or info.get("ext") in {
                "3gp", "avi", "m4v", "mkv", "mov", "mp4",
                "mpeg", "mpg", "ts", "webm",
            }
        )
        path = downloaded[0]
        if is_video and (
            path.suffix.lower() != ".mp4"
            or not has_h264
            or not has_aac
        ):
            path = Path(self._convert_to_mp4(path, output_dir, has_h264, has_aac))

        return DownloadedMedia(
            path=str(path),
            title=info.get("title") or "Media",
            is_video=bool(is_video),
        )

    @staticmethod
    def _convert_to_mp4(
        source: Path,
        output_dir: str,
        has_h264: bool,
        has_aac: bool,
    ) -> str:
        output = Path(output_dir) / "telegram-video.mp4"
        can_copy = has_h264 and has_aac

        def run_conversion(copy_streams: bool) -> subprocess.CompletedProcess[str]:
            command = [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
            ]
            if copy_streams:
                command.extend(["-c", "copy"])
            else:
                command.extend(
                    [
                        "-vf",
                        "scale=w='min(1280,iw)':h=-2",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "ultrafast",
                        "-crf",
                        "27",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "128k",
                    ]
                )
            command.extend(["-movflags", "+faststart", str(output)])
            return subprocess.run(command, capture_output=True, text=True)

        result = run_conversion(can_copy)
        if result.returncode and can_copy:
            result = run_conversion(copy_streams=False)
        if result.returncode:
            raise RuntimeError(f"FFmpeg could not prepare video: {result.stderr[-1500:]}")
        return str(output)


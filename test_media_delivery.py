import asyncio
from pathlib import Path
import subprocess
from unittest.mock import AsyncMock, Mock, call

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendAudio, SendVideo
from aiogram.types import FSInputFile, URLInputFile
import pytest

from app.bot.handlers import media as media_handler
from app.services.media_extractor import (
    DownloadedMedia,
    MediaExtractor,
    MediaInfo,
)
from app.services.state import InMemoryState
from app.services.telegram_sender import TelegramSender


def test_extractor_uses_direct_mp4_url_without_formats(monkeypatch):
    class DirectMp4:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def extract_info(self, url, download):
            return {
                "url": url,
                "title": "Direct clip",
                "ext": "mp4",
                "filesize": 100,
            }

    monkeypatch.setattr("app.services.media_extractor.yt_dlp.YoutubeDL", DirectMp4)

    info = MediaExtractor().analyze("https://cdn.example/video.mp4?signature=temporary")

    assert info.direct_url == "https://cdn.example/video.mp4?signature=temporary"
    assert info.is_video


def test_extractor_prefers_progressive_mp4_format(monkeypatch):
    class Formats:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def extract_info(self, url, download):
            return {
                "title": "Clip",
                "ext": "webm",
                "formats": [
                    {
                        "url": "https://cdn.example/video.webm",
                        "ext": "webm",
                        "height": 1080,
                        "vcodec": "vp9",
                        "acodec": "opus",
                    },
                    {
                        "url": "https://cdn.example/video.mp4",
                        "ext": "mp4",
                        "height": 720,
                        "vcodec": "avc1",
                        "acodec": "mp4a",
                    },
                ],
            }

    monkeypatch.setattr("app.services.media_extractor.yt_dlp.YoutubeDL", Formats)

    info = MediaExtractor().analyze("https://www.youtube.com/watch?v=example")

    assert info.direct_url == "https://cdn.example/video.mp4"
    assert info.ext == "mp4"


def test_extractor_marks_adaptive_formats_as_video(monkeypatch):
    class AdaptiveFormats:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def extract_info(self, url, download):
            return {
                "title": "Adaptive clip",
                "formats": [
                    {"url": "https://cdn.example/video", "vcodec": "avc1", "acodec": "none"},
                    {"url": "https://cdn.example/audio", "vcodec": "none", "acodec": "mp4a"},
                ],
            }

    monkeypatch.setattr("app.services.media_extractor.yt_dlp.YoutubeDL", AdaptiveFormats)

    info = MediaExtractor().analyze("https://www.youtube.com/watch?v=adaptive")

    assert info.direct_url is None
    assert info.is_video


def test_extractor_downloads_combined_media_when_no_direct_url(monkeypatch, tmp_path):
    class Download:
        def __init__(self, options):
            self.options = options
            assert "height<=720" in options["format"]
            assert options["concurrent_fragment_downloads"] == 8

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def extract_info(self, url, download):
            assert download
            output_path = self.options["outtmpl"].replace(
                "%(id)s.%(ext)s", "clip.mp4"
            )
            Path(output_path).write_bytes(b"video")
            return {
                "id": "clip",
                "title": "Downloaded clip",
                "ext": "mp4",
                "vcodec": "avc1",
            }

    monkeypatch.setattr("app.services.media_extractor.yt_dlp.YoutubeDL", Download)

    path = MediaExtractor().download(
        "https://www.youtube.com/watch?v=adaptive", str(tmp_path)
    )

    assert Path(path.path).name == "clip.mp4"
    assert path.title == "Downloaded clip"
    assert path.is_video


def test_extractor_converts_video_to_telegram_compatible_mp4(monkeypatch, tmp_path):
    class Download:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def extract_info(self, url, download):
            output_path = Path(self.options["outtmpl"].replace(
                "%(id)s.%(ext)s", "clip.webm"
            ))
            output_path.write_bytes(b"video")
            return {
                "title": "WebM clip",
                "ext": "webm",
                "requested_downloads": [
                    {"vcodec": "vp9", "acodec": "opus"}
                ],
            }

    def convert(command, capture_output, text):
        Path(command[-1]).write_bytes(b"mp4")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.services.media_extractor.yt_dlp.YoutubeDL", Download)
    monkeypatch.setattr("app.services.media_extractor.subprocess.run", convert)

    media = MediaExtractor().download(
        "https://example.com/clip", str(tmp_path)
    )

    assert Path(media.path).suffix == ".mp4"
    assert media.is_video


def test_media_handler_downloads_when_extractor_has_no_direct_url(monkeypatch):
    status = type(
        "StatusStub",
        (),
        {
            "edit_text": AsyncMock(),
            "delete": AsyncMock(),
        },
    )()
    message = type("MessageStub", (), {})()
    message.text = "https://source.example/watch?v=adaptive"
    message.from_user = type("UserStub", (), {"id": 123})()
    message.chat = type("ChatStub", (), {"id": 123})()
    message.bot = object()
    message.answer = AsyncMock(return_value=status)

    monkeypatch.setattr(media_handler.limiter, "allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(
        media_handler.extractor,
        "analyze",
        lambda url: MediaInfo(url, "Adaptive clip", "mp4", 10, None, None, True),
    )

    def download(url, output_dir):
        path = Path(output_dir) / "clip.mp4"
        path.write_bytes(b"video")
        return DownloadedMedia(str(path), "Adaptive clip", True)

    monkeypatch.setattr(media_handler.extractor, "download", download)
    send_file = AsyncMock()
    monkeypatch.setattr(media_handler.TelegramSender, "send_file", send_file)

    asyncio.run(media_handler.handle_message(message))

    send_file.assert_awaited_once()
    assert send_file.await_args.args[1] == 123
    assert send_file.await_args.args[3:] == ("Adaptive clip", True)
    status.delete.assert_awaited_once()


def test_media_handler_downloads_when_telegram_rejects_direct_url(monkeypatch):
    status = type(
        "StatusStub",
        (),
        {
            "edit_text": AsyncMock(),
            "delete": AsyncMock(),
        },
    )()
    message = type("MessageStub", (), {})()
    message.text = "https://source.example/watch?v=clip"
    message.from_user = type("UserStub", (), {"id": 123})()
    message.chat = type("ChatStub", (), {"id": 123})()
    message.bot = object()
    message.answer = AsyncMock(return_value=status)

    monkeypatch.setattr(media_handler.limiter, "allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(
        media_handler.extractor,
        "analyze",
        lambda url: MediaInfo(
            url, "YouTube clip", "mp4", 10, None, "https://cdn.example/clip.mp4", True
        ),
    )
    monkeypatch.setattr(
        media_handler.TelegramSender,
        "send_from_url",
        AsyncMock(side_effect=RuntimeError("Telegram could not fetch the URL")),
    )
    monkeypatch.setattr(
        media_handler.extractor,
        "download",
        lambda url, output_dir: DownloadedMedia(
            str(Path(output_dir) / "clip.mp4"), "YouTube clip", True
        ),
    )
    send_file = AsyncMock()
    monkeypatch.setattr(media_handler.TelegramSender, "send_file", send_file)

    asyncio.run(media_handler.handle_message(message))

    send_file.assert_awaited_once()
    status.delete.assert_awaited_once()


def test_youtube_uses_telegram_direct_fetch_without_local_download(monkeypatch):
    status = type(
        "StatusStub",
        (),
        {
            "edit_text": AsyncMock(),
            "delete": AsyncMock(),
        },
    )()
    message = type("MessageStub", (), {})()
    message.text = "https://youtu.be/clip"
    message.from_user = type("UserStub", (), {"id": 123})()
    message.chat = type("ChatStub", (), {"id": 123})()
    message.bot = object()
    message.answer = AsyncMock(return_value=status)

    url = "https://youtu.be/clip"
    direct_url = "https://cdn.example/clip.mp4"
    monkeypatch.setattr(media_handler.limiter, "allowed", AsyncMock(return_value=True))
    analyze = Mock(
        return_value=MediaInfo(url, "YouTube clip", "mp4", 10, None, direct_url, True)
    )
    monkeypatch.setattr(media_handler.extractor, "analyze", analyze)
    download = Mock(side_effect=AssertionError("local download must be skipped"))
    monkeypatch.setattr(media_handler.extractor, "download", download)
    send_direct = AsyncMock()
    monkeypatch.setattr(
        media_handler.TelegramSender, "send_from_url", send_direct
    )

    asyncio.run(media_handler.handle_message(message))

    analyze.assert_called_once_with(url)
    download.assert_not_called()
    send_direct.assert_awaited_once_with(
        message.bot, 123, direct_url, None, "mp4"
    )
    message.answer.assert_awaited_once_with("⌛")
    status.delete.assert_awaited_once()


def test_instagram_uses_telegram_direct_fetch_without_local_download(monkeypatch):
    status = type(
        "StatusStub",
        (),
        {
            "edit_text": AsyncMock(),
            "delete": AsyncMock(),
        },
    )()
    message = type("MessageStub", (), {})()
    message.text = "https://www.instagram.com/reel/clip/"
    message.from_user = type("UserStub", (), {"id": 123})()
    message.chat = type("ChatStub", (), {"id": 123})()
    message.bot = object()
    message.answer = AsyncMock(return_value=status)

    url = message.text
    direct_url = "https://cdn.example/instagram-clip.mp4"
    monkeypatch.setattr(media_handler.limiter, "allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(
        media_handler.extractor,
        "analyze",
        Mock(
            return_value=MediaInfo(
                url, "Instagram clip", "mp4", 10, None, direct_url, True
            )
        ),
    )
    download = Mock(side_effect=AssertionError("local download must be skipped"))
    monkeypatch.setattr(media_handler.extractor, "download", download)
    send_direct = AsyncMock()
    monkeypatch.setattr(
        media_handler.TelegramSender, "send_direct_video", send_direct
    )

    asyncio.run(media_handler.handle_message(message))

    download.assert_not_called()
    send_direct.assert_awaited_once_with(message.bot, 123, direct_url)
    status.delete.assert_awaited_once()


def test_youtube_downloads_when_no_direct_video_format_exists(monkeypatch):
    status = type(
        "StatusStub",
        (),
        {
            "edit_text": AsyncMock(),
            "delete": AsyncMock(),
        },
    )()
    message = type("MessageStub", (), {})()
    message.text = "https://youtu.be/clip"
    message.from_user = type("UserStub", (), {"id": 123})()
    message.chat = type("ChatStub", (), {"id": 123})()
    message.bot = object()
    message.answer = AsyncMock(return_value=status)

    monkeypatch.setattr(media_handler.limiter, "allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(
        media_handler.extractor,
        "analyze",
        Mock(return_value=MediaInfo(
            "https://youtu.be/clip", "YouTube clip", "mp4", 10, None, None, True
        )),
    )
    download = Mock(
        return_value=DownloadedMedia("clip.mp4", "YouTube clip", True)
    )
    monkeypatch.setattr(media_handler.extractor, "download", download)
    send_file = AsyncMock()
    monkeypatch.setattr(media_handler.TelegramSender, "send_file", send_file)
    send_direct = AsyncMock()
    monkeypatch.setattr(
        media_handler.TelegramSender, "send_direct_video", send_direct
    )

    asyncio.run(media_handler.handle_message(message))

    download.assert_called_once()
    send_direct.assert_not_awaited()
    send_file.assert_awaited_once_with(
        message.bot, 123, "clip.mp4", "YouTube clip", True
    )
    status.delete.assert_awaited_once()


def test_youtube_direct_send_failure_falls_back_to_local_download(monkeypatch):
    status = type(
        "StatusStub",
        (),
        {
            "edit_text": AsyncMock(),
            "delete": AsyncMock(),
        },
    )()
    message = type("MessageStub", (), {})()
    message.text = "https://youtu.be/clip"
    message.from_user = type("UserStub", (), {"id": 123})()
    message.chat = type("ChatStub", (), {"id": 123})()
    message.bot = object()
    message.answer = AsyncMock(return_value=status)

    monkeypatch.setattr(media_handler.limiter, "allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(
        media_handler.extractor,
        "analyze",
        Mock(return_value=MediaInfo(
            "https://youtu.be/clip",
            "YouTube clip",
            "mp4",
            10,
            None,
            "https://cdn.example/clip.mp4",
            True,
        )),
    )
    download = Mock(
        return_value=DownloadedMedia("clip.mp4", "YouTube clip", True)
    )
    monkeypatch.setattr(media_handler.extractor, "download", download)
    monkeypatch.setattr(
        media_handler.TelegramSender,
        "send_from_url",
        AsyncMock(side_effect=RuntimeError("remote fetch failed")),
    )
    send_file = AsyncMock()
    monkeypatch.setattr(media_handler.TelegramSender, "send_file", send_file)

    asyncio.run(media_handler.handle_message(message))

    download.assert_called_once()
    send_file.assert_awaited_once_with(
        message.bot, 123, "clip.mp4", "YouTube clip", True
    )
    status.delete.assert_awaited_once()


def test_video_delivery_prefers_direct_telegram_url():
    bot = type("BotStub", (), {"send_video": AsyncMock(return_value="sent")})()

    result = asyncio.run(
        TelegramSender.send_from_url(
            bot, 123, "https://cdn.example/video.mp4"
        )
    )

    assert result == "sent"
    bot.send_video.assert_awaited_once_with(123, "https://cdn.example/video.mp4")


def test_video_delivery_falls_back_to_streamed_file():
    bot = type(
        "BotStub",
        (),
        {
            "send_video": AsyncMock(
                side_effect=[
                    TelegramBadRequest(
                        method=SendVideo(chat_id=123, video="https://cdn.example/video.mp4"),
                        message="URL unavailable",
                    ),
                    "sent",
                ]
            )
        },
    )()
    headers = {"Referer": "https://source.example"}

    result = asyncio.run(
        TelegramSender.send_from_url(
            bot, 123, "https://cdn.example/video.mp4", headers
        )
    )

    assert result == "sent"
    assert bot.send_video.await_args_list[0] == call(123, "https://cdn.example/video.mp4")
    fallback = bot.send_video.await_args_list[1].args[1]
    assert isinstance(fallback, URLInputFile)
    assert fallback.headers == headers
    assert fallback.filename == "video.mp4"


def test_audio_delivery_stream_fallback_keeps_source_headers():
    url = "https://cdn.example/audio"
    headers = {"User-Agent": "test-agent"}
    bot = type(
        "BotStub",
        (),
        {
            "send_audio": AsyncMock(
                side_effect=[
                    TelegramBadRequest(
                        method=SendAudio(chat_id=123, audio=url),
                        message="URL unavailable",
                    ),
                    "sent",
                ]
            )
        },
    )()

    result = asyncio.run(
        TelegramSender.send_audio_from_url(
            bot, 123, url, "Track", headers
        )
    )

    assert result == "sent"
    assert bot.send_audio.await_args_list[0] == call(123, url, title="Track")
    fallback = bot.send_audio.await_args_list[1].args[1]
    assert isinstance(fallback, URLInputFile)
    assert fallback.headers == headers


def test_local_music_file_is_sent_as_audio_with_artist(tmp_path):
    path = tmp_path / "Track.mp3"
    path.write_bytes(b"audio")
    bot = type(
        "BotStub",
        (),
        {
            "send_audio": AsyncMock(return_value="sent"),
            "send_document": AsyncMock(),
        },
    )()

    result = asyncio.run(
        TelegramSender.send_audio_file(bot, 123, path, "Track", "Artist")
    )

    assert result == "sent"
    bot.send_audio.assert_awaited_once()
    assert bot.send_audio.await_args.args[0] == 123
    assert isinstance(bot.send_audio.await_args.args[1], FSInputFile)
    assert bot.send_audio.await_args.kwargs == {
        "title": "Track",
        "performer": "Artist",
    }
    bot.send_document.assert_not_awaited()


def test_non_mp4_video_url_is_left_for_local_conversion():
    bot = type(
        "BotStub",
        (),
        {
            "send_video": AsyncMock(
                side_effect=TelegramBadRequest(
                    method=SendVideo(chat_id=123, video="https://cdn.example/video.webm"),
                    message="Unsupported video format",
                )
            ),
            "send_document": AsyncMock(return_value="sent"),
        },
    )()

    with pytest.raises(TelegramBadRequest):
        asyncio.run(
            TelegramSender.send_from_url(
                bot, 123, "https://cdn.example/video.webm", ext="webm"
            )
        )

    bot.send_document.assert_not_awaited()


def test_local_video_is_sent_as_video_not_document(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"video")
    bot = type(
        "BotStub",
        (),
        {
            "send_video": AsyncMock(return_value="sent"),
            "send_document": AsyncMock(),
        },
    )()

    result = asyncio.run(
        TelegramSender.send_file(bot, 123, str(path), "Clip", True)
    )

    assert result == "sent"
    bot.send_video.assert_awaited_once()
    bot.send_document.assert_not_awaited()


def test_in_memory_state_expires_values(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("app.services.state.time.monotonic", lambda: now[0])
    state = InMemoryState()

    async def scenario():
        assert await state.set("key", "value", ex=5, nx=True)
        assert not await state.set("key", "other", ex=5, nx=True)
        now[0] += 5
        assert await state.get("key") is None
        assert await state.set("key", "other", ex=5, nx=True)

    asyncio.run(scenario())

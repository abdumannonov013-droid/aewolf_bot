import asyncio
import re
import logging
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from aiogram import Router
from aiogram.types import Message
from app.services.media_extractor import MediaExtractor
from app.services.ratelimit import RateLimiter
from app.services.state import state
from app.services.telegram_sender import TelegramSender

router = Router()
log = logging.getLogger(__name__)
extractor = MediaExtractor()
limiter = RateLimiter(state)

URL_RE = re.compile(r"https?://[^\s<>]+")


def _is_youtube_url(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host == "youtu.be" or any(
        host == domain or host.endswith(f".{domain}")
        for domain in ("youtube.com", "youtube-nocookie.com")
    )


def _is_instagram_url(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host in {"instagr.am", "www.instagr.am"} or (
        host == "instagram.com" or host.endswith(".instagram.com")
    )


async def _send_downloaded_media(message: Message, url: str):
    with TemporaryDirectory(prefix="zyx-media-") as output_dir:
        media = await asyncio.to_thread(extractor.download, url, output_dir)
        await TelegramSender.send_file(
            message.bot,
            message.chat.id,
            media.path,
            media.title,
            media.is_video,
        )


@router.message()
async def handle_message(message: Message):
    if not message.text:
        return

    match = URL_RE.search(message.text.strip())
    if not match:
        return

    if not await limiter.allowed(message.from_user.id):
        await message.answer("⏳ Juda tez-tez so‘rov yuborildi. Biroz kuting.")
        return

    url = match.group(0)
    status = await message.answer("⌛")

    try:
        if _is_youtube_url(url):
            info = await asyncio.to_thread(extractor.analyze, url)
            if info.direct_url and info.is_video:
                try:
                    await TelegramSender.send_from_url(
                        message.bot,
                        message.chat.id,
                        info.direct_url,
                        info.http_headers,
                        info.ext,
                    )
                except Exception:
                    log.warning(
                        "YouTube URL delivery failed; using yt-dlp fallback",
                        exc_info=True,
                    )
                    await _send_downloaded_media(message, url)
            else:
                await _send_downloaded_media(message, url)
            await status.delete()
            return

        if _is_instagram_url(url):
            info = await asyncio.to_thread(extractor.analyze, url)
            if not info.direct_url or not info.is_video:
                await status.edit_text(
                    "❌ Telegram bevosita yubora oladigan video formati topilmadi."
                )
                return
            await TelegramSender.send_direct_video(
                message.bot, message.chat.id, info.direct_url
            )
            await status.delete()
            return

        info = await asyncio.to_thread(extractor.analyze, url)

        if info.direct_url:
            try:
                if info.is_video:
                    await TelegramSender.send_from_url(
                        message.bot,
                        message.chat.id,
                        info.direct_url,
                        info.http_headers,
                        info.ext,
                    )
                else:
                    await TelegramSender.send_audio_from_url(
                        message.bot,
                        message.chat.id,
                        info.direct_url,
                        info.title,
                        info.http_headers,
                    )
            except Exception:
                log.warning(
                    "direct media delivery failed; downloading with yt-dlp",
                    exc_info=True,
                )
                await _send_downloaded_media(message, url)
        else:
            await _send_downloaded_media(message, url)

        await status.delete()

    except Exception as exc:
        log.exception("media processing failed")
        if _is_instagram_url(url):
            await status.edit_text(
                f"❌ Telegram videoni manbadan bevosita ola olmadi ({type(exc).__name__})."
            )
        else:
            await status.edit_text(
                f"❌ Media yuborilmadi ({type(exc).__name__})."
            )

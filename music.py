import asyncio
import html
import logging
import re
from typing import Any

from aiogram import Bot, Router
from aiogram.types import Message
from app.config import settings
from app.bot.keyboards.music import (
    MUSIC_PAGE_SIZE,
    music_results_keyboard,
)
from app.services.music_library import MusicLibrary
from app.services.state import state
from app.services.telegram_sender import TelegramSender

router = Router()
log = logging.getLogger(__name__)
library = MusicLibrary(settings.music_library_path)
MUSIC_RESULT_LIMIT = 50


def _normalize_search_text(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.casefold()).strip()


def _is_track_title_query(query: str, item: dict) -> bool:
    normalized_query = _normalize_search_text(query)
    if not normalized_query:
        return False

    artist_names = (
        item.get("artist"),
        item.get("uploader"),
        item.get("channel"),
    )
    if any(
        normalized_query in _normalize_search_text(name)
        for name in artist_names
        if name
    ):
        return False

    title = item.get("title") or ""
    normalized_title = _normalize_search_text(title)
    if normalized_query == normalized_title:
        return True
    if len(normalized_query.split()) > 1 and normalized_query in normalized_title:
        return True

    title_parts = re.split(r"\s+(?:-|–|—|:)\s+", title)
    return any(
        normalized_query == _normalize_search_text(part)
        for part in title_parts
    )


def _results_page_text(results: list[dict], page: int) -> str:
    start = page * MUSIC_PAGE_SIZE
    end = min(start + MUSIC_PAGE_SIZE, len(results))
    lines = [f"🎵 <b>Natijalar {start + 1}–{end}/{len(results)}:</b>", ""]
    lines.extend(
        f"{index + 1}. {html.escape(results[index]['title'])}"
        + (
            f" — {html.escape(results[index]['artist'])}"
            if results[index].get("artist")
            else ""
        )
        for index in range(start, end)
    )
    return "\n".join(lines)


async def send_music_track(bot: Bot, chat_id: int, track: dict[str, Any]):
    path = await asyncio.to_thread(library.resolve_track, track["path"])
    return await TelegramSender.send_audio_file(
        bot,
        chat_id,
        path,
        track["title"],
        track.get("artist", ""),
    )


@router.message(
    lambda message: message.text
    and message.text.casefold() in {"/musiqa", "musiqa", "🎵 musiqa"}
)
async def music_start(message: Message):
    await state.set(f"music:mode:{message.from_user.id}", "1", ex=600)
    await message.answer("🎵 Qo‘shiq yoki ijrochi nomini yozing:")


@router.message()
async def music_query(message: Message):
    if not message.text:
        return

    user_id = message.from_user.id
    mode_key = f"music:mode:{user_id}"
    if not await state.get(mode_key):
        return

    await state.delete(mode_key)
    query = message.text.strip()
    status = await message.answer("⌛")

    try:
        results = await asyncio.to_thread(
            library.search, query, MUSIC_RESULT_LIMIT
        )
        if not results:
            await status.edit_text(
                "❌ Mos musiqa topilmadi. Ruxsatli audio fayllarni musiqa "
                "kutubxonasiga qo‘shing yoki boshqa nom bilan qidiring."
            )
            return

        await state.set(
            f"music:results:{user_id}",
            str(results),
            ex=600,
        )

        if _is_track_title_query(query, results[0]):
            try:
                await send_music_track(message.bot, message.chat.id, results[0])
                await status.delete()
            except Exception:
                log.exception("failed to send requested track")
                await status.edit_text(
                    "❌ Qo‘shiqni yuborib bo‘lmadi. /musiqa orqali qayta urinib ko‘ring."
                )
            return

        await status.edit_text(
            _results_page_text(results, 0),
            reply_markup=music_results_keyboard(len(results), 0),
        )
    except Exception:
        log.exception("music search failed")
        await status.edit_text("❌ Musiqa qidirishda xatolik yuz berdi.")

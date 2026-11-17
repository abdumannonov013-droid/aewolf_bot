import ast
import logging

from aiogram import Router
from aiogram.types import CallbackQuery
from app.bot.handlers.music import _results_page_text, send_music_track
from app.bot.keyboards.music import MUSIC_PAGE_SIZE, music_results_keyboard
from app.services.state import state

router = Router()
log = logging.getLogger(__name__)


async def _get_music_results(user_id: int) -> list[dict] | None:
    raw = await state.get(f"music:results:{user_id}")
    if not raw:
        return None
    results = ast.literal_eval(raw)
    return results if isinstance(results, list) else None


@router.callback_query(lambda callback: callback.data in {
    "menu:music",
    "menu:video",
    "menu:help",
})
async def menu_selected(callback: CallbackQuery):
    await callback.answer()
    if callback.data == "menu:music":
        await state.set(
            f"music:mode:{callback.from_user.id}", "1", ex=600
        )
        await callback.message.answer("🎵 Qo‘shiq yoki ijrochi nomini yozing:")
    elif callback.data == "menu:video":
        await callback.message.answer("🔗 Video havolasini yuboring.")
    else:
        await callback.message.answer(
            "🔗 Video havolasini yuboring yoki 🎵 Musiqa tugmasini bosing."
        )


@router.callback_query(
    lambda callback: callback.data and callback.data.startswith("music:page:")
)
async def music_page_selected(callback: CallbackQuery):
    await callback.answer()
    try:
        page = int(callback.data.rsplit(":", 1)[1])
        results = await _get_music_results(callback.from_user.id)
        if results is None:
            await callback.message.answer(
                "⏳ Natijalar eskirgan. /musiqa orqali qayta qidiring."
            )
            return

        page_count = (len(results) + MUSIC_PAGE_SIZE - 1) // MUSIC_PAGE_SIZE
        if page < 0 or page >= page_count:
            await callback.message.answer("❌ Noto‘g‘ri sahifa.")
            return

        await callback.message.edit_text(
            _results_page_text(results, page),
            reply_markup=music_results_keyboard(len(results), page),
        )
    except Exception:
        log.exception("failed to show music results page")
        await callback.message.answer("❌ Natijalar ro‘yxatini ochib bo‘lmadi.")


@router.callback_query(
    lambda callback: callback.data and callback.data.startswith("music:item:")
)
async def music_selected(callback: CallbackQuery):
    await callback.answer("Tanlandi")
    try:
        index = int(callback.data.rsplit(":", 1)[1])
        results = await _get_music_results(callback.from_user.id)
        if results is None:
            await callback.message.answer(
                "⏳ Natijalar eskirgan. /musiqa orqali qayta qidiring."
            )
            return
        if index < 0 or index >= len(results):
            await callback.message.answer("❌ Noto‘g‘ri tanlov.")
            return

        item = results[index]
        status = await callback.message.answer("⌛")
        try:
            await send_music_track(
                callback.bot, callback.message.chat.id, item
            )
            await status.delete()
        except Exception:
            log.exception("failed to send selected music")
            await status.edit_text(
                "❌ Bu audio hozir olinmadi. Boshqa natijani tanlang."
            )
    except Exception:
        log.exception("invalid music callback")
        await callback.message.answer("❌ Tanlovni bajarib bo‘lmadi.")

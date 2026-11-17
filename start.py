from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from app.bot.keyboards.main import main_menu_keyboard

router = Router()

@router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "<b>AEwolf</b>\n\n"
        "🔗 Video havolasini yuboring.\n"
        "🎵 Musiqa qidirish uchun /musiqa ni bosing.",
        reply_markup=main_menu_keyboard(),
    )

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Musiqa",
                    callback_data="menu:music",
                    style="primary",
                ),
                InlineKeyboardButton(
                    text="Video",
                    callback_data="menu:video",
                    style="success",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Yordam",
                    callback_data="menu:help",
                    style="danger",
                )
            ],
        ]
    )

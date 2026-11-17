from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


MUSIC_PAGE_SIZE = 10


def music_results_keyboard(
    total: int, page: int = 0
) -> InlineKeyboardMarkup:
    start = page * MUSIC_PAGE_SIZE
    end = min(start + MUSIC_PAGE_SIZE, total)
    buttons = [
        InlineKeyboardButton(
            text=str(index + 1),
            callback_data=f"music:item:{index}",
            style="primary",
        )
        for index in range(start, end)
    ]
    rows = [buttons[i:i+5] for i in range(0, len(buttons), 5)]
    navigation = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="Oldingi",
                callback_data=f"music:page:{page - 1}",
                style="primary",
            )
        )
    if end < total:
        navigation.append(
            InlineKeyboardButton(
                text="Keyingi",
                callback_data=f"music:page:{page + 1}",
                style="primary",
            )
        )
    if navigation:
        rows.append(navigation)
    return InlineKeyboardMarkup(inline_keyboard=rows)

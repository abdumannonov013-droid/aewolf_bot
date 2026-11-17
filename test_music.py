import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from aiogram.types import InlineKeyboardMarkup

from app.bot.handlers import callbacks as callback_handlers
from app.bot.handlers import music as music_handler
from app.bot.handlers.start import start
from app.bot.keyboards.music import music_results_keyboard


def _message(text: str):
    status = type(
        "StatusStub",
        (),
        {
            "edit_text": AsyncMock(),
            "delete": AsyncMock(),
        },
    )()
    message = type("MessageStub", (), {})()
    message.text = text
    message.from_user = type("UserStub", (), {"id": 123})()
    message.chat = type("ChatStub", (), {"id": 123})()
    message.bot = object()
    message.answer = AsyncMock(return_value=status)
    return message, status


def test_song_title_search_sends_first_track(monkeypatch):
    message, status = _message("Shape of You")
    monkeypatch.setattr(
        music_handler.state, "get", AsyncMock(return_value="1")
    )
    delete_state = AsyncMock()
    monkeypatch.setattr(music_handler.state, "delete", delete_state)
    save_state = AsyncMock()
    monkeypatch.setattr(music_handler.state, "set", save_state)
    results = [
        {
            "title": "Shape of You",
            "artist": "Ed Sheeran",
            "path": "Ed Sheeran/Shape of You.mp3",
        }
    ]
    search = Mock(return_value=results)
    monkeypatch.setattr(music_handler.library, "search", search)
    resolve = Mock(return_value=Path("music_library/Ed Sheeran/Shape of You.mp3"))
    monkeypatch.setattr(music_handler.library, "resolve_track", resolve)
    send_audio = AsyncMock()
    monkeypatch.setattr(
        music_handler.TelegramSender, "send_audio_file", send_audio
    )

    asyncio.run(music_handler.music_query(message))

    message.answer.assert_awaited_once_with("⌛")
    search.assert_called_once_with("Shape of You", 50)
    resolve.assert_called_once_with("Ed Sheeran/Shape of You.mp3")
    send_audio.assert_awaited_once_with(
        message.bot,
        123,
        Path("music_library/Ed Sheeran/Shape of You.mp3"),
        "Shape of You",
        "Ed Sheeran",
    )
    delete_state.assert_awaited_once_with("music:mode:123")
    save_state.assert_awaited_once()
    status.delete.assert_awaited_once()


def test_artist_search_shows_numbered_results_and_pages(monkeypatch):
    message, status = _message("Taylor Swift")
    results = [
        {
            "title": f"Track {index}",
            "artist": "Taylor Swift",
            "path": f"Taylor Swift/Track {index}.mp3",
        }
        for index in range(12)
    ]
    monkeypatch.setattr(
        music_handler.state, "get", AsyncMock(return_value="1")
    )
    monkeypatch.setattr(music_handler.state, "delete", AsyncMock())
    save_state = AsyncMock()
    monkeypatch.setattr(music_handler.state, "set", save_state)
    search = Mock(return_value=results)
    monkeypatch.setattr(music_handler.library, "search", search)
    resolve = Mock(side_effect=AssertionError("artist search should show results"))
    monkeypatch.setattr(music_handler.library, "resolve_track", resolve)

    asyncio.run(music_handler.music_query(message))

    message.answer.assert_awaited_once_with("⌛")
    search.assert_called_once_with("Taylor Swift", 50)
    resolve.assert_not_called()
    save_state.assert_awaited_once()
    text = status.edit_text.await_args.args[0]
    markup = status.edit_text.await_args.kwargs["reply_markup"]
    assert "1. Track 0 — Taylor Swift" in text
    assert "10. Track 9" in text
    assert "11. Track 10" not in text
    assert isinstance(markup, InlineKeyboardMarkup)
    buttons = markup.inline_keyboard
    assert buttons[0][0].text == "1"
    assert buttons[0][0].style == "primary"
    assert buttons[0][0].callback_data == "music:item:0"
    assert buttons[-1][-1].text == "Keyingi"
    assert buttons[-1][-1].style == "primary"
    assert buttons[-1][-1].callback_data == "music:page:1"


def test_music_results_keyboard_has_numbered_buttons_and_navigation():
    markup = music_results_keyboard(25, page=1)

    assert markup.inline_keyboard[0][0].text == "11"
    assert markup.inline_keyboard[0][0].style == "primary"
    assert markup.inline_keyboard[0][0].callback_data == "music:item:10"
    assert [button.callback_data for button in markup.inline_keyboard[-1]] == [
        "music:page:0",
        "music:page:2",
    ]


def test_start_has_clean_aewolf_greeting_and_menu():
    message = type("MessageStub", (), {"answer": AsyncMock()})()

    asyncio.run(start(message))

    text = message.answer.await_args.args[0]
    markup = message.answer.await_args.kwargs["reply_markup"]
    assert "AEwolf" in text
    assert "Instagram qidiruvi" not in text
    assert markup.inline_keyboard[0][0].callback_data == "menu:music"
    assert markup.inline_keyboard[0][1].callback_data == "menu:video"
    assert markup.inline_keyboard[0][0].style == "primary"
    assert markup.inline_keyboard[0][1].style == "success"
    assert markup.inline_keyboard[1][0].style == "danger"


def test_music_menu_callback_starts_music_mode(monkeypatch):
    message, _ = _message("")
    callback = type("CallbackStub", (), {})()
    callback.data = "menu:music"
    callback.from_user = message.from_user
    callback.message = message
    callback.answer = AsyncMock()
    set_state = AsyncMock()
    monkeypatch.setattr(callback_handlers.state, "set", set_state)

    asyncio.run(callback_handlers.menu_selected(callback))

    callback.answer.assert_awaited_once()
    set_state.assert_awaited_once_with("music:mode:123", "1", ex=600)
    message.answer.assert_awaited_once_with(
        "🎵 Qo‘shiq yoki ijrochi nomini yozing:"
    )


def test_selected_track_shows_hourglass_while_sending(monkeypatch):
    message, status = _message("")
    callback = type("CallbackStub", (), {})()
    callback.data = "music:item:0"
    callback.from_user = message.from_user
    callback.message = message
    callback.bot = message.bot
    callback.answer = AsyncMock()
    result = {
        "title": "Track",
        "artist": "Artist",
        "path": "Artist/Track.mp3",
    }
    monkeypatch.setattr(
        callback_handlers.state, "get", AsyncMock(return_value=str([result]))
    )
    track_path = Path("music_library/Artist/Track.mp3")
    resolve = Mock(return_value=track_path)
    monkeypatch.setattr(music_handler.library, "resolve_track", resolve)
    send_audio = AsyncMock()
    monkeypatch.setattr(
        music_handler.TelegramSender, "send_audio_file", send_audio
    )

    asyncio.run(callback_handlers.music_selected(callback))

    message.answer.assert_awaited_once_with("⌛")
    resolve.assert_called_once_with(result["path"])
    send_audio.assert_awaited_once_with(
        callback.bot, 123, track_path, "Track", "Artist"
    )
    status.delete.assert_awaited_once()

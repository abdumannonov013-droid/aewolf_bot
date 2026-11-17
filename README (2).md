# AEwolf Media Bot

Python Telegram media bot that extracts media links with yt-dlp and sends them through the Telegram Bot API.

## Features
- Accepts HTTP/HTTPS media links and uses yt-dlp to prefer a single-file MP4 video format; non-MP4 video fallbacks are sent as documents.
- Asks Telegram to fetch the extracted media URL directly; falls back to a streamed upload if Telegram cannot fetch it.
- Supports public media URLs recognized by yt-dlp; adaptive formats and direct-delivery failures are downloaded before upload. Private, DRM-protected, or login-required media may not be accessible.
- YouTube links first ask Telegram to fetch the extracted video URL, then stream it with yt-dlp headers if needed; local yt-dlp download is the last fallback.
- Instagram video links use direct Telegram fetching only and do not start a local download.
- Local yt-dlp downloads fetch up to eight adaptive fragments concurrently.
- `/musiqa` searches your local, rights-cleared music library; song queries send the matching file, while artist queries show up to 50 numbered, paginated results.
- `/start` includes a compact AEwolf welcome message and a navigation menu.
- In-memory rate limiting and short-lived music search state (cleared when the bot restarts).
- FastAPI health endpoint.

Delivery speed depends on the source, media size, and Telegram. Direct URL delivery avoids routing the video through this computer, but cannot guarantee a fixed delivery time.

## Run locally
1. Install Python 3.12 or newer.
2. Install the requirements: `python -m pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set `BOT_TOKEN` to your BotFather token.
4. Install FFmpeg and make sure `ffmpeg` is on `PATH` to merge adaptive streams and prepare Telegram-compatible MP4 video.
5. Start the bot: `python run_bot.py`.
6. Open the bot in Telegram and send `/start`.

Keep `BOT_API_BASE_URL` empty when using the standard Telegram Bot API. Optional local Bot API server support is available by setting it to that server's URL.

## Music
Put audio you own or are licensed to distribute in the `music_library` directory, then send `/musiqa` and enter a song or artist name. Name files `Artist - Song.mp3` or organize them as `Artist/Song.mp3`. The bot shows `⌛` while searching or sending audio. Song queries send a matching file; artist queries show up to 50 numbered results across pages. Choose a number to send the full file. MP3/M4A tracks are sent as Telegram audio; other supported audio formats are sent as files. Set `MUSIC_LIBRARY_PATH` to use another directory.

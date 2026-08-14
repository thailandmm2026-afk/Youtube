# ============================================================
# YouTube Video / Audio Downloader Bot
# Built with Pyrogram | Style matched to @UseMasterUpdate
# ============================================================

import os
import re
import time
import asyncio
import logging
import subprocess
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from pyrogram.errors import FloodWait
import yt_dlp

# ──────────────────────────────────────────────
# Bot Configuration
# ──────────────────────────────────────────────
API_ID    = int(os.environ.get("API_ID", 31606811))
API_HASH  = os.environ.get("API_HASH", "36e6d64e83ee00422c8ba535a60eaa99")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8346296445:AAHalUn11qqIr5j29h3EZTVUmxK-AvyBDqw")

OUTPUT_FOLDER = "downloads"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

CREDIT = "@KMM_MOD1"          # ပြောင်းချင်ရင် ဒီမှာ ပြောင်းပါ
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "20000"))  # 2GB

# Cookies for YouTube bot-check bypass
# Priority: COOKIES_FILE path → cookies.txt in /app → COOKIES_BASE64 env
COOKIES_FILE = os.environ.get("COOKIES_FILE", "").strip()
COOKIES_BASE64 = os.environ.get("COOKIES_BASE64", "").strip()

def get_cookies_path() -> str | None:
    """Return path to a valid cookies.txt, or None."""
    # 1) Explicit path from env
    if COOKIES_FILE and os.path.isfile(COOKIES_FILE):
        return COOKIES_FILE
    # 2) Default file locations
    for candidate in ("cookies.txt", "/app/cookies.txt", "/tmp/cookies.txt"):
        if os.path.isfile(candidate):
            return candidate
    # 3) Base64-encoded content from env (Railway-friendly)
    if COOKIES_BASE64:
        try:
            import base64
            data = base64.b64decode(COOKIES_BASE64)
            out = "/tmp/cookies.txt"
            with open(out, "wb") as f:
                f.write(data)
            return out
        except Exception as e:
            logger.warning(f"Failed to decode COOKIES_BASE64: {e}")
    return None

def base_ydl_opts() -> dict:
    """Common yt-dlp options including cookies + anti-bot clients."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 5,
        "extractor_retries": 5,
        "socket_timeout": 30,
        # Prefer mobile / TV clients — often bypasses "Sign in to confirm you're not a bot"
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "tv", "web"],
            }
        },
    }
    cookies = get_cookies_path()
    if cookies:
        opts["cookiefile"] = cookies
        logger.info(f"Using cookies: {cookies}")
    else:
        logger.warning(
            "No cookies.txt found. YouTube may block downloads. "
            "Set COOKIES_BASE64 or add cookies.txt"
        )
    return opts

# ──────────────────────────────────────────────
# Pyrogram Client
# ──────────────────────────────────────────────
app = Client(
    "yt_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workdir="/tmp",          # Railway-friendly (ephemeral FS)
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────
def human_size(num: float) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024:
            return f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} TB"


def progress_bar(current: int, total: int, width: int = 10) -> str:
    if total == 0:
        return "░" * width
    filled = int(width * current / total)
    return f"[{'█' * filled}{'░' * (width - filled)}] {current / total * 100:.1f}%"


_last_edit: dict[int, float] = {}


async def safe_edit(msg: Message, text: str, min_interval: float = 2.5) -> None:
    now = time.time()
    if now - _last_edit.get(msg.id, 0) < min_interval:
        return
    _last_edit[msg.id] = now
    try:
        await msg.edit_text(text)
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        pass


def sanitize_filename(title: str) -> str:
    safe = re.sub(r"[^\w\s\-_.]", "", title)
    safe = re.sub(r"\s+", "_", safe).strip("._-")
    return safe[:80] or "video"


def format_duration(seconds: int | float | None) -> str:
    if not seconds:
        return "Unknown"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


# ──────────────────────────────────────────────
# YouTube URL detector
# ──────────────────────────────────────────────
YT_PATTERN = re.compile(
    r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+",
    re.IGNORECASE,
)


def extract_yt_url(text: str) -> str | None:
    m = YT_PATTERN.search(text)
    return m.group(0) if m else None


# ──────────────────────────────────────────────
# yt-dlp helpers
# ──────────────────────────────────────────────
def get_video_info(url: str) -> dict:
    """Extract title, duration, thumbnail without downloading."""
    ydl_opts = {
        **base_ydl_opts(),
        "extract_flat": False,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "title": info.get("title", "Unknown"),
        "duration": info.get("duration") or 0,
        "thumbnail": info.get("thumbnail", ""),
        "id": info.get("id", "video"),
    }


async def download_yt(
    url: str,
    choice: str,          # "video" or "audio"
    status_msg: Message,
    title: str,
) -> str | None:
    """
    Download with yt-dlp + live progress (Railway-safe).
    Returns final file path or None on failure.
    """
    safe_title = sanitize_filename(title)
    base = os.path.join(OUTPUT_FOLDER, safe_title)

    common = {
        **base_ydl_opts(),
        "concurrent_fragment_downloads": 16,
        "http_chunk_size": 10 * 1024 * 1024,
    }

    if choice == "video":
        outtmpl = f"{base}.%(ext)s"
        ydl_opts = {
            **common,
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
        }
        expected_ext = "mp4"
    else:
        outtmpl = f"{base}.%(ext)s"
        ydl_opts = {
            **common,
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }
        expected_ext = "mp3"

    # Shared state between yt-dlp thread and async updater
    progress_state = {"text": None, "done": False, "error": None}

    def progress_hook(d: dict):
        if d["status"] == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0
            bar = progress_bar(downloaded, total)
            size_str = (
                f"{human_size(downloaded)} / {human_size(total)}"
                if total else human_size(downloaded)
            )
            speed_str = f"{human_size(speed)}/s" if speed else "—"
            eta_str = f"{eta}s" if eta else "—"
            progress_state["text"] = (
                f"📥 **Downloading ({'Video' if choice == 'video' else 'Audio'})**\n"
                f"{bar}\n"
                f"`{size_str}`\n"
                f"⚡ {speed_str} | ⏱ ETA: {eta_str}\n\n"
                f"— {CREDIT}"
            )
        elif d["status"] == "finished":
            progress_state["text"] = f"✅ Download ပြီးပါပြီ။ Processing...\n\n— {CREDIT}"

    ydl_opts["progress_hooks"] = [progress_hook]

    def _run_download():
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            progress_state["error"] = str(e)
        finally:
            progress_state["done"] = True

    # Start download in thread + poll progress from async side
    loop = asyncio.get_running_loop()
    fut = loop.run_in_executor(None, _run_download)

    last_text = None
    while not progress_state["done"]:
        text = progress_state["text"]
        if text and text != last_text:
            await safe_edit(status_msg, text)
            last_text = text
        await asyncio.sleep(2.5)

    await fut  # ensure thread finished

    if progress_state["error"]:
        await safe_edit(
            status_msg,
            f"❌ Download မအောင်မြင်ပါ:\n`{progress_state['error']}`\n\n— {CREDIT}",
        )
        return None

    # Locate the output file
    final_path = f"{base}.{expected_ext}"
    if not os.path.exists(final_path):
        for f in os.listdir(OUTPUT_FOLDER):
            if f.startswith(safe_title):
                final_path = os.path.join(OUTPUT_FOLDER, f)
                break

    if not os.path.exists(final_path):
        await safe_edit(status_msg, f"❌ ဖိုင် မတွေ့ပါ။\n\n— {CREDIT}")
        return None

    return final_path


def get_video_metadata(video_path: str) -> tuple[int, int, int]:
    """Returns (duration_secs, width, height)."""
    try:
        dur = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        duration = int(float(dur.stdout.strip() or "0"))
    except Exception:
        duration = 0

    try:
        res = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                video_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        w, h = map(int, (res.stdout.strip() or "0x0").split("x"))
    except Exception:
        w, h = 0, 0

    return duration, w, h


def extract_thumbnail(video_path: str, thumb_path: str) -> bool:
    try:
        duration, _, _ = get_video_metadata(video_path)
        seek = max(1, duration * 0.3) if duration else 5
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-ss", str(seek), "-i", video_path,
                "-vframes", "1", "-vf", "scale=320:-1", "-y", thumb_path,
            ],
            timeout=30, check=True,
        )
        return os.path.exists(thumb_path)
    except Exception:
        return False


# ──────────────────────────────────────────────
# /start  &  /help
# ──────────────────────────────────────────────
@app.on_message(filters.command("start") & filters.private)
async def start_handler(_, message: Message):
    await message.reply_text(
        "🎬 **YouTube Downloader Bot**\n\n"
        "YouTube လင့်ခ်ကို ပို့ပေးပါ။\n"
        "Video (MP4) သို့မဟုတ် Audio (MP3) ရွေးနိုင်ပါတယ်။\n\n"
        "ဥပမာ:\n`https://youtube.com/watch?v=xxxxx`\n\n"
        f"— {CREDIT}"
    )


@app.on_message(filters.command("help") & filters.private)
async def help_handler(_, message: Message):
    await message.reply_text(
        "📖 **အသုံးပြုနည်း**\n\n"
        "1️⃣ YouTube လင့်ခ်ကို ကူးယူပါ\n"
        "2️⃣ Bot ကို ပို့ပါ\n"
        "3️⃣ **Video** သို့မဟုတ် **Audio** ရွေးပါ\n"
        "4️⃣ ဒေါင်းလုဒ်ပြီးရင် ဖိုင် ရရှိပါမယ်\n\n"
        "📌 /start — Bot စတင်ရန်\n"
        "📌 /help — အကူအညီ\n\n"
        f"— {CREDIT}"
    )


# ──────────────────────────────────────────────
# Handle YouTube URL
# ──────────────────────────────────────────────
@app.on_message(filters.text & filters.private & ~filters.command(["start", "help"]))
async def url_handler(_, message: Message):
    url = extract_yt_url(message.text or "")
    if not url:
        await message.reply_text(
            f"❌ YouTube လင့်ခ်တစ်ခုတည်းသာ လက်ခံပါတယ်။\n\n— {CREDIT}"
        )
        return

    status = await message.reply_text(
        f"⏳ ဗီဒီယိုအချက်အလက်များ ရယူနေပါသည်...\n\n— {CREDIT}"
    )

    try:
        info = await asyncio.to_thread(get_video_info, url)
    except Exception as e:
        await safe_edit(
            status,
            f"❌ အချက်အလက် မရယူနိုင်ပါ:\n`{e}`\n\n— {CREDIT}",
        )
        return

    title = info["title"]
    duration = format_duration(info["duration"])

    # Store for callback (in-memory)
    if not hasattr(app, "yt_cache"):
        app.yt_cache = {}
    app.yt_cache[message.from_user.id] = {
        "url": url,
        "title": title,
    }

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎥 Video (MP4)", callback_data="yt_video"),
                InlineKeyboardButton("🎵 Audio (MP3)", callback_data="yt_audio"),
            ]
        ]
    )

    await status.edit_text(
        f"📹 **{title}**\n\n"
        f"⏱ Duration: `{duration}`\n\n"
        f"အောက်ပါတွင် ရွေးချယ်ပါ 👇\n\n"
        f"— {CREDIT}",
        reply_markup=keyboard,
    )


# ──────────────────────────────────────────────
# Callback: Video / Audio choice
# ──────────────────────────────────────────────
@app.on_callback_query(filters.regex(r"^yt_(video|audio)$"))
async def choice_callback(_, query: CallbackQuery):
    await query.answer()

    choice = "video" if query.data == "yt_video" else "audio"
    user_id = query.from_user.id

    cache = getattr(app, "yt_cache", {})
    data = cache.get(user_id)
    if not data:
        await query.message.edit_text(
            f"❌ URL မတွေ့ပါ။ လင့်ခ်ကို ပြန်ပို့ပေးပါ။\n\n— {CREDIT}"
        )
        return

    url = data["url"]
    title = data["title"]

    await query.message.edit_text(
        f"⏳ ဒေါင်းလုဒ် စတင်နေပါသည်... ({'Video' if choice == 'video' else 'Audio'})\n"
        f"နာရီကျော် ဗီဒီယိုများ ဖြစ်ပါက အချိန်အနည်းငယ် စောင့်ပါ...\n\n"
        f"— {CREDIT}"
    )

    # Download
    final_path = await download_yt(url, choice, query.message, title)
    if not final_path:
        return

    file_size = os.path.getsize(final_path)
    file_size_mb = file_size / (1024 * 1024)

    if file_size_mb > MAX_FILE_SIZE_MB:
        await safe_edit(
            query.message,
            f"⚠️ ဖိုင်အရွယ်အစား ကြီးလွန်းနေပါသည် ({file_size_mb:.1f} MB)\n"
            f"Limit: {MAX_FILE_SIZE_MB} MB\n\n— {CREDIT}",
        )
        try:
            os.remove(final_path)
        except OSError:
            pass
        return

    # Upload progress
    async def upload_progress(current: int, total: int):
        bar = progress_bar(current, total)
        await safe_edit(
            query.message,
            f"📤 **Uploading to Telegram**\n"
            f"{bar}\n"
            f"`{human_size(current)} / {human_size(total)}`\n\n"
            f"— {CREDIT}",
        )

    try:
        caption = f"✅ **{title}**\n📦 {human_size(file_size)}\n\n— {CREDIT}"

        if choice == "video":
            duration, width, height = get_video_metadata(final_path)
            thumb_path = final_path + ".jpg"
            has_thumb = extract_thumbnail(final_path, thumb_path)

            # Large files → document is more reliable
            if file_size_mb > 100:
                await query.message.reply_document(
                    document=final_path,
                    caption=caption,
                    file_name=os.path.basename(final_path),
                    progress=upload_progress,
                )
            else:
                await query.message.reply_video(
                    video=final_path,
                    caption=caption,
                    duration=duration,
                    width=width or None,
                    height=height or None,
                    thumb=thumb_path if has_thumb else None,
                    supports_streaming=True,
                    progress=upload_progress,
                )

            if has_thumb and os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except OSError:
                    pass
        else:
            await query.message.reply_audio(
                audio=final_path,
                caption=caption,
                title=title,
                performer="YouTube",
                progress=upload_progress,
            )

        await safe_edit(
            query.message,
            f"✅ ဒေါင်းလုဒ် + ပို့ပြီးပါပြီ။\n\n— {CREDIT}",
        )

    except Exception as e:
        logger.exception("Upload error")
        await safe_edit(
            query.message,
            f"❌ ပို့ရာတွင် အမှားဖြစ်သွားပါပြီ:\n`{e}`\n\n— {CREDIT}",
        )
    finally:
        try:
            os.remove(final_path)
        except OSError:
            pass
        cache.pop(user_id, None)


# ──────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────
if __name__ == "__main__":
    if not all([API_ID, API_HASH, BOT_TOKEN]):
        raise SystemExit(
            "API_ID, API_HASH and BOT_TOKEN must be set in environment variables!"
        )
    logger.info("Bot is starting...")
    app.run()

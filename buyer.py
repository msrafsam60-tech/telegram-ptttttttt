from __future__ import annotations

import html
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiosqlite
from telegram import (
    ChatMemberAdministrator,
    ChatMemberOwner,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BOT_TOKEN = "8911633648:AAHqm_jr0Enb0Q4f4Wr0Ex2nqb1XLNGt7gQ"

if not BOT_TOKEN or BOT_TOKEN == "8911633648:AAHqm_jr0Enb0Q4f4Wr0Ex2nqb1XLNGt7gQ":
    BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

DB_FILE = os.getenv("DB_FILE", "bot_data.db")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("PostMakerBot")


# ---------------------------------------------------------------------------
# Button Builder — supports style= gracefully
# ---------------------------------------------------------------------------
def btn(
    text: str,
    callback_data: Optional[str] = None,
    url: Optional[str] = None,
    style: Optional[str] = None,
) -> InlineKeyboardButton:
    """
    কালার স্টাইল সহ InlineKeyboardButton তৈরি করে।
    style হতে পারে 'primary' | 'success' | 'danger'।
    PTB ভার্সনে সাপোর্ট না থাকলে স্বয়ংক্রিয়ভাবে সাধারণ বাটনে রূপান্তর হবে।
    """
    kwargs: Dict[str, Any] = {"text": text}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url

    if style:
        try:
            return InlineKeyboardButton(**kwargs, style=style)
        except TypeError:
            pass
    return InlineKeyboardButton(**kwargs)


COLOR_EMOJI = {"primary": "🔵", "success": "🟢", "danger": "🔴"}
COLOR_NAME_BN = {"primary": "প্রাইমারি (নীল)", "success": "সাকসেস (সবুজ)", "danger": "ডেঞ্জার (লাল)"}


# ---------------------------------------------------------------------------
# Message tracking helper — used for clean cancel
# ---------------------------------------------------------------------------
def track_msg(context: ContextTypes.DEFAULT_TYPE, message_id: Optional[int]) -> None:
    """মেসেজ আইডি ট্র্যাক করে রাখে যাতে বাতিল বা পাবলিশের সময় মুছে ফেলা যায়।"""
    if not message_id:
        return
    lst = context.user_data.setdefault("_trash", [])
    if message_id not in lst:
        lst.append(message_id)


async def send_tracked(target, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    """মেসেজ পাঠায় এবং ডিলিটের জন্য স্বয়ংক্রিয়ভাবে ট্র্যাক করে রাখে।"""
    sent = await target.reply_text(text, **kwargs)
    track_msg(context, sent.message_id)
    return sent


async def purge_trash(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """ট্র্যাক করা প্রতিটি সাময়িক মেসেজ ডিলিট করে চ্যাট পরিষ্কার করে।"""
    ids = context.user_data.get("_trash", [])
    for mid in ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except TelegramError:
            pass
    context.user_data.pop("_trash", None)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
async def init_db() -> None:
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                channel_title TEXT NOT NULL,
                chat_type TEXT NOT NULL DEFAULT 'channel',
                created_at TEXT NOT NULL,
                UNIQUE(user_id, channel_id)
            );
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                channel_title TEXT NOT NULL,
                post_type TEXT NOT NULL,
                content_preview TEXT NOT NULL,
                published_at TEXT NOT NULL,
                telegram_message_id INTEGER NOT NULL
            );
            """
        )
        async with db.execute("PRAGMA table_info(channels);") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]
            if "chat_type" not in columns:
                await db.execute(
                    "ALTER TABLE channels ADD COLUMN chat_type TEXT NOT NULL DEFAULT 'channel';"
                )
        await db.commit()


async def save_channel(user_id: int, channel_id: int, title: str, chat_type: str) -> None:
    async with aiosqlite.connect(DB_FILE) as db:
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """
            INSERT INTO channels (user_id, channel_id, channel_title, chat_type, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, channel_id) DO UPDATE SET
                channel_title = excluded.channel_title,
                chat_type = excluded.chat_type;
            """,
            (user_id, channel_id, title, chat_type, now),
        )
        await db.commit()


async def delete_channel(user_id: int, channel_id: int) -> None:
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "DELETE FROM channels WHERE user_id = ? AND channel_id = ?",
            (user_id, channel_id),
        )
        await db.commit()


async def get_user_channels(user_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT channel_id, channel_title, chat_type FROM channels WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


async def get_user_channel(user_id: int, channel_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT channel_id, channel_title, chat_type FROM channels WHERE user_id = ? AND channel_id = ?",
            (user_id, channel_id),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def save_published_post(
    user_id: int,
    channel_id: int,
    channel_title: str,
    post_type: str,
    content_preview: str,
    telegram_message_id: int,
) -> None:
    async with aiosqlite.connect(DB_FILE) as db:
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """
            INSERT INTO posts (user_id, channel_id, channel_title, post_type, content_preview, published_at, telegram_message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, channel_id, channel_title, post_type, content_preview[:120], now, telegram_message_id),
        )
        await db.commit()


async def get_user_posts(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT channel_title, post_type, content_preview, published_at, telegram_message_id
            FROM posts WHERE user_id = ? ORDER BY id DESC LIMIT ?
            """,
            (user_id, limit),
        ) as cursor:
            return [dict(r) for r in await cursor.fetchall()]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def is_valid_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ("http", "https", "tg"):
        return False
    if parsed.scheme.lower() in ("http", "https") and not parsed.netloc:
        return False
    return True


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------
(
    STATE_SET_CHANNEL,
    STATE_SELECT_CHANNEL,
    STATE_SELECT_TYPE,
    STATE_ENTER_CONTENT,
    STATE_ENTER_CAPTION,
    STATE_ADD_BUTTONS,
    STATE_SELECT_BUTTON_COLOR,
    STATE_CONFIRM_PUBLISH,
) = range(8)


# ---------------------------------------------------------------------------
# Keyboards — completely in Bengali
# ---------------------------------------------------------------------------
def kb_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [btn("⚙️ টার্গেট সেট করুন", callback_data="menu_set_channel", style="primary"),
         btn("📝 পোস্ট তৈরি করুন", callback_data="menu_create_post", style="success")],
        [btn("📋 আমার টার্গেটসমূহ", callback_data="menu_my_channels", style="primary"),
         btn("📚 পোস্ট হিস্ট্রি", callback_data="menu_my_posts", style="primary")],
        [btn("❓ সাহায্য ও গাইড", callback_data="menu_help", style="primary")],
    ])


def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [btn("❌ বাতিল করুন", callback_data="cancel_action", style="danger")]
    ])


def kb_skip_cancel(skip_cb: str, skip_label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [btn(skip_label, callback_data=skip_cb, style="primary")],
        [btn("❌ বাতিল করুন", callback_data="cancel_action", style="danger")],
    ])


def build_post_markup(buttons: List[List[Dict[str, str]]]) -> Optional[InlineKeyboardMarkup]:
    if not buttons:
        return None
    keyboard = []
    for row in buttons:
        btn_row = [btn(text=b["text"], url=b["url"], style=b.get("style")) for b in row]
        if btn_row:
            keyboard.append(btn_row)
    return InlineKeyboardMarkup(keyboard) if keyboard else None


# ---------------------------------------------------------------------------
# Permission checks
# ---------------------------------------------------------------------------
async def check_bot_posting_permission(bot, target_id: int) -> tuple[bool, str]:
    try:
        member = await bot.get_chat_member(chat_id=target_id, user_id=bot.id)
        if isinstance(member, ChatMemberOwner):
            return True, "মালিক (Owner)"
        if isinstance(member, ChatMemberAdministrator):
            can_post = getattr(member, "can_post_messages", None)
            if can_post is False:
                return False, "বট অ্যাডমিন কিন্তু 'Post Messages' পারমিশন দেওয়া নেই।"
            return True, "অ্যাডমিনিস্ট্রেটর (Admin)"
        return False, "বট এই চ্যানেল বা গ্রুপের অ্যাডমিনিস্ট্রেটর নয়।"
    except BadRequest as e:
        if "chat not found" in e.message.lower():
            return False, "বট এই চ্যাটে যুক্ত নেই। প্রথমে বটকে সেখানে অ্যাডমিন বানান!"
        return False, f"টেলিগ্রাম এরর: {e.message}"
    except TelegramError as e:
        return False, f"টেলিগ্রাম এপিআই এরর: {e.message}"
    except Exception as e:
        logger.error("Error checking bot permission: %s", e)
        return False, "যাচাইকরণ ব্যর্থ হয়েছে। আইডি সঠিক কি না নিশ্চিত করুন।"


async def verify_user_channel_ownership(bot, target_id: int, user_id: int) -> tuple[bool, str]:
    try:
        user_member = await bot.get_chat_member(chat_id=target_id, user_id=user_id)
        if isinstance(user_member, ChatMemberOwner):
            return True, "মালিক (Owner)"
        if isinstance(user_member, ChatMemberAdministrator):
            return True, "অ্যাডমিনিস্ট্রেটর (Admin)"
        return False, "আপনি এই চ্যানেল বা গ্রুপের মালিক অথবা অ্যাডমিন নন।"
    except BadRequest as e:
        if "user not found" in e.message.lower() or "participant" in e.message.lower():
            return False, "আপনি এই চ্যানেল বা গ্রুপের সদস্য অথবা অ্যাডমিন নন।"
        return False, f"যাচাইকরণ ব্যর্থ হয়েছে: {e.message}"
    except Exception as e:
        logger.error("Error checking user ownership: %s", e)
        return False, "ব্যবহারকারী যাচাইকরণে ত্রুটি দেখা দিয়েছে।"


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    welcome_text = (
        "👋 <b>পোস্ট মেকার বটে স্বাগতম</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "আপনার <b>চ্যানেল</b> এবং <b>গ্রুপে</b> প্রফেশনাল পোস্ট পাবলিশ করুন —\n"
        "টেক্সট, ছবি, ভিডিও এবং রঙিন URL বাটন সহ।\n\n"
        "🔐 <b>নিরাপত্তা:</b> কেবল সেইসব টার্গেট যুক্ত করতে পারবেন যেগুলোর আপনি <b>মালিক / অ্যাডমিন</b>।\n"
        "🎨 <b>কালার:</b> প্রাইমারি · সাকসেস · ডেঞ্জার\n"
        "😀 <b>ইমোজি:</b> বাটনের টেক্সটে যেকোনো ইমোজি ব্যবহার করতে পারবেন।"
    )
    if update.message:
        await update.message.reply_text(
            welcome_text, reply_markup=kb_main_menu(), parse_mode=ParseMode.HTML
        )
    elif update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                welcome_text, reply_markup=kb_main_menu(), parse_mode=ParseMode.HTML
            )
        except BadRequest:
            await update.callback_query.message.reply_text(
                welcome_text, reply_markup=kb_main_menu(), parse_mode=ParseMode.HTML
            )
    return ConversationHandler.END


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    help_text = (
        "📖 <b>সাহায্য ও গাইডবুক</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>🔹 চ্যানেল / গ্রুপ আইডি কীভাবে বের করবেন?</b>\n"
        "১. বটকে আপনার টার্গেট চ্যানেল বা গ্রুপে <b>অ্যাডমিন</b> বানান।\n"
        "২. সেখান থেকে যেকোনো একটি পোস্ট <b>@username_to_id_bot</b>-এ ফরওয়ার্ড করুন।\n"
        "৩. আপনি একটি সংখ্যাযুক্ত আইডি পাবেন — যেমন: <code>-1001234567890</code>।\n\n"
        "<b>🔹 কীভাবে পোস্ট তৈরি করবেন?</b>\n"
        "১. <b>পোস্ট তৈরি করুন</b> চাপুন → টার্গেট সিলেক্ট করুন।\n"
        "২. ফরম্যাট নির্বাচন করুন (টেক্সট / ছবি / ভিডিও)।\n"
        "৩. কনটেন্ট ও ক্যাপশন পাঠান।\n"
        "৪. URL বাটন যুক্ত করে সেটির <b>কালার</b> বেছে নিন।\n"
        "৫. প্রিভিউ দেখে <b>🚀 পাবলিশ করুন</b> বাটনে চাপ দিন।\n\n"
        "<b>🔹 বাটন লেখার নিয়ম:</b>\n"
        "<code>লেবেল - https://link.com</code>\n"
        "এক লাইনে ২টি বাটন চাইলে: <code>প্রথম বাটন - লিংক | দ্বিতীয় বাটন - লিংক</code>\n"
        "ইমোজি ব্যবহার করতে পারেন: <code>🔥 জয়েন করুন - https://t.me/example</code>"
    )
    await query.edit_message_text(
        help_text,
        reply_markup=InlineKeyboardMarkup([
            [btn("🔙 মূল মেনুতে ফিরুন", callback_data="main_menu", style="primary")]
        ]),
        parse_mode=ParseMode.HTML,
    )


async def _render_my_channels(query, user_id: int) -> None:
    channels = await get_user_channels(user_id)

    if not channels:
        msg = (
            "📋 <b>আমার টার্গেটসমূহ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "এখনো কোনো চ্যানেল বা গ্রুপ যুক্ত করা হয়নি।\n\n"
            "👉 <b>টার্গেট সেট করুন</b> দিয়ে শুরু করুন।"
        )
        keyboard = InlineKeyboardMarkup([
            [btn("⚙️ টার্গেট সেট করুন", callback_data="menu_set_channel", style="primary")],
            [btn("🔙 মূল মেনুতে ফিরুন", callback_data="main_menu", style="primary")],
        ])
    else:
        msg = "📋 <b>আমার ভেরিফায়েড টার্গেটসমূহ</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for idx, ch in enumerate(channels, 1):
            title = html.escape(ch.get("channel_title") or "নামহীন")
            raw_type = ch.get("chat_type", "channel").lower()
            c_type = "চ্যানেল" if raw_type == "channel" else "গ্রুপ"
            icon = "📢" if raw_type == "channel" else "👥"
            msg += f"{icon} <b>{idx}. {title}</b> ({c_type})\n<code>আইডি: {ch['channel_id']}</code>\n\n"

        keyboard = InlineKeyboardMarkup([
            [btn("⚙️ নতুন যোগ করুন", callback_data="menu_set_channel", style="primary"),
             btn("🗑 রিমুভ করুন", callback_data="remove_target_menu", style="danger")],
            [btn("🔙 মূল মেনুতে ফিরুন", callback_data="main_menu", style="primary")],
        ])

    await query.edit_message_text(msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)


async def my_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await _render_my_channels(query, query.from_user.id)


async def remove_target_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    channels = await get_user_channels(query.from_user.id)

    if not channels:
        await query.answer("রিমুভ করার মতো কোনো টার্গেট নেই।", show_alert=True)
        return
    await query.answer()

    keyboard = []
    for ch in channels:
        raw_type = ch.get("chat_type", "channel").lower()
        icon = "📢" if raw_type == "channel" else "👥"
        keyboard.append([
            btn(f"🗑 {icon} {ch['channel_title']}",
                callback_data=f"del_chan_{ch['channel_id']}",
                style="danger")
        ])
    keyboard.append([btn("🔙 পেছনে যান", callback_data="menu_my_channels", style="primary")])

    await query.edit_message_text(
        "🗑 <b>টার্গেট রিমুভ করুন</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "যে টার্গেটটি তালিকা থেকে বাদ দিতে চান, সেটির ওপর চাপুন:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )


async def delete_channel_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    try:
        channel_id = int(query.data.split("_")[2])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ নির্বাচন সঠিক নয়।", reply_markup=kb_main_menu())
        return

    channel = await get_user_channel(query.from_user.id, channel_id)
    if not channel:
        await query.answer("টার্গেট খুঁজে পাওয়া যায়নি।", show_alert=True)
        return

    raw_type = channel.get("chat_type", "channel").lower()
    icon = "📢" if raw_type == "channel" else "👥"
    keyboard = InlineKeyboardMarkup([
        [btn("✅ হ্যাঁ, রিমুভ করুন", callback_data=f"confirm_del_{channel_id}", style="danger")],
        [btn("🔙 বাতিল", callback_data="menu_my_channels", style="primary")],
    ])

    await query.edit_message_text(
        "⚠️ <b>টার্গেট মুছে ফেলার নিশ্চয়তা</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{icon} <b>{html.escape(channel['channel_title'])}</b>\n"
        f"🆔 <code>{channel['channel_id']}</code>\n\n"
        "আপনি কি নিশ্চিত যে এই টার্গেটটি তালিকা থেকে মুছে ফেলতে চান?",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )


async def confirm_delete_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    try:
        channel_id = int(query.data.split("_")[2])
    except (IndexError, ValueError):
        await query.answer("ত্রুটিপূর্ণ অনুরোধ।", show_alert=True)
        return

    await delete_channel(query.from_user.id, channel_id)
    await query.answer("✅ টার্গেট রিমুভ করা হয়েছে।", show_alert=False)
    await _render_my_channels(query, query.from_user.id)


async def my_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    posts = await get_user_posts(query.from_user.id, limit=10)

    if not posts:
        msg = (
            "📚 <b>পোস্ট হিস্ট্রি</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "এখনো পর্যন্ত কোনো পোস্ট পাবলিশ করা হয়নি।"
        )
    else:
        msg = "📚 <b>সর্বশেষ ১০টি পাবলিশ করা পোস্ট</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for idx, post in enumerate(posts, 1):
            ch_title = html.escape(post.get("channel_title") or "টার্গেট")
            raw_ptype = post.get("post_type", "").lower()
            p_type_map = {"text": "টেক্সট", "photo": "ছবি", "video": "ভিডিও"}
            p_type = p_type_map.get(raw_ptype, raw_ptype.capitalize())
            preview = html.escape(post.get("content_preview") or "")
            pub_date = post.get("published_at", "")[:16].replace("T", " ")
            msg += (
                f"<b>{idx}. [{p_type}]</b> → {ch_title}\n"
                f"🗓 <code>{pub_date} UTC</code>\n"
                f"💬 <i>{preview}</i>\n\n"
            )

    await query.edit_message_text(
        msg,
        reply_markup=InlineKeyboardMarkup([
            [btn("🔙 মূল মেনুতে ফিরুন", callback_data="main_menu", style="primary")]
        ]),
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# Flow 1: Set Target
# ---------------------------------------------------------------------------
async def set_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    msg = (
        "⚙️ <b>টার্গেট সেট করুন — চ্যানেল / গ্রুপ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>নির্দেশনা:</b>\n"
        "1️⃣ প্রথমে বটকে আপনার কাঙ্ক্ষিত চ্যানেল বা গ্রুপে <b>অ্যাডমিনিস্ট্রেটর</b> বানান।\n"
        "2️⃣ সেই চ্যানেল বা গ্রুপের সংখ্যাযুক্ত আইডিটি (Numeric ID) কপি করুন।\n"
        "3️⃣ নিচে পেস্ট করে মেসেজ পাঠিয়ে দিন।\n\n"
        "📌 <b>ফরম্যাট উদাহরণ:</b> <code>-1001234567890</code>"
    )
    await query.edit_message_text(msg, reply_markup=kb_cancel(), parse_mode=ParseMode.HTML)
    return STATE_SET_CHANNEL


async def set_channel_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    track_msg(context, update.message.message_id)
    user_id = update.effective_user.id
    text_val = (update.message.text or "").strip()

    if text_val.startswith("@") or not (text_val.startswith("-") or text_val.isdigit()):
        await send_tracked(
            update.message, context,
            "❌ <b>ভুল ফরম্যাট!</b>\n\n"
            "শুধুমাত্র সংখ্যাযুক্ত চ্যাট আইডি পাঠান — যেমন <code>-1001234567890</code>।",
            reply_markup=kb_cancel(), parse_mode=ParseMode.HTML,
        )
        return STATE_SET_CHANNEL

    try:
        target_id = int(text_val)
    except ValueError:
        await send_tracked(
            update.message, context,
            "❌ সঠিক সংখ্যাযুক্ত আইডি প্রদান করুন।",
            reply_markup=kb_cancel(),
        )
        return STATE_SET_CHANNEL

    try:
        chat = await context.bot.get_chat(target_id)
    except BadRequest as e:
        await send_tracked(
            update.message, context,
            f"❌ <b>চ্যাট খুঁজে পাওয়া যায়নি!</b>\n\n{html.escape(e.message)}\n\n"
            "নিশ্চিত করুন যে বটটি সেই চ্যানেল বা গ্রুপে <b>অ্যাডমিন</b> হিসেবে রয়েছে।",
            reply_markup=kb_cancel(), parse_mode=ParseMode.HTML,
        )
        return STATE_SET_CHANNEL

    if chat.type not in ("channel", "supergroup", "group"):
        await send_tracked(
            update.message, context,
            f"❌ এটি একটি <b>{chat.type}</b>। এখানে শুধু চ্যানেল ও গ্রুপ সাপোর্ট করবে।",
            reply_markup=kb_cancel(), parse_mode=ParseMode.HTML,
        )
        return STATE_SET_CHANNEL

    bot_ok, bot_reason = await check_bot_posting_permission(context.bot, target_id)
    if not bot_ok:
        await send_tracked(
            update.message, context,
            f"❌ <b>বটের পারমিশন সংক্রান্ত সমস্যা:</b>\n\n{html.escape(bot_reason)}\n\n"
            "বটকে অ্যাডমিন বানিয়ে <b>Post Messages</b> পারমিশনটি অন করে দিন।",
            reply_markup=kb_cancel(), parse_mode=ParseMode.HTML,
        )
        return STATE_SET_CHANNEL

    user_ok, user_reason = await verify_user_channel_ownership(context.bot, target_id, user_id)
    if not user_ok:
        await send_tracked(
            update.message, context,
            f"⛔ <b>অনুমতি প্রত্যাখ্যাত (Access Denied)!</b>\n\n{html.escape(user_reason)}\n\n"
            "আপনি কেবলমাত্র আপনার নিজের চ্যানেল বা গ্রুপ এখানে যোগ করতে পারবেন।",
            reply_markup=kb_cancel(), parse_mode=ParseMode.HTML,
        )
        return STATE_SET_CHANNEL

    chat_type_str = "Group" if chat.type in ("group", "supergroup") else "Channel"
    await save_channel(user_id, target_id, chat.title or chat_type_str, chat_type_str)

    # Clean up the conversation
    await purge_trash(context, update.effective_chat.id)

    icon = "📢" if chat_type_str == "Channel" else "👥"
    type_bn = "চ্যানেল" if chat_type_str == "Channel" else "গ্রুপ"
    await update.message.reply_text(
        f"✅ <b>টার্গেট সফলভাবে যুক্ত হয়েছে!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{icon} <b>{html.escape(chat.title or 'নামহীন')}</b> ({type_bn})\n"
        f"🆔 <code>{target_id}</code>\n"
        f"👤 <b>আপনার পদমর্যাদা:</b> {user_reason}\n\n"
        "এখন আপনি এই টার্গেটে পোস্ট পাবলিশ করতে পারবেন!",
        reply_markup=kb_main_menu(),
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Flow 2: Create Post
# ---------------------------------------------------------------------------
async def create_post_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    channels = await get_user_channels(query.from_user.id)

    if not channels:
        await query.edit_message_text(
            "⚠️ <b>কোনো টার্গেট যুক্ত নেই!</b>\n\n"
            "পোস্ট তৈরি করার আগে একটি চ্যানেল বা গ্রুপ যুক্ত করুন।",
            reply_markup=InlineKeyboardMarkup([
                [btn("⚙️ টার্গেট সেট করুন", callback_data="menu_set_channel", style="primary")],
                [btn("🔙 মূল মেনু", callback_data="main_menu", style="primary")],
            ]),
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    keyboard = []
    for ch in channels:
        raw_type = ch.get("chat_type", "channel").lower()
        icon = "📢" if raw_type == "channel" else "👥"
        keyboard.append([
            btn(f"{icon} {ch['channel_title']}",
                callback_data=f"sel_chan_{ch['channel_id']}",
                style="primary")
        ])
    keyboard.append([btn("❌ বাতিল করুন", callback_data="cancel_action", style="danger")])

    await query.edit_message_text(
        "📝 <b>পোস্ট তৈরি করুন — ১/৬</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "কোন চ্যানেল বা গ্রুপে পোস্ট করতে চান?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return STATE_SELECT_CHANNEL


async def select_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    try:
        channel_id = int(data.split("_")[2])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ নির্বাচন সঠিক নয়।", reply_markup=kb_main_menu())
        return ConversationHandler.END

    channel = await get_user_channel(query.from_user.id, channel_id)
    if not channel:
        await query.edit_message_text(
            "⛔ এই টার্গেটটি আপনার অ্যাকাউন্টের সাথে যুক্ত নেই।",
            reply_markup=kb_main_menu(),
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    context.user_data["draft"] = {
        "channel_id": channel["channel_id"],
        "channel_title": channel["channel_title"],
        "chat_type": channel.get("chat_type", "Channel"),
        "post_type": None,
        "text": None,
        "media_file_id": None,
        "caption": None,
        "buttons": [],
        "button_style": None,
    }

    keyboard = InlineKeyboardMarkup([
        [btn("📄 টেক্সট", callback_data="post_type_text", style="primary"),
         btn("🖼 ছবি", callback_data="post_type_photo", style="primary"),
         btn("🎥 ভিডিও", callback_data="post_type_video", style="primary")],
        [btn("❌ বাতিল করুন", callback_data="cancel_action", style="danger")],
    ])

    await query.edit_message_text(
        "📝 <b>পোস্ট তৈরি করুন — ২/৬</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 <b>টার্গেট:</b> {html.escape(channel['channel_title'])}\n\n"
        "পোস্টের ফরম্যাট বেছে নিন:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    return STATE_SELECT_TYPE


async def select_post_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    post_type = query.data.replace("post_type_", "")

    draft = context.user_data.get("draft")
    if not draft:
        await query.edit_message_text("❌ সেশনের মেয়াদ শেষ হয়ে গেছে।", reply_markup=kb_main_menu())
        return ConversationHandler.END

    draft["post_type"] = post_type

    prompts = {
        "text": ("📝 <b>পোস্ট তৈরি করুন — ৩/৬</b>\n"
                 "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                 "আপনার মেসেজের লেখা (Text) পাঠান।\n"
                 "<i>HTML ফরম্যাট সমর্থিত — &lt;b&gt;বোল্ড&lt;/b&gt;, &lt;i&gt;ইটালিক&lt;/i&gt;, &lt;a href='...'&gt;লিংক&lt;/a&gt;</i>"),
        "photo": ("🖼 <b>পোস্ট তৈরি করুন — ৩/৬</b>\n"
                  "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                  "ছবি আপলোড করুন।\n"
                  "<i>চাইলে ছবির সাথেই ক্যাপশন লিখে পাঠাতে পারেন।</i>"),
        "video": ("🎥 <b>পোস্ট তৈরি করুন — ৩/৬</b>\n"
                  "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                  "ভিডিও আপলোড করুন।\n"
                  "<i>চাইলে ভিডিওর সাথেই ক্যাপশন লিখে পাঠাতে পারেন।</i>"),
    }

    await query.edit_message_text(
        prompts.get(post_type, "কনটেন্ট পাঠান:"),
        reply_markup=kb_cancel(),
        parse_mode=ParseMode.HTML,
    )
    return STATE_ENTER_CONTENT


async def enter_content_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    track_msg(context, update.message.message_id)
    draft = context.user_data.get("draft")
    if not draft:
        await update.message.reply_text("❌ সেশনের মেয়াদ শেষ হয়ে গেছে।", reply_markup=kb_main_menu())
        return ConversationHandler.END

    post_type = draft["post_type"]

    if post_type == "text":
        if not update.message.text:
            await send_tracked(update.message, context, "❌ অনুগ্রহ করে টেক্সট মেসেজ পাঠান।", reply_markup=kb_cancel())
            return STATE_ENTER_CONTENT
        draft["text"] = update.message.text_html
        return await ask_button_step(update, context)

    if post_type == "photo":
        if not update.message.photo:
            await send_tracked(update.message, context, "❌ অনুগ্রহ করে একটি ছবি পাঠান।", reply_markup=kb_cancel())
            return STATE_ENTER_CONTENT
        draft["media_file_id"] = update.message.photo[-1].file_id
        if update.message.caption:
            draft["caption"] = update.message.caption_html
            return await ask_button_step(update, context)
        return await ask_caption_step(update, context)

    if post_type == "video":
        if not update.message.video:
            await send_tracked(update.message, context, "❌ অনুগ্রহ করে একটি ভিডিও পাঠান।", reply_markup=kb_cancel())
            return STATE_ENTER_CONTENT
        draft["media_file_id"] = update.message.video.file_id
        if update.message.caption:
            draft["caption"] = update.message.caption_html
            return await ask_button_step(update, context)
        return await ask_caption_step(update, context)

    return ConversationHandler.END


async def ask_caption_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await send_tracked(
        update.message, context,
        "📝 <b>পোস্ট তৈরি করুন — ৪/৬</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "ক্যাপশন যুক্ত করতে চান?\n"
        "ক্যাপশনের লেখা পাঠান অথবা <b>ক্যাপশন স্কিপ করুন</b> চাপুন।",
        reply_markup=kb_skip_cancel("skip_caption", "⏭ ক্যাপশন স্কিপ করুন"),
        parse_mode=ParseMode.HTML,
    )
    return STATE_ENTER_CAPTION


async def enter_caption_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    track_msg(context, update.message.message_id)
    draft = context.user_data.get("draft")
    if not draft:
        await update.message.reply_text("❌ সেশনের মেয়াদ শেষ হয়ে গেছে।", reply_markup=kb_main_menu())
        return ConversationHandler.END

    if update.message.text:
        draft["caption"] = update.message.text_html

    return await ask_button_step(update, context)


async def skip_caption_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    draft = context.user_data.get("draft")
    if not draft:
        await query.edit_message_text("❌ সেশনের মেয়াদ শেষ হয়ে গেছে।", reply_markup=kb_main_menu())
        return ConversationHandler.END
    draft["caption"] = None
    return await ask_button_step(query, context, is_query=True)


async def ask_button_step(source: Any, context: ContextTypes.DEFAULT_TYPE, is_query: bool = False) -> int:
    msg = (
        "🔗 <b>পোস্ট তৈরি করুন — ৫/৬</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>URL বাটন (ঐচ্ছিক)</b>\n\n"
        "ফরম্যাট: <code>লেবেল - https://link.com</code>\n\n"
        "<b>উদাহরণ:</b>\n"
        "• ১টি বাটন: <code>ওয়েবসাইট - https://example.com</code>\n"
        "• ইমোজি সহ: <code>🔥 জয়েন করুন - https://t.me/example</code>\n"
        "• ১ লাইনে ২টি বাটন: <code>সাইট - https://a.com | গ্রুপ - https://t.me/b</code>\n\n"
        "বাটন না লাগলে <b>বাটন স্কিপ করুন</b> চাপুন।"
    )
    keyboard = kb_skip_cancel("skip_buttons", "⏭ বাটন স্কিপ করুন")

    if is_query:
        await source.edit_message_text(msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    else:
        await send_tracked(source.message, context, msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    return STATE_ADD_BUTTONS


async def add_buttons_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    track_msg(context, update.message.message_id)
    draft = context.user_data.get("draft")
    if not draft:
        await update.message.reply_text("❌ সেশনের মেয়াদ শেষ হয়ে গেছে।", reply_markup=kb_main_menu())
        return ConversationHandler.END

    text = update.message.text or ""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    rows: List[List[Dict[str, str]]] = []

    for line in lines:
        row_items = []
        for raw_btn in line.split("|"):
            parts = re.split(r"\s+-\s+", raw_btn.strip(), maxsplit=1)
            if len(parts) != 2:
                await send_tracked(
                    update.message, context,
                    f"❌ <b>বাটনের ফরম্যাট ভুল হয়েছে!</b>\n\n"
                    f"সঠিক নিয়ম: <code>লেবেল - https://link.com</code>\n"
                    f"আপনি দিয়েছেন: <code>{html.escape(raw_btn.strip())}</code>",
                    parse_mode=ParseMode.HTML,
                )
                return STATE_ADD_BUTTONS

            btn_label = parts[0].strip()
            btn_url = parts[1].strip()

            if not is_valid_url(btn_url):
                await send_tracked(
                    update.message, context,
                    f"❌ <b>সঠিক লিংক (URL) নয়:</b> <code>{html.escape(btn_url)}</code>\n\n"
                    "লিংক অবশ্যই <code>http://</code>, <code>https://</code> অথবা <code>tg://</code> দিয়ে শুরু হতে হবে।",
                    parse_mode=ParseMode.HTML,
                )
                return STATE_ADD_BUTTONS

            row_items.append({"text": btn_label, "url": btn_url})
        if row_items:
            rows.append(row_items)

    draft["buttons"] = rows

    keyboard = InlineKeyboardMarkup([
        [btn("🔵 প্রাইমারি", callback_data="btncolor_primary", style="primary"),
         btn("🟢 সাকসেস", callback_data="btncolor_success", style="success"),
         btn("🔴 ডেঞ্জার", callback_data="btncolor_danger", style="danger")],
        [btn("❌ বাতিল করুন", callback_data="cancel_action", style="danger")],
    ])

    await send_tracked(
        update.message, context,
        "🎨 <b>পোস্ট তৈরি করুন — ৬/৬</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "বাটন তৈরি হয়ে গেছে! এবার বাটনের <b>রং (কালার)</b> বেছে নিন:\n\n"
        "🔵 <b>প্রাইমারি</b> — নীল শেড\n"
        "🟢 <b>সাকসেস</b> — সবুজ শেড\n"
        "🔴 <b>ডেঞ্জার</b> — লাল শেড",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    return STATE_SELECT_BUTTON_COLOR


async def skip_buttons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    draft = context.user_data.get("draft")
    if not draft:
        await query.edit_message_text("❌ সেশনের মেয়াদ শেষ হয়ে গেছে।", reply_markup=kb_main_menu())
        return ConversationHandler.END
    draft["buttons"] = []
    draft["button_style"] = None
    return await show_preview(query, context, is_query=True)


async def select_button_color_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    style = query.data.replace("btncolor_", "")
    draft = context.user_data.get("draft")
    if not draft:
        await query.edit_message_text("❌ সেশনের মেয়াদ শেষ হয়ে গেছে।", reply_markup=kb_main_menu())
        return ConversationHandler.END

    draft["button_style"] = style
    for row in draft.get("buttons", []):
        for b in row:
            b["style"] = style

    return await show_preview(query, context, is_query=True)


# ---------------------------------------------------------------------------
# Preview & Publish
# ---------------------------------------------------------------------------
async def show_preview(source: Any, context: ContextTypes.DEFAULT_TYPE, is_query: bool = False) -> int:
    draft = context.user_data.get("draft")
    if not draft:
        return ConversationHandler.END

    post_type = draft["post_type"]
    post_markup = build_post_markup(draft.get("buttons", []))

    target_msg = source.message

    header = (
        "👁️ <b>পোস্ট প্রিভিউ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>টার্গেট:</b> {html.escape(draft['channel_title'])} "
        f"(<code>{draft['channel_id']}</code>)\n"
    )
    if draft.get("button_style"):
        style_name = COLOR_NAME_BN.get(draft['button_style'], draft['button_style'])
        header += f"🎨 <b>বাটনের কালার:</b> {COLOR_EMOJI.get(draft['button_style'], '')} {style_name}\n"
    header += "━━━━━━━━━━━━━━━━━━━━━━━\n\nনিচে পোস্টের প্রিভিউ দেখুন 👇"

    sent_header = await target_msg.reply_text(header, parse_mode=ParseMode.HTML)
    track_msg(context, sent_header.message_id)

    try:
        if post_type == "text":
            sent = await target_msg.reply_text(
                draft["text"],
                parse_mode=ParseMode.HTML,
                reply_markup=post_markup,
                disable_web_page_preview=False,
            )
        elif post_type == "photo":
            sent = await target_msg.reply_photo(
                photo=draft["media_file_id"],
                caption=draft.get("caption"),
                parse_mode=ParseMode.HTML,
                reply_markup=post_markup,
            )
        elif post_type == "video":
            sent = await target_msg.reply_video(
                video=draft["media_file_id"],
                caption=draft.get("caption"),
                parse_mode=ParseMode.HTML,
                reply_markup=post_markup,
            )
        else:
            sent = None
        if sent:
            track_msg(context, sent.message_id)
    except TelegramError as e:
        sent = await target_msg.reply_text(f"⚠️ প্রিভিউ ত্রুটি: {html.escape(e.message)}")
        track_msg(context, sent.message_id)

    confirm_keyboard = InlineKeyboardMarkup([
        [btn("🚀 পাবলিশ করুন", callback_data="publish_confirm", style="success")],
        [btn("❌ বাতিল করুন", callback_data="cancel_action", style="danger")],
    ])

    sent_confirm = await target_msg.reply_text(
        "সবকিছু ঠিকঠাক আছে?\nচ্যানেলে পোস্ট করতে চাইলে <b>🚀 পাবলিশ করুন</b> বাটনে চাপ দিন।",
        reply_markup=confirm_keyboard,
        parse_mode=ParseMode.HTML,
    )
    track_msg(context, sent_confirm.message_id)

    return STATE_CONFIRM_PUBLISH


async def publish_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    draft = context.user_data.get("draft")

    if not draft:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ ড্রাফটের মেয়াদ শেষ হয়ে গেছে।",
            reply_markup=kb_main_menu(),
        )
        return ConversationHandler.END

    channel_id = draft["channel_id"]
    user_ok, _ = await verify_user_channel_ownership(context.bot, channel_id, user_id)
    if not user_ok:
        await purge_trash(context, update.effective_chat.id)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⛔ <b>নিরাপত্তা সতর্কতা!</b>\n\nআপনি বর্তমানে এই চ্যানেল বা গ্রুপের অ্যাডমিন নন।",
            reply_markup=kb_main_menu(),
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    post_type = draft["post_type"]
    post_markup = build_post_markup(draft.get("buttons", []))
    published_msg = None
    content_preview = ""

    try:
        if post_type == "text":
            published_msg = await context.bot.send_message(
                chat_id=channel_id, text=draft["text"],
                parse_mode=ParseMode.HTML, reply_markup=post_markup,
            )
            content_preview = re.sub(r"<[^>]*>", "", draft["text"])
        elif post_type == "photo":
            published_msg = await context.bot.send_photo(
                chat_id=channel_id, photo=draft["media_file_id"],
                caption=draft.get("caption"),
                parse_mode=ParseMode.HTML, reply_markup=post_markup,
            )
            content_preview = re.sub(r"<[^>]*>", "", draft.get("caption") or "[ছবি]")
        elif post_type == "video":
            published_msg = await context.bot.send_video(
                chat_id=channel_id, video=draft["media_file_id"],
                caption=draft.get("caption"),
                parse_mode=ParseMode.HTML, reply_markup=post_markup,
            )
            content_preview = re.sub(r"<[^>]*>", "", draft.get("caption") or "[ভিডিও]")
    except TelegramError as e:
        logger.error("Failed to post: %s", e.message)
        await purge_trash(context, update.effective_chat.id)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ <b>পাবলিশ ব্যর্থ হয়েছে!</b>\n\n{html.escape(e.message)}",
            reply_markup=kb_main_menu(),
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    if published_msg:
        await save_published_post(
            user_id=user_id, channel_id=channel_id,
            channel_title=draft["channel_title"],
            post_type=post_type, content_preview=content_preview,
            telegram_message_id=published_msg.message_id,
        )

    draft_title = draft["channel_title"]
    context.user_data.pop("draft", None)

    # 1) পুরানো প্রিভিউ মেসেজগুলো চ্যাট থেকে ক্লিন করা
    await purge_trash(context, update.effective_chat.id)

    # 2) সফল মেসেজ পাঠানো
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                "🎉 <b>পোস্ট সফলভাবে পাবলিশ হয়েছে!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🎯 <b>টার্গেট:</b> {html.escape(draft_title)}\n"
                f"🆔 <b>মেসেজ আইডি:</b> <code>{published_msg.message_id if published_msg else 'N/A'}</code>\n\n"
                "মূল মেনু:"
            ),
            reply_markup=kb_main_menu(),
            parse_mode=ParseMode.HTML,
        )
    except TelegramError as e:
        logger.error("Failed to send success message: %s", e)

    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Cancel — clean wipe
# ---------------------------------------------------------------------------
async def cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.message.delete()
        except TelegramError:
            pass
    elif update.message:
        try:
            await update.message.delete()
        except TelegramError:
            pass

    await purge_trash(context, chat_id)
    context.user_data.pop("draft", None)

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ <b>কার্যক্রম বাতিল করা হয়েছে।</b>\n\nমূল মেনু:",
            reply_markup=kb_main_menu(),
            parse_mode=ParseMode.HTML,
        )
    except TelegramError:
        pass

    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    token = BOT_TOKEN.strip()
    if not token:
        sys.stderr.write("CRITICAL ERROR: BOT_TOKEN is empty.\n")
        sys.exit(1)

    async def _post_init(app: Application) -> None:
        await init_db()

    app: Application = ApplicationBuilder().token(token).post_init(_post_init).build()

    create_post_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_post_start, pattern="^menu_create_post$")],
        states={
            STATE_SELECT_CHANNEL: [
                CallbackQueryHandler(select_channel_callback, pattern=r"^sel_chan_")
            ],
            STATE_SELECT_TYPE: [
                CallbackQueryHandler(select_post_type_callback, pattern=r"^post_type_")
            ],
            STATE_ENTER_CONTENT: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO | filters.VIDEO) & ~filters.COMMAND,
                    enter_content_process,
                )
            ],
            STATE_ENTER_CAPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_caption_process),
                CallbackQueryHandler(skip_caption_callback, pattern="^skip_caption$"),
            ],
            STATE_ADD_BUTTONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_buttons_process),
                CallbackQueryHandler(skip_buttons_callback, pattern="^skip_buttons$"),
            ],
            STATE_SELECT_BUTTON_COLOR: [
                CallbackQueryHandler(select_button_color_callback, pattern="^btncolor_")
            ],
            STATE_CONFIRM_PUBLISH: [
                CallbackQueryHandler(publish_confirm_callback, pattern="^publish_confirm$")
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_action, pattern="^cancel_action$"),
            CommandHandler("cancel", cancel_action),
            CommandHandler("start", start_command),
        ],
        per_user=True,
        per_chat=True,
    )

    set_channel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_channel_start, pattern="^menu_set_channel$")],
        states={
            STATE_SET_CHANNEL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_channel_process)
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_action, pattern="^cancel_action$"),
            CommandHandler("cancel", cancel_action),
            CommandHandler("start", start_command),
        ],
        per_user=True,
        per_chat=True,
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_callback))
    app.add_handler(set_channel_conv)
    app.add_handler(create_post_conv)

    app.add_handler(CallbackQueryHandler(start_command, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(help_callback, pattern="^menu_help$"))
    app.add_handler(CallbackQueryHandler(my_channels_callback, pattern="^menu_my_channels$"))
    app.add_handler(CallbackQueryHandler(my_posts_callback, pattern="^menu_my_posts$"))
    app.add_handler(CallbackQueryHandler(remove_target_menu_callback, pattern="^remove_target_menu$"))
    app.add_handler(CallbackQueryHandler(delete_channel_prompt_callback, pattern=r"^del_chan_"))
    app.add_handler(CallbackQueryHandler(confirm_delete_channel_callback, pattern=r"^confirm_del_"))
    app.add_handler(CallbackQueryHandler(cancel_action, pattern="^cancel_action$"))

    logger.info("Bot starting — Bengali UI + emoji buttons + clean cancel...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

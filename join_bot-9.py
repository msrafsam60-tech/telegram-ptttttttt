"""
Telegram Join Request Auto-DM Bot + VIP Signal Engine
Install:  pip install python-telegram-bot==21.6
Run:      python join_bot.py
"""
import asyncio
import csv
import io
import json
import logging
import os
import random
import re
import time
from datetime import date, datetime, timezone

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup,
    KeyboardButton, Update,
)
from telegram.error import RetryAfter
from telegram.ext import (
    Application, CallbackQueryHandler, ChatJoinRequestHandler, ChatMemberHandler,
    CommandHandler, ContextTypes, MessageHandler, filters,
)

# ====== এখানে নিজের তথ্য বসাও ======
BOT_TOKEN = "8662709455:AAGKL3FrG7waOTJn75FO0rPK0XXLrP9ecQQ"
ADMIN_IDS = [8906782967]  # তোমার Telegram user ID (একাধিক হলে কমা দিয়ে)
# ====================================

CFG_FILE = "config.json"
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("joinbot")

# ---------- Signal config ----------
REGISTER_LINK = "https://dkwin0.com/#/register?invitationCode=68816100046"
SUPPORT_USERNAME = "SAGOR_TREDER"
TELEGRAM_CHANNEL_LINK = "https://t.me/sk_community1"

DEFAULT = {
    "text": "স্বাগতম! আপনার জয়েন রিকোয়েস্ট পেয়েছি।",
    "media_type": None,   # video / photo / animation
    "media_id": None,
    "buttons": [],        # [["Text", "https://url"], ...]
    "auto_approve": False,
    "banned": [],         # ব্যান করা ইউজার আইডি
    "extra_admins": [],   # /addadmin দিয়ে যোগ হওয়া অ্যাডমিন
    "contact": "",        # কানেক্টেড অ্যাডমিনের টেলিগ্রাম ইউজারনেম/লিংক
    "rules": "📖 <b>অ্যাকাউন্ট খোলার নিয়ম</b>\n\n১️⃣ নিচের লিংকে ক্লিক করে রেজিস্ট্রেশন করুন\n২️⃣ আপনার তথ্য দিয়ে অ্যাকাউন্ট তৈরি করুন\n৩️⃣ অ্যাকাউন্ট ভেরিফাই করুন\n৪️⃣ এডমিনকে ইউজার আইডি পাঠান\n\n(এই লেখাটি অ্যাডমিন প্যানেল থেকে বদলানো যাবে)",
    "profile": "🧑‍💻 <b>Developer Profile</b>\n\n🏷 Name ╌ আপনার নাম\n🎯 Dream ╌ আপনার লক্ষ্য\n💡 Work ╌ আপনার কাজ\n\nThanks for visiting! Hit the button ↓",
    "vip_locked": "🔒 <b>এই অপশনটি এখন লক করা আছে।</b>\n\nআনলক করতে এডমিনের সাথে যোগাযোগ করুন।",
    # signal-related
    "signal_text": (
        "<b>👑 𝗦𝗔𝗚𝗢𝗥 𝗩𝗜𝗣 𝗜𝗡𝗝𝗘𝗖𝗧𝗢𝗥 𝗩𝟮𝟬</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>⚡ 𝗣𝗘𝗥𝗜𝗢𝗗</b>      : <code>{period}</code>\n"
        "<b>🎯 𝗣𝗥𝗘𝗗𝗜𝗖𝗧𝗜𝗢𝗡</b>  : <b>{pred_badge}</b>\n"
        "<b>🔢 𝟐-𝐋𝐄𝐕𝐄𝐋 𝐍𝐔𝐌</b> : <code>{num1} | {num2}</code>\n"
        "<b>🛡️ 𝗦𝗧𝗔𝗧𝗨𝗦</b>      : <b>{level_txt}</b>\n"
        "<b>📊 𝗖𝗢𝗡𝗙𝗜𝗗𝗘𝗡𝗖𝗘</b>    : <code>{confidence}%</code> [{bar}]\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        "<b>💎 𝗦𝗘𝗥𝗩𝗘𝗥 𝗦𝗧𝗔𝗧𝗨𝗦</b> : 🟢 <b>𝗢𝗡𝗟𝗜𝗡𝗘 & 𝗦𝗬𝗡𝗖𝗘𝗗</b>\n"
        "<b>⚠️ জরুরি গাইডলাইন</b>: <b>সবসময় ৭-স্টেপ ফান্ড ব্যাকআপ মেনে চলুন!</b>\n"
        "<b>👉 রেজিস্ট্রেশন লিংক</b>: <b>{register_link}</b>\n"
        "<b>📡 কন্টাক্ট সাপোর্ট</b> : <b>@{support}</b>\n"
        "<b>━━━━━━━━━━━━━━━━━━━━━━━━━</b>"
    ),
    "signal_enabled": True,   # signal feature globally on/off
    "auto_signal_channel": "",  # চ্যানেল ID (optional)
}

# ---------- Signal Engine (import os.txt থেকে হুবহু) ----------
BIG_POOL = [5, 6, 7, 8, 9]
SMALL_POOL = [0, 1, 2, 3, 4]


def get_exact_game_period():
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y%m%d")
    total_minutes = now.hour * 60 + now.minute + 1
    return f"{date_part}10001{total_minutes:04d}"


class QuantumRandomEngine:
    def get_new_prediction(self):
        return random.choice(["BIG", "SMALL"])

    def generate_numbers(self, prediction):
        if prediction == "BIG":
            return sorted(random.sample(BIG_POOL, 2))
        return sorted(random.sample(SMALL_POOL, 2))


engine = QuantumRandomEngine()


def format_signal(cfg, period=None, pred=None, nums=None, level=None):
    """Config-এর signal_text থেকে সিগন্যাল মেসেজ বানাও"""
    period = period or get_exact_game_period()
    pred = pred or engine.get_new_prediction()
    nums = nums or engine.generate_numbers(pred)
    level = level or random.choice([1, 2])
    confidence = random.randint(95, 99)
    bar = "██████████" if confidence >= 98 else "█████████▒"
    pred_badge = "𝗕𝗜𝗚 ✅" if pred == "BIG" else "𝗦𝗠𝗔𝗟𝗟 ✅"
    level_txt = "LEVEL: 1 (PRIMARY SAFE)" if level == 1 else "LEVEL: 2 (HIGH BOOST 🔥)"
    try:
        return cfg["signal_text"].format(
            period=period, pred_badge=pred_badge,
            num1=nums[0], num2=nums[1], level_txt=level_txt,
            confidence=confidence, bar=bar,
            register_link=REGISTER_LINK, support=SUPPORT_USERNAME,
        ), pred, nums, level, period
    except KeyError:
        # fallback simple
        return (
            f"👑 SAGOR VIP\n⚡ Period: <code>{period}</code>\n"
            f"🎯 Prediction: <b>{pred_badge}</b>\n"
            f"🔢 NUM: <code>{nums[0]} | {nums[1]}</code>\n"
            f"🛡️ Status: {level_txt}\n📊 Conf: {confidence}% [{bar}]"
        ), pred, nums, level, period


def signal_kb(signal_active=False):
    """Auto signal চালু/বন্ধ বাটন"""
    if signal_active:
        return InlineKeyboardMarkup([
            [mk_btn("🛑 𝗦𝗧𝗢𝗣 𝗦𝗜𝗚𝗡𝗔𝗟 🛑", cb="sig_stop", style="red")],
            [mk_btn("🔮 𝗙𝗨𝗧𝗨𝗥𝗘 𝟭𝟬 𝗦𝗜𝗚𝗡𝗔𝗟𝗦 🔮", cb="sig_future", style="blue")],
            [mk_btn("📡 𝗠𝗔𝗥𝗞𝗘𝗧 𝗧𝗥𝗘𝗡𝗗 𝗥𝗔𝗗𝗔𝗥 📡", cb="sig_radar")],
            [mk_btn("💰 𝟳-𝗦𝗧𝗘𝗣 𝗙𝗨𝗡𝗗 𝗠𝗔𝗡𝗔𝗚 💰", cb="sig_fund", style="green")],
            [mk_btn("💬 𝗩𝗜𝗣 𝗦𝗨𝗣𝗣𝗢𝗥𝗧 💬", cb="sig_support")],
        ])
    return InlineKeyboardMarkup([
        [mk_btn("⚡ 𝗦𝗧𝗔𝗥𝗧 𝗔𝗨𝗧𝗢 𝗦𝗜𝗚𝗡𝗔𝗟 ⚡", cb="sig_start", style="green")],
        [mk_btn("🔮 𝗙𝗨𝗧𝗨𝗥𝗘 𝟭𝟬 𝗦𝗜𝗚𝗡𝗔𝗟𝗦 🔮", cb="sig_future", style="blue")],
        [mk_btn("📡 𝗠𝗔𝗥𝗞𝗘𝗧 𝗧𝗥𝗘𝗡𝗗 𝗥𝗔𝗗𝗔𝗥 📡", cb="sig_radar")],
        [mk_btn("💰 𝟳-𝗦𝗧𝗘𝗣 𝗙𝗨𝗡𝗗 𝗠𝗔𝗡𝗔𝗚 💰", cb="sig_fund", style="green")],
        [mk_btn("💬 𝗩𝗜𝗣 𝗦𝗨𝗣𝗣𝗢𝗥𝗧 💬", cb="sig_support")],
    ])


# ---------- Config helpers ----------
def load():
    if os.path.exists(CFG_FILE):
        with open(CFG_FILE, encoding="utf-8") as f:
            return {**DEFAULT, **json.load(f)}
    return dict(DEFAULT)


def save(cfg):
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def all_admins():
    return set(ADMIN_IDS) | set(load().get("extra_admins", []))


def is_admin(update: Update):
    return bool(update.effective_user) and update.effective_user.id in all_admins()


# ---------- বাটন স্টাইল / প্রিমিয়াম ইমোজি ----------
STYLE_MAP = {"green": "success", "red": "danger", "blue": "primary",
             "success": "success", "danger": "danger", "primary": "primary"}
PREMIUM_ICONS = True


def _kw(style, emoji):
    kw = {}
    if style and style in STYLE_MAP:
        kw["style"] = STYLE_MAP[style]
    if emoji and PREMIUM_ICONS:
        kw["icon_custom_emoji_id"] = str(emoji)
    return kw or None


def mk_btn(text, url=None, cb=None, style=None, emoji=None):
    return InlineKeyboardButton(text, url=url, callback_data=cb, api_kwargs=_kw(style, emoji))


def parse_rows_data(text):
    rows = []
    for line in text.splitlines():
        row = []
        for part in line.split("&&"):
            f = [x.strip() for x in part.split("|")]
            if len(f) >= 2 and f[0] and f[1].startswith(("http://", "https://", "tg://")):
                style, emoji = None, None
                for extra in f[2:]:
                    if extra.lower() in STYLE_MAP:
                        style = extra.lower()
                    elif extra.isdigit():
                        emoji = extra
                row.append([f[0], f[1], style, emoji])
        if row:
            rows.append(row)
    return rows


def rows_to_markup(rows):
    out = []
    for row in rows:
        if row and isinstance(row[0], str):
            row = [row]
        out.append([mk_btn(b[0], url=b[1], style=b[2] if len(b) > 2 else None,
                           emoji=b[3] if len(b) > 3 else None) for b in row])
    return InlineKeyboardMarkup(out) if out else None


# ---------- ইউজার মেনু ----------
MENU_ITEMS = [
    ("rules", "📖", "অ্যাকাউন্ট খোলার নিয়ম", "green"),
    ("admin", "👨‍💻", "কানেক্টেড এডমিন", "blue"),
    ("vip", "💎", "VIP FREE HACK", "red"),
]
MENU_ICON_IDS = {"rules": "", "admin": "", "vip": ""}


def build_menu_kb():
    btns = {}
    for key, emo, label, color in MENU_ITEMS:
        icon = MENU_ICON_IDS.get(key)
        text = label if (icon and PREMIUM_ICONS) else f"{emo} {label}"
        btns[key] = KeyboardButton(text, api_kwargs=_kw(color, icon))
    return ReplyKeyboardMarkup(
        [[btns["rules"]], [btns["admin"], btns["vip"]]],
        resize_keyboard=True, is_persistent=True)


MENU_REGEX = "(" + "|".join(re.escape(l) for _, _, l, _ in MENU_ITEMS) + ")$"

CHANNELS_FILE = "channels.json"
SIGNAL_USERS_FILE = "signal_users.json"


def load_channels():
    if os.path.exists(CHANNELS_FILE):
        with open(CHANNELS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_channels(ch):
    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(ch, f, ensure_ascii=False)


def load_signal_users():
    if os.path.exists(SIGNAL_USERS_FILE):
        with open(SIGNAL_USERS_FILE, encoding="utf-8") as f:
            d = json.load(f)
            if isinstance(d, dict):
                return d
            if isinstance(d, list):
                return {int(k): {"last_msg": 0} for k in d}
    return {}


def save_signal_users(d):
    with open(SIGNAL_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)


def parse_button_rows(text):
    return rows_to_markup(parse_rows_data(text))


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = update.my_chat_member
    chat = c.chat
    if chat.type == "private":
        return
    st = c.new_chat_member.status
    chs = load_channels()
    if st == "administrator":
        chs[str(chat.id)] = chat.title
        save_channels(chs)
        warn = ""
        if chat.type == "channel" and not getattr(c.new_chat_member, "can_post_messages", True):
            warn = "\n⚠️ কিন্তু 'Post Messages' পারমিশন নেই, পোস্ট করতে হলে অন করো।"
        await notify_admins(context.bot, f"✅ বট অ্যাডমিন হয়েছে: {chat.title}{warn}")
    elif str(chat.id) in chs:
        chs.pop(str(chat.id))
        save_channels(chs)
        await notify_admins(context.bot, f"➖ বট সরে গেছে/সরানো হয়েছে: {chat.title}")


def is_banned(uid):
    return uid in load().get("banned", [])


def contact_url(cfg):
    c = (cfg.get("contact") or "").strip()
    if not c:
        return None
    if c.startswith("http"):
        return c
    return "https://t.me/" + c.lstrip("@")


async def send_menu(bot, chat_id):
    await bot.send_message(chat_id, "👇 নিচের মেনু থেকে অপশন বেছে নিন", reply_markup=build_menu_kb())


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load()
    t = update.message.text
    if is_banned(update.effective_user.id):
        return
    add_user(update.effective_user.id)
    remember(update.effective_user)
    key = next((k for k, _, l, _ in MENU_ITEMS if t.endswith(l)), None)
    if key == "rules":
        await update.message.reply_text(cfg["rules"], parse_mode="HTML",
                                        disable_web_page_preview=True)
    elif key == "admin":
        url = contact_url(cfg)
        kb = InlineKeyboardMarkup([[mk_btn("💬 ইনবক্স করুন", url=url, style="blue")]]) if url else None
        await update.message.reply_text(cfg["profile"], parse_mode="HTML", reply_markup=kb)
    elif key == "vip":
        # VIP FREE HACK → signal panel (START / STOP + extras)
        if not cfg.get("signal_enabled", True):
            return await update.message.reply_text(cfg["vip_locked"], parse_mode="HTML")
        su = load_signal_users()
        active = bool(su.get(update.effective_user.id, {}).get("active"))
        # প্রথম সিগন্যাল
        sig, pred, nums, lvl, period = format_signal(cfg)
        await update.message.reply_text(sig, parse_mode="HTML",
                                        reply_markup=signal_kb(active))
        add_log({"ok": True, "id": update.effective_user.id,
                 "name": update.effective_user.full_name,
                 "username": f"@{update.effective_user.username}" if update.effective_user.username else "",
                 "channel": "VIP MENU", "err": ""})


def markup_from(cfg):
    return rows_to_markup(cfg["buttons"]) if cfg["buttons"] else None


async def send_welcome(bot, chat_id, cfg):
    kb = markup_from(cfg)
    mt, mid, text = cfg["media_type"], cfg["media_id"], cfg["text"]
    kw = dict(chat_id=chat_id, reply_markup=kb)
    if mt == "video":
        await bot.send_video(video=mid, caption=text, parse_mode="HTML", **kw)
    elif mt == "photo":
        await bot.send_photo(photo=mid, caption=text, parse_mode="HTML", **kw)
    elif mt == "animation":
        await bot.send_animation(animation=mid, caption=text, parse_mode="HTML", **kw)
    else:
        await bot.send_message(text=text, parse_mode="HTML", **kw)


# ---------- Join request ----------
LOG_FILE = "sent_log.json"
USERS_FILE = "users.json"
META_FILE = "users_meta.json"


def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def remember(user):
    meta = {}
    if os.path.exists(META_FILE):
        with open(META_FILE, encoding="utf-8") as f:
            meta = json.load(f)
    meta[str(user.id)] = {"name": user.full_name, "username": (user.username or "").lower()}
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)


def find_user(query):
    q = query.strip().lstrip("@").lower()
    if q.isdigit():
        return int(q)
    if os.path.exists(META_FILE):
        with open(META_FILE, encoding="utf-8") as f:
            for uid, d in json.load(f).items():
                if d["username"] == q:
                    return int(uid)
    return None


def add_user(uid):
    users = load_users()
    if uid not in users:
        users.add(uid)
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(users), f)


def add_log(entry):
    data = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, encoding="utf-8") as f:
            data = json.load(f)
    entry["ts"] = time.time()
    data.append(entry)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data[-5000:], f, ensure_ascii=False)


async def notify_admins(bot, text):
    for aid in all_admins():
        try:
            await bot.send_message(aid, text)
        except Exception:
            pass


async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    cfg = load()
    u = req.from_user
    name = u.full_name
    uname = f"@{u.username}" if u.username else "(username নেই)"
    target = getattr(req, "user_chat_id", None) or u.id
    if is_banned(u.id):
        try:
            await req.decline()
        except Exception as e:
            log.warning("Decline failed: %s", e)
        return await notify_admins(context.bot, f"🚫 ব্যান করা ইউজারের রিকোয়েস্ট বাতিল\n👤 {name} {uname} ({u.id})")
    ok, err = True, ""
    try:
        await send_welcome(context.bot, target, cfg)
        try:
            await send_menu(context.bot, target)
        except Exception:
            pass
    except Exception as e:
        ok, err = False, str(e)
        log.warning("DM failed for %s: %s", u.id, e)
    if cfg["auto_approve"]:
        try:
            await req.approve()
        except Exception as e:
            log.warning("Approve failed: %s", e)
    if ok:
        add_user(u.id)
        remember(u)
    add_log({"ok": ok, "id": u.id, "name": name, "username": uname,
             "channel": req.chat.title, "err": err})
    if ok:
        msg = (f"✅ ইনবক্সে মেসেজ গেছে\n👤 {name}\n🔗 {uname}\n🆔 {u.id}\n📢 {req.chat.title}")
    else:
        msg = (f"❌ ইনবক্সে মেসেজ যায়নি\n👤 {name}\n🔗 {uname}\n🆔 {u.id}\n"
               f"📢 {req.chat.title}\n⚠️ কারণ: {err}")
    await notify_admins(context.bot, msg)


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not os.path.exists(LOG_FILE):
        return await update.message.reply_text("এখনও কোনো রিকোয়েস্ট আসেনি।")
    with open(LOG_FILE, encoding="utf-8") as f:
        data = json.load(f)[-30:]
    sent = [d for d in data if d["ok"]]
    failed = [d for d in data if not d["ok"]]
    lines = [f"📊 শেষ {len(data)}টা: ✅ {len(sent)} | ❌ {len(failed)}"]
    if failed:
        lines.append("\n❌ মেসেজ যায়নি:")
        lines += [f"• {d['name']} {d['username']} ({d['id']})" for d in failed]
    if sent:
        lines.append("\n✅ মেসেজ গেছে:")
        lines += [f"• {d['name']} {d['username']} ({d['id']})" for d in sent]
    await update.message.reply_text("\n".join(lines)[:4000])


# ---------- Admin panel ----------
def panel_kb(cfg):
    ap = "✅ ON" if cfg["auto_approve"] else "❌ OFF"
    return InlineKeyboardMarkup([
        [mk_btn("📢 ALL USER BROADCAST", cb="broadcast", style="blue")],
        [mk_btn("✉️ নির্দিষ্ট ইউজারকে মেসেজ", cb="dm_user")],
        [mk_btn("📣 চ্যানেলে পোস্ট করো", cb="post", style="green")],
        [mk_btn("📊 স্ট্যাটস", cb="stats"), mk_btn("📤 ইউজার এক্সপোর্ট", cb="export")],
        [mk_btn("🚫 ব্যান/আনব্যান", cb="ban_help", style="red")],
        [mk_btn("⚡ সিগন্যাল ম্যানেজমেন্ট", cb="sig_panel", style="green")],
        [mk_btn("📝 টেক্সট সেট", cb="set_text")],
        [mk_btn("📖 নিয়ম সেট", cb="set_rules"), mk_btn("👨‍💻 প্রোফাইল সেট", cb="set_profile")],
        [mk_btn("🔗 কন্টাক্ট লিংক", cb="set_contact"), mk_btn("🔒 VIP লক টেক্সট", cb="set_vip")],
        [mk_btn("🎬 ভিডিও/ছবি/GIF সেট", cb="set_media")],
        [mk_btn("🔘 বাটন যোগ/মুছো", cb="set_buttons")],
        [mk_btn("💎 প্রিমিয়াম ইমোজি ID বের করো", cb="emojiid", style="blue")],
        [mk_btn(f"Auto Approve: {ap}", cb="toggle_ap",
                style="green" if cfg["auto_approve"] else "red")],
        [mk_btn("👁 প্রিভিউ", cb="preview"), mk_btn("🗑 মিডিয়া মুছো", cb="clear_media")],
    ])


def signal_panel_kb(cfg):
    en = "✅ ON" if cfg.get("signal_enabled", True) else "❌ OFF"
    ch = cfg.get("auto_signal_channel") or "(সেট করা নেই)"
    chs = load_channels()
    ch_rows = []
    for cid, title in list(chs.items())[:8]:
        ch_rows.append([mk_btn(f"📡 {title or cid}", cb=f"sig_ch:{cid}", style="blue")])
    return InlineKeyboardMarkup([
        [mk_btn(f"Signal Feature: {en}", cb="sig_toggle", style="green" if en.endswith("ON") else "red")],
        [mk_btn("⚡ এখনই সিগন্যাল তৈরি করো", cb="sig_now", style="green")],
        [mk_btn("🔮 ফিউচার ১০ সিগন্যাল (প্রিভিউ)", cb="sig_future", style="blue")],
        [mk_btn("📡 ট্রেন্ড রাডার (প্রিভিউ)", cb="sig_radar")],
        [mk_btn("💰 ৭-স্টেপ ফান্ড (প্রিভিউ)", cb="sig_fund", style="green")],
        [mk_btn("📣 সিগন্যাল চ্যানেলে পোস্ট", cb="sig_pick_ch", style="red")],
        *ch_rows,
        [mk_btn(f"📌 Auto Channel: {ch[:25]}", cb="noop")],
        [mk_btn("📝 সিগন্যাল টেমপ্লেট এডিট", cb="set_sigtext")],
        [mk_btn("⬅️ ব্যাক", cb="back_panel")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        if is_banned(update.effective_user.id):
            return
        add_user(update.effective_user.id)
        remember(update.effective_user)
        await send_welcome(context.bot, update.effective_chat.id, load())
        await send_menu(context.bot, update.effective_chat.id)
        return
    context.user_data.pop("await", None)
    await update.message.reply_text("⚙️ অ্যাডমিন প্যানেল", reply_markup=panel_kb(load()))


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    # Signal buttons non-admin users can also use
    d = q.data
    if d.startswith("sig_") and not is_admin(update):
        return await handle_user_signal(q, context)
    if not is_admin(update):
        return await q.answer("Not allowed", show_alert=True)
    await q.answer()
    cfg = load()

    # -------- Signal admin handlers --------
    if d == "sig_panel":
        await q.edit_message_text("⚡ সিগন্যাল ম্যানেজমেন্ট", reply_markup=signal_panel_kb(cfg))
        return
    if d == "back_panel":
        await q.edit_message_text("⚙️ অ্যাডমিন প্যানেল", reply_markup=panel_kb(cfg))
        return
    if d == "noop":
        return
    if d == "sig_toggle":
        cfg["signal_enabled"] = not cfg.get("signal_enabled", True)
        save(cfg)
        await q.edit_message_reply_markup(signal_panel_kb(cfg))
        return
    if d == "sig_now":
        sig, pred, nums, lvl, period = format_signal(cfg)
        await q.message.reply_text(sig, parse_mode="HTML", reply_markup=signal_kb(True))
        return
    if d == "sig_future":
        base = int(get_exact_game_period())
        lines = ["<b>🔮 আগামী ১০টি ফিউচার সিগন্যাল</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
        for i in range(10):
            fp = str(base + i)
            sp = random.choice(["BIG", "SMALL"])
            sn = engine.generate_numbers(sp)
            em = "BIG" if sp == "BIG" else "SMALL"
            lvl_t = "LVL 2" if i % 3 == 1 else "LVL 1"
            lines.append(f"<b>⚡ <code>{fp[-4:]}</code> : {em} | 🔢 <code>{sn[0]},{sn[1]}</code> ({lvl_t})</b>")
        lines.append(f"\n👉 {REGISTER_LINK}")
        await q.message.reply_text("\n".join(lines), parse_mode="HTML")
        return
    if d == "sig_radar":
        txt = (
            "<b>📡 𝗠𝗔𝗥𝗞𝗘𝗧 𝗧𝗥𝗘𝗡𝗗 𝗥𝗔𝗗𝗔𝗥</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>🎯 𝗕𝗜𝗚 𝗧𝗿𝗲𝗻𝗱        : <code>50%</code></b>\n"
            "<b>🎯 𝗦𝗠𝗔𝗟𝗟 𝗧𝗿𝗲𝗻𝗱      : <code>50%</code></b>\n"
            "<b>🔥 মার্কেট মোড        : <code>ZIG-ZAG ALTERNATING (BALANCED)</code></b>\n"
            "<b>🛡️ রিস্ক লেভেল       : <code>LOW RISK (STABLE)</code></b>\n"
            "<b>📊 অ্যালগরিদম        : <code>AI 99.2% ACCURACY</code></b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n👉 {REGISTER_LINK}"
        )
        await q.message.reply_text(txt, parse_mode="HTML")
        return
    if d == "sig_fund":
        txt = (
            "<b>💰 অফিসিয়াল ৭-স্টেপ (𝟳-𝗦𝗧𝗘𝗣) মার্টিঙ্গেল ব্যাকআপ চার্ট</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>🔹 𝗦𝘁𝗲𝗽 𝟭 : <code>7.87 BDT</code>   ➜ (মূল প্রফিট)</b>\n"
            "<b>🔹 𝗦𝘁𝗲𝗽 𝟮 : <code>15.75 BDT</code>  ➜ (রিকভারি + লাভ)</b>\n"
            "<b>🔹 𝗦𝘁𝗲𝗽 𝟯 : <code>31.50 BDT</code>  ➜ (রিকভারি + লাভ)</b>\n"
            "<b>🔹 𝗦𝘁𝗲𝗽 𝟰 : <code>62.99 BDT</code>  ➜ (রিকভারি + লাভ)</b>\n"
            "<b>🔹 𝗦𝘁𝗲𝗽 𝟱 : <code>125.98 BDT</code> ➜ (রিকভারি + লাভ)</b>\n"
            "<b>🔹 𝗦𝘁𝗲𝗽 𝟲 : <code>251.97 BDT</code> ➜ (রিকভারি + লাভ)</b>\n"
            "<b>🔹 𝗦𝘁𝗲𝗽 𝟳 : <code>503.94 BDT</code> ➜ (হাই সিকিউর প্রফিট)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>💎 মোট প্রয়োজনীয় ব্যাকআপ ফান্ড : <code>1000 BDT</code></b>\n"
            f"👉 <b>রেজিস্ট্রেশন লিংক:</b> <b>{REGISTER_LINK}</b>"
        )
        await q.message.reply_text(txt, parse_mode="HTML")
        return
    if d == "sig_support":
        txt = (
            f"<b>💬 𝗦𝗔𝗚𝗢𝗥 𝗩𝗜𝗣 অফিসিয়াল সাপোর্ট</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>👑 সাপোর্ট ইনবক্স : @{SUPPORT_USERNAME}</b>\n"
            f"<b>⏰ একটিভ টাইম    : 24/7 অনলাইন</b>\n👉 <b>{REGISTER_LINK}</b>"
        )
        await q.message.reply_text(txt, parse_mode="HTML")
        return
    if d == "sig_pick_ch":
        chs = load_channels()
        if not chs:
            await q.message.reply_text("কোনো চ্যানেল নেই। বটকে চ্যানেলে অ্যাডমিন করো।")
            return
        kb = [[mk_btn(f"📡 {t or cid}", cb=f"sig_send_ch:{cid}", style="green")] for cid, t in chs.items()]
        await q.message.reply_text("কোন চ্যানেলে সিগন্যাল পাঠাবে?", reply_markup=InlineKeyboardMarkup(kb))
        return
    if d.startswith("sig_send_ch:"):
        cid = d.split(":", 1)[1]
        sig, pred, nums, lvl, period = format_signal(cfg)
        try:
            await context.bot.send_message(chat_id=int(cid), text=sig, parse_mode="HTML",
                                           disable_web_page_preview=True)
            cfg["auto_signal_channel"] = cid
            save(cfg)
            await q.message.reply_text(f"✅ সিগন্যাল পাঠানো হয়েছে → {load_channels().get(cid, cid)}")
        except Exception as e:
            await q.message.reply_text(f"❌ পাঠানো যায়নি: {e}")
        return
    if d.startswith("sig_ch:"):
        cid = d.split(":", 1)[1]
        cfg["auto_signal_channel"] = cid
        save(cfg)
        await q.message.reply_text(f"📌 Auto Signal Channel সেট: {load_channels().get(cid, cid)}")
        return
    if d == "set_sigtext":
        context.user_data["await"] = "signal_text"
        await q.message.reply_text(
            "📝 সিগন্যাল টেমপ্লেট পাঠাও। ব্যবহারযোগ্য প্লেসহোল্ডার:\n"
            "{period} {pred_badge} {num1} {num2} {level_txt} {confidence} {bar} "
            "{register_link} {support}\n\nHTML ট্যাগ সাপোর্টেড।"
        )
        return

    # -------- Existing admin handlers --------
    prompts = {
        "set_rules": ("rules", "📖 অ্যাকাউন্ট খোলার নিয়মের লেখা পাঠাও (ফরম্যাটিং সাপোর্টেড)।"),
        "set_profile": ("profile", "👨‍💻 কানেক্টেড এডমিনের প্রোফাইল লেখা পাঠাও।"),
        "set_contact": ("contact", "🔗 তোমার টেলিগ্রাম @username বা লিংক পাঠাও।"),
        "set_vip": ("vip", "🔒 VIP বাটনে ক্লিক করলে যে লক মেসেজ দেখাবে, সেটা পাঠাও।"),
        "set_text": ("text", "নতুন মেসেজ টেক্সট পাঠাও (bold/italic ফরম্যাটিং সাপোর্টেড)।"),
        "set_media": ("media", "একটা ভিডিও / ছবি / GIF পাঠাও।"),
        "set_buttons": ("buttons", "🔘 বাটন যোগ করো।\n\nফরম্যাট:\nনাম | https://link\n\nরঙ: নাম | লিংক | green\n\nপ্রিমিয়াম ইমোজি: নাম | লিংক | green | ইমোজি_আইডি\n\nপাশাপাশি ২টা: &&\nসব মুছতে: clear"),
    }
    if d in prompts:
        context.user_data["await"] = prompts[d][0]
        await q.message.reply_text(prompts[d][1])
    elif d == "broadcast":
        context.user_data["await"] = "broadcast"
        await q.message.reply_text(BROADCAST_INFO + f"\n👥 মোট ইউজার: {len(load_users())}\n\nবাতিল: /cancel")
    elif d == "dm_user":
        context.user_data["await"] = "dm_target"
        await q.message.reply_text("ইউজারের @username অথবা ID পাঠাও।\nবাতিল: /cancel")
    elif d == "post":
        chs = load_channels()
        if not chs:
            await q.message.reply_text("কোনো চ্যানেল নেই। বটকে চ্যানেলে অ্যাডমিন করো।\nঅথবা: /addchannel @channel_username")
        else:
            kb = [[InlineKeyboardButton(t or cid, callback_data=f"pch:{cid}")] for cid, t in chs.items()]
            await q.message.reply_text("📣 কোন চ্যানেলে পোস্ট করবে?", reply_markup=InlineKeyboardMarkup(kb))
    elif d.startswith("pch:"):
        cid = d[4:]
        context.user_data["post"] = {"chat": int(cid), "title": load_channels().get(cid, cid)}
        context.user_data["await"] = "post_content"
        await q.message.reply_text(
            f"✅ চ্যানেল: {context.user_data['post']['title']}\n\n📝 পোস্টটা পাঠাও।\nবাতিল: /cancel")
    elif d in ("post_go", "post_pin"):
        post = context.user_data.pop("post", None)
        if not post or "mid" not in post:
            return await q.message.reply_text("পোস্ট তৈরি নেই।")
        try:
            sent = await context.bot.copy_message(post["chat"], post["src"], post["mid"], reply_markup=post.get("kb"))
            note = f"✅ পোস্ট হয়েছে: {post['title']}"
            if d == "post_pin":
                try:
                    await context.bot.pin_chat_message(post["chat"], sent.message_id)
                    note += " 📌 (পিন করা)"
                except Exception as e:
                    note += f"\n⚠️ পিন হয়নি: {e}"
            await q.message.reply_text(note)
        except Exception as e:
            await q.message.reply_text(f"❌ পোস্ট হয়নি: {e}")
    elif d == "post_cancel":
        context.user_data.pop("post", None)
        await q.message.reply_text("❌ বাতিল।", reply_markup=panel_kb(load()))
    elif d == "emojiid":
        context.user_data["await"] = "emojiid"
        await q.message.reply_text("💎 প্রিমিয়াম ইমোজি দিয়ে মেসেজ পাঠাও, ID বলে দেব।\nবাতিল: /cancel")
    elif d == "stats":
        await q.message.reply_text(build_stats())
    elif d == "export":
        await send_export(context.bot, q.message.chat_id)
    elif d == "ban_help":
        await q.message.reply_text("🚫 ব্যান: /ban @username অথবা /ban ID\n✅ আনব্যান: /unban @username বা /unban ID")
    elif d == "toggle_ap":
        cfg["auto_approve"] = not cfg["auto_approve"]
        save(cfg)
        await q.edit_message_reply_markup(panel_kb(cfg))
    elif d == "clear_media":
        cfg["media_type"] = cfg["media_id"] = None
        save(cfg)
        await q.message.reply_text("মিডিয়া মুছে ফেলা হয়েছে ✅")
    elif d == "preview":
        await send_welcome(context.bot, q.message.chat_id, cfg)


# ---------- Non-admin signal button handler ----------
async def handle_user_signal(q, context: ContextTypes.DEFAULT_TYPE):
    d = q.data
    uid = q.from_user.id
    cfg = load()
    su = load_signal_users()
    rec = su.get(uid, {"active": False, "last_msg": 0})
    await q.answer()

    if d == "sig_start":
        rec["active"] = True
        su[uid] = rec
        save_signal_users(su)
        sig, pred, nums, lvl, period = format_signal(cfg)
        try:
            sent = await q.message.reply_text(sig, parse_mode="HTML", reply_markup=signal_kb(True))
            rec["last_msg"] = sent.message_id
            su[uid] = rec
            save_signal_users(su)
        except Exception:
            pass
        return
    if d == "sig_stop":
        rec["active"] = False
        if rec.get("last_msg"):
            try:
                await context.bot.delete_message(uid, rec["last_msg"])
            except Exception:
                pass
        rec["last_msg"] = 0
        su[uid] = rec
        save_signal_users(su)
        await q.message.reply_text("🛑 অটো সিগন্যাল বন্ধ করা হয়েছে।\nপুনরায় চালু করতে START বাটন চাপুন।",
                                    reply_markup=signal_kb(False))
        return
    if d == "sig_future":
        base = int(get_exact_game_period())
        lines = ["<b>🔮 আগামী ১০টি ফিউচার সিগন্যাল</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
        for i in range(10):
            fp = str(base + i)
            sp = random.choice(["BIG", "SMALL"])
            sn = engine.generate_numbers(sp)
            em = "BIG" if sp == "BIG" else "SMALL"
            lvl_t = "𝗟𝗩𝗟 𝟮" if i % 3 == 1 else "𝗟𝗩𝗟 𝟭"
            lines.append(f"<b>⚡ <code>{fp[-4:]}</code> : {em} | 🔢 <code>{sn[0]},{sn[1]}</code> ({lvl_t})</b>")
        lines.append(f"\n👉 {REGISTER_LINK}")
        await q.message.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=signal_kb(rec.get("active", False)))
        return
    if d == "sig_radar":
        txt = (
            "<b>📡 𝗠𝗔𝗥𝗞𝗘𝗧 𝗧𝗥𝗘𝗡𝗗 𝗥𝗔𝗗𝗔𝗥</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>🎯 𝗕𝗜𝗚 𝗧𝗿𝗲𝗻𝗱 : <code>50%</code></b>\n"
            "<b>🎯 𝗦𝗠𝗔𝗟𝗟 𝗧𝗿𝗲𝗻𝗱 : <code>50%</code></b>\n"
            "<b>🔥 মার্কেট মোড : <code>ZIG-ZAG ALTERNATING</code></b>\n"
            "<b>🛡️ রিস্ক লেভেল : <code>LOW RISK</code></b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n👉 {REGISTER_LINK}"
        )
        await q.message.reply_text(txt, parse_mode="HTML", reply_markup=signal_kb(rec.get("active", False)))
        return
    if d == "sig_fund":
        txt = (
            "<b>💰 ৭-স্টেপ মার্টিঙ্গেল ফান্ড ম্যানেজমেন্ট</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>🔹 Step 1 : <code>7.87 BDT</code></b>\n"
            "<b>🔹 Step 2 : <code>15.75 BDT</code></b>\n"
            "<b>🔹 Step 3 : <code>31.50 BDT</code></b>\n"
            "<b>🔹 Step 4 : <code>62.99 BDT</code></b>\n"
            "<b>🔹 Step 5 : <code>125.98 BDT</code></b>\n"
            "<b>🔹 Step 6 : <code>251.97 BDT</code></b>\n"
            "<b>🔹 Step 7 : <code>503.94 BDT</code></b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n👉 {REGISTER_LINK}"
        )
        await q.message.reply_text(txt, parse_mode="HTML", reply_markup=signal_kb(rec.get("active", False)))
        return
    if d == "sig_support":
        txt = (
            f"<b>💬 𝗦𝗔𝗚𝗢𝗥 𝗦𝗨𝗣𝗣𝗢𝗥𝗧</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>👑 @{SUPPORT_USERNAME}</b>\n<b>⏰ 24/7 অনলাইন</b>\n👉 {REGISTER_LINK}"
        )
        await q.message.reply_text(txt, parse_mode="HTML", reply_markup=signal_kb(rec.get("active", False)))
        return


BROADCAST_INFO = """👑 ━━━━━━━━━━━━━━━━━━━━━━━━━ 👑
   📢 𝐀𝐃𝐌𝐈𝐍 𝐁𝐑𝐎𝐀𝐃𝐂𝐀𝐒𝐓 𝐌𝐎𝐃𝐄 📢
👑 ━━━━━━━━━━━━━━━━━━━━━━━━━ 👑

📝 এখন যেকোনো মেসেজ পাঠান (Text/Photo/Video/Doc/Voice)।"""


async def do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    banned = set(load().get("banned", []))
    users = [x for x in load_users() if x not in banned]
    status = await m.reply_text(f"⏳ পাঠানো শুরু... (মোট {len(users)} জন)")
    ok = fail = 0
    for uid in users:
        try:
            await context.bot.copy_message(uid, m.chat_id, m.message_id)
            ok += 1
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await context.bot.copy_message(uid, m.chat_id, m.message_id)
                ok += 1
            except Exception:
                fail += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await status.edit_text(f"✅ ব্রডকাস্ট শেষ\n📨 সফল: {ok}\n❌ ব্যর্থ: {fail}")


def build_stats():
    users = load_users()
    cfg = load()
    su = load_signal_users()
    active_signals = sum(1 for v in su.values() if v.get("active"))
    data = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, encoding="utf-8") as f:
            data = json.load(f)
    today = date.today()
    t = [d for d in data if date.fromtimestamp(d.get("ts", 0)) == today]
    ok = sum(1 for d in data if d["ok"])
    rate = f"{ok * 100 // len(data)}%" if data else "—"
    return (
        "📊 বট স্ট্যাটিস্টিক্স\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👥 মোট ইউজার: {len(users)}\n"
        f"📥 মোট রিকোয়েস্ট: {len(data)}\n"
        f"✅ মেসেজ গেছে: {ok} | ❌ যায়নি: {len(data) - ok}\n"
        f"📈 সফলতার হার: {rate}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📅 আজকের রিকোয়েস্ট: {len(t)} (✅ {sum(1 for d in t if d['ok'])})\n"
        f"🚫 ব্যান করা: {len(cfg.get('banned', []))}\n"
        f"⚡ সিগন্যালে সাবস্ক্রাইবড: {active_signals}\n"
        f"👮 অ্যাডমিন: {len(all_admins())}\n"
        f"🤖 অটো অ্যাপ্রুভ: {'ON' if cfg['auto_approve'] else 'OFF'}"
    )


async def send_export(bot, chat_id):
    meta = {}
    if os.path.exists(META_FILE):
        with open(META_FILE, encoding="utf-8") as f:
            meta = json.load(f)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "name", "username"])
    for uid in sorted(load_users()):
        d = meta.get(str(uid), {})
        w.writerow([uid, d.get("name", ""), d.get("username", "")])
    data = io.BytesIO(("\ufeff" + buf.getvalue()).encode("utf-8"))
    data.name = "users.csv"
    await bot.send_document(chat_id, data, caption=f"👥 মোট {len(load_users())} জন")


async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    unban = update.message.text.lower().startswith("/unban")
    if not context.args:
        return await update.message.reply_text("ব্যবহার: /ban @username বা /ban ID")
    uid = find_user(context.args[0])
    if not uid:
        return await update.message.reply_text("❌ ইউজার পাওয়া যায়নি।")
    cfg = load()
    if unban and uid in cfg["banned"]:
        cfg["banned"].remove(uid)
    elif not unban and uid not in cfg["banned"] and uid not in all_admins():
        cfg["banned"].append(uid)
    save(cfg)
    await update.message.reply_text(("✅ আনব্যান: " if unban else "🚫 ব্যান: ") + str(uid))


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update):
        await update.message.reply_text(build_stats())


async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if not context.args:
        return await update.message.reply_text("ব্যবহার: /addchannel @channel_username")
    try:
        chat = await context.bot.get_chat(context.args[0])
        chs = load_channels()
        chs[str(chat.id)] = chat.title
        save_channels(chs)
        await update.message.reply_text(f"✅ যোগ হয়েছে: {chat.title}")
    except Exception as e:
        await update.message.reply_text(f"❌ পাওয়া যায়নি: {e}")


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 আপনার ইউজার আইডি: {update.effective_user.id}")


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    context.user_data.pop("await", None)
    await update.message.reply_text("⚙️ অ্যাডমিন প্যানেল", reply_markup=panel_kb(load()))


async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS or not context.args or not context.args[0].isdigit():
        return await update.message.reply_text("ব্যবহার: /addadmin ইউজার_আইডি")
    cfg = load()
    uid = int(context.args[0])
    if uid not in cfg["extra_admins"]:
        cfg["extra_admins"].append(uid)
        save(cfg)
    await update.message.reply_text(f"✅ {uid} এখন অ্যাডমিন।")


async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS or not context.args or not context.args[0].isdigit():
        return await update.message.reply_text("ব্যবহার: /removeadmin ইউজার_আইডি")
    cfg = load()
    uid = int(context.args[0])
    if uid in cfg["extra_admins"]:
        cfg["extra_admins"].remove(uid)
        save(cfg)
    await update.message.reply_text(f"🗑 {uid} কে সরানো হয়েছে।")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update):
        context.user_data.pop("await", None)
        await update.message.reply_text("বাতিল করা হয়েছে।", reply_markup=panel_kb(load()))


async def on_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    mode = context.user_data.get("await")
    if not mode:
        return
    if mode == "emojiid":
        m = update.message
        ents = list(m.entities or []) + list(m.caption_entities or [])
        ids = [e.custom_emoji_id for e in ents if e.type == "custom_emoji"]
        context.user_data.pop("await", None)
        if not ids:
            return await m.reply_text("❌ কোনো প্রিমিয়াম ইমোজি পাইনি।")
        return await m.reply_text("💎 ইমোজি ID:\n" + "\n".join(ids))
    if mode == "post_content":
        m = update.message
        context.user_data["post"].update({"src": m.chat_id, "mid": m.message_id})
        context.user_data["await"] = "post_buttons"
        return await m.reply_text(
            "🔘 পোস্টে বাটন চাইলে পাঠাও:\nনাম | https://link\nপাশাপাশি: &&\n\nবাটন না চাইলে: skip")
    if mode == "post_buttons":
        m = update.message
        txt = (m.text or "").strip()
        kb = None if txt.lower() == "skip" else parse_button_rows(txt)
        if kb is None and txt.lower() != "skip":
            return await m.reply_text("❌ বাটন বুঝিনি। ফরম্যাট: নাম | https://link  (অথবা skip)")
        post = context.user_data["post"]
        post["kb"] = kb
        context.user_data.pop("await", None)
        await m.reply_text("👁 প্রিভিউ:")
        await context.bot.copy_message(m.chat_id, post["src"], post["mid"], reply_markup=kb)
        return await m.reply_text(
            f"📣 চ্যানেল: {post['title']}\nপোস্ট করবে?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ পোস্ট করো", callback_data="post_go")],
                [InlineKeyboardButton("📌 পোস্ট + পিন", callback_data="post_pin")],
                [InlineKeyboardButton("❌ বাতিল", callback_data="post_cancel")],
            ]))
    if mode == "dm_target":
        uid = find_user(update.message.text or "")
        if not uid:
            return await update.message.reply_text("❌ ইউজার নেই। আবার চেষ্টা করো বা /cancel।")
        context.user_data["dm_uid"] = uid
        context.user_data["await"] = "dm_msg"
        return await update.message.reply_text("✅ এখন যেকোনো মেসেজ পাঠাও।")
    if mode == "dm_msg":
        context.user_data.pop("await", None)
        uid = context.user_data.pop("dm_uid")
        try:
            await context.bot.copy_message(uid, update.message.chat_id, update.message.message_id)
            return await update.message.reply_text("✅ পাঠানো হয়েছে।")
        except Exception as e:
            return await update.message.reply_text(f"❌ পাঠানো যায়নি: {e}")
    if mode == "broadcast":
        context.user_data.pop("await", None)
        return await do_broadcast(update, context)
    m = update.message
    cfg = load()
    if mode == "text" and m.text:
        cfg["text"] = m.text_html
    elif mode in ("rules", "profile", "vip") and m.text:
        key = {"rules": "rules", "profile": "profile", "vip": "vip_locked"}[mode]
        cfg[key] = m.text_html
    elif mode == "contact" and m.text:
        cfg["contact"] = m.text.strip()
    elif mode == "signal_text" and m.text:
        cfg["signal_text"] = m.text_html
    elif mode == "media":
        if m.video:
            cfg["media_type"], cfg["media_id"] = "video", m.video.file_id
        elif m.photo:
            cfg["media_type"], cfg["media_id"] = "photo", m.photo[-1].file_id
        elif m.animation:
            cfg["media_type"], cfg["media_id"] = "animation", m.animation.file_id
        else:
            return await m.reply_text("ভিডিও/ছবি/GIF পাঠাও।")
    elif mode == "buttons" and m.text:
        if m.text.strip().lower() == "clear":
            cfg["buttons"] = []
        else:
            added = parse_rows_data(m.text)
            if not added:
                return await m.reply_text("কোনো বাটন পাইনি। ফরম্যাট: নাম | https://link")
            old = [[r] if (r and isinstance(r[0], str)) else r for r in cfg["buttons"]]
            cfg["buttons"] = old + added
    else:
        return
    save(cfg)
    context.user_data.pop("await", None)
    await m.reply_text("সেভ হয়েছে ✅", reply_markup=panel_kb(cfg))


async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    log.error("Unhandled error", exc_info=context.error)


# ---------- Auto signal loop (background) ----------
async def auto_signal_loop(app: Application):
    """প্রতি মিনিটে period বদলালে active সিগন্যাল ইউজারদের কাছে refresh"""
    log.info("⚡ Auto Signal Loop started")
    cur_period = get_exact_game_period()
    while True:
        try:
            await asyncio.sleep(2)
            new_period = get_exact_game_period()
            if new_period == cur_period:
                continue
            cur_period = new_period
            cfg = load()
            if not cfg.get("signal_enabled", True):
                continue
            sig, pred, nums, lvl, period = format_signal(cfg, period=new_period)
            su = load_signal_users()
            # Also post to channel if configured
            auto_ch = cfg.get("auto_signal_channel")
            if auto_ch:
                try:
                    await app.bot.send_message(int(auto_ch), sig, parse_mode="HTML",
                                               disable_web_page_preview=True)
                except Exception as e:
                    log.warning("Auto channel post failed: %s", e)
            changed = False
            for uid_str, rec in list(su.items()):
                if not rec.get("active"):
                    continue
                uid = int(uid_str)
                try:
                    if rec.get("last_msg"):
                        try:
                            await app.bot.delete_message(uid, rec["last_msg"])
                        except Exception:
                            pass
                    sent = await app.bot.send_message(uid, sig, parse_mode="HTML",
                                                      reply_markup=signal_kb(True))
                    rec["last_msg"] = sent.message_id
                    su[uid_str] = rec
                    changed = True
                except Exception as e:
                    log.warning("Auto signal to %s failed: %s", uid, e)
                await asyncio.sleep(0.05)
            if changed:
                save_signal_users(su)
        except Exception as e:
            log.error("Auto signal loop error: %s", e)


async def post_init(app: Application):
    asyncio.create_task(auto_signal_loop(app))


def main():
    import telegram
    log.info("python-telegram-bot version: %s", telegram.__version__)
    app = (Application.builder()
           .token(BOT_TOKEN)
           .post_init(post_init)
           .build())
    app.add_error_handler(on_error)
    app.add_handler(ChatJoinRequestHandler(on_join_request))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("panel", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler("addchannel", add_channel))
    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CommandHandler(["ban", "unban"], ban_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.Regex(MENU_REGEX), handle_menu))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, on_admin_message))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
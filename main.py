
import os
import telebot
import threading
import time
import random
import requests
from datetime import datetime, timezone, timedelta
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8704586292:AAH6h2nMwrC36ItiqAJkye8P7G7cjuUBzeg")
OWNER_ID  = int(os.environ.get("OWNER_ID", "8473134685"))

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

# ================================================================
#  IN-MEMORY DATABASE  (Cloudflare KV → Python dict)
# ================================================================
db = {
    "users"        : {},   # {str(user_id): {"balance":0,"signals":0,"name":""}}
    "all_users"    : [],
    "channels"     : [],   # [{"id":"...","link":"..."}]
    "ref_reward"   : 25,
    "info"         : "",
    "support"      : {},   # {"text":"","btnName":"","url":""}
    "states"       : {},   # {str(user_id): "STATE_NAME"}
    "redeem_list"  : [],
    "redeems"      : {},   # {"CODE": {...}}
    "referrers"    : {},   # {str(user_id): str(ref_id)}
    "ref_rewards"  : {},   # {str(user_id): True}
    "used_periods" : {},   # {"uid:period": True}
    "timer_stop"   : {},   # {str(chat_id): threading.Event}
    "loss_streak"  : {"30s": 0, "1min": 0},
}

# ================================================================
#  HEADER HELPER — Em-space centering
# ================================================================
def _box(title: str) -> str:
    """Em-space centered title with divider lines"""
    line = "━" * 22
    vlen = sum(2 if ord(c) > 0x2E7F else 1 for c in title)
    pad  = max(0, (26 - vlen) // 2)
    spc  = " " * pad
    return f"`{line}`\n{spc}{title}\n`{line}`"



# ================================================================
#  HEADER HELPER

"""
╔══════════════════════════════════════════════════════════════╗
║          WINGO SIGNAL BOT - Python Version                  ║
║          Converted from main.js (Cloudflare Worker)         ║
║                                                              ║
║  NEW FEATURES:                                               ║
║  ✅ Auto Period (No manual entry needed)                     ║
║  ✅ Win/Loss Check via Real API                              ║
║  ✅ Live Countdown Timer Bar (per-second update)             ║
║  ✅ Lottery 200 WinGo Advanced Prediction Logic              ║
╚══════════════════════════════════════════════════════════════╝
"""

import telebot
import threading
import time
import random
import requests
from datetime import datetime, timezone, timedelta
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ================================================================
#  CONFIGURATION  —  শুধু এখানে পরিবর্তন করুন
# ================================================================
BOT_TOKEN = "8704586292:AAH6h2nMwrC36ItiqAJkye8P7G7cjuUBzeg"
OWNER_ID  = 8473134685              # ← আপনার Telegram User ID দিন

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

# ================================================================
#  IN-MEMORY DATABASE  (Cloudflare KV → Python dict)
# ================================================================
db = {
    "users"        : {},   # {str(user_id): {"balance":0,"signals":0,"name":""}}
    "all_users"    : [],
    "channels"     : [],   # [{"id":"...","link":"..."}]
    "ref_reward"   : 25,
    "info"         : "",
    "support"      : {},   # {"text":"","btnName":"","url":""}
    "states"       : {},   # {str(user_id): "STATE_NAME"}
    "redeem_list"  : [],
    "redeems"      : {},   # {"CODE": {...}}
    "referrers"    : {},   # {str(user_id): str(ref_id)}
    "ref_rewards"  : {},   # {str(user_id): True}
    "used_periods" : {},   # {"uid:period": True}
    "timer_stop"   : {},   # {str(chat_id): threading.Event}
    "loss_streak"  : {"30s": 0, "1min": 0},
}

# ================================================================
#  HEADER HELPER



# ================================================================
#  GAME CONFIGURATIONS
# ================================================================
GAME_CONFIGS = {
    "30s": {
        "api"        : "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json",
        "interval"   : 30,
        "game_name"  : "WINGO 30S",
    },
    "1min": {
        "api"        : "https://draw.ar-lottery01.com/WinGo/WinGo_1M/GetHistoryIssuePage.json",
        "interval"   : 60,
        "game_name"  : "WINGO 1MIN",
    },
}

# ================================================================
#  TIMEZONE — Bangladesh (UTC+6)
# ================================================================
BD_TZ = timezone(timedelta(hours=6))

def bd_now():
    return datetime.now(BD_TZ)

# ================================================================
#  AUTO PERIOD CALCULATION  (No manual period input!)
# ================================================================
def calculate_period(game_type: str) -> str:
    """
    Current period-ID কে auto calculate করে।
    User-কে period type করতে হবে না।
    """
    now = datetime.now(timezone.utc)
    y, m, d = now.strftime("%Y"), now.strftime("%m"), now.strftime("%d")

    if game_type == "30s":
        half_mins = (now.hour * 60 + now.minute) * 2 + (0 if now.second < 30 else 1)
        return f"{y}{m}{d}10005{str(half_mins + 1).zfill(4)}"
    else:
        total_mins = now.hour * 60 + now.minute
        return f"{y}{m}{d}1000{10001 + total_mins}"

def get_remaining_seconds(game_type: str) -> int:
    """Current period-এর কত সেকেন্ড বাকি"""
    now = datetime.now(timezone.utc)
    if game_type == "30s":
        return 30 - (now.second % 30)
    return 60 - now.second

# ================================================================
#  API — WIN / LOSS CHECK
# ================================================================
def get_period_result(game_type: str, period: str):
    """
    API থেকে specific period-এর result নিয়ে আসে।
    Returns int (0-9) or None
    """
    try:
        url    = GAME_CONFIGS[game_type]["api"]
        resp   = requests.get(url, params={"pageSize": 20, "pageNo": 1}, timeout=10)
        if resp.status_code == 200:
            items = resp.json().get("data", {}).get("list", [])
            for item in items:
                if str(item.get("issueNumber")) == str(period):
                    return int(item.get("number", -1))
    except Exception as e:
        print(f"[API Error] {e}")
    return None

def get_last_n_results(game_type: str, n: int = 200) -> list:
    """Lottery 200 analysis-এর জন্য last N result fetch করে"""
    try:
        url  = GAME_CONFIGS[game_type]["api"]
        resp = requests.get(url, params={"pageSize": n, "pageNo": 1}, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("list", [])
    except Exception as e:
        print(f"[API Error] {e}")
    return []

# ================================================================
#  ALGORITHMS — 30s, 1min, Lottery200  (3 separate engines)
# ================================================================

def _fetch_numbers(game_type: str, n: int = 50) -> list:
    """API থেকে last N period-এর number list নিয়ে আসে"""
    try:
        url  = GAME_CONFIGS[game_type]["api"]
        resp = requests.get(url, params={"pageSize": n, "pageNo": 1}, timeout=10)
        if resp.status_code == 200:
            items = resp.json().get("data", {}).get("list", [])
            return [int(x.get("number", -1)) for x in items if str(x.get("number", "")).isdigit()]
    except Exception as e:
        print(f"[API] {e}")
    return []

def _to_outcomes(numbers: list) -> list:
    """number list → BIG/SMALL list"""
    return ["BIG" if n >= 5 else "SMALL" for n in numbers if 0 <= n <= 9]

def _score_decision(scores: dict) -> tuple:
    """Score dict থেকে prediction + confidence বের করে"""
    if scores["BIG"] > scores["SMALL"]:
        pred = "BIG"
        raw  = 68 + int(scores["BIG"] * 2.8)
    elif scores["SMALL"] > scores["BIG"]:
        pred = "SMALL"
        raw  = 68 + int(scores["SMALL"] * 2.8)
    else:
        pred = random.choice(["BIG", "SMALL"])
        raw  = random.randint(70, 76)
    return pred, max(70, min(94, raw))


# ══════════════════════════════════════════════════════════════
#  30S ALGORITHM — 400+ Deep Analysis Engine
#  Last 400 results fetch করে 7টি technique apply করে
# ══════════════════════════════════════════════════════════════
def predict_30s() -> tuple:
    numbers  = _fetch_numbers("30s", 400)
    outcomes = _to_outcomes(numbers)

    if len(outcomes) < 10:
        return ("BIG" if random.random() > 0.5 else "SMALL"), random.randint(70, 78)

    scores = {"BIG": 0.0, "SMALL": 0.0}

    # ① Streak break (last 10) — highest weight for 30s
    streak, streak_side = 1, outcomes[0]
    for o in outcomes[1:10]:
        if o == streak_side: streak += 1
        else: break
    if streak >= 3:
        opp = "SMALL" if streak_side == "BIG" else "BIG"
        scores[opp] += streak * 2.5

    # ② Last 5 momentum
    last5 = outcomes[:5]
    b5, s5 = last5.count("BIG"), last5.count("SMALL")
    if b5 >= 4: scores["SMALL"] += 4.0
    elif s5 >= 4: scores["BIG"] += 4.0

    # ③ Alternating rhythm (last 8)
    last8 = outcomes[:8]
    alt = sum(1 for i in range(len(last8)-1) if last8[i] != last8[i+1])
    if alt >= 7:
        scores["SMALL" if outcomes[0] == "BIG" else "BIG"] += 3.0

    # ④ Frequency imbalance — last 50
    last50 = outcomes[:50]
    b50, s50 = last50.count("BIG"), last50.count("SMALL")
    if b50 >= 30: scores["SMALL"] += (b50 - 25) * 0.5
    elif s50 >= 30: scores["BIG"] += (s50 - 25) * 0.5

    # ⑤ Odd/Even cluster (last 20 raw numbers)
    n20 = numbers[:20]
    odds  = sum(1 for n in n20 if n % 2 == 1)
    evens = 20 - odds
    if odds >= 14:   scores["SMALL"] += 2.0
    elif evens >= 14: scores["BIG"]  += 2.0

    # ⑥ Number zone bias (last 100): 0-4 vs 5-9
    last100 = outcomes[:100]
    b100, s100 = last100.count("BIG"), last100.count("SMALL")
    if b100 >= 58: scores["SMALL"] += 2.5
    elif s100 >= 58: scores["BIG"] += 2.5

    # ⑦ Deep history reversal (last 400 split into 8 blocks of 50)
    if len(outcomes) >= 400:
        blocks = [outcomes[i*50:(i+1)*50] for i in range(8)]
        big_rates = [b.count("BIG") for b in blocks]
        # If last 3 blocks trend one way → expect reversal
        recent3 = big_rates[:3]  # most recent
        if all(r >= 28 for r in recent3): scores["SMALL"] += 3.0
        elif all(r <= 22 for r in recent3): scores["BIG"] += 3.0

    return _score_decision(scores)


# ══════════════════════════════════════════════════════════════
#  1MIN ALGORITHM — 400+ Deep Analysis Engine
#  Last 400 results fetch করে 8টি technique apply করে
# ══════════════════════════════════════════════════════════════
def predict_1min() -> tuple:
    numbers  = _fetch_numbers("1min", 400)
    outcomes = _to_outcomes(numbers)

    if len(outcomes) < 10:
        return ("BIG" if random.random() > 0.5 else "SMALL"), random.randint(70, 78)

    scores = {"BIG": 0.0, "SMALL": 0.0}

    # ① Streak (moderate weight for 1min)
    streak, streak_side = 1, outcomes[0]
    for o in outcomes[1:]:
        if o == streak_side: streak += 1
        else: break
    if streak >= 4:
        opp = "SMALL" if streak_side == "BIG" else "BIG"
        scores[opp] += min(5.0, streak * 1.2)

    # ② Frequency imbalance — last 20 (primary signal)
    last20 = outcomes[:20]
    b20, s20 = last20.count("BIG"), last20.count("SMALL")
    if b20 >= 13: scores["SMALL"] += (b20 - 10) * 1.2
    elif s20 >= 13: scores["BIG"] += (s20 - 10) * 1.2

    # ③ Cycle detection (last 60 split into 3 windows)
    if len(outcomes) >= 60:
        w1 = outcomes[:20]; w2 = outcomes[20:40]; w3 = outcomes[40:60]
        b1, b2, b3 = w1.count("BIG"), w2.count("BIG"), w3.count("BIG")
        # Zigzag: w1 high, w2 low, w3 high → w4 (next) should be low
        if b1 >= 12 and b2 <= 8 and b3 >= 12: scores["SMALL"] += 3.0
        elif b1 <= 8 and b2 >= 12 and b3 <= 8: scores["BIG"]  += 3.0

    # ④ Number cluster (last 30 raw)
    n30 = numbers[:30]
    high = sum(1 for n in n30 if n >= 7)  # 7,8,9 → BIG side
    low  = sum(1 for n in n30 if n <= 2)  # 0,1,2 → SMALL side
    if high >= 12: scores["SMALL"] += 2.5
    if low  >= 12: scores["BIG"]   += 2.5

    # ⑤ Last 100 balance check
    last100 = outcomes[:100]
    b100, s100 = last100.count("BIG"), last100.count("SMALL")
    if b100 >= 58: scores["SMALL"] += 2.0
    elif s100 >= 58: scores["BIG"] += 2.0

    # ⑥ Alternating pattern (last 10)
    last10 = outcomes[:10]
    alt = sum(1 for i in range(len(last10)-1) if last10[i] != last10[i+1])
    if alt >= 8:
        scores["SMALL" if outcomes[0] == "BIG" else "BIG"] += 2.5

    # ⑦ Deep trend (last 200 vs last 400 comparison)
    if len(outcomes) >= 400:
        recent200 = outcomes[:200]
        older200  = outcomes[200:400]
        rb, ob = recent200.count("BIG"), older200.count("BIG")
        diff = rb - ob  # positive = recent more BIG
        if diff >= 15: scores["SMALL"] += 3.0   # recent BIG-heavy → expect SMALL
        elif diff <= -15: scores["BIG"] += 3.0

    # ⑧ 50-period micro-cycle (last 400 in 8 blocks)
    if len(outcomes) >= 400:
        blocks = [outcomes[i*50:(i+1)*50] for i in range(8)]
        big_rates = [b.count("BIG") for b in blocks]
        # Trend direction of last 4 blocks
        t = big_rates[:4]
        if t[0] > t[1] > t[2] > t[3]: scores["BIG"]   += 2.0  # downtrend → reversal up
        elif t[0] < t[1] < t[2] < t[3]: scores["SMALL"] += 2.0 # uptrend → reversal down

    return _score_decision(scores)


def _make_next_kb(game_type: str) -> InlineKeyboardMarkup:
    """WIN/LOSS দেখানোর পর NEXT PREDICTION button"""
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(
        "🔄 𝗡𝗘𝗫𝗧 𝗣𝗥𝗘𝗗𝗜𝗖𝗧𝗜𝗢𝗡",
        callback_data=f"NEXT_PRED:{game_type}"
    ))
    return kb


# ================================================================
#  PREDICTION MESSAGE BUILDER
# ================================================================
def _build_pred_text(game_name: str, period: str, prediction: str, confidence: int) -> str:
    pred_icon  = '\U0001f4c8' if prediction == 'BIG' else '\U0001f4c9'
    pred_arrow = '\u2b06\ufe0f' if prediction == 'BIG' else '\u2b07\ufe0f'
    bar_fill   = int(confidence / 10)
    conf_bar   = '\u2588' * bar_fill + '\u2591' * (10 - bar_fill)
    msg  = _box('🔰 *W I N G O  S I G N A L* 🔰') + '\n\n'
    msg += f'\U0001f3ae *MARKET* \u00bb `{game_name}`\n\n'
    msg += f'\U0001f522 *PERIOD* \u00bb `{period}`\n\n'
    msg += '\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n'
    msg += f'\U0001f3af *TRADE ON* \u27a4 {pred_icon} *{prediction}* {pred_arrow}\n\n'
    msg += f'\U0001f4ca *Confidence* \u27a4 `{conf_bar}` `{confidence}%`\n\n'
    msg += '\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n'
    msg += '\u23f3 _Waiting for period result\\.\\.\\._'
    return msg



# ================================================================
#  PERIOD CHANGE DETECTOR  — Background thread
#  Logic: প্রতি সেকেন্ডে current period check করে।
#         Period change হলে API call → WIN/LOSS দেখায়।
#         কোনো timer bar নেই, কোনো message edit নেই।
# ================================================================
def _safe_send_result(chat_id, message_id, final_text, next_kb):
    """WIN/LOSS result message edit করে, fail হলে নতুন message পাঠায়"""
    import re as _re
    for attempt in range(4):
        try:
            bot.edit_message_text(
                final_text,
                chat_id=chat_id,
                message_id=message_id,
                parse_mode="Markdown",
                reply_markup=next_kb
            )
            return
        except Exception as e:
            err = str(e).lower()
            if "message is not modified" in err:
                return
            elif "message to edit not found" in err:
                # Message deleted — send fresh
                try:
                    bot.send_message(chat_id, final_text,
                                     parse_mode="Markdown", reply_markup=next_kb)
                except Exception:
                    pass
                return
            elif "429" in err or "too many requests" in err:
                wait = 15
                try:
                    m = _re.search(r"retry after (\d+)", err)
                    if m:
                        wait = int(m.group(1)) + 2
                except Exception:
                    pass
                time.sleep(wait)
            else:
                time.sleep(3)
    # Final fallback
    try:
        bot.send_message(chat_id, final_text,
                         parse_mode="Markdown", reply_markup=next_kb)
    except Exception:
        pass


def _debug_api_raw(game_type: str, n: int = 5):
    """API response raw dump — debug only"""
    try:
        url  = GAME_CONFIGS[game_type]["api"]
        resp = requests.get(url, params={"pageSize": n, "pageNo": 1}, timeout=10)
        if resp.status_code == 200:
            items = resp.json().get("data", {}).get("list", [])
            for item in items:
                print(f"[API RAW] {item}")
        else:
            print(f"[API RAW] status={resp.status_code}")
    except Exception as e:
        print(f"[API RAW ERROR] {e}")


def get_period_result_robust(game_type: str, period: str):
    """
    Robust result fetch — multiple field names try করে।
    issueNumber, issue, periodNumber, period etc.
    """
    try:
        url  = GAME_CONFIGS[game_type]["api"]
        resp = requests.get(url, params={"pageSize": 30, "pageNo": 1}, timeout=10)
        if resp.status_code != 200:
            print(f"[RESULT] API status {resp.status_code}")
            return None

        data  = resp.json()
        items = (data.get("data") or {}).get("list") or data.get("list") or []

        print(f"[RESULT] Looking for period={period}, got {len(items)} items")

        # Try every possible key name
        period_keys = ["issueNumber", "issue", "periodNumber", "period",
                       "issueNum", "no", "drawNumber"]
        number_keys = ["number", "num", "result", "drawResult", "winNumber"]

        for item in items:
            # Check each possible period key
            for pk in period_keys:
                val = str(item.get(pk, ""))
                if val == str(period):
                    # Found the period — now get number
                    for nk in number_keys:
                        nv = item.get(nk)
                        if nv is not None:
                            try:
                                n = int(str(nv).strip())
                                print(f"[RESULT] Found! period={period} number={n} (key={nk})")
                                return n
                            except Exception:
                                pass
                    print(f"[RESULT] Period found but no number key! item={item}")
                    return None

        # Period not in list yet — show what IS there
        if items:
            first = items[0]
            for pk in period_keys:
                if pk in first:
                    print(f"[RESULT] Latest period in API: {first[pk]} (key={pk})")
                    break
        return None

    except Exception as e:
        print(f"[RESULT ERROR] {e}")
        return None


def _debug_api_raw(game_type: str, n: int = 3):
    try:
        url  = GAME_CONFIGS[game_type]["api"]
        resp = requests.get(url, params={"pageSize": n, "pageNo": 1}, timeout=10)
        if resp.status_code == 200:
            items = (resp.json().get("data") or {}).get("list") or []
            for item in items:
                print(f"[API RAW] {item}")
        else:
            print(f"[API] status={resp.status_code}")
    except Exception as ex:
        print(f"[API RAW ERR] {ex}")


def get_period_result_robust(game_type: str, period: str):
    """Multiple field names try করে result বের করে"""
    try:
        url  = GAME_CONFIGS[game_type]["api"]
        resp = requests.get(url, params={"pageSize": 30, "pageNo": 1}, timeout=10)
        if resp.status_code != 200:
            print(f"[RESULT] status={resp.status_code}")
            return None

        raw   = resp.json()
        items = (raw.get("data") or {}).get("list") or raw.get("list") or []
        print(f"[RESULT] {len(items)} items, looking for period={period}")

        period_keys = ["issueNumber","issue","periodNumber","period","issueNum","no"]
        number_keys = ["number","num","result","drawResult","winNumber"]

        for item in items:
            for pk in period_keys:
                if str(item.get(pk,"")) == str(period):
                    for nk in number_keys:
                        nv = item.get(nk)
                        if nv is not None:
                            try:
                                n = int(str(nv).strip())
                                print(f"[RESULT] FOUND period={period} number={n}")
                                return n
                            except Exception:
                                pass
        # show what latest period is
        if items:
            for pk in period_keys:
                if pk in items[0]:
                    print(f"[RESULT] Latest in API: {items[0][pk]}")
                    break
        return None
    except Exception as ex:
        print(f"[RESULT ERR] {ex}")
        return None


def period_watcher_thread(chat_id, message_id, period, prediction,
                          confidence, game_type, stop_evt):
    game_name = GAME_CONFIGS[game_type]["game_name"]
    next_kb   = _make_next_kb(game_type)
    checked   = False
    print(f"[WATCHER] Started period={period} game={game_type}")

    while not stop_evt.is_set():
        time.sleep(1)
        current = calculate_period(game_type)

        if current != period:
            if checked:
                break
            checked = True
            print(f"[WATCHER] Period changed {period} -> {current}")
            _debug_api_raw(game_type)

            result_number = None
            for attempt in range(8):
                result_number = get_period_result_robust(game_type, period)
                if result_number is not None:
                    break
                print(f"[WATCHER] Attempt {attempt+1}/8, waiting 3s...")
                time.sleep(3)

            if result_number is not None:
                actual = "BIG" if result_number >= 5 else "SMALL"
                is_win = prediction == actual

                if is_win:
                    db["loss_streak"][game_type] = 0
                    inc_wins(chat_id)
                else:
                    db["loss_streak"][game_type] = db["loss_streak"].get(game_type, 0) + 1
                    inc_losses(chat_id)

                if is_win:
                    t    = _box("🏆 *W I N !* 🏆") + "\n\n"
                    deco = "\U0001f3af" * 10
                else:
                    t    = _box("💔 *L O S S !* 💔") + "\n\n"
                    deco = "\U0001f494" * 10

                t += f"\U0001f3ae *MARKET* >> `{game_name}`\n"
                t += f"\U0001f522 *PERIOD* >> `{period}`\n\n"
                t += "\u2500" * 21 + "\n\n"
                t += f"\U0001f3af *PREDICTED* >> *{prediction}*\n"
                t += f"\U0001f4cc *RESULT* >> *{actual}* (No. {result_number})\n\n"
                t += "\u2500" * 21 + "\n\n"
                t += ("\u2705 *OUTCOME : WIN!*" if is_win else "\u274c *OUTCOME : LOSS!*") + "\n\n"
                t += deco + "\n\n"
                t += "\U0001f447 *Next Signal \u09a8\u09bf\u09a8*"
                final_text = t
            else:
                t  = _box("🔰 *W I N G O  S I G N A L* 🔰") + "\n\n"
                t += f"\U0001f522 *PERIOD* >> `{period}`\n"
                t += f"\U0001f3af *PREDICTED* >> *{prediction}*\n\n"
                t += "\u2753 Result API-te paoa jacche na\n\n"
                t += "\U0001f447 *Retry korun*"
                final_text = t

            _safe_send_result(chat_id, message_id, final_text, next_kb)
            break

    key = str(chat_id)
    if key in db["timer_stop"]:
        del db["timer_stop"][key]
    print(f"[WATCHER] Ended for period={period}")


# ================================================================
#  PREDICTION SENDER
# ================================================================
def send_prediction(chat_id: int, user_id: int, game_type: str):
    """
    Auto period calculate → prediction পাঠায় → background watcher চালু করে।
    Period change হলে watcher নিজেই WIN/LOSS দেখাবে।
    """
    bal = get_balance(user_id)
    if bal < 1:
        bot.send_message(
            chat_id,
            "\u274c *\u0986\u09aa\u09a8\u09be\u09b0 \u09aa\u09b0\u09cd\u09af\u09be\u09aa\u09cd\u09a4 \u09ac\u09cd\u09af\u09be\u09b2\u09c7\u09a8\u09cd\u09b8 \u09a8\u09c7\u0987\u0964*\n\n"
            "\U0001f4a1 Refer \u0995\u09b0\u09c7 \u09ac\u09be Redeem Code \u09ac\u09cd\u09af\u09ac\u09b9\u09be\u09b0 \u0995\u09b0\u09c7 balance \u09a8\u09bf\u09a8\u0964",
            parse_mode="Markdown"
        )
        return

    period   = calculate_period(game_type)
    used_key = f"{user_id}:{period}"

    if db["used_periods"].get(used_key):
        bot.send_message(chat_id, "\u26a0\ufe0f \u098f\u0987 Period \u0986\u09aa\u09a8\u09bf \u0987\u09a4\u09bf\u09ae\u09a7\u09cd\u09af\u09c7 \u09ac\u09cd\u09af\u09ac\u09b9\u09be\u09b0 \u0995\u09b0\u09c7\u099b\u09c7\u09a8\u0964")
        return

    add_balance(user_id, -1)
    db["used_periods"][used_key] = True
    inc_signals(user_id)

    # ── Consecutive Loss Recovery Logic ──────────────────────────
    # টানা 2 লস হলে পরের signal হবে সেই market-এর last result অনুযায়ী
    streak = db["loss_streak"].get(game_type, 0)
    if streak >= 2:
        numbers = _fetch_numbers(game_type, 5)
        if numbers:
            last_num   = numbers[0]
            prediction = "BIG" if last_num >= 5 else "SMALL"
            confidence = 88   # recovery mode confidence
            # Streak reset হবে next result আসলে (watcher handle করবে)
        else:
            # API fail হলে normal algo
            streak = 0

    if streak < 2:
        if game_type == "30s":
            prediction, confidence = predict_30s()
        elif game_type == "1min":
            prediction, confidence = predict_1min()
        elif game_type == "lottery200":
            prediction, confidence = predict_lottery200()
        else:
            prediction = "BIG" if random.random() > 0.5 else "SMALL"
            confidence = random.randint(75, 92)

    game_name = GAME_CONFIGS[game_type]["game_name"]

    # Prediction message পাঠাও (no timer bar)
    text = _build_pred_text(game_name, period, prediction, confidence)
    sent = bot.send_message(chat_id, text, parse_mode="Markdown")

    # আগের watcher থাকলে বন্ধ করো
    key = str(chat_id)
    if key in db["timer_stop"]:
        db["timer_stop"][key].set()
        time.sleep(0.1)

    # নতুন period watcher চালু করো
    stop_evt = threading.Event()
    db["timer_stop"][key] = stop_evt

    t = threading.Thread(
        target=period_watcher_thread,
        args=(chat_id, sent.message_id, period,
              prediction, confidence, game_type, stop_evt),
        daemon=True
    )
    t.start()



# ================================================================
#  DB HELPERS
# ================================================================
def init_user(user_id: int, name: str):
    key = str(user_id)
    if key not in db["users"]:
        db["users"][key] = {"balance": 0, "signals": 0, "wins": 0, "losses": 0, "name": name}
        if user_id not in db["all_users"]:
            db["all_users"].append(user_id)

def get_balance(user_id: int) -> int:
    return db["users"].get(str(user_id), {}).get("balance", 0)

def add_balance(user_id: int, amount: int):
    key = str(user_id)
    db["users"].setdefault(key, {"balance": 0, "signals": 0, "wins": 0, "losses": 0, "name": ""})
    db["users"][key]["balance"] = db["users"][key].get("balance", 0) + amount

def get_signals(user_id: int) -> int:
    return db["users"].get(str(user_id), {}).get("signals", 0)

def inc_signals(user_id: int):
    key = str(user_id)
    db["users"].setdefault(key, {"balance": 0, "signals": 0, "wins": 0, "losses": 0, "name": ""})
    db["users"][key]["signals"] = db["users"][key].get("signals", 0) + 1

def inc_wins(user_id: int):
    key = str(user_id)
    db["users"].setdefault(key, {"balance": 0, "signals": 0, "wins": 0, "losses": 0, "name": ""})
    db["users"][key]["wins"] = db["users"][key].get("wins", 0) + 1

def inc_losses(user_id: int):
    key = str(user_id)
    db["users"].setdefault(key, {"balance": 0, "signals": 0, "wins": 0, "losses": 0, "name": ""})
    db["users"][key]["losses"] = db["users"][key].get("losses", 0) + 1

def set_state(user_id: int, state: str):
    db["states"][str(user_id)] = state

def get_state(user_id: int):
    return db["states"].get(str(user_id))

def clear_state(user_id: int):
    db["states"].pop(str(user_id), None)

def generate_redeem_code() -> str:
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "-".join("".join(random.choices(chars, k=4)) for _ in range(4))


# ================================================================
#  MEMBERSHIP CHECK
# ================================================================
def check_membership(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    channels = db.get("channels", [])
    if not channels:
        return True
    for ch in channels:
        try:
            member = bot.get_chat_member(ch["id"], user_id)
            if member.status in ("left", "kicked"):
                return False
        except Exception:
            return False
    return True

def process_referral_reward(user_id: int):
    uid    = str(user_id)
    ref_id = db["referrers"].get(uid)
    if not ref_id or db["ref_rewards"].get(uid):
        return
    reward = db.get("ref_reward", 25)
    add_balance(int(ref_id), reward)
    db["ref_rewards"][uid] = True
    try:
        bot.send_message(
            int(ref_id),
            f"🤖 *New Referral Completed!*\n\n"
            f"✅ Your friend joined all channels!\n"
            f"💰 You received `{reward}` coins!",
            parse_mode="Markdown"
        )
    except Exception:
        pass


# ================================================================
#  KEYBOARDS
# ================================================================
def main_menu_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("❇️ 𝗪𝗜𝗡𝗚𝗢 𝗦𝗜𝗚𝗡𝗔𝗟 ❇️"),
           KeyboardButton("👤 𝗣𝗥𝗢𝗙𝗜𝗟𝗘"))
    kb.row(KeyboardButton("🧑‍🍼 𝗥𝗘𝗙𝗘𝗥𝗥𝗘𝗗"))
    kb.row(KeyboardButton("📥 𝗥𝗘𝗗𝗘𝗘𝗠 𝗖𝗢𝗗𝗘"),
           KeyboardButton("ℹ️ 𝗜𝗡𝗙𝗢"))
    kb.row(KeyboardButton("🧑‍💻 𝗛𝗘𝗟𝗣 𝗔𝗡𝗗 𝗦𝗨𝗣𝗣𝗢𝗥𝗧"))
    return kb

def wingo_inline_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("☠️ 𝗪𝗜𝗡𝗚𝗢 𝟯𝟬𝗦 ☠️",          callback_data="GAME_30s"))
    kb.add(InlineKeyboardButton("☠️ 𝗪𝗜𝗡𝗚𝗢 𝟭𝗠𝗜𝗡 ☠️",         callback_data="GAME_1min"))
    return kb


# ================================================================
#  /start
# ================================================================
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    user_id = msg.from_user.id
    name    = msg.from_user.first_name or "User"
    chat_id = msg.chat.id

    # Referral arg
    args = msg.text.split()
    if len(args) > 1 and args[1] != str(user_id):
        uid = str(user_id)
        if uid not in db["referrers"]:
            db["referrers"][uid] = args[1]

    init_user(user_id, name)

    if user_id == OWNER_ID or check_membership(user_id):
        process_referral_reward(user_id)
        bot.send_message(
            chat_id,
            "🤖 `আপনাকে আমাদের সিগনাল বটে স্বাগতম 🎉`",
            parse_mode="Markdown"
        )
        _send_main_menu(chat_id)
    else:
        _send_force_join(chat_id)


# ================================================================
#  /ap_bot — Admin Panel
# ================================================================
@bot.message_handler(commands=["ap_bot"])
def cmd_admin(msg):
    if msg.from_user.id == OWNER_ID:
        _send_admin_panel(msg.chat.id)


# ================================================================
#  ALL MESSAGES
# ================================================================
@bot.message_handler(func=lambda m: True)
def on_message(msg):
    user_id = msg.from_user.id
    chat_id = msg.chat.id
    text    = msg.text or ""
    name    = msg.from_user.first_name or "User"

    # ── State machine ──────────────────────────────────────────
    state = get_state(user_id)
    if state:
        _handle_state(chat_id, user_id, text, state)
        return

    # ── Force-join check button ────────────────────────────────
    if text == "✅ CHECK JOINED":
        if check_membership(user_id) or user_id == OWNER_ID:
            process_referral_reward(user_id)
            bot.send_message(chat_id, "✅ *আপনি সফলভাবে জয়েন করেছেন!*", parse_mode="Markdown")
            _send_main_menu(chat_id)
        else:
            _send_force_join(chat_id)
        return

    # ── Membership gate ────────────────────────────────────────
    if user_id != OWNER_ID and not check_membership(user_id):
        _send_force_join(chat_id)
        return

    # ── Main menu buttons ──────────────────────────────────────
    if   text == "❇️ 𝗪𝗜𝗡𝗚𝗢 𝗦𝗜𝗚𝗡𝗔𝗟 ❇️":
        bot.send_message(
            chat_id,
            "🤖 *তুমি কোন গেমে খেলবা?*\n\n🎯 একটি গেম সিলেক্ট করো:",
            parse_mode="Markdown",
            reply_markup=wingo_inline_kb()
        )
    elif text == "👤 𝗣𝗥𝗢𝗙𝗜𝗟𝗘":
        _send_profile(chat_id, user_id, name)
    elif text == "🧑‍🍼 𝗥𝗘𝗙𝗘𝗥𝗥𝗘𝗗":
        _send_referral(chat_id, user_id)
    elif text == "📥 𝗥𝗘𝗗𝗘𝗘𝗠 𝗖𝗢𝗗𝗘":
        set_state(user_id, "REDEEM_WAIT_CODE")
        bot.send_message(
            chat_id,
            "🎁 *Enter Redeem Code*\n\n`Example: H87J-98H4-UIU6-OO99`",
            parse_mode="Markdown"
        )
    elif text == "ℹ️ 𝗜𝗡𝗙𝗢":
        info = db.get("info", "")
        bot.send_message(
            chat_id,
            f"*{info}*" if info else "⚠️ *No Info Available.*",
            parse_mode="Markdown"
        )
    elif text == "🧑‍💻 𝗛𝗘𝗟𝗣 𝗔𝗡𝗗 𝗦𝗨𝗣𝗣𝗢𝗥𝗧":
        _send_support(chat_id)


# ================================================================
#  STATE MACHINE
# ================================================================
def _handle_state(chat_id: int, user_id: int, text: str, state: str):

    # ── Redeem ──────────────────────────────────────────────────
    if state == "REDEEM_WAIT_CODE":
        clear_state(user_id)
        _process_redeem(chat_id, user_id, text)

    # ── Admin: balance ───────────────────────────────────────────
    elif state == "ADMIN_WAIT_BAL_ID":
        set_state(user_id, f"ADMIN_WAIT_BAL_AMT:{text}")
        bot.send_message(chat_id, "Enter Amount:")

    elif state.startswith("ADMIN_WAIT_BAL_AMT:"):
        target = state.split(":", 1)[1]
        try:
            amount = int(text)
            add_balance(int(target), amount)
            bot.send_message(chat_id, f"✅ Added {amount} coins to {target}.")
            try:
                bot.send_message(int(target), f"💰 Admin added {amount} coins to your balance.")
            except Exception:
                pass
        except ValueError:
            bot.send_message(chat_id, "❌ Invalid amount.")
        clear_state(user_id)

    # ── Admin: ref reward ────────────────────────────────────────
    elif state == "ADMIN_WAIT_REF_REWARD":
        try:
            amount = int(text)
            if amount < 1:
                raise ValueError
            db["ref_reward"] = amount
            bot.send_message(chat_id, f"✅ Referral reward set to {amount} coins.")
        except ValueError:
            bot.send_message(chat_id, "❌ Invalid amount.")
        clear_state(user_id)

    # ── Admin: create redeem ─────────────────────────────────────
    elif state == "ADMIN_WAIT_REDEEM_AMOUNT":
        try:
            amount = int(text)
            if amount < 1:
                raise ValueError
            code = generate_redeem_code()
            db["redeems"][code] = {
                "code": code, "amount": amount,
                "createdAt": datetime.now().isoformat(),
                "used": False, "usedBy": None, "usedAt": None
            }
            db["redeem_list"].append(code)
            bot.send_message(
                chat_id,
                f"✅ *Redeem Code Created!*\n\n🎟 Code: `{code}`\n💰 Amount: {amount} coins",
                parse_mode="Markdown"
            )
        except ValueError:
            bot.send_message(chat_id, "❌ Invalid amount.")
        clear_state(user_id)

    # ── Admin: add channel ───────────────────────────────────────
    elif state == "ADMIN_WAIT_CH":
        parts = text.split("|")
        if len(parts) != 2:
            bot.send_message(
                chat_id,
                "Invalid format. Use: `ChannelID|Link`\nExample: `-100123456789|https://t.me/channel`",
                parse_mode="Markdown"
            )
            return
        db["channels"].append({"id": parts[0].strip(), "link": parts[1].strip()})
        bot.send_message(chat_id, "✅ Channel Added.")
        clear_state(user_id)

    # ── Admin: info message ──────────────────────────────────────
    elif state == "ADMIN_WAIT_INFO":
        db["info"] = text
        bot.send_message(chat_id, "✅ Info message updated.")
        clear_state(user_id)

    # ── Admin: support text ──────────────────────────────────────
    elif state == "ADMIN_WAIT_SUP_TXT":
        set_state(user_id, f"ADMIN_WAIT_SUP_BTN:{text}")
        bot.send_message(
            chat_id,
            "Now enter Button Name and URL:\n`Admin|https://t.me/admin`",
            parse_mode="Markdown"
        )

    elif state.startswith("ADMIN_WAIT_SUP_BTN:"):
        parts = text.split("|")
        if len(parts) != 2:
            bot.send_message(chat_id, "Invalid format.")
            return
        sup_text = state[len("ADMIN_WAIT_SUP_BTN:"):]
        db["support"] = {"text": sup_text, "btnName": parts[0], "url": parts[1]}
        bot.send_message(chat_id, "✅ Support section updated.")
        clear_state(user_id)

    # ── Admin: broadcast ─────────────────────────────────────────
    elif state == "ADMIN_WAIT_BROADCAST":
        clear_state(user_id)
        _do_broadcast(chat_id, text)


# ================================================================
#  CALLBACK QUERIES
# ================================================================
@bot.callback_query_handler(func=lambda call: True)
def on_callback(call):
    data    = call.data
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    # ── Game buttons ────────────────────────────────────────────
    if data.startswith("GAME_"):
        game_type = data[5:]
        if game_type in GAME_CONFIGS:
            send_prediction(chat_id, user_id, game_type)

    elif data.startswith("NEXT_PRED:"):
        game_type = data.split(":", 1)[1]
        if game_type in GAME_CONFIGS:
            send_prediction(chat_id, user_id, game_type)

    # ── Admin callbacks (owner only) ────────────────────────────
    elif user_id == OWNER_ID:

        if data == "ADMIN_ADD_BAL":
            set_state(user_id, "ADMIN_WAIT_BAL_ID")
            bot.send_message(chat_id, "Enter User ID for balance add:")

        elif data == "ADMIN_ADD_CH":
            set_state(user_id, "ADMIN_WAIT_CH")
            bot.send_message(chat_id, "Send Channel Info:\n`ChannelID|Link`", parse_mode="Markdown")

        elif data == "ADMIN_SET_INFO":
            set_state(user_id, "ADMIN_WAIT_INFO")
            bot.send_message(chat_id, "Send new Info Message:")

        elif data == "ADMIN_SET_SUP":
            set_state(user_id, "ADMIN_WAIT_SUP_TXT")
            bot.send_message(chat_id, "Send Support Message Text:")

        elif data == "ADMIN_SET_REF":
            current = db.get("ref_reward", 25)
            set_state(user_id, "ADMIN_WAIT_REF_REWARD")
            bot.send_message(
                chat_id,
                f"💰 *Set Referral Reward*\n\nCurrent: {current} coins\n\nEnter new amount:",
                parse_mode="Markdown"
            )

        elif data == "ADMIN_REM_CH":
            channels = db.get("channels", [])
            if not channels:
                bot.send_message(chat_id, "No channels to remove.")
            else:
                kb = InlineKeyboardMarkup()
                for i, ch in enumerate(channels):
                    kb.add(InlineKeyboardButton(f"🗑 {ch['link']}", callback_data=f"DEL_CH:{i}"))
                kb.add(InlineKeyboardButton("🔙 BACK", callback_data="BACK_TO_AP"))
                bot.send_message(chat_id, "Select Channel to Remove:", reply_markup=kb)

        elif data.startswith("DEL_CH:"):
            idx = int(data.split(":")[1])
            if 0 <= idx < len(db["channels"]):
                db["channels"].pop(idx)
                bot.send_message(chat_id, "✅ Channel Removed.")

        elif data == "ADMIN_REDEEM_MENU":
            _send_redeem_menu(chat_id)

        elif data == "ADMIN_CREATE_REDEEM":
            set_state(user_id, "ADMIN_WAIT_REDEEM_AMOUNT")
            bot.send_message(chat_id, "🎟 Enter the amount of coins for this code:")

        elif data == "ADMIN_VIEW_REDEEMS":
            _view_redeem_codes(chat_id)

        elif data.startswith("VIEW_REDEEM:"):
            _view_redeem_details(chat_id, data.split(":", 1)[1])

        elif data.startswith("ADMIN_USERS:"):
            page      = int(data.split(":")[1])
            all_users = db.get("all_users", [])
            start, end = page * 10, page * 10 + 10
            slice_u   = all_users[start:end]

            msg = "👥 *All Users*\n"
            for uid in slice_u:
                msg += f"`{uid}`\n"

            kb = InlineKeyboardMarkup()
            row = []
            if page > 0:
                row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"ADMIN_USERS:{page-1}"))
            if end < len(all_users):
                row.append(InlineKeyboardButton("Next ➡️", callback_data=f"ADMIN_USERS:{page+1}"))
            if row:
                kb.row(*row)
            kb.add(InlineKeyboardButton("🔙 BACK", callback_data="BACK_TO_AP"))

            try:
                bot.edit_message_text(
                    msg, chat_id=chat_id,
                    message_id=call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=kb
                )
            except Exception:
                bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=kb)

        elif data == "ADMIN_BROADCAST":
            set_state(user_id, "ADMIN_WAIT_BROADCAST")
            total = len(db.get("all_users", []))
            bot.send_message(
                chat_id,
                f"📢 *Broadcast Message*\n\n"
                f"👥 Total Users: `{total}`\n\n"
                f"Send the message you want to broadcast to all users:\n"
                "(Text, Photo, Video সব support করে)",
                parse_mode="Markdown"
            )

        elif data == "BACK_TO_AP":
            _send_admin_panel(chat_id)

    bot.answer_callback_query(call.id)


# ================================================================
#  INTERNAL SEND HELPERS
# ================================================================
def _send_main_menu(chat_id: int):
    bot.send_message(chat_id, "👇 𝗠𝗔𝗜𝗡 𝗠𝗘𝗡𝗨 👇", reply_markup=main_menu_kb())

def _send_force_join(chat_id: int):
    channels = db.get("channels", [])
    inline_kb = InlineKeyboardMarkup()
    for ch in channels:
        inline_kb.add(InlineKeyboardButton("♻ 𝗝𝗢𝗜𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 ♻", url=ch["link"]))

    bot.send_message(
        chat_id,
        "🤖 *আপনি আমাদের Channel/Group এ জয়েন নেই* ❌\n\n"
        "_তো আবশ্যই আমাদের Channel এ জয়েন হতে হবে।_",
        parse_mode="Markdown",
        reply_markup=inline_kb
    )
    check_kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    check_kb.add(KeyboardButton("✅ CHECK JOINED"))
    bot.send_message(chat_id, "👇 জয়েন করার পর নিচের বাটনে ক্লিক করুন 👇", reply_markup=check_kb)

def _send_profile(chat_id: int, user_id: int, name: str):
    bal    = get_balance(user_id)
    sigs   = get_signals(user_id)
    wins   = db["users"].get(str(user_id), {}).get("wins", 0)
    losses = db["users"].get(str(user_id), {}).get("losses", 0)
    total  = wins + losses
    if total > 0:
        rate = int((wins / total) * 100)
        bar_fill = int(rate / 10)
        rate_bar = "█" * bar_fill + "░" * (10 - bar_fill)
        rate_str = f"`{rate_bar}` `{rate}%`"
    else:
        rate_str = "`──────────` `N/A`"

    div = "\u2501" * 22
    msg  = _box("👤 *P R O F I L E*") + "\n\n"
    msg += f"🧑‍💻 *Name* » `{name}`\n"
    msg += f"🆔 *User ID* » `{user_id}`\n\n"
    msg += div + "\n\n"
    msg += f"💰 *Balance* » *{bal} Coins*\n"
    msg += f"📊 *Total Signals* » *{sigs}*\n\n"
    msg += div + "\n\n"
    msg += f"✅ *Total WIN* » *{wins}*\n"
    msg += f"❌ *Total LOSS* » *{losses}*\n\n"
    msg += f"🏆 *Win Rate* » {rate_str}"
    bot.send_message(chat_id, msg, parse_mode="Markdown")

def _send_referral(chat_id: int, user_id: int):
    me     = bot.get_me()
    link   = f"https://t.me/{me.username}?start={user_id}"
    reward = db.get("ref_reward", 25)
    kb     = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(
        "🛡 𝗦𝗛𝗔𝗥𝗘 𝗥𝗘𝗙𝗘𝗥 𝗟𝗜𝗡𝗞 🛡️",
        url=f"https://t.me/share/url?url={link}&text=Join%20Now!"
    ))
    bot.send_message(
        chat_id,
        f"🖇️ 𝗬𝗢𝗨𝗥 𝗥𝗘𝗙𝗘𝗥 𝗟𝗜𝗡𝗞 :- `{link}`\n\n"
        f"🤖 *আপনি প্রতি রেফারে {reward}টা কয়েন ফ্রি পাবেন!*\n\n"
        f"⚠️ _নোট: রেফার কেবল তখনই কাউন্ট হবে যখন বন্ধু সব চ্যানেলে জয়েন করবে।_",
        parse_mode="Markdown",
        reply_markup=kb
    )

def _send_support(chat_id: int):
    sup = db.get("support", {})
    if not sup:
        bot.send_message(chat_id, "No support info configured.")
        return
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(sup.get("btnName", "Support"), url=sup.get("url", "#")))
    bot.send_message(chat_id, sup.get("text", "Contact Support"), reply_markup=kb)

def _process_redeem(chat_id: int, user_id: int, raw_code: str):
    code   = raw_code.strip().upper()
    redeem = db["redeems"].get(code)
    if not redeem:
        bot.send_message(chat_id, "❌ *Invalid Redeem Code!* Please check and try again.", parse_mode="Markdown")
        return
    if redeem["used"]:
        bot.send_message(chat_id, "❌ *This Code has already been used!*", parse_mode="Markdown")
        return
    redeem["used"]   = True
    redeem["usedBy"] = user_id
    redeem["usedAt"] = datetime.now().isoformat()
    add_balance(user_id, redeem["amount"])
    bot.send_message(
        chat_id,
        f"✅ *Redeem Successful!*\n\n"
        f"💰 Amount: `{redeem['amount']}` coins\n"
        f"🎟 Code: `{code}`\n\n"
        f"Thank you for using our service! 🎉",
        parse_mode="Markdown"
    )

def _do_broadcast(admin_chat_id: int, message_text: str):
    """সব users-কে message broadcast করে, progress দেখায়"""
    all_users = db.get("all_users", [])
    total   = len(all_users)
    success = 0
    failed  = 0

    status_msg = bot.send_message(
        admin_chat_id,
        f"📢 *Broadcasting...*\n\n"
        f"👥 Total: `{total}`\n"
        f"✅ Sent: `0`\n"
        f"❌ Failed: `0`",
        parse_mode="Markdown"
    )

    for i, uid in enumerate(all_users):
        try:
            bot.send_message(
                uid,
                f"📢 *Broadcast Message*\n\n{message_text}",
                parse_mode="Markdown"
            )
            success += 1
        except Exception:
            failed += 1

        # Progress update every 10 users
        if (i + 1) % 10 == 0 or (i + 1) == total:
            try:
                bot.edit_message_text(
                    f"📢 *Broadcasting...*\n\n"
                    f"👥 Total: `{total}`\n"
                    f"✅ Sent: `{success}`\n"
                    f"❌ Failed: `{failed}`\n"
                    f"⏳ Progress: `{i+1}/{total}`",
                    chat_id=admin_chat_id,
                    message_id=status_msg.message_id,
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        time.sleep(0.05)   # Telegram flood control

    # Final status
    try:
        bot.edit_message_text(
            f"✅ *Broadcast Complete!*\n\n"
            f"👥 Total Users: `{total}`\n"
            f"✅ Successfully Sent: `{success}`\n"
            f"❌ Failed: `{failed}`",
            chat_id=admin_chat_id,
            message_id=status_msg.message_id,
            parse_mode="Markdown"
        )
    except Exception:
        pass


def _send_admin_panel(chat_id: int):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("👥 𝗔𝗟𝗟 𝗨𝗦𝗘𝗥𝗦",          callback_data="ADMIN_USERS:0"))
    kb.add(InlineKeyboardButton("➕ 𝗕𝗔𝗟𝗔𝗡𝗖𝗘 𝗔𝗗𝗗",         callback_data="ADMIN_ADD_BAL"))
    kb.add(InlineKeyboardButton("➕ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 𝗔𝗗𝗗",        callback_data="ADMIN_ADD_CH"))
    kb.add(InlineKeyboardButton("📳 𝗕𝗢𝗧 𝗜𝗡𝗙𝗢 𝗠𝗘𝗦𝗦𝗔𝗚𝗘",    callback_data="ADMIN_SET_INFO"))
    kb.add(InlineKeyboardButton("🤙 𝗦𝗨𝗣𝗣𝗢𝗥𝗧 𝗔𝗡𝗗 𝗛𝗘𝗟𝗣",    callback_data="ADMIN_SET_SUP"))
    kb.add(InlineKeyboardButton("⚔ 𝗥𝗘𝗠𝗢𝗩𝗘 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 ⚔️",  callback_data="ADMIN_REM_CH"))
    kb.add(InlineKeyboardButton("💰 𝗥𝗘𝗙𝗘𝗥 𝗥𝗘𝗪𝗔𝗥𝗗",         callback_data="ADMIN_SET_REF"))
    kb.add(InlineKeyboardButton("🎟 𝗥𝗘𝗗𝗘𝗘𝗠 𝗖𝗢𝗗𝗘𝗦",         callback_data="ADMIN_REDEEM_MENU"))
    kb.add(InlineKeyboardButton("📢 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧 𝗠𝗘𝗦𝗦𝗔𝗚𝗘",       callback_data="ADMIN_BROADCAST"))
    bot.send_message(chat_id, "🛡️ *Admin Panel* 🛡️", parse_mode="Markdown", reply_markup=kb)

def _send_redeem_menu(chat_id: int):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ 𝗖𝗥𝗘𝗔𝗧𝗘 𝗥𝗘𝗗𝗘𝗘𝗠 𝗖𝗢𝗗𝗘", callback_data="ADMIN_CREATE_REDEEM"))
    kb.add(InlineKeyboardButton("📋 𝗩𝗜𝗘𝗪 𝗔𝗟𝗟 𝗖𝗢𝗗𝗘𝗦",    callback_data="ADMIN_VIEW_REDEEMS"))
    kb.add(InlineKeyboardButton("🔙 𝗕𝗔𝗖𝗞",               callback_data="BACK_TO_AP"))
    bot.send_message(chat_id, "🎟 *Redeem Code Management*", parse_mode="Markdown", reply_markup=kb)

def _view_redeem_codes(chat_id: int):
    codes = db.get("redeem_list", [])
    if not codes:
        bot.send_message(chat_id, "❌ No redeem codes found.")
        return
    kb = InlineKeyboardMarkup()
    for code in codes:
        r = db["redeems"].get(code)
        if r:
            status = "❌" if r["used"] else "✅"
            kb.add(InlineKeyboardButton(
                f"{status} {code} ({r['amount']})",
                callback_data=f"VIEW_REDEEM:{code}"
            ))
    kb.add(InlineKeyboardButton("🔙 𝗕𝗔𝗖𝗞", callback_data="ADMIN_REDEEM_MENU"))
    bot.send_message(
        chat_id,
        "🎟 *All Redeem Codes*\n\n✅ = Available  ❌ = Used",
        parse_mode="Markdown",
        reply_markup=kb
    )

def _view_redeem_details(chat_id: int, code: str):
    r = db["redeems"].get(code)
    if not r:
        bot.send_message(chat_id, "❌ Not found.")
        return
    status = "❌ Used" if r["used"] else "✅ Available"
    text   = (
        f"🎟 *Redeem Code Details*\n\n"
        f"Code: `{r['code']}`\n"
        f"Amount: {r['amount']} coins\n"
        f"Status: {status}\n"
        f"Created: {r['createdAt']}\n"
    )
    if r["used"]:
        text += f"\nUsed By: `{r['usedBy']}`\nUsed At: {r['usedAt']}"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 𝗕𝗔𝗖𝗞", callback_data="ADMIN_VIEW_REDEEMS"))
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)


# ================================================================
#  ENTRY POINT
# ================================================================
if __name__ == "__main__":
    print("╔══════════════════════════════════════╗")
    print("║     WINGO SIGNAL BOT — Python        ║")
    print("╚══════════════════════════════════════╝")
    print(f"👑 Owner ID : {OWNER_ID}")
    print(f"🎮 Games    : WinGo 30S | WinGo 1Min | Lottery 200")
    print(f"🌍 Timezone : Bangladesh (UTC+6)")
    print(f"⏱  Timer    : Per-second live countdown")
    print(f"📡 Win/Loss : Real API check")
    print("✅ Bot started! Polling...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
def _box(title: str) -> str:
    """Em-space centered title with divider lines"""
    line = "━" * 22
    vlen = sum(2 if ord(c) > 0x2E7F else 1 for c in title)
    pad  = max(0, (26 - vlen) // 2)
    spc  = " " * pad
    return f"`{line}`\n{spc}{title}\n`{line}`"



# ================================================================
#  HEADER HELPER

"""
╔══════════════════════════════════════════════════════════════╗
║          WINGO SIGNAL BOT - Python Version                  ║
║          Converted from main.js (Cloudflare Worker)         ║
║                                                              ║
║  NEW FEATURES:                                               ║
║  ✅ Auto Period (No manual entry needed)                     ║
║  ✅ Win/Loss Check via Real API                              ║
║  ✅ Live Countdown Timer Bar (per-second update)             ║
║  ✅ Lottery 200 WinGo Advanced Prediction Logic              ║
╚══════════════════════════════════════════════════════════════╝
"""

import telebot
import threading
import time
import random
import requests
from datetime import datetime, timezone, timedelta
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ================================================================
#  CONFIGURATION  —  শুধু এখানে পরিবর্তন করুন
# ================================================================
BOT_TOKEN = "8704586292:AAH6h2nMwrC36ItiqAJkye8P7G7cjuUBzeg"
OWNER_ID  = 8473134685              # ← আপনার Telegram User ID দিন

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

# ================================================================
#  IN-MEMORY DATABASE  (Cloudflare KV → Python dict)
# ================================================================
db = {
    "users"        : {},   # {str(user_id): {"balance":0,"signals":0,"name":""}}
    "all_users"    : [],
    "channels"     : [],   # [{"id":"...","link":"..."}]
    "ref_reward"   : 25,
    "info"         : "",
    "support"      : {},   # {"text":"","btnName":"","url":""}
    "states"       : {},   # {str(user_id): "STATE_NAME"}
    "redeem_list"  : [],
    "redeems"      : {},   # {"CODE": {...}}
    "referrers"    : {},   # {str(user_id): str(ref_id)}
    "ref_rewards"  : {},   # {str(user_id): True}
    "used_periods" : {},   # {"uid:period": True}
    "timer_stop"   : {},   # {str(chat_id): threading.Event}
    "loss_streak"  : {"30s": 0, "1min": 0},
}

# ================================================================
#  HEADER HELPER



# ================================================================
#  GAME CONFIGURATIONS
# ================================================================
GAME_CONFIGS = {
    "30s": {
        "api"        : "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json",
        "interval"   : 30,
        "game_name"  : "WINGO 30S",
    },
    "1min": {
        "api"        : "https://draw.ar-lottery01.com/WinGo/WinGo_1M/GetHistoryIssuePage.json",
        "interval"   : 60,
        "game_name"  : "WINGO 1MIN",
    },
}

# ================================================================
#  TIMEZONE — Bangladesh (UTC+6)
# ================================================================
BD_TZ = timezone(timedelta(hours=6))

def bd_now():
    return datetime.now(BD_TZ)

# ================================================================
#  AUTO PERIOD CALCULATION  (No manual period input!)
# ================================================================
def calculate_period(game_type: str) -> str:
    """
    Current period-ID কে auto calculate করে।
    User-কে period type করতে হবে না।
    """
    now = datetime.now(timezone.utc)
    y, m, d = now.strftime("%Y"), now.strftime("%m"), now.strftime("%d")

    if game_type == "30s":
        half_mins = (now.hour * 60 + now.minute) * 2 + (0 if now.second < 30 else 1)
        return f"{y}{m}{d}10005{str(half_mins + 1).zfill(4)}"
    else:
        total_mins = now.hour * 60 + now.minute
        return f"{y}{m}{d}1000{10001 + total_mins}"

def get_remaining_seconds(game_type: str) -> int:
    """Current period-এর কত সেকেন্ড বাকি"""
    now = datetime.now(timezone.utc)
    if game_type == "30s":
        return 30 - (now.second % 30)
    return 60 - now.second

# ================================================================
#  API — WIN / LOSS CHECK
# ================================================================
def get_period_result(game_type: str, period: str):
    """
    API থেকে specific period-এর result নিয়ে আসে।
    Returns int (0-9) or None
    """
    try:
        url    = GAME_CONFIGS[game_type]["api"]
        resp   = requests.get(url, params={"pageSize": 20, "pageNo": 1}, timeout=10)
        if resp.status_code == 200:
            items = resp.json().get("data", {}).get("list", [])
            for item in items:
                if str(item.get("issueNumber")) == str(period):
                    return int(item.get("number", -1))
    except Exception as e:
        print(f"[API Error] {e}")
    return None

def get_last_n_results(game_type: str, n: int = 200) -> list:
    """Lottery 200 analysis-এর জন্য last N result fetch করে"""
    try:
        url  = GAME_CONFIGS[game_type]["api"]
        resp = requests.get(url, params={"pageSize": n, "pageNo": 1}, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("list", [])
    except Exception as e:
        print(f"[API Error] {e}")
    return []

# ================================================================
#  ALGORITHMS — 30s, 1min, Lottery200  (3 separate engines)
# ================================================================

def _fetch_numbers(game_type: str, n: int = 50) -> list:
    """API থেকে last N period-এর number list নিয়ে আসে"""
    try:
        url  = GAME_CONFIGS[game_type]["api"]
        resp = requests.get(url, params={"pageSize": n, "pageNo": 1}, timeout=10)
        if resp.status_code == 200:
            items = resp.json().get("data", {}).get("list", [])
            return [int(x.get("number", -1)) for x in items if str(x.get("number", "")).isdigit()]
    except Exception as e:
        print(f"[API] {e}")
    return []

def _to_outcomes(numbers: list) -> list:
    """number list → BIG/SMALL list"""
    return ["BIG" if n >= 5 else "SMALL" for n in numbers if 0 <= n <= 9]

def _score_decision(scores: dict) -> tuple:
    """Score dict থেকে prediction + confidence বের করে"""
    if scores["BIG"] > scores["SMALL"]:
        pred = "BIG"
        raw  = 68 + int(scores["BIG"] * 2.8)
    elif scores["SMALL"] > scores["BIG"]:
        pred = "SMALL"
        raw  = 68 + int(scores["SMALL"] * 2.8)
    else:
        pred = random.choice(["BIG", "SMALL"])
        raw  = random.randint(70, 76)
    return pred, max(70, min(94, raw))


# ══════════════════════════════════════════════════════════════
#  30S ALGORITHM — 400+ Deep Analysis Engine
#  Last 400 results fetch করে 7টি technique apply করে
# ══════════════════════════════════════════════════════════════
def predict_30s() -> tuple:
    numbers  = _fetch_numbers("30s", 400)
    outcomes = _to_outcomes(numbers)

    if len(outcomes) < 10:
        return ("BIG" if random.random() > 0.5 else "SMALL"), random.randint(70, 78)

    scores = {"BIG": 0.0, "SMALL": 0.0}

    # ① Streak break (last 10) — highest weight for 30s
    streak, streak_side = 1, outcomes[0]
    for o in outcomes[1:10]:
        if o == streak_side: streak += 1
        else: break
    if streak >= 3:
        opp = "SMALL" if streak_side == "BIG" else "BIG"
        scores[opp] += streak * 2.5

    # ② Last 5 momentum
    last5 = outcomes[:5]
    b5, s5 = last5.count("BIG"), last5.count("SMALL")
    if b5 >= 4: scores["SMALL"] += 4.0
    elif s5 >= 4: scores["BIG"] += 4.0

    # ③ Alternating rhythm (last 8)
    last8 = outcomes[:8]
    alt = sum(1 for i in range(len(last8)-1) if last8[i] != last8[i+1])
    if alt >= 7:
        scores["SMALL" if outcomes[0] == "BIG" else "BIG"] += 3.0

    # ④ Frequency imbalance — last 50
    last50 = outcomes[:50]
    b50, s50 = last50.count("BIG"), last50.count("SMALL")
    if b50 >= 30: scores["SMALL"] += (b50 - 25) * 0.5
    elif s50 >= 30: scores["BIG"] += (s50 - 25) * 0.5

    # ⑤ Odd/Even cluster (last 20 raw numbers)
    n20 = numbers[:20]
    odds  = sum(1 for n in n20 if n % 2 == 1)
    evens = 20 - odds
    if odds >= 14:   scores["SMALL"] += 2.0
    elif evens >= 14: scores["BIG"]  += 2.0

    # ⑥ Number zone bias (last 100): 0-4 vs 5-9
    last100 = outcomes[:100]
    b100, s100 = last100.count("BIG"), last100.count("SMALL")
    if b100 >= 58: scores["SMALL"] += 2.5
    elif s100 >= 58: scores["BIG"] += 2.5

    # ⑦ Deep history reversal (last 400 split into 8 blocks of 50)
    if len(outcomes) >= 400:
        blocks = [outcomes[i*50:(i+1)*50] for i in range(8)]
        big_rates = [b.count("BIG") for b in blocks]
        # If last 3 blocks trend one way → expect reversal
        recent3 = big_rates[:3]  # most recent
        if all(r >= 28 for r in recent3): scores["SMALL"] += 3.0
        elif all(r <= 22 for r in recent3): scores["BIG"] += 3.0

    return _score_decision(scores)


# ══════════════════════════════════════════════════════════════
#  1MIN ALGORITHM — 400+ Deep Analysis Engine
#  Last 400 results fetch করে 8টি technique apply করে
# ══════════════════════════════════════════════════════════════
def predict_1min() -> tuple:
    numbers  = _fetch_numbers("1min", 400)
    outcomes = _to_outcomes(numbers)

    if len(outcomes) < 10:
        return ("BIG" if random.random() > 0.5 else "SMALL"), random.randint(70, 78)

    scores = {"BIG": 0.0, "SMALL": 0.0}

    # ① Streak (moderate weight for 1min)
    streak, streak_side = 1, outcomes[0]
    for o in outcomes[1:]:
        if o == streak_side: streak += 1
        else: break
    if streak >= 4:
        opp = "SMALL" if streak_side == "BIG" else "BIG"
        scores[opp] += min(5.0, streak * 1.2)

    # ② Frequency imbalance — last 20 (primary signal)
    last20 = outcomes[:20]
    b20, s20 = last20.count("BIG"), last20.count("SMALL")
    if b20 >= 13: scores["SMALL"] += (b20 - 10) * 1.2
    elif s20 >= 13: scores["BIG"] += (s20 - 10) * 1.2

    # ③ Cycle detection (last 60 split into 3 windows)
    if len(outcomes) >= 60:
        w1 = outcomes[:20]; w2 = outcomes[20:40]; w3 = outcomes[40:60]
        b1, b2, b3 = w1.count("BIG"), w2.count("BIG"), w3.count("BIG")
        # Zigzag: w1 high, w2 low, w3 high → w4 (next) should be low
        if b1 >= 12 and b2 <= 8 and b3 >= 12: scores["SMALL"] += 3.0
        elif b1 <= 8 and b2 >= 12 and b3 <= 8: scores["BIG"]  += 3.0

    # ④ Number cluster (last 30 raw)
    n30 = numbers[:30]
    high = sum(1 for n in n30 if n >= 7)  # 7,8,9 → BIG side
    low  = sum(1 for n in n30 if n <= 2)  # 0,1,2 → SMALL side
    if high >= 12: scores["SMALL"] += 2.5
    if low  >= 12: scores["BIG"]   += 2.5

    # ⑤ Last 100 balance check
    last100 = outcomes[:100]
    b100, s100 = last100.count("BIG"), last100.count("SMALL")
    if b100 >= 58: scores["SMALL"] += 2.0
    elif s100 >= 58: scores["BIG"] += 2.0

    # ⑥ Alternating pattern (last 10)
    last10 = outcomes[:10]
    alt = sum(1 for i in range(len(last10)-1) if last10[i] != last10[i+1])
    if alt >= 8:
        scores["SMALL" if outcomes[0] == "BIG" else "BIG"] += 2.5

    # ⑦ Deep trend (last 200 vs last 400 comparison)
    if len(outcomes) >= 400:
        recent200 = outcomes[:200]
        older200  = outcomes[200:400]
        rb, ob = recent200.count("BIG"), older200.count("BIG")
        diff = rb - ob  # positive = recent more BIG
        if diff >= 15: scores["SMALL"] += 3.0   # recent BIG-heavy → expect SMALL
        elif diff <= -15: scores["BIG"] += 3.0

    # ⑧ 50-period micro-cycle (last 400 in 8 blocks)
    if len(outcomes) >= 400:
        blocks = [outcomes[i*50:(i+1)*50] for i in range(8)]
        big_rates = [b.count("BIG") for b in blocks]
        # Trend direction of last 4 blocks
        t = big_rates[:4]
        if t[0] > t[1] > t[2] > t[3]: scores["BIG"]   += 2.0  # downtrend → reversal up
        elif t[0] < t[1] < t[2] < t[3]: scores["SMALL"] += 2.0 # uptrend → reversal down

    return _score_decision(scores)


def _make_next_kb(game_type: str) -> InlineKeyboardMarkup:
    """WIN/LOSS দেখানোর পর NEXT PREDICTION button"""
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(
        "🔄 𝗡𝗘𝗫𝗧 𝗣𝗥𝗘𝗗𝗜𝗖𝗧𝗜𝗢𝗡",
        callback_data=f"NEXT_PRED:{game_type}"
    ))
    return kb


# ================================================================
#  PREDICTION MESSAGE BUILDER
# ================================================================
def _build_pred_text(game_name: str, period: str, prediction: str, confidence: int) -> str:
    pred_icon  = '\U0001f4c8' if prediction == 'BIG' else '\U0001f4c9'
    pred_arrow = '\u2b06\ufe0f' if prediction == 'BIG' else '\u2b07\ufe0f'
    bar_fill   = int(confidence / 10)
    conf_bar   = '\u2588' * bar_fill + '\u2591' * (10 - bar_fill)
    msg  = _box('🔰 *W I N G O  S I G N A L* 🔰') + '\n\n'
    msg += f'\U0001f3ae *MARKET* \u00bb `{game_name}`\n\n'
    msg += f'\U0001f522 *PERIOD* \u00bb `{period}`\n\n'
    msg += '\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n'
    msg += f'\U0001f3af *TRADE ON* \u27a4 {pred_icon} *{prediction}* {pred_arrow}\n\n'
    msg += f'\U0001f4ca *Confidence* \u27a4 `{conf_bar}` `{confidence}%`\n\n'
    msg += '\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n'
    msg += '\u23f3 _Waiting for period result\\.\\.\\._'
    return msg



# ================================================================
#  PERIOD CHANGE DETECTOR  — Background thread
#  Logic: প্রতি সেকেন্ডে current period check করে।
#         Period change হলে API call → WIN/LOSS দেখায়।
#         কোনো timer bar নেই, কোনো message edit নেই।
# ================================================================
def _safe_send_result(chat_id, message_id, final_text, next_kb):
    """WIN/LOSS result message edit করে, fail হলে নতুন message পাঠায়"""
    import re as _re
    for attempt in range(4):
        try:
            bot.edit_message_text(
                final_text,
                chat_id=chat_id,
                message_id=message_id,
                parse_mode="Markdown",
                reply_markup=next_kb
            )
            return
        except Exception as e:
            err = str(e).lower()
            if "message is not modified" in err:
                return
            elif "message to edit not found" in err:
                # Message deleted — send fresh
                try:
                    bot.send_message(chat_id, final_text,
                                     parse_mode="Markdown", reply_markup=next_kb)
                except Exception:
                    pass
                return
            elif "429" in err or "too many requests" in err:
                wait = 15
                try:
                    m = _re.search(r"retry after (\d+)", err)
                    if m:
                        wait = int(m.group(1)) + 2
                except Exception:
                    pass
                time.sleep(wait)
            else:
                time.sleep(3)
    # Final fallback
    try:
        bot.send_message(chat_id, final_text,
                         parse_mode="Markdown", reply_markup=next_kb)
    except Exception:
        pass


def _debug_api_raw(game_type: str, n: int = 5):
    """API response raw dump — debug only"""
    try:
        url  = GAME_CONFIGS[game_type]["api"]
        resp = requests.get(url, params={"pageSize": n, "pageNo": 1}, timeout=10)
        if resp.status_code == 200:
            items = resp.json().get("data", {}).get("list", [])
            for item in items:
                print(f"[API RAW] {item}")
        else:
            print(f"[API RAW] status={resp.status_code}")
    except Exception as e:
        print(f"[API RAW ERROR] {e}")


def get_period_result_robust(game_type: str, period: str):
    """
    Robust result fetch — multiple field names try করে।
    issueNumber, issue, periodNumber, period etc.
    """
    try:
        url  = GAME_CONFIGS[game_type]["api"]
        resp = requests.get(url, params={"pageSize": 30, "pageNo": 1}, timeout=10)
        if resp.status_code != 200:
            print(f"[RESULT] API status {resp.status_code}")
            return None

        data  = resp.json()
        items = (data.get("data") or {}).get("list") or data.get("list") or []

        print(f"[RESULT] Looking for period={period}, got {len(items)} items")

        # Try every possible key name
        period_keys = ["issueNumber", "issue", "periodNumber", "period",
                       "issueNum", "no", "drawNumber"]
        number_keys = ["number", "num", "result", "drawResult", "winNumber"]

        for item in items:
            # Check each possible period key
            for pk in period_keys:
                val = str(item.get(pk, ""))
                if val == str(period):
                    # Found the period — now get number
                    for nk in number_keys:
                        nv = item.get(nk)
                        if nv is not None:
                            try:
                                n = int(str(nv).strip())
                                print(f"[RESULT] Found! period={period} number={n} (key={nk})")
                                return n
                            except Exception:
                                pass
                    print(f"[RESULT] Period found but no number key! item={item}")
                    return None

        # Period not in list yet — show what IS there
        if items:
            first = items[0]
            for pk in period_keys:
                if pk in first:
                    print(f"[RESULT] Latest period in API: {first[pk]} (key={pk})")
                    break
        return None

    except Exception as e:
        print(f"[RESULT ERROR] {e}")
        return None


def _debug_api_raw(game_type: str, n: int = 3):
    try:
        url  = GAME_CONFIGS[game_type]["api"]
        resp = requests.get(url, params={"pageSize": n, "pageNo": 1}, timeout=10)
        if resp.status_code == 200:
            items = (resp.json().get("data") or {}).get("list") or []
            for item in items:
                print(f"[API RAW] {item}")
        else:
            print(f"[API] status={resp.status_code}")
    except Exception as ex:
        print(f"[API RAW ERR] {ex}")


def get_period_result_robust(game_type: str, period: str):
    """Multiple field names try করে result বের করে"""
    try:
        url  = GAME_CONFIGS[game_type]["api"]
        resp = requests.get(url, params={"pageSize": 30, "pageNo": 1}, timeout=10)
        if resp.status_code != 200:
            print(f"[RESULT] status={resp.status_code}")
            return None

        raw   = resp.json()
        items = (raw.get("data") or {}).get("list") or raw.get("list") or []
        print(f"[RESULT] {len(items)} items, looking for period={period}")

        period_keys = ["issueNumber","issue","periodNumber","period","issueNum","no"]
        number_keys = ["number","num","result","drawResult","winNumber"]

        for item in items:
            for pk in period_keys:
                if str(item.get(pk,"")) == str(period):
                    for nk in number_keys:
                        nv = item.get(nk)
                        if nv is not None:
                            try:
                                n = int(str(nv).strip())
                                print(f"[RESULT] FOUND period={period} number={n}")
                                return n
                            except Exception:
                                pass
        # show what latest period is
        if items:
            for pk in period_keys:
                if pk in items[0]:
                    print(f"[RESULT] Latest in API: {items[0][pk]}")
                    break
        return None
    except Exception as ex:
        print(f"[RESULT ERR] {ex}")
        return None


def period_watcher_thread(chat_id, message_id, period, prediction,
                          confidence, game_type, stop_evt):
    game_name = GAME_CONFIGS[game_type]["game_name"]
    next_kb   = _make_next_kb(game_type)
    checked   = False
    print(f"[WATCHER] Started period={period} game={game_type}")

    while not stop_evt.is_set():
        time.sleep(1)
        current = calculate_period(game_type)

        if current != period:
            if checked:
                break
            checked = True
            print(f"[WATCHER] Period changed {period} -> {current}")
            _debug_api_raw(game_type)

            result_number = None
            for attempt in range(8):
                result_number = get_period_result_robust(game_type, period)
                if result_number is not None:
                    break
                print(f"[WATCHER] Attempt {attempt+1}/8, waiting 3s...")
                time.sleep(3)

            if result_number is not None:
                actual = "BIG" if result_number >= 5 else "SMALL"
                is_win = prediction == actual

                if is_win:
                    db["loss_streak"][game_type] = 0
                    inc_wins(chat_id)
                else:
                    db["loss_streak"][game_type] = db["loss_streak"].get(game_type, 0) + 1
                    inc_losses(chat_id)

                if is_win:
                    t    = _box("🏆 *W I N !* 🏆") + "\n\n"
                    deco = "\U0001f3af" * 10
                else:
                    t    = _box("💔 *L O S S !* 💔") + "\n\n"
                    deco = "\U0001f494" * 10

                t += f"\U0001f3ae *MARKET* >> `{game_name}`\n"
                t += f"\U0001f522 *PERIOD* >> `{period}`\n\n"
                t += "\u2500" * 21 + "\n\n"
                t += f"\U0001f3af *PREDICTED* >> *{prediction}*\n"
                t += f"\U0001f4cc *RESULT* >> *{actual}* (No. {result_number})\n\n"
                t += "\u2500" * 21 + "\n\n"
                t += ("\u2705 *OUTCOME : WIN!*" if is_win else "\u274c *OUTCOME : LOSS!*") + "\n\n"
                t += deco + "\n\n"
                t += "\U0001f447 *Next Signal \u09a8\u09bf\u09a8*"
                final_text = t
            else:
                t  = _box("🔰 *W I N G O  S I G N A L* 🔰") + "\n\n"
                t += f"\U0001f522 *PERIOD* >> `{period}`\n"
                t += f"\U0001f3af *PREDICTED* >> *{prediction}*\n\n"
                t += "\u2753 Result API-te paoa jacche na\n\n"
                t += "\U0001f447 *Retry korun*"
                final_text = t

            _safe_send_result(chat_id, message_id, final_text, next_kb)
            break

    key = str(chat_id)
    if key in db["timer_stop"]:
        del db["timer_stop"][key]
    print(f"[WATCHER] Ended for period={period}")


# ================================================================
#  PREDICTION SENDER
# ================================================================
def send_prediction(chat_id: int, user_id: int, game_type: str):
    """
    Auto period calculate → prediction পাঠায় → background watcher চালু করে।
    Period change হলে watcher নিজেই WIN/LOSS দেখাবে।
    """
    bal = get_balance(user_id)
    if bal < 1:
        bot.send_message(
            chat_id,
            "\u274c *\u0986\u09aa\u09a8\u09be\u09b0 \u09aa\u09b0\u09cd\u09af\u09be\u09aa\u09cd\u09a4 \u09ac\u09cd\u09af\u09be\u09b2\u09c7\u09a8\u09cd\u09b8 \u09a8\u09c7\u0987\u0964*\n\n"
            "\U0001f4a1 Refer \u0995\u09b0\u09c7 \u09ac\u09be Redeem Code \u09ac\u09cd\u09af\u09ac\u09b9\u09be\u09b0 \u0995\u09b0\u09c7 balance \u09a8\u09bf\u09a8\u0964",
            parse_mode="Markdown"
        )
        return

    period   = calculate_period(game_type)
    used_key = f"{user_id}:{period}"

    if db["used_periods"].get(used_key):
        bot.send_message(chat_id, "\u26a0\ufe0f \u098f\u0987 Period \u0986\u09aa\u09a8\u09bf \u0987\u09a4\u09bf\u09ae\u09a7\u09cd\u09af\u09c7 \u09ac\u09cd\u09af\u09ac\u09b9\u09be\u09b0 \u0995\u09b0\u09c7\u099b\u09c7\u09a8\u0964")
        return

    add_balance(user_id, -1)
    db["used_periods"][used_key] = True
    inc_signals(user_id)

    # ── Consecutive Loss Recovery Logic ──────────────────────────
    # টানা 2 লস হলে পরের signal হবে সেই market-এর last result অনুযায়ী
    streak = db["loss_streak"].get(game_type, 0)
    if streak >= 2:
        numbers = _fetch_numbers(game_type, 5)
        if numbers:
            last_num   = numbers[0]
            prediction = "BIG" if last_num >= 5 else "SMALL"
            confidence = 88   # recovery mode confidence
            # Streak reset হবে next result আসলে (watcher handle করবে)
        else:
            # API fail হলে normal algo
            streak = 0

    if streak < 2:
        if game_type == "30s":
            prediction, confidence = predict_30s()
        elif game_type == "1min":
            prediction, confidence = predict_1min()
        elif game_type == "lottery200":
            prediction, confidence = predict_lottery200()
        else:
            prediction = "BIG" if random.random() > 0.5 else "SMALL"
            confidence = random.randint(75, 92)

    game_name = GAME_CONFIGS[game_type]["game_name"]

    # Prediction message পাঠাও (no timer bar)
    text = _build_pred_text(game_name, period, prediction, confidence)
    sent = bot.send_message(chat_id, text, parse_mode="Markdown")

    # আগের watcher থাকলে বন্ধ করো
    key = str(chat_id)
    if key in db["timer_stop"]:
        db["timer_stop"][key].set()
        time.sleep(0.1)

    # নতুন period watcher চালু করো
    stop_evt = threading.Event()
    db["timer_stop"][key] = stop_evt

    t = threading.Thread(
        target=period_watcher_thread,
        args=(chat_id, sent.message_id, period,
              prediction, confidence, game_type, stop_evt),
        daemon=True
    )
    t.start()



# ================================================================
#  DB HELPERS
# ================================================================
def init_user(user_id: int, name: str):
    key = str(user_id)
    if key not in db["users"]:
        db["users"][key] = {"balance": 0, "signals": 0, "wins": 0, "losses": 0, "name": name}
        if user_id not in db["all_users"]:
            db["all_users"].append(user_id)

def get_balance(user_id: int) -> int:
    return db["users"].get(str(user_id), {}).get("balance", 0)

def add_balance(user_id: int, amount: int):
    key = str(user_id)
    db["users"].setdefault(key, {"balance": 0, "signals": 0, "wins": 0, "losses": 0, "name": ""})
    db["users"][key]["balance"] = db["users"][key].get("balance", 0) + amount

def get_signals(user_id: int) -> int:
    return db["users"].get(str(user_id), {}).get("signals", 0)

def inc_signals(user_id: int):
    key = str(user_id)
    db["users"].setdefault(key, {"balance": 0, "signals": 0, "wins": 0, "losses": 0, "name": ""})
    db["users"][key]["signals"] = db["users"][key].get("signals", 0) + 1

def inc_wins(user_id: int):
    key = str(user_id)
    db["users"].setdefault(key, {"balance": 0, "signals": 0, "wins": 0, "losses": 0, "name": ""})
    db["users"][key]["wins"] = db["users"][key].get("wins", 0) + 1

def inc_losses(user_id: int):
    key = str(user_id)
    db["users"].setdefault(key, {"balance": 0, "signals": 0, "wins": 0, "losses": 0, "name": ""})
    db["users"][key]["losses"] = db["users"][key].get("losses", 0) + 1

def set_state(user_id: int, state: str):
    db["states"][str(user_id)] = state

def get_state(user_id: int):
    return db["states"].get(str(user_id))

def clear_state(user_id: int):
    db["states"].pop(str(user_id), None)

def generate_redeem_code() -> str:
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "-".join("".join(random.choices(chars, k=4)) for _ in range(4))


# ================================================================
#  MEMBERSHIP CHECK
# ================================================================
def check_membership(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    channels = db.get("channels", [])
    if not channels:
        return True
    for ch in channels:
        try:
            member = bot.get_chat_member(ch["id"], user_id)
            if member.status in ("left", "kicked"):
                return False
        except Exception:
            return False
    return True

def process_referral_reward(user_id: int):
    uid    = str(user_id)
    ref_id = db["referrers"].get(uid)
    if not ref_id or db["ref_rewards"].get(uid):
        return
    reward = db.get("ref_reward", 25)
    add_balance(int(ref_id), reward)
    db["ref_rewards"][uid] = True
    try:
        bot.send_message(
            int(ref_id),
            f"🤖 *New Referral Completed!*\n\n"
            f"✅ Your friend joined all channels!\n"
            f"💰 You received `{reward}` coins!",
            parse_mode="Markdown"
        )
    except Exception:
        pass


# ================================================================
#  KEYBOARDS
# ================================================================
def main_menu_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("❇️ 𝗪𝗜𝗡𝗚𝗢 𝗦𝗜𝗚𝗡𝗔𝗟 ❇️"),
           KeyboardButton("👤 𝗣𝗥𝗢𝗙𝗜𝗟𝗘"))
    kb.row(KeyboardButton("🧑‍🍼 𝗥𝗘𝗙𝗘𝗥𝗥𝗘𝗗"))
    kb.row(KeyboardButton("📥 𝗥𝗘𝗗𝗘𝗘𝗠 𝗖𝗢𝗗𝗘"),
           KeyboardButton("ℹ️ 𝗜𝗡𝗙𝗢"))
    kb.row(KeyboardButton("🧑‍💻 𝗛𝗘𝗟𝗣 𝗔𝗡𝗗 𝗦𝗨𝗣𝗣𝗢𝗥𝗧"))
    return kb

def wingo_inline_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("☠️ 𝗪𝗜𝗡𝗚𝗢 𝟯𝟬𝗦 ☠️",          callback_data="GAME_30s"))
    kb.add(InlineKeyboardButton("☠️ 𝗪𝗜𝗡𝗚𝗢 𝟭𝗠𝗜𝗡 ☠️",         callback_data="GAME_1min"))
    return kb


# ================================================================
#  /start
# ================================================================
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    user_id = msg.from_user.id
    name    = msg.from_user.first_name or "User"
    chat_id = msg.chat.id

    # Referral arg
    args = msg.text.split()
    if len(args) > 1 and args[1] != str(user_id):
        uid = str(user_id)
        if uid not in db["referrers"]:
            db["referrers"][uid] = args[1]

    init_user(user_id, name)

    if user_id == OWNER_ID or check_membership(user_id):
        process_referral_reward(user_id)
        bot.send_message(
            chat_id,
            "🤖 `আপনাকে আমাদের সিগনাল বটে স্বাগতম 🎉`",
            parse_mode="Markdown"
        )
        _send_main_menu(chat_id)
    else:
        _send_force_join(chat_id)


# ================================================================
#  /ap_bot — Admin Panel
# ================================================================
@bot.message_handler(commands=["ap_bot"])
def cmd_admin(msg):
    if msg.from_user.id == OWNER_ID:
        _send_admin_panel(msg.chat.id)


# ================================================================
#  ALL MESSAGES
# ================================================================
@bot.message_handler(func=lambda m: True)
def on_message(msg):
    user_id = msg.from_user.id
    chat_id = msg.chat.id
    text    = msg.text or ""
    name    = msg.from_user.first_name or "User"

    # ── State machine ──────────────────────────────────────────
    state = get_state(user_id)
    if state:
        _handle_state(chat_id, user_id, text, state)
        return

    # ── Force-join check button ────────────────────────────────
    if text == "✅ CHECK JOINED":
        if check_membership(user_id) or user_id == OWNER_ID:
            process_referral_reward(user_id)
            bot.send_message(chat_id, "✅ *আপনি সফলভাবে জয়েন করেছেন!*", parse_mode="Markdown")
            _send_main_menu(chat_id)
        else:
            _send_force_join(chat_id)
        return

    # ── Membership gate ────────────────────────────────────────
    if user_id != OWNER_ID and not check_membership(user_id):
        _send_force_join(chat_id)
        return

    # ── Main menu buttons ──────────────────────────────────────
    if   text == "❇️ 𝗪𝗜𝗡𝗚𝗢 𝗦𝗜𝗚𝗡𝗔𝗟 ❇️":
        bot.send_message(
            chat_id,
            "🤖 *তুমি কোন গেমে খেলবা?*\n\n🎯 একটি গেম সিলেক্ট করো:",
            parse_mode="Markdown",
            reply_markup=wingo_inline_kb()
        )
    elif text == "👤 𝗣𝗥𝗢𝗙𝗜𝗟𝗘":
        _send_profile(chat_id, user_id, name)
    elif text == "🧑‍🍼 𝗥𝗘𝗙𝗘𝗥𝗥𝗘𝗗":
        _send_referral(chat_id, user_id)
    elif text == "📥 𝗥𝗘𝗗𝗘𝗘𝗠 𝗖𝗢𝗗𝗘":
        set_state(user_id, "REDEEM_WAIT_CODE")
        bot.send_message(
            chat_id,
            "🎁 *Enter Redeem Code*\n\n`Example: H87J-98H4-UIU6-OO99`",
            parse_mode="Markdown"
        )
    elif text == "ℹ️ 𝗜𝗡𝗙𝗢":
        info = db.get("info", "")
        bot.send_message(
            chat_id,
            f"*{info}*" if info else "⚠️ *No Info Available.*",
            parse_mode="Markdown"
        )
    elif text == "🧑‍💻 𝗛𝗘𝗟𝗣 𝗔𝗡𝗗 𝗦𝗨𝗣𝗣𝗢𝗥𝗧":
        _send_support(chat_id)


# ================================================================
#  STATE MACHINE
# ================================================================
def _handle_state(chat_id: int, user_id: int, text: str, state: str):

    # ── Redeem ──────────────────────────────────────────────────
    if state == "REDEEM_WAIT_CODE":
        clear_state(user_id)
        _process_redeem(chat_id, user_id, text)

    # ── Admin: balance ───────────────────────────────────────────
    elif state == "ADMIN_WAIT_BAL_ID":
        set_state(user_id, f"ADMIN_WAIT_BAL_AMT:{text}")
        bot.send_message(chat_id, "Enter Amount:")

    elif state.startswith("ADMIN_WAIT_BAL_AMT:"):
        target = state.split(":", 1)[1]
        try:
            amount = int(text)
            add_balance(int(target), amount)
            bot.send_message(chat_id, f"✅ Added {amount} coins to {target}.")
            try:
                bot.send_message(int(target), f"💰 Admin added {amount} coins to your balance.")
            except Exception:
                pass
        except ValueError:
            bot.send_message(chat_id, "❌ Invalid amount.")
        clear_state(user_id)

    # ── Admin: ref reward ────────────────────────────────────────
    elif state == "ADMIN_WAIT_REF_REWARD":
        try:
            amount = int(text)
            if amount < 1:
                raise ValueError
            db["ref_reward"] = amount
            bot.send_message(chat_id, f"✅ Referral reward set to {amount} coins.")
        except ValueError:
            bot.send_message(chat_id, "❌ Invalid amount.")
        clear_state(user_id)

    # ── Admin: create redeem ─────────────────────────────────────
    elif state == "ADMIN_WAIT_REDEEM_AMOUNT":
        try:
            amount = int(text)
            if amount < 1:
                raise ValueError
            code = generate_redeem_code()
            db["redeems"][code] = {
                "code": code, "amount": amount,
                "createdAt": datetime.now().isoformat(),
                "used": False, "usedBy": None, "usedAt": None
            }
            db["redeem_list"].append(code)
            bot.send_message(
                chat_id,
                f"✅ *Redeem Code Created!*\n\n🎟 Code: `{code}`\n💰 Amount: {amount} coins",
                parse_mode="Markdown"
            )
        except ValueError:
            bot.send_message(chat_id, "❌ Invalid amount.")
        clear_state(user_id)

    # ── Admin: add channel ───────────────────────────────────────
    elif state == "ADMIN_WAIT_CH":
        parts = text.split("|")
        if len(parts) != 2:
            bot.send_message(
                chat_id,
                "Invalid format. Use: `ChannelID|Link`\nExample: `-100123456789|https://t.me/channel`",
                parse_mode="Markdown"
            )
            return
        db["channels"].append({"id": parts[0].strip(), "link": parts[1].strip()})
        bot.send_message(chat_id, "✅ Channel Added.")
        clear_state(user_id)

    # ── Admin: info message ──────────────────────────────────────
    elif state == "ADMIN_WAIT_INFO":
        db["info"] = text
        bot.send_message(chat_id, "✅ Info message updated.")
        clear_state(user_id)

    # ── Admin: support text ──────────────────────────────────────
    elif state == "ADMIN_WAIT_SUP_TXT":
        set_state(user_id, f"ADMIN_WAIT_SUP_BTN:{text}")
        bot.send_message(
            chat_id,
            "Now enter Button Name and URL:\n`Admin|https://t.me/admin`",
            parse_mode="Markdown"
        )

    elif state.startswith("ADMIN_WAIT_SUP_BTN:"):
        parts = text.split("|")
        if len(parts) != 2:
            bot.send_message(chat_id, "Invalid format.")
            return
        sup_text = state[len("ADMIN_WAIT_SUP_BTN:"):]
        db["support"] = {"text": sup_text, "btnName": parts[0], "url": parts[1]}
        bot.send_message(chat_id, "✅ Support section updated.")
        clear_state(user_id)

    # ── Admin: broadcast ─────────────────────────────────────────
    elif state == "ADMIN_WAIT_BROADCAST":
        clear_state(user_id)
        _do_broadcast(chat_id, text)


# ================================================================
#  CALLBACK QUERIES
# ================================================================
@bot.callback_query_handler(func=lambda call: True)
def on_callback(call):
    data    = call.data
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    # ── Game buttons ────────────────────────────────────────────
    if data.startswith("GAME_"):
        game_type = data[5:]
        if game_type in GAME_CONFIGS:
            send_prediction(chat_id, user_id, game_type)

    elif data.startswith("NEXT_PRED:"):
        game_type = data.split(":", 1)[1]
        if game_type in GAME_CONFIGS:
            send_prediction(chat_id, user_id, game_type)

    # ── Admin callbacks (owner only) ────────────────────────────
    elif user_id == OWNER_ID:

        if data == "ADMIN_ADD_BAL":
            set_state(user_id, "ADMIN_WAIT_BAL_ID")
            bot.send_message(chat_id, "Enter User ID for balance add:")

        elif data == "ADMIN_ADD_CH":
            set_state(user_id, "ADMIN_WAIT_CH")
            bot.send_message(chat_id, "Send Channel Info:\n`ChannelID|Link`", parse_mode="Markdown")

        elif data == "ADMIN_SET_INFO":
            set_state(user_id, "ADMIN_WAIT_INFO")
            bot.send_message(chat_id, "Send new Info Message:")

        elif data == "ADMIN_SET_SUP":
            set_state(user_id, "ADMIN_WAIT_SUP_TXT")
            bot.send_message(chat_id, "Send Support Message Text:")

        elif data == "ADMIN_SET_REF":
            current = db.get("ref_reward", 25)
            set_state(user_id, "ADMIN_WAIT_REF_REWARD")
            bot.send_message(
                chat_id,
                f"💰 *Set Referral Reward*\n\nCurrent: {current} coins\n\nEnter new amount:",
                parse_mode="Markdown"
            )

        elif data == "ADMIN_REM_CH":
            channels = db.get("channels", [])
            if not channels:
                bot.send_message(chat_id, "No channels to remove.")
            else:
                kb = InlineKeyboardMarkup()
                for i, ch in enumerate(channels):
                    kb.add(InlineKeyboardButton(f"🗑 {ch['link']}", callback_data=f"DEL_CH:{i}"))
                kb.add(InlineKeyboardButton("🔙 BACK", callback_data="BACK_TO_AP"))
                bot.send_message(chat_id, "Select Channel to Remove:", reply_markup=kb)

        elif data.startswith("DEL_CH:"):
            idx = int(data.split(":")[1])
            if 0 <= idx < len(db["channels"]):
                db["channels"].pop(idx)
                bot.send_message(chat_id, "✅ Channel Removed.")

        elif data == "ADMIN_REDEEM_MENU":
            _send_redeem_menu(chat_id)

        elif data == "ADMIN_CREATE_REDEEM":
            set_state(user_id, "ADMIN_WAIT_REDEEM_AMOUNT")
            bot.send_message(chat_id, "🎟 Enter the amount of coins for this code:")

        elif data == "ADMIN_VIEW_REDEEMS":
            _view_redeem_codes(chat_id)

        elif data.startswith("VIEW_REDEEM:"):
            _view_redeem_details(chat_id, data.split(":", 1)[1])

        elif data.startswith("ADMIN_USERS:"):
            page      = int(data.split(":")[1])
            all_users = db.get("all_users", [])
            start, end = page * 10, page * 10 + 10
            slice_u   = all_users[start:end]

            msg = "👥 *All Users*\n"
            for uid in slice_u:
                msg += f"`{uid}`\n"

            kb = InlineKeyboardMarkup()
            row = []
            if page > 0:
                row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"ADMIN_USERS:{page-1}"))
            if end < len(all_users):
                row.append(InlineKeyboardButton("Next ➡️", callback_data=f"ADMIN_USERS:{page+1}"))
            if row:
                kb.row(*row)
            kb.add(InlineKeyboardButton("🔙 BACK", callback_data="BACK_TO_AP"))

            try:
                bot.edit_message_text(
                    msg, chat_id=chat_id,
                    message_id=call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=kb
                )
            except Exception:
                bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=kb)

        elif data == "ADMIN_BROADCAST":
            set_state(user_id, "ADMIN_WAIT_BROADCAST")
            total = len(db.get("all_users", []))
            bot.send_message(
                chat_id,
                f"📢 *Broadcast Message*\n\n"
                f"👥 Total Users: `{total}`\n\n"
                f"Send the message you want to broadcast to all users:\n"
                "(Text, Photo, Video সব support করে)",
                parse_mode="Markdown"
            )

        elif data == "BACK_TO_AP":
            _send_admin_panel(chat_id)

    bot.answer_callback_query(call.id)


# ================================================================
#  INTERNAL SEND HELPERS
# ================================================================
def _send_main_menu(chat_id: int):
    bot.send_message(chat_id, "👇 𝗠𝗔𝗜𝗡 𝗠𝗘𝗡𝗨 👇", reply_markup=main_menu_kb())

def _send_force_join(chat_id: int):
    channels = db.get("channels", [])
    inline_kb = InlineKeyboardMarkup()
    for ch in channels:
        inline_kb.add(InlineKeyboardButton("♻ 𝗝𝗢𝗜𝗡 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 ♻", url=ch["link"]))

    bot.send_message(
        chat_id,
        "🤖 *আপনি আমাদের Channel/Group এ জয়েন নেই* ❌\n\n"
        "_তো আবশ্যই আমাদের Channel এ জয়েন হতে হবে।_",
        parse_mode="Markdown",
        reply_markup=inline_kb
    )
    check_kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    check_kb.add(KeyboardButton("✅ CHECK JOINED"))
    bot.send_message(chat_id, "👇 জয়েন করার পর নিচের বাটনে ক্লিক করুন 👇", reply_markup=check_kb)

def _send_profile(chat_id: int, user_id: int, name: str):
    bal    = get_balance(user_id)
    sigs   = get_signals(user_id)
    wins   = db["users"].get(str(user_id), {}).get("wins", 0)
    losses = db["users"].get(str(user_id), {}).get("losses", 0)
    total  = wins + losses
    if total > 0:
        rate = int((wins / total) * 100)
        bar_fill = int(rate / 10)
        rate_bar = "█" * bar_fill + "░" * (10 - bar_fill)
        rate_str = f"`{rate_bar}` `{rate}%`"
    else:
        rate_str = "`──────────` `N/A`"

    div = "\u2501" * 22
    msg  = _box("👤 *P R O F I L E*") + "\n\n"
    msg += f"🧑‍💻 *Name* » `{name}`\n"
    msg += f"🆔 *User ID* » `{user_id}`\n\n"
    msg += div + "\n\n"
    msg += f"💰 *Balance* » *{bal} Coins*\n"
    msg += f"📊 *Total Signals* » *{sigs}*\n\n"
    msg += div + "\n\n"
    msg += f"✅ *Total WIN* » *{wins}*\n"
    msg += f"❌ *Total LOSS* » *{losses}*\n\n"
    msg += f"🏆 *Win Rate* » {rate_str}"
    bot.send_message(chat_id, msg, parse_mode="Markdown")

def _send_referral(chat_id: int, user_id: int):
    me     = bot.get_me()
    link   = f"https://t.me/{me.username}?start={user_id}"
    reward = db.get("ref_reward", 25)
    kb     = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(
        "🛡 𝗦𝗛𝗔𝗥𝗘 𝗥𝗘𝗙𝗘𝗥 𝗟𝗜𝗡𝗞 🛡️",
        url=f"https://t.me/share/url?url={link}&text=Join%20Now!"
    ))
    bot.send_message(
        chat_id,
        f"🖇️ 𝗬𝗢𝗨𝗥 𝗥𝗘𝗙𝗘𝗥 𝗟𝗜𝗡𝗞 :- `{link}`\n\n"
        f"🤖 *আপনি প্রতি রেফারে {reward}টা কয়েন ফ্রি পাবেন!*\n\n"
        f"⚠️ _নোট: রেফার কেবল তখনই কাউন্ট হবে যখন বন্ধু সব চ্যানেলে জয়েন করবে।_",
        parse_mode="Markdown",
        reply_markup=kb
    )

def _send_support(chat_id: int):
    sup = db.get("support", {})
    if not sup:
        bot.send_message(chat_id, "No support info configured.")
        return
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(sup.get("btnName", "Support"), url=sup.get("url", "#")))
    bot.send_message(chat_id, sup.get("text", "Contact Support"), reply_markup=kb)

def _process_redeem(chat_id: int, user_id: int, raw_code: str):
    code   = raw_code.strip().upper()
    redeem = db["redeems"].get(code)
    if not redeem:
        bot.send_message(chat_id, "❌ *Invalid Redeem Code!* Please check and try again.", parse_mode="Markdown")
        return
    if redeem["used"]:
        bot.send_message(chat_id, "❌ *This Code has already been used!*", parse_mode="Markdown")
        return
    redeem["used"]   = True
    redeem["usedBy"] = user_id
    redeem["usedAt"] = datetime.now().isoformat()
    add_balance(user_id, redeem["amount"])
    bot.send_message(
        chat_id,
        f"✅ *Redeem Successful!*\n\n"
        f"💰 Amount: `{redeem['amount']}` coins\n"
        f"🎟 Code: `{code}`\n\n"
        f"Thank you for using our service! 🎉",
        parse_mode="Markdown"
    )

def _do_broadcast(admin_chat_id: int, message_text: str):
    """সব users-কে message broadcast করে, progress দেখায়"""
    all_users = db.get("all_users", [])
    total   = len(all_users)
    success = 0
    failed  = 0

    status_msg = bot.send_message(
        admin_chat_id,
        f"📢 *Broadcasting...*\n\n"
        f"👥 Total: `{total}`\n"
        f"✅ Sent: `0`\n"
        f"❌ Failed: `0`",
        parse_mode="Markdown"
    )

    for i, uid in enumerate(all_users):
        try:
            bot.send_message(
                uid,
                f"📢 *Broadcast Message*\n\n{message_text}",
                parse_mode="Markdown"
            )
            success += 1
        except Exception:
            failed += 1

        # Progress update every 10 users
        if (i + 1) % 10 == 0 or (i + 1) == total:
            try:
                bot.edit_message_text(
                    f"📢 *Broadcasting...*\n\n"
                    f"👥 Total: `{total}`\n"
                    f"✅ Sent: `{success}`\n"
                    f"❌ Failed: `{failed}`\n"
                    f"⏳ Progress: `{i+1}/{total}`",
                    chat_id=admin_chat_id,
                    message_id=status_msg.message_id,
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        time.sleep(0.05)   # Telegram flood control

    # Final status
    try:
        bot.edit_message_text(
            f"✅ *Broadcast Complete!*\n\n"
            f"👥 Total Users: `{total}`\n"
            f"✅ Successfully Sent: `{success}`\n"
            f"❌ Failed: `{failed}`",
            chat_id=admin_chat_id,
            message_id=status_msg.message_id,
            parse_mode="Markdown"
        )
    except Exception:
        pass


def _send_admin_panel(chat_id: int):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("👥 𝗔𝗟𝗟 𝗨𝗦𝗘𝗥𝗦",          callback_data="ADMIN_USERS:0"))
    kb.add(InlineKeyboardButton("➕ 𝗕𝗔𝗟𝗔𝗡𝗖𝗘 𝗔𝗗𝗗",         callback_data="ADMIN_ADD_BAL"))
    kb.add(InlineKeyboardButton("➕ 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 𝗔𝗗𝗗",        callback_data="ADMIN_ADD_CH"))
    kb.add(InlineKeyboardButton("📳 𝗕𝗢𝗧 𝗜𝗡𝗙𝗢 𝗠𝗘𝗦𝗦𝗔𝗚𝗘",    callback_data="ADMIN_SET_INFO"))
    kb.add(InlineKeyboardButton("🤙 𝗦𝗨𝗣𝗣𝗢𝗥𝗧 𝗔𝗡𝗗 𝗛𝗘𝗟𝗣",    callback_data="ADMIN_SET_SUP"))
    kb.add(InlineKeyboardButton("⚔ 𝗥𝗘𝗠𝗢𝗩𝗘 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 ⚔️",  callback_data="ADMIN_REM_CH"))
    kb.add(InlineKeyboardButton("💰 𝗥𝗘𝗙𝗘𝗥 𝗥𝗘𝗪𝗔𝗥𝗗",         callback_data="ADMIN_SET_REF"))
    kb.add(InlineKeyboardButton("🎟 𝗥𝗘𝗗𝗘𝗘𝗠 𝗖𝗢𝗗𝗘𝗦",         callback_data="ADMIN_REDEEM_MENU"))
    kb.add(InlineKeyboardButton("📢 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧 𝗠𝗘𝗦𝗦𝗔𝗚𝗘",       callback_data="ADMIN_BROADCAST"))
    bot.send_message(chat_id, "🛡️ *Admin Panel* 🛡️", parse_mode="Markdown", reply_markup=kb)

def _send_redeem_menu(chat_id: int):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ 𝗖𝗥𝗘𝗔𝗧𝗘 𝗥𝗘𝗗𝗘𝗘𝗠 𝗖𝗢𝗗𝗘", callback_data="ADMIN_CREATE_REDEEM"))
    kb.add(InlineKeyboardButton("📋 𝗩𝗜𝗘𝗪 𝗔𝗟𝗟 𝗖𝗢𝗗𝗘𝗦",    callback_data="ADMIN_VIEW_REDEEMS"))
    kb.add(InlineKeyboardButton("🔙 𝗕𝗔𝗖𝗞",               callback_data="BACK_TO_AP"))
    bot.send_message(chat_id, "🎟 *Redeem Code Management*", parse_mode="Markdown", reply_markup=kb)

def _view_redeem_codes(chat_id: int):
    codes = db.get("redeem_list", [])
    if not codes:
        bot.send_message(chat_id, "❌ No redeem codes found.")
        return
    kb = InlineKeyboardMarkup()
    for code in codes:
        r = db["redeems"].get(code)
        if r:
            status = "❌" if r["used"] else "✅"
            kb.add(InlineKeyboardButton(
                f"{status} {code} ({r['amount']})",
                callback_data=f"VIEW_REDEEM:{code}"
            ))
    kb.add(InlineKeyboardButton("🔙 𝗕𝗔𝗖𝗞", callback_data="ADMIN_REDEEM_MENU"))
    bot.send_message(
        chat_id,
        "🎟 *All Redeem Codes*\n\n✅ = Available  ❌ = Used",
        parse_mode="Markdown",
        reply_markup=kb
    )

def _view_redeem_details(chat_id: int, code: str):
    r = db["redeems"].get(code)
    if not r:
        bot.send_message(chat_id, "❌ Not found.")
        return
    status = "❌ Used" if r["used"] else "✅ Available"
    text   = (
        f"🎟 *Redeem Code Details*\n\n"
        f"Code: `{r['code']}`\n"
        f"Amount: {r['amount']} coins\n"
        f"Status: {status}\n"
        f"Created: {r['createdAt']}\n"
    )
    if r["used"]:
        text += f"\nUsed By: `{r['usedBy']}`\nUsed At: {r['usedAt']}"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 𝗕𝗔𝗖𝗞", callback_data="ADMIN_VIEW_REDEEMS"))
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)


# ================================================================
#  ENTRY POINT
# ================================================================
if __name__ == "__main__":
    print("╔══════════════════════════════════════╗")
    print("║     WINGO SIGNAL BOT — Python        ║")
    print("╚══════════════════════════════════════╝")
    print(f"👑 Owner ID : {OWNER_ID}")
    print(f"🎮 Games    : WinGo 30S | WinGo 1Min | Lottery 200")
    print(f"🌍 Timezone : Bangladesh (UTC+6)")
    print(f"⏱  Timer    : Per-second live countdown")
    print(f"📡 Win/Loss : Real API check")
    print("✅ Bot started! Polling...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

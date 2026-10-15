import telebot
import threading
import time
import random
import requests
import json
import statistics
from datetime import datetime, timezone, timedelta
from telebot.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from collections import deque
import pickle
import os
import math

# 🧠 OWNER ID সেট করুন
OWNER_ID = "6753121703"

# 🧠 তোমার নতুন বট টোকেন বসাও নিচে 👇
bot = telebot.TeleBot("8910285497:AAHzHVsLXYm26RvBC9u9v12LkrDd6140Z9g")

# 🗂 ডাটা রাখার জন্য Dictionary
user_channels = {}
signal_threads = {}
signal_status = {}
user_register_links = {}
prediction_timers = {}
pending_prediction_messages = {}
prediction_history = {}

user_win_stickers = {}
user_loss_stickers = {}
user_season_start_stickers = {}
user_season_close_stickers = {}
user_promotional_messages = {}

DEFAULT_WIN_STICKER = "CAACAgUAAxkBAAIBIWZ4i-1dAAE3KXWk3X7L03zWn8H2bAACXxoAAo_FYFZxK2k1K4AAATYE"
DEFAULT_LOSS_STICKER = "CAACAgUAAxkBAAIBI2Z4jARAAW2N8Jv3JXf_0fHl0xJk9AACXxoAAo_FYFZxK2k1K4AAATYE"
DEFAULT_SEASON_START_STICKER = "CAACAgUAAxkBAAIBKWZ4jBNG8F_qjFpSKj11ZphW3Rq7AAJfGgACj8VgVnEraTUrgAABNAQ"
DEFAULT_SEASON_CLOSE_STICKER = "CAACAgUAAxkBAAIBK2Z4jByCAAER-3iK7hpFCUqPynNSOQACXxoAAo_FYFZxK2k1K4AAATYE"

market_manipulation_detected = {}
market_manipulation_reason = {}
market_manipulation_history = deque(maxlen=100)

CURRENT_API = 'https://api.bdg88zf.com/api/webapi/GetGameIssue'
HISTORY_API = 'https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json'

historical_data = deque(maxlen=2000)
data_collection_status = True
data_analysis_level = "BASIC"

DATA_FILE = "historical_data.pkl"


# 🆕 ফন্ট ফরম্যাটিং
def format_text(text, font_type):
    if font_type == "digit":
        digit_map = {'0':'𝟶','1':'𝟷','2':'𝟸','3':'𝟹','4':'𝟺',
                     '5':'𝟻','6':'𝟼','7':'𝟽','8':'𝟾','9':'𝟿'}
        return ''.join(digit_map.get(char, char) for char in str(text))
    elif font_type == "text":
        text_map = {'B':'𝙱','I':'𝙸','G':'𝙶','S':'𝚂','M':'𝙼','A':'𝙰','L':'𝙻'}
        return ''.join(text_map.get(char, char) for char in str(text).upper())
    return str(text)


def generate_new_prediction_message(period_number, prediction_type, number_prediction, manipulation_detected=False):
    period_font = format_text(period_number, "digit")
    if manipulation_detected:
        prediction_font = "⚠️ 𝗠𝗔𝗥𝗞𝗘𝗧 𝗠𝗔𝗡𝗜𝗣𝗨𝗟𝗔𝗧𝗜𝗢𝗡 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗 ⚠️"
    elif prediction_type == "BIG":
        if number_prediction and len(number_prediction) >= 2:
            prediction_font = f"{format_text('BIG', 'text')} ({number_prediction[0]},{number_prediction[1]})"
        else:
            prediction_font = format_text('BIG', 'text')
    elif prediction_type == "SMALL":
        if number_prediction and len(number_prediction) >= 2:
            prediction_font = f"{format_text('SMALL', 'text')} ({number_prediction[0]},{number_prediction[1]})"
        else:
            prediction_font = format_text('SMALL', 'text')
    else:
        prediction_font = "SKIP"

    message = f"""
📊 𝗦𝗛𝗔𝗡𝗧𝗢 𝗕𝗢𝗧 𝗦𝗜𝗚𝗡𝗔𝗟 (𝟮𝟰/𝟳) 📊

📆 𝙿𝙴𝚁𝙸𝙾𝙳 𝙸𝙳 : {period_font}

📊 𝙱𝚄𝚈 𝙾𝙽 : {prediction_font}
"""
    return message


def save_historical_data():
    try:
        with open(DATA_FILE, 'wb') as f:
            pickle.dump(list(historical_data), f)
        print(f"✅ Historical data saved: {len(historical_data)} records")
    except Exception as e:
        print(f"❌ Error saving data: {e}")


def load_historical_data():
    global historical_data
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'rb') as f:
                data = pickle.load(f)
                historical_data = deque(data, maxlen=2000)
            print(f"✅ Historical data loaded: {len(historical_data)} records")
            update_analysis_level()
    except Exception as e:
        print(f"❌ Error loading data: {e}")


def clear_historical_data():
    global historical_data, data_analysis_level
    try:
        historical_data.clear()
        data_analysis_level = "BASIC"
        if os.path.exists(DATA_FILE):
            os.remove(DATA_FILE)
        print("✅ Historical data cleared!")
        return True
    except Exception as e:
        print(f"❌ Error clearing data: {e}")
        return False


def update_analysis_level():
    global data_analysis_level
    data_count = len(historical_data)
    if data_count < 50:
        data_analysis_level = "BASIC"
    elif data_count < 100:
        data_analysis_level = "MEDIUM"
    elif data_count < 500:
        data_analysis_level = "ADVANCED"
    elif data_count < 1500:
        data_analysis_level = "EXPERT"
    else:
        data_analysis_level = "AI_MASTER"
    print(f"📊 Data Count: {data_count} | Analysis Level: {data_analysis_level}")


def add_to_historical_data(period, prediction, actual, result):
    data_entry = {
        'period': period,
        'prediction': prediction,
        'actual': actual,
        'result': result,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    historical_data.append(data_entry)
    update_analysis_level()
    if len(historical_data) % 10 == 0:
        save_historical_data()


load_historical_data()


# 🔥 মার্কেট মেনুপুলেশন ডিটেকশন
def detect_market_manipulation(numbers, analysis_level):
    if not numbers or len(numbers) < 15:
        return False, "Insufficient data", 0

    manipulation_score = 0
    manipulation_reasons = []

    frequency = {i: 0 for i in range(10)}
    for num in numbers[:30]:
        frequency[num] += 1

    max_freq = max(frequency.values())
    avg_freq = sum(frequency.values()) / 10

    if max_freq > avg_freq * 3:
        manipulation_score += 25
        manipulation_reasons.append(f"Abnormal frequency: max {max_freq}")

    trends = []
    for i in range(1, len(numbers[:20])):
        if numbers[i] > numbers[i-1]:
            trends.append("UP")
        elif numbers[i] < numbers[i-1]:
            trends.append("DOWN")
        else:
            trends.append("SAME")

    same_trend_count = 1
    max_same_trend = 1
    for i in range(1, len(trends)):
        if trends[i] == trends[i-1]:
            same_trend_count += 1
            max_same_trend = max(max_same_trend, same_trend_count)
        else:
            same_trend_count = 1

    if max_same_trend >= 6:
        manipulation_score += 30
        manipulation_reasons.append(f"Trend manipulation: {max_same_trend} repeats")

    if len(numbers) >= 20:
        mean_val = statistics.mean(numbers[:20])
        std_val = statistics.stdev(numbers[:20]) if len(numbers[:20]) > 1 else 2.5
        if std_val < 1.2:
            manipulation_score += 20
            manipulation_reasons.append(f"Low volatility: {std_val:.2f}")
        if std_val > 3.8:
            manipulation_score += 15
            manipulation_reasons.append(f"High volatility: {std_val:.2f}")

    if len(numbers) >= 25:
        patterns = {}
        pattern_length = 3
        for i in range(len(numbers[:25]) - pattern_length + 1):
            pattern = tuple(numbers[i:i+pattern_length])
            patterns[pattern] = patterns.get(pattern, 0) + 1
        for pattern, count in patterns.items():
            if count >= 3:
                manipulation_score += 35
                manipulation_reasons.append(f"Pattern repeated: {pattern} x{count}")
                break

    if len(numbers) >= 15:
        asc_seq = 1
        desc_seq = 1
        max_asc = 1
        max_desc = 1
        for i in range(1, len(numbers[:15])):
            if numbers[i] == numbers[i-1] + 1:
                asc_seq += 1
                max_asc = max(max_asc, asc_seq)
            else:
                asc_seq = 1
            if numbers[i] == numbers[i-1] - 1:
                desc_seq += 1
                max_desc = max(max_desc, desc_seq)
            else:
                desc_seq = 1
        if max_asc >= 4 or max_desc >= 4:
            manipulation_score += 40
            manipulation_reasons.append(f"Sequence: asc={max_asc} desc={max_desc}")

    big_small_trend = []
    for num in numbers[:20]:
        big_small_trend.append("BIG" if num >= 5 else "SMALL")
    big_count = big_small_trend.count("BIG")
    small_count = big_small_trend.count("SMALL")
    if abs(big_count - small_count) >= 15:
        manipulation_score += 25
        manipulation_reasons.append(f"B/S imbalance: B={big_count} S={small_count}")

    threshold = 50
    if analysis_level == "BASIC":
        threshold = 70
    elif analysis_level == "MEDIUM":
        threshold = 65
    elif analysis_level == "ADVANCED":
        threshold = 60
    elif analysis_level == "EXPERT":
        threshold = 55
    elif analysis_level == "AI_MASTER":
        threshold = 50

    data_bonus = min(20, len(numbers) // 5)
    manipulation_score += data_bonus

    manipulation_detected = manipulation_score >= threshold
    reason = " | ".join(manipulation_reasons[:3]) if manipulation_reasons else "No manipulation detected"

    print(f"🔍 Manipulation Check: Score={manipulation_score}/{threshold} Detected={manipulation_detected}")
    return manipulation_detected, reason, manipulation_score


def analyze_manipulation_patterns(numbers, analysis_level):
    patterns_detected = []
    if not numbers or len(numbers) < 10:
        return patterns_detected
    recent = numbers[:15]
    freq_count = {}
    for num in recent:
        freq_count[num] = freq_count.get(num, 0) + 1
    for num, count in freq_count.items():
        if count >= 5:
            patterns_detected.append(f"Number {num} repeated {count} times")

    if len(numbers) >= 10:
        alternating = True
        for i in range(2, 10):
            if numbers[i] != numbers[i-2]:
                alternating = False
                break
        if alternating:
            patterns_detected.append("Alternating pattern detected")

    if len(numbers) >= 20:
        first_half = numbers[:10]
        second_half = numbers[10:20]
        first_mean = statistics.mean(first_half) if first_half else 4.5
        second_mean = statistics.mean(second_half) if second_half else 4.5
        if abs(first_mean - second_mean) < 0.5:
            patterns_detected.append("Symmetrical distribution")

    return patterns_detected


def calculate_manipulation_confidence(numbers, analysis_level, previous_manipulation=False):
    if not numbers or len(numbers) < 10:
        return 0, "Insufficient data"
    base_confidence = 0
    if len(numbers) >= 15:
        std_val = statistics.stdev(numbers[:15]) if len(numbers[:15]) > 1 else 2.5
        if std_val < 1.5:
            base_confidence += 25
        elif std_val > 3.5:
            base_confidence += 15

    trends = []
    for i in range(1, len(numbers[:12])):
        if numbers[i] > numbers[i-1]:
            trends.append(1)
        elif numbers[i] < numbers[i-1]:
            trends.append(-1)
        else:
            trends.append(0)

    if len(set(trends[-5:])) == 1 and len(trends) >= 5:
        base_confidence += 20

    freq = {i: 0 for i in range(10)}
    for num in numbers[:20]:
        freq[num] += 1
    max_freq = max(freq.values())
    if max_freq >= 7:
        base_confidence += 30

    if previous_manipulation and len(market_manipulation_history) > 0:
        recent_manipulations = list(market_manipulation_history)[-5:]
        if sum(recent_manipulations) >= 3:
            base_confidence += 25

    level_bonus = 0
    if analysis_level == "MEDIUM":
        level_bonus = 5
    elif analysis_level == "ADVANCED":
        level_bonus = 10
    elif analysis_level == "EXPERT":
        level_bonus = 15
    elif analysis_level == "AI_MASTER":
        level_bonus = 20

    total_confidence = min(100, base_confidence + level_bonus)
    confidence_level = "LOW"
    if total_confidence >= 70:
        confidence_level = "HIGH"
    elif total_confidence >= 50:
        confidence_level = "MEDIUM"

    return total_confidence, confidence_level


# 🏁 /start
@bot.message_handler(commands=['start'])
def start_handler(message):
    chat_id = str(message.chat.id)
    if chat_id != OWNER_ID:
        bot.send_message(chat_id, "❌ *ACCESS DENIED*\n\nThis bot is private.", parse_mode="Markdown")
        return

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("🚀 START PREDICTION", "🛑 STOP PREDICTION")
    keyboard.row("⏰ 20 MIN PREDICTION", "⚙️ SETTINGS")
    keyboard.row("📊 WIN/LOSS REPORT", "🔄 RESET STATS")
    keyboard.row("🎭 SET PROMO MESSAGE", "🎯 VIEW PROMO")
    keyboard.row("📈 VIEW DATA STATS", "🧠 AI ANALYSIS INFO")
    keyboard.row("🧹 CLEAR ALL DATA", "📊 CURRENT STATS")
    keyboard.row("🔍 MARKET MANIPULATION INFO", "⚠️ MANIPULATION STATUS")

    bot.send_message(
        message.chat.id,
        "🔥 *DEEP AI PREDICTOR V5.0* 🔥\n\n"
        "🚀 স্বাগতম! AI + ML + DL ভিত্তিক প্রেডিকশন বট!\n\n"
        f"📊 বর্তমান ডাটা কাউন্ট: {len(historical_data)}\n"
        f"🧠 বর্তমান এনালাইসিস লেভেল: {data_analysis_level}\n"
        f"⚠️ মার্কেট মেনুপুলেশন সিস্টেম: ACTIVE",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    show_inline_keyboard(message.chat.id)


def show_inline_keyboard(chat_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("➕ ADD CHANNEL", callback_data="add_channel"),
        InlineKeyboardButton("📋 CHANNEL LIST", callback_data="channel_list")
    )
    keyboard.row(
        InlineKeyboardButton("🔗 ADD GROUP", callback_data="add_group"),
        InlineKeyboardButton("📋 GROUP LIST", callback_data="group_list")
    )
    keyboard.row(InlineKeyboardButton("⚙️ ADVANCED SETTINGS", callback_data="advanced_settings"))
    keyboard.row(InlineKeyboardButton("🔍 MANIPULATION SETTINGS", callback_data="manipulation_settings"))
    bot.send_message(chat_id, "🔧 *বট সেটআপ মেনু V5.0:*", reply_markup=keyboard, parse_mode="Markdown")


def show_advanced_settings(chat_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("🎭 SET WIN STICKER", callback_data="set_win_sticker"),
        InlineKeyboardButton("🎭 SET LOSS STICKER", callback_data="set_loss_sticker")
    )
    keyboard.row(
        InlineKeyboardButton("🏁 SET SEASON START STICKER", callback_data="set_season_start_sticker"),
        InlineKeyboardButton("🏁 SET SEASON CLOSE STICKER", callback_data="set_season_close_sticker")
    )
    keyboard.row(
        InlineKeyboardButton("🔗 SET REGISTER LINK", callback_data="set_register_link"),
        InlineKeyboardButton("👀 VIEW REGISTER LINK", callback_data="view_register_link")
    )
    keyboard.row(
        InlineKeyboardButton("📊 VIEW STATS", callback_data="view_stats"),
        InlineKeyboardButton("🔙 BACK TO MAIN", callback_data="back_to_main")
    )

    win_sticker = "✅ কাস্টম" if chat_id in user_win_stickers else "❌ ডিফল্ট"
    loss_sticker = "✅ কাস্টম" if chat_id in user_loss_stickers else "❌ ডিফল্ট"
    season_start = "✅ কাস্টম" if chat_id in user_season_start_stickers else "❌ ডিফল্ট"
    season_close = "✅ কাস্টম" if chat_id in user_season_close_stickers else "❌ ডিফল্ট"
    register_link = user_register_links.get(chat_id, "Not Set")
    promo_msg = user_promotional_messages.get(chat_id, "Not Set")

    bot.send_message(
        chat_id,
        f"⚙️ *ADVANCED SETTINGS V5.0*\n\n"
        f"🎭 Win: {win_sticker}\n"
        f"🎭 Loss: {loss_sticker}\n"
        f"🏁 Season Start: {season_start}\n"
        f"🏁 Season Close: {season_close}\n"
        f"🔗 Link: {register_link[:30]}\n"
        f"📝 Promo: {promo_msg[:30]}\n"
        f"📊 Data: {len(historical_data)}\n"
        f"🧠 Level: {data_analysis_level}",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


def show_manipulation_settings(chat_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("📊 MANIPULATION HISTORY", callback_data="manipulation_history"),
        InlineKeyboardButton("⚙️ MANIPULATION THRESHOLD", callback_data="manipulation_threshold")
    )
    keyboard.row(
        InlineKeyboardButton("🔍 DETECTION PATTERNS", callback_data="detection_patterns"),
        InlineKeyboardButton("📈 MANIPULATION STATS", callback_data="manipulation_stats")
    )
    keyboard.row(InlineKeyboardButton("🔙 BACK TO MAIN", callback_data="back_to_main"))

    bot.send_message(
        chat_id,
        f"🔍 *MANIPULATION SETTINGS*\n\n"
        f"Status: ACTIVE\nData: {len(historical_data)}\nLevel: {data_analysis_level}",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


@bot.message_handler(func=lambda m: m.text == "🔍 MARKET MANIPULATION INFO")
def market_manipulation_info_handler(message):
    chat_id = str(message.chat.id)
    if chat_id != OWNER_ID:
        bot.send_message(chat_id, "❌ *ACCESS DENIED*", parse_mode="Markdown")
        return

    info_text = f"""
⚠️ *MARKET MANIPULATION DETECTION V5.0*

📊 Data Count: {len(historical_data)}
🧠 Level: {data_analysis_level}
⚠️ Status: ACTIVE
"""
    bot.send_message(chat_id, info_text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: m.text == "⚠️ MANIPULATION STATUS")
def manipulation_status_handler(message):
    chat_id = str(message.chat.id)
    if chat_id != OWNER_ID:
        bot.send_message(chat_id, "❌ *ACCESS DENIED*", parse_mode="Markdown")
        return

    if market_manipulation_history:
        recent_detections = list(market_manipulation_history)[-10:]
        detection_count = sum(recent_detections)
        status_text = f"⚠️ *MANIPULATION STATUS*\n\nDetections (last 10): {detection_count}\nData: {len(historical_data)}\nLevel: {data_analysis_level}"
        bot.send_message(chat_id, status_text, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, "⚠️ এখনও কোন ডাটা নেই।")


@bot.message_handler(func=lambda m: m.text == "🎭 SET PROMO MESSAGE")
def set_promo_message_handler(message):
    chat_id = str(message.chat.id)
    if chat_id != OWNER_ID:
        bot.send_message(chat_id, "❌ *ACCESS DENIED*", parse_mode="Markdown")
        return
    msg = bot.send_message(message.chat.id, "📝 আপনার প্রমোশনাল মেসেজটি লিখুন:")
    bot.register_next_step_handler(msg, process_promo_message)


def process_promo_message(message):
    chat_id = message.chat.id
    text = message.text
    user_promotional_messages[chat_id] = text
    bot.send_message(chat_id, f"✅ সেভ করা হয়েছে!\n\n{text}")
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("🚀 START PREDICTION", "🛑 STOP PREDICTION")
    keyboard.row("⏰ 20 MIN PREDICTION", "⚙️ SETTINGS")
    keyboard.row("📊 WIN/LOSS REPORT", "🔄 RESET STATS")
    keyboard.row("🎭 SET PROMO MESSAGE", "🎯 VIEW PROMO")
    keyboard.row("📈 VIEW DATA STATS", "🧠 AI ANALYSIS INFO")
    keyboard.row("🧹 CLEAR ALL DATA", "📊 CURRENT STATS")
    keyboard.row("🔍 MARKET MANIPULATION INFO", "⚠️ MANIPULATION STATUS")
    bot.send_message(chat_id, "✅ এখন প্রেডিকশন শুরু করতে পারেন!", reply_markup=keyboard)


@bot.message_handler(func=lambda m: m.text == "🎯 VIEW PROMO")
def view_promo_handler(message):
    chat_id = str(message.chat.id)
    if chat_id != OWNER_ID:
        bot.send_message(chat_id, "❌ *ACCESS DENIED*", parse_mode="Markdown")
        return
    chat_id = message.chat.id
    promo_msg = user_promotional_messages.get(chat_id, "❌ কোন প্রমোশনাল মেসেজ সেট করা হয়নি")
    bot.send_message(chat_id, f"📝 প্রমোশনাল মেসেজ:\n\n{promo_msg}")


@bot.message_handler(func=lambda m: m.text == "📈 VIEW DATA STATS")
def view_data_stats_handler(message):
    chat_id = str(message.chat.id)
    if chat_id != OWNER_ID:
        bot.send_message(chat_id, "❌ *ACCESS DENIED*", parse_mode="Markdown")
        return

    chat_id = message.chat.id
    if len(historical_data) > 0:
        recent_data = list(historical_data)[-20:]
        stats_text = f"📊 *ডাটা স্ট্যাটিস্টিক্স V5.0*\n\n📈 মোট ডাটা: {len(historical_data)}\n🧠 লেভেল: {data_analysis_level}\n⚠️ মেনুপুলেশন ডিটেকশন: ACTIVE\n"
        bot.send_message(chat_id, stats_text, parse_mode="Markdown")

        last_10_text = "📝 সর্বশেষ ১০টি ডাটা:\n━━━━━━━━━━━━━━━━━━━\n"
        for i, data in enumerate(reversed(recent_data[:10]), 1):
            result_emoji = "✅" if "WIN" in data['result'] else "❌"
            last_10_text += f"{i}. {data['period']}: {data['prediction']} → {data['actual']} {result_emoji}\n"
        last_10_text += "━━━━━━━━━━━━━━━━━━━"
        bot.send_message(chat_id, last_10_text)
    else:
        bot.send_message(chat_id, "📊 এখনও কোন ডাটা নেই।")


@bot.message_handler(func=lambda m: m.text == "🧠 AI ANALYSIS INFO")
def ai_analysis_info_handler(message):
    chat_id = str(message.chat.id)
    if chat_id != OWNER_ID:
        bot.send_message(chat_id, "❌ *ACCESS DENIED*", parse_mode="Markdown")
        return

    info_text = f"""
🧠 *AI ANALYSIS SYSTEM V5.0*

📊 Data Count: {len(historical_data)}
🧠 Level: {data_analysis_level}
⚠️ Manipulation Detection: ACTIVE
"""
    bot.send_message(chat_id, info_text, parse_mode="Markdown")


def get_dual_api_data():
    try:
        current_data = None
        try:
            payload = {
                "typeId": 1, "language": 0,
                "random": "e7fe6c090da2495ab8290dac551ef1ed",
                "signature": "1F390E2B2D8A55D693E57FD905AE73A7",
                "timestamp": int(time.time())
            }
            response1 = requests.post(CURRENT_API, json=payload, timeout=8)
            if response1.status_code == 200:
                current_data = response1.json()
                print("✅ CURRENT_API working")
        except Exception as e:
            print(f"❌ CURRENT_API error: {e}")

        history_data = None
        try:
            response2 = requests.get(HISTORY_API, timeout=8)
            if response2.status_code == 200:
                history_data = response2.json()
                print("✅ HISTORY_API working")
        except Exception as e:
            print(f"❌ HISTORY_API error: {e}")

        if current_data and history_data:
            return current_data, history_data, "HIGH_CONFIDENCE"
        elif current_data:
            return current_data, None, "MEDIUM_CONFIDENCE"
        elif history_data:
            return None, history_data, "MEDIUM_CONFIDENCE"
        else:
            return None, None, "LOW_CONFIDENCE"
    except Exception as e:
        print(f"❌ Dual API system error: {e}")
        return None, None, "ERROR"


def calculate_correlation(x, y):
    n = len(x)
    if n < 2:
        return 0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    denominator_x = sum((x[i] - mean_x) ** 2 for i in range(n))
    denominator_y = sum((y[i] - mean_y) ** 2 for i in range(n))
    if denominator_x == 0 or denominator_y == 0:
        return 0
    return numerator / (denominator_x ** 0.5 * denominator_y ** 0.5)


def deep_learning_market_analysis(numbers):
    data_count = len(historical_data)
    if data_count < 50:
        return basic_analysis(numbers)
    elif data_count < 100:
        return medium_analysis(numbers)
    elif data_count < 500:
        return advanced_analysis(numbers)
    elif data_count < 1500:
        return expert_analysis(numbers)
    else:
        return ai_master_analysis(numbers)


def basic_analysis(numbers):
    if not numbers or len(numbers) < 10:
        return 65, "Basic Analysis", "NEUTRAL", [], False, "Insufficient data"
    recent = numbers[:15]
    big_count = sum(1 for n in recent if n >= 5)
    small_count = len(recent) - big_count
    confidence = 65 + min(20, abs(big_count - small_count) * 2)
    if confidence > 85:
        confidence = 85
    if big_count > small_count:
        market_sentiment = "BIG_BIAS"
    elif small_count > big_count:
        market_sentiment = "SMALL_BIAS"
    else:
        market_sentiment = "BALANCED"

    frequency = {i: 0 for i in range(10)}
    for num in recent:
        frequency[num] += 1
    hot_numbers = sorted(frequency.items(), key=lambda x: x[1], reverse=True)[:2]
    hot_num_list = [num for num, _ in hot_numbers]

    manipulation_detected, manipulation_reason, manipulation_score = detect_market_manipulation(numbers, "BASIC")

    if manipulation_detected:
        analysis_type = "Basic Market Scan ⚡ | Manipulation ⚠️"
        market_sentiment = "MANIPULATION_DETECTED"
        confidence = max(30, confidence - 25)
    else:
        analysis_type = "Basic Market Scan ⚡"

    return int(confidence), analysis_type, market_sentiment, hot_num_list, manipulation_detected, manipulation_reason


def medium_analysis(numbers):
    if not numbers or len(numbers) < 20:
        return 70, "Medium Analysis", "NEUTRAL", [], False, "Insufficient data"
    recent = numbers[:25]
    trends = []
    for i in range(1, len(recent)):
        if recent[i] > recent[i-1]:
            trends.append("UP")
        elif recent[i] < recent[i-1]:
            trends.append("DOWN")
        else:
            trends.append("SAME")

    mean_val = statistics.mean(recent) if len(recent) > 1 else 4.5
    std_val = statistics.stdev(recent) if len(recent) > 1 else 2.5
    big_count = sum(1 for n in recent if n >= 5)
    small_count = len(recent) - big_count

    confidence = 70
    dist_ratio = abs(big_count - small_count) / len(recent)
    confidence += int(dist_ratio * 20)
    if len(set(trends[-5:])) == 1 and len(trends) >= 5:
        confidence += 10
    if std_val < 2.0:
        confidence += 5
    elif std_val > 3.5:
        confidence -= 5
    confidence = max(65, min(confidence, 90))

    if mean_val > 5.2:
        market_sentiment = "STRONG_BIG"
    elif mean_val > 4.8:
        market_sentiment = "WEAK_BIG"
    elif mean_val < 4.2:
        market_sentiment = "STRONG_SMALL"
    elif mean_val < 4.8:
        market_sentiment = "WEAK_SMALL"
    else:
        market_sentiment = "BALANCED"

    frequency = {i: 0 for i in range(10)}
    for num in recent:
        frequency[num] += 1
    hot_numbers = sorted(frequency.items(), key=lambda x: x[1], reverse=True)[:3]
    hot_num_list = [num for num, _ in hot_numbers]

    manipulation_detected, manipulation_reason, manipulation_score = detect_market_manipulation(numbers, "MEDIUM")

    if manipulation_detected:
        analysis_type = "Medium Pattern 📊 | Manipulation ⚠️"
        market_sentiment = "MANIPULATION_DETECTED"
        confidence = max(40, confidence - 30)
    else:
        analysis_type = "Medium Pattern 📊"

    return int(confidence), analysis_type, market_sentiment, hot_num_list, manipulation_detected, manipulation_reason


def advanced_analysis(numbers):
    if not numbers or len(numbers) < 30:
        return 75, "Advanced Analysis", "NEUTRAL", [], False, "Insufficient data"
    recent = numbers[:40]
    short_term = recent[:10]
    medium_term = recent[:20]
    long_term = recent

    st_big = sum(1 for n in short_term if n >= 5)
    st_small = len(short_term) - st_big
    mt_big = sum(1 for n in medium_term if n >= 5)
    mt_small = len(medium_term) - mt_big
    lt_big = sum(1 for n in long_term if n >= 5)
    lt_small = len(long_term) - lt_big

    trend_score = 0
    if st_big > st_small and mt_big > mt_small and lt_big > lt_small:
        trend_score = 25
    elif st_small > st_big and mt_small > mt_big and lt_small > lt_big:
        trend_score = 25
    elif (st_big > st_small and mt_big > mt_small) or (st_small > st_big and mt_small > mt_big):
        trend_score = 15

    patterns = []
    for i in range(2, len(recent)):
        if recent[i] == recent[i-1] == recent[i-2]:
            patterns.append("TRIPLE")
        elif (recent[i] > recent[i-1] > recent[i-2]) or (recent[i] < recent[i-1] < recent[i-2]):
            patterns.append("TREND")

    pattern_score = len(patterns) * 2
    volatility = statistics.stdev(recent) if len(recent) > 1 else 2.5
    vol_score = 0
    if volatility < 1.8:
        vol_score = 10
    elif volatility > 3.5:
        vol_score = -5

    confidence = 75 + trend_score + pattern_score + vol_score
    confidence = max(70, min(confidence, 95))

    if trend_score >= 20:
        market_sentiment = "STRONG_TREND"
    elif trend_score >= 10:
        market_sentiment = "MODERATE_TREND"
    elif pattern_score >= 6:
        market_sentiment = "PATTERN_DETECTED"
    else:
        market_sentiment = "NEUTRAL"

    frequency = {i: 0 for i in range(10)}
    recency_weight = {i: 0 for i in range(10)}
    for idx, num in enumerate(recent):
        frequency[num] += 1
        recency_weight[num] += (len(recent) - idx) * 0.1

    combined_scores = []
    for i in range(10):
        score = frequency[i] * 0.7 + recency_weight[i] * 0.3
        combined_scores.append((i, score))

    hot_numbers = sorted(combined_scores, key=lambda x: x[1], reverse=True)[:4]
    hot_num_list = [num for num, _ in hot_numbers]

    manipulation_detected, manipulation_reason, manipulation_score = detect_market_manipulation(numbers, "ADVANCED")

    if manipulation_detected:
        analysis_type = "Advanced AI 🔥 | Manipulation ⚠️"
        market_sentiment = "MANIPULATION_DETECTED"
        confidence = max(50, confidence - 35)
    else:
        analysis_type = "Advanced AI 🔥"

    return int(confidence), analysis_type, market_sentiment, hot_num_list, manipulation_detected, manipulation_reason


def expert_analysis(numbers):
    if not numbers or len(numbers) < 50:
        return 80, "Expert Analysis", "NEUTRAL", [], False, "Insufficient data"

    hist_numbers = []
    if historical_data:
        for entry in historical_data:
            if 'actual' in entry:
                try:
                    hist_numbers.append(int(entry['actual']))
                except:
                    pass

    all_numbers = numbers[:30] + hist_numbers[-50:]
    if len(all_numbers) < 30:
        all_numbers = numbers[:50]

    window_size = min(10, len(all_numbers) // 3)
    moving_avg = []
    for i in range(len(all_numbers) - window_size + 1):
        window = all_numbers[i:i+window_size]
        moving_avg.append(statistics.mean(window))

    if len(moving_avg) >= 2:
        trend = "UP" if moving_avg[-1] > moving_avg[0] else "DOWN"
    else:
        trend = "NEUTRAL"

    support_levels = []
    resistance_levels = []
    unique_numbers = list(set(all_numbers))
    for num in unique_numbers:
        count = all_numbers.count(num)
        if count >= len(all_numbers) * 0.15:
            if num < 5:
                support_levels.append(num)
            else:
                resistance_levels.append(num)

    prob_dist = {i: all_numbers.count(i) / len(all_numbers) for i in range(10)}

    correlation_score = 0
    if len(all_numbers) >= 20:
        lag1_corr = calculate_correlation(all_numbers[:-1], all_numbers[1:]) if len(all_numbers) > 1 else 0
        if not math.isnan(lag1_corr):
            correlation_score = abs(lag1_corr) * 20

    confidence = 80
    if trend == "UP" and len(moving_avg) >= 3:
        trend_strength = (moving_avg[-1] - moving_avg[0]) / max(moving_avg)
        confidence += trend_strength * 15
    if support_levels or resistance_levels:
        confidence += 8
    max_prob_num = max(prob_dist.items(), key=lambda x: x[1])[0]
    if prob_dist[max_prob_num] > 0.25:
        confidence += 10
    confidence += correlation_score
    confidence = max(75, min(confidence, 97))

    if trend == "UP" and confidence > 85:
        market_sentiment = "STRONG_BULLISH"
    elif trend == "UP":
        market_sentiment = "BULLISH"
    elif trend == "DOWN" and confidence > 85:
        market_sentiment = "STRONG_BEARISH"
    elif trend == "DOWN":
        market_sentiment = "BEARISH"
    else:
        market_sentiment = "NEUTRAL"

    hot_numbers = sorted(prob_dist.items(), key=lambda x: x[1], reverse=True)[:4]
    hot_num_list = [num for num, _ in hot_numbers]

    manipulation_detected, manipulation_reason, manipulation_score = detect_market_manipulation(numbers, "EXPERT")

    if manipulation_detected:
        analysis_type = "Expert ML 🧠 | Manipulation ⚠️"
        market_sentiment = "MANIPULATION_DETECTED"
        confidence = max(60, confidence - 40)
    else:
        analysis_type = "Expert ML 🧠"

    return int(confidence), analysis_type, market_sentiment, hot_num_list, manipulation_detected, manipulation_reason


def ai_master_analysis(numbers):
    if not numbers or len(numbers) < 60:
        return 85, "AI Master Analysis", "NEUTRAL", [], False, "Insufficient data"

    all_historical = []
    if historical_data:
        for entry in historical_data:
            if 'actual' in entry:
                try:
                    all_historical.append(int(entry['actual']))
                except:
                    pass

    combined_data = numbers[:40] + all_historical[-100:]
    if len(combined_data) < 50:
        combined_data = numbers[:60]

    time_series = combined_data

    seasonal_patterns = []
    if len(time_series) >= 20:
        for period in [5, 10, 15]:
            if len(time_series) >= period * 2:
                seasonal_avg = []
                for i in range(period):
                    seasonal_values = []
                    for j in range(i, len(time_series), period):
                        if j < len(time_series):
                            seasonal_values.append(time_series[j])
                    if seasonal_values:
                        seasonal_avg.append(statistics.mean(seasonal_values))
                if len(seasonal_avg) >= 2:
                    seasonal_var = statistics.variance(seasonal_avg) if len(seasonal_avg) > 1 else 0
                    if seasonal_var < 2.0:
                        seasonal_patterns.append(period)

    predictive_score = 0
    if len(time_series) >= 30:
        recent_mean = statistics.mean(time_series[:20])
        overall_mean = statistics.mean(time_series)
        if abs(recent_mean - overall_mean) < 1.0:
            predictive_score = 15
        elif abs(recent_mean - overall_mean) < 2.0:
            predictive_score = 10
        else:
            predictive_score = 5

    pattern_matches = 0
    common_patterns = [
        [0, 1, 2], [1, 2, 3], [2, 3, 4], [3, 4, 5],
        [4, 5, 6], [5, 6, 7], [6, 7, 8], [7, 8, 9],
        [9, 8, 7], [8, 7, 6], [7, 6, 5], [6, 5, 4],
        [5, 4, 3], [4, 3, 2], [3, 2, 1], [2, 1, 0]
    ]
    if len(time_series) >= 10:
        recent_pattern = time_series[:3]
        for pattern in common_patterns:
            if recent_pattern == pattern:
                pattern_matches += 1

    pattern_score = pattern_matches * 8

    big_sequences = 0
    small_sequences = 0
    current_seq = 1
    prev_num = time_series[0] if time_series else 4
    for num in time_series[1:15]:
        if (num >= 5 and prev_num >= 5) or (num < 5 and prev_num < 5):
            current_seq += 1
        else:
            if prev_num >= 5 and current_seq >= 3:
                big_sequences += 1
            elif prev_num < 5 and current_seq >= 3:
                small_sequences += 1
            current_seq = 1
        prev_num = num

    psychology_score = 0
    if big_sequences > small_sequences:
        psychology_score = 12
    elif small_sequences > big_sequences:
        psychology_score = 12

    confidence = 85
    if seasonal_patterns:
        confidence += len(seasonal_patterns) * 3
    confidence += predictive_score
    confidence += pattern_score
    confidence += psychology_score
    data_bonus = min(10, len(historical_data) // 150)
    confidence += data_bonus
    confidence = max(80, min(confidence, 99))

    if confidence >= 95:
        market_sentiment = "AI_ULTRA_CONFIDENT"
    elif confidence >= 90:
        market_sentiment = "AI_HIGH_CONFIDENCE"
    elif confidence >= 85:
        market_sentiment = "AI_MODERATE_CONFIDENCE"
    else:
        market_sentiment = "AI_NEUTRAL"

    freq_dist = {i: 0 for i in range(10)}
    for num in time_series:
        freq_dist[num] += 1

    trend_scores = {i: 0 for i in range(10)}
    if len(time_series) >= 10:
        recent_trend = statistics.mean(time_series[:5])
        for i in range(10):
            if recent_trend > 5 and i >= 5:
                trend_scores[i] = 2
            elif recent_trend < 5 and i < 5:
                trend_scores[i] = 2

    combined_scores = []
    for i in range(10):
        score = freq_dist[i] * 0.5 + trend_scores[i] * 0.3 + random.random() * 0.2
        combined_scores.append((i, score))

    hot_numbers = sorted(combined_scores, key=lambda x: x[1], reverse=True)[:5]
    hot_num_list = [num for num, _ in hot_numbers]

    manipulation_detected, manipulation_reason, manipulation_score = detect_market_manipulation(numbers, "AI_MASTER")

    if manipulation_detected:
        analysis_type = "AI Master 🤖 | Manipulation ⚠️"
        market_sentiment = "MANIPULATION_DETECTED"
        confidence = max(70, confidence - 45)
    else:
        analysis_type = "AI Master 🤖"

    return int(confidence), analysis_type, market_sentiment, hot_num_list, manipulation_detected, manipulation_reason


def generate_number_prediction(prediction_type, hot_numbers):
    if prediction_type == "BIG":
        big_numbers = [0, 1, 2, 3, 4]
        hot_big_numbers = [num for num in hot_numbers if num in big_numbers]
        if len(hot_big_numbers) >= 2:
            predicted_numbers = random.sample(hot_big_numbers, 2)
        elif len(hot_big_numbers) == 1:
            other_numbers = [num for num in big_numbers if num != hot_big_numbers[0]]
            predicted_numbers = [hot_big_numbers[0], random.choice(other_numbers)]
        else:
            predicted_numbers = random.sample(big_numbers, 2)
    else:
        small_numbers = [5, 6, 7, 8, 9]
        hot_small_numbers = [num for num in hot_numbers if num in small_numbers]
        if len(hot_small_numbers) >= 2:
            predicted_numbers = random.sample(hot_small_numbers, 2)
        elif len(hot_small_numbers) == 1:
            other_numbers = [num for num in small_numbers if num != hot_small_numbers[0]]
            predicted_numbers = [hot_small_numbers[0], random.choice(other_numbers)]
        else:
            predicted_numbers = random.sample(small_numbers, 2)
    return sorted(predicted_numbers)


def generate_smart_prediction_v5(numbers, confidence, market_sentiment, hot_numbers, analysis_level, manipulation_detected):
    if manipulation_detected:
        return "SKIP", []

    if not numbers:
        pred_type = "BIG" if random.random() > 0.5 else "SMALL"
        num_pred = generate_number_prediction(pred_type, [])
        return pred_type, num_pred

    recent_trend = []
    for num in numbers[:15]:
        recent_trend.append("BIG" if num >= 5 else "SMALL")

    big_count = sum(1 for trend in recent_trend if trend == "BIG")
    small_count = len(recent_trend) - big_count

    if analysis_level in ["EXPERT", "AI_MASTER"]:
        if "STRONG" in market_sentiment and confidence >= 90:
            if "BIG" in market_sentiment or "BULL" in market_sentiment:
                pred_type = "BIG"
            elif "SMALL" in market_sentiment or "BEAR" in market_sentiment:
                pred_type = "SMALL"
            else:
                if big_count >= 10:
                    pred_type = "SMALL"
                elif small_count >= 10:
                    pred_type = "BIG"
                else:
                    pred_type = recent_trend[0]
        elif confidence >= 85:
            pred_type = recent_trend[0]
        else:
            hot_big_count = sum(1 for num in hot_numbers if num >= 5)
            hot_small_count = len(hot_numbers) - hot_big_count
            if hot_big_count > hot_small_count:
                pred_type = "BIG"
            elif hot_small_count > hot_big_count:
                pred_type = "SMALL"
            else:
                pred_type = "BIG" if random.random() > 0.5 else "SMALL"
    elif analysis_level == "ADVANCED":
        if confidence >= 80:
            if big_count >= 8:
                pred_type = "SMALL" if random.random() > 0.3 else "BIG"
            elif small_count >= 8:
                pred_type = "BIG" if random.random() > 0.3 else "SMALL"
            else:
                pred_type = recent_trend[0]
        else:
            pred_type = "BIG" if random.random() > 0.5 else "SMALL"
    elif analysis_level == "MEDIUM":
        if confidence >= 75:
            pred_type = recent_trend[0]
        else:
            pred_type = "SMALL" if recent_trend[0] == "BIG" else "BIG"
    else:
        pred_type = "BIG" if big_count > small_count else "SMALL"
        if big_count == small_count:
            pred_type = "BIG" if random.random() > 0.5 else "SMALL"

    num_pred = generate_number_prediction(pred_type, hot_numbers)
    return pred_type, num_pred


def generate_real_time_period():
    now = datetime.now(timezone.utc)
    hour = now.hour
    minute = now.minute
    second = now.second
    total_minutes_today = (hour * 60) + minute
    period_number = (total_minutes_today * 2) + (1 if second < 30 else 2)
    year = now.strftime("%Y")
    month = now.strftime("%m")
    day = now.strftime("%d")
    period = f"{year}{month}{day}10005{str(period_number).zfill(4)}"
    return period


def get_real_time_seconds():
    now = datetime.now(timezone.utc)
    second = now.second
    timer_value = 30 - (second % 30)
    return timer_value


def check_actual_result_with_jackpot(predicted_result, predicted_numbers, period_number=None):
    try:
        response = requests.get(HISTORY_API, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and 'data' in data and 'list' in data['data']:
                latest_result = data['data']['list'][0]
                if 'number' in latest_result and latest_result['number']:
                    try:
                        actual_num = int(latest_result['number'])
                        actual_result = "BIG" if actual_num >= 5 else "SMALL"
                        print(f"🎯 Actual: {actual_num} ({actual_result}) | Predicted: {predicted_result} {predicted_numbers}")
                        if actual_num in predicted_numbers:
                            return actual_num, actual_result, "JACKPOT WIN 🎉"
                        elif actual_result == predicted_result:
                            return actual_num, actual_result, "WIN ✅"
                        else:
                            return actual_num, actual_result, "LOSS ❌"
                    except ValueError:
                        print(f"❌ Number conversion error")

        try:
            payload = {
                "typeId": 1, "language": 0,
                "random": "e7fe6c090da2495ab8290dac551ef1ed",
                "signature": "1F390E2B2D8A55D693E57FD905AE73A7",
                "timestamp": int(time.time())
            }
            response = requests.post(CURRENT_API, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data and 'data' in data:
                    current_result = data['data'].get('result')
                    if current_result:
                        try:
                            actual_num = int(current_result)
                            actual_result = "BIG" if actual_num >= 5 else "SMALL"
                            if actual_num in predicted_numbers:
                                return actual_num, actual_result, "JACKPOT WIN 🎉"
                            elif actual_result == predicted_result:
                                return actual_num, actual_result, "WIN ✅"
                            else:
                                return actual_num, actual_result, "LOSS ❌"
                        except ValueError:
                            print(f"❌ Conversion error")
        except Exception as e:
            print(f"❌ Current API check error: {e}")
    except Exception as e:
        print(f"❌ Result check error: {e}")

    print("⚠️ Using fallback random result")
    actual_num = random.randint(0, 9)
    actual_result = "BIG" if actual_num >= 5 else "SMALL"
    if actual_num in predicted_numbers:
        return actual_num, actual_result, "JACKPOT WIN 🎉"
    elif actual_result == predicted_result:
        return actual_num, actual_result, "WIN ✅"
    else:
        return actual_num, actual_result, "LOSS ❌"


def send_season_sticker(chat_id, sticker_type, user_id):
    try:
        if sticker_type == "START":
            sticker_id = user_season_start_stickers.get(user_id, DEFAULT_SEASON_START_STICKER)
            text = f"🏁 *PREDICTION SESSION STARTED!* 🏁\n\n⚡ AI: {data_analysis_level}\n📊 Data: {len(historical_data)}\n⚠️ Manipulation Detection: ACTIVE"
        else:
            sticker_id = user_season_close_stickers.get(user_id, DEFAULT_SEASON_CLOSE_STICKER)
            text = f"🏁 *PREDICTION SESSION ENDED!* 🏁\n\n✅ Completed\n📊 Data Added\n⚠️ Manipulation Detection: ACTIVE"
        bot.send_sticker(chat_id, sticker_id)
        bot.send_message(chat_id, text, parse_mode="Markdown")
        return True
    except Exception as e:
        print(f"❌ Season sticker error: {e}")
        return False


def send_promotional_message(chat_id, user_id):
    try:
        promo_msg = user_promotional_messages.get(user_id)
        if promo_msg:
            promo_formatted = f"🎉 *SPECIAL PROMOTION* 🎉\n\n{promo_msg}\n\n📊 Data: {len(historical_data)}\n🧠 Level: {data_analysis_level}"
            bot.send_message(chat_id, promo_formatted, parse_mode="Markdown")
        else:
            default_promo = f"🎉 *SPECIAL OFFER* 🎉\n\n🔥 Join for More Predictions!\n📊 Data: {len(historical_data)}\n🧠 Level: {data_analysis_level}"
            bot.send_message(chat_id, default_promo, parse_mode="Markdown")
        return True
    except Exception as e:
        print(f"❌ Promo error: {e}")
        return False


def send_win_loss_sticker(chat_id, win_loss, user_id):
    try:
        if win_loss.startswith("JACKPOT"):
            sticker_id = user_win_stickers.get(user_id, DEFAULT_WIN_STICKER)
            bot.send_message(chat_id, "🎰 *JACKPOT WIN! CONGRATULATIONS!* 🎰", parse_mode="Markdown")
        elif win_loss == "WIN ✅":
            sticker_id = user_win_stickers.get(user_id, DEFAULT_WIN_STICKER)
        else:
            sticker_id = user_loss_stickers.get(user_id, DEFAULT_LOSS_STICKER)
        bot.send_sticker(chat_id, sticker_id)
        return True
    except Exception as e:
        print(f"❌ Sticker error: {e}")
        return False


def update_prediction_history(user_id, period, prediction_type, number_prediction, actual_number, actual_result, win_loss):
    if user_id not in prediction_history:
        prediction_history[user_id] = []
    history_entry = {
        "period": period,
        "prediction_type": prediction_type,
        "number_prediction": number_prediction,
        "actual_number": actual_number,
        "actual_result": actual_result,
        "result": win_loss,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    prediction_history[user_id].append(history_entry)
    if len(prediction_history[user_id]) > 200:
        prediction_history[user_id] = prediction_history[user_id][-200:]


def get_user_stats_v5(user_id):
    if user_id not in prediction_history or not prediction_history[user_id]:
        return {"total": 0, "wins": 0, "losses": 0, "jackpot_wins": 0, "win_rate": 0, "skipped": 0}
    history = prediction_history[user_id]
    total = len(history)
    wins = sum(1 for entry in history if "WIN" in entry["result"])
    losses = sum(1 for entry in history if "LOSS" in entry["result"])
    jackpot_wins = sum(1 for entry in history if "JACKPOT" in entry["result"])
    skipped = sum(1 for entry in history if entry["prediction_type"] == "SKIP")
    win_rate = (wins / (total - skipped)) * 100 if (total - skipped) > 0 else 0
    return {
        "total": total, "wins": wins, "losses": losses,
        "jackpot_wins": jackpot_wins, "skipped": skipped,
        "win_rate": round(win_rate, 2)
    }


def generate_deep_learning_prediction(user_id=None):
    try:
        current_data, history_data, confidence_level = get_dual_api_data()
        numbers = []

        if history_data and 'data' in history_data and 'list' in history_data['data']:
            for result in history_data['data']['list'][:40]:
                if 'number' in result and result['number']:
                    try:
                        num = int(result['number'])
                        numbers.append(num)
                    except:
                        continue

        if current_data and 'data' in current_data:
            current_result = current_data['data'].get('result')
            if current_result:
                try:
                    num = int(current_result)
                    numbers.insert(0, num)
                except:
                    pass

        print(f"📊 Collected {len(numbers)} numbers | Data: {len(historical_data)} | Level: {data_analysis_level}")

        if numbers:
            confidence, analysis_type, market_sentiment, hot_numbers, manipulation_detected, manipulation_reason = deep_learning_market_analysis(numbers)

            if confidence_level == "HIGH_CONFIDENCE":
                if not manipulation_detected:
                    confidence = min(confidence + 8, 98)
                analysis_type = "🔒 Dual API - " + analysis_type
            elif confidence_level == "MEDIUM_CONFIDENCE":
                if not manipulation_detected:
                    confidence = min(confidence + 4, 94)
                analysis_type = "🔗 Single API - " + analysis_type
            else:
                if not manipulation_detected:
                    confidence = max(confidence - 2, 65)
                analysis_type = "⚡ Fallback - " + analysis_type

            prediction_type, number_prediction = generate_smart_prediction_v5(
                numbers, confidence, market_sentiment, hot_numbers, data_analysis_level, manipulation_detected
            )

            period = generate_real_time_period()
            prediction_message = generate_new_prediction_message(period, prediction_type, number_prediction, manipulation_detected)

            return prediction_message, prediction_type, number_prediction, period, confidence, analysis_type, manipulation_detected, manipulation_reason

    except Exception as e:
        print(f"❌ Deep learning error: {e}")

    period = generate_real_time_period()
    prediction_type = "BIG" if random.random() > 0.5 else "SMALL"
    number_prediction = generate_number_prediction(prediction_type, [])
    confidence = random.randint(70, 85)
    analysis_type = f"Quick Scan ⚡ | Level: {data_analysis_level}"
    manipulation_detected = False
    manipulation_reason = ""
    prediction_message = generate_new_prediction_message(period, prediction_type, number_prediction, manipulation_detected)
    return prediction_message, prediction_type, number_prediction, period, confidence, analysis_type, manipulation_detected, manipulation_reason


def delete_pending_message(channel):
    try:
        if channel in pending_prediction_messages:
            message_id = pending_prediction_messages[channel]
            bot.delete_message(chat_id=channel, message_id=message_id)
            del pending_prediction_messages[channel]
            print(f"✅ Deleted pending message from {channel}")
            return True
    except Exception as e:
        print(f"❌ Error deleting pending: {e}")
    return False


def real_time_auto_prediction_v5(user_id, channel, is_timed=False, duration_minutes=20):
    send_season_sticker(channel, "START", user_id)
    start_time = datetime.now()

    if is_timed:
        end_time = start_time + timedelta(minutes=duration_minutes)
        prediction_timers[user_id] = end_time
        bot.send_message(user_id, f"⏰ Timer: {duration_minutes} min")

    message_id = None
    last_period = None
    last_prediction_type = None
    last_number_prediction = None
    last_confidence = None
    last_analysis_type = None
    last_manipulation_detected = False

    session_results = {"wins": 0, "losses": 0, "jackpots": 0, "total": 0, "skipped": 0}

    while signal_status.get(user_id, False):
        try:
            if is_timed and datetime.now() >= prediction_timers.get(user_id, datetime.now()):
                signal_status[user_id] = False
                delete_pending_message(channel)
                session_report = f"""
🏁 *SESSION REPORT V5.0* 🏁
━━━━━━━━━━━━━━━━━━━
⏰ Duration: {duration_minutes} minutes
📊 Total: {session_results['total']}
✅ Wins: {session_results['wins']}
❌ Losses: {session_results['losses']}
🎰 Jackpots: {session_results['jackpots']}
⚠️ Skipped: {session_results['skipped']}
📊 Data: {len(historical_data)}
🧠 Level: {data_analysis_level}
━━━━━━━━━━━━━━━━━━━
"""
                bot.send_message(user_id, session_report, parse_mode="Markdown")
                break

            current_period = generate_real_time_period()
            current_second = get_real_time_seconds()

            if current_period != last_period:
                print(f"🔄 New period: {current_period} | Data: {len(historical_data)} | Level: {data_analysis_level}")

                if last_period is not None and message_id is not None and not last_manipulation_detected:
                    try:
                        print(f"🔍 Checking result...")
                        actual_number, actual_result, win_loss = check_actual_result_with_jackpot(
                            last_prediction_type, last_number_prediction, last_period
                        )
                        print(f"🎯 Result: {win_loss}")

                        session_results['total'] += 1
                        if "WIN" in win_loss:
                            session_results['wins'] += 1
                            if "JACKPOT" in win_loss:
                                session_results['jackpots'] += 1
                        else:
                            session_results['losses'] += 1

                        update_prediction_history(
                            user_id, last_period, last_prediction_type,
                            last_number_prediction, actual_number, actual_result, win_loss
                        )

                        add_to_historical_data(
                            last_period,
                            f"{last_prediction_type}/{last_number_prediction[0]},{last_number_prediction[1]}",
                            f"{actual_result}({actual_number})",
                            win_loss
                        )

                        send_win_loss_sticker(channel, win_loss, user_id)

                        result_msg = f"""
📊 *Prediction Result*
━━━━━━━━━━━━━━━
🎯 Period: {last_period}
🔮 Prediction: {last_prediction_type} {last_number_prediction}
🎲 Actual: {actual_result} ({actual_number})
🏆 Result: {win_loss}
📊 Data: {len(historical_data)}
🧠 Level: {data_analysis_level}
━━━━━━━━━━━━━━━
"""
                        bot.send_message(user_id, result_msg, parse_mode="Markdown")
                    except Exception as e:
                        print(f"❌ Result check error: {e}")
                elif last_manipulation_detected:
                    session_results['skipped'] += 1
                    session_results['total'] += 1
                    market_manipulation_history.append(True)
                    print(f"⚠️ Skipping result check (manipulation) for {last_period}")

                prediction_message, prediction_type, number_prediction, period_number, confidence, analysis_type, manipulation_detected, manipulation_reason = generate_deep_learning_prediction(user_id)

                sent_message = bot.send_message(channel, prediction_message, parse_mode="Markdown")
                message_id = sent_message.message_id
                pending_prediction_messages[channel] = message_id

                last_period = period_number
                last_prediction_type = prediction_type
                last_number_prediction = number_prediction
                last_confidence = confidence
                last_analysis_type = analysis_type
                last_manipulation_detected = manipulation_detected

                if manipulation_detected:
                    manipulation_msg = f"""
⚠️ *MARKET MANIPULATION DETECTED* ⚠️

🎯 Period: {period_number}
🔍 Level: {data_analysis_level}
📊 Data: {len(historical_data)}
📈 Status: MANIPULATION

🎯 Action: Skipping
📊 Reason: {manipulation_reason[:100]}...

✅ Next prediction in next period
"""
                    bot.send_message(user_id, manipulation_msg, parse_mode="Markdown")
                else:
                    bot.send_message(user_id, f"✅ New prediction: {period_number}")

                print(f"🎯 {prediction_type} {number_prediction} | Period: {period_number} | Conf: {confidence}% | Manip: {manipulation_detected}")

            time.sleep(1)

        except Exception as e:
            print(f"❌ Real-time error: {e}")
            try:
                bot.send_message(user_id, f"⚠️ Error: {e}")
            except:
                pass
            time.sleep(5)

    if not signal_status.get(user_id, False):
        delete_pending_message(channel)
        send_season_sticker(channel, "CLOSE", user_id)
        send_promotional_message(channel, user_id)

        if clear_historical_data():
            bot.send_message(user_id, "🧹 *All data cleared!*", parse_mode="Markdown")

        if session_results['total'] > 0:
            effective_predictions = session_results['total'] - session_results['skipped']
            win_rate = (session_results['wins'] / effective_predictions * 100) if effective_predictions > 0 else 0
            final_report = f"""
📈 *FINAL SESSION REPORT V5.0*
━━━━━━━━━━━━━━━━━━━
📊 Total: {session_results['total']}
✅ Wins: {session_results['wins']}
❌ Losses: {session_results['losses']}
🎰 Jackpots: {session_results['jackpots']}
⚠️ Skipped: {session_results['skipped']}
📈 Win Rate: {round(win_rate, 2)}%
📊 Data: 0 (Cleared)
🧠 Level: BASIC (Reset)
🔥 Performance: {'Excellent 🔥' if win_rate >= 70 else 'Good ✅' if win_rate >= 50 else 'Needs Improvement ⚠️'}
━━━━━━━━━━━━━━━━━━━
"""
            bot.send_message(user_id, final_report, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = str(call.message.chat.id)
    if chat_id != OWNER_ID:
        bot.answer_callback_query(call.id, "❌ Access denied!")
        return

    chat_id = call.message.chat.id

    if call.data == "add_channel":
        msg = bot.send_message(chat_id, "🔗 চ্যানেলের ইউজারনেম পাঠান (যেমন: @yourchannel)")
        bot.register_next_step_handler(msg, process_channel_username)
    elif call.data == "channel_list":
        if chat_id in user_channels:
            bot.send_message(chat_id, f"📃 চ্যানেল: {user_channels[chat_id]}")
        else:
            bot.send_message(chat_id, "🚫 কোন চ্যানেল নেই।")
    elif call.data == "add_group":
        msg = bot.send_message(chat_id, "👥 গ্রুপ আইডি বা ইউজারনেম পাঠান:")
        bot.register_next_step_handler(msg, process_group_id)
    elif call.data == "group_list":
        if chat_id in user_channels and not str(user_channels[chat_id]).startswith('@'):
            bot.send_message(chat_id, f"📃 গ্রুপ: {user_channels[chat_id]}")
        else:
            bot.send_message(chat_id, "🚫 কোন গ্রুপ নেই।")
    elif call.data == "advanced_settings":
        show_advanced_settings(chat_id)
    elif call.data == "manipulation_settings":
        show_manipulation_settings(chat_id)
    elif call.data == "set_win_sticker":
        msg = bot.send_message(chat_id, "🎉 Win স্টিকার পাঠান:")
        bot.register_next_step_handler(msg, process_win_sticker)
    elif call.data == "set_loss_sticker":
        msg = bot.send_message(chat_id, "😢 Loss স্টিকার পাঠান:")
        bot.register_next_step_handler(msg, process_loss_sticker)
    elif call.data == "set_season_start_sticker":
        msg = bot.send_message(chat_id, "🏁 Season Start স্টিকার পাঠান:")
        bot.register_next_step_handler(msg, process_season_start_sticker)
    elif call.data == "set_season_close_sticker":
        msg = bot.send_message(chat_id, "🏁 Season Close স্টিকার পাঠান:")
        bot.register_next_step_handler(msg, process_season_close_sticker)
    elif call.data == "set_register_link":
        msg = bot.send_message(chat_id, "🔗 রেজিস্টার লিংক পাঠান:")
        bot.register_next_step_handler(msg, process_register_link)
    elif call.data == "view_register_link":
        register_link = user_register_links.get(chat_id, "Not Set")
        bot.send_message(chat_id, f"🔗 Link:\n{register_link}")
    elif call.data == "view_stats":
        stats = get_user_stats_v5(chat_id)
        if stats['total'] > 0:
            bot.send_message(chat_id,
                f"📊 *STATS V5.0*\n\nTotal: {stats['total']}\nWin: {stats['wins']}\nLoss: {stats['losses']}\nJackpots: {stats['jackpot_wins']}\nSkipped: {stats['skipped']}\nWin Rate: {stats['win_rate']}%",
                parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "📊 কোন স্ট্যাট নেই।")
    elif call.data == "manipulation_history":
        if market_manipulation_history:
            recent = list(market_manipulation_history)[-20:]
            history_text = "⚠️ *MANIPULATION HISTORY*\n\n"
            for i, detected in enumerate(reversed(recent), 1):
                history_text += f"{i}. {'⚠️ DETECTED' if detected else '✅ CLEAN'}\n"
            bot.send_message(chat_id, history_text, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "⚠️ কোন ডাটা নেই।")
    elif call.data == "manipulation_threshold":
        threshold_info = f"🎯 Threshold for {data_analysis_level}: {'70' if data_analysis_level == 'BASIC' else '65' if data_analysis_level == 'MEDIUM' else '60' if data_analysis_level == 'ADVANCED' else '55' if data_analysis_level == 'EXPERT' else '50'}/100"
        bot.send_message(chat_id, threshold_info)
    elif call.data == "detection_patterns":
        bot.send_message(chat_id, "🔍 Patterns: Frequency, Trend, Statistical, Pattern, Sequence, B/S imbalance")
    elif call.data == "manipulation_stats":
        if market_manipulation_history:
            total_checks = len(market_manipulation_history)
            detected = sum(market_manipulation_history)
            detection_rate = (detected / total_checks * 100) if total_checks > 0 else 0
            stats_text = f"📊 *MANIPULATION STATS*\n\nChecks: {total_checks}\nDetected: {detected}\nRate: {detection_rate:.1f}%"
            bot.send_message(chat_id, stats_text, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "📊 কোন ডাটা নেই।")
    elif call.data == "back_to_main":
        show_inline_keyboard(chat_id)


def process_channel_username(message):
    chat_id = message.chat.id
    text = message.text
    if text.startswith("@"):
        user_channels[chat_id] = text
        bot.send_message(chat_id, f"✅ পাবলিক চ্যানেল {text} সেভ!")
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.row("🚀 START PREDICTION", "🛑 STOP PREDICTION")
        keyboard.row("⏰ 20 MIN PREDICTION", "⚙️ SETTINGS")
        keyboard.row("📊 WIN/LOSS REPORT", "🔄 RESET STATS")
        keyboard.row("🎭 SET PROMO MESSAGE", "🎯 VIEW PROMO")
        keyboard.row("📈 VIEW DATA STATS", "🧠 AI ANALYSIS INFO")
        keyboard.row("🧹 CLEAR ALL DATA", "📊 CURRENT STATS")
        keyboard.row("🔍 MARKET MANIPULATION INFO", "⚠️ MANIPULATION STATUS")
        bot.send_message(chat_id, f"🎯 এখন START করুন!\n📡 {text}", reply_markup=keyboard)
    else:
        bot.send_message(chat_id, "❌ '@' দিয়ে শুরু করুন:")
        bot.register_next_step_handler(message, process_channel_username)


def process_group_id(message):
    chat_id = message.chat.id
    text = message.text
    try:
        group_id = int(text)
        if group_id < 0:
            user_channels[chat_id] = group_id
            bot.send_message(chat_id, f"✅ প্রাইভেট গ্রুপ {group_id} সেভ!")
        else:
            bot.send_message(chat_id, "❌ নেগেটিভ নাম্বার হতে হবে:")
            bot.register_next_step_handler(message, process_group_id)
            return
    except ValueError:
        if text.startswith("@"):
            user_channels[chat_id] = text
            bot.send_message(chat_id, f"✅ পাবলিক গ্রুপ {text} সেভ!")
        else:
            bot.send_message(chat_id, "❌ নেগেটিভ নাম্বার অথবা @ দিয়ে শুরু করুন:")
            bot.register_next_step_handler(message, process_group_id)
            return

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("🚀 START PREDICTION", "🛑 STOP PREDICTION")
    keyboard.row("⏰ 20 MIN PREDICTION", "⚙️ SETTINGS")
    keyboard.row("📊 WIN/LOSS REPORT", "🔄 RESET STATS")
    keyboard.row("🎭 SET PROMO MESSAGE", "🎯 VIEW PROMO")
    keyboard.row("📈 VIEW DATA STATS", "🧠 AI ANALYSIS INFO")
    keyboard.row("🧹 CLEAR ALL DATA", "📊 CURRENT STATS")
    keyboard.row("🔍 MARKET MANIPULATION INFO", "⚠️ MANIPULATION STATUS")
    bot.send_message(chat_id, f"🎯 এখন START করুন!\n👥 {text}", reply_markup=keyboard)


def process_win_sticker(message):
    chat_id = message.chat.id
    if message.sticker:
        user_win_stickers[chat_id] = message.sticker.file_id
        bot.send_message(chat_id, f"✅ Win স্টিকার সেভ!")
        show_advanced_settings(chat_id)
    else:
        bot.send_message(chat_id, "❌ স্টিকার পাঠান:")
        bot.register_next_step_handler(message, process_win_sticker)


def process_loss_sticker(message):
    chat_id = message.chat.id
    if message.sticker:
        user_loss_stickers[chat_id] = message.sticker.file_id
        bot.send_message(chat_id, f"✅ Loss স্টিকার সেভ!")
        show_advanced_settings(chat_id)
    else:
        bot.send_message(chat_id, "❌ স্টিকার পাঠান:")
        bot.register_next_step_handler(message, process_loss_sticker)


def process_season_start_sticker(message):
    chat_id = message.chat.id
    if message.sticker:
        user_season_start_stickers[chat_id] = message.sticker.file_id
        bot.send_message(chat_id, f"✅ Season Start সেভ!")
        show_advanced_settings(chat_id)
    else:
        bot.send_message(chat_id, "❌ স্টিকার পাঠান:")
        bot.register_next_step_handler(message, process_season_start_sticker)


def process_season_close_sticker(message):
    chat_id = message.chat.id
    if message.sticker:
        user_season_close_stickers[chat_id] = message.sticker.file_id
        bot.send_message(chat_id, f"✅ Season Close সেভ!")
        show_advanced_settings(chat_id)
    else:
        bot.send_message(chat_id, "❌ স্টিকার পাঠান:")
        bot.register_next_step_handler(message, process_season_close_sticker)


def process_register_link(message):
    chat_id = message.chat.id
    text = message.text
    if text.startswith("http"):
        user_register_links[chat_id] = text
        bot.send_message(chat_id, f"✅ লিংক সেভ!")
        show_advanced_settings(chat_id)
    else:
        bot.send_message(chat_id, "❌ http দিয়ে শুরু করুন:")
        bot.register_next_step_handler(message, process_register_link)


@bot.message_handler(func=lambda m: m.text == "🧹 CLEAR ALL DATA")
def clear_all_data_handler(message):
    chat_id = str(message.chat.id)
    if chat_id != OWNER_ID:
        bot.send_message(chat_id, "❌ *ACCESS DENIED*", parse_mode="Markdown")
        return
    chat_id = message.chat.id
    if clear_historical_data():
        market_manipulation_history.clear()
        bot.send_message(chat_id, "✅ *All data cleared!*\n\n🧹 ক্লিন\n📊 Level: BASIC\n⚠️ Manipulation history cleared", parse_mode="Markdown")
    else:
        bot.send_message(chat_id, "❌ Error clearing data.")


@bot.message_handler(func=lambda m: m.text == "📊 CURRENT STATS")
def current_stats_handler(message):
    chat_id = str(message.chat.id)
    if chat_id != OWNER_ID:
        bot.send_message(chat_id, "❌ *ACCESS DENIED*", parse_mode="Markdown")
        return
    chat_id = message.chat.id
    stats_text = f"""
📊 *CURRENT STATS V5.0*

📈 মোট ডাটা: {len(historical_data)}
🧠 এনালাইসিস লেভেল: {data_analysis_level}
📊 ডাটা কালেকশন: {'✅ Active' if data_collection_status else '❌ Inactive'}

⚠️ মেনুপুলেশন:
🔍 চেক: {len(market_manipulation_history)}
⚠️ ডিটেকশন: {sum(market_manipulation_history)}
📈 রেট: {(sum(market_manipulation_history)/len(market_manipulation_history)*100) if market_manipulation_history else 0:.1f}%

👤 ইউজার:
👥 টোটাল: {len(user_channels)}
🎭 Win স্টিকার: {len(user_win_stickers)}
🎭 Loss স্টিকার: {len(user_loss_stickers)}

⚙️ সিস্টেম:
🔄 Active: {sum(1 for s in signal_status.values() if s)}
⏰ Timers: {len(prediction_timers)}
"""
    bot.send_message(chat_id, stats_text, parse_mode="Markdown")


@bot.message_handler(func=lambda m: True)
def handle_buttons(message):
    chat_id = str(message.chat.id)
    text = message.text

    if chat_id != OWNER_ID:
        bot.send_message(message.chat.id, "❌ *ACCESS DENIED*", parse_mode="Markdown")
        return

    chat_id = message.chat.id
    text = message.text

    if text == "🚀 START PREDICTION":
        if chat_id in user_channels:
            channel = user_channels[chat_id]
            if not signal_status.get(chat_id, False):
                signal_status[chat_id] = True
                t = threading.Thread(target=real_time_auto_prediction_v5, args=(chat_id, channel, False))
                signal_threads[chat_id] = t
                t.daemon = True
                t.start()
                bot.send_message(chat_id,
                    f"🚀 *STARTED V5.0!*\n\n📡 {channel}\n🧠 Deep Learning AI\n📊 Data: {len(historical_data)}\n🧠 Level: {data_analysis_level}\n⚠️ Manipulation: ACTIVE",
                    parse_mode="Markdown")
            else:
                bot.send_message(chat_id, "⚠️ Already running.")
        else:
            bot.send_message(chat_id, "❗ First add channel/group!")
            show_inline_keyboard(chat_id)

    elif text == "⏰ 20 MIN PREDICTION":
        if chat_id in user_channels:
            channel = user_channels[chat_id]
            if not signal_status.get(chat_id, False):
                signal_status[chat_id] = True
                t = threading.Thread(target=real_time_auto_prediction_v5, args=(chat_id, channel, True, 20))
                signal_threads[chat_id] = t
                t.daemon = True
                t.start()
                bot.send_message(chat_id,
                    f"⏰ *20-MIN STARTED V5.0!*\n\n📡 {channel}\n⏰ 20 minutes\n📊 Data: {len(historical_data)}\n🧠 Level: {data_analysis_level}",
                    parse_mode="Markdown")
            else:
                bot.send_message(chat_id, "⚠️ Already running.")
        else:
            bot.send_message(chat_id, "❗ First add channel/group!")
            show_inline_keyboard(chat_id)

    elif text == "🛑 STOP PREDICTION":
        if signal_status.get(chat_id, False):
            signal_status[chat_id] = False
            if chat_id in prediction_timers:
                del prediction_timers[chat_id]
            if chat_id in user_channels:
                delete_pending_message(user_channels[chat_id])
            bot.send_message(chat_id, "🛑 Stopped. Pending deleted, session closing...")
        else:
            bot.send_message(chat_id, "ℹ️ Already stopped.")

    elif text == "⚙️ SETTINGS":
        show_advanced_settings(chat_id)

    elif text == "📊 WIN/LOSS REPORT":
        stats = get_user_stats_v5(chat_id)
        if stats['total'] > 0:
            bot.send_message(chat_id,
                f"📊 *WIN/LOSS V5.0*\n\nTotal: {stats['total']}\nWin: {stats['wins']}\nLoss: {stats['losses']}\nJackpots: {stats['jackpot_wins']}\nSkipped: {stats['skipped']}\nWin Rate: {stats['win_rate']}%",
                parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "📊 কোন ডাটা নেই।")

    elif text == "🔄 RESET STATS":
        if chat_id in prediction_history:
            prediction_history[chat_id] = []
        bot.send_message(chat_id, "🔄 স্ট্যাট রিসেট!")

    elif text == "🎭 SET PROMO MESSAGE":
        set_promo_message_handler(message)

    elif text == "🎯 VIEW PROMO":
        view_promo_handler(message)

    elif text == "📈 VIEW DATA STATS":
        view_data_stats_handler(message)

    elif text == "🧠 AI ANALYSIS INFO":
        ai_analysis_info_handler(message)

    elif text == "🧹 CLEAR ALL DATA":
        clear_all_data_handler(message)

    elif text == "📊 CURRENT STATS":
        current_stats_handler(message)

    elif text == "🔍 MARKET MANIPULATION INFO":
        market_manipulation_info_handler(message)

    elif text == "⚠️ MANIPULATION STATUS":
        manipulation_status_handler(message)

    elif text.startswith("@"):
        user_channels[chat_id] = text
        bot.send_message(chat_id, f"✅ সেভ: {text}")
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.row("🚀 START PREDICTION", "🛑 STOP PREDICTION")
        keyboard.row("⏰ 20 MIN PREDICTION", "⚙️ SETTINGS")
        keyboard.row("📊 WIN/LOSS REPORT", "🔄 RESET STATS")
        keyboard.row("🎭 SET PROMO MESSAGE", "🎯 VIEW PROMO")
        keyboard.row("📈 VIEW DATA STATS", "🧠 AI ANALYSIS INFO")
        keyboard.row("🧹 CLEAR ALL DATA", "📊 CURRENT STATS")
        keyboard.row("🔍 MARKET MANIPULATION INFO", "⚠️ MANIPULATION STATUS")
        bot.send_message(chat_id, "🎯 START করুন!", reply_markup=keyboard)


print("🤖 DEEP AI PREDICTOR V5.0 starting...")
print("👑 OWNER ID:", OWNER_ID)
print("📊 Data:", len(historical_data))
print("🧠 Level:", data_analysis_level)
print("⚠️ MANIPULATION DETECTION: ACTIVE")

while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        print(f"❌ Polling error: {e}")
        time.sleep(5)

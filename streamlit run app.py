import streamlit as st
import requests
import pandas as pd
import numpy as np
import time
import os
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(layout="wide")
st.title("📊 كاشف فرص العملات الرقمية + RSI (نسخة نهائية 5.1)")

# ==============================
# إعدادات
# ==============================
MIN_VOLUME = 2_000_000
DROP_THRESHOLD = -20
THREADS = 5           # عدد الخيوط للفحص المتوازي
DELAY = 1             # ثانية لكل طلب OHLC
TOTAL_COINS = 1000    # عدد العملات المؤهلة للفحص
RSI_PERIOD = 14
OHLC_DAYS = 30        # آخر 30 يوم
CACHE_DIR = "cache"   # مجلد تخزين البيانات

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# ==============================
# أدوات مساعدة
# ==============================
def fetch_market_list():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "volume_desc",
        "per_page": 100,
        "page": 1,
        "price_change_percentage": "30d"
    }
    all_coins = []
    pages = TOTAL_COINS // 100 + (TOTAL_COINS % 100 > 0)
    for page in range(1, pages + 1):
        params["page"] = page
        try:
            data = requests.get(url, params=params, timeout=10).json()
            all_coins.extend(data)
        except:
            continue
        time.sleep(1)
    return all_coins[:TOTAL_COINS]

def pre_filter_coins(coins):
    filtered = []
    for coin in coins:
        if not isinstance(coin, dict):
            continue
        price = coin.get("current_price")
        volume = coin.get("total_volume")
        change_30d = coin.get("price_change_percentage_30d_in_currency")
        if price is None or volume is None or change_30d is None:
            continue
        if volume < MIN_VOLUME:
            continue
        if change_30d > DROP_THRESHOLD:
            continue
        filtered.append(coin)
    return filtered

def fetch_ohlc_daily(symbol):
    """جلب بيانات يومية لآخر 30 يوم مع التخزين المؤقت"""
    cache_file = os.path.join(CACHE_DIR, f"{symbol}_ohlc.csv")
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file, parse_dates=["time"])
        if (pd.Timestamp.now() - df["time"].max()).days < 1:
            return df
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{symbol.lower()}/ohlc"
        params = {"vs_currency": "usd", "days": OHLC_DAYS}
        r = requests.get(url, params=params, timeout=10).json()
        df = pd.DataFrame(r, columns=["time", "open", "high", "low", "close"])
        df["time"] = pd.to_datetime(df["time"], unit='ms')
        df.to_csv(cache_file, index=False)
        time.sleep(DELAY)
        return df
    except:
        return pd.DataFrame()

def calculate_rsi(df, period=RSI_PERIOD):
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def add_indicators(df):
    df["ema50"] = df["close"].ewm(span=50).mean()
    df["ema200"] = df["close"].ewm(span=200).mean()
    df["rsi"] = calculate_rsi(df)
    df["macd"] = df["close"].ewm(span=12).mean() - df["close"].ewm(span=26).mean()
    df["signal"] = df["macd"].ewm(span=9).mean()
    return df

def calculate_score(df):
    latest = df.iloc[-1]
    score = 0
    if latest["rsi"] < 50:
        score += 20
    if latest["macd"] > latest["signal"]:
        score += 20
    if latest["ema50"] > latest["ema200"]:
        score += 20
    if "volumeto" not in df.columns:
        df["volumeto"] = df.get("volumefrom", 0) * df["close"]
    avg_vol = df["volumeto"].rolling(20).mean().iloc[-1] if "volumeto" in df else 0
    if latest.get("volumeto", 0) > avg_vol:
        score += 10
    return score

# ==============================
# تحليل عملة واحدة
# ==============================
def analyze_coin(coin):
    try:
        symbol = coin["symbol"]
        df = fetch_ohlc_daily(symbol)
        if df.empty or len(df) < RSI_PERIOD:
            return None
        df = add_indicators(df)
        score = calculate_score(df)
        latest_price = df.iloc[-1]["close"]
        high = df["high"].max()
        low = df["low"].min()
        range_pct = (high - low) / low
        touches = sum(df["low"] <= low * 1.02)
        if score >= 50:
            signal = "🔥 فرصة قوية"
        elif score >= 30:
            signal = "🟡 فرصة متوسطة"
        else:
            signal = "⚪ ضعيف"
        return {
            "العملة": symbol.upper(),
            "السعر": latest_price,
            "RSI": round(df["rsi"].iloc[-1], 2),
            "Score": score,
            "لمسات الدعم": touches,
            "النطاق %": round(range_pct * 100, 2),
            "التقييم": signal
        }
    except:
        return None

# ==============================
# عرض الجدول بالألوان
# ==============================
def color_score(val):
    if val == "🔥 فرصة قوية":
        return 'background-color: #FF5733; color: white'
    elif val == "🟡 فرصة متوسطة":
        return 'background-color: #FFC300; color: black'
    else:
        return 'background-color: #C0C0C0; color: black'

# ==============================
# تشغيل البرنامج
# ==============================
if st.button("🚀 ابدأ الفحص"):
    st.info(f"⏳ جاري فحص {TOTAL_COINS} عملة بعد الفلترة...")
    coins = fetch_market_list()
    filtered_coins = pre_filter_coins(coins)
    results = []

    progress_text = st.empty()
    progress_bar = st.progress(0)
    total = len(filtered_coins)

    success_data = 0
    fail_data = 0

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = [executor.submit(analyze_coin, coin) for coin in filtered_coins]
        for i, future in enumerate(futures):
            result = future.result()
            if result:
                results.append(result)
                success_data += 1
            else:
                fail_data += 1
            progress_text.text(f"جاري الفحص: {i+1}/{total} عملة")
            progress_bar.progress((i+1)/total)

    st.info(f"🌟 العملات التي تم جلب بياناتها بنجاح: {success_data}")
    st.warning(f"⚠️ العملات التي فشل تحميل بياناتها: {fail_data}")

    if results:
        df_results = pd.DataFrame(results)
        df_results = df_results.sort_values(by="Score", ascending=False)

        # عداد النجاح والفشل حسب التقييم
        success_count = df_results[df_results["التقييم"].isin(["🔥 فرصة قوية", "🟡 فرصة متوسطة"])].shape[0]
        fail_count = df_results[df_results["التقييم"] == "⚪ ضعيف"].shape[0]

        st.success(f"✅ عدد العملات الناجحة حسب التقييم: {success_count} | عدد العملات الفاشلة: {fail_count}")
        st.dataframe(df_results.style.applymap(color_score, subset=["التقييم"]), use_container_width=True)
    else:
        st.warning("❌ لا توجد فرص حالياً")

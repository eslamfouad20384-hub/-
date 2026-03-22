import streamlit as st
import requests
import pandas as pd
import numpy as np
import time
import os
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

st.set_page_config(layout="wide")
st.title("📊 كاشف فرص العملات الرقمية + RSI (نسخة محسنة 6.0)")

# ==============================
# إعدادات
# ==============================
MIN_VOLUME = 2_000_000
THREADS = 5
DELAY = 1
TOTAL_COINS = 100
RSI_PERIOD = 14
OHLC_DAYS = 30
CACHE_DIR = "cache"

CRYPTOCOMPARE_KEY = "c9d4fdc4a8bbdc7ce6d2aee814d87e46153d13a0f287a72394cee48cb8db0e1c"
NOMICS_KEY = "YOUR_NOMICS_KEY"

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# ==============================
# Safe request
# ==============================
def safe_request(url, params=None, headers=None):
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
    except:
        return None

# ==============================
# جلب السوق
# ==============================
def fetch_market_list():
    all_data = []
    page = 1
    while len(all_data) < TOTAL_COINS:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "volume_desc",
            "per_page": 100,
            "page": page
        }
        data = safe_request(url, params)
        if not data: break
        clean = [x for x in data if "symbol" in x]
        all_data.extend(clean)
        page += 1
    df = pd.DataFrame(all_data[:TOTAL_COINS])
    df = df[df["total_volume"] > MIN_VOLUME]
    return df

# ==============================
# OHLC sources
# ==============================
@lru_cache(maxsize=500)
def fetch_ohlc_cc(symbol):
    url = f"https://min-api.cryptocompare.com/data/v2/histoday"
    params = {"fsym": symbol.upper(), "tsym": "USD", "limit": OHLC_DAYS}
    headers = {"authorization": f"Apikey {CRYPTOCOMPARE_KEY}"}
    data = safe_request(url, params, headers)
    try:
        df = pd.DataFrame(data["Data"]["Data"])
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df
    except:
        return None

@lru_cache(maxsize=500)
def fetch_ohlc_coincap(symbol):
    url = f"https://api.coincap.io/v2/assets/{symbol.lower()}/history"
    params = {"interval": "d1"}
    data = safe_request(url, params)
    try:
        df = pd.DataFrame(data["data"])
        df = df.rename(columns={"priceUsd":"close"})
        df["close"] = df["close"].astype(float)
        df["time"] = pd.to_datetime(df["time"])
        return df
    except:
        return None

@lru_cache(maxsize=500)
def fetch_ohlc_nomics(symbol):
    url = f"https://api.nomics.com/v1/candles"
    params = {"key": NOMICS_KEY, "currency": symbol.upper(), "interval": "1d"}
    data = safe_request(url, params)
    try:
        df = pd.DataFrame(data)
        df["close"] = df["close"].astype(float)
        df["time"] = pd.to_datetime(df["timestamp"])
        return df
    except:
        return None

@lru_cache(maxsize=500)
def fetch_ohlc_coingecko(symbol):
    cache_file = os.path.join(CACHE_DIR, f"{symbol}_ohlc.csv")
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file, parse_dates=["time"])
        if (pd.Timestamp.now() - df["time"].max()).days < 1:
            return df
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{symbol.lower()}/ohlc"
        params = {"vs_currency": "usd", "days": OHLC_DAYS}
        r = requests.get(url, params=params, timeout=10).json()
        df = pd.DataFrame(r, columns=["time","open","high","low","close"])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        df.to_csv(cache_file, index=False)
        return df
    except:
        return None

# ==============================
# Indicators
# ==============================
def calculate_rsi(df, period=RSI_PERIOD):
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period).mean()
    avg_loss = loss.ewm(alpha=1/period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def add_indicators(df):
    df["ema50"] = df["close"].ewm(span=50).mean()
    df["ema200"] = df["close"].ewm(span=200).mean()
    df["rsi"] = calculate_rsi(df)
    return df

def calculate_score(df):
    latest = df.iloc[-1]
    score = 0
    if latest["rsi"] < 50: score += 20
    if latest["ema50"] > latest["ema200"]: score += 20
    return score

# ==============================
# تحليل عملة واحدة
# ==============================
def analyze_coin(coin):
    symbol = coin["symbol"]
    # جلب البيانات من كل المصادر بالتتابع
    df = fetch_ohlc_coingecko(symbol) or fetch_ohlc_cc(symbol) or fetch_ohlc_coincap(symbol) or fetch_ohlc_nomics(symbol)
    if df is None or len(df) < RSI_PERIOD:
        return None
    df = add_indicators(df)
    score = calculate_score(df)
    latest_price = df.iloc[-1]["close"]
    # تحديد التقييم
    if score >= 40: signal = "🔥 فرصة قوية"
    elif score >= 20: signal = "🟡 فرصة متوسطة"
    else: signal = "⚪ ضعيف"
    return {"العملة": symbol.upper(), "السعر": latest_price, "RSI": round(df["rsi"].iloc[-1],2), "Score": score, "التقييم": signal}

# ==============================
# ألوان التقييم
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
    results = []
    success_count = 0
    fail_count = 0

    progress_text = st.empty()
    progress_bar = st.progress(0)
    total = len(coins)

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = [executor.submit(analyze_coin, coin) for coin in coins]
        for i, future in enumerate(futures):
            result = future.result()
            if result:
                results.append(result)
                success_count += 1
            else:
                fail_count += 1
            progress_text.text(f"جاري الفحص: {i+1}/{total} عملة")
            progress_bar.progress((i+1)/total)

    st.write(f"🌟 العملات التي تم جلب بياناتها بنجاح: {success_count}")
    st.write(f"⚠️ العملات التي فشل تحميل بياناتها: {fail_count}")

    if results:
        df_results = pd.DataFrame(results)
        df_results = df_results.sort_values(by="Score", ascending=False)
        st.dataframe(df_results.style.applymap(color_score, subset=["التقييم"]), use_container_width=True)
    else:
        st.warning("❌ لا توجد فرص حالياً")

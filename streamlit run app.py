import streamlit as st
import requests
import pandas as pd
import numpy as np
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(layout="wide")
st.title("👑 Crypto Scanner AI ELITE")

# ==============================
# إعدادات
# ==============================
MIN_VOLUME = 2_000_000
TOTAL_COINS = 150
RSI_PERIOD = 14
OHLC_DAYS = 30
CACHE_DIR = "cache"
MAX_WORKERS = 12

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# ==============================
# جلب السوق
# ==============================
def fetch_market_list():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "volume_desc",
        "per_page": 100,
        "page": 1
    }

    coins = []
    for page in range(1, 3):
        params["page"] = page
        try:
            data = requests.get(url, params=params, timeout=10).json()
            coins.extend(data)
        except:
            continue
        time.sleep(1)

    return coins[:TOTAL_COINS]

# ==============================
# OHLC
# ==============================
def fetch_ohlc(symbol):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{symbol}/ohlc"
        params = {"vs_currency": "usd", "days": OHLC_DAYS}
        data = requests.get(url, params=params, timeout=10).json()

        df = pd.DataFrame(data, columns=["time","open","high","low","close"])
        df["time"] = pd.to_datetime(df["time"], unit='ms')
        return df
    except:
        return pd.DataFrame()

# ==============================
# RSI
# ==============================
def calculate_rsi(df):
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(RSI_PERIOD).mean()
    avg_loss = loss.rolling(RSI_PERIOD).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ==============================
# تحليل العملة
# ==============================
def analyze_coin(coin):
    if coin["total_volume"] < MIN_VOLUME:
        return None

    symbol = coin["id"]
    df = fetch_ohlc(symbol)

    if df.empty or len(df) < 20:
        return None

    df["rsi"] = calculate_rsi(df)
    df["ema50"] = df["close"].ewm(span=50).mean()
    df["ema200"] = df["close"].ewm(span=200).mean()

    latest = df.iloc[-1]

    # ==============================
    # 🔍 الهبوط الحقيقي
    # ==============================
    max_price = df["high"].max()
    current_price = latest["close"]
    drop_percent = ((current_price - max_price) / max_price) * 100

    # ==============================
    # 📊 Volume Profile
    # ==============================
    avg_volume = coin["total_volume"] / 30
    volume_score = 1 if coin["total_volume"] > avg_volume else 0

    # ==============================
    # 🧠 AI Score
    # ==============================
    score = 0

    # RSI
    if latest["rsi"] < 30:
        score += 25
    elif latest["rsi"] < 40:
        score += 15

    # Trend
    if latest["ema50"] > latest["ema200"]:
        score += 25

    # ارتداد من القاع
    if current_price > df["low"].min() * 1.05:
        score += 15

    # Volume
    score += volume_score * 15

    # الهبوط
    if drop_percent < -30:
        score += 20

    # ==============================
    # 🎯 احتمال الصعود (AI)
    # ==============================
    probability = int(min(95, max(5, score * 1.3)))

    # ==============================
    # 📈 دعم + Target + StopLoss
    # ==============================
    support = df["low"].tail(10).min()

    target = current_price + (current_price - support) * 1.5
    stop_loss = support * 0.97

    # ==============================
    # التقييم
    # ==============================
    if score >= 70:
        signal = "🔥 قوية"
    elif score >= 40:
        signal = "🟡 متوسطة"
    else:
        signal = "⚪ ضعيف"

    return {
        "العملة": coin["symbol"].upper(),
        "السعر": round(current_price, 4),
        "هبوط %": round(drop_percent, 2),
        "RSI": round(latest["rsi"], 2),
        "Score": score,
        "احتمال %": probability,
        "Support": round(support, 4),
        "Target": round(target, 4),
        "StopLoss": round(stop_loss, 4),
        "التقييم": signal
    }

# ==============================
# تشغيل
# ==============================
if st.button("🚀 فحص السوق"):
    coins = fetch_market_list()

    results = []
    progress = st.progress(0)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(analyze_coin, coin) for coin in coins]

        for i, f in enumerate(as_completed(futures)):
            try:
                res = f.result()
                if res:
                    results.append(res)
            except:
                pass

            progress.progress((i+1)/len(futures))

    if results:
        df = pd.DataFrame(results)

        df = df.sort_values(
            by=["Score", "احتمال %"],
            ascending=False
        )

        st.success(f"✅ {len(df)} فرصة جاهزة")

        st.dataframe(df, use_container_width=True)

    else:
        st.warning("❌ مفيش فرص حالياً")

import streamlit as st
import requests
import pandas as pd
import numpy as np
import time
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(layout="wide")
st.title("📊 كاشف مناطق التجميع + RSI (نسخة محسنة - فرص أكتر)")

# ==============================
# إعدادات
# ==============================
MIN_VOLUME = 500_000         # بدل 2 مليون
DROP_THRESHOLD = -10         # بدل -20%
THREADS = 3
DELAY = 1                    # ثانية لكل طلب OHLC
TOTAL_COINS = 300            # بدل 200
RSI_PERIOD = 14

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
    for page in range(1, pages+1):
        params["page"] = page
        try:
            data = requests.get(url, params=params, timeout=10).json()
            all_coins.extend(data)
        except:
            continue
        time.sleep(1)
    return all_coins[:TOTAL_COINS]

def filter_coins(coins):
    filtered = []
    for coin in coins:
        price = coin.get("current_price")
        volume = coin.get("total_volume")
        change_30d = coin.get("price_change_percentage_30d_in_currency")
        if price is None:
            continue
        if volume < MIN_VOLUME:
            continue
        if change_30d is None or change_30d > DROP_THRESHOLD:
            continue
        filtered.append(coin)
    return filtered

def fetch_ohlc_cryptocompare(symbol):
    try:
        url = "https://min-api.cryptocompare.com/data/v2/histohour"
        params = {"fsym": symbol.upper(), "tsyms": "USD", "limit": 200}
        r = requests.get(url, params=params, timeout=10).json()
        df = pd.DataFrame(r["Data"]["Data"])
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

def calculate_score(df):
    latest = df.iloc[-1]
    score = 0
    if "rsi" in df.columns and latest["rsi"] < 50:
        score += 20
    if "macd" in df.columns and "signal" in df.columns and latest["macd"] > latest["signal"]:
        score += 20
    if "ema50" in df.columns and "ema200" in df.columns and latest["ema50"] > latest["ema200"]:
        score += 20
    if "volumeto" not in df.columns:
        df["volumeto"] = df.get("volumefrom", 0) * df["close"]
    avg_vol = df["volumeto"].rolling(20).mean().iloc[-1]
    if latest["volumeto"] > avg_vol:
        score += 10
    return score

def add_indicators(df):
    df["ema50"] = df["close"].ewm(span=50).mean()
    df["ema200"] = df["close"].ewm(span=200).mean()
    df["rsi"] = calculate_rsi(df)
    df["macd"] = df["close"].ewm(span=12).mean() - df["close"].ewm(span=26).mean()
    df["signal"] = df["macd"].ewm(span=9).mean()
    return df

# ==============================
# تحليل عملة واحدة
# ==============================
def analyze_coin(coin):
    try:
        symbol = coin["symbol"].upper()
        price = coin.get("current_price")
        volume = coin.get("total_volume")
        change_30d = coin.get("price_change_percentage_30d_in_currency")

        df = fetch_ohlc_cryptocompare(symbol)
        if df.empty or len(df) < RSI_PERIOD:
            return None

        df = add_indicators(df)
        score = calculate_score(df)

        latest_price = df.iloc[-1]["close"]
        high = df["high"].max()
        low = df["low"].min()
        range_pct = (high - low)/low
        touches = sum(df["low"] <= low*1.02)

        if score >= 50:
            signal = "🔥 فرصة قوية"
        elif score >= 30:
            signal = "🟡 فرصة متوسطة"
        else:
            signal = "⚪ ضعيف"

        return {
            "العملة": symbol,
            "السعر": latest_price,
            "RSI": round(df["rsi"].iloc[-1],2),
            "Score": score,
            "لمسات الدعم": touches,
            "النطاق %": round(range_pct*100,2),
            "التقييم": signal
        }
    except:
        return None

# ==============================
# تشغيل البرنامج
# ==============================
if st.button("🚀 ابدأ الفحص"):
    st.info(f"⏳ جاري فحص {TOTAL_COINS} عملة بعد الفلترة...")
    coins = fetch_market_list()
    filtered_coins = filter_coins(coins)
    results = []

    progress_text = st.empty()
    progress_bar = st.progress(0)
    total = len(filtered_coins)

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = [executor.submit(analyze_coin, coin) for coin in filtered_coins]
        for i, future in enumerate(futures):
            result = future.result()
            if result:
                results.append(result)
            progress_text.text(f"جاري الفحص: {i+1}/{total} عملة")
            progress_bar.progress((i+1)/total)

    if results:
        df_results = pd.DataFrame(results)
        df_results = df_results.sort_values(by="Score", ascending=False)
        st.success(f"✅ تم العثور على {len(df_results)} فرصة قوية")
        st.dataframe(df_results, use_container_width=True)
    else:
        st.warning("❌ لا توجد فرص حالياً")

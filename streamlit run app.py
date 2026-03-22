import streamlit as st
import requests
import pandas as pd
import numpy as np
import time
import os

st.set_page_config(layout="wide")
st.title("📊 كاشف فرص العملات الرقمية + RSI (نسخة تحليلية 7.0)")

# ==============================
# إعدادات
# ==============================
MIN_VOLUME = 2_000_000
DROP_THRESHOLD = -20
TOTAL_COINS = 100
RSI_PERIOD = 14
OHLC_DAYS = 30
CACHE_DIR = "cache"

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# ==============================
# أدوات مساعدة
# ==============================
def fetch_market_list():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usd", "order": "volume_desc", "per_page": 100, "page":1, "price_change_percentage":"30d"}
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
        df["time"] = pd.to_datetime(df["time"], unit='ms')
        df.to_csv(cache_file, index=False)
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
    return 100 - (100 / (1 + rs))

def add_indicators(df):
    df["ema50"] = df["close"].ewm(span=50).mean()
    df["ema200"] = df["close"].ewm(span=200).mean()
    df["rsi"] = calculate_rsi(df)
    return df

def calculate_score(df):
    latest = df.iloc[-1]
    score = 0
    if latest["rsi"] < 50:
        score += 20
    if latest["ema50"] > latest["ema200"]:
        score += 20
    return score

# ==============================
# تحليل عملة واحدة مع تفصيل كل خطوة
# ==============================
def analyze_coin(coin):
    symbol = coin["symbol"]
    df = fetch_ohlc_daily(symbol)
    if df.empty or len(df) < RSI_PERIOD:
        return None

    df = add_indicators(df)
    latest = df.iloc[-1]

    steps = {}
    steps["RSI"] = "✅" if latest["rsi"] < 30 else "❌"
    steps["EMA50>EMA200"] = "✅" if latest["ema50"] > latest["ema200"] else "❌"

    low = df["low"].min()
    touches = sum(df["low"] <= low * 1.02)
    steps["لمسات الدعم"] = "✅" if touches >= 1 else "❌"

    score = calculate_score(df)
    if score >= 40:
        signal = "🔥 فرصة قوية"
    elif score >= 20:
        signal = "🟡 فرصة متوسطة"
    else:
        signal = "⚪ ضعيف"

    return {
        "العملة": symbol.upper(),
        "السعر": latest["close"],
        "RSI": round(latest["rsi"],2),
        "EMA50": round(latest["ema50"],2),
        "EMA200": round(latest["ema200"],2),
        "لمسات الدعم": touches,
        "Score": score,
        "التقييم": signal,
        "RSI_OK": steps["RSI"],
        "EMA_OK": steps["EMA50>EMA200"],
        "Support_OK": steps["لمسات الدعم"]
    }

def color_score(val):
    if val == "🔥 فرصة قوية":
        return 'background-color: #FF5733; color: white'
    elif val == "🟡 فرصة متوسطة":
        return 'background-color: #FFC300; color: black'
    else:
        return 'background-color: #C0C0C0; color: black'

# ==============================
# تشغيل الفحص وعرض كل خطوة
# ==============================
if st.button("🚀 ابدأ الفحص"):
    st.info(f"⏳ جاري فحص {TOTAL_COINS} عملة بعد الفلترة...")
    coins = fetch_market_list()
    filtered_coins = pre_filter_coins(coins)
    results = []

    success_count = 0
    fail_count = 0

    progress_text = st.empty()
    progress_bar = st.progress(0)
    total = len(filtered_coins)

    for i, coin in enumerate(filtered_coins):
        res = analyze_coin(coin)
        symbol = coin["symbol"].upper()
        if res:
            results.append(res)
            success_count += 1
            st.write(f"✅ {symbol} تم جلب البيانات بنجاح: RSI {res['RSI_OK']}, EMA {res['EMA_OK']}, Support {res['Support_OK']}")
        else:
            fail_count += 1
            st.write(f"⚠️ {symbol} فشل جلب البيانات")
        progress_text.text(f"جاري الفحص: {i+1}/{total} عملة")
        progress_bar.progress((i+1)/total)

    st.write(f"🌟 العملات التي تم جلب بياناتها بنجاح: {success_count}")
    st.write(f"⚠️ العملات التي فشل تحميل بياناتها: {fail_count}")

    if results:
        df_results = pd.DataFrame(results).sort_values(by="Score", ascending=False)
        st.dataframe(df_results.style.applymap(color_score, subset=["التقييم"]), use_container_width=True)
    else:
        st.warning("❌ لا توجد فرص حالياً")

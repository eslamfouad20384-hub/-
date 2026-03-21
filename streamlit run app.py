import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor
import time

st.set_page_config(layout="wide")
st.title("📊 كاشف مناطق التجميع + توقع الصعود (500 عملة)")

# ==============================
# إعدادات
# ==============================
MIN_VOLUME = 2_000_000
DROP_THRESHOLD = -20
RANGE_THRESHOLD = 0.15
RSI_LOW = 25
RSI_HIGH = 55
THREADS = 5
DELAY = 0.5  # ثانية بين كل طلب OHLC

# ==============================
# جلب البيانات
# ==============================

def get_markets():
    all_coins = []
    for page in range(1, 6):  # 5 صفحات × 100 عملة = 500 عملة
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "volume_desc",
            "per_page": 100,
            "page": page,
            "price_change_percentage": "30d"
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            all_coins.extend(data)
        except Exception as e:
            st.warning(f"⚠️ خطأ في الصفحة {page}: {e}")
        time.sleep(1)  # delay لتجنب rate limit
    return all_coins

def get_ohlc(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": 7}
    try:
        data = requests.get(url, params=params, timeout=10).json()
        df = pd.DataFrame(data, columns=["time","open","high","low","close"])
        time.sleep(DELAY)  # delay لكل طلب OHLC
        return df
    except:
        return pd.DataFrame()  # لو فشل ترجع فاضي

# ==============================
# RSI
# ==============================

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ==============================
# Score التجميع
# ==============================

def calculate_score(touches, drop, range_ratio, rsi, volume):
    score = 0
    if touches >= 4:
        score += 3
    elif touches >= 2:
        score += 2
    else:
        score += 1

    if drop <= -50:
        score += 2
    elif drop <= -30:
        score += 1

    if range_ratio < 0.05:
        score += 2
    elif range_ratio < 0.10:
        score += 1

    if 35 <= rsi <= 45:
        score += 2
    elif 30 < rsi < 50:
        score += 1

    if volume > MIN_VOLUME * 2:
        score += 1

    return score

# ==============================
# توقع الصعود %
# ==============================

def predict_up_probability(score, rsi, volume, range_ratio, price, high):
    prob = 0
    prob += (score / 10) * 40
    if 35 <= rsi <= 45:
        prob += 20
    elif 30 < rsi < 50:
        prob += 10
    if volume > MIN_VOLUME * 2:
        prob += 20
    elif volume > MIN_VOLUME:
        prob += 10
    if range_ratio < 0.05:
        prob += 10
    if price > high * 0.95:
        prob += 10
    return round(min(prob, 100), 1)

# ==============================
# تحليل العملة
# ==============================

def analyze_coin(coin):
    try:
        coin_id = coin["id"]
        name = coin["symbol"].upper()
        price = coin["current_price"]
        volume = coin["total_volume"]
        change_30d = coin.get("price_change_percentage_30d_in_currency", 0)

        if volume < MIN_VOLUME:
            return None

        if change_30d is None or change_30d > DROP_THRESHOLD:
            return None

        df = get_ohlc(coin_id)
        if df.empty:
            # لو OHLC فاضي، رجع بيانات تقريبة
            score = 1
            prob = 10
            return {
                "العملة": name,
                "السعر": price,
                "التغيير 30 يوم %": round(change_30d, 2),
                "RSI": None,
                "النطاق %": None,
                "لمسات الدعم": 0,
                "Score": score,
                "احتمال الصعود %": prob,
                "التقييم": "⚪ بيانات قليلة"
            }

        high = df["high"].max()
        low = df["low"].min()
        range_ratio = (high - low) / low

        if range_ratio > RANGE_THRESHOLD:
            return None

        if price < low * 1.02:
            return None

        df["RSI"] = calculate_rsi(df["close"])
        rsi = df["RSI"].iloc[-1]

        if rsi is None or not (RSI_LOW < rsi < RSI_HIGH):
            return None

        touches = sum(df["low"] <= low * 1.02)

        score = calculate_score(touches, change_30d, range_ratio, rsi, volume)
        prob = predict_up_probability(score, rsi, volume, range_ratio, price, high)

        if score >= 8:
            signal = "🔥 تجميع قوي"
        elif score >= 5:
            signal = "🟡 تجميع متوسط"
        else:
            signal = "⚪ ضعيف"

        return {
            "العملة": name,
            "السعر": price,
            "التغيير 30 يوم %": round(change_30d, 2),
            "RSI": round(rsi, 2),
            "النطاق %": round(range_ratio * 100, 2),
            "لمسات الدعم": touches,
            "Score": score,
            "احتمال الصعود %": prob,
            "التقييم": signal
        }

    except:
        return None

# ==============================
# تشغيل البرنامج
# ==============================

if st.button("🚀 ابدأ الفحص"):
    st.write("⏳ جاري فحص 500 عملة مع OHLC...")

    coins = get_markets()
    results = []

    progress_text = st.empty()
    progress_bar = st.progress(0)
    total = len(coins)

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = [executor.submit(analyze_coin, coin) for coin in coins]

        for i, future in enumerate(futures):
            result = future.result()
            if result:
                results.append(result)

            progress_text.text(f"جاري الفحص: {i+1}/{total} عملة")
            progress_bar.progress((i + 1) / total)

    if results:
        df = pd.DataFrame(results)
        df = df.sort_values(by="احتمال الصعود %", ascending=False)

        st.success(f"✅ تم العثور على {len(df)} فرصة قوية")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("❌ لا يوجد فرص حالياً")

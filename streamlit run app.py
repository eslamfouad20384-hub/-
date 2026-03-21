import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(layout="wide")
st.title("📊 كاشف مناطق التجميع + توقع الصعود (PRO MAX)")

# ==============================
# إعدادات
# ==============================
MIN_VOLUME = 5_000_000
DROP_THRESHOLD = -30
RANGE_THRESHOLD = 0.10
RSI_LOW = 30
RSI_HIGH = 50

# ==============================
# جلب البيانات
# ==============================

def get_markets():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "volume_desc",
        "per_page": 100,
        "page": 1,
        "price_change_percentage": "30d"
    }
    return requests.get(url, params=params).json()

def get_ohlc(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": 7}
    data = requests.get(url, params=params).json()
    df = pd.DataFrame(data, columns=["time","open","high","low","close"])
    return df

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

    # 1. Score
    prob += (score / 10) * 40

    # 2. RSI
    if 35 <= rsi <= 45:
        prob += 20
    elif 30 < rsi < 50:
        prob += 10

    # 3. Volume
    if volume > MIN_VOLUME * 2:
        prob += 20
    elif volume > MIN_VOLUME:
        prob += 10

    # 4. ضيق النطاق
    if range_ratio < 0.05:
        prob += 10

    # 5. قرب المقاومة
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
            return None

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

        # تصنيف
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
# تشغيل
# ==============================

if st.button("🚀 ابدأ الفحص"):
    st.write("⏳ جاري فحص السوق...")

    coins = get_markets()
    results = []

    progress = st.progress(0)
    total = len(coins)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(analyze_coin, coin) for coin in coins]

        for i, future in enumerate(futures):
            result = future.result()
            if result:
                results.append(result)

            progress.progress((i + 1) / total)

    if results:
        df = pd.DataFrame(results)
        df = df.sort_values(by="احتمال الصعود %", ascending=False)

        st.success(f"✅ تم العثور على {len(df)} فرصة قوية")
        st.dataframe(df, use_container_width=True)

    else:
        st.warning("❌ لا يوجد فرص حالياً")

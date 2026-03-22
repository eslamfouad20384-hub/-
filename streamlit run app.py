import streamlit as st
import requests
import pandas as pd
import numpy as np
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(layout="wide")
st.title("👑 Crypto Smart Money Scanner ELITE - Target احترافي + فرص مراقبة")

# ==============================
# إعدادات
MIN_VOLUME = 2_000_000
TOTAL_COINS = 150
RSI_PERIOD = 14
OHLC_DAYS = 60
MAX_WORKERS = 12
SIDEWAYS_RANGE = 0.08
VOL_MULTIPLIER = 1.2

# ==============================
# جلب السوق
def fetch_market_list():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usd", "order": "volume_desc", "per_page": 100, "page": 1}
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
def calculate_rsi(df):
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(RSI_PERIOD).mean()
    avg_loss = loss.rolling(RSI_PERIOD).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ==============================
# دعم حقيقي
def get_real_support(df):
    df['pivot_low'] = df['low'].rolling(5).min()
    return df['pivot_low'].mode()[0]

# ==============================
# Target احترافي للبيع
def get_real_target(df, current_price):
    # 1️⃣ HVN / High Volume Nodes
    df['pivot_high'] = df['high'].rolling(5).max()
    highs = df['pivot_high'].unique()
    resistance_HVN = [h for h in highs if h > current_price]

    # 2️⃣ مستوى Fibonacci 1.618
    support = get_real_support(df)
    target_fibo = current_price + (current_price - support) * 1.618

    # 3️⃣ مستويات نفسية
    round_levels = [round(x, 0) for x in range(int(current_price), int(current_price*1.5))]
    psychological_levels = [lvl for lvl in round_levels if lvl > current_price]

    # جمع كل المستويات
    target_candidates = resistance_HVN + [target_fibo] + psychological_levels

    if target_candidates:
        return min(target_candidates)  # أقرب مستوى فوق السعر الحالي
    else:
        return target_fibo

# ==============================
# تحليل العملة
def analyze_coin(coin):
    try:
        if coin["total_volume"] < MIN_VOLUME:
            return None

        symbol = coin["id"]
        df = fetch_ohlc(symbol)
        if df.empty or len(df) < 20:
            return None

        # مؤشرات
        df["rsi"] = calculate_rsi(df)
        df["ema50"] = df["close"].ewm(span=50).mean()
        df["ema200"] = df["close"].ewm(span=200).mean()
        latest = df.iloc[-1]

        # الهبوط الحقيقي
        max_price = df["high"].max()
        current_price = latest["close"]
        drop_percent = ((current_price - max_price) / max_price) * 100

        # الحركة العرضية
        recent = df.tail(10)
        high = recent["high"].max()
        low = recent["low"].min()
        range_percent = (high - low) / low
        sideways = range_percent < SIDEWAYS_RANGE

        # الضغط
        volatility = recent["close"].std()
        low_volatility = volatility < (recent["close"].mean() * 0.02)

        # Volume Rising
        volume_now = coin["total_volume"]
        volume_avg = volume_now / 30
        volume_rising = volume_now > volume_avg * VOL_MULTIPLIER

        # Smart Money Setup
        smart_setup = (
            drop_percent < -25 and
            sideways and
            low_volatility and
            volume_rising
        )

        # AI Score
        score = 0
        if smart_setup: score += 50
        if latest["rsi"] < 45: score += 15
        if latest["ema50"] > latest["ema200"]: score += 15
        if drop_percent < -40: score += 10
        probability = int(min(95, max(5, score * 1.2)))

        # الدعم والهدف الاحترافي للبيع
        support = get_real_support(df)
        stop_loss = support * 0.97
        target = get_real_target(df, current_price)

        # التقييم النهائي
        if smart_setup and score >= 60:
            signal = "🚀 انفجار محتمل"
        elif score >= 40:
            signal = "🟡 مراقبة"
        else:
            signal = "⚪ ضعيف"

        # لو لسه السعر ما وصلش للـ Target النهائي لكن باقي الشروط متحققة → فرصة مراقبة
        if not smart_setup and score >= 40:
            signal = "🟡 مراقبة"

        return {
            "العملة": coin["symbol"].upper(),
            "السعر": round(current_price, 4),
            "هبوط %": round(drop_percent, 2),
            "Range %": round(range_percent*100, 2),
            "RSI": round(latest["rsi"], 2),
            "Score": score,
            "احتمال %": probability,
            "Support": round(support, 4),
            "StopLoss": round(stop_loss, 4),
            "Target البيع": round(target, 4),
            "Setup": "✅" if smart_setup else "❌",
            "التقييم": signal
        }

    except:
        return None

# ==============================
# تشغيل
if st.button("🚀 فحص السوق"):
    st.info("⏳ جاري البحث عن فرص الانفجار...")

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
        # ترتيب الفرص حسب القوة: Setup → Score → Probability
        df = df.sort_values(by=["Setup", "Score", "احتمال %"], ascending=False)
        st.success(f"🔥 تم العثور على {len(df)} فرصة")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("❌ لا توجد فرص حالياً")

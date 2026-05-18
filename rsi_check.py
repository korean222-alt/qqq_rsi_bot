import requests
import pandas as pd
import os
import json
from datetime import datetime, timedelta
from pathlib import Path

STATE_FILE = "state.json"

def load_state():
    if Path(STATE_FILE).exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def within_cooldown(last_alert_date, days=14):
    if last_alert_date is None:
        return False
    last = datetime.fromisoformat(last_alert_date)
    return datetime.now() - last < timedelta(days=days)

def get_prices(ticker, interval="1d", range_="1y"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={interval}&range={range_}"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    data = r.json()
    closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
    return [x for x in closes if x is not None]

def calculate_rsi(prices, period=14):
    delta = pd.Series(prices).diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period-1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period-1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def check_ma_touch(prices, ma_period, tolerance=0.015):
    ma = pd.Series(prices).rolling(ma_period).mean().iloc[-1]
    current = prices[-1]
    pct_diff = abs(current - ma) / ma
    return pct_diff <= tolerance, current, ma

def send_telegram(message):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message})

today = datetime.now().strftime("%Y-%m-%d")
state = load_state()
alerts = []

# QQQ RSI 31
try:
    weekly = get_prices("QQQ", interval="1wk", range_="2y")
    rsi = calculate_rsi(weekly)
    prev_below = state.get("qqq_rsi_below31", False)
    now_below = rsi <= 31
    if now_below and not prev_below:
        if not within_cooldown(state.get("qqq_rsi_down_alert")):
            alerts.append(f"📉 QQQ 주봉 RSI {rsi:.1f} → 31 하향 돌파!")
            state["qqq_rsi_down_alert"] = today
    elif not now_below and prev_below:
        alerts.append(f"📈 QQQ 주봉 RSI {rsi:.1f} → 31 상향 돌파!")
    state["qqq_rsi_below31"] = now_below
    daily = get_prices("QQQ")
    for ma in [100, 200]:
        touched, price, ma_val = check_ma_touch(daily, ma)
        key = f"qqq_ma{ma}_touched"
        if touched and not state.get(key, False):
            if not within_cooldown(state.get(f"qqq_ma{ma}_alert")):
                alerts.append(f"📊 QQQ {ma}일선 터치! ${price:.2f} / MA ${ma_val:.2f}")
                state[f"qqq_ma{ma}_alert"] = today
        state[key] = touched
except Exception as e:
    print(f"QQQ 오류: {e}")

# SPX RSI 31
try:
    weekly = get_prices("%5EGSPC", interval="1wk", range_="2y")
    rsi = calculate_rsi(weekly)
    prev_below = state.get("spx_rsi_below31", False)
    now_below = rsi <= 31
    if now_below and not prev_below:
        if not within_cooldown(state.get("spx_rsi_down_alert")):
            alerts.append(f"📉 SPX 주봉 RSI {rsi:.1f} → 31 하향 돌파!")
            state["spx_rsi_down_alert"] = today
    elif not now_below and prev_below:
        alerts.append(f"📈 SPX 주봉 RSI {rsi:.1f} → 31 상향 돌파!")
    state["spx_rsi_below31"] = now_below
    daily = get_prices("%5EGSPC")
    for ma in [100, 200]:
        touched, price, ma_val = check_ma_touch(daily, ma)
        key = f"spx_ma{ma}_touched"
        if touched and not state.get(key, False):
            if not within_cooldown(state.get(f"spx_ma{ma}_alert")):
                alerts.append(f"📊 SPX {ma}일선 터치! ${price:.2f} / MA ${ma_val:.2f}")
                state[f"spx_ma{ma}_alert"] = today
        state[key] = touched
except Exception as e:
    print(f"SPX 오류: {e}")

# NVDA 100일선
try:
    daily = get_prices("NVDA")
    touched, price, ma_val = check_ma_touch(daily, 100)
    key = "nvda_ma100_touched"
    if touched and not state.get(key, False):
        if not within_cooldown(state.get("nvda_ma100_alert")):
            alerts.append(f"📊 NVDA 100일선 터치! ${price:.2f} / MA ${ma_val:.2f}")
            state["nvda_ma100_alert"] = today
    state[key] = touched
except Exception as e:
    print(f"NVDA 오류: {e}")

# TSLA 200일선
try:
    daily = get_prices("TSLA")
    touched, price, ma_val = check_ma_touch(daily, 200)
    key = "tsla_ma200_touched"
    if touched and not state.get(key, False):
        if not within_cooldown(state.get("tsla_ma200_alert")):
            alerts.append(f"📊 TSLA 200일선 터치! ${price:.2f} / MA ${ma_val:.2f}")
            state["tsla_ma200_alert"] = today
    state[key] = touched
except Exception as e:
    print(f"TSLA 오류: {e}")

# BTC 200일선
try:
    daily = get_prices("BTC-USD")
    touched, price, ma_val = check_ma_touch(daily, 200)
    key = "btc_ma200_touched"
    if touched and not state.get(key, False):
        if not within_cooldown(state.get("btc_ma200_alert")):
            alerts.append(f"📊 BTC 200일선 터치! ${price:.0f} / MA ${ma_val:.0f}")
            state["btc_ma200_alert"] = today
    state[key] = touched
except Exception as e:
    print(f"BTC 오류: {e}")

# 전송
if alerts:
    msg = "🔔 시장 알림\n" + "─"*20 + "\n" + "\n".join(alerts)
    send_telegram(msg)
    print(msg)
else:
    print("알람 없음")

save_state(state)


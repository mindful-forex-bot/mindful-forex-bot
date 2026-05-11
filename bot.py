import pandas as pd
import numpy as np
import asyncio
import os
import requests
import pandas_ta as ta
from twelvedata import TDClient
from datetime import datetime, time

# --- MFBS LOGIC CONFIG ---
NTFY_TOPIC = "mfbs" 
TD_KEY = os.getenv("TWELVE_DATA_KEY")
SYMBOLS = ["XAU/USD", "EUR/USD", "GBP/USD", "BTC/USD"]

# --- UPDATED FILTER SETTINGS (OPTIMIZED FOR H1) ---
PIP_FLOOR = 10.0       # Lowered slightly to capture more moves
MIN_ADX = 22.0        # Dropped from 30 to catch trends as they form
MAX_CHASE_PIPS = 12.0  # Increased from 5 to account for H1 volatility/Gold jumps
EXTREME_GREED = 85    # Filter for BTC buys
EXTREME_FEAR = 15     # Filter for BTC sells

# --- SESSION TIMES (LAS VEGAS / PDT) ---
LONDON_START = time(23, 0) # 11:00 PM
LONDON_END = time(8, 0)    # 8:00 AM
NY_START = time(5, 0)      # 5:00 AM
NY_END = time(14, 0)       # 2:00 PM

def get_active_session():
    """Checks current time vs London and NY hours (PDT)."""
    now = datetime.now().time()
    
    is_london = now >= LONDON_START or now <= LONDON_END
    is_ny = NY_START <= now <= NY_END
    
    if is_london and is_ny:
        return True, "London/NY Overlap"
    elif is_london:
        return True, "London Session"
    elif is_ny:
        return True, "New York Session"
    
    return False, "Market Lull"

def get_sentiment():
    """Fetches Crypto Fear & Greed Index (0-100)."""
    try:
        response = requests.get("https://api.alternative.me/fng/?limit=1").json()
        val = int(response['data'][0]['value'])
        label = response['data'][0]['value_classification']
        return val, label
    except:
        return 50, "Neutral"

def calculate_chandelier(df, period=22, multiplier=3.0):
    """MFBS Custom Chandelier Exit."""
    df.columns = [x.lower() for x in df.columns]
    atr = ta.atr(df['high'], df['low'], df['close'], length=period)
    long_stop = df['high'].rolling(period).max() - (atr * multiplier)
    short_stop = df['low'].rolling(period).min() + (atr * multiplier)
    return long_stop, short_stop, atr 

def send_ntfy_push(title, message, tags="chart,moneybag", priority="high"):
    """Broadcasts signal directly to the ntfy app on your phone."""
    try:
        requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", 
            data=message.encode('utf-8'),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": tags,
                "Click": "https://www.tradingview.com/chart/"
            })
        return True
    except Exception as e:
        print(f"❌ ntfy error: {e}")
        return False

async def send_msg(pair, action, price, sl, adx_val, fng_info, session_name):
    risk = abs(price - sl)
    tp = price + (risk * 3) if "BUY" in action else price - (risk * 3)
    
    mult = 100 if "XAU" in pair or "JPY" in pair else 10000
    pips = abs(price - tp) * mult
    
    if pips < PIP_FLOOR:
        return False 

    prec = 2 if "XAU" in pair or "BTC" in pair else 5

    title = f"MFBS LOGIC: {pair}"
    msg = (f"{action} \n"
           f"Session: {session_name}\n\n"
           f"Entry: {price:.{prec}f}\n"
           f"TP: {tp:.{prec}f} 🎯 (+{pips:.1f} Pips)\n"
           f"SL: {sl:.{prec}f} 🛑\n\n"
           f"ADX: {adx_val:.2f} | Sentiment: {fng_info}\n"
           f"Trend: Daily Confirmed")

    return send_ntfy_push(title, msg)

async def run_scan():
    fng_val, fng_label = get_sentiment()
    fng_info = f"{fng_val} ({fng_label})"

    active, session_name = get_active_session()

    if not active:
        print(f"💤 {session_name}: Outside high-volume hours. Sentiment: {fng_info}")
        return

    print(f"🔍 MFBS Logic: Scanning H1 | {session_name} | Sentiment: {fng_info}")
    td = TDClient(apikey=TD_KEY)
    signal_triggered = False 
    
    for symbol in SYMBOLS:
        try:
            ts_d = td.time_series(symbol=symbol, interval="1day", outputsize=50).as_pandas()
            ch_l_d, ch_s_d, _ = calculate_chandelier(ts_d)
            daily_bullish = ts_d.iloc[-1]['close'] > ch_l_d.iloc[-1]
            daily_bearish = ts_d.iloc[-1]['close'] < ch_s_d.iloc[-1]

            ts_h1 = td.time_series(symbol=symbol, interval="1h", outputsize=100).as_pandas()
            ch_l_h1, ch_s_h1, _ = calculate_chandelier(ts_h1)
            
            # Using simple ADX and RSI from pandas_ta
            adx_df = ts_h1.ta.adx(length=14)
            adx_h1 = adx_df['ADX_14'].iloc[-1]
            rsi_h1 = ts_h1.ta.rsi(length=14).iloc[-1]
            
            latest = ts_h1.iloc[-1]
            prev = ts_h1.iloc[-2]
            mult = 100 if "XAU" in symbol or "JPY" in symbol else 10000

            # BUY Logic
            if latest['close'] > ch_l_h1.iloc[-1] and prev['close'] <= ch_l_h1.iloc[-2]:
                if symbol == "BTC/USD" and fng_val >= EXTREME_GREED:
                    print(f"⚠️ {symbol} Buy Blocked: Sentiment too greedy")
                else:
                    chase_dist = (latest['close'] - ch_l_h1.iloc[-1]) * mult
                    if chase_dist <= MAX_CHASE_PIPS:
                        if daily_bullish and adx_h1 > MIN_ADX and rsi_h1 < 65:
                            sent = await send_msg(symbol, "BUY 📈", latest['close'], ch_l_h1.iloc[-1], adx_h1, fng_info, session_name)
                            if sent: signal_triggered = True
            
            # SELL Logic
            elif latest['close'] < ch_s_h1.iloc[-1] and prev['close'] >= ch_s_h1.iloc[-2]:
                if symbol == "BTC/USD" and fng_val <= EXTREME_FEAR:
                    print(f"⚠️ {symbol} Sell Blocked: Sentiment in extreme panic")
                else:
                    chase_dist = (ch_s_h1.iloc[-1] - latest['close']) * mult
                    if chase_dist <= MAX_CHASE_PIPS:
                        if daily_bearish and adx_h1 > MIN_ADX and rsi_h1 > 35:
                            sent = await send_msg(symbol, "SELL 📉", latest['close'], ch_s_h1.iloc[-1], adx_h1, fng_info, session_name)
                            if sent: signal_triggered = True

            await asyncio.sleep(1)

        except Exception as e:
            print(f"❌ Error scanning {symbol}: {e}")

    if not signal_triggered:
        broadcast_msg = (
            f"Session: {session_name}\n"
            f"Mood: {fng_info}\n\n"
            f"No high-probability entries detected. We stay patient. 🛡"
        )
        send_ntfy_push("MFBS SESSION REPORT", broadcast_msg, tags="bar_chart", priority="default")
        print(f"📢 {session_name} Broadcast Sent.")

if __name__ == "__main__":
    async def loop():
        while True:
            await run_scan()
            # Scans once per hour
            print("⏳ Sleeping for 1 hour...")
            await asyncio.sleep(3600) 
            
    # Now correctly calling the loop instead of just a single scan
    asyncio.run(loop())

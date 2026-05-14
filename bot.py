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

# --- LOOSENED FILTER SETTINGS ---
PIP_FLOOR = 8.0         # Lowered from 10.0
MIN_ADX = 18.0          # Lowered from 22.0
MAX_CHASE_PIPS = 25.0   # Increased from 12.0
EXTREME_GREED = 90      
EXTREME_FEAR = 10       

# --- SESSION TIMES (LAS VEGAS / PDT) ---
LONDON_START = time(23, 0) # 11:00 PM
LONDON_END = time(8, 0)    # 8:00 AM
NY_START = time(5, 0)      # 5:00 AM
NY_END = time(14, 0)       # 2:00 PM

def get_active_session():
    now = datetime.now().time()
    is_london = now >= LONDON_START or now <= LONDON_END
    is_ny = NY_START <= now <= NY_END
    
    if is_london and is_ny: return True, "London/NY Overlap"
    elif is_london: return True, "London Session"
    elif is_ny: return True, "New York Session"
    return False, "Market Lull"

def get_sentiment():
    try:
        response = requests.get("https://api.alternative.me/fng/?limit=1").json()
        val = int(response['data'][0]['value'])
        label = response['data'][0]['value_classification']
        return val, label
    except:
        return 50, "Neutral"

def calculate_chandelier(df, period=22, multiplier=3.0):
    df.columns = [x.lower() for x in df.columns]
    atr = ta.atr(df['high'], df['low'], df['close'], length=period)
    long_stop = df['high'].rolling(period).max() - (atr * multiplier)
    short_stop = df['low'].rolling(period).min() + (atr * multiplier)
    return long_stop, short_stop, atr 

def send_ntfy_push(title, message, tags="chart,moneybag", priority="high"):
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
    
    if pips < PIP_FLOOR: return False 

    prec = 2 if "XAU" in pair or "BTC" in pair else 5
    title = f"MFBS LOGIC: {pair}"
    msg = (f"{action} \nSession: {session_name}\n\n"
           f"Entry: {price:.{prec}f}\nTP: {tp:.{prec}f} 🎯\nSL: {sl:.{prec}f} 🛑\n\n"
           f"ADX: {adx_val:.2f} | Sentiment: {fng_info}")
    return send_ntfy_push(title, msg)

async def run_scan():
    fng_val, fng_label = get_sentiment()
    fng_info = f"{fng_val} ({fng_label})"
    active, session_name = get_active_session()

    # --- MODIFIED: BYPASS LULL FOR TESTING ---
    if not active:
        print(f"⚠️ Outside hours ({session_name}), but running scan anyway...")
        session_name = f"Testing ({session_name})"
    else:
        print(f"🔍 Starting MFBS Scan | {session_name}")

    td = TDClient(apikey=TD_KEY)
    signal_triggered = False 
    
    for symbol in SYMBOLS:
        try:
            print(f"📡 Fetching {symbol}...")
            ts_d = td.time_series(symbol=symbol, interval="1day", outputsize=50).as_pandas()
            await asyncio.sleep(2) 
            ts_h1 = td.time_series(symbol=symbol, interval="1h", outputsize=100).as_pandas()
            
            daily_bullish = True 
            daily_bearish = True 

            ch_l_h1, ch_s_h1, _ = calculate_chandelier(ts_h1)
            adx_h1 = ts_h1.ta.adx(length=14)['ADX_14'].iloc[-1]
            rsi_h1 = ts_h1.ta.rsi(length=14).iloc[-1]
            
            latest, prev = ts_h1.iloc[-1], ts_h1.iloc[-2]
            mult = 100 if "XAU" in symbol or "JPY" in symbol else 10000

            # BUY Logic
            if latest['close'] > ch_l_h1.iloc[-1] and prev['close'] <= ch_l_h1.iloc[-2]:
                if not (symbol == "BTC/USD" and fng_val >= EXTREME_GREED):
                    dist = (latest['close'] - ch_l_h1.iloc[-1]) * mult
                    if dist <= MAX_CHASE_PIPS and daily_bullish and adx_h1 > MIN_ADX and rsi_h1 < 75:
                        if await send_msg(symbol, "BUY 📈", latest['close'], ch_l_h1.iloc[-1], adx_h1, fng_info, session_name):
                            signal_triggered = True
            
            # SELL Logic
            elif latest['close'] < ch_s_h1.iloc[-1] and prev['close'] >= ch_s_h1.iloc[-2]:
                if not (symbol == "BTC/USD" and fng_val <= EXTREME_FEAR):
                    dist = (ch_s_h1.iloc[-1] - latest['close']) * mult
                    if dist <= MAX_CHASE_PIPS and daily_bearish and adx_h1 > MIN_ADX and rsi_h1 > 25:
                        if await send_msg(symbol, "SELL 📉", latest['close'], ch_s_h1.iloc[-1], adx_h1, fng_info, session_name):
                            signal_triggered = True

            print(f"✅ {symbol} complete. Pacing for rate limit...")
            await asyncio.sleep(13)

        except Exception as e:
            print(f"❌ Error {symbol}: {e}")
            await asyncio.sleep(15)

    if not signal_triggered:
        send_ntfy_push("MFBS SESSION REPORT", f"Session: {session_name}\nNo entries found. Patience pays.", tags="bar_chart", priority="default")

if __name__ == "__main__":
    asyncio.run(run_scan())

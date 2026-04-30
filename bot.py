import pandas as pd
import numpy as np
import asyncio
import os
import requests
import telegram
import pandas_ta as ta
from twelvedata import TDClient
from datetime import datetime, time

# --- MFBS LOGIC CONFIG ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
TD_KEY = os.getenv("TWELVE_DATA_KEY")
SYMBOLS = ["XAU/USD", "EUR/USD", "GBP/USD", "BTC/USD"]

# --- FILTER SETTINGS ---
PIP_FLOOR = 15.0      
MIN_ADX = 30.0        
MAX_CHASE_PIPS = 5.0  
EXTREME_GREED = 85    # Filter for BTC buys
EXTREME_FEAR = 15     # Filter for BTC sells

# --- SESSION TIMES (LAS VEGAS / PDT) ---
LONDON_START = time(23, 0) # 11:00 PM
LONDON_END = time(8, 0)    # 8:00 AM

def is_london_session():
    """Checks if current time is within high-volume London hours."""
    now = datetime.now().time()
    if now >= LONDON_START or now <= LONDON_END:
        return True
    return False

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

async def send_msg(pair, action, price, sl, adx_val, fng_info, status_msg="London Session Active"):
    bot = telegram.Bot(token=TOKEN)
    
    risk = abs(price - sl)
    tp = price + (risk * 3) if "BUY" in action else price - (risk * 3)
    
    mult = 100 if "XAU" in pair or "JPY" in pair else 10000
    pips = abs(price - tp) * mult
    
    if pips < PIP_FLOOR:
        return False # Signal rejected by floor

    prec = 2 if "XAU" in pair or "BTC" in pair else 5

    msg = (f"🛡 **MFBS LOGIC SCANNER**\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"**Asset:** {pair}\n"
           f"**Action:** {action} ({status_msg})\n\n"
           f"**Entry:** {price:.{prec}f}\n"
           f"**TP:** {tp:.{prec}f} 🎯 (+{pips:.1f} Pips)\n"
           f"**SL:** {sl:.{prec}f} 🛑\n\n"
           f"📈 **ADX:** {adx_val:.2f} | **Sentiment:** {fng_info}\n"
           f"🌍 **Global Trend:** Daily Confirmed\n"
           f"━━━━━━━━━━━━━━━━━━")

    async with bot:
        await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
    return True

async def run_scan():
    # Fetch Market Sentiment for the run
    fng_val, fng_label = get_sentiment()
    fng_info = f"{fng_val} ({fng_label})"

    if not is_london_session():
        print(f"💤 Market Lull: Outside London hours. Current Sentiment: {fng_info}")
        return

    print(f"🔍 MFBS Logic: Scanning H1 | Sentiment: {fng_info}")
    td = TDClient(apikey=TD_KEY)
    signal_triggered = False # Track if any signal was sent
    
    for symbol in SYMBOLS:
        try:
            ts_d = td.time_series(symbol=symbol, interval="1day", outputsize=50).as_pandas()
            ch_l_d, ch_s_d, _ = calculate_chandelier(ts_d)
            daily_bullish = ts_d.iloc[-1]['close'] > ch_l_d.iloc[-1]
            daily_bearish = ts_d.iloc[-1]['close'] < ch_s_d.iloc[-1]

            ts_h1 = td.time_series(symbol=symbol, interval="1h", outputsize=100).as_pandas()
            ch_l_h1, ch_s_h1, _ = calculate_chandelier(ts_h1)
            
            adx_h1 = ts_h1.ta.adx(length=14)['ADX_14'].iloc[-1]
            rsi_h1 = ts_h1.ta.rsi(length=14).iloc[-1]
            
            latest = ts_h1.iloc[-1]
            prev = ts_h1.iloc[-2]
            mult = 100 if "XAU" in symbol or "JPY" in symbol else 10000

            # BUY Logic
            if latest['close'] > ch_l_h1.iloc[-1] and prev['close'] <= ch_l_h1.iloc[-2]:
                if symbol == "BTC/USD" and fng_val >= EXTREME_GREED:
                    print(f"⚠️ {symbol} Buy Blocked: Sentiment too greedy ({fng_val})")
                else:
                    chase_dist = (latest['close'] - ch_l_h1.iloc[-1]) * mult
                    if chase_dist <= MAX_CHASE_PIPS:
                        if daily_bullish and adx_h1 > MIN_ADX and rsi_h1 < 65:
                            sent = await send_msg(symbol, "BUY 📈", latest['close'], ch_l_h1.iloc[-1], adx_h1, fng_info)
                            if sent: signal_triggered = True
            
            # SELL Logic
            elif latest['close'] < ch_s_h1.iloc[-1] and prev['close'] >= ch_s_h1.iloc[-2]:
                if symbol == "BTC/USD" and fng_val <= EXTREME_FEAR:
                    print(f"⚠️ {symbol} Sell Blocked: Sentiment in extreme panic ({fng_val})")
                else:
                    chase_dist = (ch_s_h1.iloc[-1] - latest['close']) * mult
                    if chase_dist <= MAX_CHASE_PIPS:
                        if daily_bearish and adx_h1 > MIN_ADX and rsi_h1 > 35:
                            sent = await send_msg(symbol, "SELL 📉", latest['close'], ch_s_h1.iloc[-1], adx_h1, fng_info)
                            if sent: signal_triggered = True

            await asyncio.sleep(1)

        except Exception as e:
            print(f"❌ Error scanning {symbol}: {e}")

    # HOURLY NEWS BROADCAST: If no technical signal was fired, send a sentiment update
    if not signal_triggered:
        bot = telegram.Bot(token=TOKEN)
        broadcast_msg = (
            f"📊 **MTC HOURLY SENTIMENT REPORT**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"**Current Mood:** {fng_info}\n\n"
            f"**Market Note:** Technical setups are currently forming. No high-probability entries detected this hour. We stay patient and wait for logic confirmation. 🛡\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        async with bot:
            await bot.send_message(chat_id=CHANNEL_ID, text=broadcast_msg, parse_mode="Markdown")
        print("📢 Sentiment Broadcast Sent.")

if __name__ == "__main__":
    asyncio.run(run_scan())

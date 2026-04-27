import pandas as pd
import numpy as np
import asyncio
import os
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
MAX_CHASE_PIPS = 5.0  # <--- KILL SIGNAL if price moved > 5 pips from entry

# --- SESSION TIMES (LAS VEGAS / PDT) ---
LONDON_START = time(23, 0) # 11:00 PM
LONDON_END = time(8, 0)    # 8:00 AM

def is_london_session():
    """Checks if current time is within high-volume London hours."""
    now = datetime.now().time()
    if now >= LONDON_START or now <= LONDON_END:
        return True
    return False

def calculate_chandelier(df, period=22, multiplier=3.0):
    """MFBS Custom Chandelier Exit."""
    df.columns = [x.lower() for x in df.columns]
    atr = ta.atr(df['high'], df['low'], df['close'], length=period)
    long_stop = df['high'].rolling(period).max() - (atr * multiplier)
    short_stop = df['low'].rolling(period).min() + (atr * multiplier)
    return long_stop, short_stop, atr 

async def send_msg(pair, action, price, sl, adx_val, status_msg="London Session Active"):
    bot = telegram.Bot(token=TOKEN)
    
    # Calculate Risk and TP (3:1 Reward-to-Risk)
    risk = abs(price - sl)
    tp = price + (risk * 3) if "BUY" in action else price - (risk * 3)
    
    # Pip Calculation Logic
    mult = 100 if "XAU" in pair or "JPY" in pair else 10000
    pips = abs(price - tp) * mult
    
    # --- GATEKEEPER: Stop small signals ---
    if pips < PIP_FLOOR:
        return 

    prec = 2 if "XAU" in pair or "BTC" in pair else 5

    msg = (f"🛡 **MFBS LOGIC SCANNER**\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"**Asset:** {pair}\n"
           f"**Action:** {action} ({status_msg})\n\n"
           f"**Entry:** {price:.{prec}f}\n"
           f"**TP:** {tp:.{prec}f} 🎯 (+{pips:.1f} Pips)\n"
           f"**SL:** {sl:.{prec}f} 🛑\n\n"
           f"📈 **ADX:** {adx_val:.2f} | **TF:** 1-Hour\n"
           f"🌍 **Global Trend:** Daily Confirmed\n"
           f"━━━━━━━━━━━━━━━━━━")

    async with bot:
        await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")

async def run_scan():
    # 1. SESSION CHECK: Only trade London Session
    if not is_london_session():
        print("💤 Market Lull: Outside London hours. Scanner sleeping...")
        return

    print(f"🔍 MFBS Logic: Scanning H1 | Session: London...")
    td = TDClient(apikey=TD_KEY)
    
    for symbol in SYMBOLS:
        try:
            # Check DAILY Trend
            ts_d = td.time_series(symbol=symbol, interval="1day", outputsize=50).as_pandas()
            ch_l_d, ch_s_d, _ = calculate_chandelier(ts_d)
            daily_bullish = ts_d.iloc[-1]['close'] > ch_l_d.iloc[-1]
            daily_bearish = ts_d.iloc[-1]['close'] < ch_s_d.iloc[-1]

            # Check 1-HOUR Entry
            ts_h1 = td.time_series(symbol=symbol, interval="1h", outputsize=100).as_pandas()
            ch_l_h1, ch_s_h1, _ = calculate_chandelier(ts_h1)
            
            adx_h1 = ts_h1.ta.adx(length=14)['ADX_14'].iloc[-1]
            rsi_h1 = ts_h1.ta.rsi(length=14).iloc[-1]
            
            latest = ts_h1.iloc[-1]
            prev = ts_h1.iloc[-2]
            mult = 100 if "XAU" in symbol or "JPY" in symbol else 10000

            # BUY Logic + Anti-Chase
            if latest['close'] > ch_l_h1.iloc[-1] and prev['close'] <= ch_l_h1.iloc[-2]:
                chase_dist = (latest['close'] - ch_l_h1.iloc[-1]) * mult
                if chase_dist <= MAX_CHASE_PIPS: # Only fire if we are close to entry
                    if daily_bullish and adx_h1 > MIN_ADX and rsi_h1 < 65:
                        await send_msg(symbol, "BUY 📈", latest['close'], ch_l_h1.iloc[-1], adx_h1)
                else:
                    print(f"⚠️ {symbol} Buy skipped: Price moved {chase_dist:.1f} pips past entry.")

            # SELL Logic + Anti-Chase
            elif latest['close'] < ch_s_h1.iloc[-1] and prev['close'] >= ch_s_h1.iloc[-2]:
                chase_dist = (ch_s_h1.iloc[-1] - latest['close']) * mult
                if chase_dist <= MAX_CHASE_PIPS:
                    if daily_bearish and adx_h1 > MIN_ADX and rsi_h1 > 35:
                        await send_msg(symbol, "SELL 📉", latest['close'], ch_s_h1.iloc[-1], adx_h1)
                else:
                    print(f"⚠️ {symbol} Sell skipped: Price moved {chase_dist:.1f} pips past entry.")

            print(f"✅ {symbol} check complete.")
            await asyncio.sleep(1)

        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_scan())

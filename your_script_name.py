import pandas as pd
import numpy as np
import asyncio
import os
import telegram
import time
from twelvedata import TDClient

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
TD_KEY = os.getenv("TWELVE_DATA_KEY")

SYMBOLS = ["XAU/USD", "EUR/USD", "GBP/USD", "BTC/USD"]

# Helper: Professional Pip Calculation
def get_pips(pair, entry, current, action):
    if any(x in pair for x in ["XAU", "BTC", "JPY"]):
        multiplier = 10 if "XAU" in pair else 1 # Gold uses 10 for standard pip feel
    else:
        multiplier = 10000 # Standard Forex
    
    diff = current - entry if "BUY" in action else entry - current
    return round(diff * multiplier, 1)

async def send_pre_alert(pair):
    """Sends a heads-up so people can open their apps ASAP."""
    bot = telegram.Bot(token=TOKEN)
    display_name = "GOLD (XAU/USD)" if "XAU" in pair else pair
    msg = (
        f"🏛️ **MINDFUL PRE-ALERT**\n\n"
        f"**Asset:** {display_name}\n"
        f"**Status:** MTC Logic is detecting high volume. 📊\n"
        f"📢 _Get ready. Signal incoming shortly._"
    )
    async with bot:
        await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")

async def send_msg(pair, action, price, sl):
    bot = telegram.Bot(token=TOKEN)
    display_name = "GOLD (XAU/USD)" if "XAU" in pair else pair
    
    # 1:3 Risk/Reward
    risk = abs(price - sl)
    tp = price + (risk * 3) if "BUY" in action else price - (risk * 3)
    
    prec = 2 if any(x in pair for x in ["XAU", "BTC"]) else 5

    msg = (
        f"🚨 **MINDFUL FOREX BOT SIGNAL**\n\n"
        f"**Asset:** {display_name}\n"
        f"**Action:** {action}\n\n"
        f"**Entry:** {price:.{prec}f}\n"
        f"**Take Profit:** {tp:.{prec}f} 🎯\n"
        f"**Stop Loss:** {sl:.{prec}f} 🛑\n\n"
        f"✨ _High Reward | Trend Aligned Exclusive_"
    )
    
    try:
        async with bot:
            await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
        print(f"✅ Signal sent for {display_name}")
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

def calculate_chandelier(df, period=22, multiplier=3.5):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    atr = true_range.rolling(period).mean()

    long_stop = df['high'].rolling(period).max() - (atr * multiplier)
    short_stop = df['low'].rolling(period).min() + (atr * multiplier)
    return long_stop, short_stop

async def run_scan():
    td = TDClient(apikey=TD_KEY)
    for symbol in SYMBOLS:
        print(f"--- MTC Scan: {symbol} ---")
        try:
            # 1. 1-HOUR TREND
            ts_1h = td.time_series(symbol=symbol, interval="1h", outputsize=50).as_pandas()
            ch_long_1h, ch_short_1h = calculate_chandelier(ts_1h)
            is_bullish_1h = ts_1h.iloc[-1]['close'] > ch_long_1h.iloc[-1]
            is_bearish_1h = ts_1h.iloc[-1]['close'] < ch_short_1h.iloc[-1]

            # 2. 15-MINUTE ENTRY
            ts_15 = td.time_series(symbol=symbol, interval="15min", outputsize=50).as_pandas()
            ch_long_15, ch_short_15 = calculate_chandelier(ts_15)

            latest = ts_15.iloc[-1]
            prev = ts_15.iloc[-2]

            # NEW: PRE-ALERT LOGIC (Price is within 0.05% of breaking the stop)
            dist_to_long = abs(latest['close'] - ch_long_15.iloc[-1]) / latest['close']
            if dist_to_long < 0.0005: # Very close to a breakout
                 await send_pre_alert(symbol)

            # 3. TRIGGER LOGIC
            if latest['close'] > ch_long_15.iloc[-1] and prev['close'] <= ch_long_15.iloc[-2]:
                if is_bullish_1h:
                    await send_msg(symbol, "BUY 📈", latest['close'], ch_long_15.iloc[-1])

            elif latest['close'] < ch_short_15.iloc[-1] and prev['close'] >= ch_short_15.iloc[-2]:
                if is_bearish_1h:
                    await send_msg(symbol, "SELL 📉", latest['close'], ch_short_15.iloc[-1])
            
            time.sleep(1) 
            
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_scan())

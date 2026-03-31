import pandas as pd
import numpy as np
import asyncio
import os
import telegram
import time
from twelvedata import TDClient

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
TD_KEY = os.getenv("TWELVE_DATA_KEY")

# Official Watchlist - Stick to top 4 to stay under 800-credit daily limit with MTC
# Or run every 30 minutes for all 8 symbols.
SYMBOLS = ["XAU/USD", "EUR/USD", "GBP/USD", "BTC/USD"]

async def send_msg(pair, action, price, sl):
    bot = telegram.Bot(token=TOKEN)
    display_name = "GOLD (XAU/USD)" if "XAU" in pair else pair
    
    # Calculate a 1:2 Risk/Reward Take Profit
    risk = abs(price - sl)
    tp = price + (risk * 2) if "BUY" in action else price - (risk * 2)
    
    # Formatting precision
    prec = 2 if any(x in pair for x in ["XAU", "BTC"]) else 5

    msg = (
        f"🚨 **MINDFUL FOREX BOT SIGNAL**\n\n"
        f"**Asset:** {display_name}\n"
        f"**Action:** {action}\n\n"
        f"**Entry:** {price:.{prec}f}\n"
        f"**Take Profit:** {tp:.{prec}f} 🎯\n"
        f"**Stop Loss:** {sl:.{prec}f} 🛑\n\n"
        f"✨ _Trend Aligned | Mindful Trading Exclusive_"
    )
    
    try:
        async with bot:
            await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
        print(f"✅ Signal sent for {display_name}")
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

def calculate_chandelier(df, period=22, multiplier=2.5):
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    atr = true_range.rolling(period).mean()

    long_stop = df['High'].rolling(period).max() - (atr * multiplier)
    short_stop = df['Low'].rolling(period).min() + (atr * multiplier)
    return long_stop, short_stop

async def run_scan():
    td = TDClient(apikey=TD_KEY)
    for symbol in SYMBOLS:
        print(f"--- MTC Scan (15M + 1H): {symbol} ---")
        try:
            # 1. GET 1-HOUR TREND DATA
            ts_1h = td.time_series(symbol=symbol, interval="1h", outputsize=50)
            df_1h = ts_1h.as_pandas()
            df_1h.columns = [c.capitalize() for c in df_1h.columns]
            df_1h = df_1h.sort_index(ascending=True)
            ch_long_1h, ch_short_1h = calculate_chandelier(df_1h)
            
            is_bullish_1h = df_1h.iloc[-1]['Close'] > ch_long_1h.iloc[-1]
            is_bearish_1h = df_1h.iloc[-1]['Close'] < ch_short_1h.iloc[-1]

            # 2. GET 15-MINUTE ENTRY DATA
            ts_15 = td.time_series(symbol=symbol, interval="15min", outputsize=50)
            df_15 = ts_15.as_pandas()
            df_15.columns = [c.capitalize() for c in df_15.columns]
            df_15 = df_15.sort_index(ascending=True)
            df_15['Ch_Long'], df_15['Ch_Short'] = calculate_chandelier(df_15)

            latest = df_15.iloc[-1]
            prev = df_15.iloc[-2]

            # 3. TRIGGER LOGIC WITH TREND FILTER
            # BUY only if 1H trend is up
            if latest['Close'] > latest['Ch_Long'] and prev['Close'] <= prev['Ch_Long']:
                if is_bullish_1h:
                    await send_msg(symbol, "BUY 📈", latest['Close'], latest['Ch_Long'])
                else:
                    print(f"⚠️ {symbol} Buy signal ignored (1H Trend Bearish)")

            # SELL only if 1H trend is down
            elif latest['Close'] < latest['Ch_Short'] and prev['Close'] >= prev['Ch_Short']:
                if is_bearish_1h:
                    await send_msg(symbol, "SELL 📉", latest['Close'], latest['Ch_Short'])
                else:
                    print(f"⚠️ {symbol} Sell signal ignored (1H Trend Bullish)")
            
            else:
                print(f"No signal for {symbol}.")
            
            time.sleep(2) # Safe buffer for Twelve Data
            
        except Exception as e:
            print(f"❌ Error scanning {symbol}: {e}")

if __name__ == "__main__":
    if not TOKEN or not TD_KEY:
        print("❌ Missing Secrets!")
    else:
        asyncio.run(run_scan())

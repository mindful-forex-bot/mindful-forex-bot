import pandas as pd
import numpy as np
import asyncio
import os
import telegram
import time
import mplfinance as mpf
from twelvedata import TDClient

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
TD_KEY = os.getenv("TWELVE_DATA_KEY")

SYMBOLS = ["XAU/USD", "EUR/USD", "GBP/USD", "BTC/USD"]

def generate_chart(df, symbol, entry, tp, sl):
    """Generates a professional signal chart with TP/SL lines."""
    plot_df = df.tail(30).copy()
    plot_df.index = pd.to_datetime(plot_df.index)
    
    # Define horizontal lines: Entry (Blue), TP (Green), SL (Red)
    h_lines = dict(hlines=[entry, tp, sl], 
                   colors=['#3498db', '#2ecc71', '#e74c3c'], 
                   linestyle='dashed', linewidths=1.5)

    file_path = f"signal_{symbol.replace('/', '_')}.png"
    mpf.plot(plot_df, type='candle', style='charles',
             title=f"\n{symbol} Signal Analysis",
             hlines=h_lines, savefig=file_path, tight_layout=True)
    return file_path

async def send_msg(pair, action, price, sl, df_for_chart):
    bot = telegram.Bot(token=TOKEN)
    display_name = "GOLD (XAU/USD)" if "XAU" in pair else pair
    
    risk = abs(price - sl)
    tp = price + (risk * 3) if "BUY" in action else price - (risk * 3)
    prec = 2 if any(x in pair for x in ["XAU", "BTC"]) else 5

    # Generate the chart image
    chart_file = generate_chart(df_for_chart, pair, price, tp, sl)

    msg = (
        f"🚨 **MINDFUL SIGNAL**\n\n"
        f"**Asset:** {display_name}\n"
        f"**Action:** {action}\n\n"
        f"**Entry:** {price:.{prec}f}\n"
        f"**Take Profit:** {tp:.{prec}f} 🎯\n"
        f"**Stop Loss:** {sl:.{prec}f} 🛑\n\n"
        f"✨ _High Reward | Trend Aligned_"
    )
    
    try:
        async with bot:
            with open(chart_file, 'rb') as photo:
                await bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=msg, parse_mode="Markdown")
        print(f"✅ Visual Signal sent for {display_name}")
    except Exception as e:
        print(f"❌ Telegram Error: {e}")
    finally:
        if os.path.exists(chart_file):
            os.remove(chart_file)

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
        try:
            # Optimize: Get 1h and 15m in one loop
            ts_1h = td.time_series(symbol=symbol, interval="1h", outputsize=50).as_pandas()
            ch_long_1h, ch_short_1h = calculate_chandelier(ts_1h)
            
            ts_15 = td.time_series(symbol=symbol, interval="15min", outputsize=50).as_pandas()
            ch_long_15, ch_short_15 = calculate_chandelier(ts_15)

            latest = ts_15.iloc[-1]
            prev = ts_15.iloc[-2]

            # TRIGGER LOGIC with Trend Alignment
            if latest['close'] > ch_long_15.iloc[-1] and prev['close'] <= ch_long_15.iloc[-2]:
                if ts_1h.iloc[-1]['close'] > ch_long_1h.iloc[-1]: # Trend Check
                    await send_msg(symbol, "BUY 📈", latest['close'], ch_long_15.iloc[-1], ts_15)

            elif latest['close'] < ch_short_15.iloc[-1] and prev['close'] >= ch_short_15.iloc[-2]:
                if ts_1h.iloc[-1]['close'] < ch_short_1h.iloc[-1]: # Trend Check
                    await send_msg(symbol, "SELL 📉", latest['close'], ch_short_15.iloc[-1], ts_15)
            
            time.sleep(2) # Avoid rate limits
            
        except Exception as e:
            print(f"❌ Error scanning {symbol}: {e}")

if __name__ == "__main__":
    asyncio.run(run_scan())

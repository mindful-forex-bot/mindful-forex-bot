import pandas as pd
import numpy as np
import asyncio
import os
import telegram
from twelvedata import TDClient

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
TD_KEY = os.getenv("TWELVE_DATA_KEY")

SYMBOLS = ["XAU/USD", "EUR/USD", "GBP/USD"]

async def send_msg(pair, action, price, sl):
    bot = telegram.Bot(token=TOKEN)
    display_name = "GOLD (XAUUSD)" if "XAU" in pair else pair
    msg = (
        f"🚨 **MINDFUL ALPHA SIGNAL**\n\n"
        f"**Asset:** {display_name}\n"
        f"**Action:** {action}\n"
        f"**Entry:** {price:.2f}\n"
        f"**Exit (SL):** {sl:.2f}\n\n"
        f"✨ _Mindful Trading Exclusive_"
    )
    try:
        async with bot:
            await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
        print(f"✅ Signal sent for {display_name}")
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

def calculate_chandelier(df, period=22, multiplier=2.5):
    # Manual ATR Calculation
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    atr = true_range.rolling(period).mean()

    # Chandelier Logic
    long_stop = df['High'].rolling(period).max() - (atr * multiplier)
    short_stop = df['Low'].rolling(period).min() + (atr * multiplier)
    return long_stop, short_stop

async def run_scan():
    td = TDClient(apikey=TD_KEY)
    for symbol in SYMBOLS:
        print(f"--- 15M Scan: {symbol} ---")
        try:
            ts = td.time_series(symbol=symbol, interval="15min", outputsize=100)
            df = ts.as_pandas()
            if df is None or df.empty:
                print(f"⚠️ No data for {symbol}.")
                continue

            df.columns = [c.capitalize() for c in df.columns]
            df = df.sort_index(ascending=True)

            # Manual Math (No pandas-ta needed!)
            df['Ch_Long'], df['Ch_Short'] = calculate_chandelier(df)

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            print(f"Price: {latest['Close']:.2f} | Long: {latest['Ch_Long']:.2f} | Short: {latest['Ch_Short']:.2f}")

            if latest['Close'] > latest['Ch_Long'] and prev['Close'] <= prev['Ch_Long']:
                await send_msg(symbol, "BUY 📈", latest['Close'], latest['Ch_Long'])
            elif latest['Close'] < latest['Ch_Short'] and prev['Close'] >= prev['Ch_Short']:
                await send_msg(symbol, "SELL 📉", latest['Close'], latest['Ch_Short'])
            else:
                print(f"No signal for {symbol}.")
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    if not TOKEN or not TD_KEY:
        print("❌ Missing Secrets!")
    else:
        asyncio.run(run_scan())

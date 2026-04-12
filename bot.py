import pandas as pd
import numpy as np
import asyncio
import os
import telegram
import pandas_ta as ta
from twelvedata import TDClient

# --- MFBS LOGIC CONFIG ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
TD_KEY = os.getenv("TWELVE_DATA_KEY")
SYMBOLS = ["XAU/USD", "EUR/USD", "GBP/USD", "BTC/USD"]

def calculate_chandelier(df, period=22, multiplier=3.0):
    """MFBS Custom Chandelier Exit."""
    df.columns = [x.lower() for x in df.columns]
    atr = ta.atr(df['high'], df['low'], df['close'], length=period)
    long_stop = df['high'].rolling(period).max() - (atr * multiplier)
    short_stop = df['low'].rolling(period).min() + (atr * multiplier)
    return long_stop, short_stop

async def send_msg(pair, action, price, sl, adx_val):
    bot = telegram.Bot(token=TOKEN)
    
    # 3:1 Reward Ratio for larger pip moves
    risk = abs(price - sl)
    tp = price + (risk * 3) if "BUY" in action else price - (risk * 3)

    # Pip Calculation (Handles Gold and FX)
    mult = 100 if "XAU" in pair or "JPY" in pair else 10000
    pips = abs(price - tp) * mult
    prec = 2 if "XAU" in pair or "BTC" in pair else 5

    msg = (f"🛡 **MFBS LOGIC SCANNER**\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"**Asset:** {pair}\n"
           f"**Action:** {action} (Trend Aligned)\n\n"
           f"**Entry:** {price:.{prec}f}\n"
           f"**TP:** {tp:.{prec}f} 🎯 (+{pips:.1f} Pips)\n"
           f"**SL:** {sl:.{prec}f} 🛑\n\n"
           f"📈 **ADX:** {adx_val:.2f} | **TF:** 1-Hour\n"
           f"🌍 **Global Trend:** Daily Confirmed\n"
           f"━━━━━━━━━━━━━━━━━━")

    async with bot:
        await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")

async def run_scan():
    print(f"🔍 MFBS Logic: Scanning H1 with D1 Trend Filter...")
    td = TDClient(apikey=TD_KEY)
    
    for symbol in SYMBOLS:
        try:
            # 1. Check DAILY Trend (The "Boss" Timeframe)
            ts_d = td.time_series(symbol=symbol, interval="1day", outputsize=50).as_pandas()
            ch_long_d, ch_short_d = calculate_chandelier(ts_d)
            daily_bullish = ts_d.iloc[-1]['close'] > ch_long_d.iloc[-1]
            daily_bearish = ts_d.iloc[-1]['close'] < ch_short_d.iloc[-1]

            # 2. Check 1-HOUR Entry
            ts_h1 = td.time_series(symbol=symbol, interval="1h", outputsize=50).as_pandas()
            ch_long_h1, ch_short_h1 = calculate_chandelier(ts_h1)
            adx_h1 = ts_h1.ta.adx(length=14)['ADX_14'].iloc[-1]
            
            latest = ts_h1.iloc[-1]
            prev = ts_h1.iloc[-2]

            # --- MULTI-TIMEFRAME SIGNAL LOGIC ---
            
            # BUY if 1H crosses UP and Daily is BULLISH
            if latest['close'] > ch_long_h1.iloc[-1] and prev['close'] <= ch_long_h1.iloc[-2]:
                if daily_bullish and adx_h1 > 25:
                    await send_msg(symbol, "BUY 📈", latest['close'], ch_long_h1.iloc[-1], adx_h1)

            # SELL if 1H crosses DOWN and Daily is BEARISH
            elif latest['close'] < ch_short_h1.iloc[-1] and prev['close'] >= ch_short_h1.iloc[-2]:
                if daily_bearish and adx_h1 > 25:
                    await send_msg(symbol, "SELL 📉", latest['close'], ch_short_h1.iloc[-1], adx_h1)

            print(f"✅ {symbol} check complete.")
            await asyncio.sleep(1)

        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_scan())

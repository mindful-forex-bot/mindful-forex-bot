import pandas as pd
import numpy as np
import asyncio
import os
import telegram
import time
import mplfinance as mpf
import pandas_ta as ta
from twelvedata import TDClient

print("🚀 BOT STARTING: Checking Markets...")

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
TD_KEY = os.getenv("TWELVE_DATA_KEY")

SYMBOLS = ["XAU/USD", "EUR/USD", "GBP/USD", "BTC/USD"]

def validate_signal_logic(action, entry, sl, adx_value):
    """Prevents upside-down signals and overextended trends."""
    if adx_value > 45:
        print(f"⚠️ Signal Rejected: ADX is {adx_value:.2f} (Trend may be exhausted)")
        return False
    
    # Check if SL is on the wrong side of the entry
    if "BUY" in action and sl >= entry:
        print(f"❌ Rejected: BUY Stop Loss ({sl}) is above Entry ({entry})")
        return False
    if "SELL" in action and sl <= entry:
        print(f"❌ Rejected: SELL Stop Loss ({sl}) is below Entry ({entry})")
        return False
        
    return True

def generate_chart(df, symbol, entry, tp, sl):
    """Generates a technical analysis chart with TP/SL levels."""
    plot_df = df.tail(30).copy()
    plot_df.index = pd.to_datetime(plot_df.index)
    
    h_lines = dict(
        hlines=[entry, tp, sl], 
        colors=['#3498db', '#2ecc71', '#e74c3c'], 
        linestyle='dashed', 
        linewidths=1.5
    )
    
    file_path = f"signal_{symbol.replace('/', '_')}.png"
    mpf.plot(
        plot_df, 
        type='candle', 
        style='charles', 
        title=f"\n{symbol} Analysis", 
        hlines=h_lines, 
        savefig=file_path
    )
    return file_path

async def send_msg(pair, action, price, sl, df_for_chart, adx_val):
    """Calculates risk/reward and sends the Telegram alert."""
    
    # 1. Logic Validation
    if not validate_signal_logic(action, price, sl, adx_val):
        return

    bot = telegram.Bot(token=TOKEN)
    
    # 2. Calculate Risk and TP (3:1 Reward Ratio)
    risk = abs(price - sl)
    
    if "BUY" in action:
        tp = price + (risk * 3)
    else:  # SELL
        tp = price - (risk * 3)

    # 3. Handle Precision (2 decimals for XAU/BTC, 5 for FX)
    prec = 2 if any(x in pair for x in ["XAU", "BTC"]) else 5
    
    # 4. Create Visuals and Send
    chart_file = generate_chart(df_for_chart, pair, price, tp, sl)
    
    msg = (f"🚨 **MINDFUL SIGNAL**\n\n"
           f"**Asset:** {pair}\n"
           f"**Action:** {action}\n\n"
           f"**Entry:** {price:.{prec}f}\n"
           f"**TP:** {tp:.{prec}f} 🎯\n"
           f"**SL:** {sl:.{prec}f} 🛑\n\n"
           f"📊 **ADX:** {adx_val:.2f}")

    async with bot:
        with open(chart_file, 'rb') as photo:
            await bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=msg, parse_mode="Markdown")
    
    # Clean up local file
    if os.path.exists(chart_file):
        os.remove(chart_file)

def calculate_chandelier(df, period=22, multiplier=3.5):
    """Custom Chandelier Exit Calculation."""
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    
    atr = np.max(ranges, axis=1).rolling(period).mean()
    
    long_stop = df['high'].rolling(period).max() - (atr * multiplier)
    short_stop = df['low'].rolling(period).min() + (atr * multiplier)
    
    return long_stop, short_stop

async def run_scan():
    """Main scanning loop."""
    print(f"🔍 Scanning {len(SYMBOLS)} symbols...")
    td = TDClient(apikey=TD_KEY)
    
    for symbol in SYMBOLS:
        try:
            # Get 1-Hour Trend Context
            ts_1h = td.time_series(symbol=symbol, interval="1h", outputsize=50).as_pandas()
            adx_df = ts_1h.ta.adx(length=14)
            current_adx = adx_df['ADX_14'].iloc[-1]
            ch_long_1h, ch_short_1h = calculate_chandelier(ts_1h)

            # Get 15-Min Entry Context
            ts_15 = td.time_series(symbol=symbol, interval="15min", outputsize=50).as_pandas()
            ch_long_15, ch_short_15 = calculate_chandelier(ts_15)
            
            latest = ts_15.iloc[-1]
            prev = ts_15.iloc[-2]
            
            # --- SIGNAL LOGIC: Chandelier Alignment ---
            
            # BUY Condition: 15m Price crosses Chandelier Long AND 1h Price is above Chandelier Long
            if latest['close'] > ch_long_15.iloc[-1] and prev['close'] <= ch_long_15.iloc[-2]:
                if ts_1h.iloc[-1]['close'] > ch_long_1h.iloc[-1]:
                    await send_msg(symbol, "BUY 📈", latest['close'], ch_long_15.iloc[-1], ts_15, current_adx)
            
            # SELL Condition: 15m Price crosses Chandelier Short AND 1h Price is below Chandelier Short
            elif latest['close'] < ch_short_15.iloc[-1] and prev['close'] >= ch_short_15.iloc[-2]:
                if ts_1h.iloc[-1]['close'] < ch_short_1h.iloc[-1]:
                    await send_msg(symbol, "SELL 📉", latest['close'], ch_short_15.iloc[-1], ts_15, current_adx)
            
            print(f"✅ {symbol} check complete.")
            await asyncio.sleep(2) # Avoid rate limiting
            
        except Exception as e:
            print(f"❌ Error scanning {symbol}: {e}")

if __name__ == "__main__":
    asyncio.run(run_scan())
    print("🏁 Scan Finished.")

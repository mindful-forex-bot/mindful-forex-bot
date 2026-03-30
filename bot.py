import pandas_ta as ta
import asyncio
import os
import telegram
from twelvedata import TDClient

# Pulling from GitHub Secrets
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
TD_KEY = os.getenv("TWELVE_DATA_KEY")

# Official Twelve Data Symbols
# Note: XAU/USD is the gold standard for Twelve Data
SYMBOLS = ["XAU/USD", "EUR/USD", "GBP/USD"]

async def send_msg(pair, action, price, sl):
    bot = telegram.Bot(token=TOKEN)
    # Formatting the name for the Telegram alert
    display_name = "GOLD (XAUUSD)" if "XAU" in pair else pair
    
    msg = (
        f"🚨 **MINDFUL ALPHA SIGNAL**\n\n"
        f"**Asset:** {display_name}\n"
        f"**Action:** {action}\n"
        f"**Entry:** {price:.4f}\n"
        f"**Exit (SL):** {sl:.4f}\n\n"
        f"✨ _Mindful Trading Exclusive_"
    )
    try:
        async with bot:
            await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
        print(f"✅ Signal sent for {display_name}")
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

async def run_scan():
    # Initialize the Twelve Data Client
    td = TDClient(apikey=TD_KEY)
    
    for symbol in SYMBOLS:
        print(f"--- 15M Scan: {symbol} ---")
        try:
            # Fetch 15-minute data (Last 50 candles)
            ts = td.time_series(symbol=symbol, interval="15min", outputsize=50)
            df = ts.as_pandas()
            
            if df is None or df.empty:
                print(f"⚠️ No data for {symbol}. Check your API key or symbol tier.")
                continue

            # Standardize column names for pandas-ta (Capitalize Open, High, Low, Close)
            df.columns = [c.capitalize() for c in df.columns]
            
            # Ensure data is sorted by time (oldest to newest)
            df = df.sort_index(ascending=True)

            # 1. Calculate ATR (Length 22)
            df['ATR'] = df.ta.atr(length=22)
            
            # 2. Calculate Chandelier Lines (Multiplier 2.5)
            multiplier = 2.5 
            df['HH'] = df['High'].rolling(window=22).max()
            df['LL'] = df['Low'].rolling(window=22).min()
            
            # Long and Short Stop Lines
            df['Ch_Long'] = df['HH'] - (df['ATR'] * multiplier)
            df['Ch_Short'] = df['LL'] + (df['ATR'] * multiplier)

            # Get current and previous values to detect the crossover
            latest = df.iloc[-1]
            prev = df.iloc[-2]

            # LOGGING: This helps you see the numbers in GitHub Action logs
            print(f"Price: {latest['Close']:.4f} | Long Line: {latest['Ch_Long']:.4f} | Short Line: {latest['Ch_Short']:.4f}")

            # SIGNAL LOGIC
            # BUY: Price crosses ABOVE the Long Stop line
            if latest['Close'] > latest['Ch_Long'] and prev['Close'] <= prev['Ch_Long']:
                await send_msg(symbol, "BUY 📈", latest['Close'], latest['Ch_Long'])
            
            # SELL: Price crosses BELOW the Short Stop line
            elif latest['Close'] < latest['Ch_Short'] and prev['Close'] >= prev['Ch_Short']:
                await send_msg(symbol, "SELL 📉", latest['Close'], latest['Ch_Short'])
            
            else:
                # Calculate how far we are from the next potential move
                dist_long = abs(latest['Close'] - latest['Ch_Long'])
                print(f"Waiting for crossover. Distance to Long: {dist_long:.4f}")

        except Exception as e:
            print(f"❌ Error scanning {symbol}: {e}")

if __name__ == "__main__":
    # Safety check for Secrets
    if not TOKEN or not TD_KEY:
        print("❌ CRITICAL: Missing GitHub Secrets (TELEGRAM_BOT_TOKEN or TWELVE_DATA_KEY)")
    else:
        asyncio.run(run_scan())

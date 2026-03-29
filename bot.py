import yfinance as yf
import pandas_ta as ta
import asyncio
import os
import telegram

# Pulling from GitHub Secrets
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
SYMBOLS = ["GC=F", "EURUSD=X", "GBPUSD=X"]

async def send_msg(pair, action, price, sl):
    name = "GOLD (XAUUSD)" if "GC=F" in pair else pair.replace("=X", "")
    bot = telegram.Bot(token=TOKEN)
    
    msg = (
        f"🚨 **MINDFUL ALPHA SIGNAL**\n\n"
        f"**Asset:** {name}\n"
        f"**Action:** {action}\n"
        f"**Entry:** {price:.4f}\n"
        f"**Exit (SL):** {sl:.4f}\n\n"
        f"✨ _Mindful After Hours Exclusive_"
    )
    
    try:
        async with bot:
            await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
        print(f"✅ Signal sent for {name}")
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

async def run_scan():
    for symbol in SYMBOLS:
        print(f"Scanning {symbol}...")
        # Get enough data for the 22-period calculation
        df = yf.download(symbol, period="5d", interval="1h", progress=False)
        
        if df.empty or len(df) < 25:
            print(f"Skipping {symbol}: Need more data.")
            continue

        # FIX: The function is called 'cdl' in the library, not 'chandelier'
        df.ta.cdl(length=22, multiplier=3, append=True)
        
        # Find the columns (they usually look like CHAND_LONG... or CHAND_SHORT...)
        long_col = [c for c in df.columns if 'CHAND_LONG' in c]
        short_col = [c for c in df.columns if 'CHAND_SHORT' in c]

        if not long_col or not short_col:
            print(f"Skipping {symbol}: Chandelier columns not found.")
            continue

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        L_VAL = latest[long_col[0]]
        S_VAL = latest[short_col[0]]
        P_L_VAL = prev[long_col[0]]
        P_S_VAL = prev[short_col[0]]

        # Signal Logic
        if latest['Close'] > L_VAL and prev['Close'] <= P_L_VAL:
            await send_msg(symbol, "BUY 📈", latest['Close'], L_VAL)
        elif latest['Close'] < S_VAL and prev['Close'] >= P_S_VAL:
            await send_msg(symbol, "SELL 📉", latest['Close'], S_VAL)
        else:
            print(f"No signal for {symbol} right now.")

if __name__ == "__main__":
    if not TOKEN or not CHANNEL_ID:
        print("❌ Missing Secrets! Check GitHub Settings.")
    else:
        asyncio.run(run_scan())

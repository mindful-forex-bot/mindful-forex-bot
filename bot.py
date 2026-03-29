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
        df = yf.download(symbol, period="5d", interval="1h", progress=False)
        
        if df.empty or len(df) < 22:
            print(f"Skipping {symbol}: Need more data.")
            continue

        df.ta.chandelier(length=22, multiplier=3, append=True)
        
        # Automatically find the right column names
        long_col = [c for c in df.columns if 'CHAND_LONG' in c][0]
        short_col = [c for c in df.columns if 'CHAND_SHORT' in c][0]

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        if latest['Close'] > latest[long_col] and prev['Close'] <= prev[long_col]:
            await send_msg(symbol, "BUY 📈", latest['Close'], latest[long_col])
        elif latest['Close'] < latest[short_col] and prev['Close'] >= prev[short_col]:
            await send_msg(symbol, "SELL 📉", latest['Close'], latest[short_col])
        else:
            print(f"No signal for {symbol} right now.")

if __name__ == "__main__":
    if not TOKEN or not CHANNEL_ID:
        print("❌ Missing Secrets! Check GitHub Settings.")
    else:
        asyncio.run(run_scan())

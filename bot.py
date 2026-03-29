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
        # Get data and fix the MultiIndex issue immediately
        df = yf.download(symbol, period="5d", interval="1h", progress=False)
        
        if df.empty or len(df) < 25:
            print(f"Skipping {symbol}: Need more data.")
            continue

        # FIX: Flatten the MultiIndex headers so pandas-ta can read them
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

        # 1. Calculate ATR
        df['ATR'] = df.ta.atr(length=22)
        
        # 2. Calculate Chandelier Lines manually (Highest High / Lowest Low)
        df['HH'] = df['High'].rolling(window=22).max()
        df['LL'] = df['Low'].rolling(window=22).min()
        df['Ch_Long'] = df['HH'] - (df['ATR'] * 3)
        df['Ch_Short'] = df['LL'] + (df['ATR'] * 3)

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # Logic: Price crosses ABOVE Chandelier Long = BUY
        if latest['Close'] > latest['Ch_Long'] and prev['Close'] <= prev['Ch_Long']:
            await send_msg(symbol, "BUY 📈", latest['Close'], latest['Ch_Long'])
            
        # Logic: Price crosses BELOW Chandelier Short = SELL
        elif latest['Close'] < latest['Ch_Short'] and prev['Close'] >= prev['Ch_Short']:
            await send_msg(symbol, "SELL 📉", latest['Close'], latest['Ch_Short'])
        else:
            print(f"No signal for {symbol} right now.")

if __name__ == "__main__":
    if not TOKEN or not CHANNEL_ID:
        print("❌ Missing Secrets!")
    else:
        asyncio.run(run_scan())

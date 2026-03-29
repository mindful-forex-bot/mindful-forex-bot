import yfinance as yf
import pandas as pd
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
        
        if df.empty or len(df) < 25:
            print(f"Skipping {symbol}: Need more data.")
            continue

        # MANUAL CHANDELIER CALCULATION (Prevents library crashes)
        # 1. Calculate ATR
        df['ATR'] = df.ta.atr(length=22)
        
        # 2. Calculate Highest High and Lowest Low over 22 periods
        df['HH'] = df['High'].rolling(window=22).max()
        df['LL'] = df['Low'].rolling(window=22).min()
        
        # 3. Calculate Chandelier Lines
        df['Chandelier_Long'] = df['HH'] - (df['ATR'] * 3)
        df['Chandelier_Short'] = df['LL'] + (df['ATR'] * 3)

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # Logic: Price crosses ABOVE Chandelier Long = BUY
        if latest['Close'] > latest['Chandelier_Long'] and prev['Close'] <= prev['Chandelier_Long']:
            await send_msg(symbol, "BUY 📈", latest['Close'], latest['Chandelier_Long'])
            
        # Logic: Price crosses BELOW Chandelier Short = SELL
        elif latest['Close'] < latest['Chandelier_Short'] and prev['Close'] >= prev['Chandelier_Short']:
            await send_msg(symbol, "SELL 📉", latest['Close'], latest['Chandelier_Short'])
        else:
            print(f"No signal for {symbol} right now.")

if __name__ == "__main__":
    if not TOKEN or not CHANNEL_ID:
        print("❌ Missing Secrets! Check GitHub Settings.")
    else:
        asyncio.run(run_scan())

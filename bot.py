import pandas as pd
import numpy as np
import asyncio
import os
import telegram
import pandas_ta as ta
from twelvedata import TDClient
import MetaTrader5 as mt5  # New Import

# --- MFBS LOGIC CONFIG ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
TD_KEY = os.getenv("TWELVE_DATA_KEY")
SYMBOLS = ["XAU/USD", "EUR/USD", "GBP/USD", "BTC/USD"]

# MT5 Configuration
MT5_LOGIN = 12345678  # Replace with your MT5 account number
MT5_PASS = "your_password"
MT5_SERVER = "your_broker_server"

def calculate_chandelier(df, period=22, multiplier=3.0):
    """MFBS Custom Chandelier Exit."""
    df.columns = [x.lower() for x in df.columns]
    atr = ta.atr(df['high'], df['low'], df['close'], length=period)
    long_stop = df['high'].rolling(period).max() - (atr * multiplier)
    short_stop = df['low'].rolling(period).min() + (atr * multiplier)
    return long_stop, short_stop

def execute_mt5_trade(pair, action, price, sl, tp):
    """Executes the trade in MetaTrader 5."""
    # Map TwelveData symbols to MT5 symbols (e.g., XAU/USD -> XAUUSD)
    mt5_symbol = pair.replace("/", "") 
    
    # Check if symbol exists in MT5
    symbol_info = mt5.symbol_info(mt5_symbol)
    if symbol_info is None:
        print(f"❌ {mt5_symbol} not found in MT5")
        return None

    if not symbol_info.visible:
        mt5.symbol_select(mt5_symbol, True)

    trade_type = mt5.ORDER_TYPE_BUY if "BUY" in action else mt5.ORDER_TYPE_SELL
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": mt5_symbol,
        "volume": 0.1,  # Adjust lot size based on your risk
        "type": trade_type,
        "price": mt5.symbol_info_tick(mt5_symbol).ask if trade_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(mt5_symbol).bid,
        "sl": float(sl),
        "tp": float(tp),
        "magic": 101010, # MFBS Bot ID
        "comment": "MFBS Logic Auto-Trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ Trade Failed: {result.comment}")
    else:
        print(f"🚀 Trade Executed: {mt5_symbol} {action}")
    return result

async def send_msg(pair, action, price, sl, adx_val):
    bot = telegram.Bot(token=TOKEN)
    
    # 3:1 Reward Ratio
    risk = abs(price - sl)
    tp = price + (risk * 3) if "BUY" in action else price - (risk * 3)

    # --- EXECUTE TRADE IN MT5 ---
    execute_mt5_trade(pair, action, price, sl, tp)

    # Pip Calculation
    mult = 100 if "XAU" in pair or "JPY" in pair else 10000
    pips = abs(price - tp) * mult
    prec = 2 if "XAU" in pair or "BTC" in pair else 5

    msg = (f"🛡 **MFBS LOGIC SCANNER**\n"
           f"━━━━━━━━━━━━━━━━━━\n"
           f"**Asset:** {pair}\n"
           f"**Action:** {action} (Auto-Executed)\n\n"
           f"**Entry:** {price:.{prec}f}\n"
           f"**TP:** {tp:.{prec}f} 🎯 (+{pips:.1f} Pips)\n"
           f"**SL:** {sl:.{prec}f} 🛑\n\n"
           f"📈 **ADX:** {adx_val:.2f} | **TF:** 1-Hour\n"
           f"🌍 **Global Trend:** Daily Confirmed\n"
           f"━━━━━━━━━━━━━━━━━━")

    async with bot:
        await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")

async def run_scan():
    # Initialize MT5 Connection
    if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASS, server=MT5_SERVER):
        print("❌ MT5 Initialization failed")
        return

    print(f"🔍 MFBS Logic: Trading H1 with D1 Filter...")
    td = TDClient(apikey=TD_KEY)
    
    for symbol in SYMBOLS:
        try:
            # 1. Daily Trend Filter
            ts_d = td.time_series(symbol=symbol, interval="1day", outputsize=50).as_pandas()
            ch_long_d, ch_short_d = calculate_chandelier(ts_d)
            daily_bullish = ts_d.iloc[-1]['close'] > ch_long_d.iloc[-1]
            daily_bearish = ts_d.iloc[-1]['close'] < ch_short_d.iloc[-1]

            # 2. H1 Entry Check
            ts_h1 = td.time_series(symbol=symbol, interval="1h", outputsize=50).as_pandas()
            ch_long_h1, ch_short_h1 = calculate_chandelier(ts_h1)
            adx_h1 = ts_h1.ta.adx(length=14)['ADX_14'].iloc[-1]
            
            latest = ts_h1.iloc[-1]
            prev = ts_h1.iloc[-2]

            # BUY Execution
            if latest['close'] > ch_long_h1.iloc[-1] and prev['close'] <= ch_long_h1.iloc[-2]:
                if daily_bullish and adx_h1 > 25:
                    await send_msg(symbol, "BUY 📈", latest['close'], ch_long_h1.iloc[-1], adx_h1)

            # SELL Execution
            elif latest['close'] < ch_short_h1.iloc[-1] and prev['close'] >= ch_short_h1.iloc[-2]:
                if daily_bearish and adx_h1 > 25:
                    await send_msg(symbol, "SELL 📉", latest['close'], ch_short_h1.iloc[-1], adx_h1)

            print(f"✅ {symbol} check complete.")
            await asyncio.sleep(1)

        except Exception as e:
            print(f"❌ Error: {e}")
    
    mt5.shutdown()

if __name__ == "__main__":
    asyncio.run(run_scan())

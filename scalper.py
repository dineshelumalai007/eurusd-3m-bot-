import time
import MetaTrader5 as mt5

SYMBOL = "EURUSD"
TIMEFRAME = mt5.TIMEFRAME_M3
MAGIC = 998877

BASE_LOT = 0.16           # Max $5 risk
PARTIAL_LOT = 0.10        # 3 Pips profit booking size
SL_POINTS = 30            # 3 Pips SL
PARTIAL_POINTS = 30       # 3 Pips Partial Trigger
RUNNER_TP_POINTS = 60     # 6 Pips Runner TP
MAX_SLIPPAGE = 5
BIG_SPIKE_POINTS = 50     # 5 Pips spike candle

tracked_positions = {}
last_processed_candle_time = None
current_trend = None      # "BUY", "SELL", or None (Neutral/Chop Stopped)

def get_filling_mode(symbol):
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_IOC
    filling_flags = info.filling_mode
    if filling_flags & 1:
        return mt5.ORDER_FILLING_FOK
    elif filling_flags & 2:
        return mt5.ORDER_FILLING_IOC
    else:
        return mt5.ORDER_FILLING_RETURN

def init_mt5():
    if not mt5.initialize():
        print("❌ MT5 initialize panna mudiyala!")
        quit()
    if not mt5.symbol_select(SYMBOL, True):
        print(f"❌ Symbol {SYMBOL} Market Watch-la add panna mudiyala!")
        quit()
    print("✅ MT5 Connected. Scalper Bot Active.")

def get_bot_positions():
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return []
    return [p for p in positions if p.magic == MAGIC]

def close_single_position(ticket, volume, pos_type):
    tick = mt5.symbol_info_tick(SYMBOL)
    price = tick.bid if pos_type == mt5.POSITION_TYPE_BUY else tick.ask
    order_type = mt5.ORDER_TYPE_SELL if pos_type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": ticket,
        "symbol": SYMBOL,
        "volume": volume,
        "type": order_type,
        "price": price,
        "deviation": MAX_SLIPPAGE,
        "magic": MAGIC,
        "comment": "Close_Scale",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(SYMBOL),
    }
    res = mt5.order_send(req)
    return res.retcode == mt5.TRADE_RETCODE_DONE

def close_all_positions(reason="Opposite trend trigger"):
    positions = get_bot_positions()
    for pos in positions:
        close_single_position(pos.ticket, pos.volume, pos.type)
    tracked_positions.clear()
    print(f"🧹 [{reason}]: Running trades ellaam close aayiduchu.")

def place_order(direction):
    tick = mt5.symbol_info_tick(SYMBOL)
    point = mt5.symbol_info(SYMBOL).point

    if direction == "BUY":
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
        sl = price - (SL_POINTS * point)
        tp = price + (RUNNER_TP_POINTS * point)
    else:
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
        sl = price + (SL_POINTS * point)
        tp = price - (RUNNER_TP_POINTS * point)

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": BASE_LOT,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": MAX_SLIPPAGE,
        "magic": MAGIC,
        "comment": f"M3_{direction}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(SYMBOL),
    }

    res = mt5.order_send(req)
    if res.retcode == mt5.TRADE_RETCODE_DONE:
        time.sleep(0.3)
        current_trades = get_bot_positions()
        for t in current_trades:
            if t.ticket not in tracked_positions:
                tracked_positions[t.ticket] = {
                    "partial_done": False,
                    "direction": direction,
                    "open_price": price
                }
        print(f"🚀 [{time.strftime('%H:%M:%S')}] {direction} Entry Opened @ {price}")
    else:
        print(f"❌ Order Failed: Retcode {res.retcode} | {res.comment}")

def move_sl_to_be(ticket, open_price, current_tp):
    req = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "symbol": SYMBOL,
        "sl": open_price,
        "tp": current_tp,
    }
    mt5.order_send(req)

def manage_running_trades():
    positions = get_bot_positions()
    active_tickets = [p.ticket for p in positions]

    for t in list(tracked_positions.keys()):
        if t not in active_tickets:
            del tracked_positions[t]

    if not positions:
        return

    tick = mt5.symbol_info_tick(SYMBOL)
    point = mt5.symbol_info(SYMBOL).point

    for pos in positions:
        ticket = pos.ticket
        if ticket not in tracked_positions:
            direction = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"
            tracked_positions[ticket] = {"partial_done": False, "direction": direction, "open_price": pos.price_open}

        if not tracked_positions[ticket]["partial_done"]:
            gain_points = (tick.bid - pos.price_open) / point if pos.type == mt5.POSITION_TYPE_BUY else (pos.price_open - tick.ask) / point

            if gain_points >= PARTIAL_POINTS:
                if close_single_position(ticket, PARTIAL_LOT, pos.type):
                    print(f"💰 Ticket #{ticket}: +3 Pips hit! 0.10 Lot Booked (+$3.00).")
                    move_sl_to_be(ticket, pos.price_open, pos.tp)
                    tracked_positions[ticket]["partial_done"] = True
                    print(f"⚡ Momentum Add-on: Immediate {tracked_positions[ticket]['direction']} trigger!")
                    place_order(tracked_positions[ticket]["direction"])

def check_candle_pattern():
    global last_processed_candle_time, current_trend

    # 5 closed bars thevai (c1, c2, c3, c4 and current forming)
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 6)
    if rates is None or len(rates) < 6:
        return

    c1 = rates[-2]  # Recent closed
    c2 = rates[-3]  # 2nd closed
    c3 = rates[-4]  # 3rd closed
    c4 = rates[-5]  # 4th closed
    current_candle_time = rates[-1]['time']

    if current_candle_time == last_processed_candle_time:
        return

    last_processed_candle_time = current_candle_time

    point = mt5.symbol_info(SYMBOL).point
    c1_color = "GREEN" if c1['close'] > c1['open'] else "RED"
    c2_color = "GREEN" if c2['close'] > c2['open'] else "RED"
    c3_color = "GREEN" if c3['close'] > c3['open'] else "RED"
    c4_color = "GREEN" if c4['close'] > c4['open'] else "RED"

    c1_size_points = abs(c1['close'] - c1['open']) / point
    c2_body_high = max(c2['open'], c2['close'])
    c2_body_low = min(c2['open'], c2['close'])

    print(f"📊 [{time.strftime('%H:%M:%S')}] Closed: [4: {c4_color}, 3: {c3_color}, 2: {c2_color}, 1: {c1_color}] | Current Trend: {current_trend}")

    # --- Rule 4: Chop Market Alternating Freeze Rule ---
    # BUY poitu irundha: SELL -> BUY -> SELL -> BUY sequence
    if current_trend == "BUY" and c4_color == "RED" and c3_color == "GREEN" and c2_color == "RED" and c1_color == "GREEN":
        print("⚠️ Chop detected (SELL -> BUY -> SELL -> BUY). Bot stop aagi neutral aagudhu.")
        close_all_positions("Chop Freeze")
        current_trend = None
        return

    # SELL poitu irundha: BUY -> SELL -> BUY -> SELL sequence
    if current_trend == "SELL" and c4_color == "GREEN" and c3_color == "RED" and c2_color == "BUY" and c1_color == "RED":
        print("⚠️ Chop detected (BUY -> SELL -> BUY -> SELL). Bot stop aagi neutral aagudhu.")
        close_all_positions("Chop Freeze")
        current_trend = None
        return

    # --- Rule 2: Sudden 5 to 6 Pip Big Spike Reversal ---
    if current_trend == "BUY" and c1_color == "RED" and c1_size_points >= BIG_SPIKE_POINTS:
        print(f"⚡ Sudden 5-Pip Red Spike ({c1_size_points:.1f} pts). Instant reversal to SELL.")
        close_all_positions("Spike Reversal SELL")
        current_trend = "SELL"
        place_order("SELL")
        return

    if current_trend == "SELL" and c1_color == "GREEN" and c1_size_points >= BIG_SPIKE_POINTS:
        print(f"⚡ Sudden 5-Pip Green Spike ({c1_size_points:.1f} pts). Instant reversal to BUY.")
        close_all_positions("Spike Reversal BUY")
        current_trend = "BUY"
        place_order("BUY")
        return

    # --- Rule 5: 1st Candle Body Breakout Override (PDF Image Rule) ---
    # Buy scenario: 2 sell vandhaalum, 1st sell candle body high-ah thaandi single buy candle body close vecha BUY
    if current_trend == "SELL" and c1_color == "GREEN" and c1['close'] > c2_body_high:
        print("🚀 Breakout Override: Single Green candle closed above previous Sell body high. Switching to BUY.")
        close_all_positions("Breakout Override BUY")
        current_trend = "BUY"
        place_order("BUY")
        return

    # Sell scenario: 2 buy vandhaalum, 1st buy candle body low-ah thaandi single sell candle body close vecha SELL
    if current_trend == "BUY" and c1_color == "RED" and c1['close'] < c2_body_low:
        print("🚀 Breakout Override: Single Red candle closed below previous Buy body low. Switching to SELL.")
        close_all_positions("Breakout Override SELL")
        current_trend = "SELL"
        place_order("SELL")
        return

    # --- Rule 1: 2-Candle Trend Switch ---
    if c2_color == "GREEN" and c1_color == "GREEN":
        if current_trend != "BUY":
            print("🔄 2 Green Candles: Trend Switched to BUY.")
            close_all_positions("2 Candle BUY Switch")
            current_trend = "BUY"
            place_order("BUY")

    elif c2_color == "RED" and c1_color == "RED":
        if current_trend != "SELL":
            print("🔄 2 Red Candles: Trend Switched to SELL.")
            close_all_positions("2 Candle SELL Switch")
            current_trend = "SELL"
            place_order("SELL")

def check_reentry():
    # --- Rule 3: Continuous Re-entry if SL Hit during active trend ---
    positions = get_bot_positions()
    if len(positions) == 0 and current_trend is not None:
        print(f"🔁 SL hit / No Active Orders. Re-entering in trend: {current_trend}")
        place_order(current_trend)

init_mt5()

try:
    while True:
        manage_running_trades()
        check_candle_pattern()
        check_reentry()
        time.sleep(0.5)
except KeyboardInterrupt:
    print("🛑 Bot stopped.")
    mt5.shutdown()

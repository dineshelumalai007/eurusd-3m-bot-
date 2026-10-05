import time
import MetaTrader5 as mt5
import pandas as pd

SYMBOL = "EURUSD"
TIMEFRAME = mt5.TIMEFRAME_M3
MAGIC = 998877

BASE_LOT = 0.16           # Max $5 risk
PARTIAL_LOT = 0.10        # 3 Pips profit booking size
SL_POINTS = 30            # 3 Pips SL
PARTIAL_POINTS = 30       # 3 Pips Partial Trigger
RUNNER_TP_POINTS = 60     # 6 Pips Runner TP
MAX_SLIPPAGE = 5

tracked_positions = {}
last_processed_candle_time = None


def get_filling_mode(symbol):
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_IOC
    filling_flags = info.filling_mode
    if filling_flags & 1:  # FOK
        return mt5.ORDER_FILLING_FOK
    elif filling_flags & 2:  # IOC
        return mt5.ORDER_FILLING_IOC
    else:  # RETURN
        return mt5.ORDER_FILLING_RETURN


def init_mt5():
    if not mt5.initialize():
        print("X MT5 initialize panna mudiyala!")
        quit()
    if not mt5.symbol_select(SYMBOL, True):
        print(f"X Symbol {SYMBOL} Market Watch-la add panna mudiyala!")
        quit()
    print("MT5 Connected. Scalper Bot Active.")


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


def close_all_positions():
    positions = get_bot_positions()
    for pos in positions:
        close_single_position(pos.ticket, pos.volume, pos.type)
    tracked_positions.clear()
    print("/ Opposite trend trigger: Running trades ellaam close aayiduchu.")


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
        print(f"[{time.strftime('%H:%M:%S')}] {direction} Entry Opened @ {price}")
    else:
        print(f"Order Failed: Retcode {res.retcode} | {res.comment}")


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

    # Clean up closed positions from memory
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
            tracked_positions[ticket] = {
                "partial_done": False,
                "direction": direction,
                "open_price": pos.price_open
            }

        if not tracked_positions[ticket]["partial_done"]:
            gain_points = (
                (tick.bid - pos.price_open) / point
                if pos.type == mt5.POSITION_TYPE_BUY
                else (pos.price_open - tick.ask) / point
            )

            if gain_points >= PARTIAL_POINTS:
                if close_single_position(ticket, PARTIAL_LOT, pos.type):
                    print(f"Ticket #{ticket}: +3 Pips hit! 0.10 Lot Booked (+$3.00).")
                    move_sl_to_be(ticket, pos.price_open, pos.tp)
                    tracked_positions[ticket]["partial_done"] = True
                    print(f"Momentum Add-on: Immediate {tracked_positions[ticket]['direction']} trigger!")
                    place_order(tracked_positions[ticket]["direction"])


def check_candle_pattern():
    global last_processed_candle_time
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 4)
    if rates is None or len(rates) < 3:
        return

    c1 = rates[-3]
    c2 = rates[-2]
    current_candle_time = rates[-1]['time']

    if current_candle_time == last_processed_candle_time:
        return
    last_processed_candle_time = current_candle_time

    c1_color = "GREEN" if c1['close'] > c1['open'] else "RED"
    c2_color = "GREEN" if c2['close'] > c2['open'] else "RED"

    print(f"[{time.strftime('%H:%M:%S')}] New M3 Candle Started | Last 2 Closed: [1: {c1_color}, 2: {c2_color}]")

    positions = get_bot_positions()
    running_direction = None
    if positions:
        running_direction = "BUY" if positions[0].type == mt5.POSITION_TYPE_BUY else "SELL"

    if c1_color == "GREEN" and c2_color == "GREEN":
        if running_direction == "SELL":
            print("Reversal: 2 Green Candles against SELL.")
            close_all_positions()
            place_order("BUY")
        elif running_direction is None:
            place_order("BUY")

    elif c1_color == "RED" and c2_color == "RED":
        if running_direction == "BUY":
            print("Reversal: 2 Red Candles against BUY.")
            close_all_positions()
            place_order("SELL")
        elif running_direction is None:
            place_order("SELL")


if __name__ == "__main__":
    init_mt5()
    try:
        while True:
            manage_running_trades()
            check_candle_pattern()
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Bot stopped.")
        mt5.shutdown()

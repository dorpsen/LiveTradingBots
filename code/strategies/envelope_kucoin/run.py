import os
import sys
import json
import ta
import time # Added for potential delays
from datetime import datetime

# Adjust the path to point to the directory containing the 'utilities' folder
# Assuming 'run.py' is in '.../strategies/envelope_kucoin/'
# and 'kucoin_futures.py' is in '.../utilities/'
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..')) # Go up three levels

# Import the correct class
from utilities.kucoin_futures import KucoinFutures


# --- CONFIG ---

# <<< --- ADD SANDBOX TOGGLE HERE --- >>>
use_sandbox = True  # SET TO False FOR LIVE TRADING!

params = {
    'base_symbol': 'BTC', # e.g., 'BTC', 'ETH'
    # 'symbol': '/USDT:USDT', # Symbol is now constructed below
    'timeframe': '1h',
    'margin_mode': 'isolated',  # 'cross'
    'balance_fraction': 1, # Fraction of available balance to use for *total* position size across envelopes
    'leverage': 1,
    'average_type': 'DCM',  # 'SMA', 'EMA', 'WMA', 'DCM'
    'average_period': 5,
    'envelopes': [0.07, 0.11, 0.14], # Percentage deviations for entry bands
    'stop_loss_pct': 0.4, # Stop loss percentage from *entry* price (applied per order)
#    'price_jump_pct': 0.3,  # optional, uncomment to use for emergency close
    'use_longs': True,  # set to False if you want to use only shorts
    'use_shorts': True,  # set to False if you want to use only longs
    'stop_price_type': 'MP', # KuCoin stop price type: 'MP' (Mark), 'IP' (Index), 'TP' (Trade/Last)
}

# Construct the full symbol for KuCoin USDT Margined Futures
params['symbol'] = f"{params['base_symbol']}/USDT:USDT"

# --- FILE PATHS ---
# Assuming 'secret.json' is in the root 'LiveTradingBots' directory
project_root = os.path.join(os.path.dirname(__file__), '..', '..', '..')
key_path = os.path.join(project_root, 'secret.json')

# <<< --- SELECT KEY NAME BASED ON SANDBOX MODE --- >>>
# IMPORTANT: Make sure you have corresponding entries in your secret.json
# For example: 'kucoin_envelope' for live keys, 'kucoin_envelope_sandbox' for sandbox keys
key_name = 'kucoin_envelope_sandbox' if use_sandbox else 'kucoin_envelope' # Use a distinct key name for KuCoin in your secret.json

# Place tracker file within the specific strategy directory
strategy_dir = os.path.dirname(__file__)
# Optionally, use a different tracker file name for sandbox
tracker_suffix = "_sandbox" if use_sandbox else ""
tracker_file = os.path.join(strategy_dir, f"tracker_{params['symbol'].replace('/', '-').replace(':', '-')}.json")

# --- CONSTANTS ---
trigger_price_delta = 0.005  # % delta for trigger price relative to limit price for entry orders (1h)
# trigger_price_delta = 0.0015 # (15m)

# --- AUTHENTICATION ---
print(f"\n{datetime.now().strftime('%H:%M:%S')}: >>> Starting KuCoin execution for {params['symbol']}")
# <<< --- ADD INDICATION OF MODE --- >>>
print(f"*** MODE: {'SANDBOX' if use_sandbox else 'LIVE'} ***")
print(f"Using API key name: '{key_name}' from {key_path}")
print(f"Using tracker file: {tracker_file}")

try:
    with open(key_path, "r") as f:
        api_setup = json.load(f)[key_name]
    
    # <<< --- CONDITIONALLY ADD sandbox_mode FLAG --- >>>
    # The KucoinFutures class __init__ looks for this 'sandbox_mode' key
    if use_sandbox:
        api_setup['sandbox_mode'] = True

    # Add the required password for KuCoin Futures
    if 'password' not in api_setup:
         raise ValueError(f"KuCoin API setup in {key_path} under '{key_name}' must include 'password'")
    kucoin = KucoinFutures(api_setup)
    # Fetch contract size early for amount calculations
    contract_size = kucoin.markets[params['symbol']]['contractSize']
    print(f"{datetime.now().strftime('%H:%M:%S')}: KuCoin authenticated. Contract size for {params['symbol']}: {contract_size}")
except FileNotFoundError:
    print(f"ERROR: Key file not found at {key_path}")
    sys.exit(1)
except KeyError:
    print(f"ERROR: Key name '{key_name}' not found in {key_path}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: Failed to initialize KuCoin client: {e}")
    sys.exit(1)


# --- TRACKER FILE ---
if not os.path.exists(tracker_file):
    print(f"{datetime.now().strftime('%H:%M:%S')}: Tracker file not found, creating: {tracker_file}")
    with open(tracker_file, 'w') as file:
        json.dump({"status": "ok_to_trade", "last_side": None, "stop_loss_ids": []}, file, indent=4)

def read_tracker_file(file_path):
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except Exception as e:
        print(f"ERROR reading tracker file {file_path}: {e}")
        # Return a default state to prevent crashing, but log the error
        return {"status": "error_reading_tracker", "last_side": None, "stop_loss_ids": []}


def update_tracker_file(file_path, data):
    try:
        with open(file_path, 'w') as file:
            json.dump(data, file, indent=4)
    except Exception as e:
        print(f"ERROR writing tracker file {file_path}: {e}")

# --- CANCEL OPEN ORDERS ---
print(f"{datetime.now().strftime('%H:%M:%S')}: Cancelling existing orders for {params['symbol']}...")
try:
    # Cancel regular limit orders first (if any were manually placed or leftover)
    orders = kucoin.fetch_open_orders(params['symbol'])
    for order in orders:
        print(f"Cancelling regular order ID: {order['id']}")
        kucoin.cancel_order(order['id'], params['symbol'])
        time.sleep(0.2) # Small delay

    # Cancel trigger/stop orders
    trigger_orders = kucoin.fetch_open_trigger_orders(params['symbol'])
    long_orders_left = 0
    short_orders_left = 0
    cancelled_trigger_ids = set()
    for order in trigger_orders:
        order_id = order['id']
        if order_id in cancelled_trigger_ids:
            continue # Skip if already processed (safety check)

        # Check if it's an entry order (not reduceOnly)
        # Use .get() for safety in case fields are missing
        is_reduce_only = order.get('reduceOnly', order.get('info', {}).get('reduceOnly', False))

        if not is_reduce_only:
            if order['side'] == 'buy':
                long_orders_left += 1
            elif order['side'] == 'sell':
                short_orders_left += 1

        print(f"Cancelling trigger order ID: {order_id} (Side: {order['side']}, ReduceOnly: {is_reduce_only})")
        try:
            kucoin.cancel_trigger_order(order['id'], params['symbol'])
            cancelled_trigger_ids.add(order_id)
        except Exception as e:
            print(f"Warning: Failed to cancel trigger order {order_id}: {e}")
        time.sleep(0.2) # Small delay

    print(f"{datetime.now().strftime('%H:%M:%S')}: Orders cancelled. Remaining potential entry orders detected before cancel: {long_orders_left} longs, {short_orders_left} shorts")

except Exception as e:
    print(f"ERROR during order cancellation: {e}")
    # Decide if you want to exit or continue cautiously
    # sys.exit(1)


# --- FETCH OHLCV DATA, CALCULATE INDICATORS ---
try:
    print(f"{datetime.now().strftime('%H:%M:%S')}: Fetching OHLCV data...")
    # Fetch 100 periods + average_period for indicator calculation, then drop the last (incomplete) candle
    fetch_limit = 100 + params['average_period']
    data_raw = kucoin.fetch_recent_ohlcv(params['symbol'], params['timeframe'], limit=fetch_limit)

    if data_raw.empty or len(data_raw) < params['average_period']:
         raise ValueError(f"Insufficient OHLCV data fetched ({len(data_raw)} candles) for timeframe {params['timeframe']}")

    data = data_raw.iloc[:-1].copy() # Use .copy() to avoid SettingWithCopyWarning

    print(f"{datetime.now().strftime('%H:%M:%S')}: Calculating indicators ({params['average_type']} {params['average_period']})...")
    if 'DCM' == params['average_type']:
        # Ensure enough data for the window
        if len(data) < params['average_period']: raise ValueError("Not enough data for Donchian Channel")
        ta_obj = ta.volatility.DonchianChannel(data['high'], data['low'], data['close'], window=params['average_period'])
        data['average'] = ta_obj.donchian_channel_mband()
    elif 'SMA' == params['average_type']:
        data['average'] = ta.trend.sma_indicator(data['close'], window=params['average_period'])
    elif 'EMA' == params['average_type']:
        data['average'] = ta.trend.ema_indicator(data['close'], window=params['average_period'])
    elif 'WMA' == params['average_type']:
        data['average'] = ta.trend.wma_indicator(data['close'], window=params['average_period'])
    else:
        raise ValueError(f"The average type {params['average_type']} is not supported")

    # Drop rows with NaN in 'average' created by the indicator calculation
    data.dropna(subset=['average'], inplace=True)
    if data.empty:
        raise ValueError("No valid data left after calculating average and dropping NaNs.")

    for i, e in enumerate(params['envelopes']):
        data[f'band_high_{i + 1}'] = data['average'] * (1 + e) # Corrected formula for high band
        data[f'band_low_{i + 1}'] = data['average'] * (1 - e)

    print(f"{datetime.now().strftime('%H:%M:%S')}: OHLCV data processed. Last close: {data['close'].iloc[-1]}, Last avg: {data['average'].iloc[-1]}")

except Exception as e:
    print(f"ERROR fetching or processing OHLCV data: {e}")
    sys.exit(1)


# --- CHECKS IF STOP LOSS WAS TRIGGERED ---
tracker_info = read_tracker_file(tracker_file)
if tracker_info['status'] == "error_reading_tracker":
    print("ERROR: Cannot proceed due to tracker file read error.")
    sys.exit(1)

try:
    # Only check if we previously had stop loss orders tracked
    if tracker_info.get('stop_loss_ids'):
        print(f"{datetime.now().strftime('%H:%M:%S')}: Checking for triggered stop losses (tracked IDs: {tracker_info['stop_loss_ids']})...")
        # Fetch recent closed orders (limit might be needed for efficiency)
        closed_orders = kucoin.fetch_closed_trigger_orders(params['symbol']) # Might need since/limit params
        triggered_sl_found = False
        if closed_orders:
            # Check the most recent closed orders against our tracked IDs
            for order in reversed(closed_orders): # Check newest first
                 if order['id'] in tracker_info['stop_loss_ids']:
                    print(f"{datetime.now().strftime('%H:%M:%S')}: /!\\ Stop loss ID {order['id']} found in closed orders.")
                    # Infer position side from the side of the triggered SL order
                    last_position_side = 'long' if order['side'] == 'sell' else 'short'
                    update_tracker_file(tracker_file, {
                        "last_side": last_position_side,
                        "status": "stop_loss_triggered",
                        "stop_loss_ids": [], # Clear SL IDs
                    })
                    print(f"{datetime.now().strftime('%H:%M:%S')}: Status updated to stop_loss_triggered (inferred position: {last_position_side}).")
                    triggered_sl_found = True
                    break # Stop checking once found
        if not triggered_sl_found:
             print(f"{datetime.now().strftime('%H:%M:%S')}: No tracked stop loss IDs found among recent closed trigger orders.")

except Exception as e:
    print(f"Warning: Failed to check closed trigger orders: {e}")


# --- CHECK FOR MULTIPLE OPEN POSITIONS (SHOULDN'T HAPPEN WITH ISOLATED MARGIN NORMALLY) ---
# This logic might be less relevant for isolated margin if only one position per symbol is allowed,
# but kept as a safety check. KuCoin might allow long/short simultaneously in some modes.
try:
    print(f"{datetime.now().strftime('%H:%M:%S')}: Checking open positions...")
    positions = kucoin.fetch_open_positions(params['symbol'])
    if len(positions) > 1:
        print(f"Warning: Found {len(positions)} open positions for {params['symbol']}. Attempting to close older ones.")
        # Sort by entry timestamp if available, otherwise fallback might be needed
        try:
            # Use info['openTm'] or similar if unified timestamp is unreliable
            sorted_positions = sorted(positions, key=lambda p: p.get('timestamp', p.get('info', {}).get('openTm', 0)), reverse=True)
        except KeyError:
             print("Warning: Could not reliably sort positions by timestamp. Closing all but first fetched.")
             sorted_positions = positions # Keep original order as fallback

        latest_position = sorted_positions[0]
        print(f"Keeping latest position: Side {latest_position.get('side')}, Contracts {latest_position.get('contracts')}")
        for pos in sorted_positions[1:]:
            pos_side = pos.get('side')
            pos_contracts = pos.get('contracts')
            print(f"{datetime.now().strftime('%H:%M:%S')}: Double position case. Closing older position: Side {pos_side}, Contracts {pos_contracts}")
            try:
                # Use the close_position method
                kucoin.close_position(pos['symbol']) # Side might not be needed if it closes the whole symbol pos
                time.sleep(1) # Allow time for closure
            except Exception as e_close:
                print(f"ERROR closing older position (Side: {pos_side}): {e_close}")
        # Re-fetch positions after attempting closure
        positions = kucoin.fetch_open_positions(params['symbol'])

except Exception as e:
    print(f"ERROR checking or closing multiple positions: {e}")
    # Potentially exit if state is uncertain
    # sys.exit(1)


# --- CHECKS IF A POSITION IS OPEN ---
position = None # Initialize position to None
open_position = False
if positions:
     if len(positions) == 1:
        position = positions[0]
        open_position = True
        # Safely access position details using .get()
        pos_side = position.get('side', 'N/A')
        pos_contracts = position.get('contracts', 0) # Amount in contracts
        pos_entry_price = position.get('entryPrice', 0)
        pos_mark_price = position.get('markPrice', 0)
        # Calculate position value in USDT (Contracts * ContractValue * MarkPrice)
        # ContractValue is often 1 for USDT pairs, but use contract_size for accuracy
        position_value_usdt = abs(float(pos_contracts) * float(contract_size) * float(pos_mark_price))

        print(f"{datetime.now().strftime('%H:%M:%S')}: Position found: Side: {pos_side}, Contracts: {pos_contracts}, Entry: {pos_entry_price}, Mark: {pos_mark_price}, Value: ~{position_value_usdt:.2f} USDT")
     else:
         # This case should ideally be handled above, but log if still occurs
         print(f"Warning: {len(positions)} positions remain after cleanup attempt. Cannot proceed with single position logic.")
         # Decide how to handle this - maybe exit?
         sys.exit(1) # Exit if state is ambiguous
else:
     print(f"{datetime.now().strftime('%H:%M:%S')}: No open position found for {params['symbol']}.")


# --- CHECKS IF CLOSE ALL (PRICE JUMP) SHOULD TRIGGER ---
if 'price_jump_pct' in params and open_position and position:
    print(f"{datetime.now().strftime('%H:%M:%S')}: Checking for price jump closure...")
    last_close_price = data['close'].iloc[-1]
    entry_price = float(position.get('entryPrice', 0))
    pos_side = position.get('side')
    should_close = False

    if entry_price == 0:
        print("Warning: Cannot check price jump, entry price is zero.")
    elif pos_side == 'long':
        close_threshold = entry_price * (1 - params['price_jump_pct'])
        if last_close_price < close_threshold:
            print(f"{datetime.now().strftime('%H:%M:%S')}: /!\\ Price jump detected for LONG. Close: {last_close_price} < Threshold: {close_threshold}")
            should_close = True
    elif pos_side == 'short':
        close_threshold = entry_price * (1 + params['price_jump_pct'])
        if last_close_price > close_threshold:
            print(f"{datetime.now().strftime('%H:%M:%S')}: /!\\ Price jump detected for SHORT. Close: {last_close_price} > Threshold: {close_threshold}")
            should_close = True

    if should_close:
        print(f"{datetime.now().strftime('%H:%M:%S')}: Closing position due to price jump...")
        try:
            kucoin.close_position(params['symbol'])
            update_tracker_file(tracker_file, {
                "last_side": pos_side,
                "status": "close_all_triggered",
                "stop_loss_ids": [],
            })
            print(f"{datetime.now().strftime('%H:%M:%S')}: Position closed via price jump trigger. Exiting script run.")
            sys.exit(0) # Exit after closing
        except Exception as e:
            print(f"ERROR closing position after price jump detection: {e}")
            # Continue or exit depending on desired robustness
            sys.exit(1)


# --- OK TO TRADE CHECK ---
tracker_info = read_tracker_file(tracker_file) # Re-read in case it was updated by SL check
print(f"{datetime.now().strftime('%H:%M:%S')}: Okay to trade check, status was '{tracker_info.get('status', 'unknown')}'")
last_price = data['close'].iloc[-1]
resume_price = data['average'].iloc[-1] # Use the latest average price

if tracker_info.get('status') != "ok_to_trade":
    print(f"Current Status: {tracker_info.get('status')}. Last Side: {tracker_info.get('last_side')}. Last Price: {last_price}. Resume Price (Avg): {resume_price}")
    # Check conditions to resume trading
    if tracker_info.get('last_side') == 'long' and last_price >= resume_price:
        print(f"{datetime.now().strftime('%H:%M:%S')}: Price crossed above average after long SL/close. Resuming trading.")
        update_tracker_file(tracker_file, {"status": "ok_to_trade", "last_side": tracker_info.get('last_side'), "stop_loss_ids": []})
    elif tracker_info.get('last_side') == 'short' and last_price <= resume_price:
        print(f"{datetime.now().strftime('%H:%M:%S')}: Price crossed below average after short SL/close. Resuming trading.")
        update_tracker_file(tracker_file, {"status": "ok_to_trade", "last_side": tracker_info.get('last_side'), "stop_loss_ids": []})
    else:
        print(f"{datetime.now().strftime('%H:%M:%S')}: <<< Conditions not met to resume trading. Status remains '{tracker_info.get('status')}'. Exiting.")
        sys.exit(0)
else:
     print(f"{datetime.now().strftime('%H:%M:%S')}: Status is 'ok_to_trade'. Proceeding.")


# --- SET MARGIN MODE AND LEVERAGE (only if no position) ---
if not open_position:
    try:
        print(f"{datetime.now().strftime('%H:%M:%S')}: Setting margin mode to '{params['margin_mode']}' and leverage to {params['leverage']}x for {params['symbol']}...")
        # Set margin mode first (important for KuCoin)
        kucoin.set_margin_mode(params['symbol'], margin_mode=params['margin_mode'])
        time.sleep(0.5) # Allow time for mode change
        # Then set leverage
        kucoin.set_leverage(params['symbol'], leverage=params['leverage'])
        print(f"{datetime.now().strftime('%H:%M:%S')}: Margin mode and leverage set.")
    except Exception as e:
        print(f"Warning: Failed to set margin mode or leverage: {e}. Check KuCoin account state.")
        # Decide if this is critical - might be okay if already set correctly.


# --- MANAGE ORDERS FOR EXISTING POSITION (TP / SL) ---
current_stop_loss_ids = [] # Store IDs of SL orders placed in this run
if open_position and position:
    print(f"{datetime.now().strftime('%H:%M:%S')}: Managing Take Profit (TP) and Stop Loss (SL) for open {position.get('side')} position...")
    entry_price = float(position.get('entryPrice', 0))
    if entry_price == 0:
        print("ERROR: Cannot set TP/SL because entry price is zero. Exiting.")
        sys.exit(1)

    if position.get('side') == 'long':
        close_side = 'sell'
        # SL price based on entry price
        stop_loss_price = entry_price * (1 - params['stop_loss_pct'])
        # TP price is the current average
        take_profit_price = data['average'].iloc[-1]
    elif position.get('side') == 'short':
        close_side = 'buy'
        # SL price based on entry price
        stop_loss_price = entry_price * (1 + params['stop_loss_pct'])
        # TP price is the current average
        take_profit_price = data['average'].iloc[-1]
    else:
        print(f"ERROR: Unknown position side '{position.get('side')}'. Cannot set TP/SL.")
        sys.exit(1)

    # Amount is the current position size in contracts
    amount_contracts = abs(float(position.get('contracts', 0)))
    if amount_contracts == 0:
         print("Warning: Position size is zero, cannot place TP/SL.")
    else:
        print(f"Placing TP/SL for {amount_contracts} contracts. TP Trigger: {take_profit_price}, SL Trigger: {stop_loss_price}")
        # Place Take Profit (Exit at Average) - Trigger Market Order
        try:
            tp_order = kucoin.place_trigger_market_order(
                symbol=params['symbol'],
                side=close_side,
                amount=amount_contracts,
                trigger_price=take_profit_price,
                reduce=True,
                stop_price_type=params['stop_price_type'], # Use configured type
                print_error=True,
            )
            if tp_order:
                print(f"{datetime.now().strftime('%H:%M:%S')}: Placed TP Order ID: {tp_order.get('id')}")
            else:
                 print(f"Warning: Failed to place TP order.")
        except Exception as e:
            print(f"ERROR placing TP order: {e}")

        time.sleep(0.2) # Delay between orders

        # Place Stop Loss - Trigger Market Order
        try:
            sl_order = kucoin.place_trigger_market_order(
                symbol=params['symbol'],
                side=close_side,
                amount=amount_contracts,
                trigger_price=stop_loss_price,
                reduce=True,
                stop_price_type=params['stop_price_type'], # Use configured type
                print_error=True,
            )
            if sl_order and sl_order.get('id'):
                current_stop_loss_ids.append(sl_order['id'])
                print(f"{datetime.now().strftime('%H:%M:%S')}: Placed SL Order ID: {sl_order['id']}")
            else:
                 print(f"Warning: Failed to place SL order or get ID.")
        except Exception as e:
            print(f"ERROR placing SL order: {e}")

    # Update tracker info immediately after placing orders for the current position
    info = {
        "status": "ok_to_trade",
        "last_side": position.get('side'),
        "stop_loss_price": stop_loss_price, # Store calculated SL price for reference
        "stop_loss_ids": current_stop_loss_ids, # Track only the SL IDs placed *now*
    }
    update_tracker_file(tracker_file, info)

# --- PLACE NEW ENTRY ORDERS (IF NO POSITION) ---
elif not open_position: # Only place new entry orders if no position is open
    print(f"{datetime.now().strftime('%H:%M:%S')}: No open position. Placing new entry, TP, and SL orders...")
    try:
        # Fetch available balance (e.g., USDT)
        balance_data = kucoin.fetch_balance()
        available_balance = float(balance_data.get('USDT', {}).get('free', 0)) # Use free balance
        if available_balance <= 0:
             raise ValueError("Insufficient free USDT balance (0 or less).")

        # Calculate total USDT value to allocate based on fraction and leverage
        total_usdt_for_trades = available_balance * params['balance_fraction']
        # USDT value per envelope order
        usdt_per_order = total_usdt_for_trades / len(params['envelopes'])

        print(f"{datetime.now().strftime('%H:%M:%S')}: Available Balance: {available_balance:.2f} USDT. Total for strategy: {total_usdt_for_trades:.2f} USDT. USDT per envelope: {usdt_per_order:.2f}")

        min_amount_contracts = kucoin.fetch_min_amount_tradable(params['symbol'])
        print(f"Minimum order size: {min_amount_contracts} contracts.")

        # Determine which ranges to use based on orders cancelled earlier
        # If orders were cancelled, we assume those levels were hit and shouldn't be re-entered immediately
        # This logic might need refinement depending on desired re-entry behavior
        range_longs = range(long_orders_left, len(params['envelopes']))
        range_shorts = range(short_orders_left, len(params['envelopes']))

        long_ok = params['use_longs']
        short_ok = params['use_shorts']

        if long_ok:
            print(f"--- Placing LONG Orders (Envelopes {list(r+1 for r in range_longs)}) ---")
            for i in range_longs:
                band_key = f'band_low_{i + 1}'
                entry_limit_price = data[band_key].iloc[-1]
                # Trigger slightly above the limit price for buys
                entry_trigger_price = entry_limit_price * (1 + trigger_price_delta)

                # Calculate amount in contracts
                # Amount = (USDT Value / Entry Price) / Contract Size
                if entry_limit_price <= 0 or contract_size <= 0:
                     print(f"Warning: Invalid price ({entry_limit_price}) or contract size ({contract_size}) for long envelope {i+1}. Skipping.")
                     continue
                amount_contracts_float = usdt_per_order / (entry_limit_price * contract_size)
                amount_contracts = int(amount_contracts_float) # KuCoin requires integer contracts

                print(f"Long Env {i+1}: Limit: {entry_limit_price:.4f}, Trigger: {entry_trigger_price:.4f}, Calc Contracts: {amount_contracts_float:.4f} -> Int: {amount_contracts}")

                if amount_contracts >= min_amount_contracts:
                    # Place Entry Order (Trigger Limit)
                    try:
                        entry_order = kucoin.place_trigger_limit_order(
                            symbol=params['symbol'], side='buy', amount=amount_contracts,
                            trigger_price=entry_trigger_price, price=entry_limit_price,
                            stop_price_type=params['stop_price_type'], print_error=True,
                        )
                        if entry_order: print(f"  Placed Entry Order ID: {entry_order.get('id')}")
                        else: print("  Warning: Failed to place entry order.")
                    except Exception as e: print(f"  ERROR placing entry order: {e}")
                    time.sleep(0.2)

                    # Place Take Profit Order (Trigger Market at Average)
                    tp_price = data['average'].iloc[-1]
                    try:
                        tp_order = kucoin.place_trigger_market_order(
                            symbol=params['symbol'], side='sell', amount=amount_contracts,
                            trigger_price=tp_price, reduce=True,
                            stop_price_type=params['stop_price_type'], print_error=True,
                        )
                        if tp_order: print(f"  Placed TP Order (Trigger: {tp_price:.4f}) ID: {tp_order.get('id')}")
                        else: print("  Warning: Failed to place TP order.")
                    except Exception as e: print(f"  ERROR placing TP order: {e}")
                    time.sleep(0.2)

                    # Place Stop Loss Order (Trigger Market based on Entry)
                    sl_price = entry_limit_price * (1 - params['stop_loss_pct'])
                    try:
                        sl_order = kucoin.place_trigger_market_order(
                            symbol=params['symbol'], side='sell', amount=amount_contracts,
                            trigger_price=sl_price, reduce=True,
                            stop_price_type=params['stop_price_type'], print_error=True,
                        )
                        if sl_order and sl_order.get('id'):
                            current_stop_loss_ids.append(sl_order['id'])
                            print(f"  Placed SL Order (Trigger: {sl_price:.4f}) ID: {sl_order['id']}")
                        else: print("  Warning: Failed to place SL order or get ID.")
                    except Exception as e: print(f"  ERROR placing SL order: {e}")
                    time.sleep(0.2)
                else:
                    print(f"  Skipping Long Env {i+1}: Calculated amount {amount_contracts} < min {min_amount_contracts}")

        if short_ok:
            print(f"--- Placing SHORT Orders (Envelopes {list(r+1 for r in range_shorts)}) ---")
            for i in range_shorts:
                band_key = f'band_high_{i + 1}'
                entry_limit_price = data[band_key].iloc[-1]
                # Trigger slightly below the limit price for sells
                entry_trigger_price = entry_limit_price * (1 - trigger_price_delta)

                # Calculate amount in contracts
                if entry_limit_price <= 0 or contract_size <= 0:
                     print(f"Warning: Invalid price ({entry_limit_price}) or contract size ({contract_size}) for short envelope {i+1}. Skipping.")
                     continue
                amount_contracts_float = usdt_per_order / (entry_limit_price * contract_size)
                amount_contracts = int(amount_contracts_float)

                print(f"Short Env {i+1}: Limit: {entry_limit_price:.4f}, Trigger: {entry_trigger_price:.4f}, Calc Contracts: {amount_contracts_float:.4f} -> Int: {amount_contracts}")

                if amount_contracts >= min_amount_contracts:
                     # Place Entry Order (Trigger Limit)
                    try:
                        entry_order = kucoin.place_trigger_limit_order(
                            symbol=params['symbol'], side='sell', amount=amount_contracts,
                            trigger_price=entry_trigger_price, price=entry_limit_price,
                            stop_price_type=params['stop_price_type'], print_error=True,
                        )
                        if entry_order: print(f"  Placed Entry Order ID: {entry_order.get('id')}")
                        else: print("  Warning: Failed to place entry order.")
                    except Exception as e: print(f"  ERROR placing entry order: {e}")
                    time.sleep(0.2)

                    # Place Take Profit Order (Trigger Market at Average)
                    tp_price = data['average'].iloc[-1]
                    try:
                        tp_order = kucoin.place_trigger_market_order(
                            symbol=params['symbol'], side='buy', amount=amount_contracts,
                            trigger_price=tp_price, reduce=True,
                            stop_price_type=params['stop_price_type'], print_error=True,
                        )
                        if tp_order: print(f"  Placed TP Order (Trigger: {tp_price:.4f}) ID: {tp_order.get('id')}")
                        else: print("  Warning: Failed to place TP order.")
                    except Exception as e: print(f"  ERROR placing TP order: {e}")
                    time.sleep(0.2)

                    # Place Stop Loss Order (Trigger Market based on Entry)
                    sl_price = entry_limit_price * (1 + params['stop_loss_pct'])
                    try:
                        sl_order = kucoin.place_trigger_market_order(
                            symbol=params['symbol'], side='buy', amount=amount_contracts,
                            trigger_price=sl_price, reduce=True,
                            stop_price_type=params['stop_price_type'], print_error=True,
                        )
                        if sl_order and sl_order.get('id'):
                            current_stop_loss_ids.append(sl_order['id'])
                            print(f"  Placed SL Order (Trigger: {sl_price:.4f}) ID: {sl_order['id']}")
                        else: print("  Warning: Failed to place SL order or get ID.")
                    except Exception as e: print(f"  ERROR placing SL order: {e}")
                    time.sleep(0.2)
                else:
                    print(f"  Skipping Short Env {i+1}: Calculated amount {amount_contracts} < min {min_amount_contracts}")

        # Update tracker file with the SL IDs placed for the new potential entries
        info = {
            "status": "ok_to_trade",
            "last_side": tracker_info.get('last_side'), # Keep last side until a position is actually entered
            "stop_loss_ids": current_stop_loss_ids,
        }
        update_tracker_file(tracker_file, info)

    except Exception as e:
        print(f"ERROR during balance fetching or new order placement: {e}")
        # Update tracker to reflect potential partial state? Or just log?
        # For safety, maybe don't update tracker if orders failed significantly.
        # update_tracker_file(tracker_file, {"status": "error_placing_orders", "last_side": tracker_info.get('last_side'), "stop_loss_ids": []})


# --- FINAL ---
print(f"{datetime.now().strftime('%H:%M:%S')}: <<< KuCoin script run finished for {params['symbol']}")

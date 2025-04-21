import ccxt
import time
import pandas as pd
from typing import Any, Optional, Dict, List

class KucoinFutures():
    def __init__(self, api_setup: Optional[Dict[str, Any]] = None) -> None:
        """
        Initializes the KucoinFutures client.

        Args:
            api_setup (Optional[Dict[str, Any]]): Dictionary containing API key, secret,
                                                  and optional password for KuCoin Futures.
                                                  If None, initializes an unauthenticated client.
        """
        if api_setup is None:
            self.session = ccxt.kucoinfutures()
        else:
            # Ensure 'options' exists, set defaultType if not present
            api_setup.setdefault("options", {})
            api_setup["options"].setdefault("defaultType", "future")
            self.session = ccxt.kucoinfutures(api_setup)
            # Check if sandbox mode is requested (e.g., via a custom key in api_setup or implicitly)
            # Kucoin sandbox needs separate API keys usually. CCXT handles it via set_sandbox_mode
            if api_setup.get("sandbox_mode", False): # Assuming you add 'sandbox_mode': True to api_setup
                 self.session.set_sandbox_mode(True)

        try:
            self.markets = self.session.load_markets()
        except Exception as e:
            raise Exception(f"Failed to load KuCoin Futures markets: {e}")

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetches the ticker information for a specific symbol."""
        try:
            # KuCoin Futures symbols often end with 'M', e.g., 'BTC/USDT:USDT' -> 'BTCUSDTM'
            # CCXT usually handles the conversion, but be mindful of the exact symbol format required.
            return self.session.fetch_ticker(symbol)
        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to fetch ticker for {symbol}: {e}")

    def fetch_min_amount_tradable(self, symbol: str) -> float:
        """Fetches the minimum order amount (in base currency/contracts) for a symbol."""
        try:
            # KuCoin uses 'contracts' for amount limits in futures
            min_amount = self.markets[symbol]['limits']['amount']['min']
            if min_amount is None:
                 # Fallback or further investigation needed if 'min' is not directly available
                 print(f"Warning: Minimum amount not directly found for {symbol}. Check market data: {self.markets[symbol]['limits']}")
                 # Kucoin might express this in terms of contract size or lot size.
                 # For KuCoin futures, amount is usually in contracts (integer).
                 return 1.0 # Defaulting to 1 contract, adjust as needed based on KuCoin specifics
            return float(min_amount)
        except KeyError as e:
             raise Exception(f"KuCoin Futures: Could not find limit information '{e}' for {symbol} in markets.")
        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to fetch minimum amount tradable for {symbol}: {e}")

    def amount_to_precision(self, symbol: str, amount: float) -> str:
        """Formats the amount to the precision required by the exchange for the given symbol."""
        try:
            # For KuCoin futures, amount is typically an integer number of contracts.
            # Using amount_to_precision might work, but ensure it rounds correctly for integers.
            # return self.session.amount_to_precision(symbol, amount)
            # Safer approach for integer contracts:
            return str(int(amount))
        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to convert amount {amount} for {symbol} to precision: {e}")

    def price_to_precision(self, symbol: str, price: float) -> str:
        """Formats the price to the precision required by the exchange for the given symbol."""
        try:
            return self.session.price_to_precision(symbol, price)
        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to convert price {price} to precision for {symbol}: {e}")

    def fetch_balance(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fetches the account balance."""
        if params is None:
            # KuCoin Futures often requires specifying the currency (e.g., USDT)
            params = {'type': 'future', 'code': 'USDT'} # Adjust 'code' if using other margin currencies
        try:
            # Use fetch_balance with type='future'
            return self.session.fetch_balance(params=params)
        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to fetch balance: {e}")

    def fetch_order(self, id: str, symbol: str) -> Dict[str, Any]:
        """Fetches information about a specific order by its ID."""
        try:
            return self.session.fetch_order(id, symbol)
        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to fetch order {id} info for {symbol}: {e}")

    def fetch_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetches all open orders for a specific symbol."""
        try:
            return self.session.fetch_open_orders(symbol)
        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to fetch open orders for {symbol}: {e}")

    def fetch_open_trigger_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetches open stop/trigger orders for a symbol."""
        try:
            # CCXT standard is often params={'stop': True}, but verify KuCoin's implementation
            # KuCoin might list stop orders separately or require specific params.
            # This might fetch regular orders and then need filtering, or use a specific param.
            # Check ccxt documentation for kucoinfutures fetch_open_orders params.
            # Example using a potential KuCoin param (check if needed): params={'stopOrder': True}
            # Sticking to ccxt standard for now:
            return self.session.fetch_open_orders(symbol, params={'stop': True})
        except Exception as e:
            # If the above fails, you might need fetch_orders with status filtering or a private API call.
            raise Exception(f"KuCoin Futures: Failed to fetch open trigger orders for {symbol}: {e}. Check ccxt implementation details.")

    def fetch_closed_trigger_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetches closed stop/trigger orders for a symbol."""
        try:
            # Fetching closed *stop* orders via unified API can be tricky.
            # `fetch_closed_orders` might not support the 'stop' param directly for KuCoin.
            # You might need `fetch_orders` and filter by status and type, or use a private endpoint.
            # Sticking to ccxt standard attempt:
            return self.session.fetch_closed_orders(symbol, params={'stop': True})
        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to fetch closed trigger orders for {symbol}: {e}. This might require fetch_orders with filtering.")

    def cancel_order(self, id: str, symbol: str) -> Dict[str, Any]:
        """Cancels a regular open order."""
        try:
            return self.session.cancel_order(id, symbol)
        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to cancel the {symbol} order {id}: {e}")

    def cancel_trigger_order(self, id: str, symbol: str) -> Dict[str, Any]:
        """Cancels an open stop/trigger order."""
        try:
            # Similar to fetching, cancelling stop orders might need specific params.
            # CCXT standard is often params={'stop': True}.
            # KuCoin might require params={'orderType': 'stop'} or similar. Check ccxt docs.
            # Sticking to ccxt standard attempt:
            return self.session.cancel_order(id, symbol, params={'stop': True})
        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to cancel the {symbol} trigger order {id}: {e}. Check ccxt implementation details.")

    def fetch_open_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches open positions, optionally filtered by symbol."""
        try:
            # KuCoin fetch_positions might return positions for all symbols if symbol is None
            # or specific symbol if provided.
            # No extra params like productType/marginCoin usually needed for KuCoin via ccxt standard call.
            positions = self.session.fetch_positions(symbols=[symbol] if symbol else None)
            # Filter out positions with zero contracts/size
            # KuCoin uses 'contracts' or sometimes 'size' field in the position info
            real_positions = [
                p for p in positions if p.get('info') and float(p['info'].get('currentQty', 0)) != 0
            ]
            # Alternative check if 'contracts' field exists directly in the unified structure
            # real_positions = [p for p in positions if p.get('contracts') and float(p['contracts']) != 0]

            # If the above filtering doesn't work, inspect the raw `p['info']` structure from KuCoin
            # print("Raw position data sample:", positions[0]['info'] if positions else "No positions")

            return real_positions
        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to fetch open positions for {symbol if symbol else 'all symbols'}: {e}")

    def close_position(self, symbol: str, side: Optional[str] = None) -> Dict[str, Any]:
        """Closes an open position for the given symbol using ccxt's close_position."""
        try:
            # CCXT's close_position aims to place a market order to close the position.
            # The 'side' parameter might be ignored by some exchange implementations if they
            # automatically detect the side to close.
            return self.session.close_position(symbol, side=side)
        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to close position for {symbol}: {e}")

    def set_margin_mode(self, symbol: str, margin_mode: str = 'isolated') -> None:
        """Sets the margin mode (isolated or cross) for a symbol."""
        try:
            # Standard ccxt call. KuCoin requires 'isolated' or 'cross'.
            # Ensure no open positions or orders exist for the symbol before changing mode.
            # The `params` argument might be needed if ccxt unification isn't perfect,
            # e.g., params={'marginMode': margin_mode}, but try without first.
            self.session.set_margin_mode(margin_mode.lower(), symbol) # Use lowercase
            print(f"KuCoin Futures: Set margin mode to {margin_mode} for {symbol}")
        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to set margin mode for {symbol}: {e}. Ensure no open positions/orders.")

    def set_leverage(self, symbol: str, leverage: int, params: Optional[Dict[str, Any]] = None) -> None:
        """Sets the leverage for a symbol."""
        if params is None:
            params = {}
        try:
            # KuCoin's set_leverage is usually straightforward.
            # Margin mode should typically be set *before* setting leverage.
            # The unified method takes leverage, symbol, and optional params.
            self.session.set_leverage(leverage, symbol, params=params)
            print(f"KuCoin Futures: Set leverage to {leverage}x for {symbol}")
        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to set leverage for {symbol}: {e}")

    def fetch_recent_ohlcv(self, symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
        """
        Fetches recent OHLCV data, handling pagination if necessary.

        Args:
            symbol (str): The trading symbol (e.g., 'BTC/USDT:USDT').
            timeframe (str): The timeframe (e.g., '1m', '5m', '1h', '1d').
            limit (int): The total number of candles to fetch.

        Returns:
            pd.DataFrame: DataFrame with OHLCV data indexed by timestamp.
        """
        # KuCoin's fetch_ohlcv limit per request (check ccxt docs, often 1500)
        kucoin_fetch_limit = 1500
        timeframe_to_milliseconds = self.session.parse_timeframe(timeframe) * 1000

        all_ohlcv = []
        # Fetching backwards from the current time
        end_timestamp = self.session.milliseconds()
        since = end_timestamp - limit * timeframe_to_milliseconds

        while len(all_ohlcv) < limit:
            try:
                # Calculate how many more candles are needed, capped by KuCoin's limit
                fetch_num = min(limit - len(all_ohlcv), kucoin_fetch_limit)
                # Calculate the 'since' timestamp for this specific request
                current_since = end_timestamp - fetch_num * timeframe_to_milliseconds

                # Ensure we don't request data from before the overall target 'since'
                current_since = max(current_since, since)

                print(f"Fetching {fetch_num} candles for {symbol} since {pd.to_datetime(current_since, unit='ms')}...")

                fetched_data = self.session.fetch_ohlcv(
                    symbol,
                    timeframe,
                    since=current_since,
                    limit=fetch_num # Request the calculated number
                )

                if not fetched_data:
                    print("No more data returned, stopping fetch.")
                    break # Exit loop if no more data is available

                # Prepend fetched data to maintain chronological order
                all_ohlcv = fetched_data + all_ohlcv

                # Update the end_timestamp for the next iteration to the start of the fetched data
                end_timestamp = fetched_data[0][0] # Timestamp of the earliest candle fetched

                # Small delay to avoid rate limits
                time.sleep(self.session.rateLimit / 1000)

                # Break if we fetched data older than our overall target 'since'
                # (handles cases where exchange returns slightly more/less than requested)
                if fetched_data[0][0] < since:
                     break

            except ccxt.RateLimitExceeded as e:
                print(f"Rate limit exceeded, sleeping: {e}")
                time.sleep(5) # Wait longer if rate limited
            except Exception as e:
                raise Exception(f"KuCoin Futures: Failed to fetch OHLCV data chunk for {symbol} in timeframe {timeframe}: {e}")

        if not all_ohlcv:
             return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # Trim excess candles if we fetched more than requested due to chunking alignment
        all_ohlcv = all_ohlcv[-limit:]

        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True) # Ensure data is sorted chronologically

        return df


    def place_market_order(self, symbol: str, side: str, amount: float, reduce: bool = False) -> Dict[str, Any]:
        """Places a market order."""
        try:
            params = {
                'reduceOnly': reduce,
            }
            # Amount for KuCoin Futures is in contracts (integer)
            amount_str = self.amount_to_precision(symbol, amount)
            print(f"Placing KuCoin Market Order: {symbol}, {side}, Amount: {amount_str}, Reduce: {reduce}")
            return self.session.create_order(symbol, 'market', side, float(amount_str), params=params) # Use float for ccxt call

        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to place market order of {amount} contracts {symbol}: {e}")

    def place_limit_order(self, symbol: str, side: str, amount: float, price: float, reduce: bool = False) -> Dict[str, Any]:
        """Places a limit order."""
        try:
            params = {
                'reduceOnly': reduce,
            }
            amount_str = self.amount_to_precision(symbol, amount)
            price_str = self.price_to_precision(symbol, price)
            print(f"Placing KuCoin Limit Order: {symbol}, {side}, Amount: {amount_str}, Price: {price_str}, Reduce: {reduce}")
            return self.session.create_order(symbol, 'limit', side, float(amount_str), float(price_str), params=params) # Use float for ccxt call

        except Exception as e:
            raise Exception(f"KuCoin Futures: Failed to place limit order of {amount} contracts {symbol} at price {price}: {e}")

    def place_trigger_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        trigger_price: float,
        reduce: bool = False,
        stop_price_type: Optional[str] = None, # e.g., 'MP', 'IP', 'TP' - Mark, Index, Trade Price
        print_error: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Places a stop-market (trigger) order."""
        try:
            amount_str = self.amount_to_precision(symbol, amount)
            trigger_price_str = self.price_to_precision(symbol, trigger_price)
            params = {
                'reduceOnly': reduce,
                'stopPrice': float(trigger_price_str), # Use float for ccxt call
                # 'stop': 'loss', # or 'entry'. Might be needed depending on ccxt/KuCoin specifics
            }
            if stop_price_type:
                params['stopPriceType'] = stop_price_type # KuCoin specific param

            print(f"Placing KuCoin Trigger Market: {symbol}, {side}, Amount: {amount_str}, Trigger: {trigger_price_str}, Reduce: {reduce}, StopType: {stop_price_type}")
            # Use 'market' type with stopPrice param for stop-market
            return self.session.create_order(symbol, 'market', side, float(amount_str), params=params)
        except Exception as err:
            if print_error:
                print(f"KuCoin Futures Error placing trigger market order: {err}")
                return None
            else:
                raise err

    def place_trigger_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        trigger_price: float,
        price: float, # The limit price once triggered
        reduce: bool = False,
        stop_price_type: Optional[str] = None, # e.g., 'MP', 'IP', 'TP'
        print_error: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Places a stop-limit (trigger) order."""
        try:
            amount_str = self.amount_to_precision(symbol, amount)
            trigger_price_str = self.price_to_precision(symbol, trigger_price)
            price_str = self.price_to_precision(symbol, price)
            params = {
                'reduceOnly': reduce,
                'stopPrice': float(trigger_price_str), # Use float for ccxt call
                # 'stop': 'loss', # or 'entry'. Might be needed
            }
            if stop_price_type:
                params['stopPriceType'] = stop_price_type # KuCoin specific param

            print(f"Placing KuCoin Trigger Limit: {symbol}, {side}, Amount: {amount_str}, Trigger: {trigger_price_str}, LimitPrice: {price_str}, Reduce: {reduce}, StopType: {stop_price_type}")
            # Use 'limit' type with stopPrice param for stop-limit
            return self.session.create_order(symbol, 'limit', side, float(amount_str), float(price_str), params=params)
        except Exception as err:
            if print_error:
                print(f"KuCoin Futures Error placing trigger limit order: {err}")
                return None
            else:
                raise err

# Example Usage (replace with your actual keys and desired symbol)
# Ensure you have installed ccxt: pip install ccxt pandas

# For authenticated access (replace with your actual credentials)
# kucoin_api_setup = {
#     'apiKey': 'YOUR_KUCOIN_API_KEY',
#     'secret': 'YOUR_KUCOIN_SECRET',
#     'password': 'YOUR_KUCOIN_API_PASSWORD', # Password is required for KuCoin Futures API
#     # 'sandbox_mode': True # Uncomment for sandbox testing (requires separate sandbox keys)
# }
# kucoin = KucoinFutures(kucoin_api_setup)

# For unauthenticated access (limited functionality)
# kucoin = KucoinFutures()

# try:
#     # --- Examples ---
#     symbol = 'BTC/USDT:USDT' # Standard CCXT symbol format for USDT-margined BTC perpetual

#     # Fetch ticker
#     ticker = kucoin.fetch_ticker(symbol)
#     print(f"\nTicker for {symbol}:")
#     print(ticker)

#     # Fetch min amount
#     min_amount = kucoin.fetch_min_amount_tradable(symbol)
#     print(f"\nMin amount for {symbol}: {min_amount} contracts")

#     # Fetch balance (requires authentication)
#     # balance = kucoin.fetch_balance()
#     # print("\nBalance:")
#     # print(balance['USDT']) # Assuming USDT balance

#     # Fetch OHLCV
#     ohlcv = kucoin.fetch_recent_ohlcv(symbol, '1h', limit=5)
#     print(f"\nRecent 1h OHLCV for {symbol}:")
#     print(ohlcv)

#     # Fetch open positions (requires authentication)
#     # positions = kucoin.fetch_open_positions(symbol)
#     # print(f"\nOpen positions for {symbol}:")
#     # print(positions)

#     # --- Order Placement Examples (require authentication and careful testing!) ---
#     # print("\n--- Placing Test Orders (Ensure sufficient funds & use small amounts!) ---")
#     # current_price = float(ticker['last'])
#     # test_amount = min_amount # Use minimum amount for safety

#     # Market Buy
#     # market_buy_order = kucoin.place_market_order(symbol, 'buy', test_amount)
#     # print("\nMarket Buy Order Response:", market_buy_order)
#     # time.sleep(2) # Wait a bit

#     # Limit Sell (above current price)
#     # limit_sell_price = current_price * 1.01
#     # limit_sell_order = kucoin.place_limit_order(symbol, 'sell', test_amount, limit_sell_price, reduce=True) # Example reduceOnly
#     # print("\nLimit Sell Order Response:", limit_sell_order)
#     # time.sleep(2)

#     # Stop Market Sell (below current price - Stop Loss)
#     # stop_loss_price = current_price * 0.99
#     # stop_market_order = kucoin.place_trigger_market_order(symbol, 'sell', test_amount, stop_loss_price, reduce=True, stop_price_type='MP')
#     # print("\nStop Market Order Response:", stop_market_order)
#     # time.sleep(2)

#     # Stop Limit Buy (above current price - Stop Entry)
#     # stop_entry_trigger = current_price * 1.005
#     # stop_entry_limit = current_price * 1.006
#     # stop_limit_order = kucoin.place_trigger_limit_order(symbol, 'buy', test_amount, stop_entry_trigger, stop_entry_limit, stop_price_type='MP')
#     # print("\nStop Limit Order Response:", stop_limit_order)
#     # time.sleep(2)

#     # --- Cleanup Examples (Fetch and cancel open orders) ---
#     # open_orders = kucoin.fetch_open_orders(symbol)
#     # print(f"\nOpen orders for {symbol} before cancel:", open_orders)
#     # for order in open_orders:
#     #     print(f"Cancelling order {order['id']}...")
#     #     kucoin.cancel_order(order['id'], symbol)
#     #     time.sleep(1)

#     # open_trigger_orders = kucoin.fetch_open_trigger_orders(symbol)
#     # print(f"\nOpen trigger orders for {symbol} before cancel:", open_trigger_orders)
#     # for order in open_trigger_orders:
#     #      print(f"Cancelling trigger order {order['id']}...")
#     #      kucoin.cancel_trigger_order(order['id'], symbol) # Use the specific cancel method
#     #      time.sleep(1)


# except Exception as e:
#     print(f"\nAn error occurred: {e}")


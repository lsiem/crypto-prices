#!/Users/lasse/.crypto-tracker-env/bin/python3

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

import requests
import requests_cache
from tabulate import tabulate
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.progress import Progress

# Install cache with 5-minute expiry
requests_cache.install_cache(
    cache_name=os.path.expanduser('~/.crypto_price_cache'),
    backend='sqlite',
    expire_after=timedelta(minutes=5)
)

# Constants
# API endpoint for CoinGecko
API_URL = "https://api.coingecko.com/api/v3/coins/markets"
HISTORY_API_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
CACHE_FILE = os.path.expanduser("~/.crypto_prices_fallback.json")
HISTORY_CACHE_FILE = os.path.expanduser("~/.crypto_prices_history_fallback.json")
COINS = ["bitcoin", "ethereum", "binancecoin", "solana"]
COIN_SYMBOLS = {"bitcoin": "BTC", "ethereum": "ETH", "binancecoin": "BNB", "solana": "SOL"}
TIMEOUT = 3  # seconds
CURRENCY = "usd"
GRAPH_WIDTH = 20  # Width of price graph in characters
DAYS_HISTORY = 7  # Number of days of price history to fetch

def get_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Display cryptocurrency prices in the terminal")
    parser.add_argument("--quiet", "-q", action="store_true", help="Display minimal output")
    parser.add_argument("--verbose", "-v", action="store_true", help="Display verbose output with more details")
    parser.add_argument("--graph", "-g", action="store_true", help="Display price graphs")
    parser.add_argument("--no-graph", "-n", action="store_true", help="Hide price graphs")
    return parser.parse_args()

def format_price(value):
    """Format price with appropriate decimal places based on value."""
    if value is None:
        return "N/A"
    if value >= 1000:
        return f"${value:,.2f}"
    elif value >= 1:
        return f"${value:.2f}"
    else:
        return f"${value:.6f}"

def format_percent(value):
    """Format percentage change with color."""
    if value is None:
        return "N/A"
    
    if value > 0:
        return f"\033[32m+{value:.2f}%\033[0m"  # Green for positive
    elif value < 0:
        return f"\033[31m{value:.2f}%\033[0m"  # Red for negative
    else:
        return f"{value:.2f}%"

def save_fallback_data(data):
    """Save current data as fallback for future use."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'data': data
            }, f)
    except Exception:
        pass  # Silently fail if we can't write fallback file

def get_fallback_data():
    """Get fallback data if available."""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                cache_data = json.load(f)
                # Check if cache is less than 1 day old
                cache_time = datetime.fromisoformat(cache_data['timestamp'])
                if datetime.now() - cache_time < timedelta(days=1):
                    return cache_data['data']
    except Exception:
        pass
    return None

def save_history_fallback_data(data):
    """Save historical data as fallback for future use."""
    try:
        with open(HISTORY_CACHE_FILE, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'data': data
            }, f)
    except Exception:
        pass  # Silently fail if we can't write fallback file

def get_history_fallback_data():
    """Get historical fallback data if available."""
    try:
        if os.path.exists(HISTORY_CACHE_FILE):
            with open(HISTORY_CACHE_FILE, 'r') as f:
                cache_data = json.load(f)
                # Check if cache is less than 1 day old
                cache_time = datetime.fromisoformat(cache_data['timestamp'])
                if datetime.now() - cache_time < timedelta(days=1):
                    return cache_data['data']
    except Exception:
        pass
    return None

def fetch_price_history():
    """Fetch price history for each cryptocurrency."""
    history_data = {}
    
    with Progress() as progress:
        task = progress.add_task("[cyan]Fetching price history...", total=len(COINS))
        
        for coin in COINS:
            try:
                params = {
                    'vs_currency': CURRENCY,
                    'days': DAYS_HISTORY,
                    'interval': 'daily'
                }
                
                response = requests.get(
                    HISTORY_API_URL.format(coin_id=coin),
                    params=params,
                    timeout=TIMEOUT
                )
                response.raise_for_status()
                coin_data = response.json()
                history_data[coin] = coin_data['prices']
                progress.update(task, advance=1)
                
            except (requests.RequestException, json.JSONDecodeError):
                # Skip this coin on error
                progress.update(task, advance=1)
                continue
    
    # Save successful data fetch as fallback
    if history_data:
        save_history_fallback_data(history_data)
    
    # If we couldn't get any data, try fallback
    if not history_data:
        return get_history_fallback_data()
    
    return history_data

def create_sparkline(prices, width=GRAPH_WIDTH, height=1):
    """Create a simple ASCII sparkline from price data."""
    if not prices or len(prices) < 2:
        return "─" * width  # Return a flat line if no data
    
    # Extract just the price values (second element in each pair)
    values = [p[1] for p in prices]
    
    # Find min and max for scaling
    min_val = min(values)
    max_val = max(values)
    
    # If all values are the same, return a flat line
    if min_val == max_val:
        return "─" * width
    
    # Scale the values to fit our height
    range_val = max_val - min_val
    
    # Create sparkline characters based on price trend
    blocks = "▁▂▃▄▅▆▇█"
    
    # Sample the prices to fit our width
    step = max(1, len(values) // width)
    sampled_values = values[::step][:width]
    
    # Pad to desired width if needed
    sampled_values = sampled_values + [sampled_values[-1]] * (width - len(sampled_values))
    
    # Scale and convert to sparkline characters
    result = ""
    for val in sampled_values:
        if max_val == min_val:  # Avoid division by zero
            idx = 0
        else:
            # Scale to 0-7 (for 8 possible characters)
            idx = int(((val - min_val) / range_val) * 7)
        result += blocks[idx]
    
    # Determine color based on price trend
    if values[-1] > values[0]:
        return f"\033[32m{result}\033[0m"  # Green for upward trend
    elif values[-1] < values[0]:
        return f"\033[31m{result}\033[0m"  # Red for downward trend
    else:
        return result  # Default color for flat trend

def fetch_crypto_prices():
    """Fetch cryptocurrency prices from CoinGecko API."""
    params = {
        'vs_currency': CURRENCY,
        'ids': ','.join(COINS),
        'order': 'market_cap_desc',
        'per_page': 100,
        'page': 1,
        'sparkline': False,
        'price_change_percentage': '24h'
    }

    try:
        response = requests.get(API_URL, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        
        # Save successful data fetch as fallback
        save_fallback_data(data)
        
        return data, response.from_cache
    except (requests.RequestException, json.JSONDecodeError) as e:
        # Try to use fallback data
        fallback_data = get_fallback_data()
        if fallback_data:
            return fallback_data, False
        
        print(f"Error fetching cryptocurrency data: {e}", file=sys.stderr)
        sys.exit(1)

def display_crypto_prices(prices_data, from_cache, args):
    """Display cryptocurrency prices in a nice table."""
    if from_cache:
        cache_status = " (cached)"
    else:
        cache_status = ""
        
    if args.quiet:
        # Quieter output, just BTC price
        for coin in prices_data:
            if coin['id'] == 'bitcoin':
                btc_price = format_price(coin['current_price'])
                btc_change = format_percent(coin['price_change_percentage_24h'])
                print(f"BTC: {btc_price} ({btc_change}){cache_status}")
                break
        return

    # Prepare data for table
    table_data = []
    for coin in prices_data:
        symbol = COIN_SYMBOLS.get(coin['id'], coin['symbol'].upper())
        price = format_price(coin['current_price'])
        change_24h = format_percent(coin['price_change_percentage_24h'])
        
        # Add extra info for verbose mode
        if args.verbose:
            market_cap = f"${coin['market_cap'] / 1_000_000_000:.2f}B"
            volume = f"${coin['total_volume'] / 1_000_000:.2f}M"
            table_data.append([symbol, price, change_24h, market_cap, volume])
        else:
            table_data.append([symbol, price, change_24h])
    
    # Create table headers
    if args.verbose:
        headers = ["Coin", "Price", "24h Change", "Market Cap", "24h Volume"]
    else:
        headers = ["Coin", "Price", "24h Change"]
    
    # Get current time for the timestamp
    current_time = datetime.now().strftime("%H:%M:%S")
    
    print(f"\n💰 Crypto Prices{cache_status} @ {current_time}")
    print(tabulate(table_data, headers=headers, tablefmt="simple"))

def display_price_graphs(prices_data, history_data, args):
    """Display price graphs for each cryptocurrency."""
    if not history_data:
        print("No historical data available for graphs")
        return
    
    console = Console()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Coin")
    table.add_column("7-Day Price Trend")
    table.add_column("Current Price")
    table.add_column("24h Change")
    
    for coin_data in prices_data:
        coin_id = coin_data['id']
        if coin_id in history_data:
            symbol = COIN_SYMBOLS.get(coin_id, coin_data['symbol'].upper())
            price = format_price(coin_data['current_price'])
            change_24h = coin_data['price_change_percentage_24h']
            
            # Format the percentage with color but without ANSI codes for rich
            if change_24h > 0:
                change_text = Text(f"+{change_24h:.2f}%", style="green")
            elif change_24h < 0:
                change_text = Text(f"{change_24h:.2f}%", style="red")
            else:
                change_text = Text(f"{change_24h:.2f}%")
            
            # Create the sparkline from historical data
            sparkline = create_sparkline(history_data[coin_id])
            
            table.add_row(symbol, sparkline, price, change_text)
    
    console.print("\n📈 7-Day Price History")
    console.print(table)

def main():
    args = get_args()
    prices_data, from_cache = fetch_crypto_prices()
    
    # Determine if we should show graphs
    show_graphs = not args.quiet and not args.no_graph
    if args.graph:
        show_graphs = True
    
    # Display regular price table
    display_crypto_prices(prices_data, from_cache, args)
    
    # Display graphs if requested
    if show_graphs:
        history_data = fetch_price_history()
        if history_data:
            display_price_graphs(prices_data, history_data, args)

if __name__ == "__main__":
    main()


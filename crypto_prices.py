#!/usr/bin/env python3

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
import requests_cache
from tabulate import tabulate
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.progress import Progress

# Import configuration manager
from config_manager import ConfigManager, load_config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.expanduser('~/.crypto_prices.log'))
    ]
)
logger = logging.getLogger('crypto_prices')

# Global configuration
config = None

# Coin symbols mapping (will be updated from config)
COIN_SYMBOLS = {
    "bitcoin": "BTC", 
    "ethereum": "ETH", 
    "binancecoin": "BNB", 
    "solana": "SOL",
    "monero": "XMR"
}

def initialize_config():
    """Initialize configuration from files or defaults."""
    global config
    config = load_config()
    
    # Setup cache based on config
    cache_filename = os.path.expanduser(f"~/{config['cache']['filename']}")
    requests_cache.install_cache(
        cache_name=cache_filename,
        backend=config['cache']['backend'],
        expire_after=timedelta(seconds=config['cache']['expiration'])
    )
    
    # Update constants based on config
    update_constants_from_config()
    
    return config

def update_constants_from_config():
    """Update global constants based on configuration."""
    global COIN_SYMBOLS
    
    # Update coin symbols dictionary with any additional coins
    # This ensures we have a symbol for each coin in the config
    for coin in config['cryptocurrencies']:
        if coin not in COIN_SYMBOLS:
            # Default to uppercase if not in our predefined mapping
            COIN_SYMBOLS[coin] = coin.upper()[:3]

def get_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Display cryptocurrency prices in the terminal")
    parser.add_argument("--quiet", "-q", action="store_true", help="Display minimal output")
    parser.add_argument("--verbose", "-v", action="store_true", help="Display verbose output with more details")
    parser.add_argument("--graph", "-g", action="store_true", help="Display price graphs")
    parser.add_argument("--no-graph", "-n", action="store_true", help="Hide price graphs")
    parser.add_argument("--config", "-c", help="Path to custom config file")
    parser.add_argument("--refresh", "-r", type=int, help="Refresh rate in seconds (0 to disable)")
    parser.add_argument("--coins", help="Comma-separated list of coins to display")
    parser.add_argument("--days", "-d", type=int, help="Number of days of price history to fetch")
    parser.add_argument("--save-config", "-s", action="store_true", help="Save current settings to config file")
    return parser.parse_args()

def format_price(value):
    """Format price with appropriate decimal places based on value."""
    if value is None:
        return "N/A"
    
    # Get currency symbol and position from config
    symbol = config['currency']['symbol']
    position = config['currency']['symbol_position']
    decimals = config['display']['price_decimals']
    
    # Format the value based on its size
    if value >= 1000:
        formatted = f"{value:,.{decimals}f}"
    elif value >= 1:
        formatted = f"{value:.{decimals}f}"
    else:
        # For very small values, use more decimal places
        formatted = f"{value:.6f}"
    
    # Add the currency symbol in the right position
    if position == 'prefix':
        return f"{symbol}{formatted}"
    else:
        return f"{formatted}{symbol}"

def format_percent(value):
    """Format percentage change with color."""
    if value is None:
        return "N/A"
    
    decimals = config['display']['percent_decimals']
    
    if value > 0:
        return f"\033[32m+{value:.{decimals}f}%\033[0m"  # Green for positive
    elif value < 0:
        return f"\033[31m{value:.{decimals}f}%\033[0m"  # Red for negative
    else:
        return f"{value:.{decimals}f}%"

def save_fallback_data(data):
    """Save current data as fallback for future use."""
    fallback_file = os.path.expanduser("~/.crypto_prices_fallback.json")
    try:
        with open(fallback_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'data': data
            }, f)
        logger.debug(f"Saved fallback data to {fallback_file}")
    except Exception as e:
        logger.warning(f"Failed to save fallback data: {e}")

def get_fallback_data():
    """Get fallback data if available."""
    fallback_file = os.path.expanduser("~/.crypto_prices_fallback.json")
    try:
        if os.path.exists(fallback_file):
            with open(fallback_file, 'r') as f:
                cache_data = json.load(f)
                # Check if cache is less than 1 day old
                cache_time = datetime.fromisoformat(cache_data['timestamp'])
                if datetime.now() - cache_time < timedelta(days=1):
                    logger.info("Using fallback data (API unavailable)")
                    return cache_data['data']
                else:
                    logger.debug("Fallback data is too old")
    except Exception as e:
        logger.warning(f"Failed to read fallback data: {e}")
    return None

def save_history_fallback_data(data):
    """Save historical data as fallback for future use."""
    history_fallback_file = os.path.expanduser("~/.crypto_prices_history_fallback.json")
    try:
        with open(history_fallback_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'data': data
            }, f)
        logger.debug(f"Saved history fallback data to {history_fallback_file}")
    except Exception as e:
        logger.warning(f"Failed to save history fallback data: {e}")

def get_history_fallback_data():
    """Get historical fallback data if available."""
    history_fallback_file = os.path.expanduser("~/.crypto_prices_history_fallback.json")
    try:
        if os.path.exists(history_fallback_file):
            with open(history_fallback_file, 'r') as f:
                cache_data = json.load(f)
                # Check if cache is less than 1 day old
                cache_time = datetime.fromisoformat(cache_data['timestamp'])
                if datetime.now() - cache_time < timedelta(days=1):
                    logger.info("Using historical fallback data (API unavailable)")
                    return cache_data['data']
                else:
                    logger.debug("Historical fallback data is too old")
    except Exception as e:
        logger.warning(f"Failed to read history fallback data: {e}")
    return None

def fetch_crypto_prices():
    """Fetch cryptocurrency prices from CoinGecko API."""
    # Get values from config
    coins = config['cryptocurrencies']
    currency = config['currency']['base']
    timeout = config['api']['timeout']
    api_endpoint = config['api']['endpoint']
    markets_endpoint = f"{api_endpoint}/coins/markets"
    
    params = {
        'vs_currency': currency,
        'ids': ','.join(coins),
        'order': 'market_cap_desc',
        'per_page': 100,
        'page': 1,
        'sparkline': False,
        'price_change_percentage': '24h'
    }
    
    # Add API key if configured
    if config['api']['api_key']:
        params['x_cg_pro_api_key'] = config['api']['api_key']

    try:
        logger.debug(f"Fetching crypto prices for {len(coins)} coins")
        response = requests.get(markets_endpoint, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        
        # Save successful data fetch as fallback
        save_fallback_data(data)
        
        # Check if response is from cache
        from_cache = hasattr(response, 'from_cache') and response.from_cache
        
        return data, from_cache
    except (requests.RequestException, json.JSONDecodeError) as e:
        logger.error(f"Error fetching cryptocurrency data: {e}")
        
        # Try to use fallback data if enabled
        if config['api']['use_fallback']:
            fallback_data = get_fallback_data()
            if fallback_data:
                return fallback_data, False
        
        # If no fallback or fallback disabled, exit with error
        logger.critical("No data available and no fallback. Exiting.")
        sys.exit(1)


def fetch_price_history():
    """Fetch price history for each cryptocurrency."""
    history_data = {}
    coins = config['cryptocurrencies']
    days = config['graph']['days']
    timeout = config['api']['timeout']
    currency = config['currency']['base']
    api_endpoint = config['api']['endpoint']
    history_endpoint = f"{api_endpoint}/coins/{{coin_id}}/market_chart"
    
    with Progress() as progress:
        task = progress.add_task("[cyan]Fetching price history...", total=len(coins))
        
        for coin in coins:
            try:
                params = {
                    'vs_currency': currency,
                    'days': days,
                    'interval': 'daily'
                }
                
                # Add API key if configured
                if config['api']['api_key']:
                    params['x_cg_pro_api_key'] = config['api']['api_key']
                
                logger.debug(f"Fetching price history for {coin}")
                response = requests.get(
                    history_endpoint.format(coin_id=coin),
                    params=params,
                    timeout=timeout
                )
                response.raise_for_status()
                coin_data = response.json()
                history_data[coin] = coin_data['prices']
                progress.update(task, advance=1)
                
            except (requests.RequestException, json.JSONDecodeError) as e:
                logger.warning(f"Failed to fetch history for {coin}: {e}")
                # Skip this coin on error
                progress.update(task, advance=1)
                continue
    
    # Save successful data fetch as fallback
    if history_data:
        save_history_fallback_data(history_data)
    
    # If we couldn't get any data, try fallback
    if not history_data and config['api']['use_fallback']:
        return get_history_fallback_data()
    
    return history_data

def create_sparkline(prices, width=None, height=None):
    """Create a simple ASCII sparkline from price data."""
    # Use config values if not explicitly provided
    if width is None:
        width = config['graph']['width']
    if height is None:
        height = config['graph']['height']
        
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


def display_crypto_prices(prices_data, from_cache, args):
    """Display cryptocurrency prices in a nice table."""
    if from_cache:
        cache_status = " (cached)"
    else:
        cache_status = ""
        
    # Determine display mode from config and args
    display_mode = config['display']['default_mode']
    
    # Command line args override config
    if args.quiet:
        display_mode = 'quiet'
    elif args.verbose:
        display_mode = 'verbose'
    
    if display_mode == 'quiet':
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
        if display_mode == 'verbose' or args.verbose:
            market_cap = f"${coin['market_cap'] / 1_000_000_000:.2f}B"
            volume = f"${coin['total_volume'] / 1_000_000:.2f}M"
            table_data.append([symbol, price, change_24h, market_cap, volume])
        else:
            table_data.append([symbol, price, change_24h])
    
    # Create table headers
    if display_mode == 'verbose' or args.verbose:
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
    
    # Get graph days from config
    days = config['graph']['days']
    
    # Initialize Rich components
    console = Console()
    table = Table(show_header=True, header_style="bold")
    
    # Add columns
    table.add_column("Coin")
    table.add_column(f"{days}-Day Price Trend")
    table.add_column("Current Price")
    table.add_column("24h Change")
    
    # Add rows for each cryptocurrency
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
            
            # Strip ANSI color codes for Rich
            import re
            ansi_escape = re.compile(r'\033\[(?:\d+(?:;\d+)*)?[m|K]')
            clean_sparkline = ansi_escape.sub('', sparkline)
            
            # Apply Rich style based on trend
            if "▁▂▃▄▅▆▇█" in clean_sparkline:
                trend = history_data[coin_id][-1][1] - history_data[coin_id][0][1]
                if trend > 0:
                    sparkline_text = Text(clean_sparkline, style="green")
                elif trend < 0:
                    sparkline_text = Text(clean_sparkline, style="red")
                else:
                    sparkline_text = Text(clean_sparkline)
            else:
                sparkline_text = Text(clean_sparkline)
            
            table.add_row(symbol, sparkline_text, price, change_text)
    
    # Print the table
    console.print(f"\n📈 {days}-Day Price History")
    console.print(table)

def main():
    # Parse command-line arguments first
    args = get_args()
    
    # Initialize configuration, potentially using custom config path
    global config
    if args.config:
        config = load_config(args.config)
    else:
        config = initialize_config()
    
    # Override config with command-line arguments if provided
    if args.refresh is not None:
        config['display']['refresh_rate'] = args.refresh
    
    if args.coins:
        config['cryptocurrencies'] = args.coins.split(',')
    
    if args.days:
        config['graph']['days'] = args.days
    
    # Save updated config if requested
    if args.save_config:
        config_manager = ConfigManager()
        config_manager.config = config
        config_manager.save()
        print(f"Configuration saved.")
    
    # Fetch price data
    prices_data, from_cache = fetch_crypto_prices()
    
    # Determine if we should show graphs based on config and args
    show_graphs = config['display']['show_graphs']
    
    # Command-line args override config
    if args.no_graph:
        show_graphs = False
    elif args.graph:
        show_graphs = True
    
    # Quiet mode disables graphs
    if args.quiet:
        show_graphs = False
    
    # Display regular price table
    display_crypto_prices(prices_data, from_cache, args)
    
    # Display graphs if requested
    if show_graphs:
        history_data = fetch_price_history()
        if history_data:
            display_price_graphs(prices_data, history_data, args)
    
    # If refresh is enabled, loop with delay
    refresh_rate = config['display']['refresh_rate']
    if refresh_rate > 0 and not args.quiet:
        try:
            while True:
                time.sleep(refresh_rate)
                print("\033c", end="")  # Clear screen
                prices_data, from_cache = fetch_crypto_prices()
                display_crypto_prices(prices_data, from_cache, args)
                if show_graphs:
                    history_data = fetch_price_history()
                    if history_data:
                        display_price_graphs(prices_data, history_data, args)
        except KeyboardInterrupt:
            print("\nExiting...")
            sys.exit(0)

if __name__ == "__main__":
    main()


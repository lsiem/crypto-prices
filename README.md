# Crypto Prices Terminal Tracker

A lightweight command-line utility for tracking cryptocurrency prices in real-time, with beautiful terminal visualization including price graphs and color-coded trends.

## Features

- **Multi-coin Support**: Track Bitcoin (BTC), Ethereum (ETH), Binance Coin (BNB), Solana (SOL) and more
- **Real-time Data**: Fetches current prices from CoinGecko API
- **Smart Caching**: Uses a 5-minute cache to reduce API calls and improve performance
- **Fallback Mechanism**: Continues to display data even when API is unavailable
- **Beautiful Visualizations**: 
  - Color-coded price changes (green for positive, red for negative)
  - ASCII/Unicode price history graphs for the last 7 days
  - Tabular display with clean formatting
- **Multiple Display Modes**:
  - Quiet mode (`-q`) for minimal output
  - Verbose mode (`-v`) with additional market data
  - Graph mode (`-g`) specifically for trend visualization
- **Terminal Integration**: Can be configured to run at terminal startup

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/YOUR_USERNAME/crypto-prices.git
   cd crypto-prices
   ```

2. Create a virtual environment (optional but recommended):
   ```
   python -m venv .crypto-tracker-env
   source .crypto-tracker-env/bin/activate
   ```

3. Install dependencies:
   ```
   pip install requests requests-cache tabulate rich
   ```

4. Make the script executable:
   ```
   chmod +x crypto_prices.py
   ```

5. Optional: Create a symlink to make it available system-wide:
   ```
   ln -s $(pwd)/crypto_prices.py ~/.local/bin/crypto-prices
   ```

## Usage

Basic usage:
```
./crypto_prices.py
```

Display options:
```
./crypto_prices.py -q        # Quiet mode (BTC only)
./crypto_prices.py -v        # Verbose mode with market cap and volume
./crypto_prices.py -g        # Force graph display
./crypto_prices.py --no-graph # Hide graphs
```

Run at terminal startup by adding to your `.zshrc` or `.bashrc`:
```
(crypto-prices &) 2>/dev/null
```

## Dependencies

- Python 3.6+
- requests
- requests-cache
- tabulate
- rich

## License

MIT

## Data Source

Price data provided by [CoinGecko API](https://www.coingecko.com/en/api)


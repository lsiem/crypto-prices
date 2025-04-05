"""Configuration management for the crypto price tracker application."""

import logging
import os
import sys
from copy import deepcopy
from typing import Any, Dict, List, Optional, Union

import yaml

# Setup logging
logger = logging.getLogger(__name__)

# Define paths for configuration
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yaml')
USER_CONFIG_PATH = os.path.expanduser('~/.config/crypto-prices/config.yaml')

# Default configuration values
DEFAULT_CONFIG = {
    'cryptocurrencies': [
        'bitcoin',     # BTC
        'ethereum',    # ETH
        'binancecoin', # BNB
        'monero',      # XMR
        'solana'       # SOL
    ],
    'display': {
        'default_mode': 'normal',
        'show_graphs': True,
        'refresh_rate': 300,  # 5 minutes
        'price_decimals': 2,
        'percent_decimals': 2
    },
    'cache': {
        'enabled': True,
        'expiration': 300,  # 5 minutes
        'backend': 'sqlite',
        'filename': '.crypto_cache'
    },
    'graph': {
        'days': 7,
        'width': 40,
        'height': 10,
        'style': 'unicode',  # or 'ascii'
        'color_scheme': 'default'  # or 'monochrome', 'rainbow'
    },
    'currency': {
        'base': 'usd',
        'symbol': '$',
        'symbol_position': 'prefix'  # or 'suffix'
    },
    'api': {
        'endpoint': 'https://api.coingecko.com/api/v3',
        'api_key': '',  # for API Pro users
        'timeout': 10,
        'use_fallback': True
    }
}

# Configuration validation schemas with allowed values
VALIDATION_SCHEMA = {
    'display': {
        'default_mode': ['normal', 'quiet', 'verbose', 'graph'],
        'show_graphs': [True, False],
    },
    'cache': {
        'enabled': [True, False],
        'backend': ['sqlite', 'memory'],
    },
    'graph': {
        'style': ['unicode', 'ascii'],
        'color_scheme': ['default', 'monochrome', 'rainbow'],
    },
    'currency': {
        'symbol_position': ['prefix', 'suffix'],
    },
}


class ConfigManager:
    """Manages configuration loading, validation, and access for the application."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the configuration manager.
        
        Args:
            config_path: Optional path to a configuration file. If not provided,
                         the default paths will be checked.
        """
        self.config_path = config_path
        self.config = deepcopy(DEFAULT_CONFIG)
        self.loaded = False

    def load(self) -> Dict[str, Any]:
        """Load configuration from file.
        
        Returns:
            Dict containing the merged configuration.
        """
        # Try to load configuration from file
        loaded_config = None
        
        # If a specific path was provided, try that first
        if self.config_path and os.path.exists(self.config_path):
            loaded_config = self._load_from_file(self.config_path)
        
        # If no specific path or it failed, try the user config
        if not loaded_config and os.path.exists(USER_CONFIG_PATH):
            loaded_config = self._load_from_file(USER_CONFIG_PATH)
        
        # If user config doesn't exist, try the default config
        if not loaded_config and os.path.exists(DEFAULT_CONFIG_PATH):
            loaded_config = self._load_from_file(DEFAULT_CONFIG_PATH)
        
        # If we loaded something, merge it with defaults and validate
        if loaded_config:
            self._merge_config(loaded_config)
        
        # Mark as loaded
        self.loaded = True
        
        # Validate the final config
        self._validate_config()
        
        return self.config

    def _load_from_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Load configuration from a YAML file.
        
        Args:
            file_path: Path to the configuration file.
            
        Returns:
            Loaded configuration dict or None if loading failed.
        """
        try:
            with open(file_path, 'r') as f:
                config = yaml.safe_load(f)
                logger.info(f"Loaded configuration from {file_path}")
                return config
        except (yaml.YAMLError, OSError) as e:
            logger.warning(f"Failed to load configuration from {file_path}: {e}")
            return None

    def _merge_config(self, loaded_config: Dict[str, Any]) -> None:
        """Merge loaded configuration with defaults.
        
        Args:
            loaded_config: The configuration loaded from file.
        """
        # Merge top-level sections
        for section, values in loaded_config.items():
            if section in self.config:
                if isinstance(values, dict) and isinstance(self.config[section], dict):
                    # For dict sections, update the defaults with loaded values
                    self.config[section].update(values)
                else:
                    # For simple values or lists, replace the defaults
                    self.config[section] = values
            else:
                # Add new sections
                self.config[section] = values

    def _validate_config(self) -> None:
        """Validate and normalize configuration values."""
        # Validate and correct display settings
        for section, validations in VALIDATION_SCHEMA.items():
            if section in self.config:
                for option, valid_values in validations.items():
                    if option in self.config[section]:
                        value = self.config[section][option]
                        if value not in valid_values:
                            # Reset to default if current value is invalid
                            logger.warning(
                                f"Invalid value '{value}' for '{section}.{option}'. "
                                f"Must be one of {valid_values}. Using default: "
                                f"'{DEFAULT_CONFIG[section][option]}'."
                            )
                            self.config[section][option] = DEFAULT_CONFIG[section][option]
        
        # Ensure numeric values are within reasonable ranges
        self._validate_numeric_range('display.refresh_rate', 0, 3600)  # 0 to 1 hour
        self._validate_numeric_range('display.price_decimals', 0, 10)
        self._validate_numeric_range('display.percent_decimals', 0, 10)
        self._validate_numeric_range('cache.expiration', 30, 86400)  # 30 sec to 1 day
        self._validate_numeric_range('graph.days', 1, 365)  # 1 day to 1 year
        self._validate_numeric_range('graph.width', 10, 200)
        self._validate_numeric_range('graph.height', 1, 50)
        self._validate_numeric_range('api.timeout', 1, 60)  # 1 to 60 seconds
        
        # Validate cryptocurrency list
        if not self.config['cryptocurrencies'] or not isinstance(self.config['cryptocurrencies'], list):
            logger.warning("Invalid or empty cryptocurrencies list. Using defaults.")
            self.config['cryptocurrencies'] = DEFAULT_CONFIG['cryptocurrencies']

    def _validate_numeric_range(self, path: str, min_val: float, max_val: float) -> None:
        """Validate that a numeric config value is within a specified range.
        
        Args:
            path: Dot-separated path to the config value (e.g., 'display.refresh_rate')
            min_val: Minimum allowed value
            max_val: Maximum allowed value
        """
        # Split the path into section and option
        parts = path.split('.')
        if len(parts) != 2:
            return
        
        section, option = parts
        
        # Check if the section and option exist
        if section in self.config and option in self.config[section]:
            value = self.config[section][option]
            
            # Validate that it's a number and in range
            try:
                value = float(value)
                if value < min_val or value > max_val:
                    logger.warning(
                        f"Value {value} for '{path}' is out of range [{min_val}, {max_val}]. "
                        f"Using default: {DEFAULT_CONFIG[section][option]}"
                    )
                    self.config[section][option] = DEFAULT_CONFIG[section][option]
            except (ValueError, TypeError):
                logger.warning(
                    f"Invalid numeric value '{value}' for '{path}'. "
                    f"Using default: {DEFAULT_CONFIG[section][option]}"
                )
                self.config[section][option] = DEFAULT_CONFIG[section][option]

    def get(self, path: Optional[str] = None, default: Any = None) -> Any:
        """Get a configuration value by path.
        
        Args:
            path: Dot-separated path to the config value (e.g., 'display.refresh_rate')
            default: Default value to return if path is not found
            
        Returns:
            The configuration value at the specified path, or the default
        """
        # Load configuration if not already loaded
        if not self.loaded:
            self.load()
            
        # Return the entire config if no path is specified
        if not path:
            return self.config
            
        # Split the path and navigate the config
        parts = path.split('.')
        result = self.config
        
        for part in parts:
            if isinstance(result, dict) and part in result:
                result = result[part]
            else:
                return default
                
        return result

    def set(self, path: str, value: Any) -> None:
        """Set a configuration value by path.
        
        Args:
            path: Dot-separated path to the config value (e.g., 'display.refresh_rate')
            value: The value to set
        """
        # Load configuration if not already loaded
        if not self.loaded:
            self.load()
            
        # Split the path and navigate/create the config structure
        parts = path.split('.')
        config = self.config
        
        # Navigate to the right level, creating dict nodes as needed
        for i, part in enumerate(parts[:-1]):
            if part not in config:
                config[part] = {}
            elif not isinstance(config[part], dict):
                # If this level exists but isn't a dict, make it one
                config[part] = {}
            config = config[part]
            
        # Set the value at the final level
        config[parts[-1]] = value
        
        # Revalidate the config
        self._validate_config()

    def save(self, file_path: Optional[str] = None) -> bool:
        """Save the current configuration to a file.
        
        Args:
            file_path: Path to save the configuration to. If not provided,
                      the user config path will be used.
                      
        Returns:
            True if the save was successful, False otherwise.
        """
        save_path = file_path or USER_CONFIG_PATH
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        try:
            with open(save_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False)
            logger.info(f"Saved configuration to {save_path}")
            return True
        except (OSError, IOError) as e:
            logger.error(f"Failed to save configuration to {save_path}: {e}")
            return False


# Helper function for external modules
def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load and validate configuration.
    
    Args:
        config_path: Optional path to configuration file
        
    Returns:
        Dict containing the configuration
    """
    config_manager = ConfigManager(config_path)
    return config_manager.load()


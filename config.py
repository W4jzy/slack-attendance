import os
from configparser import ConfigParser
from typing import Dict, Optional, Any
import logging

class ConfigError(Exception):
    """Base exception for configuration related errors"""
    pass

# Type-safe configuration dictionary
config: Dict[str, Optional[str]] = {
    "admin_group": None,
    "export_channel": None,
    "coming_text": "Coming",
    "late_text": "Late",
    "notcoming_text": "Not Coming",
    "coming_training": "Coming",
    "late_training": "Late",
    "notcoming_training": "Not Coming",
}

def load_settings(filename: str = 'config.ini', logger: Optional[logging.Logger] = None) -> None:
    """
    Load settings from configuration file.
    
    Args:
        filename: Path to configuration file
        logger: Optional logger instance
        
    Raises:
        ConfigError: If configuration cannot be loaded
    """
    parser = ConfigParser()
    try:
        if not os.path.exists(filename):
            error_msg = f'Configuration file {filename} not found'
            if logger:
                logger.error(error_msg)
            raise ConfigError(error_msg)

        parser.read(filename)
        
        if not parser.has_section('settings'):
            error_msg = 'Missing [settings] section in config file'
            if logger:
                logger.error(error_msg)
            raise ConfigError(error_msg)

        for key in config.keys():
            if parser.has_option('settings', key):
                config[key] = parser.get('settings', key)
            elif logger:
                logger.warning(f"Missing configuration key: {key}")

        update_global_variables(logger)
        
        if logger:
            logger.info("Configuration loaded successfully")
            
    except ConfigParser.Error as e:
        error_msg = f"Configuration parsing error: {e}"
        if logger:
            logger.error(error_msg)
        raise ConfigError(error_msg)
    except Exception as e:
        error_msg = f"Unexpected error loading configuration: {e}"
        if logger:
            logger.error(error_msg)
        raise ConfigError(error_msg)

def save_settings(filename: str = 'config.ini', logger: Optional[logging.Logger] = None) -> None:
    """
    Save settings to configuration file.
    
    Args:
        filename: Path to configuration file
        logger: Optional logger instance
        
    Raises:
        ConfigError: If configuration cannot be saved
    """
    try:
        parser = ConfigParser()
        if os.path.exists(filename):
            parser.read(filename)

        if not parser.has_section('settings'):
            parser.add_section('settings')

        for key, value in config.items():
            parser.set('settings', key, str(value) if value is not None else "")

        with open(filename, 'w') as configfile:
            parser.write(configfile)
            
        if logger:
            logger.info("Configuration saved successfully")
            
    except (IOError, OSError) as e:
        error_msg = f"File operation error: {e}"
        if logger:
            logger.error(error_msg)
        raise ConfigError(error_msg)
    except Exception as e:
        error_msg = f"Unexpected error saving configuration: {e}"
        if logger:
            logger.error(error_msg)
        raise ConfigError(error_msg)

def get_setting(key: str, logger: Optional[logging.Logger] = None) -> Optional[str]:
    """
    Get configuration setting value.
    
    Args:
        key: Configuration key
        logger: Optional logger instance
        
    Returns:
        Optional[str]: Configuration value
        
    Raises:
        ConfigError: If key is invalid
    """
    if key not in config:
        error_msg = f"Invalid configuration key: {key}"
        if logger:
            logger.error(error_msg)
        raise ConfigError(error_msg)
    return config.get(key)

def set_setting(key: str, value: Optional[str], logger: Optional[logging.Logger] = None) -> None:
    """
    Set configuration setting value.
    
    Args:
        key: Configuration key
        value: Configuration value
        logger: Optional logger instance
        
    Raises:
        ConfigError: If key is invalid
    """
    if key not in config:
        error_msg = f"Invalid configuration key: {key}"
        if logger:
            logger.error(error_msg)
        raise ConfigError(error_msg)
    config[key] = value
    if logger:
        logger.debug(f"Updated configuration: {key}={value}")

def update_global_variables(logger: Optional[logging.Logger] = None) -> None:
    """
    Update global variables from configuration.
    
    Args:
        logger: Optional logger instance
        
    Raises:
        ConfigError: If required configuration is missing
    """
    try:
        global admin_group, export_channel
        global coming_text, late_text, notcoming_text, coming_training, late_training, notcoming_training

        admin_group = config["admin_group"]
        export_channel = config["export_channel"]
        coming_text = config["coming_text"]
        late_text = config["late_text"]
        notcoming_text = config["notcoming_text"]
        coming_training = config["coming_training"]
        late_training = config["late_training"]
        notcoming_training = config["notcoming_training"]
        
    except KeyError as e:
        error_msg = f"Missing configuration key: {e}"
        if logger:
            logger.error(error_msg)
        raise ConfigError(error_msg)

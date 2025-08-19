"""
Configuration Reader for Splunk MCP Server

Loads and validates configuration from YAML file.
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional
from pathlib import Path


class ConfigReader:
    """Handles loading and validation of configuration."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the configuration reader.
        
        Args:
            config_path: Path to configuration file. If not provided,
                        looks for config.yml in the project root.
        """
        self.logger = logging.getLogger(__name__)
        
        if config_path is None:
            # Look for config.yml in project root
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config.yml"
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self._validate_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Please ensure config.yml exists and is properly configured."
            )
        
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
                
            if config is None:
                raise ValueError("Configuration file is empty")
                
            return config
            
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in configuration file: {e}")
        except Exception as e:
            raise ValueError(f"Error loading configuration: {e}")
    
    def _validate_config(self):
        """Validate the configuration structure and required fields."""
        required_sections = ['splunk', 'indexes', 'query_settings']
        
        for section in required_sections:
            if section not in self.config:
                raise ValueError(f"Missing required configuration section: {section}")
        
        # Validate Splunk connection settings
        if 'host' not in self.config['splunk']:
            raise ValueError("Missing 'host' in splunk configuration")
        if 'port' not in self.config['splunk']:
            raise ValueError("Missing 'port' in splunk configuration")
        if 'username' not in self.config['splunk']:
            raise ValueError("Missing 'username' in splunk configuration")
        
        # Validate indexes
        if 'uat' not in self.config['indexes']:
            raise ValueError("Missing 'uat' indexes in configuration")
        if 'prod' not in self.config['indexes']:
            raise ValueError("Missing 'prod' indexes in configuration")
    
    
    def get_splunk_config(self) -> Dict[str, Any]:
        """
        Get Splunk connection configuration.
        
        Returns:
            Splunk configuration dictionary
        """
        return self.config['splunk']
    
    def get_index_for_environment(self, environment: str) -> str:
        """
        Get the index for a specific environment.
        
        Args:
            environment: Environment name ('uat' or 'prod')
            
        Returns:
            Index name for the environment
            
        Raises:
            ValueError: If environment not found
        """
        if environment not in self.config['indexes']:
            available = list(self.config['indexes'].keys())
            raise ValueError(
                f"Environment '{environment}' not found. "
                f"Available environments: {', '.join(available)}"
            )
        
        return self.config['indexes'][environment]
    
    
    def get_query_settings(self) -> Dict[str, Any]:
        """Get query settings from configuration."""
        return self.config.get('query_settings', {
            'default_earliest_time': '-30d',
            'default_latest_time': 'now',
            'max_results': 10000,
            'page_size': 1000,
            'output_mode': 'json',
            'include_field_summary': True,
            'include_raw_events': True,
            'max_execution_time': 300
        })
    
    def get_formatting_settings(self) -> Dict[str, Any]:
        """Get formatting settings from configuration."""
        return self.config.get('formatting', {
            'timestamp_format': 'ISO8601',
            'pretty_print': True,
            'include_metadata': True
        })
    
    def get_logging_settings(self) -> Dict[str, Any]:
        """Get logging settings from configuration."""
        return self.config.get('logging', {
            'level': 'INFO',
            'log_queries': True
        })
    
    def list_environments(self) -> list:
        """Get list of configured environments."""
        return list(self.config['indexes'].keys())
    
    def reload(self):
        """Reload configuration from file."""
        self.config = self._load_config()
        self._validate_config()
        self.logger.info("Configuration reloaded successfully")


# Singleton instance
_config_reader = None

def get_config_reader(config_path: Optional[str] = None) -> ConfigReader:
    """
    Get the singleton ConfigReader instance.
    
    Args:
        config_path: Path to configuration file (only used on first call)
        
    Returns:
        ConfigReader instance
    """
    global _config_reader
    if _config_reader is None:
        _config_reader = ConfigReader(config_path)
    return _config_reader

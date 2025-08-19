"""
Splunk Client Wrapper for MCP Server

Provides a robust interface to Splunk with proper error handling,
DNS resolution, timeouts, and retry logic.
"""

import logging
import socket
import time
import json
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

import splunklib.client as client
import splunklib.results as results
from splunklib.binding import HTTPError

from ..config.config_reader import get_config_reader
from .credential_manager import credential_manager


class SplunkClient:
    """Wrapper for Splunk SDK with enhanced error handling."""
    
    def __init__(self):
        """Initialize the Splunk client."""
        self.logger = logging.getLogger(__name__)
        self.config_reader = get_config_reader()
        self._connections = {}
        self._last_query_info = {}
    
    def _resolve_hostname(self, hostname: str) -> str:
        """
        Resolve hostname to IP address for better DNS handling.
        
        Args:
            hostname: Hostname to resolve
            
        Returns:
            IP address or original hostname if resolution fails
        """
        try:
            # Try to resolve the hostname
            ip_address = socket.gethostbyname(hostname)
            self.logger.debug(f"Resolved {hostname} to {ip_address}")
            return ip_address
        except socket.gaierror:
            self.logger.warning(f"Could not resolve hostname {hostname}, using as-is")
            return hostname
    
    def _create_connection(self, retry_count: int = 3) -> client.Service:
        """
        Create a connection to Splunk with retry logic.
        
        Args:
            retry_count: Number of connection attempts
            
        Returns:
            Splunk Service object
            
        Raises:
            ConnectionError: If connection fails after all retries
        """
        splunk_config = self.config_reader.get_splunk_config()
        
        # Get decrypted credentials
        credentials = credential_manager.get_credentials(splunk_config)
        
        # Resolve hostname for better DNS handling
        host = self._resolve_hostname(splunk_config['host'])
        port = splunk_config['port']
        timeout = splunk_config.get('timeout', 30)
        verify_ssl = splunk_config.get('verify_ssl', False)
        
        # Connection parameters
        kwargs = {
            'host': host,
            'port': port,
            'username': credentials['username'],
            'password': credentials['password'],
            'autologin': True,
            'owner': 'nobody',
            'app': '-'
        }
        
        # Handle SSL verification
        if not verify_ssl:
            kwargs['verify'] = False
        
        # Retry logic
        last_error = None
        for attempt in range(retry_count):
            try:
                self.logger.info(f"Connecting to Splunk (attempt {attempt + 1}/{retry_count})")
                
                # Create connection with timeout
                service = client.connect(**kwargs)
                
                # Test the connection
                service.apps.list()
                
                self.logger.info(f"Successfully connected to Splunk")
                return service
                
            except HTTPError as e:
                last_error = e
                if e.status == 401:
                    raise ConnectionError(f"Authentication failed: Invalid credentials")
                else:
                    self.logger.warning(f"HTTP error on attempt {attempt + 1}: {e}")
                    
            except socket.timeout:
                last_error = "Connection timeout"
                self.logger.warning(f"Connection timeout on attempt {attempt + 1}")
                
            except Exception as e:
                last_error = e
                self.logger.warning(f"Connection error on attempt {attempt + 1}: {e}")
            
            # Wait before retry (exponential backoff)
            if attempt < retry_count - 1:
                wait_time = 2 ** attempt
                self.logger.info(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
        
        # All retries failed
        raise ConnectionError(
            f"Failed to connect to Splunk after {retry_count} attempts. "
            f"Last error: {last_error}"
        )
    
    def get_connection(self, force_new: bool = False) -> client.Service:
        """
        Get a connection to Splunk, creating new one if needed.
        
        Args:
            force_new: Force creation of new connection
            
        Returns:
            Splunk Service object
        """
        if force_new or 'main' not in self._connections:
            self._connections['main'] = self._create_connection()
        
        # Test if connection is still alive
        try:
            self._connections['main'].apps.list()
        except Exception:
            self.logger.info(f"Connection expired, reconnecting...")
            self._connections['main'] = self._create_connection()
        
        return self._connections['main']
    
    def check_connection(self) -> Dict[str, Any]:
        """
        Check connection to Splunk.
        
        Returns:
            Connection status information
        """
        try:
            service = self.get_connection()
            
            # Get server info
            info = service.info()
            
            # Get user info
            current_user = service.users[credentials['username']] if 'credentials' in locals() else None
            
            # Get available indexes
            indexes = [idx.name for idx in service.indexes.list()][:10]  # Limit to 10 for brevity
            
            return {
                'status': 'connected',
                'server_info': {
                    'version': info.get('version', 'Unknown'),
                    'build': info.get('build', 'Unknown'),
                    'server_name': info.get('serverName', 'Unknown')
                },
                'available_indexes': indexes,
                'connection_time': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'connection_time': time.strftime('%Y-%m-%d %H:%M:%S')
            }
    
    def execute_query(
        self,
        query: str,
        earliest_time: Optional[str] = None,
        latest_time: Optional[str] = None,
        max_results: Optional[int] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute a Splunk query with pagination support.
        
        Args:
            query: SPL query to execute
            earliest_time: Earliest time for search (e.g., '-24h')
            latest_time: Latest time for search (e.g., 'now')
            max_results: Maximum number of results to return
            timeout: Query timeout in seconds
            
        Returns:
            Query results with metadata
        """
        try:
            service = self.get_connection()
            query_settings = self.config_reader.get_query_settings()
            
            # Set defaults from config
            if earliest_time is None:
                earliest_time = query_settings.get('default_earliest_time', '-30d')
            if latest_time is None:
                latest_time = query_settings.get('default_latest_time', 'now')
            if max_results is None:
                max_results = query_settings.get('max_results', 10000)
            if timeout is None:
                timeout = query_settings.get('max_execution_time', 300)
            
            # Ensure query starts with 'search' if it doesn't have a generating command
            if not any(query.strip().startswith(cmd) for cmd in ['search', '|', 'index']):
                query = f"search {query}"
            
            self.logger.info(f"Executing query: {query[:100]}...")
            
            # Create search job
            kwargs = {
                'earliest_time': earliest_time,
                'latest_time': latest_time,
                'max_count': max_results,
                'exec_mode': 'normal',
                'output_mode': 'json'
            }
            
            job = service.jobs.create(query, **kwargs)
            
            # Wait for job to complete with timeout
            start_time = time.time()
            while not job.is_done():
                if time.time() - start_time > timeout:
                    job.cancel()
                    raise TimeoutError(f"Query execution exceeded timeout of {timeout} seconds")
                time.sleep(0.5)
            
            # Get job statistics
            stats = {
                'scan_count': int(job['scanCount']),
                'event_count': int(job['eventCount']),
                'result_count': int(job['resultCount']),
                'run_duration': float(job['runDuration'])
            }
            
            # Store query info for pagination
            self._last_query_info = {
                'job_id': job.sid,
                'query': query,
                'stats': stats
            }
            
            # Get results
            results_reader = job.results(count=max_results, output_mode='json')
            results_data = json.loads(results_reader.read())
            
            # Clean up job
            job.cancel()
            
            return {
                'status': 'success',
                'query': query,
                'time_range': {
                    'earliest': earliest_time,
                    'latest': latest_time
                },
                'statistics': stats,
                'results': results_data.get('results', []),
                'fields': results_data.get('fields', []),
                'messages': results_data.get('messages', [])
            }
            
        except TimeoutError as e:
            return {
                'status': 'error',
                'query': query,
                'error': str(e),
                'error_type': 'timeout'
            }
            
        except HTTPError as e:
            return {
                'status': 'error',
                'query': query,
                'error': f"HTTP Error {e.status}: {e.message}",
                'error_type': 'http_error'
            }
            
        except Exception as e:
            self.logger.error(f"Query execution failed: {e}")
            return {
                'status': 'error',
                'query': query,
                'error': str(e),
                'error_type': 'general_error'
            }
    
    def get_indexes(self) -> List[str]:
        """
        Get list of available indexes.
        
        Returns:
            List of index names
        """
        try:
            service = self.get_connection()
            indexes = [idx.name for idx in service.indexes.list()]
            return indexes
        except Exception as e:
            self.logger.error(f"Failed to get indexes: {e}")
            return []
    
    def get_sourcetypes(self, index: Optional[str] = None) -> List[str]:
        """
        Get list of available sourcetypes.
        
        Args:
            index: Optional index to filter sourcetypes
            
        Returns:
            List of sourcetype names
        """
        try:
            service = self.get_connection()
            
            # Query to get sourcetypes
            if index:
                query = f"| metadata type=sourcetypes index={index}"
            else:
                query = "| metadata type=sourcetypes"
            
            # Execute query
            result = self.execute_query(
                query=query,
                earliest_time="-7d",
                latest_time="now",
                max_results=1000
            )
            
            if result['status'] == 'success':
                sourcetypes = [r.get('sourcetype', '') for r in result.get('results', [])]
                return [st for st in sourcetypes if st]
            
            return []
            
        except Exception as e:
            self.logger.error(f"Failed to get sourcetypes: {e}")
            return []
    
    def close_all_connections(self):
        """Close all active connections."""
        for env, service in self._connections.items():
            try:
                service.logout()
                self.logger.info(f"Closed connection to {env}")
            except Exception as e:
                self.logger.warning(f"Error closing connection to {env}: {e}")
        
        self._connections.clear()


# Singleton instance
splunk_client = SplunkClient()

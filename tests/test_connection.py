#!/usr/bin/env python3
"""
Splunk Connection Test

Tests the connection to Splunk server using configured credentials
and executes a simple query to verify functionality.
"""

import sys
import os
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.config.config_reader import get_config_reader
from src.utils.splunk_client import splunk_client
from src.utils.credential_manager import credential_manager


def test_connection():
    """Test connection to Splunk server."""
    print("=" * 60)
    print("SPLUNK MCP SERVER - CONNECTION TEST")
    print("=" * 60)
    print()
    
    try:
        # Load configuration
        print("1. Loading configuration...")
        config_reader = get_config_reader()
        splunk_config = config_reader.get_splunk_config()
        print(f"   ✓ Configuration loaded")
        print(f"   - Host: {splunk_config['host']}")
        print(f"   - Port: {splunk_config['port']}")
        print()
        
        # Test credential decryption
        print("2. Testing credential decryption...")
        try:
            credentials = credential_manager.get_credentials(splunk_config)
            print(f"   ✓ Credentials decrypted successfully")
            print(f"   - Username: {credentials['username']}")
            print()
        except Exception as e:
            print(f"   ✗ Failed to decrypt credentials: {e}")
            print("   Please run encrypt_password.py to set up credentials")
            return False
        
        # Test connection
        print("3. Testing connection to Splunk...")
        connection_result = splunk_client.check_connection()
        
        if connection_result['status'] == 'connected':
            print(f"   ✓ Successfully connected to Splunk")
            print(f"   - Version: {connection_result['server_info']['version']}")
            print(f"   - Server: {connection_result['server_info']['server_name']}")
            print(f"   - Available indexes: {', '.join(connection_result['available_indexes'][:5])}")
            if len(connection_result['available_indexes']) > 5:
                print(f"     ... and {len(connection_result['available_indexes']) - 5} more")
            print()
        else:
            print(f"   ✗ Failed to connect: {connection_result['error']}")
            return False
        
        # Execute test query
        print("4. Executing test query...")
        # Note: | makeresults doesn't require an index - it generates synthetic data
        test_query = "| makeresults count=5 | eval test_field=\"MCP Connection Test\""
        print(f"   Query: {test_query}")
        print("   Note: This query generates synthetic data and doesn't require an index")
        
        query_result = splunk_client.execute_query(
            query=test_query,
            earliest_time="-1h",
            latest_time="now",
            max_results=10
        )
        
        if query_result['status'] == 'success':
            print(f"   ✓ Query executed successfully")
            print(f"   - Results returned: {query_result['statistics']['result_count']}")
            print(f"   - Execution time: {query_result['statistics']['run_duration']:.2f}s")
            
            # Verify results
            if query_result['results'] and len(query_result['results']) == 5:
                first_result = query_result['results'][0]
                if 'test_field' in first_result and first_result['test_field'] == 'MCP Connection Test':
                    print(f"   ✓ Results validated successfully")
                else:
                    print(f"   ⚠ Results structure unexpected")
            print()
        else:
            print(f"   ✗ Query failed: {query_result['error']}")
            return False
        
        # Test environment indexes
        print("5. Testing environment index configuration...")
        environments = config_reader.list_environments()
        for env in environments:
            index = config_reader.get_index_for_environment(env)
            print(f"   {env.upper()}: {index}")
        print()
        
        # Final status
        print("=" * 60)
        print("CONNECTION TEST: PASSED ✓")
        print("=" * 60)
        print("\nYour Splunk MCP Server is properly configured and ready to use!")
        print("\nTo start the server, run:")
        print("  python splunk_mcp.py")
        
        return True
        
    except FileNotFoundError as e:
        print(f"\n✗ Configuration file not found: {e}")
        print("\nPlease ensure config.yml exists and is properly configured")
        return False
        
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Clean up connections
        splunk_client.close_all_connections()


if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""
Splunk MCP Server

A Model Context Protocol server for executing Splunk queries
in UAT and PROD environments with secure credential management.
"""

import asyncio
import logging
import sys
from typing import Any, Sequence

from mcp import server, types
from mcp.server import Server
from mcp.server.stdio import stdio_server

# Import our modules
try:
    from src.config.config_reader import get_config_reader
    from src.utils.splunk_client import splunk_client
    from src.utils.response_formatter import response_formatter
    from src.utils.credential_manager import credential_manager
except ImportError as e:
    print(f"[ERROR] Import Error: {e}")
    print("\n[INFO] Please install required dependencies:")
    print("   pip install -r requirements.txt")
    sys.exit(1)


# Set up logging
def setup_logging():
    """Configure logging based on config settings."""
    try:
        config_reader = get_config_reader()
        log_settings = config_reader.get_logging_settings()
        
        log_level = getattr(logging, log_settings.get('level', 'INFO'))
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        logging.basicConfig(
            level=log_level,
            format=log_format
        )
        
        # Optionally log to file
        if 'log_file' in log_settings:
            file_handler = logging.FileHandler(log_settings['log_file'])
            file_handler.setFormatter(logging.Formatter(log_format))
            logging.getLogger().addHandler(file_handler)
            
    except Exception as e:
        # Fallback to basic logging if config fails
        logging.basicConfig(level=logging.INFO)
        logging.warning(f"Could not load logging config: {e}")


# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

# Create MCP server instance
app = Server("splunk-mcp-server")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """List available MCP tools."""
    return [
        types.Tool(
            name="get_index_for_environment",
            description="Get the index name for a specific environment (UAT or PROD). Use this first to determine which index to use for your queries.",
            inputSchema={
                "type": "object",
                "properties": {
                    "environment": {
                        "type": "string",
                        "description": "Environment to get index for (uat or prod)",
                        "enum": ["uat", "prod"]
                    }
                },
                "required": ["environment"]
            }
        ),
        types.Tool(
            name="check_connection",
            description="Check connection status to Splunk server. Returns server info and available indexes.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="execute_query",
            description="Execute a Splunk SPL query. Use the index from get_index_for_environment. To filter by sourcetype, first use get_sourcetypes to find available sourcetypes, then add 'sourcetype=your_sourcetype' to your query. Example: 'index=index_app_fxs sourcetype=trade_server order_id=ABC'. Supports time ranges and pagination.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SPL query to execute (e.g., 'index=index_app_fxs sourcetype=accessfx_trade_server_ext order_id=ABC')"
                    },
                    "earliest_time": {
                        "type": "string",
                        "description": "Earliest time for search (e.g., '-2d' for last 2 days, '-7d', '2024-01-01T00:00:00')",
                        "default": "-30d"
                    },
                    "latest_time": {
                        "type": "string",
                        "description": "Latest time for search (e.g., 'now', '-1h', '2024-01-01T23:59:59')",
                        "default": "now"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default from config)",
                        "minimum": 1,
                        "maximum": 50000
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="get_available_indexes",
            description="Get list of all available indexes in Splunk.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="get_sourcetypes",
            description="Get list of available sourcetypes from Splunk, optionally filtered by index. Use this to discover what sourcetypes are available, then include 'sourcetype=your_sourcetype' in your execute_query calls.",
            inputSchema={
                "type": "object",
                "properties": {
                    "index": {
                        "type": "string",
                        "description": "Optional index to filter sourcetypes"
                    }
                },
                "required": []
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> Sequence[types.TextContent]:
    """Handle tool calls."""
    
    logger.info(f"Executing tool: {name} with arguments: {arguments}")
    
    try:
        # Get config reader for query settings
        config_reader = get_config_reader()
        query_settings = config_reader.get_query_settings()
        
        if name == "get_index_for_environment":
            environment = arguments.get("environment")
            if not environment:
                raise ValueError("environment parameter is required")
            
            # Get index for environment
            index = config_reader.get_index_for_environment(environment)
            
            # Format response
            formatted = response_formatter.format_environment_index_response(environment, index)
            
            return [types.TextContent(type="text", text=formatted)]
            
        elif name == "check_connection":
            # Check connection (run in thread to avoid blocking)
            result = await asyncio.to_thread(
                splunk_client.check_connection
            )
            
            # Format response
            formatted = response_formatter.format_connection_response(result)
            
            return [types.TextContent(type="text", text=formatted)]
            
        elif name == "execute_query":
            query = arguments.get("query")
            
            if not query:
                raise ValueError("query parameter is required")
            
            # Fix double-escaping issue: if query contains escaped quotes, unescape them
            # This handles cases where the MCP client sends already-escaped strings
            # Check if the string contains literal backslash-quote sequences
            if '\\"' in query:
                # Replace literal \" with just "
                query = query.replace('\\"', '"')
                logger.info(f"Unescaped query: {query}")
            
            # Get optional parameters
            earliest_time = arguments.get("earliest_time")
            latest_time = arguments.get("latest_time")
            max_results = arguments.get("max_results")
            
            # Log query if configured
            if query_settings.get('log_queries', True):
                logger.info(f"Executing query: {query}")
            
            # Execute query (run in thread to avoid blocking)
            result = await asyncio.to_thread(
                splunk_client.execute_query,
                query=query,
                earliest_time=earliest_time,
                latest_time=latest_time,
                max_results=max_results
            )
            
            # Format response with pagination support
            formatted = response_formatter.format_query_response(
                result,
                include_raw=query_settings.get('include_raw_events', True),
                page_size=query_settings.get('page_size', 1000)
            )
            
            return [types.TextContent(type="text", text=formatted)]
            
        elif name == "get_available_indexes":
            # Get indexes (run in thread to avoid blocking)
            indexes = await asyncio.to_thread(
                splunk_client.get_indexes
            )
            
            # Format response
            formatted = response_formatter.format_indexes_response(indexes)
            
            return [types.TextContent(type="text", text=formatted)]
            
        elif name == "get_sourcetypes":
            index = arguments.get("index")
            
            # Get sourcetypes (run in thread to avoid blocking)
            sourcetypes = await asyncio.to_thread(
                splunk_client.get_sourcetypes,
                index
            )
            
            # Format response
            formatted = response_formatter.format_sourcetypes_response(
                sourcetypes,
                index
            )
            
            return [types.TextContent(type="text", text=formatted)]
            
        else:
            raise ValueError(f"Unknown tool: {name}")
            
    except FileNotFoundError as e:
        # Config file not found
        import json
        error_response = {
            "status": "error",
            "tool": name,
            "error": str(e),
            "message": "Configuration file not found. Please create config.yaml from config.yaml.example"
        }
        logger.error(f"Configuration error: {e}")
        return [types.TextContent(type="text", text=json.dumps(error_response, indent=2))]
        
    except ValueError as e:
        # Validation errors
        import json
        error_response = {
            "status": "error",
            "tool": name,
            "error": str(e),
            "message": f"Invalid parameters: {str(e)}"
        }
        logger.error(f"Validation error in tool {name}: {e}")
        return [types.TextContent(type="text", text=json.dumps(error_response, indent=2))]
        
    except ConnectionError as e:
        # Connection errors
        import json
        error_response = {
            "status": "error",
            "tool": name,
            "error": str(e),
            "message": "Failed to connect to Splunk. Check your configuration and network."
        }
        logger.error(f"Connection error in tool {name}: {e}")
        return [types.TextContent(type="text", text=json.dumps(error_response, indent=2))]
        
    except Exception as e:
        # General errors
        import json
        error_response = {
            "status": "error",
            "tool": name,
            "error": str(e),
            "message": f"Failed to execute {name}: {str(e)}"
        }
        logger.error(f"Error in tool {name}: {e}", exc_info=True)
        return [types.TextContent(type="text", text=json.dumps(error_response, indent=2))]


@app.list_resources()
async def list_resources() -> list[types.Resource]:
    """List available resources."""
    return [
        types.Resource(
            uri="splunk://config",
            name="Current Configuration",
            description="View current Splunk MCP configuration (sanitized)",
            mimeType="application/json"
        ),
        types.Resource(
            uri="splunk://environments",
            name="Available Environments",
            description="List configured Splunk environments",
            mimeType="application/json"
        )
    ]


@app.read_resource()
async def read_resource(uri: str) -> str:
    """Read resource content."""
    import json
    
    try:
        config_reader = get_config_reader()
        
        if uri == "splunk://config":
            # Return sanitized config (no passwords)
            config = config_reader.config.copy()
            
            # Remove sensitive data
            if 'splunk' in config:
                if 'password' in config['splunk']:
                    config['splunk']['password'] = "***HIDDEN***"
                if 'password_encrypted' in config['splunk']:
                    config['splunk']['password_encrypted'] = "***ENCRYPTED***"
                if 'password_salt' in config['splunk']:
                    config['splunk']['password_salt'] = "***SALT***"
            
            return json.dumps(config, indent=2)
            
        elif uri == "splunk://environments":
            environments = config_reader.list_environments()
            env_info = {}
            
            for env in environments:
                index = config_reader.get_index_for_environment(env)
                env_info[env] = {
                    "index": index
                }
            
            return json.dumps(env_info, indent=2)
            
        else:
            raise ValueError(f"Unknown resource: {uri}")
            
    except Exception as e:
        logger.error(f"Error reading resource {uri}: {e}")
        return json.dumps({"error": str(e)})


async def main():
    """Main entry point for the MCP server."""
    logger.info("Starting Splunk MCP Server...")
    
    try:
        # Verify configuration exists
        config_reader = get_config_reader()
        environments = config_reader.list_environments()
        logger.info(f"Configured environments: {', '.join(environments)}")
        
    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        print("\n[ERROR] Configuration file not found!")
        print("[INFO] Please ensure config.yml exists")
        print("[INFO] Then run: python encrypt_password.py")
        print("       to securely encrypt your password")
        sys.exit(1)
        
    except Exception as e:
        logger.error(f"Startup error: {e}")
        print(f"\n[ERROR] Failed to start server: {e}")
        sys.exit(1)
    
    # Run the server
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )
    
    # Cleanup
    logger.info("Shutting down Splunk MCP Server...")
    splunk_client.close_all_connections()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

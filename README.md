# Splunk MCP Server

A secure Model Context Protocol (MCP) server for executing Splunk queries with environment-specific index mappings and enterprise-grade credential management.

## Features

- 🔐 **Secure Credential Management**: Machine-specific encryption ensures passwords can only be decrypted on the authorized machine
- 🌐 **Environment-Specific Indexes**: Same credentials for UAT/PROD with different index mappings
- 📊 **AI-Optimized Output**: JSON responses formatted for optimal consumption by AI assistants like GitHub Copilot
- 📄 **Pagination Support**: Handle large result sets with automatic pagination guidance
- 🔄 **Automatic Retry Logic**: Built-in connection retry with exponential backoff
- 🔍 **Dynamic Discovery**: Automatically discover available sourcetypes and indexes

## Installation

### Prerequisites

- Python 3.8 or higher
- Access to Splunk Enterprise (UAT and/or PROD)
- Valid Splunk credentials

### Setup Steps

1. **Clone the repository**
   ```bash
   cd /Users/abhishek_aditya/code/Splunk-MCP-Server
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Update configuration file**
   
   Edit `config.yml` with your actual Splunk server hostname:
   - Replace `splunk.yourcompany.com` with your actual Splunk server
   - Update index mappings for UAT and PROD environments

4. **Encrypt your passwords**
   ```bash
   python encrypt_password.py
   ```
   
   Follow the prompts to:
   - Enter your Splunk username (same for UAT and PROD)
   - Enter your Splunk password (same for UAT and PROD)
   - Copy the encrypted output to your `config.yml`

5. **Test the connection**
   ```bash
   python tests/test_connection.py
   ```
   
   This will verify:
   - Configuration is loaded correctly
   - Credentials can be decrypted
   - Connection to Splunk is successful
   - Test query executes properly

## Configuration

### Configuration Structure (`config.yml`)

```yaml
splunk:
  host: "splunk.yourcompany.com"  # Your Splunk server
  port: 8089
  username: "your_username"  # Your Splunk username
  password_encrypted: "xxx"  # From encrypt_password.py
  password_salt: "xxx"       # From encrypt_password.py
  machine_hash: "xxx"        # From encrypt_password.py

indexes:
  uat: "index_app_fxs_uat"   # UAT environment index
  prod: "index_app_fxs"       # PROD environment index

query_settings:
  default_earliest_time: "-30d"  # Default: last 30 days
  default_latest_time: "now"
  max_results: 10000
  page_size: 1000
```

## Usage

### Starting the Server

```bash
python splunk_mcp.py
```

### Available Tools

#### 1. **get_index_for_environment**
Get the index name for UAT or PROD environment. Use this first to determine which index to use.

**Parameters:**
- `environment`: "uat" or "prod"

**Example:**
```json
{
  "tool": "get_index_for_environment",
  "arguments": {
    "environment": "prod"
  }
}
```
Returns: `{"index": "index_app_fxs"}`

#### 2. **check_connection**
Verify connectivity to Splunk server.

**Parameters:** None

**Example:**
```json
{
  "tool": "check_connection",
  "arguments": {}
}
```

#### 3. **execute_query**
Execute SPL queries. Use the index from `get_index_for_environment`. To filter by sourcetype, first use `get_sourcetypes` to discover available sourcetypes.

**Parameters:**
- `query`: SPL query string (include the index)
- `earliest_time` (optional): Start time (default: "-30d")
- `latest_time` (optional): End time (default: "now")
- `max_results` (optional): Maximum results

**Example:**
```json
{
  "tool": "execute_query",
  "arguments": {
    "query": "index=index_app_fxs sourcetype=accessfx_trade_server_ext order_id=ABC",
    "earliest_time": "-2d",
    "latest_time": "now"
  }
}
```

#### 4. **get_available_indexes**
List all available indexes in Splunk.

**Parameters:** None

#### 5. **get_sourcetypes**
List available sourcetypes from Splunk, optionally filtered by index. Use this to discover what sourcetypes are available, then include `sourcetype=your_sourcetype` in your queries.

**Parameters:**
- `index` (optional): Filter by specific index

**Example:**
```json
{
  "tool": "get_sourcetypes",
  "arguments": {
    "index": "index_app_fxs"
  }
}
```

## Workflow Example

### Finding Failed Orders in Production

1. **Get PROD index:**
   ```
   Tool: get_index_for_environment
   Input: {"environment": "prod"}
   Output: {"index": "index_app_fxs"}
   ```

2. **Get available sourcetypes (optional):**
   ```
   Tool: get_sourcetypes
   Input: {"index": "index_app_fxs"}
   Output: {"sourcetypes": ["trade_server", "risk_engine", ...]}
   ```

3. **Execute search query:**
   ```
   Tool: execute_query
   Input: {
     "query": "index=index_app_fxs sourcetype=trade_server order_id=ABC123 | head 100",
     "earliest_time": "-2d"
   }
   ```

4. **AI analyzes the JSON response** to identify issues

## Cross-Platform Support

The password encryption utility works across all major operating systems:
- **Windows**: Uses USERNAME environment variable and Windows paths
- **macOS**: Uses USER environment variable and Unix paths  
- **Linux**: Uses USER environment variable and Unix paths

The machine identifier combines:
- MAC address (network hardware ID)
- Username (OS-agnostic)
- Home directory path (cross-platform)
- Platform info (OS and architecture)

## Example SPL Queries

### Basic Searches

```spl
# Find all errors in the last 24 hours
index=main error

# Count events by host
index=main | stats count by host

# Search for specific error patterns
index=app_logs "NullPointerException" | head 100

# Time-based analysis
index=main | timechart span=1h count by status
```

### Application Monitoring

```spl
# Find slow API responses
index=app_logs response_time>1000 
| stats avg(response_time) as avg_time, max(response_time) as max_time by endpoint

# Error rate by service
index=app_logs 
| stats count(eval(status>=400)) as errors, count as total by service 
| eval error_rate=round((errors/total)*100, 2)

# Find failed login attempts
index=security action=login result=failure 
| stats count by user, src_ip 
| sort -count
```

### Log Analysis

```spl
# Extract and analyze log levels
index=app_logs 
| rex field=_raw "(?<log_level>ERROR|WARN|INFO|DEBUG)" 
| stats count by log_level

# Find unique error messages
index=app_logs ERROR 
| rex field=_raw "ERROR.*?(?<error_message>[^\\n]+)" 
| stats count by error_message 
| sort -count

# Trace specific request IDs
index=app_logs request_id="abc-123-def" 
| sort _time
```

### Performance Monitoring

```spl
# Database query performance
index=db_logs 
| stats avg(query_time) as avg_time, p95(query_time) as p95_time by query_type

# Memory usage trends
index=metrics metric_name=memory_usage 
| timechart span=5m avg(value) as avg_memory by host

# CPU spikes
index=metrics metric_name=cpu_usage value>80 
| table _time, host, value
```

## Handling Large Result Sets

When queries return more than the configured `page_size` (default: 1000), the server provides:

1. **Preview of first 100 results**
2. **Pagination metadata** showing total pages needed
3. **Guidance** on refining queries

### Best Practices for Large Datasets

1. **Use time constraints**
   ```spl
   index=main earliest=-1h latest=now
   ```

2. **Add specific filters**
   ```spl
   index=main host=prod-server-01 status=error
   ```

3. **Use statistical commands**
   ```spl
   index=main | stats count by field
   ```

4. **Limit results explicitly**
   ```spl
   index=main | head 1000
   ```

5. **Use summary indexes for historical data**
   ```spl
   index=summary_daily
   ```

## Security Considerations

1. **Password Encryption**: Passwords are encrypted using machine-specific identifiers (MAC address, username, home directory)
2. **No Plain Text Storage**: Never store plain text passwords in configuration
3. **Machine Binding**: Encrypted passwords only work on the machine where they were encrypted
4. **Secure Your Config**: Add `config.yaml` to `.gitignore` and never commit it

## Session Management

### Connection Lifetime
- **Initial Authentication**: Uses username/password from config
- **Connection Reuse**: Connections are reused for up to 1 hour
- **Automatic Refresh**: After 1 hour, a new connection is automatically created
- **Session Testing**: Each query tests the connection and reconnects if needed
- **No Token Expiry**: Using username/password auth, there's no token to expire

### Query Guidelines for AI Assistants

When using with GitHub Copilot or other AI assistants, ensure queries:

1. **Escape Special Characters in String Literals**:
   ```spl
   # Correct:
   index=app_fxs "Error while loading cache"
   
   # Incorrect (will cause parsing errors):
   index=app_fxs ERROR c.j.c.f.a.w.f.i.c.i.CacheAfxFeatureToggleImpl
   ```

2. **Use Proper Field Searches**:
   ```spl
   # For exact phrase matching:
   index=app_fxs "ERROR c.j.c.f.a.w.f.i.c.i.CacheAfxFeatureToggleImpl"
   
   # For field-based search:
   index=app_fxs logger="c.j.c.f.a.w.f.i.c.i.CacheAfxFeatureToggleImpl" level=ERROR
   ```

3. **Count Occurrences**:
   ```spl
   index=app_fxs "Error while loading afxFeatureToggles cache" 
   | stats count
   ```

## Troubleshooting

### Common Issues

1. **"Cannot decrypt password: Different machine"**
   - Re-run `encrypt_password.py` on the current machine
   - Update `config.yaml` with new encrypted values

2. **Connection timeouts**
   - Check network connectivity to Splunk servers
   - Verify firewall rules allow port 8089
   - Increase timeout in configuration

3. **Authentication failures**
   - Verify username is correct
   - Re-encrypt password using `encrypt_password.py`
   - Check account permissions in Splunk

4. **Query timeouts**
   - Reduce time range
   - Add more specific filters
   - Increase `max_execution_time` in config

### Debug Mode

Enable debug logging in `config.yaml`:
```yaml
logging:
  level: "DEBUG"
  log_file: "splunk_mcp.log"
```

## Integration with GitHub Copilot

This MCP server is optimized for use with GitHub Copilot and other AI assistants:

1. **Structured JSON responses** for easy parsing
2. **Field summaries** to understand data structure
3. **Event summaries** with top values and distributions
4. **Clear error messages** with troubleshooting tips
5. **Pagination guidance** for large result sets

## Contributing

Feel free to submit issues or pull requests to improve the server.

## License

This project is for internal enterprise use. Please follow your organization's guidelines for code sharing and distribution.

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review example queries
3. Verify configuration settings
4. Enable debug logging for detailed information

---

**Note**: This server is designed for enterprise Splunk deployments with username/password authentication. Token-based authentication can be added if your organization enables it.

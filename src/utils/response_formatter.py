"""
Response Formatter for Splunk MCP Server

Formats Splunk query results into clean, AI-friendly JSON format
with support for pagination and field summaries.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import Counter


class ResponseFormatter:
    """Formats Splunk responses for optimal AI consumption."""
    
    def __init__(self):
        """Initialize the response formatter."""
        self.logger = logging.getLogger(__name__)
    
    def format_connection_response(self, connection_data: Dict[str, Any]) -> str:
        """
        Format connection check response.
        
        Args:
            connection_data: Connection status data
            
        Returns:
            Formatted JSON string
        """
        formatted = {
            "type": "connection_status",
            "status": connection_data.get('status', 'unknown'),
            "timestamp": datetime.now().isoformat()
        }
        
        if connection_data['status'] == 'connected':
            formatted.update({
                "server_info": connection_data.get('server_info', {}),
                "available_indexes": connection_data.get('available_indexes', []),
                "message": "Successfully connected to Splunk"
            })
        else:
            formatted.update({
                "error": connection_data.get('error', 'Unknown error'),
                "message": "Failed to connect to Splunk"
            })
        
        return json.dumps(formatted, indent=2)
    
    def format_query_response(
        self, 
        query_data: Dict[str, Any],
        include_raw: bool = True,
        page_size: int = 1000
    ) -> str:
        """
        Format query execution response with pagination support.
        
        Args:
            query_data: Query results data
            include_raw: Whether to include raw events
            page_size: Number of results per page
            
        Returns:
            Formatted JSON string
        """
        if query_data['status'] == 'error':
            return self._format_error_response(query_data)
        
        results = query_data.get('results', [])
        total_results = len(results)
        stats = query_data.get('statistics', {})
        
        # Calculate pagination info
        pagination_info = self._calculate_pagination(total_results, page_size)
        
        # Generate field summary
        field_summary = self._generate_field_summary(results)
        
        # Generate event summary
        event_summary = self._generate_event_summary(results)
        
        # Format the response
        formatted = {
            "type": "query_results",
            "status": "success",
            "query": query_data.get('query', ''),
            "timestamp": datetime.now().isoformat(),
            "time_range": query_data.get('time_range', {}),
            "statistics": {
                "total_events": stats.get('event_count', 0),
                "total_results": total_results,
                "scan_count": stats.get('scan_count', 0),
                "execution_time": f"{stats.get('run_duration', 0):.2f}s"
            },
            "pagination": pagination_info,
            "field_summary": field_summary,
            "event_summary": event_summary
        }
        
        # Add results based on pagination
        if total_results <= page_size:
            # All results fit in one page
            if include_raw:
                formatted["results"] = self._clean_results(results)
            formatted["message"] = f"Query completed with {total_results} results"
        else:
            # Results need pagination
            formatted["results_preview"] = self._clean_results(results[:100])  # First 100 results
            formatted["message"] = (
                f"Query returned {total_results} results (exceeds page size of {page_size}). "
                f"Showing preview of first 100 results. "
                f"Use pagination or refine your query for complete results."
            )
            formatted["pagination_guidance"] = {
                "total_pages": pagination_info['total_pages'],
                "results_per_page": page_size,
                "suggestion": "Consider adding filters or time constraints to reduce result set"
            }
        
        # Add any messages from Splunk
        if query_data.get('messages'):
            formatted["splunk_messages"] = query_data['messages']
        
        return json.dumps(formatted, indent=2, default=str)
    
    def _format_error_response(self, query_data: Dict[str, Any]) -> str:
        """Format error response."""
        formatted = {
            "type": "query_error",
            "status": "error",
            "query": query_data.get('query', ''),
            "timestamp": datetime.now().isoformat(),
            "error": {
                "message": query_data.get('error', 'Unknown error'),
                "type": query_data.get('error_type', 'general_error')
            },
            "troubleshooting": self._get_troubleshooting_tips(query_data.get('error_type', ''))
        }
        
        return json.dumps(formatted, indent=2)
    
    def _calculate_pagination(self, total_results: int, page_size: int) -> Dict[str, Any]:
        """Calculate pagination information."""
        total_pages = (total_results + page_size - 1) // page_size
        
        return {
            "total_results": total_results,
            "page_size": page_size,
            "total_pages": total_pages,
            "requires_pagination": total_pages > 1
        }
    
    def _generate_field_summary(self, results: List[Dict]) -> Dict[str, Any]:
        """Generate summary of fields in results."""
        if not results:
            return {}
        
        field_summary = {}
        sample_size = min(100, len(results))  # Analyze first 100 results
        
        for result in results[:sample_size]:
            for field, value in result.items():
                if field.startswith('_'):  # Skip internal fields
                    continue
                    
                if field not in field_summary:
                    field_summary[field] = {
                        "sample_values": [],
                        "value_count": Counter()
                    }
                
                # Add to sample values (limit to 5 unique)
                if value not in field_summary[field]["sample_values"]:
                    if len(field_summary[field]["sample_values"]) < 5:
                        field_summary[field]["sample_values"].append(str(value))
                
                # Count occurrences
                field_summary[field]["value_count"][str(value)] += 1
        
        # Clean up and format
        formatted_summary = {}
        for field, data in field_summary.items():
            top_values = data["value_count"].most_common(5)
            formatted_summary[field] = {
                "sample_values": data["sample_values"],
                "unique_count": len(data["value_count"]),
                "top_values": [{"value": v, "count": c} for v, c in top_values]
            }
        
        return formatted_summary
    
    def _generate_event_summary(self, results: List[Dict]) -> Dict[str, Any]:
        """Generate summary statistics for events."""
        if not results:
            return {}
        
        summary = {
            "total_events": len(results)
        }
        
        # Check for common fields and generate summaries
        if any('host' in r for r in results):
            hosts = Counter(r.get('host', 'unknown') for r in results)
            summary["unique_hosts"] = len(hosts)
            summary["top_hosts"] = [
                {"host": h, "count": c} for h, c in hosts.most_common(5)
            ]
        
        if any('source' in r for r in results):
            sources = Counter(r.get('source', 'unknown') for r in results)
            summary["unique_sources"] = len(sources)
            summary["top_sources"] = [
                {"source": s, "count": c} for s, c in sources.most_common(5)
            ]
        
        if any('sourcetype' in r for r in results):
            sourcetypes = Counter(r.get('sourcetype', 'unknown') for r in results)
            summary["sourcetypes"] = [
                {"sourcetype": st, "count": c} for st, c in sourcetypes.most_common()
            ]
        
        # Look for error/severity fields
        for severity_field in ['severity', 'level', 'log_level']:
            if any(severity_field in r for r in results):
                severities = Counter(r.get(severity_field, 'unknown') for r in results)
                summary["severity_distribution"] = [
                    {"level": l, "count": c} for l, c in severities.most_common()
                ]
                break
        
        return summary
    
    def _clean_results(self, results: List[Dict]) -> List[Dict]:
        """Clean and format result events."""
        cleaned = []
        
        for result in results:
            cleaned_result = {}
            
            # Prioritize important fields
            priority_fields = ['_time', 'host', 'source', 'sourcetype', 'message', '_raw']
            
            for field in priority_fields:
                if field in result:
                    cleaned_result[field] = result[field]
            
            # Add other non-internal fields
            for field, value in result.items():
                if not field.startswith('_') and field not in cleaned_result:
                    cleaned_result[field] = value
            
            # Add select internal fields if no raw message
            if '_raw' not in cleaned_result and 'message' not in cleaned_result:
                for field, value in result.items():
                    if field.startswith('_') and field not in ['_time', '_raw']:
                        cleaned_result[field] = value
            
            cleaned.append(cleaned_result)
        
        return cleaned
    
    def _get_troubleshooting_tips(self, error_type: str) -> List[str]:
        """Get troubleshooting tips based on error type."""
        tips = {
            'timeout': [
                "Query took too long to execute",
                "Try reducing the time range",
                "Add more specific filters to reduce data volume",
                "Consider using summary indexes for large datasets"
            ],
            'http_error': [
                "Check your network connectivity",
                "Verify Splunk server is accessible",
                "Ensure credentials are correct",
                "Check if your account has necessary permissions"
            ],
            'general_error': [
                "Verify query syntax is correct",
                "Check if specified indexes exist",
                "Ensure you have permissions for the requested data",
                "Try a simpler query to test connectivity"
            ]
        }
        
        return tips.get(error_type, tips['general_error'])
    
    def format_indexes_response(self, indexes: List[str]) -> str:
        """Format indexes list response."""
        formatted = {
            "type": "indexes_list",
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "total_indexes": len(indexes),
            "indexes": indexes,
            "message": f"Found {len(indexes)} indexes"
        }
        
        return json.dumps(formatted, indent=2)
    
    def format_sourcetypes_response(
        self, 
        sourcetypes: List[str],
        index: Optional[str] = None
    ) -> str:
        """Format sourcetypes list response."""
        formatted = {
            "type": "sourcetypes_list",
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "total_sourcetypes": len(sourcetypes),
            "sourcetypes": sourcetypes
        }
        
        if index:
            formatted["index"] = index
            formatted["message"] = f"Found {len(sourcetypes)} sourcetypes in index '{index}'"
        else:
            formatted["message"] = f"Found {len(sourcetypes)} sourcetypes"
        
        return json.dumps(formatted, indent=2)
    
    def format_environment_index_response(self, environment: str, index: str) -> str:
        """Format environment-specific index response."""
        formatted = {
            "type": "environment_index",
            "status": "success",
            "environment": environment,
            "timestamp": datetime.now().isoformat(),
            "index": index,
            "message": f"Index for {environment.upper()} environment: {index}"
        }
        
        return json.dumps(formatted, indent=2)


# Singleton instance
response_formatter = ResponseFormatter()

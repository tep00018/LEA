# src/mcp/mcp_server.py
"""
Enhanced MCP Server for LEA Tutor with Full Tool Integration
Unified server for all tool interactions via MCP protocol
"""
import asyncio
import json
from typing import Dict, Any, List
from src.mcp.tool_registry import MCPToolRegistry

class LEAMCPServer:
    """Enhanced MCP Server that handles all tool requests via unified protocol"""
    
    def __init__(self, redis_client=None):
        """Initialize MCP server with comprehensive tool registry"""
        try:
            self.tool_registry = MCPToolRegistry(redis_client)
            self.active_sessions = {}
            self.server_stats = {
                "requests_handled": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "tools_available": len(self.tool_registry.get_available_tools())
            }
            print(f"DEBUG: LEA MCP Server initialized with {self.server_stats['tools_available']} tools")
        except Exception as e:
            print(f"DEBUG: Failed to initialize MCP tool registry: {e}")
            self.tool_registry = None
            self.active_sessions = {}
            self.server_stats = {"error": "Failed to initialize"}
            raise e
    
    async def handle_tool_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle incoming tool requests via MCP protocol with enhanced error handling
        
        Expected request format:
        {
            "tool": "tool_name",
            "parameters": {...},
            "session_id": "optional_session_id",
            "request_id": "optional_request_id"
        }
        """
        self.server_stats["requests_handled"] += 1
        
        try:
            if not self.tool_registry:
                self.server_stats["failed_requests"] += 1
                return {
                    "success": False,
                    "error": "Tool registry not available",
                    "server_status": "registry_unavailable"
                }
                
            tool_name = request.get("tool")
            parameters = request.get("parameters", {})
            session_id = request.get("session_id")
            request_id = request.get("request_id")
            
            if not tool_name:
                self.server_stats["failed_requests"] += 1
                return {
                    "success": False,
                    "error": "Tool name is required",
                    "available_tools": self.tool_registry.get_available_tools(),
                    "request_id": request_id
                }
            
            print(f"DEBUG: MCP Server handling request for tool: {tool_name}")
            
            # Execute the tool with enhanced logging
            start_time = asyncio.get_event_loop().time()
            result = await self.tool_registry.execute_tool(tool_name, parameters)
            execution_time = asyncio.get_event_loop().time() - start_time
            
            # Add execution metadata to the result
            if isinstance(result, dict):
                result["execution_time"] = round(execution_time, 3)
                result["request_id"] = request_id
                result["server_timestamp"] = asyncio.get_event_loop().time()
            
            # Track success/failure
            if result.get("success", False):
                self.server_stats["successful_requests"] += 1
            else:
                self.server_stats["failed_requests"] += 1
            
            # Add session tracking if provided
            if session_id:
                if session_id not in self.active_sessions:
                    self.active_sessions[session_id] = []
                
                self.active_sessions[session_id].append({
                    "tool": tool_name,
                    "parameters": parameters,
                    "result": result,
                    "timestamp": asyncio.get_event_loop().time(),
                    "execution_time": execution_time,
                    "request_id": request_id
                })
                
                # Keep only last 10 requests per session to prevent memory bloat
                if len(self.active_sessions[session_id]) > 10:
                    self.active_sessions[session_id] = self.active_sessions[session_id][-10:]
            
            return result
            
        except Exception as e:
            self.server_stats["failed_requests"] += 1
            print(f"DEBUG: MCP Server error: {e}")
            return {
                "success": False,
                "error": f"MCP Server error: {str(e)}",
                "request_id": request.get("request_id"),
                "server_timestamp": asyncio.get_event_loop().time()
            }
    
    async def handle_batch_request(self, requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Handle multiple tool requests in parallel with improved error handling"""
        print(f"DEBUG: MCP Server handling batch request with {len(requests)} tools")
        
        if not self.tool_registry:
            error_response = {
                "success": False,
                "error": "Tool registry not available",
                "server_status": "registry_unavailable"
            }
            return [error_response for _ in requests]
        
        # Execute all requests in parallel with timeout protection
        try:
            tasks = [
                asyncio.wait_for(self.handle_tool_request(request), timeout=60.0)
                for request in requests
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.TimeoutError:
            return [{
                "success": False,
                "error": "Batch request timed out",
                "timeout": 60.0
            } for _ in requests]
        
        # Handle any exceptions in the batch
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "success": False,
                    "error": f"Tool execution failed: {str(result)}",
                    "request_index": i,
                    "batch_error": True
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    def get_available_tools(self) -> Dict[str, Any]:
        """Get comprehensive information about all available tools"""
        if not self.tool_registry:
            return {
                "tools": [],
                "schemas": {},
                "total_tools": 0,
                "error": "Tool registry not available",
                "server_stats": self.server_stats
            }
            
        return {
            "tools": self.tool_registry.get_available_tools(),
            "schemas": self.tool_registry.get_tool_schemas(),
            "total_tools": len(self.tool_registry.tools),
            "server_stats": self.server_stats,
            "rag_courses": self.tool_registry.get_rag_courses(),
            "capabilities": {
                "web_search": "web_search" in self.tool_registry.tools,
                "youtube_search": "youtube_worked_examples" in self.tool_registry.tools,
                "rag_retrieval": "rag_retrieval" in self.tool_registry.tools,
                "academic_calendar": "academic_calendar" in self.tool_registry.tools,
                "weather_services": "uk_weather_forecast" in self.tool_registry.tools,
                "kc_models": "kc_model_lookup" in self.tool_registry.tools
            }
        }
    
    async def get_tool_info(self, tool_name: str) -> Dict[str, Any]:
        """Get detailed information about a specific tool"""
        if not self.tool_registry:
            return {"error": "Tool registry not available"}
        
        return await self.tool_registry.get_tool_info(tool_name)
    
    def get_session_history(self, session_id: str) -> Dict[str, Any]:
        """Get the request history for a specific session"""
        if session_id not in self.active_sessions:
            return {
                "session_id": session_id,
                "exists": False,
                "message": "Session not found or no requests made"
            }
        
        return {
            "session_id": session_id,
            "exists": True,
            "request_count": len(self.active_sessions[session_id]),
            "requests": self.active_sessions[session_id]
        }
    
    def get_server_stats(self) -> Dict[str, Any]:
        """Get comprehensive server statistics"""
        stats = self.server_stats.copy()
        stats.update({
            "active_sessions": len(self.active_sessions),
            "uptime_requests": stats["requests_handled"],
            "success_rate": round(
                (stats["successful_requests"] / max(stats["requests_handled"], 1)) * 100, 2
            ),
            "tools_registered": len(self.tool_registry.tools) if self.tool_registry else 0
        })
        return stats
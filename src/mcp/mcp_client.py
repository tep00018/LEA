# src/mcp/mcp_client.py
"""
MCP Client for LEA Agent Orchestrator
Handles all tool requests via MCP protocol instead of direct connections
"""

import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

class LEAMCPClient:
    """
    MCP Client that Agent Orchestrator uses to access all tools
    Replaces direct RAG, KC Model, and Mastery Tracker connections
    """
    
    def __init__(self, mcp_server):
        """Initialize with reference to MCP server"""
        self.mcp_server = mcp_server
        self.client_id = f"orchestrator_client_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"DEBUG: MCP Client initialized with ID: {self.client_id}")
    
    async def get_course_content_via_rag(
        self, 
        query: str, 
        course: str, 
        max_results: int = 3
    ) -> Dict[str, Any]:
        """Get course content via MCP RAG tool"""
        try:
            request = {
                "tool": "rag_retrieval",
                "parameters": {
                    "query": query,
                    "course": course,
                    "max_results": max_results,
                    "use_reranking": True
                },
                "session_id": self.client_id,
                "request_id": f"rag_{datetime.now().strftime('%H%M%S')}"
            }
            
            print(f"DEBUG: MCP Client requesting RAG for query: '{query}' in course: {course}")
            result = await self.mcp_server.handle_tool_request(request)
            
            if result.get("success", False):
                print(f"DEBUG: RAG via MCP successful - {result.get('num_results', 0)} results")
                return {
                    "success": True,
                    "content": self._format_rag_content(result.get("results", [])),
                    "num_results": result.get("num_results", 0),
                    "course": course
                }
            else:
                print(f"DEBUG: RAG via MCP failed: {result.get('error', 'Unknown error')}")
                return {"success": False, "error": result.get("error", "RAG request failed")}
                
        except Exception as e:
            print(f"ERROR: MCP RAG request failed: {e}")
            return {"success": False, "error": f"MCP RAG error: {str(e)}"}
    
    def _format_rag_content(self, results: List[Dict]) -> str:
        """Format RAG results into content for LLM"""
        if not results:
            return "No relevant course content found."
        
        content_pieces = []
        for i, result in enumerate(results, 1):
            content = result.get("content", "")
            metadata = result.get("metadata", {})
            
            # Create a formatted content piece
            piece = f"Content {i}:\n{content[:800]}..."
            if metadata.get("source"):
                piece += f"\n(Source: {metadata['source']})"
            
            content_pieces.append(piece)
        
        return "\n\n".join(content_pieces)
    
    async def get_kc_model_data(
        self, 
        course: str, 
        component_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get KC model data via MCP"""
        try:
            request = {
                "tool": "kc_model_lookup",
                "parameters": {
                    "module": course,
                    "component": component_id
                },
                "session_id": self.client_id,
                "request_id": f"kc_{datetime.now().strftime('%H%M%S')}"
            }
            
            print(f"DEBUG: MCP Client requesting KC model for course: {course}")
            result = await self.mcp_server.handle_tool_request(request)
            
            if result.get("success", False):
                print(f"DEBUG: KC model via MCP successful")
                return {
                    "success": True,
                    "kc_model": result.get("kc_model", {}),
                    "component_data": result.get("component_data"),
                    "summary": result.get("summary", "")
                }
            else:
                print(f"DEBUG: KC model via MCP failed: {result.get('error', 'Unknown error')}")
                return {"success": False, "error": result.get("error", "KC model request failed")}
                
        except Exception as e:
            print(f"ERROR: MCP KC model request failed: {e}")
            return {"success": False, "error": f"MCP KC model error: {str(e)}"}
    
    async def update_mastery(
        self,
        username: str,
        course_code: str,
        interaction_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update mastery via MCP mastery service"""
        try:
            request = {
                "tool": "mastery_update",
                "parameters": {
                    "username": username,
                    "course_code": course_code,
                    "interaction_data": interaction_data
                },
                "session_id": self.client_id,
                "request_id": f"mastery_{datetime.now().strftime('%H%M%S')}"
            }
            
            print(f"DEBUG: MCP Client updating mastery for {username}")
            result = await self.mcp_server.handle_tool_request(request)
            
            if result.get("success", False):
                print(f"DEBUG: Mastery update via MCP successful")
                return result
            else:
                print(f"DEBUG: Mastery update via MCP failed: {result.get('error', 'Unknown error')}")
                return {"success": False, "error": result.get("error", "Mastery update failed")}
                
        except Exception as e:
            print(f"ERROR: MCP mastery update failed: {e}")
            return {"success": False, "error": f"MCP mastery error: {str(e)}"}
    
    async def get_mastery_summary(
        self,
        username: str,
        course_code: str
    ) -> Dict[str, Any]:
        """Get mastery summary via MCP"""
        try:
            request = {
                "tool": "mastery_summary",
                "parameters": {
                    "username": username,
                    "course_code": course_code
                },
                "session_id": self.client_id,
                "request_id": f"mastery_get_{datetime.now().strftime('%H%M%S')}"
            }
            
            result = await self.mcp_server.handle_tool_request(request)
            
            if result.get("success", False):
                return result
            else:
                return {"success": False, "error": result.get("error", "Failed to get mastery")}
                
        except Exception as e:
            print(f"ERROR: MCP get mastery failed: {e}")
            return {"success": False, "error": f"MCP mastery get error: {str(e)}"}
    
    async def batch_request(self, requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Make multiple MCP requests in parallel"""
        try:
            # Add session info to all requests
            for request in requests:
                request["session_id"] = self.client_id
                if "request_id" not in request:
                    request["request_id"] = f"batch_{datetime.now().strftime('%H%M%S')}"
            
            print(f"DEBUG: MCP Client making batch request with {len(requests)} tools")
            results = await self.mcp_server.handle_batch_request(requests)
            
            print(f"DEBUG: Batch request completed - {len(results)} results")
            return results
            
        except Exception as e:
            print(f"ERROR: MCP batch request failed: {e}")
            return [{"success": False, "error": f"Batch request error: {str(e)}"}] * len(requests)
    
    def get_available_tools(self) -> Dict[str, Any]:
        """Get available MCP tools"""
        return self.mcp_server.get_available_tools()
    
    async def health_check(self) -> Dict[str, Any]:
        """Check MCP server health"""
        try:
            tools_info = self.get_available_tools()
            return {
                "success": True,
                "server_available": True,
                "tools_count": tools_info.get("total_tools", 0),
                "capabilities": tools_info.get("capabilities", {}),
                "client_id": self.client_id
            }
        except Exception as e:
            return {
                "success": False,
                "server_available": False,
                "error": str(e),
                "client_id": self.client_id
            }
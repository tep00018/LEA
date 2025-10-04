# src/storage/memory_schemas.py
"""
Memory Management Schemas for LEA
Handles short-term and long-term memory organization
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import json

class MemorySchemas:
    """
    Schema definitions for memory management in Redis
    """
    
    # Key patterns
    @staticmethod
    def get_short_term_key(username: str, session_id: str) -> str:
        """Key for short-term session memory"""
        return f"memory:short:{username}:{session_id}"
    
    @staticmethod
    def get_long_term_key(username: str, course: str = None) -> str:
        """Key for consolidated long-term memory"""
        if course:
            return f"memory:long:{username}:{course}"
        return f"memory:long:{username}:general"
    
    @staticmethod
    def get_consolidation_queue_key() -> str:
        """Key for memory consolidation queue"""
        return "memory:consolidation:queue"
    
    @staticmethod
    def get_active_session_key(username: str) -> str:
        """Key for tracking active session"""
        return f"memory:session:active:{username}"
    
    @staticmethod
    def get_memory_index_key(username: str) -> str:
        """Key for memory search index"""
        return f"memory:index:{username}"
    
    # Memory entry structures
    @staticmethod
    def create_short_term_entry(
        interaction_type: str,
        content: Dict[str, Any],
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create a structured short-term memory entry"""
        return {
            "timestamp": datetime.now().isoformat(),
            "type": interaction_type,  # 'chat', 'quiz', 'tutorial', 'feedback'
            "content": content,
            "metadata": metadata or {},
            "processed": False
        }
    
    @staticmethod
    def create_long_term_entry(
        session_id: str,
        summary: str,
        key_concepts: List[str],
        learning_patterns: Dict[str, Any],
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create a structured long-term memory entry"""
        return {
            "session_id": session_id,
            "consolidated_at": datetime.now().isoformat(),
            "summary": summary,
            "key_concepts": key_concepts,
            "learning_patterns": learning_patterns,
            "metadata": metadata or {},
            "retrieval_count": 0
        }
    
    @staticmethod
    def create_consolidation_task(
        username: str,
        session_id: str,
        priority: int = 1
    ) -> Dict[str, Any]:
        """Create a consolidation queue task"""
        return {
            "username": username,
            "session_id": session_id,
            "queued_at": datetime.now().isoformat(),
            "priority": priority,  # 1=normal, 2=high, 3=urgent
            "attempts": 0
        }
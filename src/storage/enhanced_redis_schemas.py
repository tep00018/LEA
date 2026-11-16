# File: src/storage/enhanced_redis_schemas.py
"""
Enhanced Redis Schemas for LEA Pedagogical Tracking
Extends the existing Redis client with educational metrics
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import json

class LEAPedagogicalSchemas:
    """
    Schema definitions and methods for pedagogical data in Redis
    
    This class defines how we store and retrieve learning-related metrics
    including cognitive load, engagement, mastery, and scaffolding data.
    """
    
    @staticmethod
    def get_cognitive_load_key(username: str, session_id: str = None) -> str:
        """Generate key for cognitive load data"""
        if session_id:
            return f"cognitive_load:{username}:{session_id}"
        return f"cognitive_load:{username}:current"
    
    @staticmethod
    def get_engagement_key(username: str, course: str) -> str:
        """Generate key for engagement tracking"""
        return f"engagement:{username}:{course}"
    
    @staticmethod
    def get_mastery_key(username: str, course: str) -> str:
        """Generate key for detailed mastery tracking"""
        return f"mastery:{username}:{course}"
    
    @staticmethod
    def get_scaffolding_key(username: str, course: str) -> str:
        """Generate key for scaffolding history"""
        return f"scaffolding:{username}:{course}"
    
    @staticmethod
    def create_cognitive_load_entry() -> Dict[str, Any]:
        """
        Create a cognitive load tracking entry structure
        
        Based on requirement 2.1.1b: Dynamic Cognitive Load Assessment
        Tracks: response accuracy, solution time, help-seeking patterns, self-report
        """
        return {
            "baseline": {
                "response_time_avg": None,  # Average response time in seconds
                "accuracy_rate": None,       # Baseline accuracy (0.0-1.0)
                "established_at": None,      # When baseline was established
                "sample_size": 0            # Number of interactions used
            },
            "current": {
                "load_level": 0.5,          # Current load (0.0-1.0, 0.5 is moderate)
                "response_time": None,       # Last response time
                "accuracy_trend": [],        # Recent accuracy values
                "help_requests": 0,          # Help requests this session
                "self_report": None,         # Paas scale rating (1-9)
                "timestamp": datetime.now().isoformat()
            },
            "indicators": {
                "struggling_pattern": False,  # Detected struggling behavior
                "optimal_challenge": True,    # In the "flow" zone
                "overloaded": False          # Cognitive overload detected
            }
        }
    
    @staticmethod
    def create_mastery_entry(course: str, objectives: List[Dict]) -> Dict[str, Any]:
        """
        Create a detailed mastery tracking structure
        
        Based on requirement 2.1.2b: Mastery Estimation Algorithm
        Tracks mastery at concept, LO, week, and course levels
        """
        mastery_structure = {
            "course_level": {
                "overall_mastery": 0.0,
                "last_updated": datetime.now().isoformat()
            },
            "week_level": {},  # Will be populated dynamically
            "learning_objectives": {},  # Detailed LO tracking
            "knowledge_components": {}  # Granular skill tracking
        }
        
        # Initialize from course objectives (KC model)
        for objective in objectives:
            week = objective.get("week", 1)
            lo_id = f"week{week}_lo{objective.get('id', 1)}"
            
            # Initialize week level if not exists
            if f"week_{week}" not in mastery_structure["week_level"]:
                mastery_structure["week_level"][f"week_{week}"] = {
                    "mastery": 0.0,
                    "objectives_completed": 0,
                    "total_objectives": 0
                }
            
            # Add learning objective
            mastery_structure["learning_objectives"][lo_id] = {
                "title": objective.get("title", ""),
                "mastery": 0.0,
                "attempts": 0,
                "last_attempt": None,
                "difficulty": objective.get("difficulty_level", 3)
            }
            
            # Add knowledge components (granular skills)
            for skill in objective.get("granular_skills", []):
                mastery_structure["knowledge_components"][skill] = {
                    "mastery": 0.0,
                    "exposures": 0,
                    "correct_applications": 0,
                    "last_seen": None
                }
        
        return mastery_structure
    
    @staticmethod
    def create_engagement_entry() -> Dict[str, Any]:
        """
        Create engagement tracking structure
        
        Based on requirements 2.1.3e and 2.1.4f
        Tracks both behavioral and emotional engagement
        """
        return {
            "behavioral": {
                "session_count": 0,
                "avg_session_duration": 0,
                "interaction_frequency": 0,  # Messages per session
                "feature_usage": {
                    "tutor_me": 0,
                    "quiz_me": 0,
                    "examples_requested": 0,
                    "help_requested": 0
                }
            },
            "emotional": {
                "sentiment_scores": [],      # Track sentiment over time
                "frustration_events": 0,
                "celebration_events": 0,
                "current_state": "neutral"   # Current emotional state
            },
            "motivational": {
                "streak_days": 0,
                "goals_completed": 0,
                "self_efficacy_trend": [],   # Self-reported confidence
                "persistence_score": 0.5     # Tendency to retry after failure
            },
            "flow_states": {
                "optimal_challenge_time": 0, # Time in flow state (minutes)
                "too_easy_time": 0,
                "too_hard_time": 0,
                "last_flow_state": None
            }
        }
    
    @staticmethod
    def create_scaffolding_entry() -> Dict[str, Any]:
        """
        Create scaffolding history structure
        
        Based on requirement 2.2a-f
        Tracks scaffolding type, timing, and effectiveness
        """
        return {
            "history": [],  # List of scaffolding events
            "preferences": {
                "preferred_types": [],       # Which scaffolding works best
                "optimal_timing": "immediate", # When to provide scaffolding
                "fading_rate": "moderate"    # How quickly to reduce support
            },
            "effectiveness": {
                "conceptual": {"success_rate": 0.0, "usage_count": 0},
                "procedural": {"success_rate": 0.0, "usage_count": 0},
                "strategic": {"success_rate": 0.0, "usage_count": 0},
                "metacognitive": {"success_rate": 0.0, "usage_count": 0}
            }
        }
# File: src/tutor/tutor_state.py
"""
Tutor State Management for LEA Tutor System
Handles session persistence, progress tracking, and mastery calculations
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

class ScaffoldingLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium" 
    LOW = "low"

class SessionStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"

@dataclass
class InteractionRecord:
    """Records a single student-tutor interaction"""
    timestamp: str
    go_id: str
    student_input: str
    tutor_response: str
    response_quality: float  # 0.0 to 1.0
    scaffolding_level: str
    is_correct: bool
    time_to_respond: Optional[float] = None  # seconds

@dataclass 
class GOProgress:
    """Tracks progress on a single Granular Objective"""
    go_id: str
    skill_name: str
    mastery_level: float  # 0.0 to 1.0
    interaction_count: int
    correct_count: int
    last_interaction: str
    time_spent: float  # seconds
    scaffolding_history: List[str]
    difficulty_level: float  # 0.0 to 1.0, adapts based on performance

    def update_mastery(self, is_correct: bool, response_quality: float):
        """Update mastery level based on new interaction"""
        self.interaction_count += 1
        if is_correct:
            self.correct_count += 1
        
        # Weighted moving average of mastery
        weight = 0.3  # How much new evidence counts
        self.mastery_level = (1 - weight) * self.mastery_level + weight * response_quality
        self.last_interaction = datetime.now().isoformat()
    
    def get_accuracy(self) -> float:
        """Get current accuracy rate"""
        if self.interaction_count == 0:
            return 0.0
        return self.correct_count / self.interaction_count

class TutorStateManager:
    """Manages tutoring session state and progress tracking - FIXED: LEARedisClient compatibility"""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        
        # FIXED: Handle LEARedisClient compatibility like KC model loader
        self._is_lea_redis = hasattr(redis_client, 'redis_client') if redis_client else False
        if self._is_lea_redis and redis_client:
            # LEARedisClient - use the underlying Redis client
            self._cache_client = redis_client.redis_client if hasattr(redis_client, 'redis_client') else redis_client
        else:
            # Standard Redis client
            self._cache_client = redis_client
        
        self.session_timeout = 30  # minutes
        print(f"DEBUG: TutorStateManager initialized - Redis client type: {'LEARedisClient' if self._is_lea_redis else 'Standard Redis'}")
    
    def create_session(self, username: str, course: str, week: int, go_list: List[Dict]) -> str:
        """Create a new tutoring session - FIXED: Redis compatibility"""
        session_id = f"tutor_{username}_{course}_w{week}_{uuid.uuid4().hex[:8]}"
        
        # Initialize GO progress tracking
        go_progress = {}
        for go_data in go_list:
            go_progress[go_data['go_id']] = GOProgress(
                go_id=go_data['go_id'],
                skill_name=go_data['skill_name'],
                mastery_level=0.0,
                interaction_count=0,
                correct_count=0,
                last_interaction="",
                time_spent=0.0,
                scaffolding_history=[ScaffoldingLevel.MEDIUM.value],
                difficulty_level=0.5
            )
        
        session_data = {
            "session_id": session_id,
            "username": username,
            "course": course,
            "week": week,
            "status": SessionStatus.ACTIVE.value,
            "current_go_index": 0,
            "go_list": go_list,
            "go_progress": {k: asdict(v) for k, v in go_progress.items()},
            "scaffolding_level": ScaffoldingLevel.MEDIUM.value,
            "interaction_history": [],
            "session_stats": {
                "start_time": datetime.now().isoformat(),
                "total_interactions": 0,
                "total_correct": 0,
                "total_time_seconds": 0,
                "scaffolding_adjustments": 0
            },
            "learning_preferences": {
                "preferred_scaffolding": ScaffoldingLevel.MEDIUM.value,
                "response_time_avg": 0.0,
                "needs_more_examples": False,
                "learns_from_mistakes": True
            }
        }
        
        # Store in Redis if available - FIXED: Use proper cache client
        if self._cache_client:
            try:
                if hasattr(self._cache_client, 'setex'):
                    self._cache_client.setex(
                        f"tutor_session:{session_id}",
                        self.session_timeout * 60,
                        json.dumps(session_data)
                    )
                    print(f"DEBUG: Session {session_id} stored in Redis successfully")
                else:
                    print("DEBUG: Redis client does not support setex, session stored in memory only")
            except Exception as e:
                print(f"Warning: Could not store session in Redis: {e}")
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Retrieve session data - FIXED: Redis compatibility"""
        if self._cache_client:
            try:
                if hasattr(self._cache_client, 'get'):
                    session_data = self._cache_client.get(f"tutor_session:{session_id}")
                    if session_data:
                        return json.loads(session_data)
            except Exception as e:
                print(f"Warning: Could not retrieve session from Redis: {e}")
        
        return None
    
    def update_session(self, session_id: str, session_data: Dict) -> bool:
        """Update session data - FIXED: Redis compatibility"""
        if self._cache_client:
            try:
                if hasattr(self._cache_client, 'setex'):
                    self._cache_client.setex(
                        f"tutor_session:{session_id}",
                        self.session_timeout * 60,
                        json.dumps(session_data)
                    )
                    return True
            except Exception as e:
                print(f"Warning: Could not update session in Redis: {e}")
        
        return False
    
    def record_interaction(self, session_data: Dict, go_id: str, student_input: str, 
                          tutor_response: str, response_quality: float, 
                          scaffolding_level: str, response_time: float = None) -> Dict:
        """Record a student-tutor interaction and update progress"""
        
        is_correct = response_quality > 0.7
        
        # Create interaction record
        interaction = InteractionRecord(
            timestamp=datetime.now().isoformat(),
            go_id=go_id,
            student_input=student_input,
            tutor_response=tutor_response,
            response_quality=response_quality,
            scaffolding_level=scaffolding_level,
            is_correct=is_correct,
            time_to_respond=response_time
        )
        
        # Add to interaction history
        session_data["interaction_history"].append(asdict(interaction))
        
        # Update GO progress
        if go_id in session_data["go_progress"]:
            go_progress = GOProgress(**session_data["go_progress"][go_id])
            go_progress.update_mastery(is_correct, response_quality)
            
            if response_time:
                go_progress.time_spent += response_time
            
            session_data["go_progress"][go_id] = asdict(go_progress)
        
        # Update session stats
        stats = session_data["session_stats"]
        stats["total_interactions"] += 1
        if is_correct:
            stats["total_correct"] += 1
        
        if response_time:
            # Update average response time
            if stats["total_interactions"] > 1:
                current_avg = session_data["learning_preferences"]["response_time_avg"]
                new_avg = (current_avg * (stats["total_interactions"] - 1) + response_time) / stats["total_interactions"]
                session_data["learning_preferences"]["response_time_avg"] = new_avg
            else:
                session_data["learning_preferences"]["response_time_avg"] = response_time
        
        return session_data
    
    def calculate_scaffolding_level(self, session_data: Dict, current_go_id: str) -> str:
        """Calculate appropriate scaffolding level based on performance patterns"""
        
        # Get recent performance (last 3 interactions)
        recent_interactions = session_data["interaction_history"][-3:]
        current_go_interactions = [i for i in recent_interactions if i["go_id"] == current_go_id]
        
        # If no interactions yet, start with medium
        if not current_go_interactions:
            return ScaffoldingLevel.MEDIUM.value
        
        # Calculate recent accuracy
        recent_correct = sum(1 for i in current_go_interactions if i["is_correct"])
        recent_accuracy = recent_correct / len(current_go_interactions)
        
        # Get current GO progress
        go_progress = session_data["go_progress"].get(current_go_id)
        if not go_progress:
            return ScaffoldingLevel.MEDIUM.value
        
        overall_accuracy = go_progress["correct_count"] / max(go_progress["interaction_count"], 1)
        
        # Decision logic for scaffolding
        consecutive_correct = self._get_consecutive_correct(session_data, current_go_id)
        consecutive_incorrect = self._get_consecutive_incorrect(session_data, current_go_id)
        
        # Fading logic: reduce scaffolding if performing well
        if consecutive_correct >= 3 or (overall_accuracy > 0.8 and recent_accuracy > 0.7):
            new_level = ScaffoldingLevel.LOW.value
        # Increase scaffolding if struggling
        elif consecutive_incorrect >= 2 or (overall_accuracy < 0.4 and recent_accuracy < 0.5):
            new_level = ScaffoldingLevel.HIGH.value
        else:
            new_level = ScaffoldingLevel.MEDIUM.value
        
        # Update scaffolding history
        current_level = session_data.get("scaffolding_level", ScaffoldingLevel.MEDIUM.value)
        if new_level != current_level:
            go_progress["scaffolding_history"].append(new_level)
            session_data["session_stats"]["scaffolding_adjustments"] += 1
        
        return new_level
    
    def _get_consecutive_correct(self, session_data: Dict, go_id: str) -> int:
        """Get count of consecutive correct answers for a GO"""
        consecutive = 0
        interactions = reversed(session_data["interaction_history"])
        
        for interaction in interactions:
            if interaction["go_id"] == go_id:
                if interaction["is_correct"]:
                    consecutive += 1
                else:
                    break
            
        return consecutive
    
    def _get_consecutive_incorrect(self, session_data: Dict, go_id: str) -> int:
        """Get count of consecutive incorrect answers for a GO"""
        consecutive = 0
        interactions = reversed(session_data["interaction_history"])
        
        for interaction in interactions:
            if interaction["go_id"] == go_id:
                if not interaction["is_correct"]:
                    consecutive += 1
                else:
                    break
        
        return consecutive
    
    def check_go_mastery(self, session_data: Dict, go_id: str, mastery_threshold: float = 0.8) -> bool:
        """Check if a GO has been mastered"""
        go_progress = session_data["go_progress"].get(go_id)
        if not go_progress:
            return False
        
        return (go_progress["mastery_level"] >= mastery_threshold and 
                go_progress["interaction_count"] >= 2)
    
    def get_next_go(self, session_data: Dict) -> Optional[Dict]:
        """Get the next GO to work on"""
        current_index = session_data["current_go_index"]
        go_list = session_data["go_list"]
        
        # Check if current GO is mastered
        if current_index < len(go_list):
            current_go = go_list[current_index]
            if self.check_go_mastery(session_data, current_go["go_id"]):
                # Move to next GO
                session_data["current_go_index"] += 1
                current_index += 1
        
        # Return next GO if available
        if current_index < len(go_list):
            return go_list[current_index]
        
        return None
    
    def calculate_session_progress(self, session_data: Dict) -> Dict:
        """Calculate overall session progress"""
        go_list = session_data["go_list"]
        go_progress = session_data["go_progress"]
        
        total_gos = len(go_list)
        mastered_gos = sum(1 for go in go_list if self.check_go_mastery(session_data, go["go_id"]))
        
        # Calculate weighted progress (mastery + current GO progress)
        total_mastery = sum(progress["mastery_level"] for progress in go_progress.values())
        weighted_progress = total_mastery / total_gos if total_gos > 0 else 0
        
        stats = session_data["session_stats"]
        accuracy = stats["total_correct"] / max(stats["total_interactions"], 1)
        
        return {
            "completion_percent": (mastered_gos / total_gos * 100) if total_gos > 0 else 0,
            "weighted_progress": weighted_progress * 100,
            "gos_mastered": mastered_gos,
            "total_gos": total_gos,
            "overall_accuracy": accuracy,
            "interactions": stats["total_interactions"],
            "time_spent_minutes": stats.get("total_time_seconds", 0) / 60,
            "scaffolding_adjustments": stats.get("scaffolding_adjustments", 0)
        }
    
    def is_session_complete(self, session_data: Dict) -> bool:
        """Check if tutoring session is complete"""
        go_list = session_data["go_list"]
        return all(self.check_go_mastery(session_data, go["go_id"]) for go in go_list)
    
    def generate_session_summary(self, session_data: Dict) -> Dict:
        """Generate a comprehensive session summary"""
        progress = self.calculate_session_progress(session_data)
        
        # Analyze learning patterns
        scaffolding_changes = session_data["session_stats"].get("scaffolding_adjustments", 0)
        start_time = datetime.fromisoformat(session_data["session_stats"]["start_time"])
        duration = datetime.now() - start_time
        
        # Identify strengths and areas for improvement
        go_performances = []
        for go_data in session_data["go_list"]:
            go_id = go_data["go_id"]
            go_progress = session_data["go_progress"].get(go_id, {})
            
            go_performances.append({
                "skill_name": go_data["skill_name"],
                "mastery_level": go_progress.get("mastery_level", 0),
                "accuracy": go_progress.get("correct_count", 0) / max(go_progress.get("interaction_count", 1), 1),
                "interactions": go_progress.get("interaction_count", 0)
            })
        
        # Sort by mastery for recommendations
        go_performances.sort(key=lambda x: x["mastery_level"])
        
        return {
            "session_id": session_data["session_id"],
            "duration_minutes": duration.seconds // 60,
            "completion_status": "complete" if self.is_session_complete(session_data) else "partial",
            "progress": progress,
            "learning_efficiency": {
                "interactions_per_go": progress["interactions"] / max(progress["total_gos"], 1),
                "scaffolding_adaptations": scaffolding_changes,
                "avg_response_time": session_data["learning_preferences"]["response_time_avg"]
            },
            "strengths": [go for go in go_performances if go["mastery_level"] > 0.8][-3:],  # Top 3
            "improvement_areas": [go for go in go_performances if go["mastery_level"] < 0.6][:3],  # Bottom 3
            "recommendations": self._generate_recommendations(session_data, go_performances)
        }
    
    def _generate_recommendations(self, session_data: Dict, go_performances: List[Dict]) -> List[str]:
        """Generate personalized learning recommendations"""
        recommendations = []
        
        # Based on overall accuracy
        overall_accuracy = session_data["session_stats"]["total_correct"] / max(session_data["session_stats"]["total_interactions"], 1)
        
        if overall_accuracy > 0.8:
            recommendations.append("Excellent work! You're ready for more advanced challenges.")
        elif overall_accuracy > 0.6:
            recommendations.append("Good progress! Focus on the concepts you found challenging.")
        else:
            recommendations.append("Consider reviewing the basics before moving to new topics.")
        
        # Based on scaffolding patterns
        scaffolding_adjustments = session_data["session_stats"].get("scaffolding_adjustments", 0)
        if scaffolding_adjustments > 3:
            recommendations.append("You adapted well to different levels of support - great flexibility!")
        
        # Based on specific GO performance
        weak_areas = [go["skill_name"] for go in go_performances if go["mastery_level"] < 0.5]
        if weak_areas:
            recommendations.append(f"Spend extra time on: {', '.join(weak_areas[:2])}")
        
        return recommendations


# Example usage and testing
if __name__ == "__main__":
    # Test without Redis
    state_manager = TutorStateManager()
    
    # Mock GO data
    go_list = [
        {"go_id": "GO_01", "skill_name": "Linear Regression", "description": "Basic regression"},
        {"go_id": "GO_02", "skill_name": "Model Evaluation", "description": "Evaluating models"}
    ]
    
    # Create session
    session_id = state_manager.create_session("test_user", "CMP511", 3, go_list)
    print(f"Created session: {session_id}")
    
    # Simulate some interactions
    session_data = {
        "session_id": session_id,
        "username": "test_user",
        "course": "CMP511", 
        "week": 3,
        "current_go_index": 0,
        "go_list": go_list,
        "go_progress": {
            "GO_01": {
                "go_id": "GO_01",
                "skill_name": "Linear Regression",
                "mastery_level": 0.0,
                "interaction_count": 0,
                "correct_count": 0,
                "last_interaction": "",
                "time_spent": 0.0,
                "scaffolding_history": ["medium"]
            }
        },
        "scaffolding_level": "medium",
        "interaction_history": [],
        "session_stats": {
            "start_time": datetime.now().isoformat(),
            "total_interactions": 0,
            "total_correct": 0,
            "scaffolding_adjustments": 0
        },
        "learning_preferences": {
            "response_time_avg": 0.0
        }
    }
    
    # Record some interactions
    session_data = state_manager.record_interaction(
        session_data, "GO_01", "Linear regression finds the best line", 
        "Great answer!", 0.9, "medium", 15.0
    )
    
    # Calculate new scaffolding level
    new_level = state_manager.calculate_scaffolding_level(session_data, "GO_01")
    print(f"New scaffolding level: {new_level}")
    
    # Check progress
    progress = state_manager.calculate_session_progress(session_data)
    print(f"Session progress: {progress}")
# File: src/core/go_strategy.py - FIXED VERSION
# Enhanced GO-Level Mastery Strategy for LEA
"""
Complete implementation of GO-based tutoring and quiz strategies
FIXED: Import issues and proper auth service handling
"""

import json
import time
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

class MasteryLevel(Enum):
    """GO mastery level thresholds"""
    NOT_STARTED = 0.0
    STRUGGLING = 0.3      # Below this = needs intensive support
    DEVELOPING = 0.5      # Basic understanding
    PROFICIENT = 0.7      # Good grasp
    MASTERED = 0.85       # Mastery achieved - can move on

@dataclass
class GOProgress:
    """Individual GO progress tracking"""
    go_id: str
    skill_name: str
    current_mastery: float
    attempts: int
    first_attempt: str
    last_attempt: str
    total_time_spent: int  # seconds
    consecutive_correct: int
    mastery_achieved: bool
    mastery_achieved_date: Optional[str] = None

class GOSequencer:
    """Manages GO progression and mastery strategy"""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.mastery_threshold = MasteryLevel.MASTERED.value
        self.repetition_intervals = [1, 3, 7, 14]  # days for spaced repetition
    
    def get_week_go_sequence(self, course: str, week: int) -> List[Dict[str, Any]]:
        """Get ordered list of GOs for a week - FIXED: Proper auth service handling"""
        try:
            # Import here to avoid circular imports
            from src.core.kc_model_loader import KCModelLoader
            
            # Use the redis_client passed in constructor instead of trying to get auth service
            if not self.redis_client:
                print("DEBUG: No Redis client available for KC Model loading")
                return []
            
            kc_loader = KCModelLoader(self.redis_client, module=course)
            week_content = kc_loader.get_week_content(course, week)
            
            go_sequence = []
            for lo in week_content.learning_objectives:
                for go in lo.granular_objectives:
                    go_sequence.append({
                        "go_id": go.go_id,
                        "skill_name": go.skill_name,
                        "description": go.description,
                        "lo_id": lo.lo_id,
                        "lo_title": getattr(lo, 'title', getattr(lo, 'objective_name', f"LO {lo.lo_id}")),  # FIXED
                        # "lo_title": lo.title,
                        "week": week,
                        "difficulty_estimate": self._estimate_go_difficulty(go),
                        "prerequisites": getattr(go, 'prerequisites', [])
                    })
            
            print(f"DEBUG: Successfully loaded {len(go_sequence)} GOs for {course} Week {week}")
            return go_sequence
            
        except Exception as e:
            print(f"DEBUG: Error loading GO sequence for {course} Week {week}: {e}")
            return []
    
    def _estimate_go_difficulty(self, go) -> float:
        """Estimate GO difficulty based on content analysis"""
        # Simple heuristic based on description complexity
        description = getattr(go, 'description', '')
        keywords = getattr(go, 'content_keywords', [])
        
        base_difficulty = 0.5
        
        # Complexity indicators
        complex_terms = ['algorithm', 'optimization', 'neural', 'deep', 'advanced', 'complex']
        if any(term in description.lower() for term in complex_terms):
            base_difficulty += 0.2
        
        # Length factor
        if len(description) > 200:
            base_difficulty += 0.1
        
        # Keyword density
        if len(keywords) > 5:
            base_difficulty += 0.1
        
        return min(0.9, base_difficulty)

class TutorSequencer:
    """Manages tutoring sequence and GO progression"""
    
    def __init__(self, go_sequencer: GOSequencer, redis_client=None):
        self.go_sequencer = go_sequencer
        self.redis_client = redis_client
    
    def get_next_tutor_go(self, username: str, course: str, week: int) -> Optional[Dict[str, Any]]:
        """Get next GO for tutoring based on mastery strategy"""
        
        # Get user's current GO progress
        user_progress = self._load_user_go_progress(username, course, week)
        
        # Get week's GO sequence
        go_sequence = self.go_sequencer.get_week_go_sequence(course, week)
        
        if not go_sequence:
            print(f"DEBUG: No GO sequence found for {course} Week {week}")
            return None
        
        print(f"DEBUG: Checking mastery for {len(go_sequence)} GOs for {username}")
        
        # Strategy: Find first unmastered GO
        for go_data in go_sequence:
            go_id = go_data["go_id"]
            
            if go_id not in user_progress or not user_progress[go_id].mastery_achieved:
                # Check prerequisites are met
                if self._prerequisites_met(go_data, user_progress):
                    current_mastery = user_progress.get(go_id, GOProgress(
                        go_id=go_id,
                        skill_name=go_data["skill_name"],
                        current_mastery=0.0,
                        attempts=0,
                        first_attempt="",
                        last_attempt="",
                        total_time_spent=0,
                        consecutive_correct=0,
                        mastery_achieved=False
                    )).current_mastery
                    
                    print(f"DEBUG: Next GO for tutoring: {go_data['skill_name']} (mastery: {current_mastery:.2f})")
                    
                    return {
                        **go_data,
                        "current_mastery": current_mastery,
                        "reason": "Next unmastered GO in sequence"
                    }
        
        # All GOs mastered - check for spaced repetition
        review_go = self._get_review_go(user_progress, go_sequence)
        if review_go:
            return {
                **review_go,
                "reason": "Spaced repetition review"
            }
        
        print(f"DEBUG: All GOs mastered for {course} Week {week}!")
        return None  # Week completed!
    
    def _prerequisites_met(self, go_data: Dict, user_progress: Dict[str, GOProgress]) -> bool:
        """Check if GO prerequisites are satisfied"""
        prerequisites = go_data.get("prerequisites", [])
        
        for prereq_id in prerequisites:
            if prereq_id not in user_progress or not user_progress[prereq_id].mastery_achieved:
                return False
        
        return True
    
    def _get_review_go(self, user_progress: Dict[str, GOProgress], go_sequence: List[Dict]) -> Optional[Dict]:
        """Get GO that needs spaced repetition review"""
        
        now = datetime.now()
        
        for go_data in go_sequence:
            go_id = go_data["go_id"]
            
            if go_id in user_progress and user_progress[go_id].mastery_achieved:
                progress = user_progress[go_id]
                
                if progress.mastery_achieved_date:
                    achieved_date = datetime.fromisoformat(progress.mastery_achieved_date)
                    days_since = (now - achieved_date).days
                    
                    # Check if it's time for review based on spaced repetition
                    for interval in self.repetition_intervals:
                        if days_since >= interval and days_since < interval + 2:  # 2-day window
                            return go_data
        
        return None
    
    def update_tutor_progress(self, username: str, course: str, week: int, go_id: str, 
                            interaction_result: Dict[str, Any]) -> GOProgress:
        """Update GO progress based on tutoring interaction"""
        
        user_progress = self._load_user_go_progress(username, course, week)
        
        if go_id not in user_progress:
            user_progress[go_id] = GOProgress(
                go_id=go_id,
                skill_name=interaction_result.get("skill_name", "Unknown"),
                current_mastery=0.0,
                attempts=0,
                first_attempt=datetime.now().isoformat(),
                last_attempt="",
                total_time_spent=0,
                consecutive_correct=0,
                mastery_achieved=False
            )
        
        progress = user_progress[go_id]
        
        # Update progress based on interaction
        is_correct = interaction_result.get("is_correct", False)
        new_mastery = interaction_result.get("mastery_estimate", progress.current_mastery)
        time_spent = interaction_result.get("time_spent", 30)  # seconds
        
        progress.attempts += 1
        progress.last_attempt = datetime.now().isoformat()
        progress.total_time_spent += time_spent
        progress.current_mastery = new_mastery
        
        if is_correct:
            progress.consecutive_correct += 1
        else:
            progress.consecutive_correct = 0
        
        # Check for mastery achievement
        if (progress.current_mastery >= self.go_sequencer.mastery_threshold and 
            progress.consecutive_correct >= 2 and 
            not progress.mastery_achieved):
            
            progress.mastery_achieved = True
            progress.mastery_achieved_date = datetime.now().isoformat()
            print(f"DEBUG: 🎉 GO {go_id} MASTERED by {username}!")
        
        # Save progress
        self._save_user_go_progress(username, course, week, user_progress)
        
        return progress
    
    def _load_user_go_progress(self, username: str, course: str, week: int) -> Dict[str, GOProgress]:
        """Load user's GO progress for a week"""
        try:
            if self.redis_client:
                key = f"go_progress:{username}:{course}:week_{week}"
                if hasattr(self.redis_client, 'get_redis'):
                    redis_conn = self.redis_client.get_redis()
                else:
                    redis_conn = self.redis_client
                    
                data = redis_conn.get(key)
                if data:
                    raw_data = json.loads(data)
                    return {
                        go_id: GOProgress(**go_data) 
                        for go_id, go_data in raw_data.items()
                    }
            
            # Fallback to file storage
            from pathlib import Path
            file_path = Path(f"./data/go_progress/go_progress_{username}_{course}_week_{week}.json")
            if file_path.exists():
                with open(file_path, 'r') as f:
                    raw_data = json.load(f)
                    return {
                        go_id: GOProgress(**go_data) 
                        for go_id, go_data in raw_data.items()
                    }
                    
        except Exception as e:
            print(f"DEBUG: Error loading GO progress for {username}: {e}")
        
        return {}
    
    def _save_user_go_progress(self, username: str, course: str, week: int, 
                              progress: Dict[str, GOProgress]):
        """Save user's GO progress using LEA Redis methods"""
        try:
            # Convert to serializable format
            serializable_data = {
                go_id: {
                    "go_id": p.go_id,
                    "skill_name": p.skill_name,
                    "current_mastery": p.current_mastery,
                    "attempts": p.attempts,
                    "first_attempt": p.first_attempt,
                    "last_attempt": p.last_attempt,
                    "total_time_spent": p.total_time_spent,
                    "consecutive_correct": p.consecutive_correct,
                    "mastery_achieved": p.mastery_achieved,
                    "mastery_achieved_date": p.mastery_achieved_date
                }
                for go_id, p in progress.items()
            }
            
            # 🔥 REAL-TIME: Use LEARedisClient methods
            if self.redis_client and hasattr(self.redis_client, 'update_go_progress'):
                # Your Redis client is actually LEARedisClient!
                success = self.redis_client.update_go_progress(username, course, week, serializable_data)
                if success:
                    print(f"DEBUG: ✅ GO progress saved via LEA Redis for {username}")
            else:
                # Fallback to direct Redis (your original code)
                json_data = json.dumps(serializable_data, indent=2)
                
                if hasattr(self.redis_client, 'get_redis'):
                    redis_conn = self.redis_client.get_redis()
                else:
                    redis_conn = self.redis_client
                    
                key = f"go_progress:{username}:{course}:week_{week}"
                redis_conn.setex(key, 86400 * 30, json_data)
                print(f"DEBUG: ✅ GO progress saved via direct Redis for {username}")
            
            # File backup (keep existing)
            from pathlib import Path
            backup_dir = Path("./data/go_progress")
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = backup_dir / f"go_progress_{username}_{course}_week_{week}.json"
            with open(file_path, 'w') as f:
                f.write(json.dumps(serializable_data, indent=2))
                
        except Exception as e:
            print(f"DEBUG: Error saving GO progress for {username}: {e}")

class QuizSequencer:
    """Manages quiz generation and GO-level scoring"""
    
    def __init__(self, go_sequencer: GOSequencer, redis_client=None):
        self.go_sequencer = go_sequencer
        self.redis_client = redis_client
    
    def generate_week_quiz(self, course: str, week: int, username: str) -> Dict[str, Any]:
        """Generate quiz with one question per GO"""
        
        go_sequence = self.go_sequencer.get_week_go_sequence(course, week)
        
        if not go_sequence:
            return {"error": "No GOs found for this week"}
        
        # Get user's previous quiz attempts to avoid repetition
        quiz_history = self._get_quiz_history(username, course, week)
        
        quiz_questions = []
        for go_data in go_sequence:
            question = self._generate_go_question(go_data, quiz_history)
            if question:
                quiz_questions.append(question)
        
        print(f"DEBUG: Generated quiz with {len(quiz_questions)} questions for {len(go_sequence)} GOs")
        
        return {
            "quiz_id": f"{course}_week_{week}_{username}_{int(time.time())}",
            "course": course,
            "week": week,
            "username": username,
            "questions": quiz_questions,
            "total_questions": len(quiz_questions),
            "go_coverage": [q["go_id"] for q in quiz_questions],
            "created_at": datetime.now().isoformat()
        }
    
    def _generate_go_question(self, go_data: Dict[str, Any], quiz_history: List[Dict]) -> Dict[str, Any]:
        """Generate a question specifically for this GO"""
        
        # Check if we've asked about this GO recently
        go_id = go_data["go_id"]
        recent_questions = [
            q for q in quiz_history 
            if q.get("go_id") == go_id and 
            (datetime.now() - datetime.fromisoformat(q.get("asked_at", "2020-01-01"))).days < 7
        ]
        
        # Determine question difficulty based on previous attempts
        if recent_questions:
            avg_score = sum(q.get("score", 0) for q in recent_questions) / len(recent_questions)
            if avg_score > 0.8:
                difficulty = "hard"
            elif avg_score > 0.5:
                difficulty = "medium"
            else:
                difficulty = "easy"
        else:
            difficulty = "medium"  # Default for first attempt
        
        return {
            "question_id": f"{go_id}_{int(time.time())}",
            "go_id": go_id,
            "skill_name": go_data["skill_name"],
            "lo_id": go_data["lo_id"],
            "difficulty": difficulty,
            "question_type": self._select_question_type(go_data, difficulty),
            "content": go_data["description"],
            "points": 1.0,  # Each GO worth 1 point
            "estimated_time": 90  # 90 seconds per question
        }
    
    def _select_question_type(self, go_data: Dict, difficulty: str) -> str:
        """Select appropriate question type based on GO and difficulty"""
        
        skill_name = go_data["skill_name"].lower()
        
        # Question type selection strategy
        if difficulty == "easy":
            if "definition" in skill_name or "concept" in skill_name:
                return "multiple_choice"
            else:
                return "true_false"
        
        elif difficulty == "medium":
            if "apply" in skill_name or "use" in skill_name:
                return "fill_in_blank"
            else:
                return "multiple_choice"
        
        else:  # hard
            if "analyze" in skill_name or "evaluate" in skill_name:
                return "open_ended"
            else:
                return "fill_in_blank"
    
    def score_quiz_by_go(self, quiz_results: List[Dict]) -> Dict[str, Any]:
        """Score quiz at GO level and aggregate up"""
        
        go_scores = {}
        lo_scores = {}
        total_score = 0
        total_possible = 0
        
        for result in quiz_results:
            go_id = result["go_id"]
            lo_id = result["lo_id"]
            score = result.get("score", 0.0)
            possible = result.get("points", 1.0)
            
            # GO level scoring
            go_scores[go_id] = {
                "score": score,
                "possible": possible,
                "percentage": (score / possible) * 100 if possible > 0 else 0,
                "mastery_contribution": score / possible if possible > 0 else 0
            }
            
            # LO level aggregation
            if lo_id not in lo_scores:
                lo_scores[lo_id] = {"score": 0, "possible": 0, "go_count": 0}
            
            lo_scores[lo_id]["score"] += score
            lo_scores[lo_id]["possible"] += possible
            lo_scores[lo_id]["go_count"] += 1
            
            total_score += score
            total_possible += possible
        
        # Calculate LO percentages
        for lo_id in lo_scores:
            lo_data = lo_scores[lo_id]
            lo_data["percentage"] = (lo_data["score"] / lo_data["possible"]) * 100 if lo_data["possible"] > 0 else 0
        
        return {
            "go_scores": go_scores,
            "lo_scores": lo_scores,
            "overall_score": total_score,
            "overall_possible": total_possible,
            "overall_percentage": (total_score / total_possible) * 100 if total_possible > 0 else 0,
            "gos_mastered": len([s for s in go_scores.values() if s["mastery_contribution"] >= 0.8]),
            "total_gos": len(go_scores)
        }
    
    def _get_quiz_history(self, username: str, course: str, week: int) -> List[Dict]:
        """Get user's quiz history for this week"""
        try:
            if self.redis_client:
                key = f"quiz_history:{username}:{course}:week_{week}"
                if hasattr(self.redis_client, 'get_redis'):
                    redis_conn = self.redis_client.get_redis()
                else:
                    redis_conn = self.redis_client
                    
                data = redis_conn.get(key)
                if data:
                    return json.loads(data)
            
            return []
            
        except Exception as e:
            print(f"DEBUG: Error loading quiz history: {e}")
            return []

class RepeatStrategy:
    """Strategy for handling repeats in tutoring and quizzing"""
    
    @staticmethod
    def handle_tutor_repeat(go_progress: GOProgress, attempt_number: int) -> Dict[str, Any]:
        """Determine strategy for repeated tutoring attempts"""
        
        if attempt_number <= 2:
            return {
                "approach": "reinforcement",
                "scaffolding": "medium",
                "hint_level": "minimal",
                "explanation": "Let's reinforce this concept with a different approach."
            }
        
        elif attempt_number <= 4:
            return {
                "approach": "scaffolded_breakdown",
                "scaffolding": "high",
                "hint_level": "substantial",
                "explanation": "Let's break this down into smaller steps."
            }
        
        else:
            return {
                "approach": "prerequisite_review",
                "scaffolding": "intensive",
                "hint_level": "guided",
                "explanation": "Let's review the foundation concepts first."
            }
    
    @staticmethod
    def handle_quiz_repeat(previous_attempts: List[Dict], go_mastery: float) -> Dict[str, Any]:
        """Determine strategy for repeated quiz attempts"""
        
        if len(previous_attempts) == 1:
            return {
                "difficulty_adjustment": "maintain",
                "question_type": "alternative_format",
                "explanation": "Let's try a different question format for this concept."
            }
        
        elif len(previous_attempts) == 2:
            if go_mastery < 0.5:
                return {
                    "difficulty_adjustment": "decrease",
                    "question_type": "simplified",
                    "explanation": "Let's focus on the core concept with a simpler question."
                }
            else:
                return {
                    "difficulty_adjustment": "maintain",
                    "question_type": "different_context",
                    "explanation": "Let's apply this concept in a different context."
                }
        
        else:  # 3+ attempts
            return {
                "difficulty_adjustment": "adaptive",
                "question_type": "prerequisite_check",
                "explanation": "Let's check understanding of the prerequisite concepts first."
            }
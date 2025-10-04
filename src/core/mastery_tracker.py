# FIXED VERSION of mastery_tracker.py
# Key fixes:
# 1. Fixed username handling in serialization/deserialization
# 2. Better error handling and fallbacks
# 3. Improved mastery calculation for quiz interactions
# 4. Enhanced real-time updates

import json
import time
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np
from openai import OpenAI

@dataclass
class MasteryLevel:
    """Simple mastery representation for individual concepts"""
    level: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0 (how confident we are in this assessment)
    last_updated: str
    interaction_count: int
    evidence_summary: str  # Brief description of why we think this mastery level

@dataclass
class LearnerMastery:
    """Complete mastery profile for a learner"""
    username: str
    course_code: str
    go_masteries: Dict[str, MasteryLevel]  # GO_ID -> MasteryLevel
    lo_masteries: Dict[str, MasteryLevel]  # LO_ID -> MasteryLevel  
    week_masteries: Dict[int, MasteryLevel]  # Week_num -> MasteryLevel
    last_session: str
    total_interactions: int

class MasteryTracker:
    """
    FIXED: Enhanced mastery tracking with proper username handling
    """

    def __init__(self, storage_backend="redis", redis_client=None):
        """Initialize mastery tracker with storage backend"""
        self.openai_client = OpenAI()  # Uses OPENAI_API_KEY environment variable
        self.storage_backend = storage_backend
        self.redis_client = redis_client
        
        # Always initialize storage_path
        self.storage_path = Path("./data/mastery_tracking")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Update storage backend if Redis not available
        if storage_backend == "file" or not redis_client:
            self.storage_backend = "file"
        
        print(f"DEBUG: MasteryTracker initialized with {self.storage_backend} storage")
    
    def get_mastery_summary(self, username: str, course_code: str = None) -> Dict[str, Any]:
        """
        FIXED: Get mastery summary with proper username handling
        """
        try:
            # Ensure we have a valid username
            if not username or username in ['', 'unknown_user', None]:
                print(f"WARNING: Invalid username '{username}', using default")
                username = "default_user"
            
            # Convert async call to sync using asyncio
            import asyncio
            
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is running, get cached data
                    return self._get_cached_mastery_sync(username, course_code)
                else:
                    # If loop not running, we can use run_until_complete
                    return loop.run_until_complete(self.get_mastery_summary_async(username, course_code))
            except RuntimeError:
                # No event loop, create new one
                return asyncio.run(self.get_mastery_summary_async(username, course_code))
                
        except Exception as e:
            print(f"DEBUG: Error in sync mastery summary for {username}: {e}")
            return self._get_default_mastery_summary(username, course_code)

    def _get_cached_mastery_sync(self, username: str, course_code: str) -> Dict[str, Any]:
        """FIXED: Get cached mastery data with proper username handling"""
        try:
            # Ensure username is valid
            if not username or username in ['', 'unknown_user', None]:
                username = "default_user"
            
            if self.storage_backend == "redis" and self.redis_client:
                key = f"mastery:{username}:{course_code or 'CMP511'}"
                
                # Handle different Redis client types
                if hasattr(self.redis_client, 'get_redis'):
                    redis_conn = self.redis_client.get_redis()
                else:
                    redis_conn = self.redis_client
                
                data = redis_conn.get(key)
                if data:
                    mastery_data = json.loads(data)
                    learner_mastery = self._deserialize_mastery(mastery_data)
                    
                    # FIXED: Ensure username consistency
                    learner_mastery.username = username
                    
                    return self._format_mastery_summary(learner_mastery)
            
            # Fallback to file storage
            file_path = self.storage_path / f"mastery_{username}_{course_code or 'CMP511'}.json"
            if file_path.exists():
                with open(file_path, 'r') as f:
                    mastery_data = json.load(f)
                    learner_mastery = self._deserialize_mastery(mastery_data)
                    
                    # FIXED: Ensure username consistency
                    learner_mastery.username = username
                    
                    return self._format_mastery_summary(learner_mastery)
                        
        except Exception as e:
            print(f"DEBUG: Error getting cached mastery for {username}: {e}")
        
        return self._get_default_mastery_summary(username, course_code)
           
    async def get_mastery_summary_async(self, username: str, course_code: str = None) -> Dict[str, Any]:
        """FIXED: Async mastery summary with username validation"""
        try:
            # Ensure username is valid
            if not username or username in ['', 'unknown_user', None]:
                username = "default_user"
                
            learner_mastery = await self.load_learner_mastery(username, course_code or "CMP511")
            return self._format_mastery_summary(learner_mastery)
        except Exception as e:
            print(f"DEBUG: Error in async mastery summary for {username}: {e}")
            return self._get_default_mastery_summary(username, course_code)

    async def assess_response_mastery(
        self, 
        student_response: str,
        go_data: Dict[str, Any],
        lo_data: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, float]:
        """FIXED: Enhanced quiz mastery assessment"""
        
        # Check if this is a quiz context (has different evaluation needs)
        is_quiz = context.get('is_quiz', False)
        is_correct = context.get('correct', None)
        quiz_score = context.get('score', None)
        
        if is_quiz and is_correct is not None:
            # FIXED: Better quiz mastery scoring
            if is_correct and quiz_score is not None:
                # For correct quiz answers, use high mastery but not perfect
                # to allow for improvement through additional interactions
                base_mastery = min(0.95, max(0.7, quiz_score))
            elif is_correct:
                # Correct answer without specific score
                base_mastery = 0.8
            else:
                # Incorrect answer - show some learning happened
                base_mastery = 0.3
            
            # Adjust based on question complexity
            question_type = context.get('question_type', 'multiple_choice')
            complexity_bonus = {
                'open_ended': 0.1,
                'fill_in_blank': 0.05,
                'multiple_choice': 0.0,
                'true_false': -0.05
            }.get(question_type, 0.0)
            
            final_mastery = min(1.0, max(0.1, base_mastery + complexity_bonus))
            
            return {
                'go_mastery': {
                    'level': final_mastery,
                    'confidence': 0.9,  # High confidence in quiz evaluations
                    'evidence': f"Quiz response: {'Correct' if is_correct else 'Incorrect'} (Score: {quiz_score}, Type: {question_type})"
                },
                'lo_mastery': {
                    'level': final_mastery * 0.85,  # Slightly lower for LO
                    'confidence': 0.8,
                    'evidence': f"Quiz performance indicates {'good' if is_correct else 'developing'} understanding"
                },
                'week_mastery': {
                    'level': final_mastery * 0.75,  # Lower for week-level
                    'confidence': 0.7,
                    'evidence': f"Week mastery based on quiz performance: {'Strong' if is_correct else 'Needs practice'}"
                }
            }

            # For non-quiz responses, use LLM evaluation
            assessment_prompt = f"""
            You are an expert educational assessor. Analyze this student response to estimate their mastery level.
            
            LEARNING CONTEXT:
            - Granular Objective: {go_data.get('skill_name', 'Unknown')}
            - GO Description: {go_data.get('description', 'No description')}
            - Learning Objective: {lo_data.get('title', 'Unknown')}
            - Week Topic: {context.get('week_topic', 'Unknown')}
            - Course: {context.get('course_code', 'Unknown')}
            
            STUDENT RESPONSE:
            "{student_response}"
            
            For each level, consider:
            - Conceptual understanding (do they grasp the core ideas?)
            - Application ability (can they use the knowledge?)
            - Explanation quality (can they articulate their understanding?)
            - Confidence indicators (do they seem sure or uncertain?)
            
            RESPONSE FORMAT (JSON):
            {{
                "go_mastery": {{
                    "level": 0.75,
                    "confidence": 0.8,
                    "evidence": "Student demonstrates solid understanding of the concept with minor gaps"
                }},
                "lo_mastery": {{
                    "level": 0.65,
                    "confidence": 0.7, 
                    "evidence": "Good grasp of fundamentals, needs work on advanced applications"
                }},
                "week_mastery": {{
                    "level": 0.7,
                    "confidence": 0.75,
                    "evidence": "Strong foundation, ready to progress to more complex topics"
                }}
            }}
            
            IMPORTANT: 
            - Levels range from 0.0 (no mastery) to 1.0 (complete mastery)
            - Confidence ranges from 0.0 (very uncertain) to 1.0 (very certain)
            - Be realistic - most responses will be in 0.3-0.8 range
            """
            
            try:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": assessment_prompt}],
                    temperature=0.3,
                    max_tokens=500
                )
                
                assessment_text = response.choices[0].message.content.strip()
                
                # Extract JSON from response
                start_idx = assessment_text.find('{')
                end_idx = assessment_text.rfind('}') + 1
                
                if start_idx != -1 and end_idx != -1:
                    json_str = assessment_text[start_idx:end_idx]
                    assessment_data = json.loads(json_str)
                    
                    return {
                        'go_mastery': assessment_data['go_mastery'],
                        'lo_mastery': assessment_data['lo_mastery'], 
                        'week_mastery': assessment_data['week_mastery']
                    }
                else:
                    print("WARNING: Could not parse LLM assessment, using enhanced fallback")
                    return self._enhanced_fallback_assessment(student_response, context)
                    
            except Exception as e:
                print(f"ERROR: LLM assessment failed: {e}")
                return self._enhanced_fallback_assessment(student_response, context)
                
        # For non-quiz responses, use LLM evaluation (existing code)

        return await self._llm_evaluate_response(student_response, go_data, lo_data, context)
    
    async def _llm_evaluate_response(self, student_response: str, go_data: Dict, lo_data: Dict, context: Dict) -> Dict:
        """LLM-based evaluation for non-quiz responses"""
        assessment_prompt = f"""
You are an expert educational assessor. Analyze this student response to estimate their mastery level.

LEARNING CONTEXT:
- Granular Objective: {go_data.get('skill_name', 'Unknown')}
- GO Description: {go_data.get('description', 'No description')}
- Learning Objective: {lo_data.get('title', 'Unknown')}
- Week Topic: {context.get('week_topic', 'Unknown')}
- Course: {context.get('course_code', 'Unknown')}

STUDENT RESPONSE:
"{student_response}"

For each level, consider:
- Conceptual understanding (do they grasp the core ideas?)
- Application ability (can they use the knowledge?)
- Explanation quality (can they articulate their understanding?)
- Confidence indicators (do they seem sure or uncertain?)

RESPONSE FORMAT (JSON):
{{
    "go_mastery": {{
        "level": 0.75,
        "confidence": 0.8,
        "evidence": "Student demonstrates solid understanding of the concept with minor gaps"
    }},
    "lo_mastery": {{
        "level": 0.65,
        "confidence": 0.7, 
        "evidence": "Good grasp of fundamentals, needs work on advanced applications"
    }},
    "week_mastery": {{
        "level": 0.7,
        "confidence": 0.75,
        "evidence": "Strong foundation, ready to progress to more complex topics"
    }}
}}

IMPORTANT: 
- Levels range from 0.0 (no mastery) to 1.0 (complete mastery)
- Confidence ranges from 0.0 (very uncertain) to 1.0 (very certain)
- Be realistic - most responses will be in 0.3-0.8 range
"""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": assessment_prompt}],
                temperature=0.3,
                max_tokens=500
            )
            
            assessment_text = response.choices[0].message.content.strip()
            
            # Extract JSON from response
            start_idx = assessment_text.find('{')
            end_idx = assessment_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = assessment_text[start_idx:end_idx]
                assessment_data = json.loads(json_str)
                return assessment_data
            else:
                print("WARNING: Could not parse LLM assessment, using enhanced fallback")
                return self._enhanced_fallback_assessment(student_response, context)
                
        except Exception as e:
            print(f"ERROR: LLM assessment failed: {e}")
            return self._enhanced_fallback_assessment(student_response, context)
    
    async def update_learner_mastery(
        self,
        username: str,
        course_code: str,
        student_response: str,
        go_id: str,
        lo_id: str,
        week_number: int,
        context: Dict[str, Any]
    ) -> LearnerMastery:
        """FIXED: Main method with proper username handling"""
        
        # FIXED: Ensure username is valid throughout the process
        if not username or username in ['', 'unknown_user', None]:
            print(f"WARNING: Invalid username '{username}', using context username")
            # Try to get username from context
            username = context.get('username', 'default_user')
        
        print(f"DEBUG: Updating mastery for user '{username}' in course '{course_code}'")
        
        # Load current mastery profile
        learner_mastery = await self.load_learner_mastery(username, course_code)
        
        # Ensure the learner_mastery object has the correct username
        learner_mastery.username = username
        
        # Get KC data for context
        go_data = context.get('go_data', {})
        lo_data = context.get('lo_data', {})
        
        # Assess current response
        assessment = await self.assess_response_mastery(
            student_response, go_data, lo_data, context
        )
        
        # Update masteries with moving average
        current_time = datetime.now().isoformat()
        
        # Update GO mastery
        self._update_mastery_level(
            learner_mastery.go_masteries,
            go_id,
            assessment['go_mastery'],
            current_time
        )
        
        # Update LO mastery
        self._update_mastery_level(
            learner_mastery.lo_masteries,
            lo_id,
            assessment['lo_mastery'],
            current_time
        )
        
        # Update Week mastery
        self._update_mastery_level(
            learner_mastery.week_masteries,
            week_number,
            assessment['week_mastery'],
            current_time
        )
        
        # Update metadata
        learner_mastery.last_session = current_time
        learner_mastery.total_interactions += 1
        
        # FIXED: Save with proper username
        await self.save_learner_mastery(learner_mastery)
        
        print(f"DEBUG: Updated mastery for {username} - GO:{assessment['go_mastery']['level']:.2f}, LO:{assessment['lo_mastery']['level']:.2f}")
        
        return learner_mastery

    async def load_learner_mastery(self, username: str, course_code: str) -> LearnerMastery:
        """FIXED: Load learner mastery with proper username handling"""
        
        # Ensure username is valid
        if not username or username in ['', 'unknown_user', None]:
            username = "default_user"
        
        try:
            if self.storage_backend == "redis" and self.redis_client:
                # Use LEARedisClient's mastery methods if available
                if hasattr(self.redis_client, 'load_mastery_data'):
                    mastery_data = self.redis_client.load_mastery_data(
                        username, course_code, prefer_latest=True
                    )
                else:
                    # Direct Redis access
                    key = f"mastery:{username}:{course_code}"
                    if hasattr(self.redis_client, 'get_redis'):
                        redis_conn = self.redis_client.get_redis()
                    else:
                        redis_conn = self.redis_client
                    
                    data = redis_conn.get(key)
                    mastery_data = json.loads(data) if data else None
                
                if mastery_data:
                    mastery_obj = self._deserialize_mastery(mastery_data)
                    # FIXED: Ensure username consistency
                    mastery_obj.username = username
                    print(f"DEBUG: ✅ Loaded mastery from Redis for {username} (interactions: {mastery_obj.total_interactions})")
                    return mastery_obj
            
            # Fallback to file storage
            file_path = self.storage_path / f"mastery_{username}_{course_code}.json"
            if file_path.exists():
                with open(file_path, 'r') as f:
                    mastery_data = json.load(f)
                    mastery_obj = self._deserialize_mastery(mastery_data)
                    # FIXED: Ensure username consistency
                    mastery_obj.username = username
                    print(f"DEBUG: Loaded mastery from file for {username}")
                    return mastery_obj
        
        except Exception as e:
            print(f"WARNING: Could not load mastery for {username}: {e}")
        
        # Return empty mastery profile
        print(f"DEBUG: Creating new mastery profile for {username}")
        return LearnerMastery(
            username=username,  # FIXED: Use the validated username
            course_code=course_code,
            go_masteries={},
            lo_masteries={},
            week_masteries={},
            last_session=datetime.now().isoformat(),
            total_interactions=0
        )
    
    async def save_learner_mastery(self, learner_mastery: LearnerMastery) -> bool:
        """FIXED: Save learner mastery with proper username handling"""
        
        try:
            # Ensure username is valid before saving
            if not learner_mastery.username or learner_mastery.username in ['', 'unknown_user', None]:
                print(f"ERROR: Cannot save mastery with invalid username: '{learner_mastery.username}'")
                return False
            
            # Update last session timestamp
            learner_mastery.last_session = datetime.now().isoformat()
            
            # Serialize to JSON
            mastery_data = self._serialize_mastery(learner_mastery)
            
            success = False
            
            # Save to Redis if available
            if self.storage_backend == "redis" and self.redis_client:
                try:
                    if hasattr(self.redis_client, 'save_mastery_data'):
                        # Use LEARedisClient's methods
                        success = self.redis_client.save_mastery_data(
                            learner_mastery.username, 
                            learner_mastery.course_code, 
                            mastery_data,
                            real_time=True
                        )
                    else:
                        # Direct Redis access
                        key = f"mastery:{learner_mastery.username}:{learner_mastery.course_code}"
                        if hasattr(self.redis_client, 'get_redis'):
                            redis_conn = self.redis_client.get_redis()
                        else:
                            redis_conn = self.redis_client
                        
                        redis_conn.set(key, json.dumps(mastery_data))
                        success = True
                    
                    if success:
                        print(f"DEBUG: ✅ Mastery saved to Redis for {learner_mastery.username}")
                except Exception as redis_error:
                    print(f"DEBUG: Redis save failed: {redis_error}")
            
            # Always save to file as backup
            try:
                file_path = self.storage_path / f"mastery_{learner_mastery.username}_{learner_mastery.course_code}.json"
                with open(file_path, 'w') as f:
                    f.write(json.dumps(mastery_data, indent=2))
                success = True
                print(f"DEBUG: ✅ Mastery backed up to file for {learner_mastery.username}")
            except Exception as file_error:
                print(f"DEBUG: File save failed: {file_error}")
            
            return success
        
        except Exception as e:
            print(f"ERROR: Could not save mastery for {learner_mastery.username}: {e}")
            return False
    
    def _serialize_mastery(self, learner_mastery: LearnerMastery) -> Dict:
        """FIXED: Convert LearnerMastery to JSON with username validation"""
        # Ensure username is valid
        username = learner_mastery.username
        if not username or username in ['', 'unknown_user', None]:
            username = "default_user"
            learner_mastery.username = username
        
        return {
            'username': username,  # FIXED: Use validated username
            'course_code': learner_mastery.course_code,
            'go_masteries': {k: asdict(v) for k, v in learner_mastery.go_masteries.items()},
            'lo_masteries': {k: asdict(v) for k, v in learner_mastery.lo_masteries.items()},
            'week_masteries': {str(k): asdict(v) for k, v in learner_mastery.week_masteries.items()},
            'last_session': learner_mastery.last_session,
            'total_interactions': learner_mastery.total_interactions
        }
    
    def _deserialize_mastery(self, data: Dict) -> LearnerMastery:
        """FIXED: Convert JSON dict back to LearnerMastery with better username handling"""
        try:
            # FIXED: Better username handling
            username = data.get('username', data.get('user', 'default_user'))
            if not username or username in ['', 'unknown_user', None]:
                username = "default_user"
            
            course_code = data.get('course_code', data.get('course', 'unknown_course'))
            
            # Safely convert masteries (existing code)
            go_masteries = {}
            if 'go_masteries' in data:
                for k, v in data['go_masteries'].items():
                    if isinstance(v, dict):
                        go_masteries[k] = MasteryLevel(**v)
                    else:
                        go_masteries[k] = MasteryLevel(
                            level=float(v),
                            confidence=0.8,
                            last_updated=datetime.now().isoformat(),
                            interaction_count=1,
                            evidence_summary="Legacy data"
                        )
            
            lo_masteries = {}
            if 'lo_masteries' in data:
                for k, v in data['lo_masteries'].items():
                    if isinstance(v, dict):
                        lo_masteries[k] = MasteryLevel(**v)
                    else:
                        lo_masteries[k] = MasteryLevel(
                            level=float(v),
                            confidence=0.8,
                            last_updated=datetime.now().isoformat(),
                            interaction_count=1,
                            evidence_summary="Legacy data"
                        )
            
            week_masteries = {}
            if 'week_masteries' in data:
                for k, v in data['week_masteries'].items():
                    week_key = int(k) if isinstance(k, str) and k.isdigit() else k
                    if isinstance(v, dict):
                        week_masteries[week_key] = MasteryLevel(**v)
                    else:
                        week_masteries[week_key] = MasteryLevel(
                            level=float(v),
                            confidence=0.8,
                            last_updated=datetime.now().isoformat(),
                            interaction_count=1,
                            evidence_summary="Legacy data"
                        )
            
            return LearnerMastery(
                username=username,  # FIXED: Use validated username
                course_code=course_code,
                go_masteries=go_masteries,
                lo_masteries=lo_masteries,
                week_masteries=week_masteries,
                last_session=data.get('last_session', datetime.now().isoformat()),
                total_interactions=data.get('total_interactions', 0)
            )
            
        except Exception as e:
            print(f"DEBUG: Error deserializing mastery data: {e}")
            print(f"DEBUG: Data keys: {list(data.keys()) if data else 'None'}")
            
            # Return minimal valid object with safe username
            username = data.get('username', data.get('user', 'default_user'))
            if not username or username in ['', 'unknown_user', None]:
                username = "default_user"
            
            return LearnerMastery(
                username=username,
                course_code=data.get('course_code', data.get('course', 'unknown_course')),
                go_masteries={},
                lo_masteries={},
                week_masteries={},
                last_session=datetime.now().isoformat(),
                total_interactions=0
            )

    def _format_mastery_summary(self, learner_mastery: LearnerMastery) -> Dict[str, Any]:
        """Format mastery data for orchestrator compatibility - FIXED: Better week mastery calculation"""
        # Calculate averages
        go_levels = [m.level for m in learner_mastery.go_masteries.values()]
        lo_levels = [m.level for m in learner_mastery.lo_masteries.values()]
    
        # FIXED: Calculate week mastery properly for current week
        week_masteries_dict = {}
        for week_num, mastery in learner_mastery.week_masteries.items():
            week_masteries_dict[week_num] = mastery.level
        
        # Calculate week mastery based on GO masteries for each week
        for week_num in range(1, 13):  # Assuming max 12 weeks
            week_go_levels = []
            
            for go_id, mastery in learner_mastery.go_masteries.items():
                # Check if GO belongs to this week (exclude chat interactions)
                if f"_{week_num:02d}_" in go_id or go_id.startswith(f"GO_{week_num:02d}"):
                    if "CHAT" not in go_id:  # Exclude chat interactions from week mastery
                        week_go_levels.append(mastery.level)
            
            # Update week mastery if we have GO data for this week
            if week_go_levels:
                calculated_week_mastery = sum(week_go_levels) / len(week_go_levels)
                week_masteries_dict[week_num] = max(
                    week_masteries_dict.get(week_num, 0.0), 
                    calculated_week_mastery
                )
                print(f"DEBUG: Week {week_num} mastery calculated: {calculated_week_mastery:.3f} from {len(week_go_levels)} GOs")
        
        week_levels = list(week_masteries_dict.values())
        
        return {
            # Orchestrator-expected format
            'go_masteries': {go_id: mastery.level for go_id, mastery in learner_mastery.go_masteries.items()},
            'lo_masteries': {lo_id: mastery.level for lo_id, mastery in learner_mastery.lo_masteries.items()},
            'week_masteries': week_masteries_dict,
            
            # Additional summary data
            'username': learner_mastery.username,
            'course': learner_mastery.course_code,
            'total_interactions': learner_mastery.total_interactions,
            'last_session': learner_mastery.last_session,
            'averages': {
                'go_mastery': np.mean(go_levels) if go_levels else 0.0,
                'lo_mastery': np.mean(lo_levels) if lo_levels else 0.0, 
                'week_mastery': np.mean(week_levels) if week_levels else 0.0
            },
            'mastery_counts': {
                'go_tracked': len(learner_mastery.go_masteries),
                'lo_tracked': len(learner_mastery.lo_masteries),
                'weeks_tracked': len(week_masteries_dict)
            },
            'high_mastery_items': {
                'gos': [go_id for go_id, mastery in learner_mastery.go_masteries.items() if mastery.level > 0.8],
                'los': [lo_id for lo_id, mastery in learner_mastery.lo_masteries.items() if mastery.level > 0.8],
                'weeks': [week for week, mastery_level in week_masteries_dict.items() if mastery_level > 0.8]
            },
            'current_week_breakdown': self._get_current_week_breakdown(learner_mastery),
            'last_updated_timestamp': time.time()  # For real-time updates
        }

    def _get_current_week_breakdown(self, learner_mastery: LearnerMastery) -> Dict[str, Any]:
        """Get detailed breakdown for current week activities"""
        breakdown = {
            'quiz_interactions': 0,
            'tutor_interactions': 0,
            'chat_interactions': 0,
            'recent_gos': [],
            'struggling_gos': [],
            'mastered_gos': []
        }
        
        try:
            for go_id, mastery in learner_mastery.go_masteries.items():
                # Check if this is a recent GO (from current session)
                if mastery.last_updated:
                    try:
                        last_update = datetime.fromisoformat(mastery.last_updated)
                        if (datetime.now() - last_update).seconds < 3600:  # Within last hour
                            breakdown['recent_gos'].append({
                                'go_id': go_id,
                                'mastery_level': mastery.level,
                                'interaction_count': mastery.interaction_count
                            })
                    except:
                        pass
                
                # Categorize by mastery level
                if mastery.level > 0.8:
                    breakdown['mastered_gos'].append(go_id)
                elif mastery.level < 0.3:
                    breakdown['struggling_gos'].append(go_id)
                
                # Count interaction types
                if 'QUIZ' in go_id:
                    breakdown['quiz_interactions'] += mastery.interaction_count
                elif 'TUTOR' in go_id:
                    breakdown['tutor_interactions'] += mastery.interaction_count
                elif 'CHAT' in go_id:
                    breakdown['chat_interactions'] += mastery.interaction_count
            
            return breakdown
            
        except Exception as e:
            print(f"DEBUG: Error creating week breakdown: {e}")
            return breakdown
    
    def _get_default_mastery_summary(self, username: str, course_code: str) -> Dict[str, Any]:
        """Default mastery summary when data unavailable"""
        return {
            'go_masteries': {},
            'lo_masteries': {},
            'week_masteries': {},
            'username': username,
            'course': course_code or "CMP511",
            'total_interactions': 0,
            'last_session': datetime.now().isoformat(),
            'averages': {'go_mastery': 0.0, 'lo_mastery': 0.0, 'week_mastery': 0.0},
            'mastery_counts': {'go_tracked': 0, 'lo_tracked': 0, 'weeks_tracked': 0},
            'high_mastery_items': {'gos': [], 'los': [], 'weeks': []}
        }

    def _enhanced_fallback_assessment(self, student_response: str, context: Dict) -> Dict[str, float]:
        """Enhanced fallback assessment with context awareness"""
        response_length = len(student_response.split())
        
        # Base mastery calculation
        base_mastery = min(0.8, 0.3 + (response_length / 50) * 0.4)
        
        # Adjust based on context
        if context.get('is_quiz', False):
            # Quiz context - be more conservative
            base_mastery *= 0.8
        
        # Adjust based on keywords that indicate understanding
        understanding_keywords = [
            'because', 'therefore', 'however', 'example', 'like', 'such as',
            'understand', 'think', 'believe', 'seems', 'appears', 'algorithm',
            'model', 'data', 'predict', 'classification', 'regression'
        ]
        
        keyword_count = sum(1 for word in understanding_keywords 
                           if word in student_response.lower())
        keyword_bonus = min(0.2, keyword_count * 0.05)
        
        # Check for code-related understanding
        code_indicators = ['sklearn', 'fit', 'predict', 'import', 'def', 'class']
        code_count = sum(1 for indicator in code_indicators 
                        if indicator in student_response.lower())
        code_bonus = min(0.15, code_count * 0.05)
        
        final_mastery = min(1.0, base_mastery + keyword_bonus + code_bonus)
        
        return {
            'go_mastery': {
                'level': final_mastery,
                'confidence': 0.5,  # Lower confidence for fallback
                'evidence': f"Fallback assessment based on response analysis (length: {response_length}, keywords: {keyword_count})"
            },
            'lo_mastery': {
                'level': final_mastery * 0.9,
                'confidence': 0.4,
                'evidence': "Estimated from GO mastery using enhanced heuristic"
            },
            'week_mastery': {
                'level': final_mastery * 0.8,
                'confidence': 0.4,
                'evidence': "Estimated from GO mastery using enhanced heuristic"
            }
        }

    def _update_mastery_level(self, mastery_dict: Dict, key: Any, new_assessment: Dict[str, Any], timestamp: str):
        """Update mastery level using improved weighted moving average"""
        
        if key not in mastery_dict:
            # First assessment
            mastery_dict[key] = MasteryLevel(
                level=new_assessment['level'],
                confidence=new_assessment['confidence'],
                last_updated=timestamp,
                interaction_count=1,
                evidence_summary=new_assessment['evidence']
            )
            print(f"DEBUG: New mastery tracking for {key}: {new_assessment['level']:.3f}")
        else:
            # Update existing mastery
            current = mastery_dict[key]
            
            # FIXED: Adaptive weighting based on confidence and interaction count
            base_weight = 0.3  # Base weight for new evidence
            
            # Increase weight for high-confidence assessments
            confidence_boost = (new_assessment['confidence'] - 0.5) * 0.2
            
            # Decrease weight as interaction count increases (more stable)
            stability_factor = max(0.1, 1.0 - (current.interaction_count * 0.05))
            
            final_weight = max(0.1, min(0.6, base_weight + confidence_boost)) * stability_factor
            
            new_level = (1 - final_weight) * current.level + final_weight * new_assessment['level']
            new_confidence = (1 - final_weight) * current.confidence + final_weight * new_assessment['confidence']
            
            mastery_dict[key] = MasteryLevel(
                level=new_level,
                confidence=new_confidence,
                last_updated=timestamp,
                interaction_count=current.interaction_count + 1,
                evidence_summary=new_assessment['evidence']
            )
            
            print(f"DEBUG: Updated mastery for {key}: {current.level:.3f} -> {new_level:.3f} (weight: {final_weight:.3f})")
            
# Integration helper functions for existing systems
class MasteryIntegrationHelper:
    """Helper class to integrate mastery tracking with existing systems"""
    
    def __init__(self, mastery_tracker: MasteryTracker):
        self.mastery_tracker = mastery_tracker
    
    async def track_tutor_interaction(
        self, username: str, course_code: str, student_response: str,
        tutor_session, week_number: int
    ) -> Optional[LearnerMastery]:
        """Integration point for tutor mode"""
        
        if not tutor_session or not tutor_session.go_list:
            return None
        
        # Get current GO and LO from session
        current_go = tutor_session.go_list[tutor_session.current_go_index]
        go_id = current_go['go_id']
        
        # Extract LO ID from GO ID (assuming format like "GO_03_01_01" -> "LO_03_01")
        lo_id = "_".join(go_id.split("_")[:3])
        
        # Build context
        context = {
            'go_data': current_go,
            'lo_data': {'title': f"Learning Objective {lo_id}"},
            'week_topic': f"Week {week_number}",
            'course_code': course_code
        }
        
        # Update mastery
        return await self.mastery_tracker.update_learner_mastery(
            username, course_code, student_response, go_id, lo_id, week_number, context
        )
    
    async def track_quiz_interaction(
        self, username: str, course_code: str, question_data: Dict,
        student_answer: str, is_correct: bool, week_number: int
    ) -> Optional[LearnerMastery]:
        """Integration point for quiz mode"""
        
        # Build synthetic response for mastery assessment
        response_quality = "correct" if is_correct else "incorrect"
        student_response = f"Answer: {student_answer} ({response_quality})"
        
        # Extract IDs from question data
        go_id = question_data.get('go_id', 'UNKNOWN_GO')
        lo_id = "_".join(go_id.split("_")[:3]) if go_id != 'UNKNOWN_GO' else 'UNKNOWN_LO'
        
        context = {
            'go_data': {'skill_name': question_data.get('skill', 'Unknown skill')},
            'lo_data': {'title': f"Learning Objective {lo_id}"},
            'week_topic': f"Week {week_number}",
            'course_code': course_code,
            'is_quiz': True,
            'correct': is_correct
        }
        
        return await self.mastery_tracker.update_learner_mastery(
            username, course_code, student_response, go_id, lo_id, week_number, context
        )
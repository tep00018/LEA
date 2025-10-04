# src/mcp/tools/mastery_service.py
"""
Mastery Service - MCP Tool for Learning Progress Tracking
Centralized service for all mastery tracking operations with Redis persistence
"""

import json
import time
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np
from openai import OpenAI

@dataclass
class MasteryLevel:
    """Mastery level for individual learning components"""
    level: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    last_updated: str
    interaction_count: int
    evidence_summary: str

@dataclass
class MasterySnapshot:
    """Complete mastery snapshot for a learner"""
    username: str
    course_code: str
    go_masteries: Dict[str, MasteryLevel]
    lo_masteries: Dict[str, MasteryLevel]  
    week_masteries: Dict[int, MasteryLevel]
    course_mastery: MasteryLevel
    last_session: str
    total_interactions: int

class MasteryService:
    """
    Centralized Mastery Service accessible via MCP
    Handles all mastery CRUD operations with LLM assessment
    """
    
    def __init__(self, redis_client=None):
        """Initialize mastery service"""
        self.redis_client = redis_client
        self.openai_client = OpenAI()
        
        # Storage setup
        self.storage_path = Path("./data/mastery_tracking")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Determine storage backend
        self.use_redis = redis_client is not None
        
        print(f"DEBUG: MasteryService initialized with {'Redis' if self.use_redis else 'file'} storage")
    
    async def update_mastery(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main MCP tool method for updating mastery
        
        Expected parameters:
        - username: str
        - course_code: str  
        - interaction_data: Dict containing response, context, etc.
        """
        try:
            username = parameters.get("username")
            course_code = parameters.get("course_code")
            interaction_data = parameters.get("interaction_data", {})
            
            if not username or not course_code:
                return {
                    "success": False,
                    "error": "Username and course_code are required"
                }
            
            print(f"DEBUG: MasteryService updating mastery for {username} in {course_code}")
            
            # Load current mastery
            current_mastery = await self.load_mastery_snapshot(username, course_code)
            
            # Extract interaction details
            student_response = interaction_data.get("student_response", "")
            interaction_type = interaction_data.get("interaction_type", "unknown")
            week_number = interaction_data.get("week_number", 1)
            go_id = interaction_data.get("go_id", f"GO_{week_number:02d}_01_01")
            lo_id = interaction_data.get("lo_id", f"LO_{week_number:02d}_01")
            
            # Assess mastery using LLM
            assessment = await self.assess_interaction_mastery(
                student_response, 
                interaction_data,
                current_mastery
            )
            
            # Update mastery levels
            updated_mastery = self.apply_mastery_updates(
                current_mastery,
                assessment,
                go_id,
                lo_id,
                week_number
            )
            
            # Save updated mastery
            save_success = await self.save_mastery_snapshot(updated_mastery)
            
            if save_success:
                return {
                    "success": True,
                    "tool": "mastery_update",
                    "updated_masteries": {
                        "go_mastery": assessment.get("go_mastery", {}).get("level", 0.0),
                        "lo_mastery": assessment.get("lo_mastery", {}).get("level", 0.0),
                        "week_mastery": assessment.get("week_mastery", {}).get("level", 0.0),
                        "course_mastery": updated_mastery.course_mastery.level
                    },
                    "total_interactions": updated_mastery.total_interactions,
                    "assessment_confidence": assessment.get("go_mastery", {}).get("confidence", 0.5)
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to save mastery data"
                }
                
        except Exception as e:
            print(f"ERROR: MasteryService update failed: {e}")
            return {
                "success": False,
                "error": f"Mastery update error: {str(e)}"
            }
    
    async def get_mastery_summary(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get mastery summary via MCP
        
        Expected parameters:
        - username: str
        - course_code: str
        """
        try:
            username = parameters.get("username")
            course_code = parameters.get("course_code")
            
            if not username or not course_code:
                return {
                    "success": False,
                    "error": "Username and course_code are required"
                }
            
            mastery_snapshot = await self.load_mastery_snapshot(username, course_code)
            
            # Format for orchestrator compatibility
            summary = self.format_mastery_summary(mastery_snapshot)
            
            return {
                "success": True,
                "tool": "mastery_summary",
                **summary
            }
            
        except Exception as e:
            print(f"ERROR: MasteryService summary failed: {e}")
            return {
                "success": False,
                "error": f"Mastery summary error: {str(e)}"
            }
    
    async def get_week_mastery(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get specific week mastery for UI display
        
        Expected parameters:
        - username: str
        - course_code: str
        - week_number: int (optional)
        """
        try:
            username = parameters.get("username")
            course_code = parameters.get("course_code")
            week_number = parameters.get("week_number")
            
            mastery_snapshot = await self.load_mastery_snapshot(username, course_code)
            
            week_masteries = {}
            for week, mastery_level in mastery_snapshot.week_masteries.items():
                week_masteries[week] = {
                    "level": mastery_level.level,
                    "confidence": mastery_level.confidence,
                    "last_updated": mastery_level.last_updated,
                    "interaction_count": mastery_level.interaction_count
                }
            
            if week_number is not None:
                # Return specific week
                week_data = week_masteries.get(week_number)
                if week_data:
                    return {
                        "success": True,
                        "tool": "week_mastery",
                        "week_number": week_number,
                        "mastery_data": week_data
                    }
                else:
                    return {
                        "success": True,
                        "tool": "week_mastery",
                        "week_number": week_number,
                        "mastery_data": {"level": 0.0, "confidence": 0.0, "interaction_count": 0}
                    }
            else:
                # Return all weeks
                return {
                    "success": True,
                    "tool": "week_mastery",
                    "week_masteries": week_masteries,
                    "course_mastery": {
                        "level": mastery_snapshot.course_mastery.level,
                        "confidence": mastery_snapshot.course_mastery.confidence
                    }
                }
                
        except Exception as e:
            print(f"ERROR: Week mastery request failed: {e}")
            return {
                "success": False,
                "error": f"Week mastery error: {str(e)}"
            }
    
    async def assess_interaction_mastery(
        self, 
        student_response: str,
        interaction_data: Dict[str, Any],
        current_mastery: MasterySnapshot
    ) -> Dict[str, Any]:
        """Use LLM to assess mastery from student interaction"""
        
        # Build assessment context
        interaction_type = interaction_data.get("interaction_type", "unknown")
        course_code = interaction_data.get("course_code", "Unknown")
        week_number = interaction_data.get("week_number", 1)
        is_correct = interaction_data.get("is_correct", None)
        
        # Get current mastery levels for context
        week_mastery = current_mastery.week_masteries.get(week_number)
        current_week_level = week_mastery.level if week_mastery else 0.0
        
        assessment_prompt = f"""
You are an expert educational assessor analyzing student learning progress.

LEARNING CONTEXT:
- Course: {course_code}
- Week: {week_number}
- Interaction Type: {interaction_type}
- Current Week Mastery: {current_week_level:.2f}/1.0
- Total Interactions: {current_mastery.total_interactions}

STUDENT RESPONSE:
"{student_response}"

{"CORRECTNESS: " + str(is_correct) if is_correct is not None else ""}

Assess the student's mastery at three levels:
1. Granular Objective (GO) - specific skill demonstrated
2. Learning Objective (LO) - broader concept understanding  
3. Week Topic - overall week mastery
4. Course Level - cumulative course understanding

Consider:
- Conceptual understanding depth
- Application ability
- Explanation clarity
- Confidence indicators
- Progress from previous interactions

RESPONSE FORMAT (JSON):
{{
    "go_mastery": {{
        "level": 0.75,
        "confidence": 0.8,
        "evidence": "Student shows solid understanding with minor gaps"
    }},
    "lo_mastery": {{
        "level": 0.65,
        "confidence": 0.7,
        "evidence": "Good foundation, needs advanced practice"
    }},
    "week_mastery": {{
        "level": 0.7,
        "confidence": 0.75,
        "evidence": "Strong week progress, ready for next challenges"
    }},
    "course_mastery": {{
        "level": 0.68,
        "confidence": 0.65,
        "evidence": "Steady overall progress with good retention"
    }}
}}

IMPORTANT: 
- Levels: 0.0 (no mastery) to 1.0 (complete mastery)
- Confidence: 0.0 (uncertain) to 1.0 (very certain)
- Most responses should be 0.3-0.8 range
- Consider cumulative learning
"""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": assessment_prompt}],
                temperature=0.3,
                max_tokens=600
            )
            
            assessment_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            start_idx = assessment_text.find('{')
            end_idx = assessment_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = assessment_text[start_idx:end_idx]
                assessment_data = json.loads(json_str)
                
                print(f"DEBUG: LLM mastery assessment - GO: {assessment_data['go_mastery']['level']:.2f}")
                return assessment_data
            else:
                print("WARNING: Could not parse LLM assessment, using fallback")
                return self.fallback_assessment(student_response, interaction_data)
                
        except Exception as e:
            print(f"ERROR: LLM assessment failed: {e}")
            return self.fallback_assessment(student_response, interaction_data)
    
    def fallback_assessment(self, student_response: str, interaction_data: Dict) -> Dict[str, Any]:
        """Simple fallback assessment when LLM fails"""
        # Basic heuristics
        response_length = len(student_response.split())
        is_correct = interaction_data.get("is_correct", None)
        
        # Length-based assessment
        base_mastery = min(0.8, 0.3 + (response_length / 50) * 0.4)
        
        # Correctness bonus/penalty
        if is_correct is True:
            base_mastery = min(1.0, base_mastery + 0.2)
        elif is_correct is False:
            base_mastery = max(0.1, base_mastery - 0.1)
        
        return {
            "go_mastery": {
                "level": base_mastery,
                "confidence": 0.4,
                "evidence": "Fallback assessment based on response analysis"
            },
            "lo_mastery": {
                "level": base_mastery * 0.9,
                "confidence": 0.3,
                "evidence": "Estimated from GO mastery"
            },
            "week_mastery": {
                "level": base_mastery * 0.8,
                "confidence": 0.3,
                "evidence": "Estimated from GO mastery"
            },
            "course_mastery": {
                "level": base_mastery * 0.7,
                "confidence": 0.3,
                "evidence": "Estimated from GO mastery"
            }
        }
    
    def apply_mastery_updates(
        self,
        current_mastery: MasterySnapshot,
        assessment: Dict[str, Any],
        go_id: str,
        lo_id: str,
        week_number: int
    ) -> MasterySnapshot:
        """Apply mastery updates using weighted averages"""
        
        timestamp = datetime.now().isoformat()
        
        # Update GO mastery
        self.update_mastery_level(
            current_mastery.go_masteries,
            go_id,
            assessment["go_mastery"],
            timestamp
        )
        
        # Update LO mastery
        self.update_mastery_level(
            current_mastery.lo_masteries,
            lo_id,
            assessment["lo_mastery"],
            timestamp
        )
        
        # Update Week mastery
        self.update_mastery_level(
            current_mastery.week_masteries,
            week_number,
            assessment["week_mastery"],
            timestamp
        )
        
        # Update Course mastery
        course_assessment = {
            "level": assessment["course_mastery"]["level"],
            "confidence": assessment["course_mastery"]["confidence"],
            "evidence": assessment["course_mastery"]["evidence"]
        }
        
        if current_mastery.course_mastery.interaction_count == 0:
            current_mastery.course_mastery = MasteryLevel(
                level=course_assessment["level"],
                confidence=course_assessment["confidence"],
                last_updated=timestamp,
                interaction_count=1,
                evidence_summary=course_assessment["evidence"]
            )
        else:
            # Weighted average for course mastery
            weight = 0.1  # Course mastery changes slowly
            new_level = (1 - weight) * current_mastery.course_mastery.level + weight * course_assessment["level"]
            new_confidence = (1 - weight) * current_mastery.course_mastery.confidence + weight * course_assessment["confidence"]
            
            current_mastery.course_mastery = MasteryLevel(
                level=new_level,
                confidence=new_confidence,
                last_updated=timestamp,
                interaction_count=current_mastery.course_mastery.interaction_count + 1,
                evidence_summary=course_assessment["evidence"]
            )
        
        # Update metadata
        current_mastery.last_session = timestamp
        current_mastery.total_interactions += 1
        
        return current_mastery
    
    def update_mastery_level(self, mastery_dict: Dict, key: Any, assessment: Dict, timestamp: str):
        """Update individual mastery level with weighted average"""
        
        if key not in mastery_dict:
            # First interaction for this component
            mastery_dict[key] = MasteryLevel(
                level=assessment["level"],
                confidence=assessment["confidence"],
                last_updated=timestamp,
                interaction_count=1,
                evidence_summary=assessment["evidence"]
            )
        else:
            # Update existing mastery
            current = mastery_dict[key]
            
            # Weighted average (30% new evidence, 70% historical)
            weight = 0.3
            new_level = (1 - weight) * current.level + weight * assessment["level"]
            new_confidence = (1 - weight) * current.confidence + weight * assessment["confidence"]
            
            mastery_dict[key] = MasteryLevel(
                level=new_level,
                confidence=new_confidence,
                last_updated=timestamp,
                interaction_count=current.interaction_count + 1,
                evidence_summary=assessment["evidence"]
            )
    
    async def load_mastery_snapshot(self, username: str, course_code: str) -> MasterySnapshot:
        """Load complete mastery snapshot"""
        key = f"mastery:{username}:{course_code}"
        
        try:
            # Try Redis first
            if self.use_redis and hasattr(self.redis_client, 'get_redis'):
                data = self.redis_client.get_redis().get(key)
                if data:
                    mastery_data = json.loads(data)
                    return self.deserialize_mastery(mastery_data)
            
            # Fallback to file
            file_path = self.storage_path / f"{key.replace(':', '_')}.json"
            if file_path.exists():
                with open(file_path, 'r') as f:
                    mastery_data = json.load(f)
                    return self.deserialize_mastery(mastery_data)
                    
        except Exception as e:
            print(f"WARNING: Could not load mastery for {username}: {e}")
        
        # Return empty snapshot
        return MasterySnapshot(
            username=username,
            course_code=course_code,
            go_masteries={},
            lo_masteries={},
            week_masteries={},
            course_mastery=MasteryLevel(0.0, 0.0, datetime.now().isoformat(), 0, "Initial state"),
            last_session=datetime.now().isoformat(),
            total_interactions=0
        )
    
    async def save_mastery_snapshot(self, mastery: MasterySnapshot) -> bool:
        """Save complete mastery snapshot"""
        key = f"mastery:{mastery.username}:{mastery.course_code}"
        
        try:
            serialized = self.serialize_mastery(mastery)
            json_data = json.dumps(serialized, indent=2)
            
            # Save to Redis
            if self.use_redis and hasattr(self.redis_client, 'get_redis'):
                self.redis_client.get_redis().setex(key, 86400 * 30, json_data)  # 30 day expiry
            
            # Always save to file as backup
            file_path = self.storage_path / f"{key.replace(':', '_')}.json"
            with open(file_path, 'w') as f:
                f.write(json_data)
            
            return True
            
        except Exception as e:
            print(f"ERROR: Could not save mastery: {e}")
            return False
    
    def serialize_mastery(self, mastery: MasterySnapshot) -> Dict:
        """Convert mastery snapshot to JSON"""
        return {
            "username": mastery.username,
            "course_code": mastery.course_code,
            "go_masteries": {k: asdict(v) for k, v in mastery.go_masteries.items()},
            "lo_masteries": {k: asdict(v) for k, v in mastery.lo_masteries.items()},
            "week_masteries": {str(k): asdict(v) for k, v in mastery.week_masteries.items()},
            "course_mastery": asdict(mastery.course_mastery),
            "last_session": mastery.last_session,
            "total_interactions": mastery.total_interactions
        }
    
    def deserialize_mastery(self, data: Dict) -> MasterySnapshot:
        """Convert JSON back to mastery snapshot"""
        return MasterySnapshot(
            username=data["username"],
            course_code=data["course_code"],
            go_masteries={k: MasteryLevel(**v) for k, v in data["go_masteries"].items()},
            lo_masteries={k: MasteryLevel(**v) for k, v in data["lo_masteries"].items()},
            week_masteries={int(k): MasteryLevel(**v) for k, v in data["week_masteries"].items()},
            course_mastery=MasteryLevel(**data["course_mastery"]),
            last_session=data["last_session"],
            total_interactions=data["total_interactions"]
        )
    
    def format_mastery_summary(self, mastery: MasterySnapshot) -> Dict[str, Any]:
        """Format mastery for orchestrator compatibility"""
        # Calculate averages
        go_levels = [m.level for m in mastery.go_masteries.values()]
        lo_levels = [m.level for m in mastery.lo_masteries.values()]
        week_levels = [m.level for m in mastery.week_masteries.values()]
        
        return {
            "go_masteries": {k: v.level for k, v in mastery.go_masteries.items()},
            "lo_masteries": {k: v.level for k, v in mastery.lo_masteries.items()},
            "week_masteries": {k: v.level for k, v in mastery.week_masteries.items()},
            "course_mastery": mastery.course_mastery.level,
            "username": mastery.username,
            "course": mastery.course_code,
            "total_interactions": mastery.total_interactions,
            "last_session": mastery.last_session,
            "averages": {
                "go_mastery": np.mean(go_levels) if go_levels else 0.0,
                "lo_mastery": np.mean(lo_levels) if lo_levels else 0.0,
                "week_mastery": np.mean(week_levels) if week_levels else 0.0
            },
            "mastery_counts": {
                "go_tracked": len(mastery.go_masteries),
                "lo_tracked": len(mastery.lo_masteries),
                "weeks_tracked": len(mastery.week_masteries)
            }
        }
    
    def get_schema(self) -> Dict[str, Any]:
        """Return MCP schema for mastery tools"""
        return {
            "update": {
                "name": "mastery_update",
                "description": "Update student mastery levels based on learning interactions",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "username": {"type": "string", "required": True},
                        "course_code": {"type": "string", "required": True},
                        "interaction_data": {
                            "type": "object",
                            "properties": {
                                "student_response": {"type": "string"},
                                "interaction_type": {"type": "string"},
                                "week_number": {"type": "integer"},
                                "go_id": {"type": "string"},
                                "lo_id": {"type": "string"},
                                "is_correct": {"type": "boolean"}
                            }
                        }
                    }
                }
            },
            "summary": {
                "name": "mastery_summary", 
                "description": "Get complete mastery summary for a student",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "username": {"type": "string", "required": True},
                        "course_code": {"type": "string", "required": True}
                    }
                }
            },
            "week_mastery": {
                "name": "week_mastery",
                "description": "Get week-specific mastery data for UI display",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "username": {"type": "string", "required": True},
                        "course_code": {"type": "string", "required": True},
                        "week_number": {"type": "integer"}
                    }
                }
            }
        }
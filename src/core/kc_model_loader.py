# File: src/core/kc_model_loader.py

import json
import redis
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
import os

# Configure logging for debugging and monitoring
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class GranularObjective:
    """Represents the most granular learning unit in the KC model"""
    go_id: str
    skill_name: str
    description: str
    cognitive_level: str  # ADD THIS
    mastery_threshold: float  # ADD THIS
    estimated_time_minutes: int  # ADD THIS
    skill_category: str  # ADD THIS
    complexity: str  # ADD THIS
    conceptual_tags: List[str]  # ADD THIS (replaces content_keywords)
    prerequisite_concepts: List[str]  # ADD THIS (replaces prerequisites)
    
    # Keep backward compatibility
    @property
    def prerequisites(self):
        return self.prerequisite_concepts
    
    @property
    def content_keywords(self):
        return self.conceptual_tags
    
    @property
    def assessment_type(self):
        # Derive from cognitive level
        level_to_assessment = {
            'Remember': 'multiple_choice',
            'Understand': 'multiple_choice',
            'Apply': 'problem_solving',
            'Analyze': 'open_ended',
            'Evaluate': 'open_ended',
            'Create': 'open_ended'
        }
        return level_to_assessment.get(self.cognitive_level, 'multiple_choice')
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
        

@dataclass
class LearningObjective:
    """Represents a learning objective containing multiple granular objectives"""
    lo_id: str
    objective_name: str
    description: str  # Added this field
    granular_objectives: List[GranularObjective]
    mastery_threshold: float = 0.8
    
    def get_mastery_from_gos(self, go_masteries: Dict[str, float]) -> float:
        """Calculate LO mastery from constituent GO masteries"""
        if not self.granular_objectives:
            return 0.0
        
        total_mastery = sum(
            go_masteries.get(go.go_id, 0.0) 
            for go in self.granular_objectives
        )
        return total_mastery / len(self.granular_objectives)


@dataclass
class WeekContent:
    """Represents a week's worth of learning content"""
    week_id: str
    week_number: int
    topic: str
    learning_objectives: List[LearningObjective]
    
    def is_unlocked(self, lo_masteries: Dict[str, float]) -> bool:
        """Check if week should be unlocked based on previous week's mastery"""
        # Week 1 is always unlocked
        if self.week_number == 1:
            return True
            
        # For other weeks, we need to check if prerequisites are met
        # This would typically check the previous week's mastery
        # For now, we'll use a simple rule
        return True  # Simplified for proof of concept


class KCModelLoader:
    """
    Loads and manages KC (Knowledge Component) models for dynamic content generation.
    This replaces all hardcoded course content with structured, adaptive curriculum.
    
    FIXED: Now compatible with both standard Redis and LEARedisClient
    """
    
    def __init__(self, redis_client, module: str, kc_model_path: Optional[str] = None):
        """
        Initialize KC Model Loader
        
        Args:
            redis_client: Redis connection (standard Redis or LEARedisClient)
            module: Module name for organizing KC models (e.g., "CMP511")
            kc_model_path: Path to directory containing KC JSON files (optional)
        """
        self.redis_client = redis_client
        self.module = module  # Store the module name
        
        # FIXED: Detect if we're using LEARedisClient and adapt accordingly
        self._is_lea_redis = hasattr(redis_client, 'redis_client')
        if self._is_lea_redis:
            # LEARedisClient - use the underlying Redis client for caching
            self._cache_client = redis_client.redis_client if hasattr(redis_client, 'redis_client') else redis_client
        else:
            # Standard Redis client
            self._cache_client = redis_client
        
        # If no path provided, calculate it relative to project root
        if kc_model_path is None:
            # Get the directory where this file is located
            current_file = Path(__file__).resolve()
            # Go up to project root (src/core -> src -> project_root)
            project_root = current_file.parent.parent.parent
            # Data directory is at project_root/data/kc_models/module
            kc_model_path = project_root / "data" / "kc_models" / module
        else:
            # If custom path provided, append the module to it
            kc_model_path = Path(kc_model_path) / module
        
        self.kc_model_path = Path(kc_model_path)
        self.cache_ttl = 3600  # Cache models for 1 hour
        
        logger.info(f"KC Model Loader initialized for module '{module}' with path: {self.kc_model_path}")
        logger.info(f"Redis client type: {'LEARedisClient' if self._is_lea_redis else 'Standard Redis'}")
        
        # Verify the path exists
        if not self.kc_model_path.exists():
            logger.warning(f"KC model directory does not exist: {self.kc_model_path}")
            # Try to create it
            try:
                self.kc_model_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created KC model directory: {self.kc_model_path}")
            except Exception as e:
                logger.error(f"Failed to create KC model directory: {e}")
    
    def load_course_model(self, course_code: str) -> Dict[str, Any]:
        """
        Load KC model for a specific course, using cache if available
        
        Args:
            course_code: Course identifier (e.g., "CMP511")
            
        Returns:
            Parsed KC model dictionary
        """
        # Check Redis cache first - FIXED: Use proper cache client
        # Include module in cache key to avoid conflicts between modules
        cache_key = f"kc_model:{self.module}:{course_code}"
        try:
            if hasattr(self._cache_client, 'get'):
                cached_model = self._cache_client.get(cache_key)
                if cached_model:
                    logger.info(f"Loading KC model from cache for {self.module}/{course_code}")
                    return json.loads(cached_model)
        except Exception as e:
            logger.warning(f"Redis cache read failed: {e}")
        
        # Load from file if not cached - NEW FILENAME FORMAT
        model_file = self.kc_model_path / f"kc_model_{course_code}.json"
        
        if not model_file.exists():
            logger.warning(f"KC model not found at {model_file}, using default model")
            # Return a default model for testing
            return self._get_default_model(course_code)
        
        with open(model_file, 'r') as f:
            kc_model = json.load(f)
        
        # Validate model structure
        self._validate_model_structure(kc_model)
        
        # Cache the model - FIXED: Use proper cache client
        try:
            if hasattr(self._cache_client, 'setex'):
                self._cache_client.setex(
                    cache_key, 
                    self.cache_ttl, 
                    json.dumps(kc_model)
                )
        except Exception as e:
            logger.warning(f"Redis cache write failed: {e}")
        
        logger.info(f"Loaded and cached KC model for {self.module}/{course_code}")
        return kc_model
    
    def invalidate_cache(self, course_code: str) -> None:
        """Force reload of KC model on next access"""
        # Include module in cache key
        cache_key = f"kc_model:{self.module}:{course_code}"
        try:
            if hasattr(self._cache_client, 'delete'):
                self._cache_client.delete(cache_key)
                logger.info(f"Invalidated KC model cache for {self.module}/{course_code}")
        except Exception as e:
            logger.warning(f"Failed to invalidate cache: {e}")
            

    
    def _get_default_model(self, course_code: str) -> Dict[str, Any]:
        """Return a default KC model for testing when file is not found"""
        return {
            "course_info": {
                "course_code": course_code,
                "course_name": "Machine Learning Fundamentals",
                "total_weeks": 12
            },
            "week_navigation": {
                "week_01": {
                    "week_number": 1,
                    "topic": "Introduction to AI/ML",
                    "week_display": "Week 1: Introduction to AI/ML",
                    "learning_objectives": [
                        {
                            "lo_id": "LO_01_01",
                            "objective_name": "Types of AI",
                            "description": "Understand different types of artificial intelligence",
                            "mastery_threshold": 0.8,
                            "granular_objectives": [
                                {
                                    "go_id": "GO_01_01_01",
                                    "skill_name": "Identify AI types",
                                    "description": "Distinguish between narrow and general AI",
                                    "prerequisites": [],
                                    "assessment_type": "multiple_choice",
                                    "content_keywords": ["AI", "narrow AI", "general AI", "AGI"]
                                },
                                {
                                    "go_id": "GO_01_01_02",
                                    "skill_name": "ML vs Traditional Programming",
                                    "description": "Explain the difference between ML and traditional programming",
                                    "prerequisites": ["GO_01_01_01"],
                                    "assessment_type": "open_ended",
                                    "content_keywords": ["machine learning", "programming", "algorithms"]
                                }
                            ]
                        },
                        {
                            "lo_id": "LO_01_02",
                            "objective_name": "ML Fundamentals",
                            "description": "Understand basic machine learning concepts",
                            "mastery_threshold": 0.8,
                            "granular_objectives": [
                                {
                                    "go_id": "GO_01_02_01",
                                    "skill_name": "Supervised vs Unsupervised",
                                    "description": "Differentiate between supervised and unsupervised learning",
                                    "prerequisites": ["GO_01_01_02"],
                                    "assessment_type": "multiple_choice",
                                    "content_keywords": ["supervised learning", "unsupervised learning", "labels"]
                                }
                            ]
                        }
                    ]
                },
                "week_02": {
                    "week_number": 2,
                    "topic": "Classification & KNN", 
                    "week_display": "Week 2: Classification & KNN",
                    "learning_objectives": [
                        {
                            "lo_id": "LO_02_01",
                            "objective_name": "KNN Algorithm",
                            "description": "Understand and implement k-nearest neighbors",
                            "mastery_threshold": 0.8,
                            "granular_objectives": [
                                {
                                    "go_id": "GO_02_01_01",
                                    "skill_name": "KNN Concepts",
                                    "description": "Understand how KNN works",
                                    "prerequisites": ["GO_01_02_01"],
                                    "assessment_type": "problem_solving",
                                    "content_keywords": ["KNN", "classification", "distance metrics"]
                                }
                            ]
                        }
                    ]
                }
            }
        }
    
    def _validate_model_structure(self, model: Dict[str, Any]) -> None:
        """Validate that KC model has required structure"""
        required_keys = ["course_info", "week_navigation"]
        for key in required_keys:
            if key not in model:
                raise ValueError(f"KC model missing required key: {key}")
        
        # Validate course_info
        course_info_keys = ["course_code", "course_name", "total_weeks"]
        for key in course_info_keys:
            if key not in model["course_info"]:
                raise ValueError(f"course_info missing required key: {key}")
    
    def get_week_content(self, course_code: str, week_number: int) -> WeekContent:
        """Get content for a specific week"""
        kc_model = self.load_course_model(course_code)
        week_key = f"week_{week_number:02d}"
        
        if week_key not in kc_model["week_navigation"]:
            raise ValueError(f"Week {week_number} not found in course {course_code}")
        
        week_data = kc_model["week_navigation"][week_key]
        
        # Parse learning objectives
        learning_objectives = []
        for lo_data in week_data.get("learning_objectives", []):
            granular_objectives = [
                GranularObjective(
                    go_id=go["go_id"],
                    skill_name=go["skill_name"],
                    description=go.get("description", ""),
                    cognitive_level=go.get("cognitive_level", "Understand"),  # ADD
                    mastery_threshold=go.get("mastery_threshold", 0.7),  # ADD
                    estimated_time_minutes=go.get("estimated_time_minutes", 15),  # ADD
                    skill_category=go.get("skill_category", "conceptual"),  # ADD
                    complexity=go.get("complexity", "basic"),  # ADD
                    conceptual_tags=go.get("conceptual_tags", go.get("content_keywords", [])),  # UPDATED
                    prerequisite_concepts=go.get("prerequisite_concepts", go.get("prerequisites", []))  # UPDATED
                )
                for go in lo_data.get("granular_objectives", [])
            ]
            
            learning_objectives.append(
                LearningObjective(
                    lo_id=lo_data["lo_id"],
                    objective_name=lo_data.get("objective_name", lo_data.get("title", "")),
                    description=lo_data.get("description", ""),
                    granular_objectives=granular_objectives,
                    mastery_threshold=lo_data.get("mastery_threshold", 0.8)
                )
            )
        
        return WeekContent(
            week_id=week_key,
            week_number=week_number,
            topic=week_data.get("topic", week_data.get("week_name", f"Week {week_number}")),
            learning_objectives=learning_objectives
        )
    

    
    def get_all_weeks(self, course_code: str) -> List[WeekContent]:
        """Get all weeks for a course in order"""
        kc_model = self.load_course_model(course_code)
        total_weeks = kc_model["course_info"]["total_weeks"]
        
        weeks = []
        for week_num in range(1, min(total_weeks + 1, 13)):  # Cap at 12 weeks for safety
            try:
                week_content = self.get_week_content(course_code, week_num)
                weeks.append(week_content)
            except ValueError:
                logger.warning(f"Week {week_num} not found in course {course_code}")
                
        return weeks
    
    def get_learning_objective(self, course_code: str, lo_id: str) -> Optional[LearningObjective]:
        """
        Get a specific learning objective by ID
        
        Args:
            course_code: Course identifier
            lo_id: Learning objective ID
            
        Returns:
            LearningObjective if found, None otherwise
        """
        weeks = self.get_all_weeks(course_code)
        
        for week in weeks:
            for lo in week.learning_objectives:
                if lo.lo_id == lo_id:
                    return lo
        
        return None
    
    def get_granular_objective(self, course_code: str, go_id: str) -> Optional[GranularObjective]:
        """
        Get a specific granular objective by ID
        
        Args:
            course_code: Course identifier
            go_id: Granular objective ID
            
        Returns:
            GranularObjective if found, None otherwise
        """
        weeks = self.get_all_weeks(course_code)
        
        for week in weeks:
            for lo in week.learning_objectives:
                for go in lo.granular_objectives:
                    if go.go_id == go_id:
                        return go
        
        return None
    
    def get_prerequisite_chain(self, course_code: str, go_id: str) -> List[str]:
        """
        Get all prerequisites for a granular objective (recursive)
        
        Args:
            course_code: Course identifier
            go_id: Granular objective ID
            
        Returns:
            List of prerequisite GO IDs in dependency order
        """
        visited = set()
        prerequisites = []
        
        def _collect_prereqs(current_go_id: str):
            if current_go_id in visited:
                return
            
            visited.add(current_go_id)
            go = self.get_granular_objective(course_code, current_go_id)
            
            if go:
                for prereq_id in go.prerequisites:
                    _collect_prereqs(prereq_id)
                    if prereq_id not in prerequisites:
                        prerequisites.append(prereq_id)
        
        _collect_prereqs(go_id)
        return prerequisites
    
    def get_content_context(self, course_code: str, lo_id: str) -> Dict[str, Any]:
        """
        Get contextual information for content generation
        
        Args:
            course_code: Course identifier
            lo_id: Learning objective ID
            
        Returns:
            Dictionary with context for LLM content generation
        """
        lo = self.get_learning_objective(course_code, lo_id)
        if not lo:
            return {}
        
        # Collect all keywords and skills for RAG retrieval
        keywords = []
        skills = []
        assessment_types = set()
        
        for go in lo.granular_objectives:
            keywords.extend(go.content_keywords)
            skills.append(go.skill_name)
            assessment_types.add(go.assessment_type)
        
        # Find week context
        week_topic = ""
        week_number = 0
        for week in self.get_all_weeks(course_code):
            if any(wlo.lo_id == lo_id for wlo in week.learning_objectives):
                week_topic = week.topic
                week_number = week.week_number
                break
        
        return {
            "lo_id": lo_id,
            "objective_name": lo.objective_name,
            "week_topic": week_topic,
            "week_number": week_number,
            "keywords": list(set(keywords)),  # Unique keywords
            "skills": skills,
            "assessment_types": list(assessment_types),
            "granular_objectives": [go.to_dict() for go in lo.granular_objectives]
        }
    
    def get_unlocked_content(self, course_code: str, lo_masteries: Dict[str, float]) -> List[WeekContent]:
        """
        Get all unlocked weeks based on current mastery levels
        
        Args:
            course_code: Course identifier
            lo_masteries: Dictionary mapping LO IDs to mastery levels
            
        Returns:
            List of unlocked WeekContent objects
        """
        all_weeks = self.get_all_weeks(course_code)
        unlocked_weeks = []
        
        # Week 1 is always unlocked
        if all_weeks:
            unlocked_weeks.append(all_weeks[0])
        
        # Check subsequent weeks
        for i in range(1, len(all_weeks)):
            # Week is unlocked if previous week's LOs are mastered
            prev_week = all_weeks[i-1]
            if prev_week.is_unlocked(lo_masteries):
                unlocked_weeks.append(all_weeks[i])
            else:
                break  # Stop at first locked week
        
        return unlocked_weeks
    
    def invalidate_cache(self, course_code: str) -> None:
        """Force reload of KC model on next access"""
        cache_key = f"kc_model:{course_code}"
        try:
            if hasattr(self._cache_client, 'delete'):
                self._cache_client.delete(cache_key)
                logger.info(f"Invalidated KC model cache for {course_code}")
        except Exception as e:
            logger.warning(f"Failed to invalidate cache: {e}")


# Example usage update:
if __name__ == "__main__":
    # Initialize with Redis connection and module
    try:
        redis_conn = redis.Redis(host='localhost', port=6379, decode_responses=True)
        redis_conn.ping()
        print("Redis connection successful")
    except:
        print("Redis connection failed, using mock Redis")
        redis_conn = None
    
    if redis_conn:
        # NOW REQUIRES MODULE PARAMETER
        kc_loader = KCModelLoader(redis_conn, module="CMP511")
        
        # Load course model
        course_model = kc_loader.load_course_model("CMP511")
        print(f"Loaded course: {course_model['course_info']['course_name']}")
              
        # Get week content
        week1 = kc_loader.get_week_content("CMP511", 1)
        print(f"\nWeek 1 Topic: {week1.topic}")
        print(f"Number of LOs: {len(week1.learning_objectives)}")
        
        # Get content context for generation
        if week1.learning_objectives:
            context = kc_loader.get_content_context("CMP511", week1.learning_objectives[0].lo_id)
            print(f"\nContent context for {context['objective_name']}:")
            print(f"Keywords: {context['keywords']}")
            print(f"Skills: {context['skills']}")
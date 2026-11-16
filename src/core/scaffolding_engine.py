# File: src/core/scaffolding_engine.py

"""
Scaffolding Decision Engine for Intelligent Tutoring System
Implements CL by ZPD matrix-based scaffolding selection with fading triggers
"""
import redis
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ScaffoldingDecision:
    """Represents a scaffolding decision with all parameters"""
    strategy_type: str  # procedural, conceptual, strategic, metacognitive
    intensity_level: str  # very_high, high, medium, low
    fade_threshold: int  # consecutive correct responses before fading
    content_adaptations: Dict[str, Any]
    hint_structure: List[str]
    feedback_style: str
    
    
class ScaffoldingEngine:
    """
    Manages scaffolding decisions based on CL by ZPD matrix
    and implements fading logic based on performance
    """
    
    # CL by ZPD Scaffolding Matrix (from research)
    SCAFFOLDING_MATRIX = {
        ("low", "low"): {
            "strategy": "conceptual",
            "intensity": "high",
            "fade_threshold": 2,
            "description": "Heavy conceptual support for low-prepared learners"
        },
        ("low", "medium"): {
            "strategy": "procedural",
            "intensity": "medium",
            "fade_threshold": 3,
            "description": "Step-by-step guidance for moderate challenges"
        },
        ("low", "high"): {
            "strategy": "strategic",
            "intensity": "low",
            "fade_threshold": 4,
            "description": "Light strategic hints for well-prepared learners"
        },
        ("medium", "low"): {
            "strategy": "procedural",
            "intensity": "high",
            "fade_threshold": 2,
            "description": "Detailed procedures to reduce cognitive load"
        },
        ("medium", "medium"): {
            "strategy": "strategic",
            "intensity": "medium",
            "fade_threshold": 3,
            "description": "Balanced strategic support"
        },
        ("medium", "high"): {
            "strategy": "metacognitive",
            "intensity": "low",
            "fade_threshold": 4,
            "description": "Self-reflection prompts for advanced learners"
        },
        ("high", "low"): {
            "strategy": "conceptual",
            "intensity": "very_high",
            "fade_threshold": 2,
            "description": "Maximum support for overwhelmed learners"
        },
        ("high", "medium"): {
            "strategy": "procedural",
            "intensity": "high",
            "fade_threshold": 2,
            "description": "Structured support to manage high load"
        },
        ("high", "high"): {
            "strategy": "strategic",
            "intensity": "medium",
            "fade_threshold": 3,
            "description": "Strategic guidance despite high load"
        }
    }
    
    # Scaffolding strategy definitions
    STRATEGY_DEFINITIONS = {
        "conceptual": {
            "focus": "Understanding core concepts and relationships",
            "hint_style": "explanatory",
            "example_type": "conceptual_models",
            "feedback_emphasis": "why_and_how"
        },
        "procedural": {
            "focus": "Step-by-step problem solving processes",
            "hint_style": "sequential",
            "example_type": "worked_examples",
            "feedback_emphasis": "next_steps"
        },
        "strategic": {
            "focus": "Problem-solving strategies and approaches",
            "hint_style": "guidance",
            "example_type": "strategy_comparison",
            "feedback_emphasis": "approach_evaluation"
        },
        "metacognitive": {
            "focus": "Self-reflection and learning awareness",
            "hint_style": "reflective",
            "example_type": "self_assessment",
            "feedback_emphasis": "learning_process"
        }
    }
    
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self.fading_tracker = {}  # Track consecutive successes per user
        
    def get_scaffolding_decision(
        self,
        cl_level: str,
        zpd_level: str,
        username: str,
        learning_objective: str,
        recent_performance: List[bool]
    ) -> ScaffoldingDecision:
        """
        Determine scaffolding strategy based on CL by ZPD levels
        
        Args:
            cl_level: Cognitive load level (low/medium/high)
            zpd_level: ZPD level (low/medium/high)
            username: User identifier for fading tracking
            learning_objective: Current LO for context
            recent_performance: List of recent correct/incorrect responses
            
        Returns:
            ScaffoldingDecision with all parameters
        """
        
        # Get base strategy from matrix
        matrix_entry = self.SCAFFOLDING_MATRIX.get(
            (cl_level, zpd_level),
            self.SCAFFOLDING_MATRIX[("medium", "medium")]  # Default
        )
        
        # Check for fading
        current_intensity = self._apply_fading_logic(
            username,
            learning_objective,
            matrix_entry["intensity"],
            matrix_entry["fade_threshold"],
            recent_performance
        )
        
        # Get strategy details
        strategy_details = self.STRATEGY_DEFINITIONS[matrix_entry["strategy"]]
        
        # Build content adaptations
        content_adaptations = self._build_content_adaptations(
            matrix_entry["strategy"],
            current_intensity,
            cl_level,
            zpd_level
        )
        
        # Generate hint structure
        hint_structure = self._generate_hint_structure(
            matrix_entry["strategy"],
            current_intensity,
            strategy_details["hint_style"]
        )
        
        # Determine feedback style
        feedback_style = self._determine_feedback_style(
            strategy_details["feedback_emphasis"],
            current_intensity,
            cl_level
        )
        
        decision = ScaffoldingDecision(
            strategy_type=matrix_entry["strategy"],
            intensity_level=current_intensity,
            fade_threshold=matrix_entry["fade_threshold"],
            content_adaptations=content_adaptations,
            hint_structure=hint_structure,
            feedback_style=feedback_style
        )
        
        # Log decision
        self._log_scaffolding_decision(username, learning_objective, decision)
        
        return decision
    
    def _apply_fading_logic(
        self,
        username: str,
        learning_objective: str,
        base_intensity: str,
        fade_threshold: int,
        recent_performance: List[bool]
    ) -> str:
        """
        Apply fading logic based on consecutive correct responses
        
        Returns adjusted intensity level
        """
        
        # Track consecutive correct responses
        fading_key = f"{username}:{learning_objective}"
        
        if fading_key not in self.fading_tracker:
            self.fading_tracker[fading_key] = {
                "consecutive_correct": 0,
                "total_faded": 0
            }
        
        tracker = self.fading_tracker[fading_key]
        
        # Update consecutive correct count
        if recent_performance and recent_performance[-1]:  # Last response was correct
            tracker["consecutive_correct"] += 1
        else:
            tracker["consecutive_correct"] = 0
        
        # Check if we should fade
        if tracker["consecutive_correct"] >= fade_threshold:
            # Fade intensity
            intensity_levels = ["very_high", "high", "medium", "low", "minimal"]
            current_index = intensity_levels.index(base_intensity) if base_intensity in intensity_levels else 2
            
            # Move one level lower (toward minimal)
            if current_index < len(intensity_levels) - 1:
                new_intensity = intensity_levels[current_index + 1]
                tracker["total_faded"] += 1
                tracker["consecutive_correct"] = 0  # Reset counter
                
                logger.info(f"Fading scaffolding for {username} on {learning_objective}: {base_intensity} -> {new_intensity}")
                #UPDATED
                print(f"👤👤 Fading: {new_intensity}")
                return new_intensity
        
        return base_intensity
    
    def _build_content_adaptations(
        self,
        strategy: str,
        intensity: str,
        cl_level: str,
        zpd_level: str
    ) -> Dict[str, Any]:
        """
        Build specific content adaptations based on strategy and intensity
        """
        
        adaptations = {
            "content_density": self._get_content_density(intensity),
            "example_count": self._get_example_count(intensity),
            "visualization_level": self._get_visualization_level(strategy, intensity),
            "interaction_type": self._get_interaction_type(strategy, cl_level),
            "pacing": self._get_pacing(cl_level, intensity)
        }
        
        # Strategy-specific adaptations
        if strategy == "conceptual":
            adaptations["concept_maps"] = intensity in ["very_high", "high"]
            adaptations["analogies"] = True
            adaptations["prerequisite_review"] = zpd_level == "low"
            
        elif strategy == "procedural":
            adaptations["step_breakdown"] = {
                "very_high": "micro_steps",
                "high": "detailed_steps",
                "medium": "standard_steps",
                "low": "overview_only"
            }.get(intensity, "standard_steps")
            adaptations["worked_examples"] = intensity in ["very_high", "high", "medium"]
            
        elif strategy == "strategic":
            adaptations["strategy_comparison"] = True
            adaptations["decision_trees"] = intensity in ["high", "medium"]
            adaptations["heuristics"] = True
            
        elif strategy == "metacognitive":
            adaptations["reflection_prompts"] = True
            adaptations["self_assessment"] = True
            adaptations["learning_analytics"] = True
        
        return adaptations
    
    def _generate_hint_structure(
        self,
        strategy: str,
        intensity: str,
        hint_style: str
    ) -> List[str]:
        """
        Generate hint structure based on strategy and intensity
        """
        
        hint_counts = {
            "very_high": 5,
            "high": 4,
            "medium": 3,
            "low": 2,
            "minimal": 1
        }
        
        num_hints = hint_counts.get(intensity, 3)
        
        # Generate hint templates based on style
        if hint_style == "explanatory":
            hints = [
                "Think about the fundamental concept...",
                "Remember that this relates to...",
                "The key principle here is...",
                "Consider how this connects to...",
                "The underlying reason is..."
            ][:num_hints]
            
        elif hint_style == "sequential":
            hints = [
                "First, identify...",
                "Next, calculate...",
                "Then, apply...",
                "After that, verify...",
                "Finally, conclude..."
            ][:num_hints]
            
        elif hint_style == "guidance":
            hints = [
                "What strategy might work here?",
                "Consider approaching this by...",
                "A useful technique would be...",
                "Try breaking this down into...",
                "The pattern suggests..."
            ][:num_hints]
            
        elif hint_style == "reflective":
            hints = [
                "What do you already know about this?",
                "How does this compare to previous problems?",
                "What makes this challenging?",
                "What would happen if...?",
                "How confident are you and why?"
            ][:num_hints]
        
        else:
            hints = [f"Hint {i+1}" for i in range(num_hints)]
        
        return hints
    
    def _determine_feedback_style(
        self,
        emphasis: str,
        intensity: str,
        cl_level: str
    ) -> str:
        """
        Determine feedback style based on emphasis and learner state
        """
        
        # Base style on emphasis
        base_styles = {
            "why_and_how": "explanatory_detailed",
            "next_steps": "directive_supportive",
            "approach_evaluation": "analytical_comparative",
            "learning_process": "reflective_metacognitive"
        }
        
        style = base_styles.get(emphasis, "balanced")
        
        # Modify based on intensity and cognitive load
        if intensity in ["very_high", "high"]:
            style += "_encouraging"
        elif cl_level == "high":
            style += "_concise"
        else:
            style += "_balanced"
        
        return style
    
    def _get_content_density(self, intensity: str) -> str:
        """Determine appropriate content density"""
        density_map = {
            "very_high": "minimal",
            "high": "low",
            "medium": "moderate",
            "low": "standard",
            "minimal": "full"
        }
        return density_map.get(intensity, "moderate")
    
    def _get_example_count(self, intensity: str) -> int:
        """Determine number of examples to provide"""
        example_map = {
            "very_high": 3,
            "high": 2,
            "medium": 2,
            "low": 1,
            "minimal": 1
        }
        return example_map.get(intensity, 2)
    
    def _get_visualization_level(self, strategy: str, intensity: str) -> str:
        """Determine visualization requirements"""
        if strategy in ["conceptual", "procedural"] and intensity in ["very_high", "high"]:
            return "rich_visual"
        elif strategy == "strategic":
            return "moderate_visual"
        else:
            return "minimal_visual"
    
    def _get_interaction_type(self, strategy: str, cl_level: str) -> str:
        """Determine interaction type based on strategy and cognitive load"""
        if cl_level == "high":
            return "guided_simple"
        elif strategy == "metacognitive":
            return "open_reflective"
        elif strategy in ["procedural", "conceptual"]:
            return "structured_interactive"
        else:
            return "exploratory"
    
    def _get_pacing(self, cl_level: str, intensity: str) -> str:
        """Determine appropriate pacing"""
        if cl_level == "high" or intensity in ["very_high", "high"]:
            return "slow_paced"
        elif cl_level == "low" and intensity == "minimal":
            return "self_paced_fast"
        else:
            return "moderate_paced"
    
    def _log_scaffolding_decision(
            self,
            username: str,
            learning_objective: str,
            decision: ScaffoldingDecision
        ) -> None:
            """Log scaffolding decision for analysis"""
            
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "username": username,
                "learning_objective": learning_objective,
                "strategy": decision.strategy_type,
                "intensity": decision.intensity_level,
                "fade_threshold": decision.fade_threshold,
                "adaptations": decision.content_adaptations
            }
            
            try:
                # Store in Redis for analysis - handle LEARedisClient properly
                key = f"scaffolding_log:{username}:{learning_objective}"
                
                # Try to get the underlying Redis client
                if hasattr(self.redis_client, 'get_redis'):
                    redis_conn = self.redis_client.get_redis()
                    redis_conn.lpush(key, json.dumps(log_entry))
                    redis_conn.ltrim(key, 0, 99)  # Keep last 100 decisions
                elif hasattr(self.redis_client, 'lpush'):
                    # Direct Redis client
                    self.redis_client.lpush(key, json.dumps(log_entry))
                    self.redis_client.ltrim(key, 0, 99) # Keep last 100 decisions
                else:
                    # LEARedisClient might have different methods - try alternative
                    logger.warning(f"Redis client doesn't support lpush directly, skipping scaffolding log")
                    # Could implement alternative storage or create a method in LEARedisClient
                    
            except Exception as e:
                logger.warning(f"Failed to log scaffolding decision: {e}")
                # Don't let logging failures break the scaffolding decision
    
    # def _log_scaffolding_decision(
    #     self,
    #     username: str,
    #     learning_objective: str,
    #     decision: ScaffoldingDecision
    # ) -> None:
    #     """Log scaffolding decision for analysis"""
        
    #     log_entry = {
    #         "timestamp": datetime.now().isoformat(),
    #         "username": username,
    #         "learning_objective": learning_objective,
    #         "strategy": decision.strategy_type,
    #         "intensity": decision.intensity_level,
    #         "fade_threshold": decision.fade_threshold,
    #         "adaptations": decision.content_adaptations
    #     }
        
    #     # Store in Redis for analysis
    #     key = f"scaffolding_log:{username}:{learning_objective}"
    #     self.redis_client.lpush(key, json.dumps(log_entry))
    #     self.redis_client.ltrim(key, 0, 99)  # Keep last 100 decisions
    
    def get_fading_status(self, username: str, learning_objective: str) -> Dict[str, Any]:
        """Get current fading status for a user on an objective"""
        
        fading_key = f"{username}:{learning_objective}"
        
        if fading_key not in self.fading_tracker:
            return {
                "consecutive_correct": 0,
                "total_faded": 0,
                "current_status": "not_started"
            }
        
        tracker = self.fading_tracker[fading_key]
        
        return {
            "consecutive_correct": tracker["consecutive_correct"],
            "total_faded": tracker["total_faded"],
            "current_status": "active_fading" if tracker["total_faded"] > 0 else "building"
        }
    
    def reset_fading(self, username: str, learning_objective: str) -> None:
        """Reset fading progress for a user on an objective"""
        
        fading_key = f"{username}:{learning_objective}"
        if fading_key in self.fading_tracker:
            self.fading_tracker[fading_key] = {
                "consecutive_correct": 0,
                "total_faded": 0
            }
            logger.info(f"Reset fading progress for {username} on {learning_objective}")


# Example usage
if __name__ == "__main__":
    # Initialize scaffolding engine
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    engine = ScaffoldingEngine(redis_client)
    
    # Get scaffolding decision
    decision = engine.get_scaffolding_decision(
        cl_level="medium",
        zpd_level="medium",
        username="test_user",
        learning_objective="LO_01_01",
        recent_performance=[True, True, False, True, True]
    )
    
    print(f"Scaffolding Decision:")
    print(f"  Strategy: {decision.strategy_type}")
    print(f"  Intensity: {decision.intensity_level}")
    print(f"  Fade Threshold: {decision.fade_threshold}")
    print(f"  Content Adaptations: {json.dumps(decision.content_adaptations, indent=2)}")
    print(f"  Hints Available: {len(decision.hint_structure)}")
    print(f"  Feedback Style: {decision.feedback_style}")
    
    # Check fading status
    status = engine.get_fading_status("test_user", "LO_01_01")
    print(f"\nFading Status:")
    print(f"  Consecutive Correct: {status['consecutive_correct']}")
    print(f"  Total Faded: {status['total_faded']}")
    print(f"  Status: {status['current_status']}")
# File: src/simulation/lea_simulation_framework.py
"""
LEA Simulation Framework with Learner Agents
Comprehensive simulation system for automated testing and metrics validation
"""

import mesa
import random
import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path

# Import LEA components
from src.core.enhanced_metrics_integration import EnhancedMetricsIntegration, LEASimulationFramework

class LearnerPersonality(Enum):
    """Different learner personality types for simulation"""
    CONFIDENT_QUICK = "confident_quick"      # High learning rate, low need for scaffolding
    METHODICAL_STEADY = "methodical_steady"  # Moderate learning rate, consistent effort
    STRUGGLING_PERSISTENT = "struggling_persistent"  # Low learning rate, high effort
    EASILY_DISTRACTED = "easily_distracted"  # Variable performance, needs engagement
    PERFECTIONIST = "perfectionist"          # High standards, may get frustrated
    CREATIVE_DIVERGENT = "creative_divergent" # Non-linear thinking, creative solutions

@dataclass
class LearnerProfile:
    """Comprehensive learner profile for simulation"""
    personality: LearnerPersonality
    learning_rate: float          # 0.1-0.9 (how quickly they learn)
    initial_motivation: float     # 0.3-0.9 (starting motivation)
    cognitive_capacity: float     # 3.0-8.0 (cognitive load tolerance)
    attention_span: float         # 0.3-0.9 (ability to maintain focus)
    help_seeking: float          # 0.2-0.8 (likelihood to ask for help)
    persistence: float           # 0.3-0.9 (how long they keep trying)
    metacognition: float         # 0.2-0.8 (self-awareness of learning)
    
    # Performance characteristics
    accuracy_variance: float     # How much performance varies
    time_per_interaction: float  # Base time for interactions
    fatigue_rate: float         # How quickly they get tired
    
    # Interaction patterns
    question_types_preferred: List[str]
    scaffolding_preference: str  # 'high', 'medium', 'low'
    feedback_sensitivity: float  # How much feedback affects them

class LEALearnerAgent(mesa.Agent):
    """Sophisticated learner agent that interacts with real LEA system"""
    
    def __init__(self, unique_id: int, model, profile: LearnerProfile):
        super().__init__(unique_id, model)
        self.profile = profile
        self.username = f"sim_learner_{unique_id}"
        
        # Dynamic state variables
        self.current_motivation = profile.initial_motivation
        self.current_cognitive_load = 5.0  # Starting CL
        self.current_mastery = {}  # Track mastery by topic
        self.fatigue_level = 0.0
        self.consecutive_correct = 0
        self.consecutive_incorrect = 0
        
        # Learning session state
        self.session_active = False
        self.session_start_time = None
        self.interaction_count = 0
        self.questions_asked = 0
        self.help_requests = 0
        
        # Performance tracking
        self.performance_history = []
        self.engagement_history = []
        self.cognitive_load_history = []
        
        # Interaction patterns
        self.last_interaction_time = None
        self.preferred_difficulty = 0.5  # Adaptive preference
        
        print(f"DEBUG: Created learner {unique_id} with personality {profile.personality.value}")
    
    def step(self):
        """Execute one learning step"""
        if not self.session_active:
            return
        
        # Check if agent should continue (attention span, fatigue)
        if not self._should_continue_session():
            self._end_session()
            return
        
        # Generate learning interaction based on personality and state
        interaction_type = self._choose_interaction_type()
        
        if interaction_type == "quiz_question":
            self._attempt_quiz_question()
        elif interaction_type == "ask_question":
            self._ask_question()
        elif interaction_type == "request_help":
            self._request_help()
        elif interaction_type == "take_break":
            self._take_short_break()
        
        # Update agent state
        self._update_state()
        self.interaction_count += 1
    
    def start_session(self, session_type: str = "mixed"):
        """Start a learning session"""
        self.session_active = True
        self.session_start_time = datetime.now()
        self.interaction_count = 0
        self.fatigue_level = 0.0
        
        print(f"DEBUG: Learner {self.unique_id} starting {session_type} session")
    
    def _should_continue_session(self) -> bool:
        """Decide if agent should continue the session"""
        # Check fatigue
        if self.fatigue_level > 0.8:
            return False
        
        # Check motivation
        if self.current_motivation < 0.2:
            return False
        
        # Check attention span
        session_duration = (datetime.now() - self.session_start_time).total_seconds() / 60
        max_duration = self.profile.attention_span * 60  # Convert to minutes
        
        if session_duration > max_duration:
            return False
        
        # Check if reached interaction limit
        max_interactions = int(self.profile.attention_span * 50)  # Variable based on attention
        if self.interaction_count > max_interactions:
            return False
        
        return True
    
    def _choose_interaction_type(self) -> str:
        """Choose what type of interaction to do next"""
        # Base probabilities
        probabilities = {
            "quiz_question": 0.4,
            "ask_question": 0.3,
            "request_help": 0.2,
            "take_break": 0.1
        }
        
        # Adjust based on personality
        if self.profile.personality == LearnerPersonality.CONFIDENT_QUICK:
            probabilities["quiz_question"] = 0.6
            probabilities["request_help"] = 0.1
        elif self.profile.personality == LearnerPersonality.STRUGGLING_PERSISTENT:
            probabilities["request_help"] = 0.4
            probabilities["quiz_question"] = 0.3
        elif self.profile.personality == LearnerPersonality.EASILY_DISTRACTED:
            probabilities["take_break"] = 0.2
            probabilities["ask_question"] = 0.4
        elif self.profile.personality == LearnerPersonality.PERFECTIONIST:
            probabilities["quiz_question"] = 0.5
            probabilities["request_help"] = 0.3
        
        # Adjust based on current state
        if self.current_cognitive_load > 7:
            probabilities["take_break"] += 0.2
            probabilities["request_help"] += 0.1
        
        if self.consecutive_incorrect > 2:
            probabilities["request_help"] += 0.3
            probabilities["quiz_question"] -= 0.2
        
        if self.current_motivation < 0.4:
            probabilities["take_break"] += 0.2
        
        # Normalize probabilities
        total = sum(probabilities.values())
        probabilities = {k: v/total for k, v in probabilities.items()}
        
        # Choose based on weighted random
        return np.random.choice(list(probabilities.keys()), p=list(probabilities.values()))
    
    def _attempt_quiz_question(self):
        """Simulate attempting a quiz question"""
        # Generate question characteristics
        intended_difficulty = self._get_preferred_difficulty()
        question_type = self._get_preferred_question_type()
        
        # Simulate LEA orchestrator processing
        orchestrator_data = self._simulate_orchestrator_response()
        
        # Calculate success probability based on agent characteristics
        success_prob = self._calculate_success_probability(intended_difficulty, orchestrator_data)
        
        # Determine outcome
        is_correct = np.random.random() < success_prob
        response_time = self._calculate_response_time(intended_difficulty, is_correct)
        
        # Update performance tracking
        self._record_quiz_performance(is_correct, intended_difficulty, response_time, orchestrator_data)
        
        # Update consecutive counters
        if is_correct:
            self.consecutive_correct += 1
            self.consecutive_incorrect = 0
        else:
            self.consecutive_correct = 0
            self.consecutive_incorrect += 1
        
        # Update motivation based on outcome and personality
        self._update_motivation_from_performance(is_correct, orchestrator_data)
        
        print(f"DEBUG: Learner {self.unique_id} answered quiz question: {'correct' if is_correct else 'incorrect'} (prob={success_prob:.2f})")
    
    def _ask_question(self):
        """Simulate asking a question"""
        self.questions_asked += 1
        
        # Generate question based on current understanding and personality
        question_complexity = self._determine_question_complexity()
        
        # Simulate getting an answer (affects motivation and understanding)
        answer_quality = np.random.uniform(0.6, 0.9)  # LEA generally gives good answers
        
        # Update understanding based on answer
        learning_gain = answer_quality * self.profile.learning_rate * 0.1
        self._update_topic_mastery(learning_gain)
        
        # Positive motivation boost from getting help
        motivation_boost = 0.05 + (answer_quality * 0.1)
        self.current_motivation = min(1.0, self.current_motivation + motivation_boost)
        
        print(f"DEBUG: Learner {self.unique_id} asked question (complexity={question_complexity:.2f})")
    
    def _request_help(self):
        """Simulate requesting help or scaffolding"""
        self.help_requests += 1
        
        # More likely if struggling or if personality is help-seeking
        help_effectiveness = self.profile.help_seeking * np.random.uniform(0.7, 0.95)
        
        # Reduce cognitive load
        cl_reduction = help_effectiveness * 2.0
        self.current_cognitive_load = max(2.0, self.current_cognitive_load - cl_reduction)
        
        # Increase understanding
        learning_gain = help_effectiveness * 0.15
        self._update_topic_mastery(learning_gain)
        
        # Mixed motivation effect (help is good, but may feel dependent)
        if self.profile.personality == LearnerPersonality.PERFECTIONIST:
            motivation_change = -0.02  # Slight negative for perfectionist
        else:
            motivation_change = 0.08   # Generally positive
        
        self.current_motivation = np.clip(self.current_motivation + motivation_change, 0, 1)
        
        print(f"DEBUG: Learner {self.unique_id} requested help (effectiveness={help_effectiveness:.2f})")
    
    def _take_short_break(self):
        """Simulate taking a short break"""
        # Reduce fatigue and cognitive load
        fatigue_reduction = np.random.uniform(0.1, 0.3)
        self.fatigue_level = max(0, self.fatigue_level - fatigue_reduction)
        
        cl_reduction = np.random.uniform(1.0, 2.0)
        self.current_cognitive_load = max(2.0, self.current_cognitive_load - cl_reduction)
        
        # Small motivation boost from rest
        self.current_motivation = min(1.0, self.current_motivation + 0.05)
        
        print(f"DEBUG: Learner {self.unique_id} took break (fatigue reduced by {fatigue_reduction:.2f})")
    
    def _simulate_orchestrator_response(self) -> Dict[str, Any]:
        """Simulate what the LEA orchestrator would return for this learner"""
        
        # Calculate ZPD score based on current state
        ideal_cl = 5.0  # Ideal cognitive load
        cl_distance = abs(self.current_cognitive_load - ideal_cl)
        zpd_score = max(0.1, 1.0 - (cl_distance / 5.0))  # Further from ideal = lower ZPD
        
        # Adjust ZPD based on recent performance
        if self.consecutive_correct > 2:
            zpd_score = min(1.0, zpd_score + 0.2)  # In good zone
        elif self.consecutive_incorrect > 2:
            zpd_score = max(0.1, zpd_score - 0.3)  # Struggling
        
        # Scaffolding decision based on current state
        if self.current_cognitive_load > 7 or self.consecutive_incorrect > 1:
            scaffolding = "increase_support"
        elif self.current_cognitive_load < 3 or self.consecutive_correct > 3:
            scaffolding = "reduce_support"
        else:
            scaffolding = "maintain_flow"
        
        return {
            'cognitive_state': type('CognitiveState', (), {
                'cognitive_load': self.current_cognitive_load,
                'zpd_score': zpd_score,
                'motivation_score': self.current_motivation
            })(),
            'scaffolding_strategy': {
                'intervention_type': scaffolding,
                'support_level': self._determine_support_level()
            }
        }
    
    def _calculate_success_probability(self, difficulty: float, orchestrator_data: Dict) -> float:
        """Calculate probability of success based on agent state and question difficulty"""
        
        # Base success rate from learning ability
        base_success = self.profile.learning_rate
        
        # Adjust for difficulty
        difficulty_factor = max(0.1, 1.0 - (difficulty - 0.5))
        
        # Adjust for current cognitive load
        cl_factor = 1.0 - (max(0, self.current_cognitive_load - 5.0) / 5.0)  # Penalty for high CL
        
        # Adjust for motivation
        motivation_factor = 0.5 + (self.current_motivation * 0.5)
        
        # Adjust for fatigue
        fatigue_factor = 1.0 - self.fatigue_level
        
        # ZPD bonus - better performance when in optimal zone
        zpd_score = orchestrator_data['cognitive_state'].zpd_score
        zpd_bonus = zpd_score * 0.3  # Up to 30% bonus for good ZPD
        
        # Recent performance momentum
        momentum = 0
        if self.consecutive_correct > 0:
            momentum = min(0.2, self.consecutive_correct * 0.05)  # Positive momentum
        elif self.consecutive_incorrect > 0:
            momentum = max(-0.3, -self.consecutive_incorrect * 0.1)  # Negative momentum
        
        # Combine factors
        success_prob = (base_success * difficulty_factor * cl_factor * 
                       motivation_factor * fatigue_factor) + zpd_bonus + momentum
        
        # Add personality-specific adjustments
        if self.profile.personality == LearnerPersonality.CONFIDENT_QUICK:
            success_prob += 0.1
        elif self.profile.personality == LearnerPersonality.STRUGGLING_PERSISTENT:
            success_prob -= 0.15
        elif self.profile.personality == LearnerPersonality.PERFECTIONIST:
            # Perfectionist has high variance - either very good or frustrated
            if success_prob > 0.6:
                success_prob += 0.1
            else:
                success_prob -= 0.1
        
        # Add random variance based on personality
        variance = self.profile.accuracy_variance
        noise = np.random.normal(0, variance)
        success_prob += noise
        
        return np.clip(success_prob, 0.05, 0.95)  # Keep within bounds
    
    def _get_preferred_difficulty(self) -> float:
        """Get preferred difficulty level for this learner"""
        # Base preference on recent performance
        if self.consecutive_correct > 2:
            self.preferred_difficulty = min(0.8, self.preferred_difficulty + 0.1)
        elif self.consecutive_incorrect > 1:
            self.preferred_difficulty = max(0.2, self.preferred_difficulty - 0.1)
        
        # Add personality adjustment
        if self.profile.personality == LearnerPersonality.CONFIDENT_QUICK:
            return min(0.9, self.preferred_difficulty + 0.2)
        elif self.profile.personality == LearnerPersonality.STRUGGLING_PERSISTENT:
            return max(0.3, self.preferred_difficulty - 0.1)
        
        return self.preferred_difficulty
    
    def _get_preferred_question_type(self) -> str:
        """Get preferred question type based on personality"""
        preferences = self.profile.question_types_preferred
        if preferences:
            return np.random.choice(preferences)
        return "multiple_choice"
    
    def _calculate_response_time(self, difficulty: float, is_correct: bool) -> float:
        """Calculate response time based on difficulty and outcome"""
        base_time = self.profile.time_per_interaction
        
        # Adjust for difficulty
        difficulty_multiplier = 0.8 + (difficulty * 0.6)
        
        # Adjust for correctness (wrong answers often take longer due to uncertainty)
        correctness_multiplier = 1.0 if is_correct else 1.3
        
        # Adjust for cognitive load
        cl_multiplier = 1.0 + (max(0, self.current_cognitive_load - 5.0) / 10.0)
        
        # Personality adjustments
        if self.profile.personality == LearnerPersonality.CONFIDENT_QUICK:
            personality_multiplier = 0.7
        elif self.profile.personality == LearnerPersonality.METHODICAL_STEADY:
            personality_multiplier = 1.2
        elif self.profile.personality == LearnerPersonality.PERFECTIONIST:
            personality_multiplier = 1.4  # Takes time to be sure
        else:
            personality_multiplier = 1.0
        
        response_time = (base_time * difficulty_multiplier * correctness_multiplier * 
                        cl_multiplier * personality_multiplier)
        
        # Add random variance
        variance = response_time * 0.3
        response_time += np.random.normal(0, variance)
        
        return max(5.0, response_time)  # Minimum 5 seconds
    
    def _record_quiz_performance(self, is_correct: bool, difficulty: float, 
                                response_time: float, orchestrator_data: Dict):
        """Record performance data for analysis"""
        performance_record = {
            'timestamp': datetime.now(),
            'is_correct': is_correct,
            'difficulty': difficulty,
            'response_time': response_time,
            'cognitive_load': self.current_cognitive_load,
            'motivation': self.current_motivation,
            'fatigue': self.fatigue_level,
            'zpd_score': orchestrator_data['cognitive_state'].zpd_score,
            'scaffolding': orchestrator_data['scaffolding_strategy']['intervention_type'],
            'consecutive_correct': self.consecutive_correct,
            'consecutive_incorrect': self.consecutive_incorrect
        }
        
        self.performance_history.append(performance_record)
        
        # Keep history manageable
        if len(self.performance_history) > 100:
            self.performance_history = self.performance_history[-100:]
    
    def _update_motivation_from_performance(self, is_correct: bool, orchestrator_data: Dict):
        """Update motivation based on performance and personality"""
        base_change = 0.1 if is_correct else -0.08
        
        # Personality-specific adjustments
        if self.profile.personality == LearnerPersonality.PERFECTIONIST:
            if is_correct:
                base_change = 0.05  # Less boost from success
            else:
                base_change = -0.15  # More penalty from failure
        
        elif self.profile.personality == LearnerPersonality.EASILY_DISTRACTED:
            base_change *= 1.5  # More volatile motivation
        
        elif self.profile.personality == LearnerPersonality.STRUGGLING_PERSISTENT:
            if not is_correct:
                base_change = -0.05  # Less penalty - more persistent
        
        # ZPD effect on motivation
        zpd_score = orchestrator_data['cognitive_state'].zpd_score
        if zpd_score > 0.7:  # In good zone
            base_change += 0.02
        elif zpd_score < 0.3:  # Struggling zone
            base_change -= 0.03
        
        # Apply feedback sensitivity
        base_change *= self.profile.feedback_sensitivity
        
        # Update motivation
        self.current_motivation = np.clip(self.current_motivation + base_change, 0.1, 1.0)
    
    def _update_topic_mastery(self, learning_gain: float):
        """Update mastery for current topics"""
        # Simplified mastery update
        current_topic = "general"  # Would be more specific in real implementation
        
        if current_topic not in self.current_mastery:
            self.current_mastery[current_topic] = 0.0
        
        self.current_mastery[current_topic] = min(1.0, 
            self.current_mastery[current_topic] + learning_gain)
    
    def _determine_question_complexity(self) -> float:
        """Determine complexity of question agent would ask"""
        # Base complexity on current understanding and personality
        base_complexity = 0.5
        
        # Adjust based on metacognition (self-awareness)
        if self.profile.metacognition > 0.6:
            # Good metacognition leads to more targeted questions
            if self.consecutive_incorrect > 1:
                base_complexity = 0.3  # Asks about basics when struggling
            else:
                base_complexity = 0.7  # Asks deeper questions when doing well
        
        # Personality adjustments
        if self.profile.personality == LearnerPersonality.CREATIVE_DIVERGENT:
            base_complexity += 0.2  # Asks more complex, creative questions
        
        return np.clip(base_complexity, 0.1, 0.9)
    
    def _determine_support_level(self) -> str:
        """Determine appropriate support level for this learner's current state"""
        if self.current_cognitive_load > 7 or self.consecutive_incorrect > 2:
            return "high"
        elif self.current_cognitive_load < 3 or self.consecutive_correct > 3:
            return "low"
        else:
            return "medium"
    
    def _update_state(self):
        """Update agent state after interaction"""
        # Increase fatigue
        fatigue_increase = 0.02 + (self.current_cognitive_load / 100.0)
        fatigue_increase *= self.profile.fatigue_rate
        self.fatigue_level = min(1.0, self.fatigue_level + fatigue_increase)
        
        # Slight cognitive load increase over time (mental effort)
        cl_increase = np.random.uniform(0.05, 0.15)
        self.current_cognitive_load = min(10.0, self.current_cognitive_load + cl_increase)
        
        # Natural motivation decay
        motivation_decay = 0.01 * (1.0 - self.profile.persistence)
        self.current_motivation = max(0.1, self.current_motivation - motivation_decay)
    
    def _end_session(self):
        """End the learning session"""
        self.session_active = False
        session_duration = (datetime.now() - self.session_start_time).total_seconds() / 60
        
        print(f"DEBUG: Learner {self.unique_id} ended session after {session_duration:.1f} minutes, "
              f"{self.interaction_count} interactions")
    
    def get_session_summary(self) -> Dict[str, Any]:
        """Get summary of agent's learning session"""
        if not self.performance_history:
            return {"error": "No performance data available"}
        
        correct_answers = sum(1 for p in self.performance_history if p['is_correct'])
        total_answers = len(self.performance_history)
        
        return {
            'learner_id': self.unique_id,
            'personality': self.profile.personality.value,
            'session_duration_minutes': (datetime.now() - self.session_start_time).total_seconds() / 60,
            'total_interactions': self.interaction_count,
            'quiz_attempts': total_answers,
            'questions_asked': self.questions_asked,
            'help_requests': self.help_requests,
            'accuracy': correct_answers / total_answers if total_answers > 0 else 0,
            'final_motivation': self.current_motivation,
            'final_cognitive_load': self.current_cognitive_load,
            'fatigue_level': self.fatigue_level,
            'avg_response_time': np.mean([p['response_time'] for p in self.performance_history]),
            'mastery_levels': self.current_mastery.copy(),
            'performance_trend': self._calculate_performance_trend()
        }
    
    def _calculate_performance_trend(self) -> str:
        """Calculate if performance is improving, declining, or stable"""
        if len(self.performance_history) < 5:
            return "insufficient_data"
        
        recent_accuracy = np.mean([p['is_correct'] for p in self.performance_history[-5:]])
        earlier_accuracy = np.mean([p['is_correct'] for p in self.performance_history[:5]])
        
        if recent_accuracy > earlier_accuracy + 0.1:
            return "improving"
        elif recent_accuracy < earlier_accuracy - 0.1:
            return "declining"
        else:
            return "stable"

class LEASimulationModel(mesa.Model):
    """Mesa model for LEA simulation with multiple learner agents"""
    
    def __init__(self, num_agents: int = 10, metrics_integration: EnhancedMetricsIntegration = None):
        super().__init__()
        self.num_agents = num_agents
        self.metrics_integration = metrics_integration
        self.running = True
        
        # Create scheduler
        self.schedule = mesa.time.RandomActivation(self)
        
        # Create learner agents with diverse profiles
        for i in range(num_agents):
            profile = self._create_learner_profile(i)
            agent = LEALearnerAgent(i, self, profile)
            self.schedule.add(agent)
        
        # Start all agents in learning sessions
        for agent in self.schedule.agents:
            agent.start_session("mixed")
        
        print(f"DEBUG: LEA Simulation Model created with {num_agents} agents")
    
    def _create_learner_profile(self, agent_id: int) -> LearnerProfile:
        """Create diverse learner profiles"""
        # Cycle through personalities
        personalities = list(LearnerPersonality)
        personality = personalities[agent_id % len(personalities)]
        
        # Base characteristics with personality-specific adjustments
        if personality == LearnerPersonality.CONFIDENT_QUICK:
            profile = LearnerProfile(
                personality=personality,
                learning_rate=np.random.uniform(0.7, 0.9),
                initial_motivation=np.random.uniform(0.7, 0.9),
                cognitive_capacity=np.random.uniform(6.0, 8.0),
                attention_span=np.random.uniform(0.6, 0.8),
                help_seeking=np.random.uniform(0.2, 0.4),
                persistence=np.random.uniform(0.6, 0.8),
                metacognition=np.random.uniform(0.6, 0.8),
                accuracy_variance=0.1,
                time_per_interaction=np.random.uniform(20, 40),
                fatigue_rate=0.8,
                question_types_preferred=["multiple_choice", "true_false"],
                scaffolding_preference="low",
                feedback_sensitivity=0.8
            )
        
        elif personality == LearnerPersonality.METHODICAL_STEADY:
            profile = LearnerProfile(
                personality=personality,
                learning_rate=np.random.uniform(0.5, 0.7),
                initial_motivation=np.random.uniform(0.6, 0.8),
                cognitive_capacity=np.random.uniform(4.0, 6.0),
                attention_span=np.random.uniform(0.7, 0.9),
                help_seeking=np.random.uniform(0.4, 0.6),
                persistence=np.random.uniform(0.7, 0.9),
                metacognition=np.random.uniform(0.5, 0.7),
                accuracy_variance=0.05,
                time_per_interaction=np.random.uniform(45, 70),
                fatigue_rate=0.6,
                question_types_preferred=["multiple_choice", "fill_in_blank"],
                scaffolding_preference="medium",
                feedback_sensitivity=0.7
            )
        
        elif personality == LearnerPersonality.STRUGGLING_PERSISTENT:
            profile = LearnerProfile(
                personality=personality,
                learning_rate=np.random.uniform(0.2, 0.4),
                initial_motivation=np.random.uniform(0.5, 0.7),
                cognitive_capacity=np.random.uniform(3.0, 5.0),
                attention_span=np.random.uniform(0.4, 0.6),
                help_seeking=np.random.uniform(0.6, 0.8),
                persistence=np.random.uniform(0.8, 0.95),
                metacognition=np.random.uniform(0.3, 0.5),
                accuracy_variance=0.15,
                time_per_interaction=np.random.uniform(60, 90),
                fatigue_rate=1.2,
                question_types_preferred=["multiple_choice"],
                scaffolding_preference="high",
                feedback_sensitivity=0.9
            )
        
        elif personality == LearnerPersonality.EASILY_DISTRACTED:
            profile = LearnerProfile(
                personality=personality,
                learning_rate=np.random.uniform(0.4, 0.6),
                initial_motivation=np.random.uniform(0.4, 0.6),
                cognitive_capacity=np.random.uniform(4.0, 6.0),
                attention_span=np.random.uniform(0.3, 0.5),
                help_seeking=np.random.uniform(0.3, 0.5),
                persistence=np.random.uniform(0.3, 0.5),
                metacognition=np.random.uniform(0.2, 0.4),
                accuracy_variance=0.2,
                time_per_interaction=np.random.uniform(15, 60),  # Highly variable
                fatigue_rate=1.0,
                question_types_preferred=["true_false", "multiple_choice"],
                scaffolding_preference="medium",
                feedback_sensitivity=1.2
            )
        
        elif personality == LearnerPersonality.PERFECTIONIST:
            profile = LearnerProfile(
                personality=personality,
                learning_rate=np.random.uniform(0.6, 0.8),
                initial_motivation=np.random.uniform(0.6, 0.8),
                cognitive_capacity=np.random.uniform(5.0, 7.0),
                attention_span=np.random.uniform(0.6, 0.8),
                help_seeking=np.random.uniform(0.2, 0.5),
                persistence=np.random.uniform(0.7, 0.9),
                metacognition=np.random.uniform(0.7, 0.9),
                accuracy_variance=0.25,  # High variance - all or nothing
                time_per_interaction=np.random.uniform(50, 80),
                fatigue_rate=1.1,
                question_types_preferred=["open_ended", "fill_in_blank"],
                scaffolding_preference="low",
                feedback_sensitivity=1.5
            )
        
        else:  # CREATIVE_DIVERGENT
            profile = LearnerProfile(
                personality=personality,
                learning_rate=np.random.uniform(0.5, 0.7),
                initial_motivation=np.random.uniform(0.6, 0.8),
                cognitive_capacity=np.random.uniform(4.0, 7.0),
                attention_span=np.random.uniform(0.5, 0.7),
                help_seeking=np.random.uniform(0.3, 0.6),
                persistence=np.random.uniform(0.5, 0.8),
                metacognition=np.random.uniform(0.6, 0.8),
                accuracy_variance=0.15,
                time_per_interaction=np.random.uniform(30, 70),
                fatigue_rate=0.9,
                question_types_preferred=["open_ended", "multiple_choice"],
                scaffolding_preference="medium",
                feedback_sensitivity=0.6
            )
        
        return profile
    
    def step(self):
        """Execute one step of the simulation"""
        self.schedule.step()
        
        # Check if any agents are still active
        active_agents = sum(1 for agent in self.schedule.agents if agent.session_active)
        
        if active_agents == 0:
            print("DEBUG: All agents completed sessions, stopping simulation")
            self.running = False
    
    def get_simulation_results(self) -> Dict[str, Any]:
        """Get comprehensive simulation results"""
        agent_summaries = []
        
        for agent in self.schedule.agents:
            summary = agent.get_session_summary()
            agent_summaries.append(summary)
        
        # Aggregate statistics
        total_interactions = sum(s['total_interactions'] for s in agent_summaries)
        avg_accuracy = np.mean([s['accuracy'] for s in agent_summaries])
        avg_motivation = np.mean([s['final_motivation'] for s in agent_summaries])
        avg_session_duration = np.mean([s['session_duration_minutes'] for s in agent_summaries])
        
        # Personality-based analysis
        personality_stats = {}
        for personality in LearnerPersonality:
            personality_agents = [s for s in agent_summaries if s['personality'] == personality.value]
            if personality_agents:
                personality_stats[personality.value] = {
                    'count': len(personality_agents),
                    'avg_accuracy': np.mean([s['accuracy'] for s in personality_agents]),
                    'avg_motivation': np.mean([s['final_motivation'] for s in personality_agents]),
                    'avg_help_requests': np.mean([s['help_requests'] for s in personality_agents])
                }
        
        return {
            'simulation_summary': {
                'total_agents': len(agent_summaries),
                'total_interactions': total_interactions,
                'avg_accuracy': avg_accuracy,
                'avg_motivation': avg_motivation,
                'avg_session_duration': avg_session_duration
            },
            'agent_summaries': agent_summaries,
            'personality_analysis': personality_stats,
            'timestamp': datetime.now().isoformat()
        }

class ComprehensiveLEASimulation:
    """High-level simulation orchestrator for comprehensive testing"""
    
    def __init__(self, metrics_integration: EnhancedMetricsIntegration = None):
        self.metrics_integration = metrics_integration or EnhancedMetricsIntegration()
        self.simulation_results = []
        self.output_dir = Path("./data/simulation_results")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    async def run_comprehensive_simulation(
        self,
        num_agents: int = 50,
        num_runs: int = 5,
        max_steps_per_run: int = 100
    ) -> Dict[str, Any]:
        """Run comprehensive simulation with multiple runs"""
        
        print(f"DEBUG: Starting comprehensive simulation: {num_runs} runs with {num_agents} agents each")
        
        all_results = []
        
        for run_id in range(num_runs):
            print(f"DEBUG: Starting simulation run {run_id + 1}/{num_runs}")
            
            # Create and run simulation
            model = LEASimulationModel(num_agents, self.metrics_integration)
            
            step_count = 0
            while model.running and step_count < max_steps_per_run:
                model.step()
                step_count += 1
                
                # Small delay to prevent overwhelming
                await asyncio.sleep(0.01)
            
            # Get results
            run_results = model.get_simulation_results()
            run_results['run_id'] = run_id
            run_results['steps_executed'] = step_count
            
            all_results.append(run_results)
            
            print(f"DEBUG: Completed run {run_id + 1}: {step_count} steps, "
                  f"avg accuracy {run_results['simulation_summary']['avg_accuracy']:.2%}")
        
        # Aggregate across runs
        comprehensive_analysis = self._analyze_comprehensive_results(all_results)
        
        # Save results
        self._save_simulation_results(comprehensive_analysis)
        
        return comprehensive_analysis
    
    def _analyze_comprehensive_results(self, all_results: List[Dict]) -> Dict[str, Any]:
        """Analyze results across multiple simulation runs"""
        
        # Aggregate simulation summaries
        all_summaries = [r['simulation_summary'] for r in all_results]
        
        aggregated_summary = {
            'total_runs': len(all_results),
            'total_agents': sum(s['total_agents'] for s in all_summaries),
            'total_interactions': sum(s['total_interactions'] for s in all_summaries),
            'avg_accuracy': {
                'mean': np.mean([s['avg_accuracy'] for s in all_summaries]),
                'std': np.std([s['avg_accuracy'] for s in all_summaries]),
                'min': np.min([s['avg_accuracy'] for s in all_summaries]),
                'max': np.max([s['avg_accuracy'] for s in all_summaries])
            },
            'avg_motivation': {
                'mean': np.mean([s['avg_motivation'] for s in all_summaries]),
                'std': np.std([s['avg_motivation'] for s in all_summaries])
            },
            'avg_session_duration': {
                'mean': np.mean([s['avg_session_duration'] for s in all_summaries]),
                'std': np.std([s['avg_session_duration'] for s in all_summaries])
            }
        }
        
        # Personality analysis across runs
        personality_analysis = {}
        for personality in LearnerPersonality:
            personality_data = []
            
            for result in all_results:
                if personality.value in result.get('personality_analysis', {}):
                    personality_data.append(result['personality_analysis'][personality.value])
            
            if personality_data:
                personality_analysis[personality.value] = {
                    'avg_accuracy': {
                        'mean': np.mean([p['avg_accuracy'] for p in personality_data]),
                        'std': np.std([p['avg_accuracy'] for p in personality_data])
                    },
                    'avg_motivation': {
                        'mean': np.mean([p['avg_motivation'] for p in personality_data]),
                        'std': np.std([p['avg_motivation'] for p in personality_data])
                    },
                    'sample_size': sum(p['count'] for p in personality_data)
                }
        
        # Learning effectiveness insights
        effectiveness_insights = self._generate_effectiveness_insights(all_results)
        
        return {
            'comprehensive_summary': aggregated_summary,
            'personality_analysis': personality_analysis,
            'effectiveness_insights': effectiveness_insights,
            'individual_runs': all_results,
            'analysis_timestamp': datetime.now().isoformat()
        }
    
    def _generate_effectiveness_insights(self, all_results: List[Dict]) -> Dict[str, Any]:
        """Generate insights about learning effectiveness"""
        
        # Collect all agent data
        all_agents = []
        for result in all_results:
            all_agents.extend(result['agent_summaries'])
        
        # Learning outcome analysis
        high_performers = [a for a in all_agents if a['accuracy'] > 0.8]
        low_performers = [a for a in all_agents if a['accuracy'] < 0.4]
        
        insights = {
            'performance_distribution': {
                'high_performers_percent': len(high_performers) / len(all_agents) * 100,
                'low_performers_percent': len(low_performers) / len(all_agents) * 100,
                'avg_accuracy_high': np.mean([a['accuracy'] for a in high_performers]) if high_performers else 0,
                'avg_accuracy_low': np.mean([a['accuracy'] for a in low_performers]) if low_performers else 0
            },
            'engagement_patterns': {
                'avg_session_duration': np.mean([a['session_duration_minutes'] for a in all_agents]),
                'avg_help_requests': np.mean([a['help_requests'] for a in all_agents]),
                'avg_questions_asked': np.mean([a['questions_asked'] for a in all_agents])
            },
            'learning_trends': {
                'improving_learners': len([a for a in all_agents if a.get('performance_trend') == 'improving']),
                'stable_learners': len([a for a in all_agents if a.get('performance_trend') == 'stable']),
                'declining_learners': len([a for a in all_agents if a.get('performance_trend') == 'declining'])
            }
        }
        
        return insights
    
    def _save_simulation_results(self, results: Dict[str, Any]):
        """Save simulation results to files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save comprehensive results as JSON
        results_file = self.output_dir / f"simulation_results_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        # Save agent data as CSV for analysis
        all_agents = []
        for result in results['individual_runs']:
            for agent in result['agent_summaries']:
                agent['run_id'] = result['run_id']
                all_agents.append(agent)
        
        df = pd.DataFrame(all_agents)
        csv_file = self.output_dir / f"agent_performance_{timestamp}.csv"
        df.to_csv(csv_file, index=False)
        
        print(f"DEBUG: Simulation results saved to {results_file} and {csv_file}")

# USAGE EXAMPLE
async def run_example_simulation():
    """Example of running the comprehensive LEA simulation"""
    
    # Initialize metrics integration
    metrics_integration = EnhancedMetricsIntegration()
    
    # Create comprehensive simulation
    simulation = ComprehensiveLEASimulation(metrics_integration)
    
    # Run simulation
    results = await simulation.run_comprehensive_simulation(
        num_agents=20,  # Start with smaller number for testing
        num_runs=3,
        max_steps_per_run=50
    )
    
    print("Simulation Complete!")
    print(f"Total interactions: {results['comprehensive_summary']['total_interactions']}")
    print(f"Average accuracy: {results['comprehensive_summary']['avg_accuracy']['mean']:.2%}")
    print(f"High performers: {results['effectiveness_insights']['performance_distribution']['high_performers_percent']:.1f}%")

if __name__ == "__main__":
    asyncio.run(run_example_simulation())
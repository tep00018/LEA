# src/core/agent_orchestrator_mcp.py
"""
Agent Orchestrator with MCP Integration + Motivation State Classification
ENHANCED: Uses MCP Client for all tool interactions instead of direct connections
ENHANCED: Implements behavioral-based motivation measurement and feedback injection
"""

import json
import random
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
from dataclasses import dataclass
from enum import Enum
import asyncio
import traceback
import re

# NEW: Add sentiment analysis capability
try:
    from textblob import TextBlob
    SENTIMENT_AVAILABLE = True
except ImportError:
    print("WARNING: textblob not installed. Sentiment analysis will be disabled.")
    SENTIMENT_AVAILABLE = False

from src.mcp.mcp_client import LEAMCPClient
from src.core.scaffolding_engine import ScaffoldingEngine, ScaffoldingDecision

# NEW: Motivation-related enums and dataclasses
class MotivationState(Enum):
    """Motivation states based on behavioral indicators"""
    COLD_START = "cold_start"
    MOTIVATION_DROP = "motivation_drop"
    MOTIVATION_PLATEAU = "motivation_plateau"
    MAINTAINED_HIGH = "maintained_high"

class PersistenceLevel(Enum):
    """Persistence behavior classifications"""
    EARLY_ABANDONMENT = "early_abandonment"
    DECREASED_PERSISTENCE = "decreased_persistence"
    MAINTAINS_PERSISTENCE = "maintains_persistence"
    ENHANCED_PERSISTENCE = "enhanced_persistence"

@dataclass
class MotivationMetrics:
    """Motivation measurement metrics"""
    persistence_level: PersistenceLevel
    affective_score: float  # -1.0 to 1.0 from sentiment analysis
    performance_score: float  # Current accuracy/correctness
    interaction_count: int
    session_completion_rate: float
    consecutive_correct: int
    consecutive_incorrect: int
    time_on_task: float
    help_seeking_frequency: float

@dataclass
class MotivationHistory:
    """Historical motivation data for baseline establishment"""
    baseline_established: bool
    baseline_interactions: List[Dict[str, Any]]
    recent_metrics: List[MotivationMetrics]
    state_transitions: List[Tuple[MotivationState, datetime]]
    session_count: int

@dataclass
class CognitiveState:
    """Enhanced cognitive state with MCP integration and motivation"""
    cognitive_load: float
    zpd_score: float
    motivation_score: float
    motivation_state: MotivationState  # NEW: Behavioral motivation state
    motivation_metrics: MotivationMetrics  # NEW: Detailed metrics
    fatigue_level: float
    scaffolding_level: str
    session_quality: str
    mastery_data: Dict[str, Any]  # Include mastery data from MCP
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'cognitive_load': self.cognitive_load,
            'zpd_score': self.zpd_score,
            'motivation_score': self.motivation_score,
            'motivation_state': self.motivation_state.value,
            'motivation_metrics': self._serialize_motivation_metrics(),
            'fatigue_level': self.fatigue_level,
            'scaffolding_level': self.scaffolding_level,
            'session_quality': self.session_quality,
            'mastery_data': self.mastery_data,
            'timestamp': datetime.now().isoformat()
        }
    
    def _serialize_motivation_metrics(self) -> Dict[str, Any]:
        return {
            'persistence_level': self.motivation_metrics.persistence_level.value,
            'affective_score': self.motivation_metrics.affective_score,
            'performance_score': self.motivation_metrics.performance_score,
            'interaction_count': self.motivation_metrics.interaction_count,
            'session_completion_rate': self.motivation_metrics.session_completion_rate,
            'consecutive_correct': self.motivation_metrics.consecutive_correct,
            'consecutive_incorrect': self.motivation_metrics.consecutive_incorrect,
            'time_on_task': self.motivation_metrics.time_on_task,
            'help_seeking_frequency': self.motivation_metrics.help_seeking_frequency
        }

class InteractionType(Enum):
    """Types of student interactions"""
    CHAT_QUERY = "chat_query"
    TUTOR_RESPONSE = "tutor_response" 
    QUIZ_ANSWER = "quiz_answer"
    MODE_SWITCH = "mode_switch"
    HELP_REQUEST = "help_request"
    SESSION_START = "session_start"  # NEW
    SESSION_END = "session_end"      # NEW

class LEAOrchestratorMCP:
    """
    ENHANCED: Agent Orchestrator with MCP Integration + Scaffolding Engine + Motivation State Classification
    Includes sophisticated CL×ZPD matrix scaffolding decisions and behavioral motivation measurement
    
    All external tool access now goes through MCP Client:
    - RAG retrieval via MCP
    - KC Model access via MCP  
    - Mastery tracking via MCP
    """
    
    def __init__(self, mcp_server, redis_client=None):
        """Initialize orchestrator with MCP client and motivation tracking"""
        # Initialize MCP client
        self.mcp_client = LEAMCPClient(mcp_server)
        self.redis_client = redis_client
        
        # Empirically-derived cognitive load parameters
        self.cl_params = {
            'beta_0': 0.5,   # Baseline cognitive load
            'beta_1': 1.0,   # Difficulty coefficient
            'beta_2': 4.5,   # Accuracy coefficient (inverted for load)
            'beta_4': 0.1,   # Interaction count coefficient  
            'beta_5': 1.0    # Task type coefficient
        }
        # Scaffolding engine (will be injected from streamlit app)
        self.scaffolding_engine = None
        self.decision_logger = None
        
        print("DEBUG: LEA Orchestrator initialized with scaffolding support")
        
        # ZPD parameters for Task Difficulty
        self.zpd_optimal_range = (0.5, 0.8)
        
        # Motivation formula coefficients
        self.motivation_params = {
            'go_weight': 0.5,
            'lo_weight': 0.3,
            'week_weight': 0.2,
            # NEW: Motivation measurement parameters
            'baseline_interaction_threshold': 4,  # Minimum interactions for baseline
            'sentiment_window': 5,  # Number of recent texts to analyze
            'persistence_time_threshold': 300,  # 5 minutes minimum for persistence
            'performance_window': 10,  # Recent performance window
            'abandonment_threshold': 0.3,  # Session completion below this = abandonment
        }
        
        print("DEBUG: LEA Orchestrator initialized with MCP integration and motivation state classification")
    
    async def process_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        ENHANCED: Main orchestrator entry point with MCP integration
        """
        try:
            username = state["username"]
            user_query = state["user_query"]
            course = state.get("selected_course", "CMP511")
            mode = state.get("current_mode", "chat")
            
            print(f"DEBUG: Processing {mode} interaction via MCP for {username}")
            
            # Step 1: Get current mastery via MCP
            mastery_data = await self.mcp_client.get_mastery_summary(username, course)
            if not mastery_data.get("success", False):
                print("DEBUG: Using default mastery data")
                mastery_data = {"go_masteries": {}, "lo_masteries": {}, "week_masteries": {}}
            
            # Step 2: Cognitive Load Assessment with mastery context
            cognitive_assessment = await self._assess_cognitive_state_mcp(username, state, mastery_data)
            
            # Step 3: Scaffolding Decision
            scaffolding_decision = self._determine_scaffolding_strategy(
                cognitive_assessment.get("cl_value", 5.0), 
                cognitive_assessment.get("zpd_score", 0.5)
            )
            
            # Step 4: Generate Enhanced Response with RAG
            response = await self._generate_enhanced_response_mcp(
                user_query, state, scaffolding_decision, course
            )
            
            # Step 5: Update mastery via MCP (async, non-blocking)
            asyncio.create_task(self._update_mastery_mcp(
                username, course, user_query, state, cognitive_assessment
            ))
            
            return {
                "success": True,
                "final_response": response,
                "cognitive_load": cognitive_assessment,
                "scaffolding": scaffolding_decision,
                "adaptations_applied": False,
                # "adaptations_applied": scaffolding_decision.get("adaptations_applied", False),
                "processing_mode": mode,
                "mcp_integration": True
            }
            
        except Exception as e:
            print(f"ERROR: MCP Orchestrator processing failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "final_response": "I'm having trouble processing your request right now. Please try again."
            }

    async def process_interaction(
            self, 
            username: str,
            course: str, 
            interaction_type,
            student_input: str,
            current_mode: str,
            session_context: Dict[str, Any]
        ) -> Dict[str, Any]:
            """
            ENHANCED: Main interaction processing with integrated scaffolding and motivation state classification
            """
                        
            try:
                print(f"DEBUG: 🧠 Processing {interaction_type} with MOTIVATION-ENHANCED orchestrator (scaffolding: {'✅' if self.scaffolding_engine else '❌'})")
                
                # Step 1: Get current mastery via MCP
                mastery_result = await self.mcp_client.get_mastery_summary(username, course)
                mastery_data = mastery_result if mastery_result.get("success") else {}
                
                # Step 2: Load motivation history
                motivation_history = await self._load_motivation_history(username, course)
                
                # Step 3: Calculate motivation metrics from behavioral indicators
                motivation_metrics = await self._calculate_motivation_metrics(
                    username, course, student_input, interaction_type, 
                    session_context, motivation_history
                )
                
                # Step 4: Determine motivation state
                motivation_state = self._classify_motivation_state(motivation_metrics, motivation_history)
                
                # Step 5: Calculate cognitive state with motivation context
                cognitive_state = await self._calculate_enhanced_cognitive_state(
                    username, course, student_input, interaction_type, 
                    session_context, mastery_data, motivation_state, motivation_metrics
                )
                
                # Step 6: Generate motivation-informed feedback
                motivation_feedback = self._generate_motivation_feedback(
                    motivation_state, motivation_metrics
                )
                
                # Step 7: ENHANCED - Use scaffolding engine with motivation context
                if self.scaffolding_engine:
                    scaffolding_decision = await self._get_motivation_informed_scaffolding(
                        cognitive_state, username, session_context, motivation_state
                    )
                    
                    # FIXED: Safe debug printing that handles both dict and object types
                    if hasattr(scaffolding_decision, 'strategy_type'):
                        print(f"DEBUG: 🎯 Motivation-informed scaffolding: {scaffolding_decision.strategy_type} @ {scaffolding_decision.intensity_level}")
                    else:
                        intervention_type = scaffolding_decision.get('intervention_type', 'unknown')
                        print(f"DEBUG: 🎯 Basic scaffolding decision: {intervention_type}")
                        
                else:
                    # Fallback to basic scaffolding
                    scaffolding_decision = self._determine_scaffolding_strategy(
                        cognitive_state.cognitive_load, 
                        cognitive_state.zpd_score
                    )
                    print(f"DEBUG: 📱 Basic scaffolding decision: {scaffolding_decision.get('intervention_type', 'unknown')}")
                
                # Step 8: Create enhanced adaptive context with motivation feedback injection
                adaptive_context = self._generate_motivation_enhanced_context(
                    current_mode, scaffolding_decision, motivation_feedback, 
                    cognitive_state, session_context
                )
                
                # Step 9: Generate LLM guidance with motivation integration
                llm_guidance = self._generate_motivation_informed_guidance(
                    scaffolding_decision, motivation_feedback, current_mode, cognitive_state
                )
                
                # Step 10: Update motivation history
                await self._update_motivation_history(
                    username, course, motivation_metrics, motivation_state, motivation_history
                )
                
                # Step 11: Log decisions for research
                if self.decision_logger:
                    self._log_motivation_decisions(
                        username, course, cognitive_state, motivation_state, 
                        motivation_metrics, session_context
                    )
                
                # Step 12: Update mastery via MCP (async)
                asyncio.create_task(self._update_mastery_interaction_mcp(
                    username, course, interaction_type, student_input, session_context
                ))
                
                # Step 13: Store cognitive state
                await self._store_cognitive_state(username, course, cognitive_state)
                
                # FIXED: Safe strategy_type access for final logging
                if hasattr(scaffolding_decision, 'strategy_type'):
                    strategy_used = scaffolding_decision.strategy_type
                else:
                    strategy_used = scaffolding_decision.get('intervention_type', 'basic')
                
                print(f"DEBUG: ✅ Motivation-enhanced processing complete - "
                      f"State: {motivation_state.value}, CL: {cognitive_state.cognitive_load:.2f}, Strategy: {strategy_used}")

                return {
                    'cognitive_state': cognitive_state,
                    'scaffolding_strategy': self._format_scaffolding_for_systems(scaffolding_decision), 
                    'motivation_feedback': motivation_feedback,
                    'motivation_state': motivation_state.value,
                    'motivation_metrics': motivation_metrics,
                    'adaptive_context': adaptive_context,
                    'orchestrator_guidance': llm_guidance,
                    'processing_successful': True,
                    'mcp_integrated': True,
                    'motivation_enhanced': True,
                    'scaffolding_engine_used': self.scaffolding_engine is not None,
                    'decision_logged': self.decision_logger is not None
                }

            except Exception as e:
                print(f"ERROR: Enhanced orchestrator processing failed: {e}")
                print(f"ERROR TRACEBACK:")
                print(traceback.format_exc())
                return self._get_fallback_response(current_mode)

    # NEW: Motivation measurement methods
    async def _calculate_motivation_metrics(
        self,
        username: str,
        course: str,
        student_input: str,
        interaction_type: InteractionType,
        session_context: Dict[str, Any],
        motivation_history: MotivationHistory
    ) -> MotivationMetrics:
        """Calculate motivation metrics from behavioral indicators"""
        
        try:
            # 1. PERSISTENCE LEVEL MEASUREMENT
            persistence_level = self._measure_persistence_level(
                interaction_type, session_context, motivation_history
            )
            
            # 2. AFFECTIVE STATE MEASUREMENT (Sentiment Analysis)
            affective_score = self._analyze_affective_state(
                student_input, motivation_history
            )
            
            # 3. PERFORMANCE MEASUREMENT
            performance_score = self._calculate_performance_score(
                session_context, motivation_history
            )
            
            # 4. ADDITIONAL BEHAVIORAL METRICS
            interaction_count = len(motivation_history.recent_metrics) + 1
            
            session_completion_rate = self._calculate_session_completion_rate(
                session_context, motivation_history
            )
            
            consecutive_correct, consecutive_incorrect = self._calculate_consecutive_performance(
                session_context, motivation_history
            )
            
            time_on_task = self._calculate_time_on_task(session_context)
            
            help_seeking_frequency = self._calculate_help_seeking_frequency(
                interaction_type, motivation_history
            )
            
            print(f"DEBUG: Motivation metrics - Persistence: {persistence_level.value}, "
                  f"Affective: {affective_score:.2f}, Performance: {performance_score:.2f}")
            
            return MotivationMetrics(
                persistence_level=persistence_level,
                affective_score=affective_score,
                performance_score=performance_score,
                interaction_count=interaction_count,
                session_completion_rate=session_completion_rate,
                consecutive_correct=consecutive_correct,
                consecutive_incorrect=consecutive_incorrect,
                time_on_task=time_on_task,
                help_seeking_frequency=help_seeking_frequency
            )
            
        except Exception as e:
            print(f"DEBUG: Error calculating motivation metrics: {e}")
            # Return default metrics
            return MotivationMetrics(
                persistence_level=PersistenceLevel.MAINTAINS_PERSISTENCE,
                affective_score=0.0,
                performance_score=0.5,
                interaction_count=1,
                session_completion_rate=0.5,
                consecutive_correct=0,
                consecutive_incorrect=0,
                time_on_task=0.0,
                help_seeking_frequency=0.0
            )
    
    def _measure_persistence_level(
        self,
        interaction_type: InteractionType,
        session_context: Dict[str, Any],
        motivation_history: MotivationHistory
    ) -> PersistenceLevel:
        """Measure persistence based on behavioral indicators"""
        
        # Check for early abandonment patterns
        if interaction_type == InteractionType.SESSION_END:
            session_duration = session_context.get('session_duration', 0)
            total_questions = session_context.get('total_questions', 1)
            completed_questions = session_context.get('completed_questions', 0)
            
            completion_rate = completed_questions / max(total_questions, 1)
            
            if completion_rate < 0.3 or session_duration < 60:  # Less than 30% or 1 minute
                return PersistenceLevel.EARLY_ABANDONMENT
        
        # Check for decreased persistence patterns
        if len(motivation_history.recent_metrics) >= 3:
            recent_completions = [
                m.session_completion_rate for m in motivation_history.recent_metrics[-3:]
            ]
            if len(recent_completions) >= 2 and recent_completions[-1] < recent_completions[0] - 0.2:
                return PersistenceLevel.DECREASED_PERSISTENCE
        
        # Check for enhanced persistence
        current_session_completion = session_context.get('completion_progress', 0.0)
        if current_session_completion > 0.9:  # Near completion
            recent_time_on_task = [
                m.time_on_task for m in motivation_history.recent_metrics[-3:]
            ]
            if recent_time_on_task and recent_time_on_task[-1] > np.mean(recent_time_on_task):
                return PersistenceLevel.ENHANCED_PERSISTENCE
        
        # Default to maintains persistence
        return PersistenceLevel.MAINTAINS_PERSISTENCE
    
    def _analyze_affective_state(
        self,
        student_input: str,
        motivation_history: MotivationHistory
    ) -> float:
        """Analyze affective state using sentiment analysis"""
        
        try:
            # Perform sentiment analysis on current input if available
            if SENTIMENT_AVAILABLE and student_input and len(student_input.strip()) > 0:
                blob = TextBlob(student_input)
                current_sentiment = blob.sentiment.polarity
                
                # Consider recent sentiment history
                recent_sentiments = []
                for metrics in motivation_history.recent_metrics[-self.motivation_params['sentiment_window']:]:
                    recent_sentiments.append(metrics.affective_score)
                
                if recent_sentiments:
                    # Weighted average: 60% current, 40% recent history
                    historical_avg = np.mean(recent_sentiments)
                    weighted_sentiment = 0.6 * current_sentiment + 0.4 * historical_avg
                else:
                    weighted_sentiment = current_sentiment
                
                return max(-1.0, min(1.0, weighted_sentiment))
            else:
                # No text input or sentiment analysis unavailable, use recent history or neutral
                if motivation_history.recent_metrics:
                    return motivation_history.recent_metrics[-1].affective_score
                return 0.0
                
        except Exception as e:
            print(f"DEBUG: Error in sentiment analysis: {e}")
            return 0.0
    
    def _calculate_performance_score(
        self,
        session_context: Dict[str, Any],
        motivation_history: MotivationHistory
    ) -> float:
        """Calculate current performance score"""
        
        # Get current session performance
        current_accuracy = session_context.get('current_accuracy', 0.5)
        
        # Consider recent performance trend
        recent_performances = []
        for metrics in motivation_history.recent_metrics[-self.motivation_params['performance_window']:]:
            recent_performances.append(metrics.performance_score)
        
        if recent_performances:
            # Weight current performance with recent trend
            recent_avg = np.mean(recent_performances)
            weighted_performance = 0.7 * current_accuracy + 0.3 * recent_avg
            return max(0.0, min(1.0, weighted_performance))
        
        return current_accuracy
    
    def _calculate_session_completion_rate(
        self,
        session_context: Dict[str, Any],
        motivation_history: MotivationHistory
    ) -> float:
        """Calculate session completion rate"""
        
        total_items = session_context.get('total_questions', session_context.get('total_objectives', 1))
        completed_items = session_context.get('completed_questions', session_context.get('completed_objectives', 0))
        
        if total_items > 0:
            return completed_items / total_items
        
        return 0.0
    
    def _calculate_consecutive_performance(
        self,
        session_context: Dict[str, Any],
        motivation_history: MotivationHistory
    ) -> Tuple[int, int]:
        """Calculate consecutive correct and incorrect responses"""
        
        # Look at recent quiz/tutor results
        recent_results = session_context.get('recent_results', [])
        
        consecutive_correct = 0
        consecutive_incorrect = 0
        
        # Count from most recent backwards
        for result in reversed(recent_results):
            if result.get('correct', False):
                if consecutive_incorrect == 0:
                    consecutive_correct += 1
                else:
                    break
            else:
                if consecutive_correct == 0:
                    consecutive_incorrect += 1
                else:
                    break
        
        return consecutive_correct, consecutive_incorrect
    
    def _calculate_time_on_task(self, session_context: Dict[str, Any]) -> float:
        """Calculate time spent on current task/session"""
        
        session_start = session_context.get('session_start_time')
        if session_start:
            if isinstance(session_start, str):
                session_start = datetime.fromisoformat(session_start)
            
            current_time = datetime.now()
            time_diff = (current_time - session_start).total_seconds() / 60.0  # minutes
            return min(time_diff, 120.0)  # Cap at 2 hours
        
        return 0.0
    
    def _calculate_help_seeking_frequency(
        self,
        interaction_type: InteractionType,
        motivation_history: MotivationHistory
    ) -> float:
        """Calculate help-seeking frequency"""
        
        help_requests = 0
        total_interactions = 0
        
        # Count help requests in recent history
        for metrics in motivation_history.recent_metrics[-10:]:  # Last 10 interactions
            total_interactions += 1
            # This would need to be tracked based on actual help-seeking behaviors
            # For now, estimate based on interaction patterns
        
        # Current interaction
        if interaction_type == InteractionType.HELP_REQUEST:
            help_requests += 1
        
        total_interactions += 1
        
        if total_interactions > 0:
            return help_requests / total_interactions
        
        return 0.0
    
    def _classify_motivation_state(
        self,
        metrics: MotivationMetrics,
        history: MotivationHistory
    ) -> MotivationState:
        """Classify motivation state based on metrics and framework"""
        
        # Cold Start Period - first few interactions
        if not history.baseline_established:
            if metrics.interaction_count <= self.motivation_params['baseline_interaction_threshold']:
                return MotivationState.COLD_START
            else:
                # Mark baseline as established
                history.baseline_established = True
        
        # Motivation Drop Detection
        if (metrics.persistence_level == PersistenceLevel.EARLY_ABANDONMENT or
            metrics.persistence_level == PersistenceLevel.DECREASED_PERSISTENCE or
            metrics.affective_score < -0.3 or
            metrics.performance_score < 0.5):
            return MotivationState.MOTIVATION_DROP
        
        # High Motivation Detection
        if (metrics.persistence_level == PersistenceLevel.ENHANCED_PERSISTENCE or
            metrics.affective_score > 0.3 or
            metrics.performance_score > 0.8):
            return MotivationState.MAINTAINED_HIGH
        
        # Default to plateau (stable engagement)
        return MotivationState.MOTIVATION_PLATEAU
    
    def _generate_motivation_feedback(
        self,
        motivation_state: MotivationState,
        metrics: MotivationMetrics
    ) -> Dict[str, Any]:
        """Generate feedback based on motivation state classification"""
        
        feedback_strategies = {
            MotivationState.COLD_START: {
                "strategy": "positive_reinforcement",
                "tone": "welcoming",
                "controlling_language": False,
                "emotional_support": True,
                "competence_celebration": False,
                "challenge_level": "maintain",
                "collaborative_opportunities": False,
                "feedback_message": "Welcome! Let's explore this topic together. Take your time and feel free to ask questions.",
                "system_adjustments": {
                    "reduce_pressure": True,
                    "increase_encouragement": True,
                    "simplify_interface": False
                }
            },
            
            MotivationState.MOTIVATION_DROP: {
                "strategy": "autonomy_supportive",
                "tone": "supportive",
                "controlling_language": False,
                "emotional_support": True,
                "competence_celebration": False,
                "challenge_level": "reduce",
                "collaborative_opportunities": False,
                "feedback_message": "You're doing great! Let's approach this from a different angle that might feel more comfortable.",
                "system_adjustments": {
                    "minimize_controlling_language": True,
                    "provide_emotional_support": True,
                    "reduce_difficulty": True,
                    "offer_choices": True
                }
            },
            
            MotivationState.MOTIVATION_PLATEAU: {
                "strategy": "competence_support",
                "tone": "encouraging",
                "controlling_language": False,
                "emotional_support": False,
                "competence_celebration": True,
                "challenge_level": "maintain",
                "collaborative_opportunities": False,
                "feedback_message": "Nice work on your approach! Your effort and strategy are really showing progress.",
                "system_adjustments": {
                    "celebrate_effort": True,
                    "mastery_oriented_feedback": True,
                    "growth_mindset_emphasis": True
                }
            },
            
            MotivationState.MAINTAINED_HIGH: {
                "strategy": "challenge_expansion",
                "tone": "challenging",
                "controlling_language": False,
                "emotional_support": False,
                "competence_celebration": True,
                "challenge_level": "increase",
                "collaborative_opportunities": True,
                "feedback_message": "Excellent mastery! Ready for a more advanced challenge? You could also help others learn this concept.",
                "system_adjustments": {
                    "suggest_stretch_goals": True,
                    "advanced_content": True,
                    "collaborative_learning": True,
                    "peer_teaching_opportunities": True
                }
            }
        }
        
        return feedback_strategies.get(motivation_state, feedback_strategies[MotivationState.MOTIVATION_PLATEAU])

    # NEW: Enhanced cognitive state calculation with motivation
    async def _calculate_enhanced_cognitive_state(
        self, 
        username: str, 
        course: str, 
        student_input: str,
        interaction_type: InteractionType,
        session_context: Dict[str, Any],
        mastery_data: Dict[str, Any],
        motivation_state: MotivationState,
        motivation_metrics: MotivationMetrics
    ) -> CognitiveState:
        """Enhanced cognitive state calculation with MCP mastery integration and motivation"""
        
        try:
            # Calculate recent accuracy from mastery data
            go_masteries = mastery_data.get("go_masteries", {})
            if go_masteries:
                # Use recent GO masteries (last 4)
                recent_gos = list(go_masteries.values())[-4:]
                recent_accuracy = np.mean(recent_gos)
            else:
                recent_accuracy = 0.5
            
            # Get current difficulty via MCP
            current_difficulty = await self._get_current_difficulty_mcp(course, session_context)
            
            # Get interaction count
            interaction_count = mastery_data.get("total_interactions", 0) + 1
            
            # Task type classification
            task_type = self._classify_task_type(interaction_type, student_input)
            
            # Apply cognitive load formula
            cognitive_load = (
                self.cl_params['beta_0'] +
                self.cl_params['beta_1'] * current_difficulty +
                self.cl_params['beta_2'] * (1 - recent_accuracy) +
                self.cl_params['beta_4'] * (interaction_count * 0.1) +
                self.cl_params['beta_5'] * task_type
            )
            
            # Bound cognitive load
            cognitive_load = max(0, min(10, cognitive_load))
            
            # Calculate motivation with mastery context
            motivation_score = self._calculate_motivation_from_mastery(mastery_data)
            
            # Calculate fatigue
            fatigue_level = min(1.0, interaction_count * 0.02)
            
            # Determine scaffolding
            scaffolding_level = self._determine_scaffolding_level(cognitive_load, recent_accuracy)
            
            # Session quality
            session_quality = self._assess_session_quality(
                cognitive_load, recent_accuracy, motivation_score, fatigue_level
            )
            
            print(f"DEBUG: Enhanced CL calculation - Motivation: {motivation_state.value}, "
                  f"Accuracy: {recent_accuracy:.2f}, CL: {cognitive_load:.2f}, "
                  f"Motivation Score: {motivation_score:.2f}")
            
            return CognitiveState(
                cognitive_load=cognitive_load,
                zpd_score=recent_accuracy,
                motivation_score=motivation_score,
                motivation_state=motivation_state,
                motivation_metrics=motivation_metrics,
                fatigue_level=fatigue_level,
                scaffolding_level=scaffolding_level,
                session_quality=session_quality,
                mastery_data=mastery_data
            )
            
        except Exception as e:
            print(f"DEBUG: Error in enhanced cognitive state calculation: {e}")
            return CognitiveState(
                cognitive_load=5.0,
                zpd_score=0.6,
                motivation_score=0.6,
                motivation_state=MotivationState.MOTIVATION_PLATEAU,
                motivation_metrics=MotivationMetrics(
                    persistence_level=PersistenceLevel.MAINTAINS_PERSISTENCE,
                    affective_score=0.0,
                    performance_score=0.5,
                    interaction_count=1,
                    session_completion_rate=0.5,
                    consecutive_correct=0,
                    consecutive_incorrect=0,
                    time_on_task=0.0,
                    help_seeking_frequency=0.0
                ),
                fatigue_level=0.3,
                scaffolding_level="medium",
                session_quality="good",
                mastery_data={}
            )

    # NEW: Motivation-informed scaffolding
    async def _get_motivation_informed_scaffolding(
        self,
        cognitive_state: CognitiveState,
        username: str,
        session_context: Dict[str, Any],
        motivation_state: MotivationState
    ):
        """Get scaffolding decision informed by motivation state"""
        
        if not self.scaffolding_engine:
            return self._determine_scaffolding_strategy(
                cognitive_state.cognitive_load, cognitive_state.zpd_score
            )
        
        try:
            # Adjust scaffolding parameters based on motivation state
            cl_level = self._map_cognitive_load_to_level(cognitive_state.cognitive_load)
            zpd_level = self._map_zpd_to_level(cognitive_state.zpd_score)
            
            # Motivation-based adjustments
            if motivation_state == MotivationState.MOTIVATION_DROP:
                # Increase support level for low motivation
                if cl_level == "low":
                    cl_level = "medium"
                elif cl_level == "medium":
                    cl_level = "high"
            elif motivation_state == MotivationState.MAINTAINED_HIGH:
                # Reduce support level for high motivation
                if cl_level == "high":
                    cl_level = "medium"
                elif cl_level == "medium":
                    cl_level = "low"
            
            # Get scaffolding decision with motivation context
            current_go = session_context.get('quiz_data', {}).get('current_question', {})
            go_id = current_go.get('go_id', 'UNKNOWN_GO')
            learning_objective = "_".join(go_id.split("_")[:3]) if go_id != 'UNKNOWN_GO' else 'UNKNOWN_LO'
            
            recent_performance = self._extract_recent_performance(session_context)
            
            scaffolding_decision = self.scaffolding_engine.get_scaffolding_decision(
                cl_level=cl_level,
                zpd_level=zpd_level,
                username=username,
                learning_objective=learning_objective,
                recent_performance=recent_performance
            )
            
            print(f"DEBUG: 🎯 Motivation-informed scaffolding - "
                  f"Motivation: {motivation_state.value}, CL:{cl_level}, ZPD:{zpd_level} → "
                  f"{scaffolding_decision.strategy_type}@{scaffolding_decision.intensity_level}")
            
            return scaffolding_decision
            
        except Exception as e:
            print(f"DEBUG: Motivation-informed scaffolding error: {e}")
            return self._determine_scaffolding_strategy(
                cognitive_state.cognitive_load, cognitive_state.zpd_score
            )

    # NEW: Motivation-enhanced context generation
    def _generate_motivation_enhanced_context(
        self,
        current_mode: str,
        scaffolding_decision,
        motivation_feedback: Dict,
        cognitive_state: CognitiveState,
        session_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate context enhanced with motivation feedback injection"""
        
        base_context = self._generate_enhanced_adaptive_context(
            current_mode, scaffolding_decision, motivation_feedback, 
            cognitive_state, session_context
        )
        
        # Add motivation-specific context
        base_context.update({
            "motivation_strategy": motivation_feedback.get("strategy", "maintain_flow"),
            "motivation_tone": motivation_feedback.get("tone", "encouraging"),
            "emotional_support_needed": motivation_feedback.get("emotional_support", False),
            "competence_celebration": motivation_feedback.get("competence_celebration", False),
            "challenge_adjustment": motivation_feedback.get("challenge_level", "maintain"),
            "collaborative_available": motivation_feedback.get("collaborative_opportunities", False),
            "system_adjustments": motivation_feedback.get("system_adjustments", {}),
            "motivation_message": motivation_feedback.get("feedback_message", ""),
            "controlling_language_minimized": not motivation_feedback.get("controlling_language", False)
        })
        
        return base_context
    
    # NEW: Motivation-informed guidance generation
    def _generate_motivation_informed_guidance(
        self,
        scaffolding_decision,
        motivation_feedback: Dict,
        current_mode: str,
        cognitive_state: CognitiveState
    ) -> str:
        """Generate LLM guidance informed by motivation state"""
        
        base_guidance = self._generate_enhanced_llm_guidance(
            scaffolding_decision, motivation_feedback, current_mode, cognitive_state
        )
        
        # Add motivation-specific guidance
        motivation_guidance_parts = [base_guidance]
        
        system_adjustments = motivation_feedback.get("system_adjustments", {})
        
        if system_adjustments.get("minimize_controlling_language", False):
            motivation_guidance_parts.append(
                "Avoid directive language like 'you must' or 'you should'. "
                "Instead use suggestions: 'you might consider' or 'one approach could be'."
            )
        
        if system_adjustments.get("provide_emotional_support", False):
            motivation_guidance_parts.append(
                "Provide emotional reassurance and validate the student's effort. "
                "Acknowledge that learning can be challenging."
            )
        
        if system_adjustments.get("celebrate_effort", False):
            motivation_guidance_parts.append(
                "Celebrate the student's effort and strategy rather than just correctness. "
                "Use growth mindset language that emphasizes learning process."
            )
        
        if system_adjustments.get("suggest_stretch_goals", False):
            motivation_guidance_parts.append(
                "Suggest advanced challenges or real-world applications. "
                "Offer opportunities for deeper exploration or peer teaching."
            )
        
        if system_adjustments.get("collaborative_learning", False):
            motivation_guidance_parts.append(
                "Suggest collaborative learning opportunities or ways the student "
                "could help others learn this concept."
            )
        
        return " ".join(motivation_guidance_parts)

    # NEW: Motivation history management
    async def _load_motivation_history(self, username: str, course: str) -> MotivationHistory:
        """Load motivation history from Redis"""
        try:
            if self.redis_client:
                key = f"motivation_history:{username}:{course}"
                if hasattr(self.redis_client, 'get_redis'):
                    data = self.redis_client.get_redis().get(key)
                else:
                    data = self.redis_client.get(key)
                
                if data:
                    history_dict = json.loads(data)
                    return self._deserialize_motivation_history(history_dict)
            
            # Return new history if none exists
            return MotivationHistory(
                baseline_established=False,
                baseline_interactions=[],
                recent_metrics=[],
                state_transitions=[],
                session_count=0
            )
            
        except Exception as e:
            print(f"DEBUG: Error loading motivation history: {e}")
            return MotivationHistory(
                baseline_established=False,
                baseline_interactions=[],
                recent_metrics=[],
                state_transitions=[],
                session_count=0
            )
    
    async def _update_motivation_history(
        self,
        username: str,
        course: str,
        metrics: MotivationMetrics,
        state: MotivationState,
        history: MotivationHistory
    ):
        """Update motivation history in Redis"""
        try:
            # Add current metrics to history
            history.recent_metrics.append(metrics)
            
            # Keep only recent metrics (last 20)
            if len(history.recent_metrics) > 20:
                history.recent_metrics = history.recent_metrics[-20:]
            
            # Track state transitions
            if not history.state_transitions or history.state_transitions[-1][0] != state:
                history.state_transitions.append((state, datetime.now()))
            
            # Keep only recent transitions (last 10)
            if len(history.state_transitions) > 10:
                history.state_transitions = history.state_transitions[-10:]
            
            # Store in Redis
            if self.redis_client:
                key = f"motivation_history:{username}:{course}"
                data = json.dumps(self._serialize_motivation_history(history))
                if hasattr(self.redis_client, 'get_redis'):
                    self.redis_client.get_redis().set(key, data, ex=86400*7)  # 7 days expiry
                else:
                    self.redis_client.set(key, data, ex=86400*7)
                    
        except Exception as e:
            print(f"DEBUG: Error updating motivation history: {e}")
    
    def _serialize_motivation_history(self, history: MotivationHistory) -> Dict[str, Any]:
        """Serialize motivation history for storage"""
        return {
            "baseline_established": history.baseline_established,
            "baseline_interactions": history.baseline_interactions,
            "recent_metrics": [
                {
                    "persistence_level": m.persistence_level.value,
                    "affective_score": m.affective_score,
                    "performance_score": m.performance_score,
                    "interaction_count": m.interaction_count,
                    "session_completion_rate": m.session_completion_rate,
                    "consecutive_correct": m.consecutive_correct,
                    "consecutive_incorrect": m.consecutive_incorrect,
                    "time_on_task": m.time_on_task,
                    "help_seeking_frequency": m.help_seeking_frequency
                }
                for m in history.recent_metrics
            ],
            "state_transitions": [
                [state.value, timestamp.isoformat()]
                for state, timestamp in history.state_transitions
            ],
            "session_count": history.session_count
        }
    
    def _deserialize_motivation_history(self, data: Dict[str, Any]) -> MotivationHistory:
        """Deserialize motivation history from storage"""
        recent_metrics = []
        for m_data in data.get("recent_metrics", []):
            metrics = MotivationMetrics(
                persistence_level=PersistenceLevel(m_data.get("persistence_level", "maintains_persistence")),
                affective_score=m_data.get("affective_score", 0.0),
                performance_score=m_data.get("performance_score", 0.5),
                interaction_count=m_data.get("interaction_count", 0),
                session_completion_rate=m_data.get("session_completion_rate", 0.0),
                consecutive_correct=m_data.get("consecutive_correct", 0),
                consecutive_incorrect=m_data.get("consecutive_incorrect", 0),
                time_on_task=m_data.get("time_on_task", 0.0),
                help_seeking_frequency=m_data.get("help_seeking_frequency", 0.0)
            )
            recent_metrics.append(metrics)
        
        state_transitions = []
        for state_data in data.get("state_transitions", []):
            if len(state_data) >= 2:
                state = MotivationState(state_data[0])
                timestamp = datetime.fromisoformat(state_data[1])
                state_transitions.append((state, timestamp))
        
        return MotivationHistory(
            baseline_established=data.get("baseline_established", False),
            baseline_interactions=data.get("baseline_interactions", []),
            recent_metrics=recent_metrics,
            state_transitions=state_transitions,
            session_count=data.get("session_count", 0)
        )

    # NEW: Motivation decision logging
    def _log_motivation_decisions(
        self,
        username: str,
        course: str,
        cognitive_state: CognitiveState,
        motivation_state: MotivationState,
        motivation_metrics: MotivationMetrics,
        session_context: Dict[str, Any]
    ):
        """Log motivation decisions for research analysis"""
        
        if not self.decision_logger:
            return
        
        try:
            motivation_data = {
                'username': username,
                'course': course,
                'mode': session_context.get('current_mode', 'unknown'),
                'motivation_state': motivation_state.value,
                'persistence_level': motivation_metrics.persistence_level.value,
                'affective_score': motivation_metrics.affective_score,
                'performance_score': motivation_metrics.performance_score,
                'session_completion_rate': motivation_metrics.session_completion_rate,
                'consecutive_correct': motivation_metrics.consecutive_correct,
                'consecutive_incorrect': motivation_metrics.consecutive_incorrect,
                'time_on_task': motivation_metrics.time_on_task,
                'help_seeking_frequency': motivation_metrics.help_seeking_frequency,
                'cognitive_load': cognitive_state.cognitive_load,
                'zpd_score': cognitive_state.zpd_score,
                'session_context': {
                    'question_number': session_context.get('question_number', 0),
                    'interaction_count': session_context.get('interaction_count', 0),
                    'current_accuracy': session_context.get('current_score', 0)
                }
            }
            
            # Log to decision logger
            self.decision_logger.log_motivation_decision(motivation_data)
                
        except Exception as e:
            print(f"DEBUG: Error logging motivation decisions: {e}")

    # EXISTING METHODS (from original code) - keeping all functionality

    async def _get_scaffolding_engine_decision(
        self, 
        cognitive_state: CognitiveState, 
        username: str, 
        session_context: Dict[str, Any]
    ):
        """ENHANCED: Get sophisticated scaffolding decision from scaffolding engine"""
        
        if not self.scaffolding_engine:
            return self._determine_scaffolding_strategy(
                cognitive_state.cognitive_load, cognitive_state.zpd_score
            )
        
        try:
            # Map cognitive load to discrete levels for scaffolding engine
            cl_level = self._map_cognitive_load_to_level(cognitive_state.cognitive_load)
            zpd_level = self._map_zpd_to_level(cognitive_state.zpd_score)
            
            # Get current learning objective from session context
            current_go = session_context.get('quiz_data', {}).get('current_question', {})
            go_id = current_go.get('go_id', 'UNKNOWN_GO')
            learning_objective = "_".join(go_id.split("_")[:3]) if go_id != 'UNKNOWN_GO' else 'UNKNOWN_LO'
            
            # Get recent performance for fading logic
            recent_performance = self._extract_recent_performance(session_context)
            
            # Get scaffolding decision from engine
            scaffolding_decision = self.scaffolding_engine.get_scaffolding_decision(
                cl_level=cl_level,
                zpd_level=zpd_level,
                username=username,
                learning_objective=learning_objective,
                recent_performance=recent_performance
            )
            
            print(f"DEBUG: 🎯 Scaffolding Engine - CL:{cl_level}, ZPD:{zpd_level} → {scaffolding_decision.strategy_type}@{scaffolding_decision.intensity_level}")
            
            return scaffolding_decision
            
        except Exception as e:
            print(f"DEBUG: Scaffolding engine error: {e}")
            # FIXED: Fallback returns consistent structure
            basic_decision = self._determine_scaffolding_strategy(
                cognitive_state.cognitive_load, cognitive_state.zpd_score
            )
            print(f"DEBUG: 📱 Using basic scaffolding fallback: {basic_decision.get('intervention_type', 'maintain_flow')}")
            return basic_decision
        
    def _map_cognitive_load_to_level(self, cognitive_load: float) -> str:
        """Map continuous cognitive load to discrete levels for scaffolding engine"""
        if cognitive_load >= 7.0:
            return "high"
        elif cognitive_load >= 4.0:
            return "medium"
        else:
            return "low"
    
    def _map_zpd_to_level(self, zpd_score: float) -> str:
        """Map ZPD score to discrete levels for scaffolding engine"""
        if zpd_score >= 0.8:
            return "high"
        elif zpd_score >= 0.5:
            return "medium"
        else:
            return "low"
    
    def _extract_recent_performance(self, session_context: Dict[str, Any]) -> List[bool]:
        """Extract recent performance for scaffolding fading logic"""
        try:
            # For quiz mode
            if 'quiz_history' in session_context:
                quiz_results = session_context['quiz_history']
                return [result.get('correct', False) for result in quiz_results[-5:]]
            
            # For tutor mode - check tutor session
            if 'tutor_session' in session_context:
                tutor_session = session_context['tutor_session']
                if hasattr(tutor_session, 'conversation_history'):
                    # Look for patterns of correct responses in conversation
                    recent_correct = []
                    for msg in tutor_session.conversation_history[-10:]:
                        if msg.get('role') == 'tutor' and 'correct' in msg.get('content', '').lower():
                            recent_correct.append(True)
                        elif msg.get('role') == 'tutor' and ('try again' in msg.get('content', '').lower() or 'not quite' in msg.get('content', '').lower()):
                            recent_correct.append(False)
                    return recent_correct[-5:]
            
            # Default empty performance
            return []
            
        except Exception as e:
            print(f"DEBUG: Error extracting recent performance: {e}")
            return []
    
    def _format_scaffolding_for_systems(self, scaffolding_decision) -> Dict[str, Any]:
        """Format scaffolding decision for quiz/tutor systems consumption"""
        
        # Handle both ScaffoldingDecision objects and basic dict responses
        if hasattr(scaffolding_decision, 'strategy_type'):
            # Sophisticated scaffolding engine decision
            return {
                "strategy_type": scaffolding_decision.strategy_type,
                "intensity_level": scaffolding_decision.intensity_level,
                "intervention_type": self._map_strategy_to_intervention(scaffolding_decision.strategy_type),
                "content_adaptations": scaffolding_decision.content_adaptations,
                "hint_structure": scaffolding_decision.hint_structure,
                "feedback_style": scaffolding_decision.feedback_style,
                "fade_threshold": scaffolding_decision.fade_threshold,
                "scaffolding_source": "engine",
                
                # For system consumption
                "difficulty_adjustment": self._map_intensity_to_difficulty(scaffolding_decision.intensity_level),
                "support_level": scaffolding_decision.intensity_level,
                "hint_count": len(scaffolding_decision.hint_structure),
                "example_count": scaffolding_decision.content_adaptations.get("example_count", 2)
            }
        else:
            # Basic scaffolding decision
            return {
                "intervention_type": scaffolding_decision.get("intervention_type", "maintain_flow"),
                "strategy_type": "procedural",  # Default
                "intensity_level": "medium",   # Default
                "scaffolding_source": "basic",
                "difficulty_adjustment": "maintain",
                "support_level": "medium",
                "hint_count": 2,
                "example_count": 2
            }
    
    def _map_strategy_to_intervention(self, strategy_type: str) -> str:
        """Map scaffolding strategy to intervention type for backward compatibility"""
        mapping = {
            "conceptual": "concept_review",
            "procedural": "task_breakdown", 
            "strategic": "maintain_flow",
            "metacognitive": "advanced_challenge"
        }
        return mapping.get(strategy_type, "maintain_flow")
    
    def _map_intensity_to_difficulty(self, intensity_level: str) -> str:
        """Map scaffolding intensity to difficulty adjustment"""
        mapping = {
            "very_high": "decrease_significantly",
            "high": "decrease",
            "medium": "maintain",
            "low": "increase",
            "minimal": "increase_significantly"
        }
        return mapping.get(intensity_level, "maintain")

    def _generate_enhanced_adaptive_context(
        self, 
        current_mode: str, 
        scaffolding_decision, 
        motivation: Dict, 
        cognitive_state: CognitiveState,
        session_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate enhanced adaptive context with scaffolding details"""
        
        # FIXED: Handle both ScaffoldingDecision objects and dict fallbacks
        if hasattr(scaffolding_decision, 'strategy_type'):
            # ScaffoldingDecision object
            strategy_type = scaffolding_decision.strategy_type
            intensity_level = scaffolding_decision.intensity_level
            content_adaptations = scaffolding_decision.content_adaptations
        else:
            # Dict fallback
            strategy_type = scaffolding_decision.get('intervention_type', 'procedural')
            intensity_level = scaffolding_decision.get('intensity_level', 'medium')
            content_adaptations = {}
        
        base_context = {
            "scaffolding_needed": strategy_type,
            "difficulty_adjustment": self._map_intensity_to_difficulty(intensity_level),
            "motivation_tone": motivation.get("message_tone", "encouraging"),
            "urgency_level": intensity_level,
            "cognitive_load_level": cognitive_state.cognitive_load,
            "mastery_informed": len(cognitive_state.mastery_data) > 0,
            "scaffolding_source": "engine" if hasattr(scaffolding_decision, 'strategy_type') else "basic"
        }
        
        # Add scaffolding-specific adaptations if available
        if content_adaptations:
            base_context.update({
                "content_density": content_adaptations.get("content_density", "moderate"),
                "example_count": content_adaptations.get("example_count", 2),
                "visualization_level": content_adaptations.get("visualization_level", "moderate_visual"),
                "interaction_type": content_adaptations.get("interaction_type", "structured_interactive"),
                "pacing": content_adaptations.get("pacing", "moderate_paced")
            })
        
        # Add mode-specific context
        base_context[f"{current_mode}_specific"] = self._get_mode_specific_context(
            current_mode, scaffolding_decision, session_context
        )
        
        return base_context
    
    def _get_mode_specific_context(
        self, 
        mode: str, 
        scaffolding_decision, 
        session_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get mode-specific adaptive context"""
        
        # FIXED: Safe attribute access for both object types
        if hasattr(scaffolding_decision, 'strategy_type'):
            strategy_type = scaffolding_decision.strategy_type
            intensity_level = scaffolding_decision.intensity_level
        else:
            strategy_type = scaffolding_decision.get('intervention_type', 'procedural')
            intensity_level = scaffolding_decision.get('intensity_level', 'medium')
        
        if mode == "quiz":
            return {
                "question_type_preference": self._get_question_type_recommendation(scaffolding_decision),
                "time_pressure": "reduced" if intensity_level in ['very_high', 'high'] else "normal",
                "hint_availability": "extensive" if intensity_level in ['very_high', 'high'] else "minimal"
            }
        
        elif mode == "tutor":
            return {
                "explanation_depth": self._get_explanation_depth(scaffolding_decision),
                "question_frequency": "high" if strategy_type == 'metacognitive' else "moderate",
                "example_preference": "worked_examples" if strategy_type == 'procedural' else "conceptual_models"
            }
        
        else:  # chat
            return {
                "response_style": "detailed" if intensity_level in ['very_high', 'high'] else "concise",
                "probing_questions": "frequent" if strategy_type == 'metacognitive' else "occasional"
            }
    
    def _get_question_type_recommendation(self, scaffolding_decision) -> str:
        """Recommend question type based on scaffolding decision"""
        
        # FIXED: Safe attribute access
        if hasattr(scaffolding_decision, 'strategy_type'):
            strategy = scaffolding_decision.strategy_type
            intensity = scaffolding_decision.intensity_level
        else:
            strategy = scaffolding_decision.get('intervention_type', 'procedural')
            intensity = scaffolding_decision.get('intensity_level', 'medium')
        
        if intensity in ['very_high', 'high']:
            return "multiple_choice"  # Easier for high cognitive load
        elif strategy == 'metacognitive':
            return "open_ended"      # Self-reflection
        elif strategy == 'procedural':
            return "fill_in_blank"   # Step-by-step
        else:
            return "multiple_choice" # Default
    
    def _get_explanation_depth(self, scaffolding_decision) -> str:
        """Get explanation depth based on scaffolding"""
        
        # FIXED: Safe attribute access
        if hasattr(scaffolding_decision, 'intensity_level'):
            intensity = scaffolding_decision.intensity_level
        else:
            intensity = scaffolding_decision.get('intensity_level', 'medium')
        
        depth_map = {
            "very_high": "very_detailed",
            "high": "detailed", 
            "medium": "moderate",
            "low": "concise",
            "minimal": "brief"
        }
        
        return depth_map.get(intensity, "moderate")
    
    def _generate_enhanced_llm_guidance(
        self, 
        scaffolding_decision, 
        motivation: Dict, 
        current_mode: str, 
        cognitive_state: CognitiveState
    ) -> str:
        """Generate enhanced LLM guidance with scaffolding integration"""
        
        guidance_parts = []
        
        # FIXED: Safe attribute access for scaffolding guidance
        if hasattr(scaffolding_decision, 'strategy_type'):
            # ScaffoldingDecision object
            strategy_type = scaffolding_decision.strategy_type
            intensity_level = scaffolding_decision.intensity_level
            
            # Base guidance from scaffolding
            strategy_guidance = {
                "conceptual": "Focus on explaining core concepts and relationships. Use analogies and concept maps.",
                "procedural": "Provide step-by-step guidance. Break down processes into clear stages.",
                "strategic": "Help student choose appropriate problem-solving strategies. Compare different approaches.",
                "metacognitive": "Encourage self-reflection. Ask questions about learning process and confidence."
            }
            guidance_parts.append(strategy_guidance.get(strategy_type, "Provide supportive guidance."))
            
            # Intensity-specific guidance
            if intensity_level == "very_high":
                guidance_parts.append("Provide maximum support with detailed explanations and extensive examples.")
            elif intensity_level == "high":
                guidance_parts.append("Offer substantial support with clear explanations and multiple examples.")
            elif intensity_level == "low":
                guidance_parts.append("Provide minimal scaffolding. Encourage independent thinking.")
            elif intensity_level == "minimal":
                guidance_parts.append("Give very light support. Challenge the student to think independently.")
        else:
            # Dict fallback
            intervention_type = scaffolding_decision.get('intervention_type', 'maintain_flow')
            guidance_parts.append(f"Use {intervention_type} approach to support learning.")
        
        # Motivation-based guidance
        if motivation.get("confidence_boost", False):
            guidance_parts.append("Provide extra encouragement and positive reinforcement.")
        elif motivation.get("challenge_ready", False):
            guidance_parts.append("Increase challenge level and encourage deeper exploration.")
        
        # Cognitive load adjustments
        if cognitive_state.cognitive_load > 7:
            guidance_parts.append("Keep responses concise and break complex ideas into simple steps.")
        elif cognitive_state.cognitive_load < 3:
            guidance_parts.append("Add interactive elements, ask probing questions, and increase complexity.")
        
        return " ".join(guidance_parts)
    
    def _log_orchestrator_decisions(
        self, 
        username: str, 
        course: str, 
        cognitive_state: CognitiveState,
        scaffolding_decision,
        session_context: Dict[str, Any]
    ):
        """Log orchestrator decisions for research analysis"""
        
        if not self.decision_logger:
            return
        
        try:
            # FIXED: Safe attribute access for logging
            if hasattr(scaffolding_decision, 'strategy_type'):
                strategy_type = scaffolding_decision.strategy_type
                intensity_level = scaffolding_decision.intensity_level
                fade_threshold = scaffolding_decision.fade_threshold
            else:
                strategy_type = scaffolding_decision.get('intervention_type', 'basic')
                intensity_level = scaffolding_decision.get('intensity_level', 'medium')
                fade_threshold = 3  # Default
            
            # Log cognitive decision
            cognitive_data = {
                'username': username,
                'course': course,
                'mode': session_context.get('current_mode', 'unknown'),
                'cognitive_load': cognitive_state.cognitive_load,
                'zpd_score': cognitive_state.zpd_score,
                'motivation': cognitive_state.motivation_score,
                'fatigue': cognitive_state.fatigue_level,
                'scaffolding_decision': strategy_type,
                'intervention_type': self._map_strategy_to_intervention(strategy_type),
                'difficulty_adjustment': self._map_intensity_to_difficulty(intensity_level),
                'session_context': {
                    'question_number': session_context.get('question_number', 0),
                    'interaction_count': session_context.get('interaction_count', 0),
                    'current_accuracy': session_context.get('current_score', 0)
                }
            }
            
            self.decision_logger.log_cognitive_decision(cognitive_data)
            
            # Log scaffolding decision if from engine
            if hasattr(scaffolding_decision, 'strategy_type'):
                scaffolding_data = {
                    'username': username,
                    'course': course,
                    'go_id': session_context.get('current_go_id', 'unknown'),
                    'cl_level': self._map_cognitive_load_to_level(cognitive_state.cognitive_load),
                    'zpd_level': self._map_zpd_to_level(cognitive_state.zpd_score),
                    'strategy_type': strategy_type,
                    'intensity_level': intensity_level,
                    'fade_threshold': fade_threshold,
                    'consecutive_correct': len([p for p in self._extract_recent_performance(session_context) if p]),
                    'was_faded': intensity_level in ['low', 'minimal']
                }
                
                self.decision_logger.log_scaffolding_decision(scaffolding_data)
                
        except Exception as e:
            print(f"DEBUG: Error logging orchestrator decisions: {e}")
            

    def calculate_zpd_alignment_fixed(self, difficulty: float, mastery_level: float) -> Dict[str, Any]:
        """FIXED: Calculate ZPD alignment with proper logic"""
        
        # Normalize difficulty to 0-1 scale
        if difficulty > 1.0:
            normalized_difficulty = difficulty / 10.0
        else:
            normalized_difficulty = difficulty
        
        # Define ZPD boundaries (slightly above current mastery)
        zpd_lower = max(0.0, mastery_level - 0.1)  
        zpd_upper = min(1.0, mastery_level + 0.3)  
        
        # Determine if in ZPD
        in_zpd = zpd_lower <= normalized_difficulty <= zpd_upper
        
        # Calculate alignment score
        if in_zpd:
            zpd_center = (zpd_lower + zpd_upper) / 2
            distance_from_center = abs(normalized_difficulty - zpd_center)
            zpd_width = zpd_upper - zpd_lower
            alignment_score = 1.0 - (distance_from_center / (zpd_width / 2))
        else:
            if normalized_difficulty < zpd_lower:
                distance = zpd_lower - normalized_difficulty
            else:
                distance = normalized_difficulty - zpd_upper
            alignment_score = max(0.0, 1.0 - distance * 2)
        
        result = {
            'in_zpd': in_zpd,
            'alignment_score': alignment_score,
            'normalized_difficulty': normalized_difficulty,
            'mastery_level': mastery_level,
            'zpd_range': f"[{zpd_lower:.2f}, {zpd_upper:.2f}]"
        }
        
        print(f"DEBUG: ZPD Analysis - Diff: {normalized_difficulty:.2f}, "
              f"Mastery: {mastery_level:.2f}, In ZPD: {in_zpd}, Score: {alignment_score:.2f}")
        
        return result
    
    async def _assess_cognitive_state_mcp(self, username: str, state: Dict[str, Any], mastery_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced cognitive assessment with MCP mastery data"""
        try:
            # Get recent accuracy from mastery data
            go_masteries = mastery_data.get("go_masteries", {})
            recent_accuracy = np.mean(list(go_masteries.values())) if go_masteries else 0.5
            
            # Get week difficulty via MCP
            course = state.get("selected_course", "CMP511")
            week = state.get("selected_week", 1)
            week_difficulty = await self._get_week_difficulty_mcp(course, week)
            
            # Get interaction count from mastery data
            interaction_count = mastery_data.get("total_interactions", 0)
            
            # Calculate cognitive load
            cognitive_load = self._calculate_cognitive_load_formula(
                recent_accuracy, week_difficulty, interaction_count
            )
            
            # Enhanced motivation from mastery data
            motivation = self._calculate_motivation_from_mastery(mastery_data)
            
            return {
                "cl_value": cognitive_load,
                "zpd_score": recent_accuracy,
                "motivation": motivation,
                "recommendation": self._get_cl_recommendation(cognitive_load),
                "mastery_context": mastery_data.get("averages", {}),
                "formula_variables": {
                    "accuracy": recent_accuracy,
                    "difficulty": week_difficulty,
                    "interaction_count": interaction_count,
                    "task_type": 0.5
                }
            }
            
        except Exception as e:
            print(f"DEBUG: Error in MCP cognitive assessment: {e}")
            return {
                "cl_value": 5.0,
                "zpd_score": 0.5,
                "motivation": 0.5,
                "recommendation": "maintain"
            }

    # LEGACY METHOD: Keep for backward compatibility
    async def _calculate_cognitive_state_mcp(
        self, 
        username: str, 
        course: str, 
        student_input: str,
        interaction_type: InteractionType,
        session_context: Dict[str, Any],
        mastery_data: Dict[str, Any]
    ) -> CognitiveState:
        """Legacy method - redirects to enhanced version"""
        
        # Create default motivation state and metrics for legacy calls
        default_motivation_state = MotivationState.MOTIVATION_PLATEAU
        default_motivation_metrics = MotivationMetrics(
            persistence_level=PersistenceLevel.MAINTAINS_PERSISTENCE,
            affective_score=0.0,
            performance_score=0.5,
            interaction_count=1,
            session_completion_rate=0.5,
            consecutive_correct=0,
            consecutive_incorrect=0,
            time_on_task=0.0,
            help_seeking_frequency=0.0
        )
        
        return await self._calculate_enhanced_cognitive_state(
            username, course, student_input, interaction_type,
            session_context, mastery_data, default_motivation_state, default_motivation_metrics
        )
    
    async def _generate_enhanced_response_mcp(
        self, 
        query: str, 
        state: Dict, 
        scaffolding: Dict,
        course: str
    ) -> str:
        """Generate enhanced response using MCP RAG integration"""
        try:
            # Get course content via MCP RAG
            rag_result = await self.mcp_client.get_course_content_via_rag(
                query=query,
                course=course,
                max_results=3
            )
            
            if rag_result.get("success", False):
                course_content = rag_result["content"]
                print(f"DEBUG: Retrieved RAG content via MCP - {rag_result['num_results']} results")
            else:
                course_content = f"Course content for {course} available but could not be retrieved."
                print(f"DEBUG: RAG via MCP failed: {rag_result.get('error', 'Unknown error')}")
            
            # Generate response with OpenAI
            from openai import OpenAI
            openai_client = OpenAI()
            
            # Build enhanced prompt with RAG content and scaffolding
            username = state.get("username", "Student")
            week = state.get("selected_week", 1)
            
            scaffolding_instruction = scaffolding.get("llm_instruction", "Provide helpful information.")
            cl_value = scaffolding.get("cognitive_load_score", 5.0)
            
            if cl_value > 7:
                response_style = "Keep responses concise and break complex ideas into simple steps."
            elif cl_value < 3:
                response_style = "Add interactive elements and ask follow-up questions."
            else:
                response_style = "Provide comprehensive but clear explanations."
            
            system_prompt = f"""You are LEA, an intelligent learning assistant for {course}.

CURRENT CONTEXT:
- Course: {course}, Week {week}
- Student: {username}
- Scaffolding Strategy: {scaffolding_instruction}
- Response Style: {response_style}

RELEVANT COURSE CONTENT:
{course_content}

INSTRUCTIONS:
1. Answer using the course content when relevant
2. Apply the scaffolding strategy appropriately
3. Be conversational and engaging - you're LEA!
4. Use the response style to match the student's cognitive state
5. If question isn't course-related, be helpful but try to connect to learning

Remember: "Slide In. Study Up. Show Off." - Keep it friendly!"""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ]
            
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )
            
            generated_response = response.choices[0].message.content.strip()
            print(f"DEBUG: Generated MCP-enhanced response")
            return generated_response
            
        except Exception as e:
            print(f"DEBUG: Error generating MCP-enhanced response: {e}")
            # Fallback response
            return f"I understand you're asking about {query}. Let me help you explore this topic step by step."
    
    async def _get_week_difficulty_mcp(self, course: str, week: int) -> float:
        """Get week difficulty via MCP KC model lookup"""
        try:
            kc_result = await self.mcp_client.get_kc_model_data(course)
            if kc_result.get("success", False):
                kc_model = kc_result["kc_model"]
                # Extract week difficulty from KC model
                week_key = f"week_{week:02d}"
                if "week_navigation" in kc_model and week_key in kc_model["week_navigation"]:
                    # Calculate difficulty based on learning objectives complexity
                    week_data = kc_model["week_navigation"][week_key]
                    los = week_data.get("learning_objectives", [])
                    
                    # Base difficulty increases with week number
                    base_difficulty = 0.3 + (week - 1) * 0.05
                    
                    # Complexity based on number of GOs
                    total_gos = sum(len(lo.get("granular_objectives", [])) for lo in los)
                    complexity_factor = min(0.3, total_gos * 0.02)
                    
                    final_difficulty = min(0.9, base_difficulty + complexity_factor)
                    print(f"DEBUG: Week {week} difficulty via MCP: {final_difficulty:.2f}")
                    return final_difficulty
            
            # Fallback calculation
            return 0.3 + (week - 1) * 0.05
            
        except Exception as e:
            print(f"DEBUG: Error getting week difficulty via MCP: {e}")
            return 0.5
    
    async def _get_current_difficulty_mcp(self, course: str, session_context: Dict) -> float:
        """Get current difficulty via MCP with session context"""
        try:
            week = session_context.get("selected_week", 1)
            
            # For quiz mode, use question type
            if "quiz_data" in session_context:
                current_question = session_context["quiz_data"].get("current_question", {})
                question_type = current_question.get("type", "multiple_choice")
                
                type_difficulty = {
                    "multiple_choice": 0.4,
                    "true_false": 0.3,
                    "fill_in_blank": 0.6,
                    "open_ended": 0.8
                }
                
                base_difficulty = type_difficulty.get(question_type, 0.5)
                question_number = session_context.get("question_number", 1)
                total_questions = session_context.get("total_questions", 10)
                
                if total_questions > 0:
                    progression_factor = (question_number / total_questions) * 0.2
                    return min(1.0, base_difficulty + progression_factor)
                
                return base_difficulty
            
            # For other modes, get week difficulty
            return await self._get_week_difficulty_mcp(course, week)
            
        except Exception as e:
            print(f"DEBUG: Error getting current difficulty via MCP: {e}")
            return 0.5
    
    def _calculate_motivation_from_mastery(self, mastery_data: Dict[str, Any]) -> float:
        """Calculate motivation from mastery data using CS formula"""
        try:
            averages = mastery_data.get("averages", {})
            
            go_mastery = averages.get("go_mastery", 0.0)
            lo_mastery = averages.get("lo_mastery", 0.0)
            week_mastery = averages.get("week_mastery", 0.0)
            
            # Apply CS formula: CS = 0.5GO + 0.3LO + 0.2W
            motivation_score = (
                self.motivation_params['go_weight'] * go_mastery +
                self.motivation_params['lo_weight'] * lo_mastery +
                self.motivation_params['week_weight'] * week_mastery
            )
            
            # Ensure in 0-1 range
            motivation_score = max(0.0, min(1.0, motivation_score))
            
            print(f"DEBUG: Motivation from mastery - GO: {go_mastery:.2f}, "
                  f"LO: {lo_mastery:.2f}, Week: {week_mastery:.2f} -> {motivation_score:.2f}")
            
            return motivation_score
            
        except Exception as e:
            print(f"DEBUG: Error calculating motivation from mastery: {e}")
            return 0.5
    
    async def _update_mastery_mcp(
        self,
        username: str,
        course: str,
        user_query: str,
        state: Dict[str, Any],
        cognitive_assessment: Dict[str, Any]
    ):
        """Update mastery via MCP for chat interactions"""
        try:
            week_number = state.get("selected_week", 1)
            
            interaction_data = {
                "student_response": user_query,
                "interaction_type": "chat",
                "week_number": week_number,
                "go_id": f"GO_{week_number:02d}_CHAT_01",
                "lo_id": f"LO_{week_number:02d}_CHAT",
                "course_code": course,
                "cognitive_load": cognitive_assessment.get("cl_value", 5.0),
                "zpd_score": cognitive_assessment.get("zpd_score", 0.5)
            }
            
            result = await self.mcp_client.update_mastery(username, course, interaction_data)
            
            if result.get("success", False):
                print(f"DEBUG: Mastery updated via MCP for {username}")
            else:
                print(f"DEBUG: MCP mastery update failed: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            print(f"DEBUG: Error updating mastery via MCP: {e}")
    
    async def _update_mastery_interaction_mcp(
        self,
        username: str,
        course: str,
        interaction_type: InteractionType,
        student_input: str,
        session_context: Dict[str, Any]
    ):
        """Update mastery for specific interaction types via MCP"""
        try:
            week_number = session_context.get("selected_week", 1)
            
            # Extract interaction-specific data
            interaction_data = {
                "student_response": student_input,
                "interaction_type": interaction_type.value,
                "week_number": week_number,
                "course_code": course
            }
            
            # Add quiz-specific data if available
            if interaction_type == InteractionType.QUIZ_ANSWER and "quiz_result" in session_context:
                quiz_result = session_context["quiz_result"]
                interaction_data.update({
                    "is_correct": quiz_result.get("correct", False),
                    "go_id": session_context.get("quiz_data", {}).get("current_question", {}).get("go_id", f"GO_{week_number:02d}_01_01"),
                    "lo_id": f"LO_{week_number:02d}_01"
                })
            else:
                interaction_data.update({
                    "go_id": f"GO_{week_number:02d}_01_01",
                    "lo_id": f"LO_{week_number:02d}_01"
                })
            
            result = await self.mcp_client.update_mastery(username, course, interaction_data)
            
            if result.get("success", False):
                print(f"DEBUG: {interaction_type.value} mastery updated via MCP")
            else:
                print(f"DEBUG: MCP {interaction_type.value} mastery update failed")
                
        except Exception as e:
            print(f"DEBUG: Error updating {interaction_type.value} mastery via MCP: {e}")
    
    # Helper methods
    def _calculate_cognitive_load_formula(self, accuracy: float, difficulty: float, interaction_count: int) -> float:
        """Calculate cognitive load using research formula"""
        cl = (
            self.cl_params['beta_0'] +
            self.cl_params['beta_1'] * difficulty +
            self.cl_params['beta_2'] * (1 - accuracy) +
            self.cl_params['beta_4'] * interaction_count +
            self.cl_params['beta_5'] * 0.5  # Default task type
        )
        return max(0, min(10, cl))
    
    def _get_cl_recommendation(self, cl_value: float) -> str:
        """Get recommendation based on cognitive load"""
        if cl_value < 3.5:
            return "increase_challenge"
        elif cl_value > 6.5:
            return "reduce_difficulty"
        else:
            return "maintain"
    
    def _classify_task_type(self, interaction_type: InteractionType, student_input: str) -> float:
        """Classify task type for cognitive load calculation"""
        if interaction_type == InteractionType.QUIZ_ANSWER:
            return 0.0  # Structured
        elif len(student_input.split()) > 15:
            return 1.0  # Open-ended
        else:
            return 0.0  # Structured
    
    def _determine_scaffolding_strategy(self, cognitive_load: float, zpd_score: float) -> Dict[str, Any]:
        """Determine scaffolding strategy using CL x ZPD matrix"""
        # Classify levels
        if cognitive_load >= 7:
            cl_level = "high"
        elif cognitive_load >= 4:
            cl_level = "normal"
        else:
            cl_level = "low"
            
        if zpd_score > 0.8:
            zpd_level = "high"
        elif zpd_score >= 0.5:
            zpd_level = "optimal" 
        else:
            zpd_level = "low"
        
        # Scaffolding matrix (simplified)
        strategies = {
            ("high", "low"): {
                "intervention_type": "immediate_support",
                "llm_instruction": "Provide step-by-step guidance and reduce complexity.",
                "urgency": "critical"
            },
            ("high", "optimal"): {
                "intervention_type": "task_breakdown", 
                "llm_instruction": "Break content into smaller steps and check understanding.",
                "urgency": "high"
            },
            ("normal", "optimal"): {
                "intervention_type": "maintain_flow",
                "llm_instruction": "Continue current approach with minimal adjustments.",
                "urgency": "none"
            },
            ("low", "high"): {
                "intervention_type": "advanced_challenge",
                "llm_instruction": "Increase difficulty and minimize scaffolding.",
                "urgency": "medium"
            }
        }
        
        strategy_key = (cl_level, zpd_level)
        strategy = strategies.get(strategy_key, strategies[("normal", "optimal")])
        
        strategy.update({
            "cognitive_load_level": cl_level,
            "zpd_level": zpd_level,
            "cognitive_load_score": cognitive_load,
            "zpd_score": zpd_score
        })
        
        return strategy
    
    def _determine_scaffolding_level(self, cognitive_load: float, zpd_score: float) -> str:
        """Determine scaffolding level"""
        if cognitive_load >= 8 or zpd_score < 0.3:
            return "intensive"
        elif cognitive_load >= 6 or zpd_score < 0.5:
            return "high"
        elif cognitive_load >= 4:
            return "medium"
        else:
            return "low"
    
    def _assess_session_quality(self, cl: float, zpd: float, motivation: float, fatigue: float) -> str:
        """Assess overall session quality"""
        if 4 <= cl <= 6 and 0.5 <= zpd <= 0.8 and motivation > 0.6:
            return "excellent"
        elif cl > 8 or motivation < 0.3 or fatigue > 0.8:
            return "concerning"
        else:
            return "good"
    
    async def _calculate_motivation_feedback_mcp(self, username: str, course: str, motivation_score: float) -> Dict[str, Any]:
        """Generate motivation feedback"""
        if motivation_score >= 0.8:
            return {
                "motivation_level": "high",
                "message_tone": "challenging",
                "confidence_boost": False,
                "challenge_ready": True
            }
        elif motivation_score >= 0.6:
            return {
                "motivation_level": "moderate",
                "message_tone": "encouraging", 
                "confidence_boost": False,
                "challenge_ready": False
            }
        else:
            return {
                "motivation_level": "low",
                "message_tone": "supportive",
                "confidence_boost": True,  
                "challenge_ready": False
            }
    
    def _generate_adaptive_context(self, current_mode: str, scaffolding: Dict, motivation: Dict, cognitive_state: CognitiveState) -> Dict[str, Any]:
        """Generate adaptive context for mode-specific adjustments"""
        return {
            "scaffolding_needed": scaffolding.get("intervention_type", "maintain_flow"),
            "difficulty_adjustment": "maintain",  # Could be enhanced
            "motivation_tone": motivation.get("message_tone", "encouraging"),
            "urgency_level": scaffolding.get("urgency", "none"),
            "cognitive_load_level": cognitive_state.cognitive_load,
            "mastery_informed": len(cognitive_state.mastery_data) > 0
        }
    
    def _generate_llm_guidance(self, scaffolding: Dict, motivation: Dict, current_mode: str, cognitive_state: CognitiveState) -> str:
        """Generate LLM guidance string"""
        guidance_parts = [scaffolding.get("llm_instruction", "Provide helpful guidance.")]
        
        if motivation.get("confidence_boost", False):
            guidance_parts.append("Provide extra encouragement and reassurance.")
        
        if cognitive_state.cognitive_load > 7:
            guidance_parts.append("Keep response concise and break into small steps.")
        elif cognitive_state.cognitive_load < 3:
            guidance_parts.append("Add interactive elements and ask questions.")
        
        return " ".join(guidance_parts)
    
    async def _store_cognitive_state(self, username: str, course: str, cognitive_state: CognitiveState):
        """Store cognitive state in Redis"""
        try:
            if self.redis_client:
                key = f"cognitive_state:{username}:{course}"
                data = json.dumps(cognitive_state.to_dict())
                if hasattr(self.redis_client, 'get_redis'):
                    self.redis_client.get_redis().set(key, data)
                else:
                    self.redis_client.set(key, data) 
        except Exception as e:
            print(f"DEBUG: Error storing cognitive state: {e}")
    
    def _get_fallback_response(self, current_mode: str) -> Dict[str, Any]:
        """Fallback response when processing fails"""
        default_motivation_metrics = MotivationMetrics(
            persistence_level=PersistenceLevel.MAINTAINS_PERSISTENCE,
            affective_score=0.0,
            performance_score=0.5,
            interaction_count=1,
            session_completion_rate=0.5,
            consecutive_correct=0,
            consecutive_incorrect=0,
            time_on_task=0.0,
            help_seeking_frequency=0.0
        )
        
        return {
            'cognitive_state': CognitiveState(
                cognitive_load=5.0, zpd_score=0.6, motivation_score=0.6,
                motivation_state=MotivationState.MOTIVATION_PLATEAU,
                motivation_metrics=default_motivation_metrics,
                fatigue_level=0.3, scaffolding_level="medium", session_quality="good",
                mastery_data={}
            ),
            'scaffolding_strategy': {
                "intervention_type": "maintain_flow",
                "llm_instruction": "Continue with supportive guidance."
            },
            'motivation_feedback': {"motivation_level": "moderate", "message_tone": "encouraging"},
            'motivation_state': MotivationState.MOTIVATION_PLATEAU.value,
            'motivation_metrics': default_motivation_metrics,
            'adaptive_context': {},
            'orchestrator_guidance': "Continue with current approach.",
            'processing_successful': False,
            'mcp_integrated': False,
            'motivation_enhanced': False
        }
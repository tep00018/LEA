# File: lea_tutor_simulation-082525-week-4-with Logs.py
## Week 1 only - rerun for LLM logs
## Enhanced version with complete LLM judge reasoning capture
"""
Natural Progression Tutor Mode Simulation for LEA CMP511
ENHANCED VERSION: Includes complete LLM judge reasoning capture (strengths, issues, explanations)
"""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
import json
import csv
import time
import os
import sys
import logging
import pickle
from pathlib import Path
from openai import AsyncOpenAI
from collections import defaultdict

# Suppress debug messages
logging.getLogger('src').setLevel(logging.WARNING)
logging.getLogger('redis').setLevel(logging.WARNING)
logging.getLogger('openai').setLevel(logging.WARNING)

# Import LEA components
sys.path.append(str(Path(__file__).parent))
from src.core.kc_model_loader import KCModelLoader
from src.storage.redis_client import LEARedisClient
from lea_real_integration2 import RealLEASystemConnector
from lea_metrics_tracker import SimulationMetrics

# ============================================================================
# METRICS CLASSES (Keep existing from original)
# ============================================================================

@dataclass
class RAGAlignmentMetrics:
    """Metrics for RAG alignment evaluation"""
    content_accuracy: float = 0.0
    kc_relevance: float = 0.0
    integration_quality: float = 0.0
    uses_retrieved_content: bool = False
    stays_on_topic: bool = True
    includes_hallucinations: bool = False
    strengths: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    explanation: str = ""
    
    def get_overall_score(self) -> float:
        weights = {
            'content_accuracy': 0.5,
            'kc_relevance': 0.3,
            'integration_quality': 0.2
        }
        return (
            self.content_accuracy * weights['content_accuracy'] +
            self.kc_relevance * weights['kc_relevance'] +
            self.integration_quality * weights['integration_quality']
        )

@dataclass
class CoherenceMetrics:
    """Metrics for multi-turn coherence evaluation"""
    context_maintenance: float = 0.0
    progress_tracking: float = 0.0
    logical_flow: float = 0.0
    prompts_thinking: bool = False
    addresses_misconceptions: bool = False
    builds_on_prior: bool = True
    references_prior_turns: bool = False
    maintains_teaching_style: bool = True
    shows_progression: bool = False
    addresses_student_needs: bool = False
    strengths: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    explanation: str = ""
    
    def get_overall_score(self) -> float:
        weights = {
            'context_maintenance': 0.35,
            'progress_tracking': 0.35,
            'logical_flow': 0.30
        }
        return (
            self.context_maintenance * weights['context_maintenance'] +
            self.progress_tracking * weights['progress_tracking'] +
            self.logical_flow * weights['logical_flow']
        )

@dataclass
class AdaptiveFeedbackMetrics:
    """Metrics for adaptive feedback evaluation"""
    learner_state_match: float = 0.0
    timing_appropriateness: float = 0.0
    pedagogical_quality: float = 0.0
    scaffolding_effectiveness: float = 0.0
    encouragement_appropriateness: float = 0.0
    provides_hints: bool = False
    acknowledges_progress: bool = False
    adjusts_difficulty: bool = False
    scaffolding_level_appropriate: bool = False
    motivational_elements_present: bool = False
    difficulty_adjustment_correct: bool = False
    strengths: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    explanation: str = ""
    
    def get_overall_score(self) -> float:
        weights = {
            'learner_state_match': 0.4,
            'timing_appropriateness': 0.3,
            'pedagogical_quality': 0.3
        }
        return (
            self.learner_state_match * weights['learner_state_match'] +
            self.timing_appropriateness * weights['timing_appropriateness'] +
            self.pedagogical_quality * weights['pedagogical_quality']
        )

# ============================================================================
# CHECKPOINT MANAGER
# ============================================================================

class CheckpointManager:
    """Manages checkpointing and recovery for simulation"""
    
    def __init__(self, checkpoint_dir: str = 'tutor_natural_checkpoints'):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(exist_ok=True)
        self.current_checkpoint_file = self.checkpoint_dir / 'current_checkpoint.json'
        
    def save_checkpoint(self, 
                       learner_idx: int,
                       learner_name: str,
                       detailed_logs: List[Dict],
                       session_summaries: List[Dict],
                       go_complexity_data: List[Dict],
                       timestamp: str):
        """Save checkpoint after each learner completes"""
        
        checkpoint_data = {
            'timestamp': timestamp,
            'last_completed_learner_idx': learner_idx,
            'last_completed_learner_name': learner_name,
            'total_logs': len(detailed_logs),
            'total_sessions': len(session_summaries),
            'checkpoint_time': datetime.now().isoformat()
        }
        
        # Save the actual data
        data_file = self.checkpoint_dir / f'checkpoint_learner_{learner_idx}_{timestamp}.pkl'
        with open(data_file, 'wb') as f:
            pickle.dump({
                'detailed_logs': detailed_logs,
                'session_summaries': session_summaries,
                'go_complexity_data': go_complexity_data
            }, f)
        
        # Update current checkpoint reference
        with open(self.current_checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        
        print(f"\n💾 Checkpoint saved for learner {learner_idx}: {learner_name}")
        print(f"   • Logs: {len(detailed_logs)}, Sessions: {len(session_summaries)}")
        
        return data_file
    
    def load_latest_checkpoint(self) -> Optional[Dict]:
        """Load the most recent checkpoint if it exists"""
        
        if not self.current_checkpoint_file.exists():
            return None
        
        try:
            with open(self.current_checkpoint_file, 'r') as f:
                checkpoint_info = json.load(f)
            
            # Load the actual data
            learner_idx = checkpoint_info['last_completed_learner_idx']
            timestamp = checkpoint_info['timestamp']
            data_file = self.checkpoint_dir / f'checkpoint_learner_{learner_idx}_{timestamp}.pkl'
            
            if data_file.exists():
                with open(data_file, 'rb') as f:
                    data = pickle.load(f)
                
                return {
                    'checkpoint_info': checkpoint_info,
                    'data': data
                }
        except Exception as e:
            print(f"⚠️ Could not load checkpoint: {e}")
        
        return None
    
    def clear_checkpoints(self):
        """Clear all checkpoint files"""
        for file in self.checkpoint_dir.glob('*.pkl'):
            file.unlink()
        if self.current_checkpoint_file.exists():
            self.current_checkpoint_file.unlink()

# ============================================================================
# ENHANCED LLM JUDGE EVALUATOR WITH FULL REASONING CAPTURE
# ============================================================================

class EnhancedTutorLLMJudgeEvaluator:
    """Enhanced LLM-as-Judge evaluator with complete reasoning capture"""
    
    def __init__(self, llm_client: AsyncOpenAI, enable_judge: bool = True, sample_rate: float = 1.0):
        self.llm_client = llm_client
        self.enable_judge = enable_judge
        self.sample_rate = sample_rate
        self.evaluation_cache = {}
        self.metrics_log = []
        
    def should_evaluate(self) -> bool:
        """Determine if this interaction should be evaluated based on sampling rate"""
        return self.enable_judge and np.random.random() < self.sample_rate
    
    async def evaluate_coherence(
        self,
        dialogue_history: List[Dict],
        current_response: str,
        learning_objective: str
    ) -> CoherenceMetrics:
        """Evaluate multi-turn effectiveness/coherence with full reasoning"""
        
        if not self.should_evaluate():
            return CoherenceMetrics(
                context_maintenance=0.7,
                progress_tracking=0.7,
                logical_flow=0.7,
                explanation="Skipped - sampling"
            )
        
        try:
            # Create evaluation prompt
            dialogue_text = self._format_dialogue_history(dialogue_history[-5:])  # Last 5 turns
            
            prompt = f"""Evaluate the coherence of this tutoring conversation.

LEARNING OBJECTIVE: {learning_objective}

CONVERSATION HISTORY:
{dialogue_text}

CURRENT RESPONSE:
{current_response}

Evaluate and provide JSON response with these exact fields:
{{
    "context_maintenance": 0.0-1.0,  // Does response build on prior exchanges?
    "progress_tracking": 0.0-1.0,    // Movement toward learning objective?
    "logical_flow": 0.0-1.0,          // Consistency and coherence?
    "references_prior_turns": true/false,
    "shows_progression": true/false,
    "maintains_teaching_style": true/false,
    "addresses_student_needs": true/false,
    "strengths": ["List specific strengths you observed in the response"],
    "issues": ["List specific issues or problems you identified"],
    "explanation": "Provide 2-3 sentences explaining your scoring decision, referencing specific evidence from the dialogue"
}}"""

            response = await self.llm_client.chat.completions.create(
                model="gpt-4o-mini",  # Use mini for cost efficiency
                messages=[
                    {"role": "system", "content": "You are an expert tutor evaluator. Provide only valid JSON with detailed reasoning."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            evaluation = json.loads(response.choices[0].message.content)
            
            metrics = CoherenceMetrics(
                context_maintenance=float(evaluation.get('context_maintenance', 0.5)),
                progress_tracking=float(evaluation.get('progress_tracking', 0.5)),
                logical_flow=float(evaluation.get('logical_flow', 0.5)),
                references_prior_turns=bool(evaluation.get('references_prior_turns', False)),
                shows_progression=bool(evaluation.get('shows_progression', False)),
                maintains_teaching_style=bool(evaluation.get('maintains_teaching_style', True)),
                addresses_student_needs=bool(evaluation.get('addresses_student_needs', False)),
                strengths=evaluation.get('strengths', []),
                issues=evaluation.get('issues', []),
                explanation=evaluation.get('explanation', "")
            )
            
            # Log the evaluation
            self.metrics_log.append({
                'type': 'coherence',
                'score': metrics.get_overall_score(),
                'timestamp': datetime.now().isoformat(),
                'reasoning': metrics.explanation
            })
            
            return metrics
            
        except Exception as e:
            print(f"⚠️ Coherence evaluation error: {e}")
            return CoherenceMetrics(
                context_maintenance=0.5,
                progress_tracking=0.5,
                logical_flow=0.5,
                explanation=f"Evaluation failed: {str(e)}"
            )
    
    async def evaluate_adaptive_feedback(
        self,
        learner_state: Dict,
        tutor_response: str,
        scaffolding_level: str,
        performance_history: List[float]
    ) -> AdaptiveFeedbackMetrics:
        """Evaluate adaptive feedback appropriateness with full reasoning"""
        
        if not self.should_evaluate():
            return AdaptiveFeedbackMetrics(
                learner_state_match=0.7,
                timing_appropriateness=0.7,
                pedagogical_quality=0.7,
                explanation="Skipped - sampling"
            )
        
        try:
            # Format performance history
            perf_text = "Recent performance: "
            if performance_history:
                recent_perf = performance_history[-5:]
                perf_text += ", ".join([f"Turn {i+1}: {'✓' if score > 0.5 else '✗'}" 
                                       for i, score in enumerate(recent_perf)])
            else:
                perf_text += "No data"
            
            prompt = f"""Evaluate the adaptive feedback appropriateness.

LEARNER STATE:
- Knowledge Level: {learner_state.get('knowledge_state', '?')}/5
- Current Mastery: {learner_state.get('current_mastery', 0.5)*100:.0f}%
- Motivation: {learner_state.get('motivation', 0.5)*100:.0f}%
- Current Scaffolding: {scaffolding_level}

PERFORMANCE HISTORY:
{perf_text}

TUTOR RESPONSE:
{tutor_response}

Evaluate and provide JSON response with these exact fields:
{{
    "learner_state_match": 0.0-1.0,     // Appropriate for learner's level?
    "timing_appropriateness": 0.0-1.0,  // Well-timed support?
    "pedagogical_quality": 0.0-1.0,     // Teaching quality?
    "scaffolding_level_appropriate": true/false,
    "motivational_elements_present": true/false,
    "provides_hints": true/false,
    "acknowledges_progress": true/false,
    "strengths": ["List specific pedagogical strengths in the response"],
    "issues": ["List specific issues with adaptation or scaffolding"],
    "explanation": "Provide 2-3 sentences explaining why this response is/isn't appropriate for this learner's state, referencing specific evidence"
}}"""

            response = await self.llm_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an expert tutor evaluator. Provide only valid JSON with detailed pedagogical reasoning."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            evaluation = json.loads(response.choices[0].message.content)
            
            metrics = AdaptiveFeedbackMetrics(
                learner_state_match=float(evaluation.get('learner_state_match', 0.5)),
                timing_appropriateness=float(evaluation.get('timing_appropriateness', 0.5)),
                pedagogical_quality=float(evaluation.get('pedagogical_quality', 0.5)),
                scaffolding_level_appropriate=bool(evaluation.get('scaffolding_level_appropriate', False)),
                motivational_elements_present=bool(evaluation.get('motivational_elements_present', False)),
                provides_hints=bool(evaluation.get('provides_hints', False)),
                acknowledges_progress=bool(evaluation.get('acknowledges_progress', False)),
                strengths=evaluation.get('strengths', []),
                issues=evaluation.get('issues', []),
                explanation=evaluation.get('explanation', "")
            )
            
            # Log the evaluation
            self.metrics_log.append({
                'type': 'adaptive',
                'score': metrics.get_overall_score(),
                'timestamp': datetime.now().isoformat(),
                'reasoning': metrics.explanation
            })
            
            return metrics
            
        except Exception as e:
            print(f"⚠️ Adaptive feedback evaluation error: {e}")
            return AdaptiveFeedbackMetrics(
                learner_state_match=0.5,
                timing_appropriateness=0.5,
                pedagogical_quality=0.5,
                explanation=f"Evaluation failed: {str(e)}"
            )
    
    def _format_dialogue_history(self, dialogue: List[Dict]) -> str:
        """Format dialogue history for evaluation"""
        formatted = []
        for turn in dialogue:
            if 'role' in turn and 'content' in turn:
                formatted.append(f"{turn['role'].capitalize()}: {turn['content']}")
        return "\n".join(formatted)
    
    def get_evaluation_summary(self) -> Dict:
        """Get summary of all evaluations performed"""
        if not self.metrics_log:
            return {}
        
        coherence_scores = [m['score'] for m in self.metrics_log if m['type'] == 'coherence']
        adaptive_scores = [m['score'] for m in self.metrics_log if m['type'] == 'adaptive']
        
        return {
            'total_evaluations': len(self.metrics_log),
            'coherence_evaluations': len(coherence_scores),
            'adaptive_evaluations': len(adaptive_scores),
            'avg_coherence_score': np.mean(coherence_scores) if coherence_scores else 0,
            'avg_adaptive_score': np.mean(adaptive_scores) if adaptive_scores else 0
        }

# ============================================================================
# LEARNER PROFILES (Keep all 6)
# ============================================================================

@dataclass
class EnhancedLearnerProfile:
    """Enhanced learner profile for tutor mode interactions"""
    name: str
    knowledge_state: int
    cl_tolerance: str
    motivation: float
    engagement_style: str
    learning_rate: float
    
    # Tutor-specific behaviors
    verbosity: str = "moderate"
    question_asking_tendency: float = field(default=0.3)
    confusion_expression: float = field(default=0.4)
    concept_grasp_rate: float = field(default=0.6)
    
    # Conversation patterns
    personality_traits: List[str] = field(default_factory=list)
    common_mistakes: List[str] = field(default_factory=list)
    communication_style: str = "standard"
    background_context: str = ""
    
    def generate_tutor_persona_prompt(self, current_mastery: float, scaffolding_level: str) -> str:
        """Generate persona prompt for tutor interactions"""
        
        knowledge_descriptions = {
            1: "a complete beginner struggling with basic concepts",
            2: "learning the basics but making frequent errors",
            3: "at intermediate level with some understanding",
            4: "fairly competent with occasional confusion",
            5: "advanced with strong understanding"
        }
        
        engagement_descriptions = {
            "eager": "You respond quickly and enthusiastically.",
            "reflective": "You think carefully before responding.",
            "variable": "Your engagement varies.",
            "adaptive": "You adjust based on difficulty."
        }
        
        return f"""You are {self.name}, a student in CMP511 Machine Learning.

PROFILE:
- Knowledge: {knowledge_descriptions.get(self.knowledge_state, 'intermediate')}
- Mastery: {current_mastery*100:.0f}%
- Style: {engagement_descriptions.get(self.engagement_style, 'normal')}
- Motivation: {self.motivation*100:.0f}%

TRAITS: {', '.join(self.personality_traits)}
COMMON ERRORS: {', '.join(self.common_mistakes)}

Respond as this student would."""

# ============================================================================
# RESPONSE SIMULATOR (Keep existing)
# ============================================================================

class TutorResponseSimulator:
    """Simulates student responses in tutoring conversations"""
    
    def __init__(self, llm_client: AsyncOpenAI = None):
        self.llm_client = llm_client
        
    async def generate_student_response(
        self,
        learner_profile: EnhancedLearnerProfile,
        tutor_message: str,
        current_go: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        current_mastery: float,
        scaffolding_level: str = "medium"
    ) -> str:
        """Generate a contextual student response to tutor message"""
        
        if not isinstance(current_go, dict):
            current_go = {'skill_name': str(current_go) if current_go else 'the concept'}
        if 'skill_name' not in current_go:
            current_go['skill_name'] = 'the concept'
        
        response_quality = self._calculate_response_quality(
            learner_profile, current_mastery, scaffolding_level
        )
        
        return self._generate_deterministic_response(
            learner_profile, tutor_message, current_go,
            response_quality, scaffolding_level
        )
    
    def _calculate_response_quality(self, learner_profile, current_mastery, scaffolding_level):
        """Calculate expected response quality"""
        
        base_quality = (learner_profile.knowledge_state / 5) * 0.4 + current_mastery * 0.6
        
        scaffolding_bonus = {
            "high": 0.15,
            "medium": 0.05,
            "low": -0.05
        }.get(scaffolding_level, 0)
        
        motivation_bonus = learner_profile.motivation * 0.1
        grasp_rate_bonus = learner_profile.concept_grasp_rate * 0.1
        
        quality = base_quality + scaffolding_bonus + motivation_bonus + grasp_rate_bonus
        
        return np.clip(quality, 0.1, 0.95)
    
    def _generate_deterministic_response(
        self, learner_profile, tutor_message, current_go, 
        response_quality, scaffolding_level
    ):
        """Generate deterministic response based on profile and context"""
        
        skill_name = current_go.get('skill_name', 'the concept')
        
        if np.random.random() < learner_profile.question_asking_tendency:
            questions = {
                1: [f"I don't understand {skill_name}. Can you explain differently?"],
                2: [f"So {skill_name} is like... Can you give an example?"],
                3: [f"Is {skill_name} similar to what we learned before?"],
                4: [f"I understand {skill_name} conceptually, but what about edge cases?"],
                5: [f"Regarding {skill_name}, what about optimization?"]
            }
            level_questions = questions.get(learner_profile.knowledge_state, questions[3])
            return np.random.choice(level_questions)
        
        if response_quality < 0.5 and np.random.random() < learner_profile.confusion_expression:
            confusion_responses = {
                "high": f"I'm struggling with {skill_name}. Not getting it.",
                "medium": f"Still confused about {skill_name}.",
                "low": f"I need to review {skill_name} more."
            }
            return confusion_responses.get(scaffolding_level, confusion_responses["medium"])
        
        if response_quality > 0.7:
            responses = [
                f"I think {skill_name} works by finding patterns and making predictions.",
                f"So {skill_name} helps optimize by adjusting parameters.",
                f"Yes, I see how {skill_name} connects to what we learned.",
                f"That makes sense! {skill_name} is about learning from examples."
            ]
        elif response_quality > 0.4:
            responses = [
                f"I think {skill_name} has to do with patterns, but unsure about details.",
                f"So {skill_name} is for predictions? Or classification?",
                f"I understand parts of {skill_name}, but how about complex cases?",
                f"Is {skill_name} always the best approach?"
            ]
        else:
            responses = [
                f"I'm trying to understand {skill_name}, but it's not clicking.",
                f"Can we go over {skill_name} again?",
                f"I know {skill_name} is important, but I'm missing something.",
                f"What's the simplest way to think about {skill_name}?"
            ]
        
        response = np.random.choice(responses)
        
        if learner_profile.verbosity == "brief":
            response = response.split('.')[0] + "."
        elif learner_profile.verbosity == "verbose":
            response += f" When you mentioned {skill_name}, it made me think about applications."
        
        return response
    
    def generate_go_transition_message(
        self, 
        learner_profile: EnhancedLearnerProfile,
        next_go: Dict[str, Any],
        mastered_previous: bool
    ) -> str:
        """Generate student message when transitioning to next GO"""
        
        if mastered_previous:
            if learner_profile.knowledge_state >= 4:
                return f"Great! Now let's move on to {next_go['skill_name']}."
            else:
                return f"I think I get it. Can we try {next_go['skill_name']} next?"
        else:
            if learner_profile.knowledge_state >= 3:
                return f"This is challenging. Maybe we should try {next_go['skill_name']} and come back?"
            else:
                return f"I'm still confused, but can we look at {next_go['skill_name']}?"

# ============================================================================
# MAIN NATURAL PROGRESSION SIMULATION (ENHANCED WITH REASONING)
# ============================================================================

class EnhancedNaturalProgressionTutorSimulation:
    """Enhanced natural progression tutor simulation with complete reasoning capture"""
    
    def __init__(self, openai_api_key: str = None, 
                 enable_judge: bool = True, 
                 judge_sample_rate: float = 0.2,
                 resume_from_checkpoint: bool = True):
        self._configure_logging()
        
        print("Initializing Enhanced LEA connector...")
        self.lea_connector = RealLEASystemConnector(openai_api_key)
        
        self.llm_client = AsyncOpenAI(api_key=openai_api_key) if openai_api_key else None
        self.response_simulator = TutorResponseSimulator(self.llm_client)
        
        # Enhanced judge evaluator with sampling
        self.judge_evaluator = EnhancedTutorLLMJudgeEvaluator(
            self.llm_client, 
            enable_judge=enable_judge,
            sample_rate=judge_sample_rate
        ) if self.llm_client else None
        
        self.learner_profiles = self._create_learner_profiles()
        
        # Initialize checkpoint manager
        self.checkpoint_manager = CheckpointManager()
        
        # Check for existing checkpoint
        if resume_from_checkpoint:
            checkpoint = self.checkpoint_manager.load_latest_checkpoint()
            if checkpoint:
                print(f"\n🔄 Resuming from checkpoint: {checkpoint['checkpoint_info']['last_completed_learner_name']}")
                self.detailed_logs = checkpoint['data']['detailed_logs']
                self.session_summaries = checkpoint['data']['session_summaries']
                self.go_complexity_data = checkpoint['data']['go_complexity_data']
                self.start_from_learner = checkpoint['checkpoint_info']['last_completed_learner_idx'] + 1
            else:
                self._initialize_empty_data()
                self.start_from_learner = 0
        else:
            self._initialize_empty_data()
            self.start_from_learner = 0
        
        # Universal configuration
        self.MASTERY_INCREMENT = 0.15
        self.STARTING_MASTERY = 0.25
        self.GOS_TO_COMPLETE = 3
    
    def _initialize_empty_data(self):
        """Initialize empty data containers"""
        self.detailed_logs = []
        self.session_summaries = []
        self.go_complexity_data = []
    
    def _configure_logging(self):
        """Configure logging to suppress debug messages"""
        loggers_to_suppress = [
            'src', 'src.core', 'src.mcp', 'src.quiz', 'src.tutor',
            'src.storage', 'redis', 'openai', 'httpx', 'httpcore'
        ]
        
        for logger_name in loggers_to_suppress:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.WARNING)
    
    def _create_learner_profiles(self) -> List[EnhancedLearnerProfile]:
        """Create all 6 learner profiles"""
        
        return [
            EnhancedLearnerProfile(
                name="Advanced_Eager",
                knowledge_state=5,
                cl_tolerance="high",
                motivation=0.9,
                engagement_style="eager",
                learning_rate=0.85,
                verbosity="moderate",
                question_asking_tendency=0.2,
                confusion_expression=0.1,
                concept_grasp_rate=0.9,
                personality_traits=["confident", "quick-thinking"],
                common_mistakes=["overthinking", "edge cases"],
                communication_style="Direct and technical",
                background_context="Strong STEM background"
            ),
            EnhancedLearnerProfile(
                name="Moderate_Reflective",
                knowledge_state=3,
                cl_tolerance="medium",
                motivation=0.7,
                engagement_style="reflective",
                learning_rate=0.70,
                verbosity="verbose",
                question_asking_tendency=0.5,
                confusion_expression=0.4,
                concept_grasp_rate=0.6,
                personality_traits=["thoughtful", "methodical"],
                common_mistakes=["concept confusion"],
                communication_style="Detailed and questioning",
                background_context="Some programming experience"
            ),
            EnhancedLearnerProfile(
                name="Struggling_Eager",
                knowledge_state=2,
                cl_tolerance="low",
                motivation=0.8,
                engagement_style="eager",
                learning_rate=0.60,
                verbosity="brief",
                question_asking_tendency=0.7,
                confusion_expression=0.8,
                concept_grasp_rate=0.4,
                personality_traits=["enthusiastic", "persistent"],
                common_mistakes=["fundamentals"],
                communication_style="Enthusiastic but uncertain",
                background_context="New to programming"
            ),
            EnhancedLearnerProfile(
                name="Capable_Disengaged",
                knowledge_state=4,
                cl_tolerance="high",
                motivation=0.4,
                engagement_style="reflective",
                learning_rate=0.75,
                verbosity="brief",
                question_asking_tendency=0.1,
                confusion_expression=0.2,
                concept_grasp_rate=0.75,
                personality_traits=["intelligent", "unmotivated"],
                common_mistakes=["careless errors"],
                communication_style="Terse and minimal",
                background_context="Has ability but lacks interest"
            ),
            EnhancedLearnerProfile(
                name="Novice_Variable",
                knowledge_state=1,
                cl_tolerance="medium",
                motivation=0.6,
                engagement_style="variable",
                learning_rate=0.55,
                verbosity="variable",
                question_asking_tendency=0.6,
                confusion_expression=0.7,
                concept_grasp_rate=0.3,
                personality_traits=["curious", "inconsistent"],
                common_mistakes=["prerequisites"],
                communication_style="Varies",
                background_context="Complete beginner"
            ),
            EnhancedLearnerProfile(
                name="Inconsistent_Adaptive",
                knowledge_state=3,
                cl_tolerance="variable",
                motivation=0.65,
                engagement_style="adaptive",
                learning_rate=0.65,
                verbosity="moderate",
                question_asking_tendency=0.4,
                confusion_expression=0.5,
                concept_grasp_rate=0.55,
                personality_traits=["unpredictable"],
                common_mistakes=["knowledge gaps"],
                communication_style="Adapts",
                background_context="Uneven preparation"
            )
        ]
    
    def _get_week_target_gos(self, week: int) -> List[Dict[str, Any]]:
        """Get the first 3 GOs for a given week"""
        
        gos = []
        
        try:
            week_content = self.lea_connector.kc_loader.get_week_content("CMP511", week)
            if week_content:
                for lo in week_content.learning_objectives[:3]:
                    if hasattr(lo, 'granular_objectives'):
                        for go in lo.granular_objectives[:2]:
                            if len(gos) >= 3:
                                break
                            
                            gos.append({
                                'go_id': go.go_id,
                                'skill_name': go.skill_name,
                                'mastery_threshold': go.mastery_threshold,
                                'estimated_time_minutes': go.estimated_time_minutes,
                                'complexity': go.complexity,
                                'cognitive_level': go.cognitive_level,
                                'description': go.description
                            })
                    
        except Exception as e:
            print(f"⚠️ Could not load week {week} GOs: {e}")
        
        # Fallback to mock GOs if KC model fails
        if not gos:
            week_skills = {
                1: ["Identify Types of AI", "Understand AI-ML Relationship", "Classify ML Types"],
                3: ["Understand Linear Regression Theory", "Interpret Linear Regression Coefficients", "Evaluate Linear Regression Model"],
                5: ["Understand Decision Trees", "Apply Splitting Criteria", "Prune Decision Trees"],
                7: ["Understand Neural Networks", "Apply Backpropagation", "Optimize Network Architecture"],
                9: ["Understand Clustering", "Apply K-Means", "Evaluate Cluster Quality"]
            }
            
            skills = week_skills.get(week, [f"Week {week} Concept {i+1}" for i in range(3)])
            thresholds = [0.71, 0.66, 0.81] if week == 3 else [0.65, 0.70, 0.75]
            
            for i, skill in enumerate(skills[:3]):
                gos.append({
                    'go_id': f"GO_{week:02d}_{14+i:02d}_{i+1:03d}",
                    'skill_name': skill,
                    'mastery_threshold': thresholds[i] if i < len(thresholds) else 0.65,
                    'estimated_time_minutes': 15,
                    'complexity': 'basic' if i == 0 else 'intermediate',
                    'cognitive_level': ['Remember', 'Understand', 'Apply'][i] if i < 3 else 'Understand',
                    'description': f"Students will learn {skill.lower()}"
                })
        
        return gos[:3]
    
    async def _run_natural_session(
        self,
        learner_profile: EnhancedLearnerProfile,
        week: int,
        iteration: int,
        target_gos: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Run a natural progression session with complete reasoning capture"""
        
        # Pass learner profile to connector
        self.lea_connector.current_learner_profile = learner_profile
        self.lea_connector.tutor_session = None
        
        # Initialize session metrics
        session_metrics = {
            'total_turns': 0,
            'go_completions': [],
            'conversation_history': [],
            'performance_history': [],
            'coherence_scores': [],
            'coherence_submetrics': [],
            'adaptive_scores': [],
            'adaptive_submetrics': [],
            'scaffolding_changes': 0,
            'student_correct_responses': 0,
            'student_total_responses': 0
        }
        
        # Fresh mastery for each session
        current_mastery = {go['go_id']: self.STARTING_MASTERY for go in target_gos}
        
        conversation_history = []
        performance_history = []
        
        completed_gos = 0
        current_go_idx = 0
        turns_on_current_go = 0
        previous_scaffolding = "medium"
        
        # Initial message
        current_go = target_gos[0]
        student_message = f"Can you help me understand {current_go['skill_name']}?"
        
        # Continue until 3 GOs are completed
        while completed_gos < self.GOS_TO_COMPLETE:
            turn_start_time = time.time()
            
            # Process tutor interaction
            tutor_result = await self.lea_connector.process_tutor_interaction(
                student_message,
                username=f"{learner_profile.name}_iter{iteration}",
                week=week
            )
            
            turn_duration = (time.time() - turn_start_time) * 1000
            
            # Extract evaluation score and correctness
            evaluation_score = self._extract_evaluation_score(tutor_result)
            is_correct = self._determine_correctness(tutor_result, evaluation_score)
            performance_history.append(1.0 if is_correct else 0.0)
            
            session_metrics['student_total_responses'] += 1
            if is_correct:
                session_metrics['student_correct_responses'] += 1
            
            # Update mastery
            if is_correct and current_go['go_id'] in current_mastery:
                old_mastery = current_mastery[current_go['go_id']]
                current_mastery[current_go['go_id']] = min(
                    1.0, 
                    current_mastery[current_go['go_id']] + self.MASTERY_INCREMENT
                )
            
            # Update conversation history
            conversation_history.append({
                'turn': session_metrics['total_turns'],
                'role': 'student',
                'content': student_message
            })
            conversation_history.append({
                'turn': session_metrics['total_turns'],
                'role': 'tutor',
                'content': tutor_result.get('tutor_response', '')
            })
            
            # LLM Judge evaluation for metrics with full reasoning
            coherence_metrics = None
            adaptive_metrics = None
            
            if self.judge_evaluator and tutor_result.get('tutor_response'):
                # Evaluate Multi-Turn Effectiveness (Coherence)
                coherence_metrics = await self.judge_evaluator.evaluate_coherence(
                    dialogue_history=conversation_history,
                    current_response=tutor_result['tutor_response'],
                    learning_objective=current_go['skill_name']
                )
                
                session_metrics['coherence_scores'].append(coherence_metrics.get_overall_score())
                session_metrics['coherence_submetrics'].append({
                    'context_maintenance': coherence_metrics.context_maintenance,
                    'progress_tracking': coherence_metrics.progress_tracking,
                    'logical_flow': coherence_metrics.logical_flow,
                    'references_prior_turns': coherence_metrics.references_prior_turns,
                    'shows_progression': coherence_metrics.shows_progression,
                    'maintains_teaching_style': coherence_metrics.maintains_teaching_style,
                    'addresses_student_needs': coherence_metrics.addresses_student_needs
                })
                
                # Evaluate Adaptive Feedback Appropriateness
                learner_state = {
                    'knowledge_state': learner_profile.knowledge_state,
                    'current_mastery': current_mastery.get(current_go['go_id'], self.STARTING_MASTERY),
                    'motivation': learner_profile.motivation
                }
                
                adaptive_metrics = await self.judge_evaluator.evaluate_adaptive_feedback(
                    learner_state=learner_state,
                    tutor_response=tutor_result['tutor_response'],
                    scaffolding_level=tutor_result.get('scaffolding_level', 'medium'),
                    performance_history=performance_history
                )
                
                session_metrics['adaptive_scores'].append(adaptive_metrics.get_overall_score())
                session_metrics['adaptive_submetrics'].append({
                    'learner_state_match': adaptive_metrics.learner_state_match,
                    'timing_appropriateness': adaptive_metrics.timing_appropriateness,
                    'pedagogical_quality': adaptive_metrics.pedagogical_quality,
                    'scaffolding_level_appropriate': adaptive_metrics.scaffolding_level_appropriate,
                    'motivational_elements_present': adaptive_metrics.motivational_elements_present,
                    'provides_hints': adaptive_metrics.provides_hints,
                    'acknowledges_progress': adaptive_metrics.acknowledges_progress
                })
            
            # Track scaffolding changes
            current_scaffolding = tutor_result.get('scaffolding_level', 'medium')
            if current_scaffolding != previous_scaffolding:
                session_metrics['scaffolding_changes'] += 1
                previous_scaffolding = current_scaffolding
            
            # Log detailed interaction with complete reasoning
            self._log_interaction_enhanced(
                learner_profile, iteration, week,
                session_metrics['total_turns'], student_message,
                tutor_result, current_go, current_mastery,
                turn_duration, evaluation_score, is_correct,
                coherence_metrics,
                adaptive_metrics
            )
            
            session_metrics['total_turns'] += 1
            turns_on_current_go += 1
            
            # Check if current GO is mastered
            if current_mastery[current_go['go_id']] >= current_go['mastery_threshold']:
                # GO completed!
                session_metrics['go_completions'].append({
                    'go_id': current_go['go_id'],
                    'skill_name': current_go['skill_name'],
                    'turns_to_complete': turns_on_current_go,
                    'threshold': current_go['mastery_threshold'],
                    'final_mastery': current_mastery[current_go['go_id']]
                })
                
                completed_gos += 1
                print(f"    ✅ Completed GO: {current_go['skill_name']} in {turns_on_current_go} turns")
                
                # Move to next GO if available
                if completed_gos < self.GOS_TO_COMPLETE:
                    current_go_idx = (current_go_idx + 1) % len(target_gos)
                    current_go = target_gos[current_go_idx]
                    turns_on_current_go = 0
                    
                    # Update tutor session if it exists
                    if self.lea_connector.tutor_session:
                        self.lea_connector.tutor_session.current_go_index = current_go_idx
                    
                    # Generate transition message
                    student_message = self.response_simulator.generate_go_transition_message(
                        learner_profile, current_go, True
                    )
                else:
                    # All GOs completed
                    break
            else:
                # Continue with current GO
                go_dict = {'skill_name': current_go['skill_name'], 'go_id': current_go['go_id']}
                student_message = await self.response_simulator.generate_student_response(
                    learner_profile,
                    tutor_result.get('tutor_response', ''),
                    go_dict,
                    conversation_history,
                    current_mastery[current_go['go_id']],
                    current_scaffolding
                )
        
        session_metrics['conversation_history'] = conversation_history
        session_metrics['performance_history'] = performance_history
        
        return session_metrics
    
    def _log_interaction_enhanced(
        self,
        learner_profile: EnhancedLearnerProfile,
        iteration: int,
        week: int,
        turn: int,
        student_message: str,
        tutor_result: Dict[str, Any],
        current_go: Dict[str, Any],
        current_mastery: Dict[str, float],
        processing_time: float,
        evaluation_score: float,
        is_correct: bool,
        coherence_metrics: Optional[CoherenceMetrics],
        adaptive_metrics: Optional[AdaptiveFeedbackMetrics]
    ):
        """Log detailed interaction data with complete reasoning capture"""
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "learner_name": learner_profile.name,
            "learner_knowledge_state": learner_profile.knowledge_state,
            "learner_motivation": learner_profile.motivation,
            "learner_engagement_style": learner_profile.engagement_style,
            "iteration": iteration,
            "week": week,
            "turn": turn,
            
            "student_message": student_message,
            "tutor_response": tutor_result.get('tutor_response', ''),
            
            "go_id": current_go['go_id'],
            "skill_name": current_go['skill_name'],
            "mastery_threshold": current_go['mastery_threshold'],
            "current_mastery": current_mastery.get(current_go['go_id'], self.STARTING_MASTERY),
            
            "is_correct": is_correct,
            "evaluation_score": evaluation_score,
            "scaffolding_level": tutor_result.get('scaffolding_level', 'medium'),
            "processing_time_ms": processing_time
        }
        
        # Add complete coherence metrics and reasoning if available
        if coherence_metrics:
            log_entry.update({
                "coherence_score": coherence_metrics.get_overall_score(),
                "coherence_context_maintenance": coherence_metrics.context_maintenance,
                "coherence_progress_tracking": coherence_metrics.progress_tracking,
                "coherence_logical_flow": coherence_metrics.logical_flow,
                "coherence_references_prior": coherence_metrics.references_prior_turns,
                "coherence_shows_progression": coherence_metrics.shows_progression,
                "coherence_maintains_style": coherence_metrics.maintains_teaching_style,
                "coherence_addresses_needs": coherence_metrics.addresses_student_needs,
                # REASONING FIELDS
                "coherence_strengths": json.dumps(coherence_metrics.strengths),
                "coherence_issues": json.dumps(coherence_metrics.issues),
                "coherence_explanation": coherence_metrics.explanation
            })
        
        # Add complete adaptive metrics and reasoning if available
        if adaptive_metrics:
            log_entry.update({
                "adaptive_score": adaptive_metrics.get_overall_score(),
                "adaptive_learner_match": adaptive_metrics.learner_state_match,
                "adaptive_timing": adaptive_metrics.timing_appropriateness,
                "adaptive_pedagogical_quality": adaptive_metrics.pedagogical_quality,
                "adaptive_scaffolding_appropriate": adaptive_metrics.scaffolding_level_appropriate,
                "adaptive_has_motivation": adaptive_metrics.motivational_elements_present,
                "adaptive_provides_hints": adaptive_metrics.provides_hints,
                "adaptive_acknowledges_progress": adaptive_metrics.acknowledges_progress,
                # REASONING FIELDS
                "adaptive_strengths": json.dumps(adaptive_metrics.strengths),
                "adaptive_issues": json.dumps(adaptive_metrics.issues),
                "adaptive_explanation": adaptive_metrics.explanation
            })
        
        self.detailed_logs.append(log_entry)
    
    def _log_session_summary(
        self,
        learner_profile: EnhancedLearnerProfile,
        iteration: int,
        week: int,
        session_metrics: Dict[str, Any],
        session_duration: float
    ):
        """Log session-level summary with enhanced metrics"""
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "learner_name": learner_profile.name,
            "learner_knowledge_state": learner_profile.knowledge_state,
            "iteration": iteration,
            "week": week,
            "total_turns": session_metrics['total_turns'],
            "gos_completed": len(session_metrics['go_completions']),
            "student_accuracy": session_metrics['student_correct_responses'] / max(session_metrics['student_total_responses'], 1),
            "scaffolding_changes": session_metrics['scaffolding_changes'],
            "session_duration_seconds": session_duration,
            
            # Enhanced metrics
            "avg_coherence_score": np.mean(session_metrics['coherence_scores']) if session_metrics['coherence_scores'] else None,
            "avg_adaptive_score": np.mean(session_metrics['adaptive_scores']) if session_metrics['adaptive_scores'] else None,
            
            # Sub-metrics averages
            "avg_context_maintenance": np.mean([m['context_maintenance'] for m in session_metrics['coherence_submetrics']]) if session_metrics['coherence_submetrics'] else None,
            "avg_progress_tracking": np.mean([m['progress_tracking'] for m in session_metrics['coherence_submetrics']]) if session_metrics['coherence_submetrics'] else None,
            "avg_logical_flow": np.mean([m['logical_flow'] for m in session_metrics['coherence_submetrics']]) if session_metrics['coherence_submetrics'] else None,
            
            "avg_learner_match": np.mean([m['learner_state_match'] for m in session_metrics['adaptive_submetrics']]) if session_metrics['adaptive_submetrics'] else None,
            "avg_timing_appropriateness": np.mean([m['timing_appropriateness'] for m in session_metrics['adaptive_submetrics']]) if session_metrics['adaptive_submetrics'] else None,
            "avg_pedagogical_quality": np.mean([m['pedagogical_quality'] for m in session_metrics['adaptive_submetrics']]) if session_metrics['adaptive_submetrics'] else None
        }
        
        # Add GO completion details
        for i, go_completion in enumerate(session_metrics['go_completions']):
            summary[f"go_{i+1}_id"] = go_completion['go_id']
            summary[f"go_{i+1}_turns"] = go_completion['turns_to_complete']
            summary[f"go_{i+1}_threshold"] = go_completion['threshold']
        
        self.session_summaries.append(summary)
    
    def _extract_evaluation_score(self, result: Dict[str, Any]) -> float:
        """Extract evaluation score from tutor result"""
        
        if isinstance(result.get("evaluation"), dict):
            return float(result["evaluation"].get("score", 0.5))
        
        if "evaluation_score" in result:
            return float(result["evaluation_score"])
        
        # Fallback: realistic distribution
        evaluation_score = np.random.beta(4, 3)
        return np.clip(evaluation_score, 0.1, 0.95)
    
    def _determine_correctness(self, result: Dict[str, Any], evaluation_score: float) -> bool:
        """Determine if student response was correct with realistic error rates"""
        
        if hasattr(self.lea_connector, 'current_learner_profile'):
            learner = self.lea_connector.current_learner_profile
            
            accuracy_rates = {
                1: 0.40,  # Novice: 40% correct
                2: 0.50,  # Struggling: 50% correct
                3: 0.60,  # Moderate: 60% correct
                4: 0.70,  # Capable: 70% correct
                5: 0.80   # Advanced: 80% correct
            }
            
            target_accuracy = accuracy_rates.get(learner.knowledge_state, 0.6)
            
            if evaluation_score > 0.7:
                target_accuracy = min(0.90, target_accuracy + 0.10)
            elif evaluation_score < 0.3:
                target_accuracy = max(0.20, target_accuracy - 0.10)
            
            return np.random.random() < target_accuracy
        
        if "is_correct" in result and result["is_correct"] is not None:
            return bool(result["is_correct"])
        
        return np.random.random() < (evaluation_score * 0.8 + 0.1)
    
    def analyze_go_complexity(self) -> pd.DataFrame:
        """Analyze how many turns each GO requires"""
        
        if not self.detailed_logs:
            return pd.DataFrame()
        
        df_logs = pd.DataFrame(self.detailed_logs)
        
        # Group by GO to analyze complexity
        go_complexity = df_logs.groupby('go_id').agg({
            'turn': 'count',
            'is_correct': 'mean',
            'skill_name': 'first',
            'mastery_threshold': 'first'
        }).rename(columns={'turn': 'total_turns', 'is_correct': 'accuracy'})
        
        # Add average coherence and adaptive scores if available
        if 'coherence_score' in df_logs.columns:
            go_complexity['avg_coherence'] = df_logs.groupby('go_id')['coherence_score'].mean()
        if 'adaptive_score' in df_logs.columns:
            go_complexity['avg_adaptive'] = df_logs.groupby('go_id')['adaptive_score'].mean()
        
        go_complexity = go_complexity.sort_values('total_turns', ascending=False)
        
        print("\n📊 GO Complexity Analysis (Natural Progression):")
        print("="*80)
        print(f"{'GO ID':<20} {'Skill':<35} {'Threshold':<10} {'Avg Turns':<10}")
        print("-"*80)
        
        for idx, row in go_complexity.head(10).iterrows():
            skill_display = row['skill_name'][:32] + "..." if len(row['skill_name']) > 35 else row['skill_name']
            print(f"{idx:<20} {skill_display:<35} {row['mastery_threshold']:<10.2f} {row['total_turns']/30:<10.1f}")
        
        self.go_complexity_data = go_complexity.to_dict('records')
        
        return go_complexity
    
    def _calculate_final_metrics(self) -> Dict[str, Any]:
        """Calculate comprehensive metrics with proper JSON serialization"""
        
        if not self.session_summaries:
            return {}
        
        df_sessions = pd.DataFrame(self.session_summaries)
        df_logs = pd.DataFrame(self.detailed_logs)
        
        # Overall metrics
        overall = {
            'total_sessions': int(len(self.session_summaries)),
            'total_interactions': int(len(self.detailed_logs)),
            'avg_turns_per_session': float(df_sessions['total_turns'].mean()),
            'std_turns_per_session': float(df_sessions['total_turns'].std()),
            'avg_student_accuracy': float(df_sessions['student_accuracy'].mean()),
            'avg_gos_completed': float(df_sessions['gos_completed'].mean())
        }
        
        # Add judge metrics if available
        if 'avg_coherence_score' in df_sessions.columns:
            coherence_vals = df_sessions['avg_coherence_score'].dropna()
            if len(coherence_vals) > 0:
                overall['avg_coherence_score'] = float(coherence_vals.mean())
                overall['std_coherence_score'] = float(coherence_vals.std())
        
        if 'avg_adaptive_score' in df_sessions.columns:
            adaptive_vals = df_sessions['avg_adaptive_score'].dropna()
            if len(adaptive_vals) > 0:
                overall['avg_adaptive_score'] = float(adaptive_vals.mean())
                overall['std_adaptive_score'] = float(adaptive_vals.std())
        
        # Learner metrics - properly flatten
        learner_metrics = {}
        for learner in df_sessions['learner_name'].unique():
            learner_data = df_sessions[df_sessions['learner_name'] == learner]
            learner_metrics[learner] = {
                'total_turns_mean': float(learner_data['total_turns'].mean()),
                'total_turns_std': float(learner_data['total_turns'].std()),
                'student_accuracy': float(learner_data['student_accuracy'].mean()),
                'scaffolding_changes': float(learner_data['scaffolding_changes'].mean()),
                'sessions': int(len(learner_data))
            }
            
            # Add judge metrics if available
            if 'avg_coherence_score' in learner_data.columns:
                coherence = learner_data['avg_coherence_score'].dropna()
                if len(coherence) > 0:
                    learner_metrics[learner]['coherence_score'] = float(coherence.mean())
            
            if 'avg_adaptive_score' in learner_data.columns:
                adaptive = learner_data['avg_adaptive_score'].dropna()
                if len(adaptive) > 0:
                    learner_metrics[learner]['adaptive_score'] = float(adaptive.mean())
        
        # Week metrics - properly flatten
        week_metrics = {}
        for week in df_sessions['week'].unique():
            week_data = df_sessions[df_sessions['week'] == week]
            week_metrics[str(week)] = {
                'total_turns_mean': float(week_data['total_turns'].mean()),
                'total_turns_std': float(week_data['total_turns'].std()),
                'student_accuracy': float(week_data['student_accuracy'].mean()),
                'gos_completed': float(week_data['gos_completed'].mean()),
                'sessions': int(len(week_data))
            }
        
        # GO analysis
        go_turns = []
        for _, session in df_sessions.iterrows():
            for i in range(1, 4):
                if f'go_{i}_id' in session:
                    go_turns.append({
                        'go_id': session[f'go_{i}_id'],
                        'turns': session[f'go_{i}_turns'],
                        'threshold': session[f'go_{i}_threshold'],
                        'learner': session['learner_name'],
                        'knowledge': session['learner_knowledge_state'],
                        'week': session['week']
                    })
        
        go_metrics = {}
        if go_turns:
            df_go_turns = pd.DataFrame(go_turns)
            for go_id in df_go_turns['go_id'].unique():
                go_data = df_go_turns[df_go_turns['go_id'] == go_id]['turns']
                go_metrics[go_id] = {
                    'mean': float(go_data.mean()),
                    'std': float(go_data.std()),
                    'min': float(go_data.min()),
                    'max': float(go_data.max())
                }
        
        # Judge evaluation summary if available
        judge_summary = {}
        if self.judge_evaluator:
            judge_summary = self.judge_evaluator.get_evaluation_summary()
        
        return {
            'overall': overall,
            'by_learner': learner_metrics,
            'by_week': week_metrics,
            'go_analysis': go_metrics,
            'judge_evaluation_summary': judge_summary
        }
    
    def _save_results(self):
        """Save all results to files including reasoning fields"""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("tutor_natural_results")
        output_dir.mkdir(exist_ok=True)
        
        # Save detailed logs with reasoning
        df_logs = pd.DataFrame(self.detailed_logs)
        df_logs.to_csv(output_dir / f"natural_detailed_logs_{timestamp}.csv", index=False)
        
        # Save session summaries
        df_sessions = pd.DataFrame(self.session_summaries)
        df_sessions.to_csv(output_dir / f"natural_session_summaries_{timestamp}.csv", index=False)
        
        # Save GO complexity analysis
        if self.go_complexity_data:
            df_go = pd.DataFrame(self.go_complexity_data)
            df_go.to_csv(output_dir / f"natural_go_complexity_{timestamp}.csv", index=False)
        
        # Save metrics (with proper JSON serialization)
        metrics = self._calculate_final_metrics()
        with open(output_dir / f"natural_overall_metrics_{timestamp}.json", 'w') as f:
            json.dump(metrics, f, indent=2, default=str)
        
        print(f"\n📁 Results saved to: {output_dir}/")
        print(f"   - natural_detailed_logs_{timestamp}.csv (includes reasoning)")
        print(f"   - natural_session_summaries_{timestamp}.csv")
        print(f"   - natural_go_complexity_{timestamp}.csv")
        print(f"   - natural_overall_metrics_{timestamp}.json")
        
        # Clear checkpoints after successful save
        self.checkpoint_manager.clear_checkpoints()
    
    async def run_natural_progression_simulation(
        self,
        iterations_per_learner: int = 5,
        weeks_to_test: List[int] = None
    ) -> Dict[str, Any]:
        """Run natural progression simulation with complete reasoning capture"""
        
        if weeks_to_test is None:
            weeks_to_test = [1, 3, 5, 7]
        
        # Calculate total work
        total_learners = len(self.learner_profiles)
        total_sessions = total_learners * iterations_per_learner * len(weeks_to_test)
        
        print(f"\n{'='*80}")
        print(f"🎓 ENHANCED NATURAL PROGRESSION TUTOR SIMULATION")
        print(f"   WITH COMPLETE LLM JUDGE REASONING CAPTURE")
        print(f"{'='*80}")
        print(f"Configuration:")
        print(f"  • Total learners: {total_learners}")
        print(f"  • Starting from learner: {self.start_from_learner + 1}")
        print(f"  • Iterations per learner: {iterations_per_learner}")
        print(f"  • Weeks to test: {weeks_to_test}")
        print(f"  • Total sessions: {total_sessions}")
        print(f"  • Judge evaluation: {'Enabled' if self.judge_evaluator else 'Disabled'}")
        if self.judge_evaluator:
            print(f"  • Judge sample rate: {self.judge_evaluator.sample_rate*100:.0f}%")
            print(f"  • Reasoning capture: ENABLED (strengths, issues, explanations)")
        print(f"  • Checkpointing: Enabled (after each learner)")
        print(f"{'='*80}\n")
        
        simulation_start_time = time.time()
        
        # Run simulation with checkpointing
        for learner_idx in range(self.start_from_learner, len(self.learner_profiles)):
            learner_profile = self.learner_profiles[learner_idx]
            learner_start_time = time.time()
            
            print(f"\n{'='*60}")
            print(f"👤 Starting Learner {learner_idx + 1}/{total_learners}: {learner_profile.name}")
            print(f"   Knowledge State: {learner_profile.knowledge_state}")
            print(f"   Motivation: {learner_profile.motivation:.1%}")
            print(f"{'='*60}")
            
            for iteration in range(1, iterations_per_learner + 1):
                for week in weeks_to_test:
                    session_start_time = time.time()
                    
                    print(f"\n  👤 Learner {learner_profile.name}, 📚 Week {week}, Iteration {iteration}")
                    
                    # Get target GOs for this week
                    target_gos = self._get_week_target_gos(week)
                    
                    # Run natural progression session
                    session_metrics = await self._run_natural_session(
                        learner_profile, week, iteration, target_gos
                    )
                    
                    session_duration = time.time() - session_start_time
                    
                    # Log session summary
                    self._log_session_summary(
                        learner_profile, iteration, week,
                        session_metrics, session_duration
                    )
                    
                    print(f"    ⏱️ Session completed in {session_duration:.1f}s")
            
            learner_duration = time.time() - learner_start_time
            print(f"\n✅ Learner {learner_profile.name} completed in {learner_duration/60:.1f} minutes")
            
            # Save checkpoint after each learner
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.checkpoint_manager.save_checkpoint(
                learner_idx,
                learner_profile.name,
                self.detailed_logs,
                self.session_summaries,
                self.go_complexity_data,
                timestamp
            )
        
        simulation_duration = time.time() - simulation_start_time
        
        print(f"\n{'='*80}")
        print(f"✅ SIMULATION COMPLETE")
        print(f"  • Total time: {simulation_duration/60:.1f} minutes")
        print(f"  • Sessions completed: {len(self.session_summaries)}")
        print(f"  • Average time per session: {simulation_duration/len(self.session_summaries):.2f} seconds")
        print(f"{'='*80}\n")
        
        # Calculate and save results
        self.analyze_go_complexity()
        final_metrics = self._calculate_final_metrics()
        self._save_results()
        
        # Print judge evaluation summary if available
        if self.judge_evaluator:
            summary = self.judge_evaluator.get_evaluation_summary()
            if summary:
                print(f"\n📊 Judge Evaluation Summary:")
                print(f"   Total evaluations: {summary.get('total_evaluations', 0)}")
                print(f"   Coherence evaluations: {summary.get('coherence_evaluations', 0)}")
                print(f"   Avg coherence score: {summary.get('avg_coherence_score', 0):.3f}")
                print(f"   Adaptive evaluations: {summary.get('adaptive_evaluations', 0)}")
                print(f"   Avg adaptive score: {summary.get('avg_adaptive_score', 0):.3f}")
                print(f"\n💭 Reasoning fields captured in logs:")
                print(f"   • coherence_strengths, coherence_issues, coherence_explanation")
                print(f"   • adaptive_strengths, adaptive_issues, adaptive_explanation")
        
        print(f"\n✅ Enhanced simulation complete with full reasoning capture!")
        print(f"   Total sessions: {len(self.session_summaries)}")
        print(f"   Total interactions: {len(self.detailed_logs)}")
        
        return {
            "metrics": final_metrics,
            "detailed_logs": self.detailed_logs,
            "session_summaries": self.session_summaries,
            "go_complexity": self.go_complexity_data
        }

# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def main():
    """Main execution for enhanced natural progression simulation with reasoning"""
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️  Warning: No OpenAI API key found.")
        print("   LLM Judge evaluation will be disabled.")
        enable_judge = False
    else:
        print("\n✅ OpenAI API key found")
        
        # Ask about judge evaluation
        response = input("Enable LLM Judge evaluation with reasoning capture? (y/n, default=y): ").strip().lower()
        enable_judge = response != 'n'
        
        if enable_judge:
            sample_rate = input("Judge sample rate (0.1-1.0, default=1.0 for full reasoning): ").strip()
            try:
                sample_rate = float(sample_rate) if sample_rate else 1.0
                sample_rate = max(0.1, min(1.0, sample_rate))
            except:
                sample_rate = 1.0
            print(f"\n📝 Reasoning capture enabled - will log strengths, issues, and explanations")
        else:
            sample_rate = 0
    
    # Initialize enhanced simulation
    tutor_sim = EnhancedNaturalProgressionTutorSimulation(
        api_key,
        enable_judge=enable_judge,
        judge_sample_rate=sample_rate if enable_judge else 0,
        resume_from_checkpoint=True
    )
    
    # Validate LEA integration
    validation = tutor_sim.lea_connector.validate_integration()
    print("\n🔧 LEA Integration Status:")
    for component, status in validation.items():
        print(f"   {'✅' if status else '❌'} {component}")
    
    # Ask which week to test
    print("\n📅 Select week to test:")
    print("   1 - Week 1: Introduction")
    print("   2 - Week 2: Classification")
    print("   3 - Week 3: Linear Regression")
    print("   4 - Week 4: Logistic Regression")
    print("   5 - Week 5: Support Vector Machines")
    print("   6 - Week 6: Dimensionality Reduction")
    print("   7 - Week 7: ANNs")
    print("   8 - Week 8: Neural Networks")
    print("   9 - Week 9: Deep Learning - CNNs")
    print("   10 -Week 10:Deep Learning - RNNs")
    print("   11 -Week 11:Modern Architectures")
    print("   0 - All weeks")
    
    week_choice = input("Enter week number (default=1): ").strip()
    
    if week_choice == '0':
        weeks_to_test = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    else:
        try:
            week = int(week_choice) if week_choice else 4
            weeks_to_test = [week]
        except:
            weeks_to_test = [4]
    
    # Run natural progression simulation
    results = await tutor_sim.run_natural_progression_simulation(
        iterations_per_learner=5,
        weeks_to_test=weeks_to_test
    )
    
    print(f"\n📊 SIMULATION SUMMARY:")
    print(f"   Total sessions: {results['metrics']['overall']['total_sessions']}")
    print(f"   Avg turns per session: {results['metrics']['overall']['avg_turns_per_session']:.1f}")
    print(f"   Std dev of turns: {results['metrics']['overall']['std_turns_per_session']:.1f}")
    print(f"   Student accuracy: {results['metrics']['overall']['avg_student_accuracy']:.2%}")
    
    if 'avg_coherence_score' in results['metrics']['overall']:
        print(f"   Avg coherence score: {results['metrics']['overall']['avg_coherence_score']:.3f}")
    if 'avg_adaptive_score' in results['metrics']['overall']:
        print(f"   Avg adaptive score: {results['metrics']['overall']['avg_adaptive_score']:.3f}")
    
    print(f"\n📝 Reasoning data has been captured in detailed_logs CSV file")
    print(f"   Look for columns: coherence_explanation, adaptive_explanation, etc.")
    
    return results

if __name__ == "__main__":
    asyncio.run(main())
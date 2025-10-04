# File: src/core/enhanced_metrics_integration.py
"""
Enhanced LEA Metrics Integration System
Integrates metrics collection with session management, orchestrator data, and simulation framework
"""

import asyncio
import json
import time
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path
import numpy as np
from dataclasses import dataclass, asdict

# Import your existing metrics collector
from src.core.metrics_collector import MetricsCollector, collect_session_metrics

@dataclass
class SessionData:
    """Enhanced session data structure for metrics collection"""
    session_id: str
    username: str
    course_code: str
    week: int
    session_type: str  # 'quiz', 'tutor', 'chat'
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: float = 0.0
    
    # Orchestrator data
    cognitive_loads: List[float] = None
    zpd_scores: List[float] = None
    motivation_scores: List[float] = None
    scaffolding_decisions: List[str] = None
    
    # Interaction data
    total_interactions: int = 0
    correct_responses: int = 0
    engagement_prompts: int = 0
    rag_retrievals: List[Dict] = None
    
    # Performance data
    initial_masteries: Dict[str, float] = None
    final_masteries: Dict[str, float] = None
    
    def __post_init__(self):
        if self.cognitive_loads is None:
            self.cognitive_loads = []
        if self.zpd_scores is None:
            self.zpd_scores = []
        if self.motivation_scores is None:
            self.motivation_scores = []
        if self.scaffolding_decisions is None:
            self.scaffolding_decisions = []
        if self.rag_retrievals is None:
            self.rag_retrievals = []
        if self.initial_masteries is None:
            self.initial_masteries = {}
        if self.final_masteries is None:
            self.final_masteries = {}

class EnhancedMetricsIntegration:
    """
    Enhanced integration layer for LEA metrics collection
    Handles real-time data collection, session management, and simulation coordination
    """
    
    def __init__(self, redis_client=None, output_dir: str = "./data/metrics"):
        self.metrics_collector = MetricsCollector(output_dir)
        self.redis_client = redis_client
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Active sessions for real-time tracking
        self.active_sessions = {}
        
        # Advanced tracking integration (placeholder for tracking_system.py)
        self.advanced_tracking = None
        self.simulation_mode = False
        
        print(f"DEBUG: Enhanced Metrics Integration initialized")
    
    def start_session_tracking(self, session_type: str, username: str, course: str, week: int) -> str:
        """Start tracking a new session"""
        session_id = f"{session_type}_{username}_{course}_w{week}_{int(time.time())}"
        
        # Get initial mastery state
        initial_masteries = self._get_current_masteries(username, course)
        
        session_data = SessionData(
            session_id=session_id,
            username=username,
            course_code=course,
            week=week,
            session_type=session_type,
            start_time=datetime.now(),
            initial_masteries=initial_masteries
        )
        
        self.active_sessions[session_id] = session_data
        print(f"DEBUG: Started session tracking: {session_id}")
        
        return session_id
    
    def log_orchestrator_decision(self, session_id: str, orchestrator_result: Dict[str, Any]):
        """Log orchestrator decision data for metrics"""
        if session_id not in self.active_sessions:
            print(f"WARNING: Session {session_id} not found for orchestrator logging")
            return
        
        session = self.active_sessions[session_id]
        
        # Extract cognitive state data
        cognitive_state = orchestrator_result.get('cognitive_state')
        if cognitive_state:
            session.cognitive_loads.append(getattr(cognitive_state, 'cognitive_load', 5.0))
            session.zpd_scores.append(getattr(cognitive_state, 'zpd_score', 0.5))
            session.motivation_scores.append(getattr(cognitive_state, 'motivation_score', 0.5))
        
        # Extract scaffolding decisions
        scaffolding = orchestrator_result.get('scaffolding_strategy', {})
        if scaffolding:
            intervention_type = scaffolding.get('intervention_type', 'maintain_flow')
            session.scaffolding_decisions.append(intervention_type)
        
        print(f"DEBUG: Logged orchestrator data for {session_id}")
    
    def log_interaction(self, session_id: str, interaction_data: Dict[str, Any]):
        """Log individual interaction for metrics"""
        if session_id not in self.active_sessions:
            return
        
        session = self.active_sessions[session_id]
        session.total_interactions += 1
        
        # Track correct responses
        if interaction_data.get('is_correct', False):
            session.correct_responses += 1
        
        # Track engagement prompts
        if interaction_data.get('engagement_prompt_delivered', False):
            session.engagement_prompts += 1
        
        # Log advanced tracking data if available
        if self.advanced_tracking:
            self.advanced_tracking.log_interaction(session_id, interaction_data)
    
    def log_rag_retrieval(self, session_id: str, rag_result: Dict[str, Any]):
        """Log RAG retrieval for content coverage analysis"""
        if session_id not in self.active_sessions:
            return
        
        session = self.active_sessions[session_id]
        session.rag_retrievals.append({
            'timestamp': datetime.now().isoformat(),
            'query': rag_result.get('query', ''),
            'num_results': rag_result.get('num_results', 0),
            'results': rag_result.get('results', [])
        })
    
    async def end_session_with_metrics(self, session_id: str) -> Dict[str, Any]:
        """End session and calculate comprehensive metrics"""
        if session_id not in self.active_sessions:
            print(f"ERROR: Session {session_id} not found")
            return {"success": False, "error": "Session not found"}
        
        session = self.active_sessions[session_id]
        session.end_time = datetime.now()
        session.duration_minutes = (session.end_time - session.start_time).total_seconds() / 60
        
        # Get final mastery state
        session.final_masteries = self._get_current_masteries(session.username, session.course_code)
        
        print(f"DEBUG: Ending session {session_id} after {session.duration_minutes:.1f} minutes")
        
        # Build comprehensive interaction history
        interaction_history = self._build_interaction_history(session)
        
        # Calculate metrics using the research-grade collector
        try:
            metrics = await self.metrics_collector.calculate_session_metrics(
                session_data=self._session_to_dict(session),
                interaction_history=interaction_history,
                rag_retrievals=session.rag_retrievals,
                initial_masteries=session.initial_masteries,
                final_masteries=session.final_masteries
            )
            
            # Clean up active session
            del self.active_sessions[session_id]
            
            print(f"DEBUG: ✅ Metrics calculated for {session_id}")
            print(f"DEBUG: - Concept Coverage: {metrics.concept_coverage_precision:.2%}")
            print(f"DEBUG: - Difficulty Error: {metrics.difficulty_alignment_error:.2f}")
            print(f"DEBUG: - ZPD Success: {metrics.zpd_success_rate:.2%}")
            print(f"DEBUG: - Motivation Consistency: {metrics.simulated_affective_response_consistency:.2%}")
            
            return {
                "success": True,
                "session_id": session_id,
                "metrics": metrics,
                "summary": {
                    "interactions": session.total_interactions,
                    "accuracy": session.correct_responses / max(session.total_interactions, 1),
                    "duration_minutes": session.duration_minutes,
                    "concept_coverage": metrics.concept_coverage_precision,
                    "zpd_success": metrics.zpd_success_rate,
                    "motivation_consistency": metrics.simulated_affective_response_consistency
                }
            }
            
        except Exception as e:
            print(f"ERROR: Metrics calculation failed for {session_id}: {e}")
            import traceback
            traceback.print_exc()
            
            # Clean up session anyway
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            
            return {"success": False, "error": str(e)}
    
    def _build_interaction_history(self, session: SessionData) -> List[Dict[str, Any]]:
        """Build interaction history for metrics calculation"""
        interactions = []
        
        # Build from tracked data
        for i in range(session.total_interactions):
            interaction = {
                'timestamp': session.start_time + timedelta(minutes=i * 2),  # Estimated timing
                'generated_content': f"Response to interaction {i+1}",
                'intended_difficulty': 5.0,  # Default, should be logged from orchestrator
                'accuracy': 1.0 if i < session.correct_responses else 0.5,
                'time_ratio': 1.0,
                'hints_used': 0,
                'correct': i < session.correct_responses,
                'scaffolding_intensity': session.scaffolding_decisions[i] if i < len(session.scaffolding_decisions) else 'medium',
                'engagement_prompt_delivered': False,  # Tracked separately
            }
            
            # Add orchestrator data if available
            if i < len(session.cognitive_loads):
                interaction.update({
                    'cognitive_load': session.cognitive_loads[i],
                    'zpd_score': session.zpd_scores[i] if i < len(session.zpd_scores) else 0.5,
                    'engagement': 0.7,  # Derived from other metrics
                    'motivation': session.motivation_scores[i] if i < len(session.motivation_scores) else 0.5
                })
            
            # Add RAG context if available
            if session.rag_retrievals:
                interaction['rag_context'] = session.rag_retrievals[:2]  # Sample RAG results
            
            interactions.append(interaction)
        
        return interactions
    
    def _session_to_dict(self, session: SessionData) -> Dict[str, Any]:
        """Convert session data to dictionary for metrics collector"""
        return {
            'session_id': session.session_id,
            'username': session.username,
            'course_code': session.course_code,
            'start_time': session.start_time,
            'end_time': session.end_time,
            'duration_minutes': session.duration_minutes
        }
    
    def _get_current_masteries(self, username: str, course: str) -> Dict[str, float]:
        """Get current mastery levels for a user"""
        try:
            # Try to get from your existing mastery tracker
            from src.core.mastery_tracker import MasteryTracker
            
            tracker = MasteryTracker(storage_backend="redis" if self.redis_client else "file", 
                                   redis_client=self.redis_client)
            
            summary = tracker.get_mastery_summary(username, course)
            
            # Combine all mastery types
            masteries = {}
            masteries.update(summary.get('go_masteries', {}))
            masteries.update(summary.get('lo_masteries', {}))
            
            # Add week masteries
            week_masteries = summary.get('week_masteries', {})
            for week, level in week_masteries.items():
                masteries[f"week_{week}"] = level
            
            return masteries
            
        except Exception as e:
            print(f"DEBUG: Error getting masteries for {username}: {e}")
            return {}
    
    def get_metrics_summary(self, course: Optional[str] = None, days_back: int = 7) -> Dict[str, Any]:
        """Get metrics summary for analysis"""
        try:
            summaries = self.metrics_collector.get_metric_summaries(course)
            
            # Add session statistics
            csv_path = self.output_dir / "session_metrics.csv"
            if csv_path.exists():
                import pandas as pd
                df = pd.read_csv(csv_path)
                
                # Filter by date if specified
                if days_back:
                    cutoff_date = datetime.now() - timedelta(days=days_back)
                    df['session_start'] = pd.to_datetime(df['session_start'])
                    df = df[df['session_start'] >= cutoff_date]
                
                # Add summary statistics
                summaries['session_stats'] = {
                    'total_sessions': len(df),
                    'avg_duration': df['session_duration_minutes'].mean(),
                    'avg_interactions': df['total_interactions'].mean(),
                    'courses_covered': df['course_code'].nunique(),
                    'users_active': df['username'].nunique()
                }
            
            return summaries
        except Exception as e:
            print(f"DEBUG: Error getting metrics summary: {e}")
            return {}

# STREAMLIT INTEGRATION FUNCTIONS
def integrate_with_streamlit_session(st_session_state, metrics_integration: EnhancedMetricsIntegration):
    """Integrate metrics collection with Streamlit session management"""
    
    # Initialize session tracking if not exists
    if 'metrics_session_id' not in st_session_state:
        st_session_state.metrics_session_id = None
    
    def start_mode_with_metrics(mode: str):
        """Start a new mode with metrics tracking"""
        if st_session_state.metrics_session_id:
            # End previous session
            asyncio.run(metrics_integration.end_session_with_metrics(st_session_state.metrics_session_id))
        
        # Start new session
        username = st_session_state.get('username', 'unknown')
        course = st_session_state.get('selected_course', 'unknown')
        week = st_session_state.get('selected_week', 1)
        
        st_session_state.metrics_session_id = metrics_integration.start_session_tracking(
            mode, username, course, week
        )
        print(f"DEBUG: Started metrics tracking for {mode} mode")
    
    def log_orchestrator_data(orchestrator_result: Dict):
        """Log orchestrator decision data"""
        if st_session_state.metrics_session_id:
            metrics_integration.log_orchestrator_decision(
                st_session_state.metrics_session_id, 
                orchestrator_result
            )
    
    def log_interaction_data(interaction_data: Dict):
        """Log interaction data"""
        if st_session_state.metrics_session_id:
            metrics_integration.log_interaction(
                st_session_state.metrics_session_id,
                interaction_data
            )
    
    def end_current_session():
        """End current session and calculate metrics"""
        if st_session_state.metrics_session_id:
            result = asyncio.run(metrics_integration.end_session_with_metrics(
                st_session_state.metrics_session_id
            ))
            st_session_state.metrics_session_id = None
            return result
        return None
    
    return start_mode_with_metrics, log_orchestrator_data, log_interaction_data, end_current_session

# SIMULATION FRAMEWORK
class LEASimulationFramework:
    """Simulation framework for automated metrics collection and validation"""
    
    def __init__(self, metrics_integration: EnhancedMetricsIntegration, orchestrator=None):
        self.metrics_integration = metrics_integration
        self.orchestrator = orchestrator
        self.simulation_results = []
        
        # Enable simulation mode
        self.metrics_integration.simulation_mode = True
        
        print("DEBUG: LEA Simulation Framework initialized")
    
    async def run_learner_simulation(
        self, 
        num_agents: int = 10,
        session_duration: int = 30,  # minutes
        course: str = "CMP511"
    ) -> List[Dict[str, Any]]:
        """Run simulation with multiple learner agents"""
        
        print(f"DEBUG: Starting simulation with {num_agents} agents")
        results = []
        
        for agent_id in range(num_agents):
            agent_result = await self._simulate_single_learner(
                agent_id, session_duration, course
            )
            results.append(agent_result)
            
            # Small delay between agents
            await asyncio.sleep(0.1)
        
        self.simulation_results.extend(results)
        print(f"DEBUG: Completed simulation with {len(results)} agents")
        
        return results
    
    async def _simulate_single_learner(
        self, 
        agent_id: int, 
        duration_minutes: int,
        course: str
    ) -> Dict[str, Any]:
        """Simulate a single learner session"""
        
        username = f"sim_agent_{agent_id}"
        session_id = self.metrics_integration.start_session_tracking(
            "simulation", username, course, 1
        )
        
        # Simulate learner characteristics
        learning_rate = np.random.uniform(0.1, 0.9)
        initial_motivation = np.random.uniform(0.3, 0.8)
        cognitive_capacity = np.random.uniform(3.0, 8.0)
        
        print(f"DEBUG: Simulating learner {agent_id} with learning_rate={learning_rate:.2f}")
        
        # Simulate interactions over time
        num_interactions = int(duration_minutes * np.random.uniform(0.5, 2.0))  # Variable interaction rate
        
        for i in range(num_interactions):
            # Simulate orchestrator decision
            current_cl = np.random.uniform(2.0, 8.0)
            current_zpd = learning_rate + np.random.normal(0, 0.1)
            current_motivation = max(0.1, initial_motivation + np.random.normal(0, 0.1))
            
            orchestrator_result = {
                'cognitive_state': type('CognitiveState', (), {
                    'cognitive_load': current_cl,
                    'zpd_score': np.clip(current_zpd, 0, 1),
                    'motivation_score': np.clip(current_motivation, 0, 1)
                })(),
                'scaffolding_strategy': {
                    'intervention_type': np.random.choice([
                        'maintain_flow', 'increase_support', 'reduce_support', 'concept_review'
                    ])
                }
            }
            
            self.metrics_integration.log_orchestrator_decision(session_id, orchestrator_result)
            
            # Simulate interaction outcome
            success_prob = learning_rate * (1 - current_cl / 10) * current_motivation
            is_correct = np.random.random() < success_prob
            
            interaction_data = {
                'is_correct': is_correct,
                'engagement_prompt_delivered': np.random.random() < 0.1,  # 10% chance
                'response_time': np.random.uniform(10, 120)  # seconds
            }
            
            self.metrics_integration.log_interaction(session_id, interaction_data)
            
            # Simulate RAG retrieval
            if np.random.random() < 0.3:  # 30% of interactions use RAG
                rag_result = {
                    'query': f"simulated query {i}",
                    'num_results': np.random.randint(1, 5),
                    'results': [
                        {'content': f"simulated content {j}", 'relevance': 'high'} 
                        for j in range(np.random.randint(1, 4))
                    ]
                }
                self.metrics_integration.log_rag_retrieval(session_id, rag_result)
            
            # Small delay between interactions
            await asyncio.sleep(0.01)
        
        # End session and get metrics
        result = await self.metrics_integration.end_session_with_metrics(session_id)
        
        # Add simulation metadata
        result['simulation_metadata'] = {
            'agent_id': agent_id,
            'learning_rate': learning_rate,
            'initial_motivation': initial_motivation,
            'cognitive_capacity': cognitive_capacity,
            'simulated_interactions': num_interactions
        }
        
        return result
    
    def analyze_simulation_results(self) -> Dict[str, Any]:
        """Analyze simulation results for validation"""
        if not self.simulation_results:
            return {"error": "No simulation results to analyze"}
        
        successful_sessions = [r for r in self.simulation_results if r.get('success', False)]
        
        if not successful_sessions:
            return {"error": "No successful simulation sessions"}
        
        # Extract metrics for analysis
        concept_coverage = [r['metrics'].concept_coverage_precision for r in successful_sessions]
        difficulty_errors = [r['metrics'].difficulty_alignment_error for r in successful_sessions]
        zpd_success = [r['metrics'].zpd_success_rate for r in successful_sessions]
        motivation_consistency = [r['metrics'].simulated_affective_response_consistency for r in successful_sessions]
        
        analysis = {
            'total_simulated_sessions': len(self.simulation_results),
            'successful_sessions': len(successful_sessions),
            'metrics_analysis': {
                'concept_coverage_precision': {
                    'mean': np.mean(concept_coverage),
                    'std': np.std(concept_coverage),
                    'target_met': np.mean(concept_coverage) > 0.8
                },
                'difficulty_alignment_error': {
                    'mean': np.mean(difficulty_errors),
                    'std': np.std(difficulty_errors),
                    'target_met': np.mean(difficulty_errors) < 1.0
                },
                'zpd_success_rate': {
                    'mean': np.mean(zpd_success),
                    'std': np.std(zpd_success)
                },
                'motivation_consistency': {
                    'mean': np.mean(motivation_consistency),
                    'std': np.std(motivation_consistency),
                    'target_met': np.mean(motivation_consistency) > 0.8
                }
            },
            'learning_outcomes': {
                'avg_accuracy': np.mean([r['summary']['accuracy'] for r in successful_sessions]),
                'avg_interactions': np.mean([r['summary']['interactions'] for r in successful_sessions]),
                'avg_duration': np.mean([r['summary']['duration_minutes'] for r in successful_sessions])
            }
        }
        
        return analysis

# USAGE EXAMPLE
async def example_integration():
    """Example of how to integrate the enhanced metrics system"""
    
    # Initialize the enhanced metrics integration
    metrics_integration = EnhancedMetricsIntegration()
    
    # Example: Start tracking a quiz session
    session_id = metrics_integration.start_session_tracking(
        "quiz", "test_user", "CMP511", 1
    )
    
    # Example: Log orchestrator decisions during the session
    orchestrator_result = {
        'cognitive_state': type('CognitiveState', (), {
            'cognitive_load': 4.5,
            'zpd_score': 0.7,
            'motivation_score': 0.8
        })(),
        'scaffolding_strategy': {'intervention_type': 'maintain_flow'}
    }
    
    metrics_integration.log_orchestrator_decision(session_id, orchestrator_result)
    
    # Example: Log interactions
    interaction_data = {'is_correct': True, 'engagement_prompt_delivered': False}
    metrics_integration.log_interaction(session_id, interaction_data)
    
    # Example: End session and get metrics
    result = await metrics_integration.end_session_with_metrics(session_id)
    print("Metrics result:", result)
    
    # Example: Run simulation
    simulation = LEASimulationFramework(metrics_integration)
    simulation_results = await simulation.run_learner_simulation(num_agents=5)
    analysis = simulation.analyze_simulation_results()
    print("Simulation analysis:", analysis)

if __name__ == "__main__":
    asyncio.run(example_integration())
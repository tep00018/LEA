# src/simulation/learner_agents.py
"""
Learner agent implementations for LEA simulation
"""
import mesa
import random
import asyncio
from typing import Dict, Any
from src.core.parallel_agent_orchestrator import ParallelLEAOrchestrator

class BaseLearnerAgent(mesa.Agent):
    """Base class for all learner agent types"""
    
    def __init__(self, unique_id: int, model, agent_type: str):
        super().__init__(unique_id, model)
        self.agent_type = agent_type
        self.username = f"sim_user_{unique_id}"
        self.session_id = f"sim_session_{unique_id}"
        
        # Learning characteristics (different for each agent type)
        self.current_mastery = self._initialize_mastery()
        self.learning_rate = self._get_learning_rate()
        self.cognitive_load_threshold = self._get_cognitive_threshold()
        self.engagement_level = 1.0
        self.questions_asked = 0
        self.correct_responses = 0
        
        # Track interactions for analysis
        self.interaction_history = []
    
    def step(self):
        """Execute one learning interaction step"""
        # Generate a query based on agent type and current state
        query = self._generate_query()
        
        # Interact with the real LEA orchestrator
        response_data = self._interact_with_lea(query)
        
        # Update agent state based on response
        self._update_state(response_data)
        
        # Record interaction for analysis
        self._record_interaction(query, response_data)
    
    def _interact_with_lea(self, query: str) -> Dict[str, Any]:
        """Use the actual LEA orchestrator to process the query"""
        try:
            # This uses your real orchestrator with all the actual logic
            result = asyncio.run(
                self.model.orchestrator.process_query(
                    user_query=query,
                    username=self.username,
                    selected_course="CMP511",  # Fixed for simulation
                    session_id=self.session_id,
                    selected_week=self._get_current_week()
                )
            )
            return result
        except Exception as e:
            print(f"Simulation interaction error: {e}")
            return {"response": "Error in simulation", "metadata": {}}
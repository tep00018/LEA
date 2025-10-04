# File: src/quiz/simple_quiz_system.py
"""
Simple Quiz System with MCP RAG Integration
Enhanced educational quiz generation system using centralized content retrieval
and adaptive question generation based on learner motivation states.

This module provides a comprehensive quiz system that integrates with the 
LEA (Learning Enhancement Application) architecture, utilizing MCP-based
RAG retrieval for consistent content access across all learning modalities.
"""

import os
import json
import random
import asyncio
import concurrent.futures
from openai import OpenAI
from typing import Dict, List, Optional, Any, Tuple
import time
from datetime import datetime
import uuid



def store_quiz_memory(
    redis_client, 
    username: str, 
    question: Dict, 
    user_answer: str, 
    is_correct: bool, 
    score: float
) -> None:
    """
    Store quiz interaction in the memory system for long-term tracking.
    
    This function persists quiz interactions to Redis for analytics and
    adaptive learning purposes. The stored data enables tracking of learner
    progress and performance patterns over time.
    
    Args:
        redis_client: Redis client instance for data persistence
        username: Unique identifier for the learner
        question: Dictionary containing question details
        user_answer: The learner's response to the question
        is_correct: Boolean indicating answer correctness
        score: Numerical score (0.0 to 1.0) for the response
    """
    try:
        if redis_client and hasattr(redis_client, 'store_short_term_memory'):
            redis_client.store_short_term_memory(
                username=username,
                interaction_type="quiz",
                content={
                    "question": question.get("text", ""),
                    "question_type": question.get("type", "multiple_choice"),
                    "user_answer": user_answer,
                    "correct": is_correct,
                    "score": score,
                    "go_id": question.get("go_id", ""),
                    "course": question.get("course", "CMP511"),
                    "week": question.get("week", 1),
                    "timestamp": time.time()
                }
            )
            print(f"DEBUG: Stored quiz memory for {username}")
    except Exception as e:
        print(f"DEBUG: Failed to store quiz memory: {e}")


class SimpleQuizSystem:
    """
    Enhanced quiz system utilizing MCP RAG integration for content retrieval.
    
    This system generates adaptive quiz questions based on learning objectives,
    learner motivation states, and course content. It maintains consistency
    with Chat and Tutor modes by using centralized RAG retrieval through MCP.
    
    Key Features:
        - Adaptive question generation based on cognitive load and motivation
        - Question type variety enforcement for comprehensive assessment
        - Conversational feedback using personalized language
        - Integration with centralized RAG content retrieval
        - Support for multiple question formats (MC, T/F, FIB, OE)
    """
    
    def __init__(self, openai_api_key: str, rag_tool=None):
        """
        Initialize the quiz system with required dependencies.
        
        Args:
            openai_api_key: API key for OpenAI services
            rag_tool: RAGRetrievalTool instance for content retrieval
        """
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.rag_tool = rag_tool
        self.active_quizzes = {}
        
        # Question type configuration
        self.question_types = ["multiple_choice", "true_false", "fill_in_blank", "open_ended"]
        self.type_weights = [0.4, 0.3, 0.2, 0.1]
        
        # Tracking mechanisms
        self.question_history = {}
        self.quiz_type_tracker = {}

        # Redis integration for memory persistence
        try:
            from src.storage.redis_client import LEARedisClient
            self.redis_client = LEARedisClient()
            print("DEBUG: Quiz system initialized with Redis memory support")
        except Exception as e:
            print(f"DEBUG: Quiz system running without Redis: {e}")
            self.redis_client = None
        
        print("DEBUG: SimpleQuizSystem initialized with MCP RAG integration")
    
    def set_rag_tool(self, rag_tool) -> None:
        """
        Set or update the RAG tool after initialization.
        
        This method allows for dynamic configuration of the RAG tool,
        enabling flexibility in system setup and testing scenarios.
        
        Args:
            rag_tool: RAGRetrievalTool instance for content retrieval
        """
        self.rag_tool = rag_tool
        print("DEBUG: RAG tool set for quiz system")
    
    def _run_async(self, coro):
        """
        Execute async coroutine safely in any context.
        
        This helper method detects the execution context and handles
        async operations appropriately, whether called from sync or async code.
        """
        import asyncio
        import concurrent.futures
        
        try:
            # Check if there's a running event loop in the current thread
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop - we're in a sync context
            # Create a new event loop for this operation
            return asyncio.run(coro)
        else:
            # There's already a running loop - we're in an async context
            # Use a thread pool to run the coroutine in a separate thread
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()

    async def _get_relevant_content_via_rag(
        self, 
        keywords: List[str], 
        go_data: Dict[str, Any] = None,
        course: str = "CMP511"
    ) -> str:
        """
        Get GO-specific content using MCP RAG tool with correct extraction for your RAG structure
        """
        if not self.rag_tool:
            print("WARNING: No RAG tool available, using fallback content")
            return self._get_fallback_content(go_data)
        
        try:
            skill_name = go_data.get("skill_name", "") if go_data else ""
            description = go_data.get("description", "") if go_data else ""
            
            # Construct targeted queries
            primary_query = f"{skill_name} {' '.join(keywords[:3])}" if keywords else skill_name
            
            query_variations = [
                primary_query,
                f"{skill_name} implementation" if skill_name else f"{primary_query} implementation",
                f"{skill_name} examples" if skill_name else f"{primary_query} examples"
            ]
            
            if description:
                desc_words = [word for word in description.lower().split() 
                            if len(word) > 4 and word not in ['machine', 'learning', 'using', 'with']]
                if desc_words:
                    query_variations.append(f"{desc_words[0]} {primary_query}")
            
            print(f"DEBUG: RAG search with GO-specific queries: {query_variations[:2]}")
            
            all_content_pieces = []
            
            # Execute RAG queries
            for i, query in enumerate(query_variations[:2]):
                try:
                    rag_result = await self.rag_tool.execute({
                        "query": query,
                        "course": course,
                        "max_results": 3,
                        "use_reranking": True
                    })
                    
                    if rag_result.get("success") and rag_result.get("results"):
                        for j, result in enumerate(rag_result["results"]):
                            content = None
                            
                            # Your RAG system returns dicts with 'content' field
                            if isinstance(result, dict):
                                # Based on your debug output, the 'content' field exists
                                content = result.get("content")
                                
                                # Debug if content extraction fails
                                if not content:
                                    print(f"DEBUG: Result {j} has no 'content' field. Keys: {list(result.keys())}")
                                    # Try alternative field names just in case
                                    for field in ["text", "document", "page_content", "chunk_text"]:
                                        if field in result and result[field]:
                                            content = result[field]
                                            print(f"DEBUG: Found content in '{field}' field")
                                            break
                            elif isinstance(result, str):
                                # If result is directly a string, use it as content
                                content = result
                                print(f"DEBUG: Result {j} is a string, using directly")
                            
                            # Process valid content
                            if content:
                                # Check if content is actually meaningful (not just metadata)
                                content_str = str(content)
                                
                                # Skip if content is just "metadata..." or similar placeholder
                                if content_str.strip().startswith("metadata"):
                                    print(f"DEBUG: Skipping metadata placeholder content")
                                    continue
                                
                                # Use actual content if it's substantial
                                if len(content_str) > 50:
                                    content_piece = content_str[:800]
                                    
                                    # Avoid duplicates
                                    content_hash = hash(content_piece[:100])
                                    if not any(hash(existing['content'][:100]) == content_hash 
                                             for existing in all_content_pieces):
                                        all_content_pieces.append({
                                            'content': content_piece,
                                            'source': f'query_{i}_result_{j}',
                                            'has_code': self._has_code_content(content_piece),
                                            'query_used': query,
                                            'relevance_score': result.get("relevance", result.get("rerank_score", 0.5)) if isinstance(result, dict) else 0.5
                                        })
                                        
                                        if self._has_code_content(content_piece):
                                            print(f"DEBUG: ⭐ Content piece from '{query}' contains code")
                                        
                                        # Show preview of actual content
                                        preview = content_piece[:100].replace('\n', ' ')
                                        print(f"DEBUG: Content preview: {preview}...")
                            else:
                                print(f"DEBUG: No content extracted from result {j}")
                    
                except Exception as rag_error:
                    print(f"WARNING: RAG query failed for '{query}': {rag_error}")
            
            print(f"DEBUG: Retrieved {len(all_content_pieces)} diverse content pieces via RAG")
            
            # Balance content selection
            final_content_pieces = []
            code_pieces = [p for p in all_content_pieces if p['has_code']]
            non_code_pieces = [p for p in all_content_pieces if not p['has_code']]
            
            if skill_name and any(term in skill_name.lower() for term in ['implement', 'algorithm', 'code']):
                if code_pieces:
                    final_content_pieces.extend([p['content'] for p in code_pieces[:2]])
                if non_code_pieces and len(final_content_pieces) < 2:
                    final_content_pieces.append(non_code_pieces[0]['content'])
            else:
                if non_code_pieces:
                    final_content_pieces.append(non_code_pieces[0]['content'])
                if code_pieces and len(final_content_pieces) < 2:
                    final_content_pieces.append(code_pieces[0]['content'])
                if len(final_content_pieces) < 2 and len(non_code_pieces) > 1:
                    final_content_pieces.append(non_code_pieces[1]['content'])
            
            if not final_content_pieces and all_content_pieces:
                final_content_pieces = [all_content_pieces[0]['content']]
            
            if final_content_pieces:
                final_content = "\n\n---\n\n".join(final_content_pieces)
                print(f"DEBUG: Final content length: {len(final_content)} characters")
                print(f"DEBUG: Content includes code: {self._has_code_content(final_content)}")
                return final_content
            else:
                print(f"DEBUG: No content retrieved via RAG, using fallback")
                return self._get_fallback_content(go_data)
            
        except Exception as e:
            print(f"ERROR: Failed to retrieve content via RAG: {e}")
            import traceback
            traceback.print_exc()
            return self._get_fallback_content(go_data)


    def _get_fallback_content(self, go_data: Dict[str, Any] = None) -> str:
        """
        Provide fallback content when RAG retrieval is unavailable.
        
        This method ensures quiz generation can continue even when content
        retrieval fails, maintaining system resilience and user experience.
        
        Args:
            go_data: Granular objective data for context
            
        Returns:
            Generic content string related to the learning objective
        """
        if not go_data:
            return "Content about machine learning concepts and implementation."
        
        skill_name = go_data.get("skill_name", "machine learning concept")
        description = go_data.get("description", "")
        
        fallback_content = f"""
        Content about {skill_name}:
        
        {description if description else f"{skill_name} is an important concept in machine learning."}
        
        This topic involves understanding the theoretical foundations and practical applications.
        Implementation typically requires careful consideration of data preparation, model selection,
        and evaluation metrics. Students should focus on both conceptual understanding and 
        practical implementation skills.
        """
        
        print(f"DEBUG: Using fallback content for {skill_name}")
        return fallback_content

    async def _generate_question(
        self, 
        course: str, 
        question_plan: Dict[str, Any],
        orchestrator_context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Generate an adaptive question using RAG content and orchestrator guidance.
        
        This method creates questions tailored to the learner's cognitive state
        and motivation level, utilizing course content retrieved via RAG and
        applying orchestrator recommendations for optimal learning outcomes.
        
        Args:
            course: Course identifier for content scope
            question_plan: Dictionary containing question specifications
            orchestrator_context: Optional context for adaptive generation
            
        Returns:
            Dictionary containing the generated question or None on failure
        """
        try:
            # Apply orchestrator recommendations for adaptive generation
            if orchestrator_context:
                question_plan = self._apply_orchestrator_recommendations_fixed(question_plan, orchestrator_context)
                print(f"DEBUG: 🎯 Applied orchestrator recommendations - Type: {question_plan['type']}, Difficulty: {question_plan.get('adjusted_difficulty', 'medium')}")
            
            # Retrieve content via centralized RAG tool
            content = await self._get_relevant_content_via_rag(
                question_plan["keywords"], 
                question_plan,
                course
            )
            
            # Create comprehensive generation prompt
            prompt = self._create_orchestrator_guided_prompt(question_plan, content, orchestrator_context)
            
            # Generate question using OpenAI
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an expert educational content creator. Generate quiz questions that adapt to the student's cognitive state and learning needs."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=1000
            )
            
            # Parse and enhance the generated question
            question_text = response.choices[0].message.content.strip()
            question_data = self._parse_generated_question(question_text, question_plan["type"])
            
            if question_data:
                # Add metadata for tracking and analysis
                question_data["go_id"] = question_plan["go_id"]
                question_data["lo_id"] = question_plan["lo_id"]
                question_data["skill_name"] = question_plan["skill_name"]
                question_data["course"] = course
                
                # Include orchestrator metadata if applicable
                if orchestrator_context:
                    question_data["orchestrator_applied"] = True
                    question_data["scaffolding_strategy"] = orchestrator_context.get("scaffolding_strategy", {}).get("strategy_type", "none")
                    question_data["difficulty_adjustment"] = orchestrator_context.get("scaffolding_strategy", {}).get("difficulty_adjustment", "maintain")
                    question_data["support_level"] = orchestrator_context.get("scaffolding_strategy", {}).get("support_level", "medium")
                else:
                    question_data["orchestrator_applied"] = False
                
                # Track for variety maintenance
                self._track_question_for_variety(question_data, question_plan)
            
            return question_data
            
        except Exception as e:
            print(f"ERROR: Failed to generate question: {e}")
            import traceback
            traceback.print_exc()
            return None

    def start_quiz(
        self, 
        course: str, 
        week: int, 
        username: str, 
        orchestrator_context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Initialize a new quiz session with adaptive question generation.
        Enhanced to handle both synchronous and asynchronous execution contexts.
        """
        try:
            # Verify RAG tool availability
            if not self.rag_tool:
                print("ERROR: No RAG tool available for quiz generation")
                return None
            
            # Load knowledge component model
            from src.core.kc_model_loader import KCModelLoader
            import redis
            
            redis_client = redis.Redis.from_url(
                os.getenv("REDIS_URL", "redis://localhost:6379"),
                decode_responses=True
            )
            kc_loader = KCModelLoader(redis_client, module=course)
            
            # Retrieve week content structure
            week_content = kc_loader.get_week_content(course, week)
            
            # Generate comprehensive question plan
            question_plan = []
            motivation_state = orchestrator_context.get('motivation_state') if orchestrator_context else None
            
            question_number = 1
            quiz_id = f"quiz_{username}_{course}_w{week}_{uuid.uuid4().hex[:8]}"
            
            # Initialize type tracking for variety enforcement
            self.quiz_type_tracker[quiz_id] = {
                "multiple_choice": 0, 
                "true_false": 0, 
                "fill_in_blank": 0, 
                "open_ended": 0
            }
            
            # Build question plan for all granular objectives
            for lo in week_content.learning_objectives:
                lo_question_count = 0
                
                for go in lo.granular_objectives:
                    question_type = self._select_variety_enforced_question_type(
                        go, lo, question_number, lo_question_count, 
                        motivation_state, quiz_id
                    )
                    
                    question_plan.append({
                        "go_id": go.go_id,
                        "lo_id": lo.lo_id,
                        "skill_name": go.skill_name,
                        "description": go.description,
                        "keywords": go.content_keywords,
                        "type": question_type,
                        "question_number": question_number,
                        "lo_question_count": lo_question_count,
                        "motivation_state": motivation_state,
                        "quiz_id": quiz_id,
                        "base_difficulty": 0.5
                    })
                    
                    question_number += 1
                    lo_question_count += 1
            
            # Log question distribution
            type_distribution = {}
            for q in question_plan:
                qtype = q["type"]
                type_distribution[qtype] = type_distribution.get(qtype, 0) + 1
            
            print(f"DEBUG: Question type distribution: {type_distribution}")
            
            if not question_plan:
                print(f"ERROR: No granular objectives found for {course} week {week}")
                return None
            
            # Generate initial question using the helper method
            first_question_plan = question_plan[0]
            first_question = self._run_async(
                self._generate_question(course, first_question_plan, orchestrator_context)
            )
            
            if not first_question:
                print(f"ERROR: Failed to generate first question")
                return None
            
            # Create quiz session
            quiz_session = {
                "quiz_id": quiz_id,
                "username": username,
                "course": course,
                "week": week,
                "question_plan": question_plan,
                "current_question_index": 0,
                "current_question": first_question,
                "answers": [],
                "start_time": datetime.now().isoformat(),
                "orchestrator_context": orchestrator_context,
                "motivation_tracking": {
                    "initial_state": motivation_state,
                    "state_changes": [],
                    "adaptations_applied": []
                }
            }
            
            self.active_quizzes[quiz_id] = quiz_session
            
            print(f"DEBUG: Started quiz {quiz_id} with {len(question_plan)} questions using MCP RAG")
            print(f"DEBUG: Initial motivation state: {motivation_state}")
            
            return quiz_session
            
        except Exception as e:
            print(f"ERROR: Failed to start quiz: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_next_question(self, quiz_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Generate and retrieve the next question in the quiz sequence.
        Enhanced to handle both synchronous and asynchronous execution contexts.
        """
        try:
            quiz_data["current_question_index"] += 1
            
            # Check for quiz completion
            if quiz_data["current_question_index"] >= len(quiz_data["question_plan"]):
                print(f"DEBUG: Quiz {quiz_data['quiz_id']} completed")
                return None
            
            # Retrieve orchestrator context
            orchestrator_context = quiz_data.get('orchestrator_context')
            
            # Generate next question
            next_question_plan = quiz_data["question_plan"][quiz_data["current_question_index"]]
            
            if orchestrator_context:
                print(f"DEBUG: 🎯 Generating motivation-informed next question")
            
            # Use the helper method for async execution
            next_question = self._run_async(
                self._generate_question(
                    quiz_data["course"],
                    next_question_plan,
                    orchestrator_context=orchestrator_context
                )
            )
            
            if not next_question:
                print(f"ERROR: Failed to generate next question")
                return None
            
            quiz_data["current_question"] = next_question
            return quiz_data
            
        except Exception as e:
            print(f"ERROR: Failed to get next question: {e}")
            return None

    def _apply_orchestrator_recommendations_fixed(
        self, 
        question_plan: Dict[str, Any], 
        orchestrator_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Apply orchestrator recommendations while preserving question variety.
        
        This method carefully applies cognitive load and motivation-based
        adjustments to question generation while maintaining the diversity
        necessary for comprehensive assessment.
        
        Args:
            question_plan: Original question specifications
            orchestrator_context: Context containing recommendations
            
        Returns:
            Modified question plan with applied recommendations
        """
        scaffolding = orchestrator_context.get("scaffolding_strategy", {})
        adaptive_context = orchestrator_context.get("adaptive_context", {})
        
        original_type = question_plan["type"]
        quiz_id = question_plan.get("quiz_id", "default")
        
        # Ensure type tracker exists
        if quiz_id not in self.quiz_type_tracker:
            self.quiz_type_tracker[quiz_id] = {
                "multiple_choice": 0, 
                "true_false": 0, 
                "fill_in_blank": 0, 
                "open_ended": 0
            }
        
        type_counts = self.quiz_type_tracker[quiz_id]
        total_questions = sum(type_counts.values())
        
        # Conservative type override based on cognitive state
        should_override = False
        recommended_type = original_type
        
        cognitive_state = orchestrator_context.get('cognitive_state')
        if cognitive_state:
            cognitive_load = getattr(cognitive_state, 'cognitive_load', 5.0)
            
            # Apply overrides only in extreme cases
            if cognitive_load > 8.0 and original_type == "open_ended":
                recommended_type = "multiple_choice"
                should_override = True
                print(f"DEBUG: 🚨 High CL override: {original_type} → {recommended_type}")
            elif cognitive_load < 2.0 and original_type == "true_false" and type_counts["open_ended"] < 2:
                recommended_type = "open_ended"
                should_override = True
                print(f"DEBUG: 🚀 Low CL override: {original_type} → {recommended_type}")
        
        # Apply motivation-based adjustments
        motivation_state = orchestrator_context.get('motivation_state', 'motivation_plateau')
        if motivation_state == 'motivation_drop' and original_type == "open_ended":
            recommended_type = "multiple_choice"
            should_override = True
            print(f"DEBUG: 💝 Motivation support override: {original_type} → {recommended_type}")
        elif motivation_state == 'maintained_high' and original_type == "true_false" and type_counts["open_ended"] < 2:
            recommended_type = "open_ended"
            should_override = True
            print(f"DEBUG: 🚀 High motivation challenge override: {original_type} → {recommended_type}")
        
        # Apply override if justified
        if should_override:
            question_plan["type"] = recommended_type
            print(f"DEBUG: 🔄 Question type override applied: {original_type} → {recommended_type}")
        else:
            print(f"DEBUG: ✅ Question type preserved: {original_type}")
        
        # Update tracking
        self.quiz_type_tracker[quiz_id][question_plan["type"]] += 1
        
        # Apply difficulty adjustments
        difficulty_adjustment = scaffolding.get("difficulty_adjustment", "maintain")
        question_plan["adjusted_difficulty"] = self._calculate_adjusted_difficulty(
            question_plan.get("base_difficulty", 0.5), 
            difficulty_adjustment
        )
        
        # Set support parameters
        question_plan["support_level"] = scaffolding.get("support_level", "medium")
        question_plan["hint_count"] = scaffolding.get("hint_count", 2)
        question_plan["example_count"] = scaffolding.get("example_count", 2)
        
        # Apply content adaptations
        content_adaptations = scaffolding.get("content_adaptations", {})
        question_plan["content_density"] = content_adaptations.get("content_density", "moderate")
        question_plan["visualization_level"] = content_adaptations.get("visualization_level", "moderate_visual")
        
        return question_plan

    def _calculate_adjusted_difficulty(self, base_difficulty: float, adjustment: str) -> float:
        """
        Calculate adjusted difficulty based on orchestrator recommendations.
        
        Args:
            base_difficulty: Original difficulty level (0.0 to 1.0)
            adjustment: Adjustment directive from orchestrator
            
        Returns:
            Adjusted difficulty value bounded between 0.1 and 0.9
        """
        adjustments = {
            "decrease_significantly": -0.3,
            "decrease": -0.15,
            "maintain": 0.0,
            "increase": 0.15,
            "increase_significantly": 0.3
        }
        
        adjustment_value = adjustments.get(adjustment, 0.0)
        adjusted = base_difficulty + adjustment_value
        
        return max(0.1, min(0.9, adjusted))

    def _has_code_content(self, content: str) -> bool:
        """
        Determine if content contains programming code snippets.
        
        Args:
            content: Text content to analyze
            
        Returns:
            Boolean indicating presence of code
        """
        code_indicators = [
            'import ', 'from ', 'def ', 'class ', '= ', '()', '.fit(', '.predict(', 
            'sklearn', 'numpy', 'pandas', 'matplotlib', '```python', 'print(',
            'RandomForest', 'LogisticRegression', 'train_test_split', 'X_train', 'y_train'
        ]
        
        content_lower = content.lower()
        return any(indicator.lower() in content_lower for indicator in code_indicators)

    def _create_orchestrator_guided_prompt(
        self, 
        question_plan: Dict[str, Any], 
        content: str, 
        orchestrator_context: Optional[Dict[str, Any]]
    ) -> str:
        """
        Create comprehensive prompt for question generation with orchestrator guidance.
        
        This method constructs a detailed prompt that incorporates motivation state,
        cognitive load considerations, and scaffolding strategies to generate
        questions optimally suited to the learner's current state.
        
        Args:
            question_plan: Question specifications and metadata
            content: Retrieved course content for context
            orchestrator_context: Optional adaptive generation parameters
            
        Returns:
            Complete prompt string for question generation
        """
        base_prompt = self._create_enhanced_generation_prompt(question_plan, content)
        
        if not orchestrator_context:
            return base_prompt
        
        motivation_state = orchestrator_context.get('motivation_state', 'motivation_plateau')
        motivation_feedback = orchestrator_context.get('motivation_feedback', {})
        scaffolding = orchestrator_context.get('scaffolding_strategy', {})
        
        motivation_guidance = f"""
        **EXPLICIT MOTIVATION-INFORMED ADAPTATIONS:**
        
        Current Student Motivation State: {motivation_state.upper()}
        
        SPECIFIC CONTENT ADAPTATIONS REQUIRED:
        """
        
        # Apply state-specific generation guidelines
        if motivation_state == 'motivation_drop':
            motivation_guidance += """
        - MOTIVATION DROP DETECTED - Apply supportive intervention
        - Use encouraging, non-controlling language
        - Reduce cognitive pressure with simpler question structure
        - Include extra scaffolding and hints
        - Focus on effort and process rather than just correctness
        - Provide choices where possible
        - Add emotional support elements
        - Break complex concepts into smaller, manageable pieces
        """
        elif motivation_state == 'maintained_high':
            motivation_guidance += """
        - HIGH MOTIVATION DETECTED - Apply challenge escalation
        - Increase question complexity and depth
        - Include advanced applications and transfer opportunities  
        - Offer stretch goals and extension activities
        - Use challenging, engaging language
        - Encourage peer teaching opportunities
        - Present real-world, complex scenarios
        - Minimize scaffolding to encourage independent thinking
        """
        elif motivation_state == 'cold_start':
            motivation_guidance += """
        - BASELINE ESTABLISHMENT PHASE - Apply welcoming support
        - Use especially welcoming, encouraging tone
        - Provide positive reinforcement without performance pressure
        - Include clear, friendly explanations
        - Set up supportive learning environment
        - Focus on exploration and discovery
        - Avoid overwhelming with too much information
        - Use collaborative language
        """
        elif motivation_state == 'motivation_plateau':
            motivation_guidance += """
        - STABLE ENGAGEMENT - Apply process-oriented support
        - Celebrate effort and strategic thinking
        - Provide mastery-oriented feedback
        - Emphasize growth mindset principles
        - Focus on learning process and improvement
        - Offer metacognitive prompts
        - Balance challenge with support
        """
        
        # Add scaffolding strategy guidance
        strategy_type = scaffolding.get('strategy_type', 'procedural')
        motivation_guidance += f"""
        
        SCAFFOLDING STRATEGY: {strategy_type.upper()}
        """
        
        if strategy_type == "conceptual":
            motivation_guidance += """
        - Focus on core concepts and relationships
        - Use clear explanations and analogies
        - Include conceptual understanding checks
        - Emphasize theoretical foundations
        """
        elif strategy_type == "procedural":
            motivation_guidance += """
        - Emphasize step-by-step processes
        - Break down complex procedures
        - Include procedural knowledge checks
        - Focus on implementation details
        """
        elif strategy_type == "strategic":
            motivation_guidance += """
        - Focus on problem-solving strategies
        - Compare different approaches
        - Include strategy selection opportunities
        - Emphasize decision-making processes
        """
        elif strategy_type == "metacognitive":
            motivation_guidance += """
        - Encourage self-reflection and awareness
        - Include confidence and process questions
        - Ask about learning strategies
        - Promote self-monitoring
        """
        
        return base_prompt + "\n\n" + motivation_guidance

    def _create_enhanced_generation_prompt(self, question_plan: Dict[str, Any], content: str) -> str:
        """
        Create detailed prompt for question generation with variety requirements.
        
        This method constructs the base prompt that ensures question diversity,
        appropriate difficulty, and alignment with learning objectives.
        
        Args:
            question_plan: Question specifications and metadata
            content: Retrieved course content for context
            
        Returns:
            Base prompt string for question generation
        """
        question_type = question_plan["type"]
        skill_name = question_plan["skill_name"]
        description = question_plan["description"]
        question_number = question_plan.get("question_number", 1)
        lo_question_count = question_plan.get("lo_question_count", 0)
        
        # Retrieve question history for variety enforcement
        quiz_id = question_plan.get("quiz_id", "current")
        previous_questions = self.question_history.get(quiz_id, [])
        
        prompt = f"""
        Generate a {question_type} question for the specific skill: "{skill_name}"
        
        SKILL CONTEXT:
        - Skill: {skill_name}
        - Description: {description}
        - Question #{question_number} in quiz (#{lo_question_count + 1} for this Learning Objective)
        
        VARIETY REQUIREMENTS:
        - This is question #{question_number} - ensure it's different from previous questions
        - Previous question types used: {[q.get('type') for q in previous_questions[-3:]]}
        - Avoid repetitive patterns
        - Make each question unique and engaging
        
        RELEVANT COURSE CONTENT:
        {content[:1200]}
        
        **STRATEGIC QUESTION DESIGN:**
        
        Question #{question_number} Strategy:
        {self._get_question_strategy(question_number, lo_question_count, skill_name)}
        
        **CODE INCLUSION GUIDELINES:**
        - Only include code if it directly tests "{skill_name}"
        - If including code, make it educational and well-formatted with ```python blocks
        - Vary code complexity based on skill level
        - For implementation skills: Show practical code examples
        - For conceptual skills: Focus on understanding, minimal code
        
        **QUESTION TYPE SPECIFIC REQUIREMENTS:**
        """
        
        # Add type-specific formatting requirements
        if question_type == "multiple_choice":
            prompt += """
MULTIPLE CHOICE FORMAT - Return JSON:
{
    "question": "Engaging question that varies in format and approach",
    "options": ["A) option1", "B) option2", "C) option3", "D) option4"],
    "correct_answer": "A",
    "explanation": "Clear explanation with reasoning"
}

VARIETY APPROACHES:
- Conceptual: "Which principle best explains..."
- Application: "In a real-world scenario involving..."
- Comparison: "What distinguishes X from Y..."
- Problem-solving: "Given this situation..."
- Analysis: "The following approach demonstrates..."
"""
        elif question_type == "true_false":
            prompt += """
TRUE/FALSE FORMAT - Return JSON:
{
    "question": "Clear, specific statement that can be definitively evaluated",
    "correct_answer": "True" or "False", 
    "explanation": "Detailed explanation of why the statement is true/false"
}

VARIETY APPROACHES:
- Definitional: "Machine learning model X is defined as..."
- Comparative: "Algorithm A is generally more effective than Algorithm B for..."
- Situational: "In time series analysis, technique X is always the best choice."
- Technical: "The following code implementation correctly demonstrates..."
"""
        elif question_type == "fill_in_blank":
            prompt += """
FILL IN THE BLANK FORMAT - Return JSON:
{
    "question": "Complete sentence with exactly one _____ blank",
    "correct_answer": "precise term or short phrase",
    "explanation": "Why this answer fits the context"
}

VARIETY APPROACHES:
- Technical terms: "The _____ algorithm is particularly effective for..."
- Method names: "In scikit-learn, the _____ method is used to..."
- Concepts: "The key principle behind this approach is _____"
- Parameters: "To optimize this model, you should set the _____ parameter to..."
"""
        else:  # open_ended
            prompt += """
OPEN-ENDED FORMAT - Return JSON:
{
    "question": "Thought-provoking question requiring detailed explanation",
    "sample_answer": "Comprehensive example answer (3-4 sentences)",
    "key_points": ["key_point_1", "key_point_2", "key_point_3"],
    "explanation": "What constitutes a good answer"
}

VARIETY APPROACHES:
- Analysis: "Analyze the trade-offs between..."
- Application: "Describe how you would apply X in scenario Y..."
- Evaluation: "Evaluate the effectiveness of approach X for..."
- Design: "Design a solution that addresses..."
- Comparison: "Compare and contrast methods X and Y..."
"""
        
        return prompt

    def _get_question_strategy(self, question_number: int, lo_question_count: int, skill_name: str) -> str:
        """
        Determine strategic approach for question generation.
        
        This method selects an appropriate questioning strategy based on
        the question's position in the sequence and the skill being assessed.
        
        Args:
            question_number: Overall question number in quiz
            lo_question_count: Question number within learning objective
            skill_name: Name of the skill being assessed
            
        Returns:
            Strategy description for question generation
        """
        skill_lower = skill_name.lower()
        
        strategies = [
            "Focus on conceptual understanding - test core principles",
            "Emphasize practical application - how is this used?",
            "Compare and contrast - how does this differ from alternatives?",
            "Problem-solving focus - given a scenario, what approach?",
            "Implementation details - technical specifics and methods"
        ]
        
        # Strategic selection based on position and content
        if lo_question_count == 0:
            if any(term in skill_lower for term in ['concept', 'definition', 'understanding']):
                return strategies[0]
            else:
                return strategies[1]
        elif lo_question_count == 1:
            return strategies[2]
        else:
            return strategies[(question_number % len(strategies))]

    def _track_question_for_variety(self, question_data: Dict, question_plan: Dict) -> None:
        """
        Track generated questions to ensure variety and prevent repetition.
        
        Args:
            question_data: Generated question information
            question_plan: Original question specifications
        """
        quiz_id = question_plan.get("quiz_id", "current")
        
        if quiz_id not in self.question_history:
            self.question_history[quiz_id] = []
        
        self.question_history[quiz_id].append({
            'type': question_data['type'],
            'skill': question_plan['skill_name'],
            'question_hash': hash(question_data['text'][:50]),
            'has_code': '```python' in question_data['text']
        })
        
        # Maintain memory efficiency
        if len(self.question_history[quiz_id]) > 10:
            self.question_history[quiz_id] = self.question_history[quiz_id][-10:]

    def _parse_generated_question(self, response_text: str, question_type: str) -> Optional[Dict[str, Any]]:
        """
        Parse and validate generated question from LLM response.
        
        This method extracts structured question data from the LLM's response,
        validates required fields, and formats the content appropriately.
        
        Args:
            response_text: Raw LLM response containing question
            question_type: Expected question type for validation
            
        Returns:
            Parsed question dictionary or None on parsing failure
        """
        try:
            # Extract JSON from response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                print(f"ERROR: No JSON found in response: {response_text[:200]}")
                return None
            
            json_str = response_text[start_idx:end_idx]
            question_data = json.loads(json_str)
            
            # Validate required fields
            if "question" not in question_data:
                print(f"ERROR: No question field in response")
                return None
            
            # Format and enhance question
            question_text = question_data["question"]
            question_text = self._format_code_blocks(question_text)
            
            # Standardize structure
            question_data["type"] = question_type
            question_data["text"] = question_text
            
            # Ensure correct_answer field consistency
            if question_type == "open_ended":
                question_data["correct_answer"] = question_data.get("sample_answer", "")
            
            # Add metadata
            question_data["generated_at"] = datetime.now().isoformat()
            question_data["content_hash"] = hash(question_text) % 10000
            
            return question_data
            
        except json.JSONDecodeError as e:
            print(f"ERROR: Failed to parse JSON: {e}")
            print(f"Response text: {response_text[:300]}")
            return None
        except Exception as e:
            print(f"ERROR: Failed to parse generated question: {e}")
            return None

    def _format_code_blocks(self, text: str) -> str:
        """
        Format code blocks for proper display in the interface.
        
        This method ensures code snippets are properly formatted with
        syntax highlighting markers for optimal presentation.
        
        Args:
            text: Raw text potentially containing code
            
        Returns:
            Text with properly formatted code blocks
        """
        if '```python' in text:
            return text
        
        lines = text.split('\n')
        formatted_lines = []
        in_code_block = False
        code_lines = []
        
        for line in lines:
            # Detect code patterns
            if any(indicator in line for indicator in [
                'import ', 'from ', 'def ', 'class ', '.fit(', '.predict(', 
                '= ', 'print(', 'sklearn', 'X_train', 'y_train'
            ]):
                if not in_code_block:
                    in_code_block = True
                    code_lines = [line]
                else:
                    code_lines.append(line)
            else:
                if in_code_block:
                    # End code block
                    if code_lines:
                        formatted_lines.append("```python")
                        formatted_lines.extend(code_lines)
                        formatted_lines.append("```")
                        code_lines = []
                    in_code_block = False
                formatted_lines.append(line)
        
        # Handle trailing code block
        if in_code_block and code_lines:
            formatted_lines.append("```python") 
            formatted_lines.extend(code_lines)
            formatted_lines.append("```")
        
        return '\n'.join(formatted_lines)

    def _select_variety_enforced_question_type(
        self, 
        go, 
        lo, 
        question_number: int, 
        lo_question_count: int, 
        motivation_state: str = None, 
        quiz_id: str = "default"
    ) -> str:
        """
        Select question type ensuring variety across the quiz.
        
        This method maintains balanced distribution of question types
        while considering the skill being assessed and learner motivation.
        
        Args:
            go: Granular objective being assessed
            lo: Learning objective context
            question_number: Overall question position
            lo_question_count: Position within learning objective
            motivation_state: Current learner motivation level
            quiz_id: Quiz identifier for tracking
            
        Returns:
            Selected question type string
        """
        # Retrieve current type distribution
        type_counts = self.quiz_type_tracker.get(quiz_id, {
            "multiple_choice": 0, 
            "true_false": 0, 
            "fill_in_blank": 0, 
            "open_ended": 0
        })
        total_questions = sum(type_counts.values())
        
        # Target distribution for balance
        target_distribution = {
            "multiple_choice": 0.4,
            "true_false": 0.2,
            "fill_in_blank": 0.2,
            "open_ended": 0.2
        }
        
        # Identify under-represented types
        available_types = []
        for qtype, target_ratio in target_distribution.items():
            current_ratio = type_counts[qtype] / max(1, total_questions)
            if current_ratio < target_ratio:
                available_types.append(qtype)
        
        # Ensure all types remain available
        if not available_types:
            available_types = list(target_distribution.keys())
        
        # Strategic selection based on skill content
        skill_name = go.skill_name.lower()
        
        if "concept" in skill_name or "definition" in skill_name:
            preferred_types = ["multiple_choice", "true_false"]
        elif "implement" in skill_name or "code" in skill_name:
            preferred_types = ["fill_in_blank", "multiple_choice"]
        elif "analyze" in skill_name or "compare" in skill_name:
            preferred_types = ["open_ended", "multiple_choice"]
        else:
            preferred_types = ["multiple_choice", "true_false"]
        
        # Select from available types with preference
        selected_type = None
        for pref_type in preferred_types:
            if pref_type in available_types:
                selected_type = pref_type
                break
        
        # Fallback to first available
        if not selected_type:
            selected_type = available_types[0]
        
        # Apply motivation-based adjustments
        if motivation_state == 'motivation_drop' and selected_type == "open_ended":
            alternative_types = [t for t in available_types if t != "open_ended"]
            if alternative_types:
                selected_type = alternative_types[0]
        elif motivation_state == 'maintained_high' and selected_type == "true_false":
            if "open_ended" in available_types:
                selected_type = "open_ended"
        
        # Update tracking
        type_counts[selected_type] += 1
        
        print(f"DEBUG: Q{question_number} - Selected type: {selected_type} (Available: {available_types})")
        print(f"DEBUG: Q{question_number} - Current distribution: {type_counts}")
        
        return selected_type


    def _evaluate_answer_with_motivation_context(
        self, 
        question: Dict[str, Any], 
        student_answer: str, 
        orchestrator_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate answer with motivation-aware adjustments.
        
        This method adapts evaluation feedback based on the learner's
        current motivation state, providing appropriate encouragement
        or challenge as needed.
        
        Args:
            question: Question data including correct answer
            student_answer: The learner's response
            orchestrator_context: Context containing motivation state
            
        Returns:
            Evaluation dictionary with motivation-adjusted feedback
        """
        # Perform base evaluation
        base_evaluation = self._evaluate_answer(question, student_answer)
        
        # Apply motivation-informed adjustments
        motivation_state = orchestrator_context.get('motivation_state', 'motivation_plateau')
        motivation_feedback = orchestrator_context.get('motivation_feedback', {})
        
        adjusted_evaluation = base_evaluation.copy()
        
        if motivation_state == 'motivation_drop':
            # Provide extra encouragement for low motivation
            if base_evaluation.get('correct', False):
                adjusted_evaluation['explanation'] = f"Excellent work! {base_evaluation.get('explanation', '')}"
            else:
                original_explanation = self._ensure_conversational_language(base_evaluation.get('explanation', ''))
                adjusted_evaluation['explanation'] = f"Good attempt! {original_explanation} Let's break this down step by step."
            
            # Provide slight score boost for effort
            if 'score' in adjusted_evaluation and adjusted_evaluation['score'] < 1.0:
                adjusted_evaluation['score'] = min(1.0, adjusted_evaluation['score'] + 0.1)
        
        elif motivation_state == 'maintained_high':
            # Provide challenge and detailed feedback for high motivation
            if base_evaluation.get('correct', False):
                adjusted_evaluation['explanation'] = f"Outstanding! {base_evaluation.get('explanation', '')} Ready for a more advanced perspective?"
            else:
                original_explanation = self._ensure_conversational_language(base_evaluation.get('explanation', ''))
                adjusted_evaluation['explanation'] = f"{original_explanation} What other approaches might you consider?"
        
        elif motivation_state == 'cold_start':
            # Provide welcoming support for new learners
            if base_evaluation.get('correct', False):
                adjusted_evaluation['explanation'] = f"Great start! {base_evaluation.get('explanation', '')}"
            else:
                original_explanation = self._ensure_conversational_language(base_evaluation.get('explanation', ''))
                adjusted_evaluation['explanation'] = f"Welcome to learning! {original_explanation} Don't worry - this is all part of the process."
        
        else:  # motivation_plateau
            # Maintain conversational tone
            adjusted_evaluation['explanation'] = self._ensure_conversational_language(base_evaluation.get('explanation', ''))
        
        # Add motivation metadata
        adjusted_evaluation['motivation_informed'] = True
        adjusted_evaluation['motivation_state'] = motivation_state
        adjusted_evaluation['original_score'] = base_evaluation.get('score', 0.0)
        
        return adjusted_evaluation
    #FIXED
    def _evaluate_answer(self, question: Dict[str, Any], student_answer: str) -> Dict[str, Any]:
        """FIXED: Evaluate student answer with proper handling for all question types"""
        
        try:
            question_type = question["type"]
            question_text = question["text"]
            correct_answer = question.get("correct_answer", "")
            
            print(f"DEBUG: Evaluating {question_type} question")
            print(f"DEBUG: Student answer: '{student_answer}'")
            print(f"DEBUG: Correct answer: '{correct_answer}'")
            
            # Create type-specific evaluation prompt
            if question_type == "multiple_choice":
                prompt = f"""
    Evaluate this multiple choice answer:
    
    Question: {question_text}
    Student Answer: {student_answer}
    Correct Answer: {correct_answer}
    
    Check if the student's answer matches the correct answer (consider A, B, C, D or the actual text).
    Be flexible with formatting (e.g., "A", "A)", "A.", "Option A" should all match "A").
    
    Return JSON: {{"correct": true/false, "score": 0.0-1.0, "explanation": "..."}}
    """
            
            elif question_type == "true_false":
                prompt = f"""
    Evaluate this true/false answer:
    
    Question: {question_text}
    Student Answer: {student_answer}
    Correct Answer: {correct_answer}
    
    Check if the student's answer matches the correct answer.
    Be flexible: "True", "T", "Yes", "Correct" should match "True"
    "False", "F", "No", "Incorrect" should match "False"
    
    Return JSON: {{"correct": true/false, "score": 0.0-1.0, "explanation": "..."}}
    """
            
            elif question_type == "fill_in_blank":
                prompt = f"""
    Evaluate this fill-in-the-blank answer:
    
    Question: {question_text}
    Student Answer: {student_answer}
    Correct Answer: {correct_answer}
    
    For fill-in-blank questions, be FLEXIBLE with the answer:
    - Accept synonyms and equivalent terms
    - Ignore case differences
    - Accept partial answers if they show understanding
    - For technical terms, accept common variations
    
    Examples of flexible matching:
    - "ML" should match "machine learning"
    - "classifier" should match "classification algorithm"  
    - "regression" should match "linear regression"
    
    If the student answer shows understanding of the concept, even if not exact, give partial credit.
    
    Return JSON: {{"correct": true/false, "score": 0.0-1.0, "explanation": "..."}}
    """
            
            else:  # open_ended
                key_points = question.get("key_points", [])
                sample_answer = question.get("sample_answer", "")
                
                prompt = f"""
    Evaluate this open-ended answer:
    
    Question: {question_text}
    Student Answer: {student_answer}
    Sample Answer: {sample_answer}
    Key Points to Look For: {key_points}
    
    For open-ended questions, evaluate based on:
    1. Conceptual understanding (do they grasp the main ideas?)
    2. Accuracy of information provided
    3. Completeness relative to the question complexity
    4. Quality of explanation
    
    Scoring guidelines:
    - 0.8-1.0: Excellent answer covering key concepts with good explanation
    - 0.6-0.8: Good answer with most key concepts but minor gaps
    - 0.4-0.6: Partial answer showing some understanding
    - 0.2-0.4: Minimal understanding, significant gaps
    - 0.0-0.2: Incorrect or no meaningful content
    
    Be encouraging but fair. Even short answers can get partial credit if they show understanding.
    
    Return JSON: {{"correct": true/false, "score": 0.0-1.0, "explanation": "...", "strengths": ["..."], "improvements": ["..."]}}
    """
    
            # Generate evaluation using OpenAI
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a fair and encouraging educational evaluator. Use conversational 'you' language."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            # Parse evaluation response
            eval_text = response.choices[0].message.content.strip()
            print(f"DEBUG: Raw evaluation response: {eval_text[:200]}...")
            
            # Extract JSON
            start_idx = eval_text.find('{')
            end_idx = eval_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                eval_json = eval_text[start_idx:end_idx]
                evaluation = json.loads(eval_json)
                
                # Validate and normalize evaluation
                if "correct" not in evaluation:
                    evaluation["correct"] = evaluation.get("score", 0) > 0.5
                if "score" not in evaluation:
                    evaluation["score"] = 1.0 if evaluation.get("correct") else 0.0
                if "explanation" not in evaluation:
                    evaluation["explanation"] = "Good effort!"
                
                # FIXED: Ensure scores are reasonable for each question type
                score = float(evaluation["score"])
                
                # Type-specific score adjustments for realism
                if question_type == "fill_in_blank":
                    # Fill-in-blank should have higher success rate with flexible matching
                    if score < 0.3 and len(student_answer.strip()) > 2:
                        score = 0.4  # Partial credit for trying
                        evaluation["correct"] = True
                        evaluation["explanation"] += " (Partial credit awarded)"
                
                elif question_type == "open_ended":
                    # Open-ended should give partial credit more liberally
                    if score < 0.2 and len(student_answer.strip()) > 10:
                        score = 0.3  # Partial credit for effort
                        evaluation["explanation"] += " (Credit for effort and engagement)"
                
                evaluation["score"] = score
                evaluation["correct"] = score > 0.5
                
                print(f"DEBUG: FIXED evaluation - Type: {question_type}, Score: {score:.2f}, Correct: {evaluation['correct']}")
                
                return evaluation
            else:
                print("ERROR: Could not parse evaluation JSON")
                # Fallback evaluation with type-specific handling
                if question_type in ["fill_in_blank", "open_ended"] and len(student_answer.strip()) > 2:
                    return {
                        "correct": True,
                        "score": 0.6,  # Give partial credit
                        "explanation": "I had trouble evaluating your answer, but you showed effort!"
                    }
                else:
                    return {
                        "correct": False,
                        "score": 0.0,
                        "explanation": "I had trouble evaluating your answer."
                    }
            
        except Exception as e:
            print(f"ERROR: Answer evaluation failed: {e}")
            # Generous fallback for debugging
            if len(student_answer.strip()) > 2:
                return {
                    "correct": True,
                    "score": 0.5,
                    "explanation": "Evaluation system had an issue, but you provided an answer!"
                }
            else:
                return {
                    "correct": False,
                    "score": 0.0,
                    "explanation": "No substantial answer provided."
                }

    def _ensure_conversational_language(self, explanation: str) -> str:
        """
        Ensure explanation uses conversational second-person language.
        
        This method converts any third-person references to second-person
        to maintain a personal, engaging tone in feedback.
        
        Args:
            explanation: Original explanation text
            
        Returns:
            Explanation with conversational language
        """
        if not explanation:
            return "Keep working on this concept!"
        
        conversational_explanation = explanation
        
        # Replace third-person patterns with second-person
        replacements = [
            ("the student", "you"),
            ("The student", "You"),
            ("student's", "your"),
            ("Student's", "Your"),
            ("the learner", "you"),
            ("The learner", "You"),
            ("learner's", "your"),
            ("Learner's", "Your"),
            ("they did not", "you did not"),
            ("They did not", "You did not"),
            ("they should", "you should"),
            ("They should", "You should"),
            ("their understanding", "your understanding"),
            ("Their understanding", "Your understanding"),
            ("their response", "your response"),
            ("Their response", "Your response")
        ]
        
        for old, new in replacements:
            conversational_explanation = conversational_explanation.replace(old, new)
        
        return conversational_explanation

    def submit_answer(self, quiz_data: Dict[str, Any], answer: str) -> Optional[Dict[str, Any]]:
        """
        Submit and evaluate a student answer with memory storage.
        
        This method processes answer submission, performs evaluation,
        stores the interaction for analytics, and updates the quiz session.
        
        Args:
            quiz_data: Current quiz session data
            answer: The learner's response
            
        Returns:
            Evaluation results or None on failure
        """
        try:
            current_question = quiz_data["current_question"]
            question_plan = quiz_data["question_plan"][quiz_data["current_question_index"]]
            
            # Retrieve orchestrator context for adaptive evaluation
            orchestrator_context = quiz_data.get('orchestrator_context')
            
            # Perform evaluation with optional motivation context
            if orchestrator_context:
                evaluation = self._evaluate_answer_with_motivation_context(
                    current_question, answer, orchestrator_context
                )
                print(f"DEBUG: 🎯 Motivation-aware answer evaluation complete")
            else:
                evaluation = self._evaluate_answer(current_question, answer)
            
            # Store interaction in memory system
            username = quiz_data.get("username", "unknown_user")
            store_quiz_memory(
                self.redis_client,
                username,
                current_question,
                answer,
                evaluation.get("correct", False),
                evaluation.get("score", 0.0)
            )
            
            # Record answer in session
            answer_record = {
                "question_index": quiz_data["current_question_index"],
                "go_id": question_plan["go_id"],
                "question": current_question["text"],
                "student_answer": answer,
                "correct_answer": current_question.get("correct_answer"),
                "evaluation": evaluation,
                "timestamp": datetime.now().isoformat(),
                "motivation_state": orchestrator_context.get('motivation_state') if orchestrator_context else None
            }
            
            quiz_data["answers"].append(answer_record)
            
            return evaluation
            
        except Exception as e:
            print(f"ERROR: Failed to submit answer: {e}")
            return None

    def get_quiz_session(self, quiz_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific quiz session by identifier.
        
        Args:
            quiz_id: Unique quiz session identifier
            
        Returns:
            Quiz session data or None if not found
        """
        return self.active_quizzes.get(quiz_id)

    def get_all_active_sessions(self) -> Dict[str, Dict[str, Any]]:
        """
        Retrieve all currently active quiz sessions.
        
        Returns:
            Dictionary of all active quiz sessions
        """
        return self.active_quizzes.copy()

    def close_quiz_session(self, quiz_id: str) -> bool:
        """
        Close and remove a quiz session from active tracking.
        
        Args:
            quiz_id: Unique quiz session identifier
            
        Returns:
            Boolean indicating successful closure
        """
        if quiz_id in self.active_quizzes:
            del self.active_quizzes[quiz_id]
            return True
        return False
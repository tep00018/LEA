"""
Simple Tutor System for LEA
Provides guided tutoring through learning objectives with adaptive scaffolding
UPDATED: Integrates sophisticated scaffolding engine (conceptual, procedural, strategic, metacognitive)
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import random
import asyncio

logger = logging.getLogger(__name__)

class ScaffoldingLevel(Enum):
    """Scaffolding intensity levels"""
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium" 
    LOW = "low"
    MINIMAL = "minimal"

class ScaffoldingStrategy(Enum):
    """Scaffolding strategies from engine"""
    CONCEPTUAL = "conceptual"
    PROCEDURAL = "procedural"
    STRATEGIC = "strategic"
    METACOGNITIVE = "metacognitive"

@dataclass
class TutorSession:
    """Represents a tutoring session"""
    session_id: str
    username: str
    course: str
    week: int
    go_list: List[Dict[str, Any]]
    current_go_index: int = 0
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    
    # UPDATED: Track both strategy and intensity
    scaffolding_strategy: str = "procedural"  # Default strategy
    scaffolding_intensity: str = "medium"     # Default intensity
    scaffolding_level: str = "medium"         # Keep for backwards compatibility
    
    correct_count: int = 0
    incorrect_count: int = 0
    consecutive_correct: int = 0
    consecutive_incorrect: int = 0
    interaction_count: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    mastery_scores: Dict[str, float] = field(default_factory=dict)
    current_mastery: float = 0.0
    requires_review: bool = False
    review_concepts: List[str] = field(default_factory=list)

class SimpleTutorSystem:
    """Simple tutor system with adaptive scaffolding and GO-based progression"""
    
    def __init__(self, openai_client, redis_client=None, mcp_client=None):
        """Initialize tutor system
        
        Args:
            openai_client: OpenAI client for generating responses
            redis_client: Optional Redis client for caching
            mcp_client: Optional MCP client for YouTube/tool integration
        """
        self.openai_client = openai_client
        self.redis_client = redis_client
        self.mcp_client = mcp_client
        self.sessions = {}
        
        # UPDATED: Strategy-specific scaffolding templates
        self.scaffolding_templates = {
            'conceptual': {
                'focus': "Understanding core concepts and relationships",
                'intro': "Let's explore the fundamental concepts behind this.",
                'hint': "Think about the underlying principle: ",
                'example': "Here's a conceptual model: ",
                'check': "How do these concepts relate? ",
                'feedback_style': "Focus on WHY and HOW things work",
                'prompt_guidance': "Use analogies, concept maps, and explain relationships between ideas"
            },
            'procedural': {
                'focus': "Step-by-step problem solving processes",
                'intro': "Let me walk you through this step by step.",
                'hint': "The next step is: ",
                'example': "Here's a worked example: ",
                'check': "Can you complete the next step? ",
                'feedback_style': "Focus on WHAT to do NEXT",
                'prompt_guidance': "Provide clear sequential steps, worked examples, and procedural guidance"
            },
            'strategic': {
                'focus': "Problem-solving strategies and approaches",
                'intro': "Let's think about different approaches to this.",
                'hint': "Consider this strategy: ",
                'example': "You could approach it like: ",
                'check': "Which approach would work best here? ",
                'feedback_style': "Focus on evaluating different approaches",
                'prompt_guidance': "Compare strategies, discuss trade-offs, help choose best approach"
            },
            'metacognitive': {
                'focus': "Self-reflection and learning awareness",
                'intro': "Let's reflect on your learning process.",
                'hint': "Think about your thinking: ",
                'example': "Reflect on how you approached this: ",
                'check': "What's your confidence level and why? ",
                'feedback_style': "Focus on the learning process itself",
                'prompt_guidance': "Encourage self-reflection, confidence assessment, learning strategy evaluation"
            }
        }
        
        # Intensity modifiers for prompts
        self.intensity_modifiers = {
            'very_high': "Provide maximum support with detailed explanations, multiple examples, and break everything into tiny steps",
            'high': "Give substantial support with clear explanations and examples",
            'medium': "Balance support with independent thinking opportunities",
            'low': "Provide minimal hints and encourage independent problem-solving",
            'minimal': "Only intervene when absolutely necessary"
        }
        
        logger.info(f"SimpleTutorSystem initialized with MCP client: {mcp_client is not None}")
        
    def start_tutoring_session(
        self,
        course: str,
        week: int,
        username: str,
        kc_loader,
        go_list: List[Dict[str, Any]],
        orchestrator_context: Optional[Dict] = None
    ) -> TutorSession:
        """Start a new tutoring session with GO-based progression"""
        
        session_id = f"tutor_{username}_{course}_{week}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Initialize session
        session = TutorSession(
            session_id=session_id,
            username=username,
            course=course,
            week=week,
            go_list=go_list
        )
        
        # UPDATED: Apply initial scaffolding from orchestrator if available
        if orchestrator_context and 'scaffolding_strategy' in orchestrator_context:
            self._apply_scaffolding_decision(session, orchestrator_context['scaffolding_strategy'])
        
        # Initialize mastery scores for each GO
        for go in go_list:
            go_id = go.get('go_id', f'GO_{len(session.mastery_scores)}')
            session.mastery_scores[go_id] = 0.0
        
        # Check for adaptive start based on prior mastery
        if self.redis_client:
            session = self._check_prior_mastery(session)
        
        # Generate initial message
        initial_message = self._generate_initial_message(session, orchestrator_context)
        
        session.conversation_history.append({
            "role": "tutor",
            "content": initial_message,
            "timestamp": datetime.now().isoformat(),
            "go_id": session.go_list[0].get('go_id') if session.go_list else None,
            "scaffolding_strategy": session.scaffolding_strategy,
            "scaffolding_intensity": session.scaffolding_intensity
        })
        
        self.sessions[session_id] = session
        
        logger.info(f"Started tutoring session {session_id} for {username} with {len(go_list)} GOs")
        logger.info(f"Initial scaffolding: {session.scaffolding_strategy} at {session.scaffolding_intensity} intensity")
        return session
        
    def process_student_response(
        self,
        session: TutorSession,
        student_input: str,
        rag_content: Optional[str] = None,
        orchestrator_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Process student response with enhanced evaluation and adaptive response generation"""
        
        try:
            session.interaction_count += 1
            current_go = session.go_list[session.current_go_index]
            go_id = current_go.get('go_id', f'GO_{session.current_go_index}')
            
            # Add student response to history
            session.conversation_history.append({
                "role": "student",
                "content": student_input,
                "timestamp": datetime.now().isoformat(),
                "go_id": go_id
            })
            
            # Enhanced evaluation with mastery tracking
            is_correct, mastery_score, evaluation_details = self._evaluate_response_enhanced(
                student_input, 
                current_go,
                session
            )
            
            # Update mastery for current GO
            session.mastery_scores[go_id] = mastery_score
            session.current_mastery = mastery_score
            
            # Update session tracking
            if is_correct:
                session.correct_count += 1
                session.consecutive_correct += 1
                session.consecutive_incorrect = 0
            else:
                session.incorrect_count += 1
                session.consecutive_incorrect += 1
                session.consecutive_correct = 0
                
                # Track concepts that need review
                if session.consecutive_incorrect >= 2:
                    session.requires_review = True
                    if go_id not in session.review_concepts:
                        session.review_concepts.append(go_id)
            
            logger.debug(f"Evaluation: Correct={is_correct}, Mastery={mastery_score:.2f}, "
                        f"Consecutive incorrect={session.consecutive_incorrect}")
            
            # UPDATED: Apply scaffolding from orchestrator
            if orchestrator_context and 'scaffolding_strategy' in orchestrator_context:
                self._apply_scaffolding_decision(session, orchestrator_context['scaffolding_strategy'])
                logger.info(f"Applied orchestrator scaffolding: {session.scaffolding_strategy} "
                           f"at {session.scaffolding_intensity} intensity")
            
            # Check if we should show YouTube help (3 consecutive incorrect)
            youtube_content = None
            if session.consecutive_incorrect >= 3:
                logger.info(f"🎥 YouTube TRIGGERED: {session.consecutive_incorrect} consecutive incorrect")
                if self.mcp_client:
                    youtube_content = self._get_youtube_help(session)
            
            # Generate adaptive tutor response
            tutor_message = self._generate_adaptive_response(
                session=session,
                student_input=student_input,
                is_correct=is_correct,
                mastery_score=mastery_score,
                evaluation_details=evaluation_details,
                rag_content=rag_content,
                orchestrator_context=orchestrator_context,
                youtube_content=youtube_content
            )
            
            # Add tutor response to history
            session.conversation_history.append({
                "role": "tutor",
                "content": tutor_message,
                "timestamp": datetime.now().isoformat(),
                "go_id": go_id,
                "scaffolding_strategy": session.scaffolding_strategy,
                "scaffolding_intensity": session.scaffolding_intensity,
                "scaffolding_level": session.scaffolding_intensity  # For backwards compatibility
            })
            
            # Check progression conditions
            has_achieved_mastery = mastery_score >= 0.8
            should_advance = has_achieved_mastery or (
                session.interaction_count > 5 and mastery_score >= 0.6
            )
            
            # Handle GO progression
            session_complete = False
            next_go_info = None
            
            if should_advance:
                session.current_go_index += 1
                session.consecutive_correct = 0
                session.consecutive_incorrect = 0
                
                if session.current_go_index >= len(session.go_list):
                    session_complete = True
                else:
                    next_go_info = session.go_list[session.current_go_index]
                    logger.info(f"Advancing to GO {session.current_go_index + 1}/{len(session.go_list)}")
            
            return {
                'message': tutor_message,
                'is_correct': is_correct,
                'mastery_score': mastery_score,
                'has_achieved_mastery': has_achieved_mastery,
                'session_complete': session_complete,
                'scaffolding_level': session.scaffolding_intensity,  # For backwards compatibility
                'scaffolding_strategy': session.scaffolding_strategy,  # NEW
                'scaffolding_intensity': session.scaffolding_intensity,  # NEW
                'current_go': go_id,
                'next_go': next_go_info,
                'requires_review': session.requires_review,
                'orchestrator_applied': orchestrator_context is not None,
                'youtube_shown': youtube_content is not None,
                'progress': {
                    'current': session.current_go_index + 1,
                    'total': len(session.go_list),
                    'percentage': ((session.current_go_index + 1) / len(session.go_list)) * 100
                }
            }
            
        except Exception as e:
            logger.error(f"Error processing student response: {e}", exc_info=True)
            return self._get_error_response(session)

    def _apply_scaffolding_decision(self, session: TutorSession, scaffolding_strategy: Dict[str, Any]):
        """Apply scaffolding decision from orchestrator/engine"""
        
        # Handle both ScaffoldingDecision objects and dict responses
        if hasattr(scaffolding_strategy, 'strategy_type'):
            # ScaffoldingDecision object
            session.scaffolding_strategy = scaffolding_strategy.strategy_type
            session.scaffolding_intensity = scaffolding_strategy.intensity_level
            session.scaffolding_level = scaffolding_strategy.intensity_level  # Backwards compatibility
            
        elif isinstance(scaffolding_strategy, dict):
            # Dictionary response
            session.scaffolding_strategy = scaffolding_strategy.get('strategy_type', 'procedural')
            session.scaffolding_intensity = scaffolding_strategy.get('intensity_level', 'medium')
            session.scaffolding_level = scaffolding_strategy.get('intensity_level', 'medium')
            
            # Also check for alternative key names
            if 'intervention_type' in scaffolding_strategy and 'strategy_type' not in scaffolding_strategy:
                # Map intervention types to strategies
                intervention_map = {
                    'concept_review': 'conceptual',
                    'maintain_flow': 'procedural',
                    'increase_support': 'procedural',
                    'reduce_support': 'strategic',
                    'metacognitive_prompt': 'metacognitive'
                }
                intervention = scaffolding_strategy.get('intervention_type', 'maintain_flow')
                session.scaffolding_strategy = intervention_map.get(intervention, 'procedural')
        
        logger.debug(f"Applied scaffolding: {session.scaffolding_strategy} at {session.scaffolding_intensity}")

    def _generate_adaptive_response(
        self,
        session: TutorSession,
        student_input: str,
        is_correct: bool,
        mastery_score: float,
        evaluation_details: Dict,
        rag_content: Optional[str] = None,
        orchestrator_context: Optional[Dict] = None,
        youtube_content: Optional[str] = None
    ) -> str:
        """Generate adaptive tutor response using strategy-specific scaffolding"""
        
        current_go = session.go_list[session.current_go_index]
        skill_name = current_go.get('skill_name', 'this concept')
        description = current_go.get('description', '')
        
        # Get strategy-specific templates
        strategy_template = self.scaffolding_templates.get(
            session.scaffolding_strategy, 
            self.scaffolding_templates['procedural']
        )
        
        # Get intensity modifier
        intensity_modifier = self.intensity_modifiers.get(
            session.scaffolding_intensity,
            self.intensity_modifiers['medium']
        )
        
        # Build context-aware prompt
        system_prompt = f"""You are LEA, a supportive AI tutor helping a student learn {skill_name}.

SCAFFOLDING STRATEGY: {session.scaffolding_strategy.upper()}
Focus: {strategy_template['focus']}
Feedback Style: {strategy_template['feedback_style']}
Guidance: {strategy_template['prompt_guidance']}

INTENSITY LEVEL: {session.scaffolding_intensity.upper()}
{intensity_modifier}

CRITICAL RULES:
1. Apply the {session.scaffolding_strategy} scaffolding strategy consistently
2. Match the {session.scaffolding_intensity} intensity level
3. NEVER use false praise for incorrect answers
4. Be direct, clear, and educational without being harsh
5. For incorrect answers: acknowledge difficulty, provide correct information, explain clearly

Current Status:
- Concept: {skill_name}
- Description: {description}
- Student answered: {"correctly ✓" if is_correct else "incorrectly ✗"} 
- Mastery level: {mastery_score:.1%}
- Consecutive incorrect: {session.consecutive_incorrect}
- Interaction count: {session.interaction_count}

{f"Course content available: {rag_content[:500]}" if rag_content else ""}
"""
        
        # Generate strategy-specific user prompt
        if is_correct:
            user_prompt = self._get_correct_response_prompt_with_strategy(
                student_input, mastery_score, skill_name, session, strategy_template
            )
        else:
            user_prompt = self._get_incorrect_response_prompt_with_strategy(
                student_input, skill_name, evaluation_details, session, strategy_template
            )
        
        # Add YouTube content if available
        if youtube_content:
            user_prompt += f"\n\nINCLUDE these helpful video resources:\n{youtube_content}"
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            tutor_message = response.choices[0].message.content.strip()
            
            # Ensure YouTube videos are included if available
            if youtube_content and "Video Resources" not in tutor_message:
                tutor_message += youtube_content
            
            logger.debug(f"Generated {session.scaffolding_strategy} response at {session.scaffolding_intensity} intensity")
            return tutor_message
            
        except Exception as e:
            logger.error(f"Error generating tutor response: {e}")
            return self._get_fallback_response(is_correct, skill_name, youtube_content)
    
    def _get_incorrect_response_prompt_with_strategy(
        self, 
        student_input: str, 
        skill_name: str, 
        evaluation_details: Dict,
        session: TutorSession,
        strategy_template: Dict
    ) -> str:
        """Generate strategy-specific prompt for incorrect responses"""
        
        # Check for "I don't know" type responses
        unknown_responses = ["i don't know", "idk", "no idea", "not sure", "don't know", "unsure"]
        is_unknown = any(resp in student_input.lower() for resp in unknown_responses)
        
        base_prompt = f"""The student said: "{student_input}"
Strategy to apply: {session.scaffolding_strategy}
Intensity: {session.scaffolding_intensity}"""
        
        if session.scaffolding_strategy == "conceptual":
            if is_unknown:
                return base_prompt + f"""
They don't know. Build conceptual understanding:
1. Start with: "{strategy_template['intro']}"
2. Explain the core concept using an analogy
3. Show how concepts relate to each other
4. Use: "{strategy_template['example']}" to provide a conceptual model
5. End with: "{strategy_template['check']}" """
            else:
                return base_prompt + f"""
Incorrect answer. Focus on conceptual understanding:
1. Identify the conceptual misunderstanding
2. Use: "{strategy_template['hint']}" to guide toward the principle
3. Explain WHY this concept works this way
4. Connect to related concepts they might know
5. Check understanding of relationships"""
                
        elif session.scaffolding_strategy == "procedural":
            if is_unknown:
                return base_prompt + f"""
They don't know. Provide step-by-step guidance:
1. Start with: "{strategy_template['intro']}"
2. Break down into clear sequential steps
3. Use: "{strategy_template['example']}" to show a worked example
4. Walk through each step explicitly
5. Ask them to try the first step"""
            else:
                return base_prompt + f"""
Incorrect answer. Provide procedural support:
1. Identify which step went wrong
2. Use: "{strategy_template['hint']}" for the next step
3. Show the correct procedure step-by-step
4. Provide a similar worked example
5. Guide them through trying again"""
                
        elif session.scaffolding_strategy == "strategic":
            return base_prompt + f"""
Focus on problem-solving strategies:
1. Start with: "{strategy_template['intro']}"
2. Present 2-3 different approaches to this problem
3. Use: "{strategy_template['hint']}" to suggest a strategy
4. Compare pros/cons of each approach
5. Ask: "{strategy_template['check']}" """
            
        else:  # metacognitive
            return base_prompt + f"""
Focus on learning reflection:
1. Start with: "{strategy_template['intro']}"
2. Ask them to reflect on their thinking process
3. Use: "{strategy_template['hint']}" about their approach
4. Help them identify where confusion arose
5. Ask: "{strategy_template['check']}" about confidence"""
    
    def _get_correct_response_prompt_with_strategy(
        self, 
        student_input: str, 
        mastery_score: float, 
        skill_name: str,
        session: TutorSession,
        strategy_template: Dict
    ) -> str:
        """Generate strategy-specific prompt for correct responses"""
        
        base_prompt = f"""The student correctly answered: "{student_input}"
Strategy to apply: {session.scaffolding_strategy}
Intensity: {session.scaffolding_intensity}"""
        
        if session.scaffolding_strategy == "conceptual":
            return base_prompt + f"""
Correct! Deepen conceptual understanding:
1. Praise their conceptual grasp
2. Connect this concept to broader principles
3. Ask how this relates to other concepts
4. Extend to more complex relationships"""
            
        elif session.scaffolding_strategy == "procedural":
            return base_prompt + f"""
Correct! Reinforce procedural mastery:
1. Confirm the correct procedure
2. Highlight which steps were done well
3. Suggest a slightly harder variation
4. Ask them to explain the process"""
            
        elif session.scaffolding_strategy == "strategic":
            return base_prompt + f"""
Correct! Explore strategic thinking:
1. Praise their problem-solving approach
2. Ask why they chose this strategy
3. Discuss alternative approaches
4. Challenge with a variant requiring strategy selection"""
            
        else:  # metacognitive
            return base_prompt + f"""
Correct! Promote metacognitive awareness:
1. Ask them to reflect on how they knew
2. Explore their confidence level
3. Discuss what made this click
4. Connect to their learning journey"""

    # Keep all other methods unchanged
    def _get_youtube_help(self, session: TutorSession) -> Optional[str]:
        """Get YouTube video help via MCP client (Streamlit-compatible)"""
        # [Keep existing implementation]
        try:
            if not self.mcp_client:
                logger.debug("No MCP client available for YouTube")
                return None
            
            current_go = session.go_list[session.current_go_index]
            skill_name = current_go.get('skill_name', '')
            keywords = current_go.get('content_keywords', [])
            
            # Build search query
            search_terms = [skill_name] + keywords[:2] if keywords else [skill_name]
            search_query = f"{' '.join(search_terms)} tutorial for beginners"
            logger.info(f"🎥 Requesting YouTube videos for: {search_query}")
            
            # Synchronous wrapper for async MCP call
            import nest_asyncio
            nest_asyncio.apply()  # Allow nested event loops for Streamlit
            
            async def get_videos():
                try:
                    result = await self.mcp_client.call_tool(
                        "youtube_search",
                        {
                            "query": search_query,
                            "max_results": 3
                        }
                    )
                    return result
                except Exception as e:
                    logger.error(f"YouTube API call failed: {e}")
                    return None
            
            # Handle async in Streamlit-compatible way
            try:
                import asyncio
                
                # Try to get existing loop
                try:
                    loop = asyncio.get_running_loop()
                    # Create task in existing loop
                    task = asyncio.create_task(get_videos())
                    # Wait for completion using asyncio.wait_for with timeout
                    result = asyncio.run_until_complete(asyncio.wait_for(task, timeout=10))
                except RuntimeError:
                    # No running loop, create new one
                    result = asyncio.run(get_videos())
                    
            except Exception as e:
                logger.error(f"Async execution failed, trying thread executor: {e}")
                
                # Fallback: Use thread executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, get_videos())
                    result = future.result(timeout=10)
            
            # Process results
            if result and result.get('success') and result.get('videos'):
                videos = result['videos']
                
                # Format video recommendations
                video_text = "\n\n📹 **Video Resources to Help You:**\n"
                for i, video in enumerate(videos[:3], 1):
                    video_text += f"{i}. [{video['title']}]({video['url']})\n"
                    if video.get('duration'):
                        video_text += f"   Duration: {video['duration']}\n"
                
                logger.info(f"✅ Retrieved {len(videos)} YouTube videos")
                return video_text
            else:
                logger.warning(f"YouTube search returned no videos: {result}")
                
                # Fallback: Return hardcoded educational videos for the topic
                fallback_text = self._get_fallback_youtube_links(skill_name)
                if fallback_text:
                    logger.info("Using fallback YouTube links")
                    return fallback_text
                
                return None
                
        except Exception as e:
            logger.error(f"YouTube help retrieval failed: {e}", exc_info=True)
            
            # Last resort: Return generic help message
            return self._get_fallback_youtube_links(current_go.get('skill_name', 'AI concepts'))
    
    def _get_fallback_youtube_links(self, topic: str) -> str:
        """Provide fallback YouTube links when API fails"""
        # [Keep existing implementation]
        fallback_links = {
            "AI": [
                ("IBM Technology - What is AI?", "https://www.youtube.com/results?search_query=IBM+Technology+What+is+AI"),
                ("MIT OpenCourseWare - AI Basics", "https://www.youtube.com/results?search_query=MIT+OpenCourseWare+artificial+intelligence+basics"),
                ("CrashCourse - AI Explained", "https://www.youtube.com/results?search_query=CrashCourse+Computer+Science+AI")
            ],
            "default": [
                (f"Search: {topic} tutorial", f"https://www.youtube.com/results?search_query={topic.replace(' ', '+')}+tutorial+for+beginners"),
                (f"Search: {topic} explained", f"https://www.youtube.com/results?search_query={topic.replace(' ', '+')}+explained+simply"),
                (f"Search: Learn {topic}", f"https://www.youtube.com/results?search_query=learn+{topic.replace(' ', '+')}+basics")
            ]
        }
        
        # Determine which links to use
        if "AI" in topic or "artificial" in topic.lower() or "intelligence" in topic.lower():
            links = fallback_links["AI"]
        else:
            links = fallback_links["default"]
        
        # Format as video links
        video_text = "\n\n📹 **Video Resources to Help You:**\n"
        for i, (title, url) in enumerate(links, 1):
            video_text += f"{i}. [{title}]({url})\n"
        
        return video_text
    
    def _evaluate_response_enhanced(
        self, 
        student_input: str, 
        current_go: Dict,
        session: TutorSession
    ) -> Tuple[bool, float, Dict]:
        """Enhanced response evaluation with detailed feedback"""
        # [Keep existing implementation]
        skill_name = current_go.get('skill_name', '')
        description = current_go.get('description', '')
        keywords = current_go.get('content_keywords', [])
        
        evaluation_details = {
            'matched_keywords': [],
            'missing_concepts': [],
            'understanding_level': 'none'
        }
        
        # Handle "I don't know" type responses
        unknown_responses = ["i don't know", "idk", "no idea", "not sure", "don't know", "unsure"]
        if any(resp in student_input.lower() for resp in unknown_responses):
            logger.debug(f"Evaluating response for mastery: '{student_input}'")
            base_score = 0.4
            logger.debug(f"Evaluation breakdown - Base: {base_score:.2f}, Concepts: 0.00, Final: {base_score:.2f}")
            evaluation_details['understanding_level'] = 'none'
            return False, base_score, evaluation_details
        
        # Keyword matching with weighting
        matched_keywords = []
        for keyword in keywords:
            if keyword.lower() in student_input.lower():
                matched_keywords.append(keyword)
        
        evaluation_details['matched_keywords'] = matched_keywords
        keyword_ratio = len(matched_keywords) / len(keywords) if keywords else 0.0
        
        # Identify missing concepts
        missing = [kw for kw in keywords if kw not in matched_keywords]
        evaluation_details['missing_concepts'] = missing[:3]  # Top 3 missing
        
        # Length and complexity analysis
        word_count = len(student_input.split())
        has_explanation = word_count > 10
        uses_examples = any(phrase in student_input.lower() for phrase in ['for example', 'such as', 'like'])
        
        # Calculate mastery score with multiple factors
        mastery_score = 0.3  # Base score
        mastery_score += keyword_ratio * 0.4  # Keyword understanding
        mastery_score += 0.15 if has_explanation else 0.0  # Explanation quality
        mastery_score += 0.1 if uses_examples else 0.0  # Example usage
        mastery_score += 0.05 * min(word_count / 50, 1)  # Thoroughness
        
        # Determine understanding level
        if mastery_score >= 0.8:
            evaluation_details['understanding_level'] = 'mastery'
        elif mastery_score >= 0.6:
            evaluation_details['understanding_level'] = 'developing'
        elif mastery_score >= 0.4:
            evaluation_details['understanding_level'] = 'basic'
        else:
            evaluation_details['understanding_level'] = 'minimal'
        
        is_correct = mastery_score >= 0.6
        
        logger.debug(f"Enhanced evaluation - Correct: {is_correct}, Mastery: {mastery_score:.2f}, "
                    f"Keywords: {len(matched_keywords)}/{len(keywords)}")
        
        return is_correct, mastery_score, evaluation_details
    
    def _generate_initial_message(self, session: TutorSession, orchestrator_context: Optional[Dict] = None) -> str:
        """Generate initial tutoring message"""
        # [Keep existing implementation]
        if not session.go_list:
            return "Let's begin our tutoring session. What would you like to learn about?"
        
        first_go = session.go_list[0]
        skill_name = first_go.get('skill_name', 'our first concept')
        description = first_go.get('description', '')
        
        # Check for orchestrator context
        motivation_level = "standard"
        if orchestrator_context and 'motivation_state' in orchestrator_context:
            motivation_level = orchestrator_context.get('motivation_state', 'standard')
        
        # Adaptive greeting based on context
        if motivation_level == 'cold_start':
            greeting = "Welcome! I'm LEA, and I'm here to help you learn at your own pace."
        elif motivation_level == 'maintained_high':
            greeting = "Great to see you! You've been doing excellent work."
        else:
            greeting = "Hi! I'm LEA, your AI tutor."
        
        return f"""{greeting} Today we'll work through {len(session.go_list)} concepts in {session.course}, Week {session.week}.

Let's start with: **{skill_name}**

{description}

Can you tell me what you already know about {skill_name}? Even if you're not sure, any thoughts you have will help me understand where to begin."""
    
    def _check_prior_mastery(self, session: TutorSession) -> TutorSession:
        """Check prior mastery and adjust starting point if needed"""
        # [Keep existing implementation]
        if not self.redis_client:
            return session
        
        try:
            # Get prior mastery data
            mastery_key = f"mastery:{session.username}:{session.course}"
            mastery_data = self.redis_client.get(mastery_key)
            
            if mastery_data:
                mastery_info = json.loads(mastery_data)
                
                # Check mastery for each GO
                for i, go in enumerate(session.go_list):
                    go_id = go.get('go_id')
                    if go_id and go_id in mastery_info.get('go_masteries', {}):
                        prior_mastery = mastery_info['go_masteries'][go_id]
                        session.mastery_scores[go_id] = prior_mastery
                        
                        # Skip if already mastered
                        if prior_mastery >= 0.8:
                            logger.info(f"Skipping mastered GO: {go_id} (mastery: {prior_mastery:.2f})")
                            session.current_go_index = i + 1
                
                # Ensure we don't go past the end
                if session.current_go_index >= len(session.go_list):
                    session.current_go_index = 0  # Start from beginning if all mastered
                    
        except Exception as e:
            logger.error(f"Error checking prior mastery: {e}")
        
        return session
    
    def _get_fallback_response(self, is_correct: bool, skill_name: str, youtube_content: Optional[str] = None) -> str:
        """Generate fallback response when API fails"""
        # [Keep existing implementation]
        if is_correct:
            response = f"That's correct! You understand {skill_name}. Let's continue building on this knowledge."
        else:
            response = f"Let me help clarify {skill_name}. This concept involves understanding the key principles and how to apply them."
        
        if youtube_content:
            response += youtube_content
        
        return response
    
    def _get_error_response(self, session: TutorSession) -> Dict[str, Any]:
        """Generate error response"""
        # [Keep existing implementation]
        return {
            'message': "I encountered an error processing your response. Let's continue with the current concept.",
            'is_correct': False,
            'mastery_score': 0.0,
            'has_achieved_mastery': False,
            'session_complete': False,
            'scaffolding_level': session.scaffolding_intensity,
            'scaffolding_strategy': session.scaffolding_strategy,
            'scaffolding_intensity': session.scaffolding_intensity,
            'orchestrator_applied': False
        }
    
    def get_session_summary(self, session: TutorSession) -> Dict[str, Any]:
        """Get comprehensive session summary"""
        # [Keep existing implementation with strategy info]
        total_gos = len(session.go_list)
        completed_gos = session.current_go_index
        mastered_gos = sum(1 for score in session.mastery_scores.values() if score >= 0.8)
        
        accuracy = session.correct_count / max(session.interaction_count, 1)
        average_mastery = sum(session.mastery_scores.values()) / len(session.mastery_scores) if session.mastery_scores else 0
        
        return {
            'session_id': session.session_id,
            'username': session.username,
            'course': session.course,
            'week': session.week,
            'total_gos': total_gos,
            'gos_completed': completed_gos,
            'gos_mastered': mastered_gos,
            'accuracy': accuracy,
            'average_mastery': average_mastery,
            'correct_count': session.correct_count,
            'incorrect_count': session.incorrect_count,
            'interaction_count': session.interaction_count,
            'scaffolding_strategy': session.scaffolding_strategy,
            'scaffolding_intensity': session.scaffolding_intensity,
            'requires_review': session.requires_review,
            'review_concepts': session.review_concepts,
            'duration': (datetime.now() - session.start_time).total_seconds()
        }
    
    def get_progress_report(self, username: str, course: str) -> Dict[str, Any]:
        """Generate progress report for a user"""
        # [Keep existing implementation]
        # Find all sessions for this user/course
        user_sessions = [s for s in self.sessions.values() 
                        if s.username == username and s.course == course]
        
        if not user_sessions:
            return {'message': 'No tutoring sessions found'}
        
        total_time = sum((datetime.now() - s.start_time).total_seconds() for s in user_sessions)
        total_gos = sum(len(s.go_list) for s in user_sessions)
        mastered_gos = sum(sum(1 for score in s.mastery_scores.values() if score >= 0.8) 
                          for s in user_sessions)
        
        return {
            'total_sessions': len(user_sessions),
            'total_time_hours': total_time / 3600,
            'total_gos_attempted': total_gos,
            'total_gos_mastered': mastered_gos,
            'mastery_rate': mastered_gos / total_gos if total_gos > 0 else 0,
            'sessions': [self.get_session_summary(s) for s in user_sessions[-5:]]  # Last 5 sessions
        }
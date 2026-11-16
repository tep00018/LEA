# File: src/tutor/conversation_templates.py
"""
Conversation Templates and Peer Phrases for LEA Tutor System
Provides scaffolding-appropriate conversation patterns and peer-like language
"""

import random
from typing import Dict, List

class ConversationTemplates:
    """Manages conversation templates and peer-like phrases for tutoring"""
    
    def __init__(self):
        self.templates = self._load_templates()
        self.peer_phrases = self._load_peer_phrases()
        self.transition_phrases = self._load_transition_phrases()
    
    def _load_templates(self) -> Dict:
        """Load conversation templates organized by scaffolding level and situation"""
        return {
            "high": {
                "initial": [
                    "Hey! Let's explore {skill_name} together. I'll start us off with some background: {context}. What catches your attention here?",
                    "Hi there! Ready to dive into {skill_name}? Let me give you some context first: {context}. What questions come to mind?",
                    "Let's work through {skill_name} step by step! Here's what I know: {context}. What part would you like to understand better?"
                ],
                "question": [
                    "Let me break this down for you. {explanation} Now, {simple_question}",
                    "Here's how I think about it: {explanation}. Given that, {simple_question}",
                    "Let's start with the basics: {explanation}. So, {simple_question}"
                ],
                "correct": [
                    "Yes! Exactly right! {encouragement} You're really getting this. Let's try: {next_question}",
                    "Perfect! {encouragement} That shows you understand the concept. Now: {next_question}",
                    "Spot on! {encouragement} You've got the hang of this. Ready for: {next_question}"
                ],
                "incorrect": [
                    "I can see your thinking! {gentle_explanation} Let me give you a hint: {detailed_hint}. What do you think now?",
                    "That's a thoughtful answer! {gentle_explanation} Here's another way to look at it: {detailed_hint}. Want to try again?",
                    "Good reasoning! {gentle_explanation} Let me help you along: {detailed_hint}. How does that sound?"
                ],
                "hint": [
                    "Here's a way to think about it: {step_by_step_hint}",
                    "Try approaching it like this: {step_by_step_hint}",
                    "Break it down this way: {step_by_step_hint}"
                ]
            },
            "medium": {
                "initial": [
                    "Great to see you again! Ready to dive into {skill_name}? {brief_context}",
                    "You're doing awesome! Let's tackle {skill_name}. {brief_context}",
                    "Nice progress so far! Time for {skill_name}. {brief_context}"
                ],
                "question": [
                    "You're doing well! {context} How would you approach this: {guided_question}?",
                    "I can see you're getting this! {context} What's your take on: {guided_question}?",
                    "You're on the right track! {context} How do you think about: {guided_question}?"
                ],
                "correct": [
                    "Nice work! {process_praise} That shows you understand the concept. Ready for the next challenge?",
                    "Great job! {process_praise} You're connecting the dots well. What about this: {next_question}?",
                    "Excellent! {process_praise} Your thinking is solid. Let's try: {next_question}"
                ],
                "incorrect": [
                    "Good thinking! {supportive_feedback} Here's a nudge in the right direction: {guiding_hint}",
                    "I like your approach! {supportive_feedback} Consider this perspective: {guiding_hint}",
                    "That's logical reasoning! {supportive_feedback} What if we think about it this way: {guiding_hint}"
                ],
                "hint": [
                    "Think about what we just discussed: {connection_hint}",
                    "Remember our earlier conversation about: {connection_hint}",
                    "Connect this to what you learned about: {connection_hint}"
                ]
            },
            "low": {
                "initial": [
                    "You've been crushing this! Let's tackle {skill_name}. What's your take on this topic?",
                    "Wow, you're really getting good at this! Time for {skill_name}. What do you already know?",
                    "You're becoming quite the expert! Let's explore {skill_name}. What's your intuition?"
                ],
                "question": [
                    "Challenge time! {minimal_context} What do you think about: {open_question}?",
                    "Here's something interesting: {minimal_context} How would you handle: {open_question}?",
                    "You're ready for this: {minimal_context} What's your approach to: {open_question}?"
                ],
                "correct": [
                    "Wow! {excitement} That's exactly the kind of thinking I was hoping for!",
                    "Brilliant! {excitement} You're thinking like a real expert now!",
                    "Outstanding! {excitement} That insight shows deep understanding!"
                ],
                "incorrect": [
                    "Interesting perspective! {peer_disagreement} Here's how I'd approach it: {brief_alternative}",
                    "That's one way to see it! {peer_disagreement} I think about it differently: {brief_alternative}",
                    "Creative thinking! {peer_disagreement} Another angle might be: {brief_alternative}"
                ],
                "hint": [
                    "What does your intuition tell you about this?",
                    "Trust your instincts - what feels right?",
                    "What's your gut reaction to this problem?"
                ]
            }
        }
    
    def _load_peer_phrases(self) -> Dict:
        """Load peer-like conversational phrases organized by emotion/intent"""
        return {
            "encouragement": [
                "You're really getting this!", "I love how you're thinking about this!", 
                "That's exactly right!", "You've got it!", "Perfect!", "Way to go!",
                "You're nailing this!", "That's what I'm talking about!", "Awesome work!"
            ],
            "excitement": [
                "Oh wow, great connection!", "That's such a good point!", 
                "You just made me think of something!", "I hadn't considered that!", "Brilliant!",
                "That's fascinating!", "Whoa, nice insight!", "That's genius!", "Mind blown!"
            ],
            "gentle_explanation": [
                "I can see where you're coming from!", "That's a really thoughtful answer!",
                "I like your reasoning!", "You're on an interesting track!", 
                "That's creative thinking!", "I appreciate your perspective!", "Good observation!"
            ],
            "process_praise": [
                "I love your approach!", "Great way to break that down!",
                "You're thinking like a pro!", "That's solid reasoning!", "Nice methodology!",
                "I like how you tackled that!", "Your process is spot-on!", "Smart thinking!"
            ],
            "supportive_feedback": [
                "You're so close!", "I can tell you're really thinking this through!",
                "That shows you understand the basics!", "You're on the right path!",
                "Your logic is sound!", "You're making good connections!", "Almost there!"
            ],
            "peer_disagreement": [
                "Hmm, let me share how I see it...", "I had a similar thought initially!",
                "That's one way to look at it! Here's another perspective...", 
                "Interesting! I think about it differently...", "I used to think that too!",
                "That's fair! Another way to consider it...", "Good point! I wonder though..."
            ],
            "celebration": [
                "Yes! That's it!", "You nailed it!", "Boom! Perfect!", "That's the stuff!",
                "You're on fire!", "Crushing it!", "Absolutely right!", "Bingo!"
            ],
            "thinking_together": [
                "Let's figure this out together", "What do you think we should try?",
                "How should we approach this?", "Let's brainstorm this",
                "What's our next move?", "Let's think through this step by step"
            ]
        }
    
    def _load_transition_phrases(self) -> Dict:
        """Load phrases for transitioning between topics and concepts"""
        return {
            "topic_transition": [
                "Awesome! You've mastered that concept. Now let's explore {next_topic}.",
                "Great work on that! Ready to dive into {next_topic}?",
                "You've got that down! Time for something new: {next_topic}.",
                "Perfect! Let's build on that with {next_topic}.",
                "Nice! Now that you understand that, let's tackle {next_topic}."
            ],
            "difficulty_increase": [
                "You're ready for a bigger challenge! Let's try {next_concept}.",
                "Time to level up! How about we explore {next_concept}?",
                "You've earned a tougher question: {next_concept}.",
                "Ready to stretch your brain? Let's work on {next_concept}."
            ],
            "review_transition": [
                "Let's make sure you've got this. Can you explain {review_concept}?",
                "Quick check - how would you summarize {review_concept}?",
                "Before we move on, tell me about {review_concept}.",
                "Let's solidify your understanding of {review_concept}."
            ],
            "connection_building": [
                "How does {concept_a} relate to {concept_b}?",
                "Can you connect {concept_a} with what we learned about {concept_b}?",
                "I'm curious - what's the relationship between {concept_a} and {concept_b}?",
                "Let's see if you can link {concept_a} to {concept_b}."
            ]
        }
    
    def get_template(self, scaffolding_level: str, situation: str) -> str:
        """Get a random template for the given scaffolding level and situation"""
        templates = self.templates.get(scaffolding_level, {}).get(situation, [])
        if templates:
            return random.choice(templates)
        return "Let's continue our discussion about {skill_name}."
    
    def get_phrase(self, category: str) -> str:
        """Get a random phrase from the specified category"""
        phrases = self.peer_phrases.get(category, [])
        if phrases:
            return random.choice(phrases)
        return ""
    
    def get_transition(self, transition_type: str) -> str:
        """Get a random transition phrase of the specified type"""
        transitions = self.transition_phrases.get(transition_type, [])
        if transitions:
            return random.choice(transitions)
        return "Let's move on to the next topic."
    
    def format_initial_question(self, scaffolding_level: str, skill_name: str, context: str = "") -> str:
        """Format an initial question for starting a new topic"""
        template = self.get_template(scaffolding_level, "initial")
        
        context_map = {
            "high": f"This is all about {skill_name}. Here's some background: {context}",
            "medium": f"We're exploring {skill_name}. {context[:100]}..." if context else f"Time to learn about {skill_name}!",
            "low": f"Ready for {skill_name}?" if not context else f"{context[:50]}..."
        }
        
        formatted_context = context_map.get(scaffolding_level, context)
        
        return template.format(
            skill_name=skill_name,
            context=formatted_context,
            brief_context=formatted_context
        )
    
    def format_feedback(self, scaffolding_level: str, is_correct: bool, **kwargs) -> str:
        """Format feedback based on correctness and scaffolding level"""
        situation = "correct" if is_correct else "incorrect"
        template = self.get_template(scaffolding_level, situation)
        
        # Add appropriate peer phrases
        if is_correct:
            encouragement = self.get_phrase("encouragement")
            process_praise = self.get_phrase("process_praise")
            excitement = self.get_phrase("excitement")
        else:
            encouragement = self.get_phrase("supportive_feedback")
            process_praise = self.get_phrase("gentle_explanation")
            excitement = self.get_phrase("peer_disagreement")
        
        return template.format(
            encouragement=encouragement,
            process_praise=process_praise,
            excitement=excitement,
            gentle_explanation=self.get_phrase("gentle_explanation"),
            supportive_feedback=self.get_phrase("supportive_feedback"),
            peer_disagreement=self.get_phrase("peer_disagreement"),
            **kwargs
        )
    
    def format_question(self, scaffolding_level: str, context: str = "", question: str = "", **kwargs) -> str:
        """Format a follow-up question based on scaffolding level"""
        template = self.get_template(scaffolding_level, "question")
        
        question_map = {
            "high": question or "Can you tell me what you think about this?",
            "medium": question or "How would you approach this problem?", 
            "low": question or "What's your take on this situation?"
        }
        
        formatted_question = question_map.get(scaffolding_level, question)
        
        return template.format(
            context=context,
            explanation=context,
            simple_question=formatted_question,
            guided_question=formatted_question,
            open_question=formatted_question,
            minimal_context=context[:100] if context else "",
            **kwargs
        )
    
    def get_hint_template(self, scaffolding_level: str) -> str:
        """Get a hint template based on scaffolding level"""
        return self.get_template(scaffolding_level, "hint")
    
    def create_topic_transition(self, current_topic: str, next_topic: str, performance_level: str = "good") -> str:
        """Create a smooth transition between topics"""
        if performance_level == "excellent":
            transition = self.get_transition("difficulty_increase")
        else:
            transition = self.get_transition("topic_transition")
        
        excitement = self.get_phrase("excitement")
        
        return f"{excitement} {transition.format(next_topic=next_topic, next_concept=next_topic)}"
    
    def create_connection_prompt(self, concept_a: str, concept_b: str) -> str:
        """Create a prompt that encourages connecting concepts"""
        connection_template = self.get_transition("connection_building")
        thinking_phrase = self.get_phrase("thinking_together")
        
        return f"{thinking_phrase}. {connection_template.format(concept_a=concept_a, concept_b=concept_b)}"


# Example usage and testing
if __name__ == "__main__":
    templates = ConversationTemplates()
    
    # Test different scaffolding levels
    print("=== HIGH SCAFFOLDING ===")
    print(templates.format_initial_question("high", "Linear Regression", "Linear regression is about finding relationships"))
    print()
    
    print("=== MEDIUM SCAFFOLDING ===") 
    print(templates.format_initial_question("medium", "Neural Networks"))
    print()
    
    print("=== LOW SCAFFOLDING ===")
    print(templates.format_initial_question("low", "Deep Learning"))
    print()
    
    # Test feedback
    print("=== CORRECT FEEDBACK (Medium) ===")
    print(templates.format_feedback("medium", True, next_question="What about overfitting?"))
    print()
    
    print("=== INCORRECT FEEDBACK (High) ===")
    print(templates.format_feedback("high", False, detailed_hint="Think about the slope of the line"))
    print()
    
    # Test transitions
    print("=== TOPIC TRANSITION ===")
    print(templates.create_topic_transition("Linear Regression", "Logistic Regression", "excellent"))
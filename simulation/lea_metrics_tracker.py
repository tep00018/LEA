# File: lea_metrics_tracker.py
"""
LEA Simulation Metrics Tracker
Comprehensive metrics tracking for Chat, Tutor, and Quiz modes during simulation
"""

import numpy as np
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict

@dataclass
class SimulationMetrics:
    """
    Comprehensive metrics tracking for LEA simulation across all three modes.
    Tracks the specific metrics required for evaluating system performance.
    """
    
    # Chat Mode Metrics
    chat_retrieval_attempts: int = 0
    chat_retrieval_successes: int = 0
    chat_relevance_scores: List[float] = field(default_factory=list)
    chat_response_times: List[float] = field(default_factory=list)
    chat_query_count: int = 0
    
    # Tutor Mode Metrics
    tutor_rag_alignments: int = 0
    tutor_rag_aligned: int = 0
    tutor_coherence_scores: List[float] = field(default_factory=list)
    tutor_scaffolding_total: int = 0
    tutor_scaffolding_appropriate: int = 0
    tutor_multi_turn_sequences: List[int] = field(default_factory=list)
    tutor_adaptive_adjustments: int = 0
    
    # Quiz Mode Metrics
    quiz_gos_intended: Set[str] = field(default_factory=set)
    quiz_gos_covered: Set[str] = field(default_factory=set)
    quiz_accuracy_by_type: Dict[str, List[bool]] = field(default_factory=lambda: defaultdict(list))
    quiz_difficulty_intended: List[float] = field(default_factory=list)
    quiz_difficulty_actual: List[float] = field(default_factory=list)
    quiz_total_questions: int = 0
    quiz_correct_answers: int = 0
    
    # Session-level Metrics
    session_start_time: Optional[datetime] = None
    session_end_time: Optional[datetime] = None
    total_interactions: int = 0
    mode_transitions: List[Dict[str, Any]] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize session start time if not provided"""
        if self.session_start_time is None:
            self.session_start_time = datetime.now()
    
    def get_chat_metrics(self) -> Dict[str, Any]:
        """
        Calculate Chat Mode metrics:
        - Retrieval Success Rate: Proportion of queries with successful RAG retrieval
        - Answer Relevance/Accuracy: Mean relevance score from LLM-as-Judge
        """
        retrieval_success_rate = 0.0
        if self.chat_retrieval_attempts > 0:
            retrieval_success_rate = self.chat_retrieval_successes / self.chat_retrieval_attempts
        
        answer_relevance_accuracy = 0.0
        if self.chat_relevance_scores:
            answer_relevance_accuracy = np.mean(self.chat_relevance_scores)
        
        avg_response_time = 0.0
        if self.chat_response_times:
            avg_response_time = np.mean(self.chat_response_times)
        
        return {
            'retrieval_success_rate': retrieval_success_rate,
            'answer_relevance_accuracy': answer_relevance_accuracy,
            'total_queries': self.chat_query_count,
            'avg_response_time_ms': avg_response_time,
            'relevance_scores': {
                'mean': answer_relevance_accuracy,
                'std': np.std(self.chat_relevance_scores) if self.chat_relevance_scores else 0.0,
                'min': min(self.chat_relevance_scores) if self.chat_relevance_scores else 0.0,
                'max': max(self.chat_relevance_scores) if self.chat_relevance_scores else 0.0
            }
        }
    
    def get_tutor_metrics(self) -> Dict[str, Any]:
        """
        Calculate Tutor Mode metrics:
        - RAG Alignment Precision: Proportion of responses using KC-aligned material
        - Multi-Turn Effectiveness: Coherence scoring across conversation turns
        - Adaptive Feedback Appropriateness: Proportion of appropriate scaffolding
        """
        rag_alignment_precision = 0.0
        if self.tutor_rag_alignments > 0:
            rag_alignment_precision = self.tutor_rag_aligned / self.tutor_rag_alignments
        
        multi_turn_effectiveness = 0.0
        if self.tutor_coherence_scores:
            multi_turn_effectiveness = np.mean(self.tutor_coherence_scores)
        
        adaptive_feedback_appropriateness = 0.0
        if self.tutor_scaffolding_total > 0:
            adaptive_feedback_appropriateness = self.tutor_scaffolding_appropriate / self.tutor_scaffolding_total
        
        avg_sequence_length = 0.0
        if self.tutor_multi_turn_sequences:
            avg_sequence_length = np.mean(self.tutor_multi_turn_sequences)
        
        return {
            'rag_alignment_precision': rag_alignment_precision,
            'multi_turn_effectiveness': multi_turn_effectiveness,
            'adaptive_feedback_appropriateness': adaptive_feedback_appropriateness,
            'total_interactions': self.tutor_rag_alignments,
            'avg_sequence_length': avg_sequence_length,
            'adaptive_adjustments': self.tutor_adaptive_adjustments,
            'coherence_metrics': {
                'mean': multi_turn_effectiveness,
                'std': np.std(self.tutor_coherence_scores) if self.tutor_coherence_scores else 0.0,
                'min': min(self.tutor_coherence_scores) if self.tutor_coherence_scores else 0.0,
                'max': max(self.tutor_coherence_scores) if self.tutor_coherence_scores else 0.0
            }
        }
    #FIXED
    def get_quiz_metrics(self) -> Dict[str, Any]:
        """FIXED: Calculate Quiz Mode metrics with proper accuracy calculation"""
        
        concept_coverage_precision = 0.0
        if self.quiz_gos_intended:
            concept_coverage_precision = len(self.quiz_gos_covered) / len(self.quiz_gos_intended)
        
        difficulty_alignment_error = 0.0
        if self.quiz_difficulty_intended and self.quiz_difficulty_actual:
            errors = [abs(intended - actual) 
                     for intended, actual in zip(self.quiz_difficulty_intended, self.quiz_difficulty_actual)]
            difficulty_alignment_error = np.mean(errors)
        
        # FIXED: Proper overall accuracy calculation
        total_correct = 0
        total_questions = 0
        
        for q_type, answers in self.quiz_accuracy_by_type.items():
            if answers:  # Only count if there are answers for this type
                total_correct += sum(answers)
                total_questions += len(answers)
        
        overall_accuracy = total_correct / total_questions if total_questions > 0 else 0.0
        
        # FIXED: Alternative calculation for validation
        quiz_total_accuracy = self.quiz_correct_answers / max(self.quiz_total_questions, 1)
        
        print(f"DEBUG: Quiz accuracy calculation:")
        print(f"  Method 1 (by type): {overall_accuracy:.3f} ({total_correct}/{total_questions})")
        print(f"  Method 2 (totals): {quiz_total_accuracy:.3f} ({self.quiz_correct_answers}/{self.quiz_total_questions})")
        
        # Use the method that gives non-zero results
        final_accuracy = max(overall_accuracy, quiz_total_accuracy)
        
        # Calculate accuracy by question type
        student_response_accuracy = {}
        for q_type, answers in self.quiz_accuracy_by_type.items():
            if answers:
                accuracy = sum(answers) / len(answers)
                student_response_accuracy[q_type] = accuracy
                print(f"  {q_type}: {accuracy:.3f} ({sum(answers)}/{len(answers)})")
        
        return {
            'concept_coverage_precision': concept_coverage_precision,
            'difficulty_alignment_error': difficulty_alignment_error,
            'overall_accuracy': final_accuracy,  # Use fixed calculation
            'student_response_accuracy': student_response_accuracy,
            'total_questions': max(total_questions, self.quiz_total_questions),
            'gos_intended': len(self.quiz_gos_intended),
            'gos_covered': len(self.quiz_gos_covered),
            'accuracy_breakdown': {
                'by_type_method': overall_accuracy,
                'by_totals_method': quiz_total_accuracy,
                'questions_by_type': {q_type: len(answers) for q_type, answers in self.quiz_accuracy_by_type.items() if answers}
            }
        }
    

    def get_quiz_metrics(self) -> Dict[str, Any]:
        """FIXED: Calculate Quiz Mode metrics with proper accuracy calculation"""
        
        concept_coverage_precision = 0.0
        if self.quiz_gos_intended:
            concept_coverage_precision = len(self.quiz_gos_covered) / len(self.quiz_gos_intended)
        
        difficulty_alignment_error = 0.0
        if self.quiz_difficulty_intended and self.quiz_difficulty_actual:
            errors = [abs(intended - actual) 
                     for intended, actual in zip(self.quiz_difficulty_intended, self.quiz_difficulty_actual)]
            difficulty_alignment_error = np.mean(errors)
        
        # FIXED: Calculate overall accuracy from type breakdown
        total_correct = 0
        total_questions = 0
        
        for q_type, answers in self.quiz_accuracy_by_type.items():
            if answers:
                total_correct += sum(answers)
                total_questions += len(answers)
        
        overall_accuracy = total_correct / total_questions if total_questions > 0 else 0.0
        
        # Debug output
        print(f"DEBUG: Quiz accuracy calculation:")
        print(f"  Total correct: {total_correct}")
        print(f"  Total questions: {total_questions}")
        print(f"  Overall accuracy: {overall_accuracy:.3f}")
        
        # Calculate accuracy by question type
        student_response_accuracy = {}
        for q_type, answers in self.quiz_accuracy_by_type.items():
            if answers:
                accuracy = sum(answers) / len(answers)
                student_response_accuracy[q_type] = accuracy
        
        return {
            'concept_coverage_precision': concept_coverage_precision,
            'difficulty_alignment_error': difficulty_alignment_error,
            'overall_accuracy': overall_accuracy,
            'student_response_accuracy': student_response_accuracy,
            'total_questions': total_questions,
            'gos_intended': len(self.quiz_gos_intended),
            'gos_covered': len(self.quiz_gos_covered)
        }
    
    def get_comprehensive_report(self) -> Dict[str, Any]:
        """Generate comprehensive metrics report across all modes"""
        session_duration = 0
        if self.session_start_time and self.session_end_time:
            session_duration = (self.session_end_time - self.session_start_time).total_seconds() / 60
        
        return {
            'session_info': {
                'start_time': self.session_start_time.isoformat() if self.session_start_time else None,
                'end_time': self.session_end_time.isoformat() if self.session_end_time else None,
                'duration_minutes': session_duration,
                'total_interactions': self.total_interactions,
                'mode_transitions': len(self.mode_transitions)
            },
            'chat_metrics': self.get_chat_metrics(),
            'tutor_metrics': self.get_tutor_metrics(),
            'quiz_metrics': self.get_quiz_metrics(),
            'summary': self._generate_summary()
        }
    
    def _generate_summary(self) -> Dict[str, Any]:
        """Generate executive summary of metrics"""
        chat = self.get_chat_metrics()
        tutor = self.get_tutor_metrics()
        quiz = self.get_quiz_metrics()
        
        # Determine overall performance rating
        performance_scores = []
        
        # Chat performance (target: >80% retrieval, >0.7 relevance)
        chat_score = (chat['retrieval_success_rate'] * 0.5 + 
                     min(chat['answer_relevance_accuracy'] / 0.7, 1.0) * 0.5)
        performance_scores.append(chat_score)
        
        # Tutor performance (target: >75% alignment, >0.7 coherence, >70% appropriate)
        tutor_score = (tutor['rag_alignment_precision'] * 0.33 +
                      min(tutor['multi_turn_effectiveness'] / 0.7, 1.0) * 0.33 +
                      tutor['adaptive_feedback_appropriateness'] * 0.34)
        performance_scores.append(tutor_score)
        
        # Quiz performance (target: >80% coverage, <1.0 error, >70% accuracy)
        quiz_score = (quiz['concept_coverage_precision'] * 0.33 +
                     max(0, 1 - quiz['difficulty_alignment_error'] / 2.0) * 0.33 +
                     quiz['overall_accuracy'] * 0.34)
        performance_scores.append(quiz_score)
        
        overall_score = np.mean(performance_scores)
        
        # Determine performance rating
        if overall_score >= 0.85:
            rating = "Excellent"
        elif overall_score >= 0.70:
            rating = "Good"
        elif overall_score >= 0.55:
            rating = "Satisfactory"
        else:
            rating = "Needs Improvement"
        
        return {
            'overall_performance_score': overall_score,
            'performance_rating': rating,
            'mode_scores': {
                'chat': chat_score,
                'tutor': tutor_score,
                'quiz': quiz_score
            },
            'key_strengths': self._identify_strengths(chat, tutor, quiz),
            'improvement_areas': self._identify_improvements(chat, tutor, quiz)
        }
    
    def _identify_strengths(self, chat: Dict, tutor: Dict, quiz: Dict) -> List[str]:
        """Identify system strengths based on metrics"""
        strengths = []
        
        if chat['retrieval_success_rate'] > 0.85:
            strengths.append("Excellent RAG retrieval success in Chat mode")
        if chat['answer_relevance_accuracy'] > 0.75:
            strengths.append("High answer relevance in Chat interactions")
        
        if tutor['rag_alignment_precision'] > 0.8:
            strengths.append("Strong KC alignment in Tutor responses")
        if tutor['multi_turn_effectiveness'] > 0.75:
            strengths.append("Effective multi-turn conversation coherence")
        if tutor['adaptive_feedback_appropriateness'] > 0.8:
            strengths.append("Appropriate adaptive scaffolding")
        
        if quiz['concept_coverage_precision'] > 0.85:
            strengths.append("Comprehensive concept coverage in quizzes")
        if quiz['difficulty_alignment_error'] < 0.5:
            strengths.append("Accurate difficulty calibration")
        if quiz['overall_accuracy'] > 0.75:
            strengths.append("High student success rate in quizzes")
        
        return strengths if strengths else ["System performing at baseline levels"]
    
    def _identify_improvements(self, chat: Dict, tutor: Dict, quiz: Dict) -> List[str]:
        """Identify areas needing improvement based on metrics"""
        improvements = []
        
        if chat['retrieval_success_rate'] < 0.6:
            improvements.append("Improve RAG retrieval success rate in Chat mode")
        if chat['answer_relevance_accuracy'] < 0.5:
            improvements.append("Enhance answer relevance and accuracy")
        
        if tutor['rag_alignment_precision'] < 0.6:
            improvements.append("Better align Tutor responses with KC content")
        if tutor['multi_turn_effectiveness'] < 0.5:
            improvements.append("Improve conversation coherence across turns")
        if tutor['adaptive_feedback_appropriateness'] < 0.6:
            improvements.append("Refine adaptive scaffolding strategies")
        
        if quiz['concept_coverage_precision'] < 0.7:
            improvements.append("Increase concept coverage in quiz questions")
        if quiz['difficulty_alignment_error'] > 1.5:
            improvements.append("Better calibrate question difficulty")
        if quiz['overall_accuracy'] < 0.5:
            improvements.append("Adjust quiz difficulty for better success rates")
        
        return improvements if improvements else ["All metrics meeting acceptable thresholds"]
    
    def log_mode_transition(self, from_mode: str, to_mode: str, reason: str = ""):
        """Log transitions between learning modes"""
        self.mode_transitions.append({
            'timestamp': datetime.now().isoformat(),
            'from_mode': from_mode,
            'to_mode': to_mode,
            'reason': reason,
            'interaction_count': self.total_interactions
        })
    
    def finalize_session(self):
        """Mark session as complete and calculate final metrics"""
        if not self.session_end_time:
            self.session_end_time = datetime.now()
        
        # Calculate any final aggregations
        self.total_interactions = (
            self.chat_query_count + 
            self.tutor_rag_alignments + 
            self.quiz_total_questions
        )
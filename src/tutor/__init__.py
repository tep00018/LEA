# File: src/tutor/__init__.py
"""
LEA Tutor Module - Rapid Implementation
Provides adaptive peer tutoring with scaffolding and fading support for
Granular Objectives using adaptive pedagogical strategies.

UPDATED: For rapid one-day implementation with modular components
"""

from .simple_tutor_system import SimpleTutorSystem, TutorSession
from .conversation_templates import ConversationTemplates
from .tutor_state import TutorStateManager, ScaffoldingLevel, SessionStatus

__version__ = "1.0.0"
__all__ = [
    "SimpleTutorSystem", 
    "TutorSession", 
    "ConversationTemplates",
    "TutorStateManager", 
    "ScaffoldingLevel", 
    "SessionStatus"
]
# File: streamlit_app.py
"""
FIXED: LEA Streamlit Application - Quiz continuation issue resolved
ISSUE: Quiz was stopping on correct answers due to mid-quiz week advancement
SOLUTION: Defer week advancement until quiz completion
"""

import streamlit as st
import time
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from enum import Enum
from datetime import datetime
import asyncio
import concurrent.futures
from typing import Optional
import json 
import random
import csv
from PIL import Image, ImageDraw, ImageFont
import io
import threading

class AppMode(Enum):
    CHAT = "chat"
    TUTOR = "tutor"
    QUIZ = "quiz"
    
print("DEBUG: Starting LEA app in Streamlit")

# Path setup
try:
    current_file = Path(__file__).resolve()
    project_root = current_file.parent
    while not (project_root / "src").exists() and project_root != project_root.parent:
        project_root = project_root.parent
    
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    print(f"DEBUG: Project root: {project_root}")
except Exception as e:
    print(f"ERROR: Path setup failed: {e}")

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("DEBUG: Environment loaded")
except Exception as e:
    print(f"ERROR: Environment loading failed: {e}")

# ============= MEMORY SYSTEM INTEGRATION =============

def get_redis_client():
    """Get or create Redis client singleton"""
    if 'redis_client' not in st.session_state:
        try:
            from src.storage.redis_client import LEARedisClient
            st.session_state['redis_client'] = LEARedisClient()
            print("DEBUG: Redis client initialized for memory system")
        except Exception as e:
            print(f"DEBUG: Could not initialize Redis client: {e}")
            st.session_state['redis_client'] = None
    return st.session_state['redis_client']

def store_interaction_memory(username: str, interaction_type: str, content: Dict):
    """Store interaction in memory system"""
    try:
        redis_client = get_redis_client()
        if redis_client:
            success = redis_client.store_short_term_memory(
                username=username,
                interaction_type=interaction_type,
                content=content
            )
            if success:
                print(f"DEBUG: Stored {interaction_type} memory for {username}")
    except Exception as e:
        print(f"DEBUG: Memory storage failed: {e}")
        

# Load custom page icon
def load_page_icon():
    """Load custom page icon with fallback"""
    icon_path = "./static/icon1.png"
    try:
        if os.path.exists(icon_path):
            icon = Image.open(icon_path)
            # Resize to appropriate size for browser tab (typically 32x32 or 16x16)
            icon = icon.resize((32, 32), Image.Resampling.LANCZOS)
            return icon
        else:
            print(f"DEBUG: Page icon not found at {icon_path}, using fallback")
            return "🎓"  # Fallback to emoji
    except Exception as e:
        print(f"DEBUG: Error loading page icon: {e}, using fallback")
        return "🎓"  # Fallback to emoji

# Page config with custom icon
page_icon = load_page_icon()
st.set_page_config(
    page_title="LEA - Learning Assistant",
    page_icon=page_icon,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Module Imports
from src.auth.auth_service import AuthService
from src.core.kc_model_loader import KCModelLoader
from src.quiz.simple_quiz_system import SimpleQuizSystem
from src.tutor.simple_tutor_system import SimpleTutorSystem, TutorSession
from src.core.mastery_tracker import MasteryTracker, MasteryIntegrationHelper
from src.core.go_strategy import MasteryLevel, GOProgress, GOSequencer, TutorSequencer, QuizSequencer, RepeatStrategy
from src.core.progress_integration import ProgressIntegrationBridge
from src.storage.consolidation_worker import MemoryConsolidationWorker
from src.mcp.tools.rag_retrieval_tool import RAGRetrievalTool

# Global worker reference
memory_worker = None
worker_thread = None

def start_memory_worker():
    """Start memory consolidation worker in background"""
    global memory_worker, worker_thread
    
    try:
        redis_client = get_redis_client()
        openai_key = os.getenv("OPENAI_API_KEY")
        
        if redis_client and not memory_worker:
            memory_worker = MemoryConsolidationWorker(redis_client, openai_key)
            
            # Start in background thread
            def run_worker():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(memory_worker.start())
                except Exception as e:
                    print(f"Worker error: {e}")
                finally:
                    loop.close()
            
            worker_thread = threading.Thread(target=run_worker, daemon=True)
            worker_thread.start()
            print("DEBUG: Memory consolidation worker started in background")
            return True
            
    except Exception as e:
        print(f"ERROR: Failed to start memory worker: {e}")
        return False
    
    return False

def stop_memory_worker():
    """Stop the memory worker gracefully"""
    global memory_worker
    if memory_worker:
        memory_worker.stop()
        print("DEBUG: Memory worker stopped")

# Configuration
REDIS_URL = os.getenv("REDIS_URL")
AVAILABLE_COURSES = [
    "DEMO101",
]

# AVAILABLE_COURSES = [
#     "DEMO101"
# ]

# Enhanced CSS Styling
st.markdown("""
<style>
    .main {
        padding: 0;
        max-width: 1400px;
        margin: 0 auto;
    }
    
    .quiz-progress {
        background-color: #e9ecef;
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 1rem;
        text-align: center;
        font-weight: 600;
    }
    
    .feedback-correct {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    
    .feedback-incorrect {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    
    .quiz-summary {
        background-color: #e7f3ff;
        border: 1px solid #b8daff;
        color: #004085;
        padding: 1.5rem;
        border-radius: 8px;
        margin: 1rem 0;
        text-align: center;
    }
    
    .stButton > button {
        font-size: 0.85rem !important;
        padding: 0.4rem 0.8rem !important;
    }
</style>
""", unsafe_allow_html=True)

# Simple Learning Analytics Calculator
class SimpleLearningAnalytics:
    """Simple learning analytics calculator that doesn't depend on the orchestrator"""
    
    def __init__(self):
        self.cl_params = {
            'beta_0': 0.5,   # Baseline cognitive load
            'beta_1': 1.0,   # Difficulty coefficient
            'beta_2': 4.5,   # Accuracy coefficient (inverted for load)
            'beta_4': 0.1,   # Interaction count coefficient  
            'beta_5': 1.0    # Task type coefficient
        }
    
    def calculate_learning_metrics(self, quiz_results: List[Dict], question_number: int, 
                                 current_question_type: str) -> Dict[str, float]:
        """Calculate learning metrics from quiz results"""
        
        try:
            # Calculate recent accuracy (last 4 answers)
            recent_results = quiz_results[-4:] if len(quiz_results) >= 4 else quiz_results
            if recent_results:
                recent_accuracy = sum(1 for r in recent_results if r.get('correct', False)) / len(recent_results)
            else:
                recent_accuracy = 0.5  # Default
            
            # Calculate difficulty based on question type
            type_difficulty = {
                'multiple_choice': 0.4,
                'true_false': 0.3,
                'fill_in_blank': 0.6,
                'open_ended': 0.8
            }
            current_difficulty = type_difficulty.get(current_question_type, 0.5)
            
            # Add progression factor (later questions are slightly harder)
            if question_number > 0:
                progression_factor = (question_number / 16) * 0.2  # Assuming 16 questions
                current_difficulty = min(1.0, current_difficulty + progression_factor)
            
            # Calculate task type (0=structured, 1=open-ended)
            task_type = 1.0 if current_question_type == 'open_ended' else 0.0
            
            # Apply cognitive load formula
            cognitive_load = (
                self.cl_params['beta_0'] +                           # β₀ baseline
                self.cl_params['beta_1'] * current_difficulty +      # β₁G difficulty
                self.cl_params['beta_2'] * (1 - recent_accuracy) +   # β₂(1-A) accuracy
                self.cl_params['beta_4'] * question_number +         # β₄Q fatigue
                self.cl_params['beta_5'] * task_type                 # β₅T task type
            )
            
            # Bound cognitive load to 0-10 range
            cognitive_load = max(0, min(10, cognitive_load))
            
            # Calculate motivation based on recent performance
            if len(quiz_results) >= 3:
                last_three = quiz_results[-3:]
                recent_trend = sum(1 for r in last_three if r.get('correct', False)) / len(last_three)
                motivation = max(0.2, min(1.0, recent_trend + 0.3))  # Boost motivation slightly
            else:
                motivation = 0.5
            
            # Calculate fatigue
            fatigue = min(1.0, question_number * 0.05)  # 5% fatigue per question
            
            print(f"DEBUG: Simple analytics - Accuracy: {recent_accuracy:.2f}, "
                  f"Difficulty: {current_difficulty:.2f}, CL: {cognitive_load:.2f}")
            
            return {
                'cognitive_load': cognitive_load,
                'zpd_score': recent_accuracy,
                'motivation': motivation,
                'fatigue': fatigue,
                'difficulty': current_difficulty,
                'task_type': task_type,
                'question_number': question_number
            }
            
        except Exception as e:
            print(f"DEBUG: Error calculating simple analytics: {e}")
            return {
                'cognitive_load': 5.0,
                'zpd_score': 0.5,
                'motivation': 0.5,
                'fatigue': 0.3,
                'difficulty': 0.5,
                'task_type': 0.0,
                'question_number': question_number
            }

# CACHED SERVICE INITIALIZATION
@st.cache_resource
def get_auth_service():
    """Get cached AuthService instance"""
    try:
        auth_service = AuthService(REDIS_URL)
        print("DEBUG: AuthService initialized (cached)")
        return auth_service
    except Exception as e:
        print(f"ERROR: AuthService initialization failed: {e}")
        return None

@st.cache_resource
def get_redis_client():
    """Get Redis client"""
    try:
        from src.storage.redis_client import LEARedisClient
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        client = LEARedisClient(redis_url)
        print("DEBUG: Redis client created successfully")
        return client
    except Exception as e:
        print(f"DEBUG: Redis client creation failed: {e}")
        return None

@st.cache_resource
def get_orchestrator():
    """ENHANCED DEBUG: Get full MCP orchestrator with better error handling"""
    print("DEBUG: ===== ORCHESTRATOR INITIALIZATION START =====")
    
    try:
        # Step 0: Check auth service
        auth_service = get_auth_service()
        if not auth_service:
            print("ERROR: ❌ No auth service available for orchestrator")
            return None
        
        print(f"DEBUG: ✅ Auth service available: {type(auth_service).__name__}")
        print(f"DEBUG: ✅ Redis client available: {auth_service.redis_client is not None}")
        
        # Step 1: Test imports first
        print("DEBUG: Testing imports...")
        
        # Test MCP Server import
        try:
            from src.mcp.mcp_server import LEAMCPServer
            print("DEBUG: ✅ LEAMCPServer import successful")
        except ImportError as e:
            print(f"ERROR: ❌ LEAMCPServer import failed: {e}")
            return _get_fallback_orchestrator(auth_service)
        except Exception as e:
            print(f"ERROR: ❌ LEAMCPServer import error: {e}")
            return _get_fallback_orchestrator(auth_service)
            
        
        # Test MCP Orchestrator import
        try:
            from src.core.agent_orchestrator_mcp import LEAOrchestratorMCP
            print("DEBUG: ✅ LEAOrchestratorMCP import successful")
        except ImportError as e:
            print(f"ERROR: ❌ LEAOrchestratorMCP import failed: {e}")
            return _get_fallback_orchestrator(auth_service)
        except Exception as e:
            print(f"ERROR: ❌ LEAOrchestratorMCP import error: {e}")
            return _get_fallback_orchestrator(auth_service)
        
        # Test Scaffolding Engine import
        try:
            from src.core.scaffolding_engine import ScaffoldingEngine
            print("DEBUG: ✅ ScaffoldingEngine import successful")
        except ImportError as e:
            print(f"WARNING: ⚠️ ScaffoldingEngine import failed: {e}")
            # Continue without scaffolding
        except Exception as e:
            print(f"WARNING: ⚠️ ScaffoldingEngine import error: {e}")
            # Continue without scaffolding
        
        # Step 2: Initialize MCP Server with enhanced error handling
        print("DEBUG: Initializing MCP Server...")
        try:
            mcp_server = LEAMCPServer(auth_service.redis_client)
            print("DEBUG: ✅ MCP Server created successfully")
            
            # Test server basic functionality
            if hasattr(mcp_server, 'tool_registry') and mcp_server.tool_registry:
                tool_count = len(mcp_server.tool_registry.tools) if hasattr(mcp_server.tool_registry, 'tools') else 0
                print(f"DEBUG: ✅ Tool registry available with {tool_count} tools")
            else:
                print("WARNING: ⚠️ Tool registry initialization issues")
                
        except Exception as e:
            print(f"ERROR: ❌ MCP Server initialization failed: {type(e).__name__}: {e}")
            return _get_fallback_orchestrator(auth_service)
        
        # Step 3: Initialize LEA MCP Orchestrator
        print("DEBUG: Initializing LEA MCP Orchestrator...")
        try:
            orchestrator = LEAOrchestratorMCP(mcp_server, auth_service.redis_client)
            print("DEBUG: ✅ LEA MCP Orchestrator created successfully")
            
            # Check if orchestrator has required attributes
            if hasattr(orchestrator, 'mcp_client'):
                print("DEBUG: ✅ Orchestrator has mcp_client attribute")
            else:
                print("WARNING: ⚠️ Orchestrator missing mcp_client attribute")
                
        except Exception as e:
            print(f"ERROR: ❌ LEA MCP Orchestrator initialization failed: {type(e).__name__}: {e}")
            return _get_fallback_orchestrator(auth_service)
        
        # Step 4: Try to integrate scaffolding engine with better error handling
        print("DEBUG: Integrating scaffolding engine...")
        try:
            scaffolding_engine = ScaffoldingEngine(auth_service.redis_client)
            orchestrator.scaffolding_engine = scaffolding_engine
            print("DEBUG: ✅ Scaffolding engine integrated successfully")
        except Exception as e:
            print(f"WARNING: ⚠️ Scaffolding engine integration failed: {type(e).__name__}: {e}")
            print("DEBUG: 📱 Continuing with basic scaffolding only")
            # Continue without scaffolding engine - orchestrator will use fallback
        
        # Step 5: Try to integrate decision logger
        print("DEBUG: Integrating decision logger...")
        try:
            decision_logger = DecisionLogger()
            orchestrator.decision_logger = decision_logger
            print("DEBUG: ✅ Decision logger integrated successfully")
        except Exception as e:
            print(f"WARNING: ⚠️ Decision logger initialization failed: {type(e).__name__}: {e}")
            print("DEBUG: 📊 Continuing without decision logging")
            # Continue without logging
        
        # Step 6: Test orchestrator functionality
        print("DEBUG: Testing orchestrator basic functionality...")
        try:
            # Verify the orchestrator has required methods
            required_methods = ['process_query', 'process_interaction']
            missing_methods = [method for method in required_methods if not hasattr(orchestrator, method)]
            
            if missing_methods:
                print(f"ERROR: ❌ Orchestrator missing required methods: {missing_methods}")
                return _get_fallback_orchestrator(auth_service)
            else:
                print("DEBUG: ✅ Orchestrator has all required methods")
                
            # Check component status
            has_scaffolding = hasattr(orchestrator, 'scaffolding_engine') and orchestrator.scaffolding_engine is not None
            has_logger = hasattr(orchestrator, 'decision_logger') and orchestrator.decision_logger is not None
            
            print(f"DEBUG: 🎯 Scaffolding Engine: {'✅' if has_scaffolding else '❌'}")
            print(f"DEBUG: 📊 Decision Logger: {'✅' if has_logger else '❌'}")
            
            if has_scaffolding and has_logger:
                print(f"DEBUG: 🧠 Full Orchestrator Status: ADVANCED (CL×ZPD Matrix + Research Logging)")
            elif has_scaffolding:
                print(f"DEBUG: 🧠 Full Orchestrator Status: ENHANCED (CL×ZPD Matrix)")
            else:
                print(f"DEBUG: 🧠 Full Orchestrator Status: STANDARD (Basic Scaffolding)")
            
            print("DEBUG: ===== ORCHESTRATOR INITIALIZATION SUCCESS =====")
            return orchestrator
                
        except Exception as e:
            print(f"WARNING: ⚠️ Orchestrator functionality test failed: {type(e).__name__}: {e}")
            # Return orchestrator anyway, it might still work
            print("DEBUG: ===== ORCHESTRATOR INITIALIZATION PARTIAL SUCCESS =====")
            return orchestrator
            
    except Exception as e:
        print(f"ERROR: ❌ Complete orchestrator initialization failure: {type(e).__name__}: {e}")
        print("DEBUG: ===== ORCHESTRATOR INITIALIZATION COMPLETE FAILURE =====")
        return _get_fallback_orchestrator(auth_service) if 'auth_service' in locals() else None
        

@st.cache_resource
def _get_fallback_orchestrator(_auth_service):  # FIXED: Added underscore prefix
    """Create fallback orchestrator when MCP orchestrator fails"""
    try:
        print("DEBUG: Using RAG Fallback Orchestrator as backup")
        from src.core.agent_orchestrator import RAGFallbackOrchestrator  # Make sure this import exists
        orchestrator = RAGFallbackOrchestrator(_auth_service.redis_client)
        print("DEBUG: ✅ RAG Fallback Orchestrator initialized successfully")
        return orchestrator
    except Exception as e:
        print(f"ERROR: Even fallback orchestrator failed: {e}")
        return None

@st.cache_resource  
def get_kc_loader_for_module(module: str):
    """Get cached KCModelLoader instance for specific module"""
    try:
        auth_service = get_auth_service()
        if auth_service:
            kc_loader = KCModelLoader(auth_service.redis_client, module=module)
            print(f"DEBUG: KC Model Loader initialized for module {module} (cached)")
            return kc_loader
        return None
    except Exception as e:
        print(f"ERROR: KC Model Loader initialization failed for module {module}: {e}")
        return None
        
@st.cache_resource  
def get_kc_loader():
    """Get cached KCModelLoader instance with default module (for system initialization)"""
    try:
        auth_service = get_auth_service()
        if auth_service:
            # Use DEMO101 as default for system initialization
            kc_loader = KCModelLoader(auth_service.redis_client, module="DEMO101")
            print("DEBUG: KC Model Loader initialized with default module DEMO101 (cached)")
            return kc_loader
        return None
    except Exception as e:
        print(f"ERROR: KC Model Loader initialization failed: {e}")
        return None

@st.cache_resource
def get_quiz_system():
    """Get cached SimpleQuizSystem instance with RAG tool"""
    try:
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            print("WARNING: No OpenAI API key")
            return None
        
        # Initialize RAG tool
        # from src.mcp.tools.rag_retrieval_tool import RAGRetrievalTool
        rag_tool = RAGRetrievalTool()
        
        # Initialize quiz system WITH RAG tool
        quiz_system = SimpleQuizSystem(openai_api_key, rag_tool=rag_tool)
        print("DEBUG: SimpleQuizSystem initialized with RAG tool (cached)")
        return quiz_system
        
    except Exception as e:
        print(f"ERROR: SimpleQuizSystem initialization failed: {e}")
        return None
        
@st.cache_resource
def get_chat_system():
    """Get cached Chat system instance"""
    try:
        from openai import OpenAI
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_api_key:
            openai_client = OpenAI(api_key=openai_api_key)
            print("DEBUG: Chat system initialized (cached)")
            return openai_client
        else:
            print("WARNING: No OpenAI API key for chat")
            return None
    except Exception as e:
        print(f"ERROR: Chat system initialization failed: {e}")
        return None

@st.cache_resource
def get_tutor_system():
    """Get cached Tutor system instance WITH MCP client for YouTube"""
    try:
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_api_key:
            from openai import OpenAI
            openai_client = OpenAI(api_key=openai_api_key)
            
            auth_service = get_auth_service()
            redis_client = auth_service.redis_client if auth_service else None
            
            # GET MCP CLIENT from orchestrator
            mcp_client = None
            orchestrator = get_orchestrator()
            if orchestrator and hasattr(orchestrator, 'mcp_client'):
                mcp_client = orchestrator.mcp_client
                print("DEBUG: ✅ MCP client obtained for tutor system")
            else:
                print("DEBUG: ⚠️ No MCP client available for tutor system")
            
            # PASS MCP CLIENT to tutor system
            tutor_system = SimpleTutorSystem(openai_client, redis_client, mcp_client)
            print(f"DEBUG: Tutor system initialized with MCP client: {mcp_client is not None}")
            return tutor_system
        else:
            print("WARNING: No OpenAI API key for tutor")
            return None
    except Exception as e:
        print(f"ERROR: Tutor system initialization failed: {e}")
        return None
        
@st.cache_resource
def get_mastery_tracker():
    """Get cached mastery tracker instance with fixed interface"""
    try:
        auth_service = get_auth_service()
        storage_backend = "redis" if auth_service and auth_service.redis_client else "file"
        redis_client = auth_service.redis_client if auth_service else None
        
        tracker = MasteryTracker(
            storage_backend=storage_backend,
            redis_client=redis_client
        )
        print("DEBUG: MasteryTracker initialized successfully")
        return tracker
    except Exception as e:
        print(f"WARNING: MasteryTracker initialization failed: {e}")
        return None

@st.cache_resource
def get_mastery_integration_helper():
    """Get cached mastery integration helper"""
    try:
        mastery_tracker = get_mastery_tracker()
        if mastery_tracker:
            helper = MasteryIntegrationHelper(mastery_tracker)
            print("DEBUG: MasteryIntegrationHelper initialized successfully")
            return helper
        return None
    except Exception as e:
        print(f"ERROR: MasteryIntegrationHelper initialization failed: {e}")
        return None

@st.cache_resource
def get_simple_analytics():
    """Get cached simple analytics calculator"""
    return SimpleLearningAnalytics()

@st.cache_resource
def get_go_strategy_components():
    """Get GO-based strategy components"""
    try:
        auth_service = get_auth_service()
        redis_client = auth_service.redis_client if auth_service else None
        
        from src.core.go_strategy import GOSequencer, TutorSequencer, QuizSequencer
        
        go_sequencer = GOSequencer(redis_client)
        tutor_sequencer = TutorSequencer(go_sequencer, redis_client)
        quiz_sequencer = QuizSequencer(go_sequencer, redis_client)
        
        print("DEBUG: GO strategy components initialized successfully")
        return {
            "go_sequencer": go_sequencer,
            "tutor_sequencer": tutor_sequencer,
            "quiz_sequencer": quiz_sequencer
        }
    except Exception as e:
        print(f"DEBUG: GO strategy initialization failed: {e}")
        return None

@st.cache_resource
def get_progress_bridge():
    """Get cached progress integration bridge"""
    try:
        auth_service = get_auth_service()
        mastery_tracker = get_mastery_tracker()
        
        if auth_service and mastery_tracker:
            bridge = ProgressIntegrationBridge(
                redis_client=auth_service.redis_client,
                mastery_tracker=mastery_tracker
            )
            print("DEBUG: ProgressIntegrationBridge initialized successfully")
            return bridge
        return None
    except Exception as e:
        print(f"ERROR: ProgressIntegrationBridge initialization failed: {e}")
        return None

@st.cache_data
def create_student_avatar(initial: str) -> Image.Image:
    """Create a circular avatar with student's initial - cached for performance"""
    size = 50
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Light blue background (#ADD8E6)
    light_blue = (173, 216, 230)
    draw.ellipse([0, 0, size, size], fill=light_blue)
    
    # Try to load Arial font with fallbacks for different systems
    font_size = 36
    try:
        # Windows - Load Arial Bold
        font = ImageFont.truetype("arialbd.ttf", font_size)  # <-- CHANGED: arialbd.ttf for bold
    except OSError:
        try:
            # macOS - Load Helvetica Bold or Arial Bold
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size, index=1)  # index=1 for bold
        except OSError:
            try:
                # Try Arial Bold on macOS
                font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", font_size)
            except OSError:
                try:
                    # Linux - Already using Bold variant
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
                except OSError:
                    try:
                        # Alternative Linux bold font
                        font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", font_size)
                    except OSError:
                        # Fallback to default font
                        font = ImageFont.load_default()    
    # Get text bounding box for centering
    initial_upper = initial.upper()
    bbox = draw.textbbox((0, 0), initial_upper, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Center the text
    x = (size - text_width) // 2
    y = (size - text_height) // 2 - 2  # Slight adjustment for better centering
    
    # Draw black bold text
    draw.text((x, y), initial_upper, fill='black', font=font)
    
    return img

@st.cache_data
def get_lea_avatar() -> Image.Image:
    """Get resized LEA avatar - cached for performance"""
    lea_avatar_path = "./static/icon1.png"
    
    try:
        if os.path.exists(lea_avatar_path):
            # Load and resize the image
            img = Image.open(lea_avatar_path)
            img = img.resize((50, 50), Image.Resampling.LANCZOS)
            
            # Convert to RGBA if not already
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            return img
        else:
            print(f"DEBUG: LEA avatar not found at {lea_avatar_path}")
            return create_fallback_lea_avatar()
    except Exception as e:
        print(f"DEBUG: Error loading LEA avatar: {e}")
        return create_fallback_lea_avatar()

@st.cache_data
def create_fallback_lea_avatar() -> Image.Image:
    """Create a fallback LEA avatar if image file not found"""
    size = 50
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Purple background for LEA
    purple = (138, 43, 226)
    draw.ellipse([0, 0, size, size], fill=purple)
    
    # Draw "LEA" text
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    
    text = "LEA"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x = (size - text_width) // 2
    y = (size - text_height) // 2
    
    draw.text((x, y), text, fill='white', font=font)
    
    return img

# Add this function to convert PIL images to base64 for HTML display:
import base64

def pil_image_to_base64(img: Image.Image) -> str:
    """Convert PIL image to base64 string for HTML display"""
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_b64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_b64}"


def render_login_page():
    """Render login interface with custom LEA avatar"""
    auth_service = get_auth_service()
    if not auth_service:
        st.error("Authentication service not available.")
        st.stop()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        # Get LEA avatar for header
        lea_avatar = get_lea_avatar()
        avatar_b64 = pil_image_to_base64(lea_avatar)
        
        # Custom header with avatar above and LEA text below
        st.markdown(f"""
        <div style="text-align: center; margin-bottom: 2rem;">
            <div style="display: flex; align-items: center; justify-content: center; gap: 20px;">
                <div style="display: flex; flex-direction: column; align-items: center;">
                    <img src="{avatar_b64}" style="width: 80px; height: 80px; border-radius: 50%; margin-bottom: 5px;">
                    <span style="font-size: 1.2rem; font-weight: bold; color: #262730;">LEA</span>
                </div>
                <div style="text-align: left;">
                    <span style="font-size: 2.5rem; font-weight: bold; color: #262730; line-height: 1.2;">
                        Learning Environment<br>Assistant
                    </span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<p style='text-align: center; color: #6c757d; font-size: 1.1rem; margin-bottom: 2rem;'>Slide In. Study Up. Show Off.</p>", unsafe_allow_html=True)
        
# def render_login_page():
#     """Render login interface with custom LEA avatar"""
#     auth_service = get_auth_service()
#     if not auth_service:
#         st.error("Authentication service not available.")
#         st.stop()
    
#     col1, col2, col3 = st.columns([1, 2, 1])
    
#     with col2:
#         # Try to load LEA avatar, with multiple fallbacks
#         lea_avatar_path = "./static/icon1.png"
        
#         # Check if file exists and use it directly
#         if os.path.exists(lea_avatar_path):
#             # Use Streamlit's image display in columns
#             avatar_col, title_col = st.columns([1, 4])
#             with avatar_col:
#                 st.image(lea_avatar_path, width=80)
#             with title_col:
#                 st.markdown("<h1 style='margin-top: 10px;'>LEA Learning Environment Assistant</h1>", unsafe_allow_html=True)
#         else:
#             # Fallback to emoji if image not found
#             st.markdown("<h1 style='text-align: center;'>👩‍🏫 LEA Learning Environment Assistant</h1>", unsafe_allow_html=True)
        
#         st.markdown("<p style='text-align: center; color: #6c757d; font-size: 1.1rem; margin-bottom: 2rem;'>Slide In. Study Up. Show Off.</p>", unsafe_allow_html=True)

# def render_login_page():
#     """Render login interface with custom LEA avatar"""
#     auth_service = get_auth_service()
#     if not auth_service:
#         st.error("Authentication service not available.")
#         st.stop()
    
#     col1, col2, col3 = st.columns([1, 2, 1])
    
#     with col2:
#         # Get LEA avatar for header
#         lea_avatar = get_lea_avatar()
#         avatar_b64 = pil_image_to_base64(lea_avatar)
        
#         # Custom header with LEA avatar
#         st.markdown(f"""
#         <div style="text-align: center; margin-bottom: 2rem;">
#             <img src="{lea_avatar}" style="width: 60px; height: 60px; vertical-align: middle; margin-right: 15px;">
#             <span style="font-size: 2.5rem; font-weight: bold; vertical-align: middle; color: #262730;">
#                 LEA Learning Environment Assistant
#             </span>
#         </div>
#         """, unsafe_allow_html=True)
        
#         st.markdown("<p style='text-align: center; color: #6c757d; font-size: 1.1rem; margin-bottom: 2rem;'>Slide In. Study Up. Show Off.</p>", unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["Login", "Register"])
        
        with tab1:
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                
                if st.form_submit_button("Log In", use_container_width=True, type="primary"):
                    if username and password:
                        success, session_id, message = auth_service.login_user(username, password)
                        if success:
                            st.session_state.authenticated = True
                            st.session_state.username = username
                            load_user_data_after_login(username)
                            st.success("Login successful!")
                            st.rerun()
                        else:
                            st.error(message)
                    else:
                        st.error("Please enter username and password.")
        
        with tab2:
            with st.form("register_form"):
                new_username = st.text_input("Username")
                full_name = st.text_input("Full Name")
                new_password = st.text_input("Password", type="password")
                confirm_password = st.text_input("Confirm Password", type="password")
                
                selected_courses = st.multiselect("Select Courses:", AVAILABLE_COURSES, default=["DEMO101"])
                
                if st.form_submit_button("Create Account", use_container_width=True, type="primary"):
                    if all([new_username, full_name, new_password, confirm_password]):
                        if new_password == confirm_password and len(new_password) >= 6:
                            if selected_courses:
                                success, message = auth_service.register_user(
                                    new_username, new_password, full_name, selected_courses
                                )
                                if success:
                                    st.success("Account created! Please login.")
                                    st.rerun()
                                else:
                                    st.error(message)
                            else:
                                st.error("Please select at least one course.")
                        else:
                            st.error("Password must be at least 6 characters and passwords must match.")
                    else:
                        st.error("Please fill in all fields.")

# =============================================================================
# FIXED: MODULE-LEVEL FUNCTIONS (Previously scoped inside render_quiz_interface)
# =============================================================================

def update_mastery_after_quiz_answer(username: str, answer: str, quiz_result: Dict) -> bool:
    """FIXED: Update mastery WITHOUT week advancement during quiz"""
    try:
        course = st.session_state.selected_course
        week = st.session_state.selected_week
        
        print(f"DEBUG: 🔄 QUIZ MASTERY: Update for {username} - defer week advancement")
        
        # Get current question details
        current_question = st.session_state.current_quiz_data.get("current_question", {})
        go_id = current_question.get("go_id", f"GO_{week:02d}_QUIZ_{st.session_state.quiz_progress['current']:02d}")
        
        # Get mastery tracker
        mastery_tracker = get_mastery_tracker()
        if mastery_tracker:
            # Build interaction context (KEEP ALL ORIGINAL DATA)
            interaction_context = {
                'go_data': {
                    'go_id': go_id,
                    'skill_name': current_question.get("skill_name", "Quiz Question"),
                    'description': current_question.get("text", "Quiz question")
                },
                'lo_data': {
                    'title': f"Learning Objective Week {week}"
                },
                'week_topic': f"Week {week}",
                'course_code': course,
                'is_quiz': True,
                'correct': quiz_result.get("correct", False),
                'score': quiz_result.get("score", 0.0),
                'username': username,
                'question_number': st.session_state.quiz_progress['current'],
                'quiz_data': st.session_state.current_quiz_data,
                'quiz_in_progress': True  # NEW: Flag to defer week advancement
            }
            
            # Create synthetic response for mastery assessment
            is_correct = quiz_result.get("correct", False)
            student_response = f"Quiz answer: {answer} (Result: {'Correct' if is_correct else 'Incorrect'})"
            
            # STEP 1: Update mastery system (UNCHANGED - this works fine)
            try:
                import asyncio
                import concurrent.futures
                
                def update_mastery_sync():
                    return asyncio.run(mastery_tracker.update_learner_mastery(
                        username, course, student_response, go_id, 
                        f"LO_{week:02d}_01", week, interaction_context
                    ))
                
                # Use thread executor for async operation
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(update_mastery_sync)
                    mastery_result = future.result(timeout=10)
                    
                if mastery_result:
                    print(f"DEBUG: ✅ QUIZ MASTERY: Updated for {go_id} - Correct: {is_correct}")
                    
                    # STEP 2: QUIZ-SAFE progress update (NO WEEK ADVANCEMENT)
                    print(f"DEBUG: 🔧 QUIZ MASTERY: Applying quiz-safe progress update")
                    
                    # Get fresh mastery data (this part works)
                    fresh_mastery_summary = mastery_tracker._format_mastery_summary(mastery_result)
                    
                    # SIMPLIFIED progress update for quiz mode
                    progress_bridge = get_progress_bridge()
                    if progress_bridge:
                        try:
                            # Use QUIZ-SAFE bridge method that defers week advancement
                            import threading
                            import time
                            
                            progress_result = None
                            progress_exception = None
                            
                            def run_quiz_safe_progress_update():
                                nonlocal progress_result, progress_exception
                                try:
                                    # CALL the quiz-safe method
                                    progress_result = progress_bridge.update_progress_quiz_safe(
                                        username, course, week, interaction_context, fresh_mastery_summary
                                    )
                                except Exception as e:
                                    progress_exception = e
                            
                            # Run in thread with timeout
                            progress_thread = threading.Thread(target=run_quiz_safe_progress_update)
                            progress_thread.daemon = True
                            progress_thread.start()
                            progress_thread.join(timeout=3.0)  # 3 second timeout
                            
                            if progress_thread.is_alive():
                                print(f"DEBUG: ⚠️ QUIZ MASTERY: Progress bridge timed out, using direct update")
                                
                                # DIRECT SIMPLE UPDATE (bypass bridge entirely)
                                if is_correct:
                                    auth_service = get_auth_service()
                                    if auth_service:
                                        # Calculate increment: 1 per completed GO
                                        increment = 1.0 / 11  # 11 total GOs in week
                                        
                                        try:
                                            auth_service.redis_client.update_user_progress(
                                                username=username,
                                                course=course,
                                                week=week,
                                                increment_completion=increment
                                            )
                                            print(f"DEBUG: ✅ QUIZ MASTERY: Direct progress increment: {increment:.3f}")
                                            st.success(f"✅ Progress: +{increment*100:.1f}%")
                                        except Exception as e:
                                            print(f"DEBUG: ❌ QUIZ MASTERY: Direct progress update failed: {e}")
                                
                            elif progress_exception:
                                print(f"DEBUG: ❌ QUIZ MASTERY: Progress bridge failed: {progress_exception}")
                                
                                # FALLBACK: Direct simple update
                                if is_correct:
                                    auth_service = get_auth_service()
                                    if auth_service:
                                        increment = 1.0 / 11
                                        auth_service.redis_client.update_user_progress(
                                            username=username,
                                            course=course,
                                            week=week,
                                            increment_completion=increment
                                        )
                                        print(f"DEBUG: ✅ QUIZ MASTERY: Fallback progress increment: {increment:.3f}")
                                        st.success(f"✅ Progress: +{increment*100:.1f}%")
                                        
                            elif progress_result:
                                print(f"DEBUG: ✅ QUIZ MASTERY: Quiz-safe progress bridge worked!")
                                
                                if progress_result.get("progress_updated"):
                                    completion_change = progress_result.get('completion_change', 0)
                                    print(f"DEBUG: 🚀 QUIZ MASTERY: Progress updated! Completion change: {completion_change:.3f}")
                                    
                                    # Show achievements in UI (NO WEEK ADVANCEMENT DURING QUIZ)
                                    achievements = progress_result.get("achievements", [])
                                    if achievements:
                                        for achievement in achievements:
                                            st.success(f"🎉 {achievement}")
                                    
                                    # DEFER week advancement notification until quiz end
                                    if progress_result.get("week_advancement_ready"):
                                        st.session_state.pending_week_advancement = {
                                            "next_week": progress_result.get("next_week"),
                                            "mastery_level": progress_result.get("mastery_level", 0.0)
                                        }
                                        print(f"DEBUG: 📋 QUIZ MASTERY: Week advancement deferred until quiz completion")
                                else:
                                    # Bridge ran but no progress - try simple increment
                                    if is_correct:
                                        auth_service = get_auth_service()
                                        if auth_service:
                                            increment = 1.0 / 11
                                            auth_service.redis_client.update_user_progress(
                                                username=username,
                                                course=course,
                                                week=week,
                                                increment_completion=increment
                                            )
                                            print(f"DEBUG: ✅ QUIZ MASTERY: Bridge failed, applied direct increment: {increment:.3f}")
                                            st.success(f"✅ Progress: +{increment*100:.1f}%")
                                
                        except Exception as e:
                            print(f"DEBUG: ❌ QUIZ MASTERY: Threading approach failed: {e}")
                            
                            # ULTIMATE FALLBACK: Simple direct update
                            if is_correct:
                                auth_service = get_auth_service()
                                if auth_service:
                                    increment = 1.0 / 11
                                    auth_service.redis_client.update_user_progress(
                                        username=username,
                                        course=course,
                                        week=week,
                                        increment_completion=increment
                                    )
                                    print(f"DEBUG: ✅ QUIZ MASTERY: Ultimate fallback increment: {increment:.3f}")
                                    st.success(f"✅ Progress: +{increment*100:.1f}%")
                    
                    else:
                        print("DEBUG: ⚠️ QUIZ MASTERY: No progress bridge available, using direct update")
                        
                        # Direct update without bridge
                        if is_correct:
                            auth_service = get_auth_service()
                            if auth_service:
                                increment = 1.0 / 11
                                auth_service.redis_client.update_user_progress(
                                    username=username,
                                    course=course,
                                    week=week,
                                    increment_completion=increment
                                )
                                print(f"DEBUG: ✅ QUIZ MASTERY: No bridge, direct increment: {increment:.3f}")
                                st.success(f"✅ Progress: +{increment*100:.1f}%")
                    
                    # PRESERVE: Force UI refresh
                    trigger_mastery_refresh()
                    return True
                        
            except Exception as e:
                print(f"DEBUG: ❌ QUIZ MASTERY: Mastery update failed: {e}")
                return False
                    
        return False
        
    except Exception as e:
        print(f"DEBUG: ❌ QUIZ MASTERY: Error in enhanced mastery update: {e}")
        import traceback
        traceback.print_exc()
        return False

def trigger_mastery_refresh():
    """FIXED: Function to trigger mastery refresh with proper scoping"""
    try:
        username = st.session_state.get("username")
        course = st.session_state.get("selected_course")
        
        if username and course:
            # Set flags in Redis
            auth_service = get_auth_service()
            if auth_service and auth_service.redis_client:
                # Check for update flags
                update_flag = auth_service.redis_client.get_mastery_update_flag(username, course)
                if update_flag:
                    print(f"DEBUG: ⚡ Found mastery update flag: {update_flag}")
            
            # Set Streamlit session state flags
            st.session_state["force_mastery_refresh"] = True
            st.session_state["mastery_refresh_timestamp"] = time.time()
            
            # Clear any caching that might prevent updates
            if hasattr(st, 'cache_data'):
                st.cache_data.clear()
            
            print(f"DEBUG: ⚡ Forced mastery refresh for {username} in {course}")
            
    except Exception as e:
        print(f"DEBUG: Error forcing mastery refresh: {e}")

def record_quiz_interaction_sync(answer: str, quiz_result: Dict):
    """FIXED: Renamed from record_quiz_interaction_with_mastery_sync for consistency"""
    try:
        # Check if orchestrator already processed this
        if st.session_state.get('_orchestrator_processed', False):
            print("DEBUG: Skipping duplicate mastery processing - orchestrator already handled it")
            # Reset flag
            st.session_state._orchestrator_processed = False
            return
        
        # Basic interaction recording
        print("DEBUG: Recording quiz interaction")
        auth_service = get_auth_service()
        if auth_service and hasattr(auth_service, 'redis_client'):
            try:
                username = st.session_state.username
                course = st.session_state.selected_course
                interaction_record = {
                    "timestamp": datetime.now().isoformat(),
                    "type": "quiz_answer",
                    "answer": answer[:100],
                    "is_correct": quiz_result.get("correct", False),
                    "score": quiz_result.get("score", 0.0),
                    "question_number": st.session_state.quiz_progress["current"]
                }
                history_key = f"interaction_history:{username}:{course}"
                auth_service.redis_client.get_redis().lpush(history_key, json.dumps(interaction_record))
                print("DEBUG: Quiz interaction recorded to Redis")
            except Exception as e:
                print(f"DEBUG: Basic recording failed: {e}")
        
        print("DEBUG: Quiz interaction recording completed")
            
    except Exception as e:
        print(f"DEBUG: Quiz interaction recording failed: {e}")

# =============================================================================
# CONSOLIDATED ORCHESTRATOR FUNCTIONS
# =============================================================================

def process_orchestrator_interaction(
    orchestrator, 
    interaction_type: str,
    student_input: str, 
    session_context: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """FIXED: Enhanced orchestrator processing with scaffolding integration"""
    try:
        username = st.session_state.username
        course = st.session_state.selected_course
        
        print(f"DEBUG: Processing {interaction_type} with {'MCP' if hasattr(orchestrator, 'mcp_client') else 'Fallback'} orchestrator")
        
        # Check if this is the full MCP orchestrator
        if hasattr(orchestrator, 'mcp_client') and hasattr(orchestrator, 'scaffolding_engine'):
            print("DEBUG: 🚀 Using FULL MCP Orchestrator with scaffolding!")
            
            # Use the full MCP orchestrator with scaffolding
            return run_async_safely(orchestrator.process_interaction(
                username=username,
                course=course,
                interaction_type=_map_interaction_type(interaction_type),
                student_input=student_input,
                current_mode=interaction_type.lower(),
                session_context=session_context
            ))
        
        elif hasattr(orchestrator, 'mcp_client'):
            print("DEBUG: 🔧 Using MCP Orchestrator (no scaffolding)")
            
            # Use MCP orchestrator without scaffolding
            return run_async_safely(orchestrator.process_interaction(
                username=username,
                course=course,
                interaction_type=_map_interaction_type(interaction_type),
                student_input=student_input,
                current_mode=interaction_type.lower(),
                session_context=session_context
            ))
        
        else:
            print("DEBUG: 📱 Using Fallback Orchestrator")
            
            # Use fallback orchestrator
            return run_async_safely(orchestrator.process_interaction(
                username=username,
                course=course,
                interaction_type=interaction_type,
                student_input=student_input,
                current_mode=interaction_type.lower(),
                session_context=session_context
            ))
            
    except Exception as e:
        print(f"DEBUG: Orchestrator processing error: {e}")
        return None

def _map_interaction_type(interaction_type_str: str):
    """Map string interaction type to enum for MCP orchestrator"""
    try:
        from src.core.agent_orchestrator_mcp import InteractionType
        
        mapping = {
            "quiz": InteractionType.QUIZ_ANSWER,
            "tutor": InteractionType.TUTOR_RESPONSE,
            "chat": InteractionType.CHAT_QUERY
        }
        
        return mapping.get(interaction_type_str.lower(), InteractionType.CHAT_QUERY)
    except ImportError:
        return interaction_type_str

def _process_mcp_interaction(
    orchestrator, interaction_type: str, username: str, course: str,
    student_input: str, session_context: Dict
) -> Dict[str, Any]:
    """Process interaction with MCP orchestrator"""
    try:
        from src.core.agent_orchestrator import InteractionType
        
        # Map string interaction types to enum
        interaction_type_map = {
            "quiz": InteractionType.QUIZ_ANSWER,
            "tutor": InteractionType.TUTOR_RESPONSE,
            "chat": InteractionType.CHAT_MESSAGE
        }
        
        enum_interaction_type = interaction_type_map.get(interaction_type.lower(), InteractionType.CHAT_MESSAGE)
        
        def mcp_async():
            return asyncio.run(orchestrator.process_interaction(
                username=username,
                course=course,
                interaction_type=enum_interaction_type,
                student_input=student_input,
                current_mode=interaction_type.lower(),
                session_context=session_context
            ))
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(mcp_async)
            result = future.result(timeout=30)
            
        return result
        
    except Exception as e:
        print(f"DEBUG: MCP interaction processing failed: {e}")
        return {"success": False, "error": str(e)}

def _process_regular_interaction(
    orchestrator, interaction_type: str, username: str, course: str,
    student_input: str, session_context: Dict
) -> Dict[str, Any]:
    """Process interaction with regular orchestrator"""
    try:
        from src.core.agent_orchestrator import InteractionType
        
        # Map string interaction types to enum
        interaction_type_map = {
            "quiz": InteractionType.QUIZ_ANSWER,
            "tutor": InteractionType.TUTOR_RESPONSE,
            "chat": InteractionType.CHAT_MESSAGE
        }
        
        enum_interaction_type = interaction_type_map.get(interaction_type.lower(), InteractionType.CHAT_MESSAGE)
        
        print(f"DEBUG: Regular orchestrator - mapping '{interaction_type}' to {enum_interaction_type}")
        
        result = run_async_safely(orchestrator.process_interaction(
            username=username,
            course=course,
            interaction_type=enum_interaction_type,
            student_input=student_input,
            current_mode=interaction_type.lower(),
            session_context=session_context
        ))
        
        return result
        
    except Exception as e:
        print(f"DEBUG: Regular orchestrator processing failed: {e}")
        return {"success": False, "error": str(e)}

def update_cognitive_load_from_orchestrator(orchestrator_result, enhanced_context):
    """Update cognitive load from orchestrator result"""
    try:
        cognitive_state = orchestrator_result['cognitive_state']
        st.session_state["cognitive_load"] = {
            "cl_value": cognitive_state.cognitive_load,
            "zpd_score": cognitive_state.zpd_score,
            "motivation": cognitive_state.motivation_score,
            "fatigue": cognitive_state.fatigue_level,
            "timestamp": time.time(),
            "question_number": st.session_state.quiz_progress["current"],
            "formula_variables": {
                "accuracy": cognitive_state.zpd_score,
                "difficulty": enhanced_context.get('current_difficulty', 0.5),
                "interaction_count": st.session_state.quiz_progress["current"]
            }
        }
        
        if 'scaffolding_strategy' in orchestrator_result:
            st.session_state["scaffolding"] = orchestrator_result['scaffolding_strategy']
        
        print(f"DEBUG: Updated CL from orchestrator: {cognitive_state.cognitive_load:.2f}, ZPD: {cognitive_state.zpd_score:.2f}")
        
    except Exception as e:
        print(f"DEBUG: Error updating CL from orchestrator: {e}")

def update_cognitive_load_simple_analytics(quiz_result):
    """Update cognitive load using simple analytics fallback"""
    try:
        simple_analytics = get_simple_analytics()
        if simple_analytics:
            current_question = st.session_state.current_quiz_data.get("current_question", {})
            question_type = current_question.get("type", "multiple_choice")
            
            analytics_result = simple_analytics.calculate_learning_metrics(
                quiz_results=st.session_state.quiz_results + [quiz_result],
                question_number=st.session_state.quiz_progress["current"],
                current_question_type=question_type
            )
            
            st.session_state["cognitive_load"] = {
                "cl_value": analytics_result['cognitive_load'],
                "zpd_score": analytics_result['zpd_score'],
                "motivation": analytics_result['motivation'],
                "fatigue": analytics_result['fatigue'],
                "timestamp": time.time(),
                "question_number": st.session_state.quiz_progress["current"],
                "formula_variables": {
                    "accuracy": analytics_result['zpd_score'],
                    "difficulty": analytics_result['difficulty'],
                    "interaction_count": analytics_result['question_number'],
                    "task_type": analytics_result['task_type']
                }
            }
            
            print(f"DEBUG: Updated learning analytics with simple calculator")
            
    except Exception as e:
        print(f"DEBUG: Simple analytics calculation failed: {e}")

def apply_tutor_orchestrator_enhancements(tutor_message: str, orchestrator_result: Dict) -> str:
    """Apply orchestrator enhancements specifically for tutor mode"""
    
    scaffolding = orchestrator_result.get('scaffolding_strategy', {})
    motivation = orchestrator_result.get('motivation_feedback', {})
    cognitive_state = orchestrator_result.get('cognitive_state')
    
    enhanced_message = tutor_message
    
    intervention_type = scaffolding.get('intervention_type')
    if intervention_type == 'immediate_support':
        enhanced_message = "Let me help you break this down step by step. " + enhanced_message
    elif intervention_type == 'advanced_challenge':
        enhanced_message += " Since you've got this concept down, let's try something more challenging!"
    elif intervention_type == 'concept_review':
        enhanced_message += " It might help to review the foundation concept first."
    
    if motivation.get('confidence_boost'):
        enhanced_message = "You're making great progress! " + enhanced_message
    elif motivation.get('challenge_ready'):
        enhanced_message += " You're ready for the next level!"
    
    if cognitive_state and cognitive_state.cognitive_load > 7:
        enhanced_message += "\n\nTake your time with this - there's no rush."
    elif cognitive_state and cognitive_state.cognitive_load < 3:
        enhanced_message += "\n\nWhat questions do you have about this?"
    
    return enhanced_message

def display_motivation_state_in_sidebar():
    """ENHANCED: Display motivation state and metrics in sidebar"""
    if "orchestrator_context" in st.session_state and st.session_state["orchestrator_context"]:
        orchestrator_context = st.session_state["orchestrator_context"]
        
        # Extract motivation data
        motivation_state = orchestrator_context.get('motivation_state', 'unknown')
        motivation_metrics = orchestrator_context.get('motivation_metrics')
        motivation_feedback = orchestrator_context.get('motivation_feedback', {})
        
        with st.sidebar:
            with st.expander("🎯 Motivation Analytics", expanded=True):
                
                # Motivation State Display
                state_config = {
                    'cold_start': {'emoji': '🌱', 'color': 'blue', 'desc': 'Getting Started'},
                    'motivation_drop': {'emoji': '⚠️', 'color': 'red', 'desc': 'Need Support'},
                    'motivation_plateau': {'emoji': '✅', 'color': 'green', 'desc': 'Steady Progress'},
                    'maintained_high': {'emoji': '🚀', 'color': 'purple', 'desc': 'High Engagement'}
                }
                
                config = state_config.get(motivation_state, {'emoji': '❓', 'color': 'gray', 'desc': 'Unknown'})
                
                # State indicator
                st.markdown(f"### {config['emoji']} **{config['desc']}**")
                st.caption(f"Current motivation state: {motivation_state.replace('_', ' ').title()}")
                
                if motivation_metrics:
                    # Key metrics display
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Persistence level
                        persistence = motivation_metrics.persistence_level
                        persistence_emoji = {
                            'early_abandonment': '🔴',
                            'decreased_persistence': '🟡', 
                            'maintains_persistence': '🟢',
                            'enhanced_persistence': '⭐'
                        }
                        st.metric(
                            "Persistence", 
                            persistence.replace('_', ' ').title()[:10],
                            delta=persistence_emoji.get(persistence, '❓')
                        )
                    
                    with col2:
                        # Affective score
                        affective_score = motivation_metrics.affective_score
                        if affective_score > 0.3:
                            affective_status = "Positive 😊"
                        elif affective_score < -0.3:
                            affective_status = "Negative 😔"
                        else:
                            affective_status = "Neutral 😐"
                        
                        st.metric("Mood", affective_status, delta=f"{affective_score:.2f}")
                    
                    # Performance trend
                    performance_score = motivation_metrics.performance_score
                    st.progress(performance_score)
                    st.caption(f"Performance: {performance_score*100:.0f}%")
                    
                    # Session completion
                    completion_rate = motivation_metrics.session_completion_rate
                    if completion_rate > 0:
                        st.caption(f"Session completion: {completion_rate*100:.0f}%")
                
                # Motivation feedback display
                if motivation_feedback:
                    strategy = motivation_feedback.get('strategy', 'maintain_flow')
                    tone = motivation_feedback.get('tone', 'encouraging')
                    
                    st.markdown("---")
                    st.markdown("**🎯 Current Strategy:**")
                    st.caption(f"• Approach: {strategy.replace('_', ' ').title()}")
                    st.caption(f"• Tone: {tone.title()}")
                    
                    # Challenge level indicator
                    challenge_level = motivation_feedback.get('challenge_level', 'maintain')
                    challenge_emoji = {
                        'reduce': '📉 Easier',
                        'maintain': '➡️ Same Level', 
                        'increase': '📈 More Challenge'
                    }
                    st.caption(f"• Next: {challenge_emoji.get(challenge_level, 'No Change')}")
                    
                    # System adjustments
                    adjustments = motivation_feedback.get('system_adjustments', {})
                    if adjustments:
                        active_adjustments = [k for k, v in adjustments.items() if v]
                        if active_adjustments:
                            st.markdown("**⚙️ Active Supports:**")
                            for adj in active_adjustments[:3]:
                                st.caption(f"• {adj.replace('_', ' ').title()}")

def update_session_state_with_motivation(orchestrator_result):
    """Store orchestrator results in session state for UI display"""
    if orchestrator_result and orchestrator_result.get('processing_successful', False):
        st.session_state["orchestrator_context"] = {
            'motivation_state': orchestrator_result.get('motivation_state', 'unknown'),
            'motivation_metrics': orchestrator_result.get('motivation_metrics'),
            'motivation_feedback': orchestrator_result.get('motivation_feedback', {}),
            'cognitive_state': orchestrator_result.get('cognitive_state'),
            'scaffolding_strategy': orchestrator_result.get('scaffolding_strategy', {}),
            'timestamp': time.time()
        }
        print(f"DEBUG: ✅ Motivation context stored - State: {orchestrator_result.get('motivation_state')}")

def show_motivation_feedback_message():
    """Display motivation feedback message to user when appropriate"""
    if "orchestrator_context" in st.session_state:
        orchestrator_context = st.session_state["orchestrator_context"]
        motivation_feedback = orchestrator_context.get('motivation_feedback', {})
        
        # Check if feedback message should be shown
        feedback_message = motivation_feedback.get('feedback_message', '')
        if feedback_message and feedback_message.strip():
            
            # Determine message type based on motivation state
            motivation_state = orchestrator_context.get('motivation_state', 'unknown')
            
            if motivation_state == 'motivation_drop':
                st.warning(f"💝 **Motivational Support:** {feedback_message}")
            elif motivation_state == 'maintained_high':
                st.success(f"🚀 **Challenge Ready:** {feedback_message}")
            elif motivation_state == 'cold_start':
                st.info(f"🌱 **Welcome:** {feedback_message}")
            else:
                st.info(f"✨ **Learning Tip:** {feedback_message}")

def apply_motivation_informed_ui_adjustments():
    """Apply motivation-informed UI adjustments"""
    if "orchestrator_context" in st.session_state:
        orchestrator_context = st.session_state["orchestrator_context"]
        motivation_feedback = orchestrator_context.get('motivation_feedback', {})
        
        # Get system adjustments
        adjustments = motivation_feedback.get('system_adjustments', {})
        
        # Apply UI modifications based on adjustments
        if adjustments.get('reduce_pressure', False):
            st.markdown("""
            <style>
            .stButton > button {
                background-color: #28a745;
                border-color: #28a745;
            }
            </style>
            """, unsafe_allow_html=True)
        
        if adjustments.get('increase_encouragement', False):
            # Add encouraging visual elements
            if not st.session_state.get('encouragement_shown', False):
                st.balloons()
                st.session_state.encouragement_shown = True
        
        if adjustments.get('minimize_controlling_language', False):
            # Flag for content generation to use softer language
            st.session_state['use_soft_language'] = True
        
        return adjustments
    
    return {}

# =============================================================================
# SESSION STATE INITIALIZATION
# =============================================================================

def initialize_session_state():
    """Initialize session state variables"""
    
    # Authentication
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'username' not in st.session_state:
        st.session_state.username = ""
    
    # Course selection
    if 'selected_course' not in st.session_state:
        st.session_state.selected_course = None
    if 'selected_week' not in st.session_state:
        st.session_state.selected_week = 1
    if 'enrolled_courses' not in st.session_state:
        st.session_state.enrolled_courses = []
    if 'course_weeks' not in st.session_state:
        st.session_state.course_weeks = {}

    # Default to CHAT mode
    if 'current_mode' not in st.session_state:
        st.session_state.current_mode = AppMode.CHAT
    if 'mode_history' not in st.session_state:
        st.session_state.mode_history = []
    
    # Quiz state - SIMPLE APPROACH
    if 'quiz_active' not in st.session_state:
        st.session_state.quiz_active = False
    if 'current_quiz_data' not in st.session_state:
        st.session_state.current_quiz_data = None
    if 'quiz_progress' not in st.session_state:
        st.session_state.quiz_progress = {"current": 0, "total": 0, "correct": 0}
    if 'quiz_results' not in st.session_state:
        st.session_state.quiz_results = []
    if 'show_feedback' not in st.session_state:
        st.session_state.show_feedback = False
    if 'current_feedback' not in st.session_state:
        st.session_state.current_feedback = None
    if 'quiz_completed' not in st.session_state:
        st.session_state.quiz_completed = False
    
    # NEW: Week advancement state
    if 'pending_week_advancement' not in st.session_state:
        st.session_state.pending_week_advancement = None

    # Chat state
    if 'chat_messages' not in st.session_state:
        st.session_state.chat_messages = []
    if 'chat_context' not in st.session_state:
        st.session_state.chat_context = {}
    if 'chat_session_id' not in st.session_state:
        st.session_state.chat_session_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Tutor state
    if 'tutor_session' not in st.session_state:
        st.session_state.tutor_session = None
    if 'tutor_active' not in st.session_state:
        st.session_state.tutor_active = False
    if 'tutor_messages' not in st.session_state:
        st.session_state.tutor_messages = []

    # Mastery tracking state
    if 'mastery_updated_timestamp' not in st.session_state:
        st.session_state.mastery_updated_timestamp = 0
    if 'last_mastery_update' not in st.session_state:
        st.session_state.last_mastery_update = {}
    if 'force_mastery_refresh' not in st.session_state:
        st.session_state.force_mastery_refresh = False
    if 'mastery_refresh_timestamp' not in st.session_state:
        st.session_state.mastery_refresh_timestamp = 0

# USER DATA MANAGEMENT
def load_user_data_after_login(username: str):
    """ENHANCED: Load user data with integrated progress"""
    auth_service = get_auth_service()
    if not auth_service:
        return
    
    try:
        user_data = auth_service.get_user_data(username)
        st.session_state.enrolled_courses = user_data.get("enrolled_courses", [])
        
        if st.session_state.enrolled_courses:
            st.session_state.selected_course = st.session_state.enrolled_courses[0]
            load_course_weeks()
            
            # 🚨 NEW: Load integrated progress data
            progress_bridge = get_progress_bridge()
            if progress_bridge:
                progress_summary = progress_bridge.get_progress_summary(
                    username, st.session_state.selected_course
                )
                
                # Set week based on progress (not just default to first course)
                current_week = progress_summary.get("current_week", 1)
                st.session_state.selected_week = current_week
                
                print(f"DEBUG: 📊 Loaded integrated progress - Week: {current_week}, Completion: {progress_summary.get('week_completion', 0):.1%}")
                
                # Store progress summary for sidebar display
                st.session_state["integrated_progress"] = progress_summary
        
        print(f"DEBUG: Loaded enhanced user data for {username}")
        
    except Exception as e:
        print(f"DEBUG: Error loading user data: {e}")

def get_current_kc_loader():
    """Get KCModelLoader for currently selected course (dynamic)"""
    # Get the current course from session state, default to DEMO101
    current_course = st.session_state.get("selected_course", "DEMO101")
    return get_kc_loader_for_module(current_course)

def load_course_weeks():
    """Load course weeks with proper week_display"""
    if not st.session_state.selected_course:
        return
    
    # Use course-specific KC loader
    kc_loader = get_current_kc_loader()
    if not kc_loader:
        return
    
    try:
        kc_model = kc_loader.load_course_model(st.session_state.selected_course)
        course_weeks = {}
        
        for week_key, week_data in kc_model["week_navigation"].items():
            week_number = week_data["week_number"]
            week_display = week_data.get("week_display", f"Week {week_number}")
            
            if not week_display:
                week_name = week_data.get("week_name", week_data.get("topic", f"Week {week_number}"))
                week_display = f"Week {week_number}: {week_name}"
            
            los = []
            total_gos = 0
            for lo in week_data.get("learning_objectives", []):
                go_count = len(lo.get("granular_objectives", []))
                total_gos += go_count
                los.append({
                    "id": lo["lo_id"],
                    "title": lo.get("title", lo.get("objective_name", "Learning Objective")),
                    "granular_count": go_count
                })
            
            course_weeks[week_display] = {
                "week_number": week_number,
                "learning_objectives": los,
                "total_questions": total_gos
            }
        
        st.session_state.course_weeks = course_weeks
        print(f"DEBUG: Loaded {len(course_weeks)} weeks for {st.session_state.selected_course}")
        
    except Exception as e:
        print(f"DEBUG: Error loading course weeks for {st.session_state.selected_course}: {e}")

def display_mastery_progress_in_sidebar():
    """ENHANCED: Display integrated progress with mastery insights"""
    try:
        username = st.session_state.get("username")
        course = st.session_state.get("selected_course")
        current_week = st.session_state.get("selected_week", 1)
        
        if not username or not course:
            return

        # Check if we need to force refresh
        force_refresh = st.session_state.get("force_mastery_refresh", False)
        if force_refresh:
            st.session_state["force_mastery_refresh"] = False
            print("DEBUG: Performing forced mastery refresh")

        # 🚨 NEW: Get integrated progress summary
        progress_bridge = get_progress_bridge()
        if progress_bridge:
            integrated_summary = progress_bridge.get_progress_summary(username, course)
        else:
            integrated_summary = {}

        with st.sidebar:
            with st.expander("📊 Your Learning Progress", expanded=True):
                
                # Show last update timestamp
                last_update = st.session_state.get("mastery_refresh_timestamp")
                if last_update:
                    seconds_ago = int(time.time() - last_update)
                    if seconds_ago < 10:
                        st.success(f"🔄 Just updated! ({seconds_ago}s ago)")
                    else:
                        st.info(f"📊 Updated {seconds_ago}s ago")
                
                # 🚨 NEW: Display integrated progress
                if integrated_summary:
                    # Current week progress
                    week_completion = integrated_summary.get("week_completion", 0.0)
                    st.metric(
                        f"Week {current_week} Progress", 
                        f"{week_completion*100:.0f}%",
                        delta=f"Current Week"
                    )
                    
                    # Overall course progress
                    overall_progress = integrated_summary.get("overall_course_progress", 0.0)
                    st.metric(
                        "Course Progress",
                        f"{overall_progress*100:.0f}%",
                        delta=f"{course} Overall"
                    )
                    
                    # Progress bar
                    st.progress(week_completion)
                    
                    # Ready for next week?
                    if integrated_summary.get("ready_for_next_week", False):
                        st.success("🚀 Ready for next week!")
                    else:
                        st.info("📚 Keep learning current week")
                    
                    # Recent achievements
                    achievements = integrated_summary.get("recent_achievements", [])
                    if achievements:
                        st.markdown("**🎉 Recent Achievements:**")
                        for achievement in achievements[:3]:
                            st.text(f"✅ {achievement}")
                    
                    # Total interactions
                    total_interactions = integrated_summary.get("total_interactions", 0)
                    if total_interactions > 0:
                        st.metric("Total Learning Activities", total_interactions)
                        
                        if total_interactions > 20:
                            st.success("🚀 Highly Engaged Learner!")
                        elif total_interactions > 10:
                            st.info("📈 Good Learning Momentum!")
                        else:
                            st.info("🌱 Building Learning Foundation")
                else:
                    # Fallback to original mastery display
                    st.info("🔄 Loading your progress...")
                
    except Exception as e:
        print(f"DEBUG: Error displaying integrated progress: {e}")
        # Show fallback progress indicator
        with st.sidebar:
            with st.expander("📊 Your Learning Progress", expanded=False):
                st.info("🔄 Loading your progress...")

def display_go_level_progress_in_sidebar():
    """Display GO-level progress in sidebar"""
    try:
        go_components = get_go_strategy_components()
        if not go_components:
            return
        
        username = st.session_state.get("username")
        course = st.session_state.get("selected_course") 
        week = st.session_state.get("selected_week", 1)
        
        if not username or not course:
            return
        
        # Get GO sequence and progress
        go_sequence = go_components["go_sequencer"].get_week_go_sequence(course, week)
        tutor_sequencer = go_components["tutor_sequencer"]
        user_progress = tutor_sequencer._load_user_go_progress(username, course, week)
        
        with st.sidebar:
            with st.expander("🎯 Learning Objectives Progress", expanded=True):
                if go_sequence:
                    mastered_count = 0
                    total_count = len(go_sequence)
                    
                    for go_data in go_sequence:
                        go_id = go_data["go_id"]
                        progress = user_progress.get(go_id)
                        
                        if progress:
                            mastery_pct = progress.current_mastery * 100
                            
                            if progress.mastery_achieved:
                                status = "✅ Mastered"
                                mastered_count += 1
                            elif mastery_pct >= 70:
                                status = "🟡 Almost There"
                            elif mastery_pct >= 40:
                                status = "🔄 Learning"
                            else:
                                status = "🔴 Just Started"
                            
                            st.markdown(f"**{go_data['skill_name'][:30]}...**")
                            st.progress(progress.current_mastery)
                            col1, col2 = st.columns(2)
                            with col1:
                                st.caption(f"{mastery_pct:.1f}%")
                            with col2:
                                st.caption(f"{status}")
                        else:
                            st.markdown(f"**{go_data['skill_name'][:30]}...**")
                            st.progress(0.0)
                            st.caption("⭕ Not started")
                    
                    # Summary
                    st.markdown("---")
                    st.metric("Week Progress", f"{mastered_count}/{total_count}", 
                             delta=f"{(mastered_count/total_count)*100:.0f}% Complete")
                    
                else:
                    st.info("🔄 Loading learning objectives...")
                    
    except Exception as e:
        print(f"DEBUG: Error displaying GO progress: {e}")
        
def get_mastery_data_safely(username: str, course: str) -> Dict[str, Any]:
    """Get mastery data via orchestrator if available, otherwise fallback"""
    try:
        # Try to get orchestrator
        orchestrator = get_orchestrator()
        if orchestrator and hasattr(orchestrator, 'mcp_client'):
            # Use MCP client if available
            try:
                # Handle async properly in Streamlit context
                import asyncio
                
                def get_mastery_async():
                    return asyncio.run(orchestrator.mcp_client.get_mastery_summary(username, course))
                
                # Use thread executor for async operation
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(get_mastery_async)
                    result = future.result(timeout=5)
                    
                if result.get("success", False):
                    return format_mastery_for_ui(result)
            except Exception as e:
                print(f"DEBUG: MCP mastery retrieval failed: {e}")
        
        # Fallback to direct mastery tracker access
        mastery_tracker = get_mastery_tracker()
        if mastery_tracker:
            mastery_data = mastery_tracker.get_mastery_summary(username, course)
            return format_mastery_for_ui(mastery_data)
        
        # Final fallback to cached data
        return get_cached_mastery_data(username, course)
        
    except Exception as e:
        print(f"DEBUG: Error getting mastery data safely: {e}")
        return get_default_mastery_data(username, course)

def get_cached_mastery_data(username: str, course: str) -> Dict[str, Any]:
    """Get cached mastery data from Redis or file storage"""
    try:
        # Try Redis first
        auth_service = get_auth_service()
        if auth_service and hasattr(auth_service, 'redis_client'):
            key = f"mastery:{username}:{course}"
            cached_data = auth_service.redis_client.get_redis().get(key)
            if cached_data:
                mastery_data = json.loads(cached_data)
                return format_mastery_for_ui(mastery_data)
        
        # Try file storage
        from pathlib import Path
        file_path = Path(f"./data/mastery_tracking/mastery_{username}_{course}.json")
        if file_path.exists():
            with open(file_path, 'r') as f:
                mastery_data = json.load(f)
                return format_mastery_for_ui(mastery_data)
                
    except Exception as e:
        print(f"DEBUG: Error getting cached mastery data: {e}")
    
    return get_default_mastery_data(username, course)

def format_mastery_for_ui(mastery_data: Dict) -> Dict[str, Any]:
    """Format raw mastery data for UI display"""
    try:
        # Extract mastery levels
        go_masteries = {}
        lo_masteries = {}
        week_masteries = {}
        
        # Handle different formats
        if "go_masteries" in mastery_data:
            for go_id, mastery_info in mastery_data["go_masteries"].items():
                if isinstance(mastery_info, dict) and "level" in mastery_info:
                    go_masteries[go_id] = mastery_info["level"]
                else:
                    go_masteries[go_id] = float(mastery_info)
        
        if "lo_masteries" in mastery_data:
            for lo_id, mastery_info in mastery_data["lo_masteries"].items():
                if isinstance(mastery_info, dict) and "level" in mastery_info:
                    lo_masteries[lo_id] = mastery_info["level"]
                else:
                    lo_masteries[lo_id] = float(mastery_info)
        
        if "week_masteries" in mastery_data:
            for week_str, mastery_info in mastery_data["week_masteries"].items():
                week_num = int(week_str)
                if isinstance(mastery_info, dict) and "level" in mastery_info:
                    week_masteries[week_num] = mastery_info["level"]
                else:
                    week_masteries[week_num] = float(mastery_info)
        
        # Course mastery
        course_mastery = 0.0
        if "course_mastery" in mastery_data:
            course_info = mastery_data["course_mastery"]
            if isinstance(course_info, dict) and "level" in course_info:
                course_mastery = course_info["level"]
            else:
                course_mastery = float(course_info)
        
        # Calculate averages
        go_avg = sum(go_masteries.values()) / len(go_masteries) if go_masteries else 0.0
        lo_avg = sum(lo_masteries.values()) / len(lo_masteries) if lo_masteries else 0.0
        week_avg = sum(week_masteries.values()) / len(week_masteries) if week_masteries else 0.0
        
        return {
            "go_masteries": go_masteries,
            "lo_masteries": lo_masteries,
            "week_masteries": week_masteries,
            "course_mastery": course_mastery,
            "averages": {
                "go_mastery": go_avg,
                "lo_mastery": lo_avg,
                "week_mastery": week_avg
            },
            "mastery_counts": {
                "go_tracked": len(go_masteries),
                "lo_tracked": len(lo_masteries),
                "weeks_tracked": len(week_masteries)
            },
            "total_interactions": mastery_data.get("total_interactions", 0),
            "last_session": mastery_data.get("last_session", "")
        }
        
    except Exception as e:
        print(f"DEBUG: Error formatting mastery data: {e}")
        return get_default_mastery_data("", "")

def get_default_mastery_data(username: str, course: str) -> Dict[str, Any]:
    """Default mastery data when no data is available"""
    return {
        "go_masteries": {},
        "lo_masteries": {},
        "week_masteries": {},
        "course_mastery": 0.0,
        "averages": {"go_mastery": 0.0, "lo_mastery": 0.0, "week_mastery": 0.0},
        "mastery_counts": {"go_tracked": 0, "lo_tracked": 0, "weeks_tracked": 0},
        "total_interactions": 0,
        "last_session": ""
    }

def handle_course_change(new_course: str):
    """Handle course selection change"""
    if new_course != st.session_state.get("selected_course"):
        print(f"DEBUG: Course changed from {st.session_state.get('selected_course')} to {new_course}")
        
        # Update session state
        st.session_state.selected_course = new_course
        st.session_state.selected_week = 1
        
        # Reset active sessions
        st.session_state.quiz_active = False
        st.session_state.quiz_completed = False
        st.session_state.tutor_active = False
        
        # Clear chat history
        username = st.session_state.get("username", "user")
        conversation_key = f"conversation_{username}"
        if conversation_key in st.session_state:
            st.session_state[conversation_key] = []
        
        # Reload course weeks with new KC loader
        load_course_weeks()
        
        print(f"DEBUG: Successfully switched to course {new_course}")
        st.rerun()

class RAGFallbackOrchestrator:
    """
    Simple fallback orchestrator that provides basic RAG functionality
    when MCP orchestrator fails
    """
    
    def __init__(self, redis_client=None):
        """Initialize fallback orchestrator with basic RAG capability"""
        self.redis_client = redis_client
        
        # Initialize basic RAG capability
        try:
            from src.mcp.tools.rag_retrieval_tool import RAGRetrievalTool
            self.rag_tool = RAGRetrievalTool()
            print("DEBUG: RAG tool initialized for fallback orchestrator")
        except Exception as e:
            print(f"DEBUG: RAG tool initialization failed in fallback: {e}")
            self.rag_tool = None
        
        # Initialize OpenAI client for response generation
        try:
            from openai import OpenAI
            self.openai_client = OpenAI()
            print("DEBUG: OpenAI client initialized for fallback orchestrator")
        except Exception as e:
            print(f"DEBUG: OpenAI client initialization failed in fallback: {e}")
            self.openai_client = None
        
        print("DEBUG: RAG Fallback Orchestrator initialized")
    
    async def process_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process query using basic RAG functionality
        Compatible with MCP orchestrator interface
        """
        try:
            username = state.get("username", "Student")
            user_query = state.get("user_query", "")
            course = state.get("selected_course", "DEMO101")
            week = state.get("selected_week", 1)
            
            print(f"DEBUG: RAG Fallback processing query: '{user_query}' for {course}")
            
            # Get course content via RAG if available
            course_content = ""
            if self.rag_tool and user_query.strip():
                try:
                    rag_result = await self.rag_tool.execute({
                        "query": user_query,
                        "course": course,
                        "max_results": 3,
                        "use_reranking": True
                    })
                    
                    if rag_result.get("success", False) and rag_result.get("results"):
                        content_pieces = []
                        for result in rag_result["results"][:2]:  # Use top 2 results
                            content = result.get("content", "")
                            if content and len(content) > 50:
                                content_pieces.append(content[:800] + "...")
                        
                        if content_pieces:
                            course_content = "\n\n".join(content_pieces)
                            print(f"DEBUG: Retrieved {len(content_pieces)} RAG results")
                        else:
                            course_content = f"Course materials available for {course} but no specific content found for this query."
                    else:
                        course_content = f"Course materials available for {course}."
                        print(f"DEBUG: RAG query failed or no results: {rag_result.get('error', 'Unknown error')}")
                        
                except Exception as e:
                    print(f"DEBUG: RAG retrieval failed: {e}")
                    course_content = f"Course materials available for {course}."
            
            # Generate intelligent response with OpenAI
            if self.openai_client and user_query.strip():
                response = await self._generate_intelligent_response(
                    user_query, course, week, username, course_content
                )
            else:
                # Very basic fallback
                response = f"I understand you're asking about '{user_query}'. Let me help you with that concept."
            
            # Basic cognitive load estimation
            cognitive_assessment = {
                "cl_value": 5.0,  # Neutral cognitive load
                "zpd_score": 0.6,  # Moderate challenge level
                "motivation": 0.7,  # Good motivation
                "recommendation": "maintain"
            }
            
            return {
                "success": True,
                "final_response": response,
                "cognitive_load": cognitive_assessment,
                "scaffolding": {"intervention_type": "maintain_flow"},
                "adaptations_applied": False,
                "processing_mode": "fallback_rag",
                "rag_used": bool(course_content and len(course_content) > 100)
            }
            
        except Exception as e:
            print(f"ERROR: RAG Fallback processing failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "final_response": "I'm having trouble processing your request right now. Please try again."
            }
    async def process_interaction(
        self, 
        username: str,
        course: str, 
        interaction_type,  # Can be string or enum
        student_input: str,
        current_mode: str,
        session_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process interactions for quiz/tutor modes
        """
        try:
            print(f"DEBUG: RAG Fallback processing {current_mode} interaction for {username}")
            
            # Handle quiz interactions
            if current_mode == "quiz" or str(interaction_type).lower().endswith("quiz_answer"):
                return await self._process_quiz_interaction(
                    username, course, student_input, session_context
                )
            
            # Handle tutor interactions  
            elif current_mode == "tutor" or str(interaction_type).lower().endswith("tutor_response"):
                return await self._process_tutor_interaction(
                    username, course, student_input, session_context
                )
            
            # Handle chat interactions
            else:
                return await self._process_chat_interaction(
                    username, course, student_input, session_context
                )
                
        except Exception as e:
            print(f"DEBUG: RAG Fallback interaction processing failed: {e}")
            return self._get_fallback_interaction_result()
    
    async def _process_quiz_interaction(self, username: str, course: str, 
                                      student_input: str, session_context: Dict) -> Dict[str, Any]:
        """Process quiz interaction and update mastery"""
        try:
            # Extract quiz context
            quiz_result = session_context.get("quiz_result", {})
            question_number = session_context.get("question_number", 1)
            week_number = session_context.get("selected_week", 1)
            
            is_correct = quiz_result.get("correct", False)
            score = quiz_result.get("score", 0.0)
            
            # Calculate cognitive load for quiz
            cognitive_load = self._calculate_quiz_cognitive_load(
                question_number, is_correct, session_context
            )
            
            # Create cognitive state
            cognitive_state_dict = {
                "cognitive_load": cognitive_load,
                "zpd_score": 0.8 if is_correct else 0.3,
                "motivation_score": min(0.9, 0.5 + (score * 0.4)),
                "fatigue_level": min(0.8, question_number * 0.05),
                "scaffolding_level": "low" if is_correct else "medium",
                "session_quality": "good" if is_correct else "needs_support"
            }
            
            # Update mastery for this quiz question
            await self._update_quiz_mastery(username, course, week_number, quiz_result, session_context)
            
            # Generate scaffolding advice
            scaffolding_strategy = {
                "intervention_type": "maintain_flow" if is_correct else "concept_review",
                "urgency": "none" if is_correct else "medium",
                "cognitive_load_score": cognitive_load
            }
            
            print(f"DEBUG: Quiz interaction processed - Correct: {is_correct}, CL: {cognitive_load:.2f}")
            
            return {
                'cognitive_state': type('CognitiveState', (), cognitive_state_dict)(),
                'scaffolding_strategy': scaffolding_strategy,
                'motivation_feedback': {"motivation_level": "moderate"},
                'processing_successful': True,
                'interaction_type': 'quiz'
            }
            
        except Exception as e:
            print(f"DEBUG: Quiz interaction processing failed: {e}")
            return self._get_fallback_interaction_result()
    
    async def _process_tutor_interaction(self, username: str, course: str,
                                       student_input: str, session_context: Dict) -> Dict[str, Any]:
        """Process tutor interaction"""
        try:
            # Basic tutor processing
            cognitive_load = 5.0  # Neutral for tutor
            
            cognitive_state_dict = {
                "cognitive_load": cognitive_load,
                "zpd_score": 0.6,
                "motivation_score": 0.7,
                "fatigue_level": 0.3,
                "scaffolding_level": "medium",
                "session_quality": "good"
            }
            
            return {
                'cognitive_state': type('CognitiveState', (), cognitive_state_dict)(),
                'scaffolding_strategy': {"intervention_type": "maintain_flow"},
                'motivation_feedback': {"motivation_level": "moderate"},
                'processing_successful': True,
                'interaction_type': 'tutor'
            }
            
        except Exception as e:
            print(f"DEBUG: Tutor interaction processing failed: {e}")
            return self._get_fallback_interaction_result()
    
    async def _process_chat_interaction(self, username: str, course: str,
                                      student_input: str, session_context: Dict) -> Dict[str, Any]:
        """Process chat interaction"""
        try:
            # Basic chat processing  
            cognitive_load = 4.0  # Lower for chat
            
            cognitive_state_dict = {
                "cognitive_load": cognitive_load,
                "zpd_score": 0.7,
                "motivation_score": 0.8,
                "fatigue_level": 0.2,
                "scaffolding_level": "low",
                "session_quality": "excellent"
            }
            
            return {
                'cognitive_state': type('CognitiveState', (), cognitive_state_dict)(),
                'scaffolding_strategy': {"intervention_type": "maintain_flow"},
                'motivation_feedback': {"motivation_level": "high"},
                'processing_successful': True,
                'interaction_type': 'chat'
            }
            
        except Exception as e:
            print(f"DEBUG: Chat interaction processing failed: {e}")
            return self._get_fallback_interaction_result()
    
    def _calculate_quiz_cognitive_load(self, question_number: int, is_correct: bool, 
                                     session_context: Dict) -> float:
        """Calculate cognitive load for quiz interactions"""
        
        base_load = 5.0
        
        # Difficulty increases with question number
        progression_load = question_number * 0.1
        
        # Incorrect answers increase cognitive load
        accuracy_load = -2.0 if is_correct else 2.0
        
        # Fatigue factor
        fatigue_load = min(2.0, question_number * 0.05)
        
        total_load = base_load + progression_load + accuracy_load + fatigue_load
        
        return max(1.0, min(10.0, total_load))
    
    async def _update_quiz_mastery(self, username: str, course: str, week: int,
                                 quiz_result: Dict, session_context: Dict):
        """Update mastery tracking for quiz results"""
        try:
            # Try to get mastery tracker
            mastery_tracker = get_mastery_tracker()
            if not mastery_tracker:
                print("DEBUG: No mastery tracker available for quiz update")
                return
            
            # Extract question info
            current_question = session_context.get("quiz_data", {}).get("current_question", {})
            go_id = current_question.get("go_id", f"GO_{week:02d}_QUIZ_{session_context.get('question_number', 1):02d}")
            
            # Create interaction context for mastery tracker
            interaction_context = {
                'go_data': {
                    'go_id': go_id,
                    'skill_name': current_question.get("skill", "Quiz Question"),
                    'description': current_question.get("text", "Quiz question")
                },
                'lo_data': {
                    'title': f"Learning Objective Week {week}"
                },
                'week_topic': f"Week {week}",
                'course_code': course,
                'is_quiz': True,
                'correct': quiz_result.get("correct", False),
                'score': quiz_result.get("score", 0.0)
            }
            
            # Create synthetic response for mastery assessment
            is_correct = quiz_result.get("correct", False)
            student_response = f"Quiz answer: {session_context.get('student_answer', 'Unknown')} (Result: {'Correct' if is_correct else 'Incorrect'})"
            
            # Update mastery via tracker
            if hasattr(mastery_tracker, 'update_learner_mastery'):
                # Async version
                lo_id = f"LO_{week:02d}_01" 
                await mastery_tracker.update_learner_mastery(
                    username, course, student_response, go_id, lo_id, week, interaction_context
                )
                print(f"DEBUG: ✅ Quiz mastery updated for {go_id} - Correct: {is_correct}")
            else:
                print("DEBUG: Mastery tracker update method not available")
                
        except Exception as e:
            print(f"DEBUG: Quiz mastery update failed: {e}")
    
    def _get_fallback_interaction_result(self) -> Dict[str, Any]:
        """Fallback interaction result when processing fails"""
        cognitive_state_dict = {
            "cognitive_load": 5.0,
            "zpd_score": 0.6,
            "motivation_score": 0.6,
            "fatigue_level": 0.3,
            "scaffolding_level": "medium",
            "session_quality": "good"
        }
        
        return {
            'cognitive_state': type('CognitiveState', (), cognitive_state_dict)(),
            'scaffolding_strategy': {"intervention_type": "maintain_flow"},
            'motivation_feedback': {"motivation_level": "moderate"},
            'processing_successful': False,
            'interaction_type': 'fallback'
        }
        
    async def _generate_intelligent_response(
        self, 
        query: str, 
        course: str, 
        week: int, 
        username: str, 
        course_content: str
    ) -> str:
        """Generate intelligent response using OpenAI with RAG content"""
        try:
            # Build intelligent prompt
            system_prompt = f"""You are LEA, an intelligent learning assistant for {course} at Abertay University.

CURRENT CONTEXT:
- Course: {course}, Week {week}
- Student: {username}
- Mode: Chat (conversational learning support)

{"RELEVANT COURSE CONTENT:" if course_content else ""}
{course_content if course_content else ""}

INSTRUCTIONS:
1. {"Answer using the provided course content when relevant" if course_content else "Provide helpful information about the topic"}
2. Be conversational and engaging - you're LEA! 
3. Keep responses focused but comprehensive
4. If the question isn't directly course-related, be helpful but try to connect to learning
5. Use examples and analogies when helpful
6. Remember the motto: "Slide In. Study Up. Show Off."

Be natural, helpful, and educational."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ]
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=400
            )
            
            generated_response = response.choices[0].message.content.strip()
            print(f"DEBUG: Generated intelligent fallback response")
            return generated_response
            
        except Exception as e:
            print(f"DEBUG: OpenAI response generation failed: {e}")
            # Text-based fallback
            if course_content and len(course_content) > 100:
                return f"Based on the course materials for {course}, here's what I can tell you about '{query}': {course_content[:300]}... Would you like me to elaborate on any specific aspect?"
            else:
                return f"Great question about '{query}'! This is an important topic in {course}. Let me help you understand the key concepts and how they apply to your studies."

# Decision Logger for research analysis
class DecisionLogger:
    """Log orchestrator decisions for research analysis"""
    
    def __init__(self):
        self.log_dir = Path("./data/decision_logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_session_log = []
        
        # Create CSV header if files don't exist
        self._ensure_log_files()

    
    def _ensure_log_files(self):
        """Ensure CSV log files exist with proper headers"""
        
        # Cognitive load decisions log
        cl_log_path = self.log_dir / "cognitive_load_decisions.csv"
        if not cl_log_path.exists():
            with open(cl_log_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'username', 'course', 'mode', 'cognitive_load', 
                    'zpd_score', 'motivation', 'fatigue', 'scaffolding_decision',
                    'intervention_type', 'difficulty_adjustment', 'session_context'
                ])
        
        # Scaffolding decisions log
        scaffolding_log_path = self.log_dir / "scaffolding_decisions.csv"
        if not scaffolding_log_path.exists():
            with open(scaffolding_log_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'username', 'course', 'go_id', 'cl_level', 
                    'zpd_level', 'strategy_type', 'intensity_level', 
                    'fade_threshold', 'consecutive_correct', 'was_faded'
                ])
    
    def log_cognitive_decision(self, decision_data: Dict[str, Any]):
        """Log cognitive load and ZPD decision"""
        try:
            cl_log_path = self.log_dir / "cognitive_load_decisions.csv"
            with open(cl_log_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    decision_data.get('username', 'unknown'),
                    decision_data.get('course', 'unknown'),
                    decision_data.get('mode', 'unknown'),
                    decision_data.get('cognitive_load', 0.0),
                    decision_data.get('zpd_score', 0.0),
                    decision_data.get('motivation', 0.0),
                    decision_data.get('fatigue', 0.0),
                    decision_data.get('scaffolding_decision', 'unknown'),
                    decision_data.get('intervention_type', 'unknown'),
                    decision_data.get('difficulty_adjustment', 'none'),
                    json.dumps(decision_data.get('session_context', {}))
                ])
        except Exception as e:
            print(f"DEBUG: Error logging cognitive decision: {e}")
    
    def log_scaffolding_decision(self, scaffolding_data: Dict[str, Any]):
        """Log scaffolding engine decision"""
        try:
            scaffolding_log_path = self.log_dir / "scaffolding_decisions.csv"
            with open(scaffolding_log_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    scaffolding_data.get('username', 'unknown'),
                    scaffolding_data.get('course', 'unknown'),
                    scaffolding_data.get('go_id', 'unknown'),
                    scaffolding_data.get('cl_level', 'unknown'),
                    scaffolding_data.get('zpd_level', 'unknown'),
                    scaffolding_data.get('strategy_type', 'unknown'),
                    scaffolding_data.get('intensity_level', 'unknown'),
                    scaffolding_data.get('fade_threshold', 0),
                    scaffolding_data.get('consecutive_correct', 0),
                    scaffolding_data.get('was_faded', False)
                ])
        except Exception as e:
            print(f"DEBUG: Error logging scaffolding decision: {e}")
    
    def log_motivation_decision(self, motivation_data: Dict[str, Any]):
        """Log motivation decision for research analysis"""
        try:
            motivation_log_path = self.log_dir / "motivation_decisions.csv"
            
            # Create header if file doesn't exist
            if not motivation_log_path.exists():
                with open(motivation_log_path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        'timestamp', 'username', 'course', 'mode', 'motivation_state',
                        'persistence_level', 'affective_score', 'performance_score',
                        'session_completion_rate', 'consecutive_correct', 'consecutive_incorrect',
                        'time_on_task', 'help_seeking_frequency', 'cognitive_load', 
                        'zpd_score', 'motivation_score', 'fatigue_level', 'session_context'
                    ])
            
            # Write motivation decision data
            with open(motivation_log_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    motivation_data.get('username', 'unknown'),
                    motivation_data.get('course', 'unknown'),
                    motivation_data.get('mode', 'unknown'),
                    motivation_data.get('motivation_state', 'unknown'),
                    motivation_data.get('persistence_level', 'unknown'),
                    motivation_data.get('affective_score', 0.0),
                    motivation_data.get('performance_score', 0.0),
                    motivation_data.get('session_completion_rate', 0.0),
                    motivation_data.get('consecutive_correct', 0),
                    motivation_data.get('consecutive_incorrect', 0),
                    motivation_data.get('time_on_task', 0.0),
                    motivation_data.get('help_seeking_frequency', 0.0),
                    motivation_data.get('cognitive_load', 0.0),
                    motivation_data.get('zpd_score', 0.0),
                    motivation_data.get('motivation_score', 0.0),
                    motivation_data.get('fatigue_level', 0.0),
                    json.dumps(motivation_data.get('session_context', {}))
                ])
                
        except Exception as e:
            print(f"DEBUG: Error logging motivation decision: {e}")

# CONVERSATION MANAGEMENT
def get_conversation_history_safe(username: str, limit: int = 10) -> list:
    """Safely get conversation history"""
    try:
        if f"conversation_{username}" in st.session_state:
            history = st.session_state[f"conversation_{username}"]
            return history[-limit:] if len(history) > limit else history
        return []
    except Exception as e:
        print(f"DEBUG: Error getting conversation history: {e}")
        return []

def store_conversation_message_safe(username: str, role: str, message: str):
    """Safely store conversation message"""
    try:
        conversation_key = f"conversation_{username}"
        if conversation_key not in st.session_state:
            st.session_state[conversation_key] = []
        
        st.session_state[conversation_key].append({
            "role": role,
            "message": message,
            "timestamp": time.time()
        })
        
        if len(st.session_state[conversation_key]) > 50:
            st.session_state[conversation_key] = st.session_state[conversation_key][-50:]
            
    except Exception as e:
        print(f"DEBUG: Error storing conversation: {e}")

# CHAT INTEGRATION WITH ORCHESTRATOR
def send_chat_message_with_orchestrator(user_input: str):
    """Chat with proper orchestrator integration - WITH MEMORY"""
    try:
        username = st.session_state.get("username")
        if not username:
            st.error("Please log in to continue")
            return
        
        # Store user message in conversation
        store_conversation_message_safe(username, "user", user_input)
        
        # NEW: Store in memory system
        store_interaction_memory(
            username=username,
            interaction_type="chat",
            content={
                "message": user_input,
                "course": st.session_state.get("selected_course", "DEMO101"),
                "week": st.session_state.get("selected_week", 1),
                "timestamp": time.time()
            }
        )
        
        # Get orchestrator (MCP or fallback)
        orchestrator = get_orchestrator()
        
        if not orchestrator:
            print("DEBUG: Orchestrator not available, using enhanced fallback")
            enhanced_response = get_enhanced_chat_fallback(user_input)
            store_conversation_message_safe(username, "assistant", enhanced_response)
            st.rerun()
            return
        
        # Build state for orchestrator
        conversation_history = get_conversation_history_safe(username, 10)
        state = {
            "user_query": user_input,
            "username": username,
            "selected_course": st.session_state.get("selected_course", "DEMO101"),
            "selected_week": st.session_state.get("selected_week", 1),
            "current_mode": "chat",
            "conversation_history": conversation_history,
            "session_metadata": {
                "timestamp": time.time(),
                "interface_mode": "chat",
                "message_count": len(conversation_history)
            }
        }
        
        with st.spinner("🧠 Analyzing your question..."):
            try:
                # Use RAG orchestrator (simplified)
                result = run_async_safely(orchestrator.process_query(state))
                print(f"DEBUG: Orchestrator result success: {result.get('success', False)}")
                
            except Exception as e:
                print(f"DEBUG: Orchestrator processing error: {e}")
                enhanced_fallback = get_enhanced_chat_fallback(user_input)
                store_conversation_message_safe(username, "assistant", enhanced_fallback)
                st.rerun()
                return
        
        # Process orchestrator result
        if result.get("success", False):
            response = result.get("final_response", "I'm having trouble responding right now.")
            
            # NEW: Store assistant response in memory
            store_interaction_memory(
                username=username,
                interaction_type="chat_response",
                content={
                    "user_message": user_input,
                    "assistant_response": response,
                    "course": st.session_state.get("selected_course", "DEMO101"),
                    "week": st.session_state.get("selected_week", 1),
                    "cognitive_state": result.get("cognitive_state", {}),
                    "timestamp": time.time()
                }
            )
            
            store_conversation_message_safe(username, "assistant", response)
            st.rerun()

        else:
            error_msg = result.get("error", "Unknown error")
            print(f"DEBUG: Orchestrator returned error: {error_msg}")
            
            # Enhanced fallback based on course context
            enhanced_response = get_enhanced_chat_fallback(user_input)
            store_conversation_message_safe(username, "assistant", enhanced_response)
            st.rerun()
            
    except Exception as e:
        st.error(f"Error processing your message: {e}")
        print(f"DEBUG: Chat integration error: {e}")

def get_enhanced_chat_fallback(user_input: str) -> str:
    """Enhanced chat fallback with direct RAG access"""
    try:
        course = st.session_state.get("selected_course", "DEMO101")
        week = st.session_state.get("selected_week", 1)
        
        # Try to get course content directly
        course_content = get_relevant_course_content(user_input)
        
        # Generate response with OpenAI using RAG content
        chat_system = get_chat_system()
        if chat_system and course_content:
            system_prompt = f"""You are LEA, a helpful learning assistant for {course} at Abertay University.

COURSE CONTEXT:
Week {week} of {course}

RELEVANT COURSE CONTENT:
{course_content[:800]}

INSTRUCTIONS:
1. Answer the student's question using the course content when relevant
2. Be conversational and encouraging - you're LEA!
3. If the question isn't directly course-related, be helpful but try to connect to learning
4. Keep responses focused but comprehensive
5. Remember the motto: "Slide In. Study Up. Show Off."

Be natural, helpful, and educational."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
            
            response = chat_system.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=400
            )
            
            generated_response = response.choices[0].message.content.strip()
            print(f"DEBUG: Generated enhanced fallback response with RAG")
            return generated_response
            
    except Exception as e:
        print(f"DEBUG: Enhanced fallback failed: {e}")
    
    # Final fallback
    course = st.session_state.get("selected_course", "your course")
    week = st.session_state.get("selected_week", 1)
    return f"Great question about '{user_input}'! This relates to important concepts in {course}, Week {week}. Let me help you understand the key ideas and how they apply to your studies."

# Helper function for async handling
def run_async_safely(coroutine):
    """Safely run async operations in Streamlit context"""
    try:
        import asyncio
        import concurrent.futures
        
        # Use thread executor to avoid event loop conflicts
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coroutine)
            return future.result(timeout=30)
            
    except Exception as e:
        print(f"DEBUG: Async execution failed: {e}")
        return {"success": False, "error": f"Processing failed: {str(e)}"}

def process_mcp_orchestrator(orchestrator, state):
    """Handle MCP orchestrator processing"""
    try:
        # Use thread executor for MCP async operations
        def run_mcp_async():
            return asyncio.run(orchestrator.process_query(state))
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_mcp_async)
            result = future.result(timeout=30)
            
        return result
        
    except Exception as e:
        print(f"DEBUG: MCP orchestrator processing failed: {e}")
        return {'success': False, 'error': str(e)}

# def apply_pending_week_advancement():
#     """
#     Apply any pending week advancement after quiz completion.
#     This checks if the user should advance to the next week based on quiz performance.
#     """
#     try:
#         # Check if there's a pending advancement flag
#         if st.session_state.get('pending_week_advance', False):
#             current_week = st.session_state.get('selected_week', 1)
            
#             # Get the selected week as an integer
#             if isinstance(current_week, str) and current_week.startswith('Week '):
#                 week_num = int(current_week.split()[1])
#             else:
#                 week_num = int(current_week)
            
#             # Advance to next week
#             next_week = week_num + 1
            
#             # Check if next week exists (you may want to add max week checking)
#             max_weeks = 11  # Adjust based on your course structure
#             if next_week <= max_weeks:
#                 st.session_state.selected_week = f"Week {next_week}"
#                 print(f"DEBUG: Advanced to Week {next_week}")
#                 st.success(f"🎉 Congratulations! Advanced to Week {next_week}")
#             else:
#                 print(f"DEBUG: Already at final week ({week_num})")
#                 st.info("You've completed the final week! Great job!")
            
#             # Clear the pending flag
#             st.session_state.pending_week_advance = False
            
#     except Exception as e:
#         print(f"DEBUG: Error in week advancement: {e}")
#         # If there's an error, just clear the flag and continue
#         st.session_state.pending_week_advance = False

def apply_pending_week_advancement():
    """Handle week advancement with full state reset."""
    try:
        # Check if transitioning from completed week
        if st.session_state.get('quiz_completed', False):
            current_week = st.session_state.get('selected_week', 'Week 1')
            
            # Clear ALL quiz-related state
            keys_to_clear = [k for k in st.session_state.keys() if 'quiz' in k.lower()]
            for key in keys_to_clear:
                if key != 'selected_week':
                    del st.session_state[key]
            
            print(f"DEBUG: Cleared {len(keys_to_clear)} quiz state keys after {current_week}")
    except Exception as e:
        print(f"DEBUG: Week advancement error: {e}")

# Alternative simpler version for no automatic advancement
def apply_pending_week_advancement_simple():
    """
    Placeholder for week advancement logic.
    Currently just clears any pending state.
    """
    # Clear any pending advancement flags
    if 'pending_week_advance' in st.session_state:
        del st.session_state.pending_week_advance
    
    # Add logic here to:
    # - Check quiz performance
    # - Update progress tracking
    # - Advance to next week if criteria met
    pass
    

# QUIZ FUNCTIONS
def render_quiz_interface():
    """Quiz interface WITHOUT motivation display (background tracking only)"""
    # Get LEA avatar for header
    
    # Standard quiz control buttons (existing logic)
    if st.session_state.quiz_completed:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🔄 Start New Quiz", use_container_width=True, type="primary", key="new_quiz_btn"):
                reset_quiz_state()
                # FIXED: Apply any pending week advancement when starting new quiz
                apply_pending_week_advancement()
                st.rerun()
        
        render_quiz_results()
        return
        
    elif not st.session_state.quiz_active:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            start_disabled = st.session_state.get('quiz_starting', False)
            if st.button("⭐ Start Quiz", use_container_width=True, type="primary", 
                        disabled=start_disabled, key="start_quiz_btn"):
                st.session_state['quiz_starting'] = True
                start_adaptive_quiz_with_background_motivation()
                return
        
        render_quiz_preparation_info()
        return
    
    # Active quiz content (existing logic with background motivation)
    if not st.session_state.current_quiz_data:
        st.error("No quiz data available. Please restart the quiz.")
        return
    
    quiz_data = st.session_state.current_quiz_data
    question = quiz_data.get("current_question", {})
    
    # Standard progress display (existing logic)
    progress = st.session_state.quiz_progress
    st.progress(progress['current'] / progress['total'])
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.write(f"Question {progress['current']} of {progress['total']} | Correct: {progress['correct']}")
    with col2:
        orchestrator = get_orchestrator()
        orchestrator_status = "🧠 Adaptive" if (orchestrator and hasattr(orchestrator, 'mcp_client')) else "📱 Basic"
        st.caption(f"{orchestrator_status} Mode")
    
    # End quiz button
    if st.button("❌ End Quiz", key="end_quiz_btn"):
        end_quiz()
        return
    
    # Show feedback (NO motivation insights visible to student)
    if st.session_state.show_feedback and st.session_state.current_feedback:
        render_standard_quiz_feedback()  # Standard feedback only
        return
    
    # Display question (existing logic)
    question_text = question.get('text', 'Question not available')
    
    if '```python' in question_text or '```' in question_text:
        st.markdown("### Question:")
        st.markdown(question_text, unsafe_allow_html=False)
    else:
        st.markdown(f"### {question_text}")
    
    # Question type handling (existing logic but with background motivation)
    question_type = question.get("type", "multiple_choice")
    
    if question_type == "multiple_choice":
        options = question.get("options", [])
        if options:
            radio_key = f"quiz_mc_{quiz_data.get('quiz_id', 'unknown')}_{progress['current']}"
            selected = st.radio("Select your answer:", options, key=radio_key)
            
            if st.button("Submit Answer", type="primary", disabled=not selected, 
                        key=f"submit_mc_{progress['current']}"):
                submit_answer_with_background_motivation(selected)
        else:
            st.error("No options available for this question.")
    
    elif question_type == "true_false":
        st.write("Choose True or False:")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("✅ True", use_container_width=True, type="primary", key=f"true_btn_{progress['current']}"):
                submit_answer_with_background_motivation("True")
                
        with col2:
            if st.button("❌ False", use_container_width=True, key=f"false_btn_{progress['current']}"):
                submit_answer_with_background_motivation("False")
    
    elif question_type == "fill_in_blank":
        input_key = f"quiz_fill_{quiz_data.get('quiz_id', 'unknown')}_{progress['current']}"
        answer = st.text_input("Your answer:", key=input_key)
        
        if st.button("Submit Answer", type="primary", disabled=not answer.strip(), 
                    key=f"submit_fill_{progress['current']}"):
            submit_answer_with_background_motivation(answer.strip())
    
    else:  # open_ended
        st.write("Type your answer below:")
        
        text_key = f"quiz_open_{quiz_data.get('quiz_id', 'unknown')}_{progress['current']}"
        answer = st.text_area("Your answer:", height=120, key=text_key)
        
        char_count = len(answer.strip())
        st.caption(f"Character count: {char_count}")
        
        min_chars = 10
        if st.button("Submit Answer", type="primary", disabled=char_count < min_chars, 
                    key=f"submit_open_{progress['current']}"):
            submit_answer_with_background_motivation(answer.strip())
        
        if char_count < min_chars:
            st.warning(f"Please write at least {min_chars} characters. You have {char_count}.")

def start_adaptive_quiz():
    """ENHANCED: Start quiz with orchestrator preparation"""
    print(f"DEBUG: ===== START ADAPTIVE QUIZ =====")
    
    if st.session_state.quiz_active or st.session_state.current_quiz_data:
        print("DEBUG: Quiz already active, ignoring duplicate start request")
        return
    
    quiz_system = get_quiz_system()
    orchestrator = get_orchestrator()
    
    if not quiz_system:
        st.error("Quiz system not available.")
        return
    
    try:
        st.session_state.quiz_active = True
        
        # Show orchestrator preparation status
        orchestrator_ready = orchestrator and hasattr(orchestrator, 'mcp_client')
        
        with st.spinner(f"🧠 Preparing {'adaptive' if orchestrator_ready else 'standard'} quiz..."):
            
            # Enhanced quiz generation with GO strategy
            go_components = get_go_strategy_components()
            if go_components:
                enhanced_quiz_data = go_components["quiz_sequencer"].generate_week_quiz(
                    st.session_state.selected_course,
                    st.session_state.selected_week,
                    st.session_state.username
                )
                
                if "error" not in enhanced_quiz_data:
                    st.success(f"⭐ **Adaptive Quiz Strategy:** One question per learning objective")
                    st.info(f"🧠 **Intelligence:** {'Advanced orchestrator' if orchestrator_ready else 'Basic system'}")
                    st.info(f"🎯 **Coverage:** {len(enhanced_quiz_data['go_coverage'])} specific skills")
                    
                    st.session_state.quiz_go_mapping = enhanced_quiz_data
                    print(f"DEBUG: Enhanced quiz covers GOs: {enhanced_quiz_data['go_coverage']}")
            
            # Start quiz with enhanced data
            quiz_data = quiz_system.start_quiz(
                course=st.session_state.selected_course,
                week=st.session_state.selected_week,
                username=st.session_state.username
            )
            
            if quiz_data:
                # Enhance first question with orchestrator if available
                if orchestrator_ready:
                    try:
                        # Get orchestrator recommendations for first question
                        first_question_context = {
                            'quiz_data': quiz_data,
                            'question_number': 1,
                            'username': st.session_state.username,
                            'course': st.session_state.selected_course,
                            'selected_week': st.session_state.selected_week
                        }
                        
                        # This will enhance the question generation process
                        print("DEBUG: 🚀 First question will use orchestrator recommendations")
                        
                    except Exception as e:
                        print(f"DEBUG: First question orchestrator prep failed: {e}")
                
                # Set quiz state
                st.session_state.current_quiz_data = quiz_data
                st.session_state.quiz_progress = {
                    "current": 1,
                    "total": len(quiz_data.get("question_plan", [])),
                    "correct": 0
                }
                st.session_state.quiz_results = []
                st.session_state.show_feedback = False
                st.session_state.quiz_completed = False
                
                # Initialize enhanced learning analytics
                initialize_adaptive_analytics(quiz_data, orchestrator_ready)
                
                print(f"DEBUG: ✅ {'Adaptive' if orchestrator_ready else 'Standard'} quiz started - {st.session_state.quiz_progress['total']} questions")
                st.rerun()
            else:
                st.session_state.quiz_active = False
                st.error("Failed to start quiz.")
                
    except Exception as e:
        st.session_state.quiz_active = False
        print(f"ERROR: Adaptive quiz start failed: {e}")
        st.error(f"Failed to start adaptive quiz: {str(e)}")

def render_standard_quiz_feedback():
    """Show standard quiz feedback WITHOUT motivation insights"""
    feedback = st.session_state.current_feedback
    
    # Standard feedback only
    if feedback.get("correct"):
        st.success(f"✅ Correct! {feedback.get('explanation', '')}")
    else:
        st.error(f"❌ Incorrect. {feedback.get('explanation', '')}")
    
    # REMOVED: No motivation insights visible to student
    # Background motivation is still being tracked and applied to content
    
    if st.button("Continue", type="primary", key="continue_btn"):
        continue_to_next_question()

def start_adaptive_quiz_with_background_motivation():
    """Start quiz with background motivation tracking"""
    print(f"DEBUG: ===== START QUIZ WITH BACKGROUND MOTIVATION =====")
    
    if st.session_state.quiz_active or st.session_state.current_quiz_data:
        print("DEBUG: Quiz already active, ignoring duplicate start request")
        return
    
    quiz_system = get_quiz_system()
    orchestrator = get_orchestrator()
    
    if not quiz_system:
        st.error("Quiz system not available.")
        return
    
    try:
        st.session_state.quiz_active = True
        st.session_state.quiz_start_time = datetime.now()  # Track for motivation
        
        orchestrator_ready = orchestrator and hasattr(orchestrator, 'mcp_client')
        
        with st.spinner(f"🧠 Preparing {'adaptive' if orchestrator_ready else 'standard'} quiz..."):
            
            # Get initial orchestrator context for motivation-informed quiz generation
            initial_orchestrator_context = None
            if orchestrator_ready:
                try:
                    # Get baseline context for quiz start
                    baseline_context = {
                        'username': st.session_state.username,
                        'course': st.session_state.selected_course,
                        'week': st.session_state.selected_week,
                        'session_start_time': st.session_state.quiz_start_time,
                        'interaction_count': 0,
                        'quiz_starting': True
                    }
                    
                    initial_orchestrator_context = process_orchestrator_interaction(
                        orchestrator=orchestrator,
                        interaction_type="quiz",
                        student_input="Starting quiz",
                        session_context=baseline_context
                    )
                    
                    if initial_orchestrator_context:
                        store_motivation_metrics_background(initial_orchestrator_context)
                        print(f"DEBUG: 🎯 Initial motivation state captured for quiz")
                        
                except Exception as e:
                    print(f"DEBUG: Initial orchestrator context failed: {e}")
            
            # Start quiz with motivation context
            if initial_orchestrator_context:
                quiz_data = quiz_system.start_quiz(
                    course=st.session_state.selected_course,
                    week=st.session_state.selected_week,
                    username=st.session_state.username,
                    orchestrator_context=initial_orchestrator_context
                )
            else:
                quiz_data = quiz_system.start_quiz(
                    course=st.session_state.selected_course,
                    week=st.session_state.selected_week,
                    username=st.session_state.username
                )
            
            if quiz_data:
                # Set quiz state
                st.session_state.current_quiz_data = quiz_data
                st.session_state.quiz_progress = {
                    "current": 1,
                    "total": len(quiz_data.get("question_plan", [])),
                    "correct": 0
                }
                st.session_state.quiz_results = []
                st.session_state.show_feedback = False
                st.session_state.quiz_completed = False
                
                # Initialize session tracking for motivation
                st.session_state.current_session_id = quiz_data.get("quiz_id", "unknown")
                
                print(f"DEBUG: ✅ Quiz started with background motivation tracking - {st.session_state.quiz_progress['total']} questions")
                st.rerun()
            else:
                st.session_state.quiz_active = False
                st.error("Failed to start quiz.")
                
    except Exception as e:
        st.session_state.quiz_active = False
        print(f"ERROR: Quiz start with background motivation failed: {e}")
        st.error(f"Failed to start quiz: {str(e)}")

def reset_quiz_state():
    """Reset all quiz state"""
    st.session_state.quiz_active = False
    st.session_state.quiz_completed = False
    st.session_state.current_quiz_data = None
    st.session_state.quiz_results = []
    st.session_state.show_feedback = False
    st.session_state.current_feedback = None
    st.session_state.quiz_progress = {"current": 0, "total": 0, "correct": 0}
    if "cognitive_load" in st.session_state:
        del st.session_state["cognitive_load"]
    if "_motivation_analytics" in st.session_state:
        del st.session_state["_motivation_analytics"]

# MODIFIED TUTOR INTERFACE - Background motivation only      
def render_quiz_preparation_info():
    """Show enhanced preparation info with orchestrator status"""
    if st.session_state.course_weeks and st.session_state.selected_week:
        for week_display, week_data in st.session_state.course_weeks.items():
            if week_data["week_number"] == st.session_state.selected_week:
                st.markdown(f"### 📊 {week_display}")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Learning Objectives:** {len(week_data.get('learning_objectives', []))}")
                    st.markdown(f"**Total Questions:** {week_data.get('total_questions', 'Unknown')}")

                with st.expander("📚 What We'll Cover"):
                    for lo in week_data.get('learning_objectives', []):
                        st.markdown(f"- **{lo['title']}** ({lo['granular_count']} concepts)")
                break

def render_enhanced_quiz_feedback():
    """Show enhanced feedback with orchestrator insights"""
    feedback = st.session_state.current_feedback
    
    if feedback.get("correct"):
        st.success(f"✅ Correct! {feedback.get('explanation', '')}")
    else:
        st.error(f"❌ Incorrect. {feedback.get('explanation', '')}")
    
    # Show orchestrator insights if available
    orchestrator = get_orchestrator()
    if (orchestrator and hasattr(orchestrator, 'mcp_client') and 
        hasattr(orchestrator, 'decision_logger')):
        
        with st.expander("🧠 Learning Insights", expanded=False):
            
            # Show cognitive load if available
            if "cognitive_load" in st.session_state:
                cl_data = st.session_state["cognitive_load"]
                col1, col2 = st.columns(2)
                
                with col1:
                    st.metric("Cognitive Load", f"{cl_data.get('cl_value', 5.0):.1f}/10")
                with col2:
                    st.metric("Challenge Level", f"{cl_data.get('zpd_score', 0.5):.2f}")
            
            # Show scaffolding recommendation
            if "scaffolding" in st.session_state:
                scaffolding = st.session_state["scaffolding"]
                st.caption(f"🎯 Strategy: {scaffolding.get('intervention_type', 'maintain_flow')}")
            
            st.caption("💡 These insights help adapt future questions to your learning needs")
    
    if st.button("Continue", type="primary", key="continue_btn"):
        continue_to_next_question()

def initialize_adaptive_analytics(quiz_data, orchestrator_ready):
    """Initialize enhanced analytics for adaptive quiz"""
    if orchestrator_ready:
        # Enhanced analytics with orchestrator
        current_question = quiz_data.get("current_question", {})
        question_type = current_question.get("type", "multiple_choice")
        
        # Set initial cognitive load with orchestrator context
        st.session_state["cognitive_load"] = {
            "cl_value": 5.0,  # Neutral start
            "zpd_score": 0.6,  # Moderate challenge
            "motivation": 0.7,  # Good motivation
            "fatigue": 0.0,    # No fatigue yet
            "timestamp": time.time(),
            "question_number": 1,
            "orchestrator_active": True,
            "formula_variables": {
                "accuracy": 0.6,
                "difficulty": 0.5,
                "interaction_count": 1,
                "task_type": 1.0 if question_type == 'open_ended' else 0.0
            }
        }
        
        print("DEBUG: ✅ Adaptive analytics initialized with orchestrator")
    else:
        # Basic analytics fallback
        simple_analytics = get_simple_analytics()
        if simple_analytics:
            current_question = quiz_data.get("current_question", {})
            question_type = current_question.get("type", "multiple_choice")
            
            initial_analytics = simple_analytics.calculate_learning_metrics(
                quiz_results=[], question_number=1, current_question_type=question_type
            )
            
            st.session_state["cognitive_load"] = {
                "cl_value": initial_analytics['cognitive_load'],
                "zpd_score": initial_analytics['zpd_score'],
                "motivation": initial_analytics['motivation'],
                "fatigue": initial_analytics['fatigue'],
                "timestamp": time.time(),
                "question_number": 1,
                "orchestrator_active": False,
                "formula_variables": {
                    "accuracy": initial_analytics['zpd_score'],
                    "difficulty": initial_analytics['difficulty'],
                    "interaction_count": 1,
                    "task_type": initial_analytics['task_type']
                }
            }
        
        print("DEBUG: 📱 Basic analytics initialized (fallback)")

def submit_answer_with_motivation_integration(answer: str):
    """Enhanced quiz submission with motivation integration"""
    print(f"DEBUG: ⭐ Quiz submission with motivation integration")
    
    if not st.session_state.quiz_active or not st.session_state.current_quiz_data:
        st.error("No active quiz session.")
        return
    
    quiz_system = get_quiz_system()
    orchestrator = get_orchestrator()
    
    if not quiz_system:
        st.error("Quiz system not available.")
        return
    
    try:
        # Build enhanced context for orchestrator
        enhanced_context = {
            'quiz_data': st.session_state.current_quiz_data,
            'selected_week': st.session_state.selected_week,
            'question_number': st.session_state.quiz_progress["current"],
            'total_questions': st.session_state.quiz_progress["total"],
            'current_score': st.session_state.quiz_progress["correct"],
            'quiz_history': st.session_state.quiz_results,
            'student_answer': answer.strip(),
            'course': st.session_state.selected_course,
            'username': st.session_state.username,
            'session_start_time': st.session_state.get('quiz_start_time', datetime.now()),
            'interaction_count': st.session_state.quiz_progress["current"],
            'completion_progress': st.session_state.quiz_progress["current"] / st.session_state.quiz_progress["total"]
        }
        
        # Get orchestrator analysis WITH motivation assessment
        orchestrator_result = None
        if orchestrator:
            try:
                orchestrator_result = process_orchestrator_interaction(
                    orchestrator=orchestrator,
                    interaction_type="quiz",
                    student_input=answer.strip(),
                    session_context=enhanced_context
                )
                
                if orchestrator_result:
                    print(f"DEBUG: 🎯 Orchestrator analysis complete - Motivation: {orchestrator_result.get('motivation_state')}")
                    
                    # Store motivation context for UI display
                    update_session_state_with_motivation(orchestrator_result)
                    
            except Exception as e:
                print(f"DEBUG: Orchestrator processing failed: {e}")
        
        # Evaluate quiz answer
        result = quiz_system.submit_answer(
            quiz_data=st.session_state.current_quiz_data,
            answer=answer.strip()
        )
        
        if not result:
            st.error("Failed to evaluate answer.")
            return
        
        # Update quiz state
        st.session_state.quiz_results.append(result)
        
        if result.get("correct", False):
            st.session_state.quiz_progress["correct"] += 1
        
        st.session_state.show_feedback = True
        st.session_state.current_feedback = result
        
        # Apply motivation-informed UI adjustments
        apply_motivation_informed_ui_adjustments()
        
        # Update mastery with motivation context
        enhanced_context['quiz_result'] = result
        enhanced_context['motivation_context'] = st.session_state.get("orchestrator_context", {})
        update_mastery_after_quiz_answer(st.session_state.username, answer, result)
        
        print(f"DEBUG: ✅ Quiz submission with motivation integration complete")
        st.rerun()
        
    except Exception as e:
        print(f"ERROR: Motivation-integrated quiz submission failed: {e}")
        st.error(f"Submission failed: {str(e)}")

def render_enhanced_quiz_feedback_with_motivation():
    """Show quiz feedback enhanced with motivation insights"""
    feedback = st.session_state.current_feedback
    
    # Standard feedback
    if feedback.get("correct"):
        st.success(f"✅ Correct! {feedback.get('explanation', '')}")
    else:
        st.error(f"❌ Incorrect. {feedback.get('explanation', '')}")
    
    # Show motivation feedback message
    show_motivation_feedback_message()
    
    # Enhanced insights with motivation context
    if "orchestrator_context" in st.session_state:
        orchestrator_context = st.session_state["orchestrator_context"]
        
        with st.expander("🧠 Adaptive Learning Insights", expanded=False):
            
            # Motivation state explanation
            motivation_state = orchestrator_context.get('motivation_state', 'unknown')
            state_descriptions = {
                'cold_start': "🌱 **Getting Started**: We're learning about your learning style and establishing your baseline.",
                'motivation_drop': "⚠️ **Need Support**: You might be feeling challenged right now. We're adjusting to provide more support.",
                'motivation_plateau': "✅ **Steady Progress**: You're maintaining good engagement. Keep up the consistent effort!",
                'maintained_high': "🚀 **High Engagement**: You're highly motivated! Ready for more challenging content."
            }
            
            description = state_descriptions.get(motivation_state, "❓ **Unknown State**: Learning about your current engagement level.")
            st.markdown(description)
            
            # Cognitive load context
            cognitive_state = orchestrator_context.get('cognitive_state')
            if cognitive_state:
                col1, col2 = st.columns(2)
                
                with col1:
                    cl_value = cognitive_state.cognitive_load
                    if cl_value > 7:
                        st.warning(f"🧠 High cognitive load ({cl_value:.1f}/10)")
                        st.caption("Consider taking a break or asking for help")
                    elif cl_value < 4:
                        st.info(f"🧠 Low cognitive load ({cl_value:.1f}/10)")
                        st.caption("Ready for more challenge!")
                    else:
                        st.success(f"🧠 Optimal cognitive load ({cl_value:.1f}/10)")
                        st.caption("Perfect difficulty level")
                
                with col2:
                    motivation_score = cognitive_state.motivation_score
                    if motivation_score > 0.7:
                        st.success(f"💪 High motivation ({motivation_score:.2f})")
                    elif motivation_score < 0.4:
                        st.warning(f"💪 Low motivation ({motivation_score:.2f})")
                    else:
                        st.info(f"💪 Moderate motivation ({motivation_score:.2f})")
            
            # Next question adaptations
            scaffolding = orchestrator_context.get('scaffolding_strategy', {})
            if scaffolding:
                intervention = scaffolding.get('intervention_type', 'maintain_flow')
                
                if intervention == 'immediate_support':
                    st.info("🤝 **Next Question**: Will include extra support and step-by-step guidance")
                elif intervention == 'advanced_challenge':
                    st.info("🚀 **Next Question**: Will be more challenging with minimal scaffolding")
                elif intervention == 'concept_review':
                    st.info("🔄 **Next Question**: Will review key concepts before proceeding")
                else:
                    st.info("➡️ **Next Question**: Will maintain current difficulty level")
    
    if st.button("Continue", type="primary", key="continue_btn"):
        continue_to_next_question()

def verify_progress_after_quiz():
    """Verify progress was actually updated"""
    try:
        username = st.session_state.username
        course = st.session_state.selected_course
        
        auth_service = get_auth_service()
        if auth_service:
            current_progress = auth_service.redis_client.get_user_progress(username)
            course_progress = current_progress.get(course, {})
            completion = course_progress.get("completion", 0.0)
            week = course_progress.get("week", 1)
            
            print(f"DEBUG: ✅ VERIFICATION: Progress - Week: {week}, Completion: {completion*100:.1f}%")
            
            # Show in sidebar
            with st.sidebar:
                st.success(f"📊 Current: Week {week}, {completion*100:.1f}%")
                
    except Exception as e:
        print(f"DEBUG: ❌ VERIFICATION: Failed to check progress: {e}")


def submit_answer_with_orchestrator(answer: str):
    """ENHANCED: Submit quiz answer with orchestrator integration"""
    print(f"DEBUG: ===== ORCHESTRATOR-ENHANCED QUIZ SUBMISSION =====")
    
    if not st.session_state.quiz_active or not st.session_state.current_quiz_data:
        st.error("No active quiz session.")
        return
    
    quiz_system = get_quiz_system()
    orchestrator = get_orchestrator()
    
    if not quiz_system:
        st.error("Quiz system not available.")
        return
    
    try:
        # Step 1: Build enhanced session context for orchestrator
        enhanced_context = {
            'quiz_data': st.session_state.current_quiz_data,
            'selected_week': st.session_state.selected_week,
            'question_number': st.session_state.quiz_progress["current"],
            'total_questions': st.session_state.quiz_progress["total"],
            'current_score': st.session_state.quiz_progress["correct"],
            'quiz_history': st.session_state.quiz_results,
            'student_answer': answer.strip(),
            'course': st.session_state.selected_course,
            'username': st.session_state.username,
            'current_go_id': st.session_state.current_quiz_data.get("current_question", {}).get("go_id", "unknown")
        }
        
        # Step 2: Get orchestrator recommendations BEFORE quiz evaluation
        orchestrator_context = None
        if orchestrator:
            try:
                orchestrator_context = process_orchestrator_interaction(
                    orchestrator=orchestrator,
                    interaction_type="quiz",
                    student_input=answer.strip(),
                    session_context=enhanced_context
                )
                print(f"DEBUG: ✅ Got orchestrator recommendations before quiz evaluation")
            except Exception as e:
                print(f"DEBUG: Orchestrator processing failed: {e}")


        # Add this RIGHT AFTER Step 2 in your submit_answer_with_orchestrator function:

        # Step 2.5: UPDATE SESSION STATE with orchestrator cognitive load values
        if orchestrator_context and 'cognitive_state' in orchestrator_context:
            cognitive_state = orchestrator_context['cognitive_state']
            
            # Extract scaffolding strategy for UI display
            scaffolding_strategy = orchestrator_context.get('scaffolding_strategy', {})
            
            # UPDATE the session state with real orchestrator values
            st.session_state["cognitive_load"] = {
                "cl_value": cognitive_state.cognitive_load,        # 3.17 instead of 5.0!
                "zpd_score": cognitive_state.zpd_score,           # 0.50 instead of default!
                "motivation": cognitive_state.motivation_score,   # Real motivation value
                "fatigue": cognitive_state.fatigue_level,        # Real fatigue value
                "timestamp": time.time(),
                "question_number": st.session_state.quiz_progress["current"],
                "orchestrator_active": True,
                "formula_variables": {
                    "accuracy": cognitive_state.zpd_score,
                    "difficulty": enhanced_context.get('current_difficulty', 0.5),
                    "interaction_count": st.session_state.quiz_progress["current"],
                    "task_type": 0.5  # Default
                }
            }
            
            # Also store scaffolding for UI display
            st.session_state["scaffolding"] = scaffolding_strategy
            
            print(f"DEBUG: 🎯 Updated UI with orchestrator values - CL: {cognitive_state.cognitive_load:.2f}, ZPD: {cognitive_state.zpd_score:.2f}")
        
        else:
            print(f"DEBUG: ⚠️ No orchestrator context available - using fallback analytics")
            # Use simple analytics fallback
            update_cognitive_load_simple_analytics(result)
            
        
        # Step 3: Enhanced quiz evaluation (existing logic)
        result = quiz_system.submit_answer(
            quiz_data=st.session_state.current_quiz_data,
            answer=answer.strip()
        )
        
        if not result:
            st.error("Failed to evaluate answer.")
            return
        
        # Step 4: Log orchestrator decision if available
        if orchestrator_context and hasattr(orchestrator, 'decision_logger') and orchestrator.decision_logger:
            decision_data = {
                'username': st.session_state.username,
                'course': st.session_state.selected_course,
                'mode': 'quiz',
                'question_type': st.session_state.current_quiz_data.get("current_question", {}).get("type", "unknown"),
                'is_correct': result.get("correct", False),
                'orchestrator_applied': True,
                'scaffolding_strategy': orchestrator_context.get("scaffolding_strategy", {}).get("strategy_type", "none")
            }
            orchestrator.decision_logger.log_cognitive_decision(decision_data)
        
        # Step 5: Update quiz state and continue with existing logic
        st.session_state.quiz_results.append(result)
        
        if result.get("correct", False):
            st.session_state.quiz_progress["correct"] += 1
        
        st.session_state.show_feedback = True
        st.session_state.current_feedback = result
        
        # Step 6: Update mastery tracking
        update_mastery_after_quiz_answer(st.session_state.username, answer, result)
        trigger_mastery_refresh()
        
        print(f"DEBUG: ✅ Orchestrator-enhanced quiz submission complete")
        st.rerun()
        
    except Exception as e:
        print(f"ERROR: Orchestrator-enhanced quiz submission failed: {e}")
        st.error(f"Submission failed: {str(e)}")

# EMERGENCY FIX for Quiz Hanging Issue
# Add this to your streamlit_app_optimized.py

def update_mastery_after_quiz_answer_safe(username: str, answer: str, quiz_result: Dict) -> bool:
    """EMERGENCY FIX: Safe version that prevents hanging"""
    try:
        print(f"DEBUG: 🚨 SAFE: Starting safe mastery update for {username}")
        
        course = st.session_state.selected_course
        week = st.session_state.selected_week
        
        # Add timeout protection
        import signal
        import time
        
        class TimeoutException(Exception):
            pass
        
        def timeout_handler(signum, frame):
            raise TimeoutException("Progress integration timed out")
        
        # Set 10 second timeout
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)
        
        try:
            # Get current question details
            current_question = st.session_state.current_quiz_data.get("current_question", {})
            go_id = current_question.get("go_id", f"GO_{week:02d}_QUIZ_{st.session_state.quiz_progress['current']:02d}")
            
            print(f"DEBUG: 🚨 SAFE: Processing GO {go_id}")
            
            # Get mastery tracker
            mastery_tracker = get_mastery_tracker()
            if mastery_tracker:
                # Build interaction context
                interaction_context = {
                    'go_data': {
                        'go_id': go_id,
                        'skill_name': current_question.get("skill_name", "Quiz Question"),
                        'description': current_question.get("text", "Quiz question")
                    },
                    'lo_data': {
                        'title': f"Learning Objective Week {week}"
                    },
                    'week_topic': f"Week {week}",
                    'course_code': course,
                    'is_quiz': True,
                    'correct': quiz_result.get("correct", False),
                    'score': quiz_result.get("score", 0.0),
                    'username': username,
                    'question_number': st.session_state.quiz_progress['current'],
                    'quiz_data': st.session_state.current_quiz_data
                }
                
                # Create synthetic response for mastery assessment
                is_correct = quiz_result.get("correct", False)
                student_response = f"Quiz answer: {answer} (Result: {'Correct' if is_correct else 'Incorrect'})"
                
                print(f"DEBUG: 🚨 SAFE: About to update mastery")
                
                # STEP 1: Update mastery system with timeout protection
                try:
                    import asyncio
                    import concurrent.futures
                    
                    def update_mastery_sync():
                        return asyncio.run(mastery_tracker.update_learner_mastery(
                            username, course, student_response, go_id, 
                            f"LO_{week:02d}_01", week, interaction_context
                        ))
                    
                    # Use thread executor with timeout
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(update_mastery_sync)
                        mastery_result = future.result(timeout=5)  # 5 second timeout
                        
                    print(f"DEBUG: 🚨 SAFE: Mastery update completed")
                    
                    if mastery_result:
                        print(f"DEBUG: ✅ SAFE: Quiz mastery updated for {go_id} - Correct: {is_correct}")
                        
                        # STEP 2: SIMPLIFIED progress update (bypass complex bridge)
                        print(f"DEBUG: 🚨 SAFE: Applying simplified progress update")
                        
                        # Get current progress
                        auth_service = get_auth_service()
                        if auth_service:
                            current_progress = auth_service.redis_client.get_user_progress(username)
                            course_progress = current_progress.get(course, {})
                            current_completion = course_progress.get("completion", 0.0)
                            
                            # Simple increment: 1/11 = ~0.091 per question if correct
                            if is_correct:
                                increment = 1.0 / 11  # 11 questions in quiz
                                
                                try:
                                    auth_service.redis_client.update_user_progress(
                                        username=username,
                                        course=course,
                                        week=week,
                                        increment_completion=increment
                                    )
                                    
                                    print(f"DEBUG: ✅ SAFE: Simple progress increment applied: {increment:.3f}")
                                    
                                    # Show success message
                                    st.success(f"✅ Progress updated! (+{increment*100:.1f}%)")
                                    
                                except Exception as e:
                                    print(f"DEBUG: ❌ SAFE: Simple progress update failed: {e}")
                            
                        # STEP 3: Force UI refresh
                        trigger_mastery_refresh()
                        
                        return True
                        
                except concurrent.futures.TimeoutError:
                    print(f"DEBUG: ❌ SAFE: Mastery update timed out")
                    return False
                except Exception as e:
                    print(f"DEBUG: ❌ SAFE: Mastery update failed: {e}")
                    return False
                    
        finally:
            # Cancel timeout
            signal.alarm(0)
            
        return False
        
    except TimeoutException:
        print(f"DEBUG: ❌ SAFE: Overall operation timed out")
        st.error("⚠️ Progress update timed out - continuing with quiz")
        return False
        
    except Exception as e:
        print(f"DEBUG: ❌ SAFE: Error in safe mastery update: {e}")
        st.error(f"⚠️ Progress update error - continuing with quiz")
        return False

def submit_answer_emergency_safe(answer: str):
    """EMERGENCY: Safe version of submit_answer that won't hang"""
    print(f"DEBUG: 🚨 EMERGENCY: Safe answer submission started")
    
    if not st.session_state.quiz_active:
        st.error("No active quiz session.")
        return
    
    if not st.session_state.current_quiz_data:
        st.error("No quiz data available.")
        return
    
    if not answer or not answer.strip():
        st.error("Please provide an answer.")
        return
    
    quiz_system = get_quiz_system()
    if not quiz_system:
        st.error("Quiz system not available.")
        return
    
    try:
        print(f"DEBUG: 🚨 EMERGENCY: Evaluating answer with quiz system")
        
        # STEP 1: Get quiz evaluation
        result = quiz_system.submit_answer(
            quiz_data=st.session_state.current_quiz_data,
            answer=answer.strip()
        )
        
        print(f"DEBUG: 🚨 EMERGENCY: Quiz evaluation result: {result}")
        
        if not result:
            st.error("Failed to evaluate answer.")
            return
        
        # STEP 2: Update quiz state FIRST (before mastery)
        st.session_state.quiz_results.append(result)
        
        if result.get("correct", False):
            st.session_state.quiz_progress["correct"] += 1
        
        st.session_state.show_feedback = True
        st.session_state.current_feedback = result
        
        print(f"DEBUG: 🚨 EMERGENCY: Quiz state updated successfully")
        
        # STEP 3: Try safe mastery update (with timeout protection)
        username = st.session_state.username
        try:
            update_mastery_after_quiz_answer_safe(username, answer, result)
        except Exception as e:
            print(f"DEBUG: ❌ EMERGENCY: Mastery update failed but continuing: {e}")
            st.warning("⚠️ Progress tracking had an issue but your answer was recorded")
        
        print(f"DEBUG: ✅ EMERGENCY: Safe answer submission completed")
        st.rerun()
            
    except Exception as e:
        print(f"ERROR: 🚨 EMERGENCY: Safe submission failed: {e}")
        st.error(f"Submission failed: {str(e)}")


def submit_tutor_response_with_orchestrator(student_input: str):
    """ENHANCED: Submit tutor response with progress integration"""
    tutor_system = get_tutor_system()
    orchestrator = get_orchestrator()
    
    if not tutor_system or not st.session_state.tutor_session:
        st.error("No active tutoring session.")
        return
   
    try:
        print(f"DEBUG: 🎓 Processing tutor response with orchestrator integration")
        
        # Step 1: Build enhanced session context
        enhanced_context = {
            'tutor_session': st.session_state.tutor_session,
            'selected_week': st.session_state.get("selected_week", 1),
            'current_mode': 'tutor',
            'interaction_count': len(st.session_state.tutor_messages),
            'session_progress': (st.session_state.tutor_session.current_go_index / 
                               len(st.session_state.tutor_session.go_list)) * 100,
            'current_go_id': st.session_state.tutor_session.go_list[st.session_state.tutor_session.current_go_index]['go_id']
        }
        
        # Step 2: Get orchestrator recommendations
        orchestrator_context = None
        if orchestrator:
            try:
                orchestrator_context = process_orchestrator_interaction(
                    orchestrator=orchestrator,
                    interaction_type="tutor",
                    student_input=student_input,
                    session_context=enhanced_context
                )
                print(f"DEBUG: ✅ Got orchestrator recommendations for tutor")
            except Exception as e:
                print(f"DEBUG: Orchestrator processing failed: {e}")
        
        # Step 3: Add student message to conversation
        st.session_state.tutor_messages.append({
            "role": "student",
            "content": student_input,
            "timestamp": datetime.now().isoformat(),
            "go_id": st.session_state.tutor_session.go_list[st.session_state.tutor_session.current_go_index]['go_id']
        })
        
        # Step 4: Process with enhanced tutor system
        
        rag_content = get_relevant_course_content(student_input)
        result = tutor_system.process_student_response(
            session=st.session_state.tutor_session,
            student_input=student_input,
            rag_content=rag_content,
            orchestrator_context=orchestrator_context  # NEW: Pass orchestrator context
        )

        # 🚨 NEW: Update progress from tutor mastery achievements
        if result.get('has_achieved_mastery', False):
            username = st.session_state.username
            course = st.session_state.selected_course
            week = st.session_state.selected_week
            
            # Create tutor interaction context
            current_go = session.go_list[session.current_go_index]
            tutor_context = {
                'go_data': current_go,
                'lo_data': {'title': f"Learning Objective Week {week}"},
                'week_topic': f"Week {week}",
                'course_code': course,
                'is_tutor': True,
                'mastery_achieved': True,
                'username': username
            }
            
            # Update progress via bridge
            progress_bridge = get_progress_bridge()
            if progress_bridge:
                progress_result = progress_bridge.update_progress_from_mastery(
                    username, course, week, tutor_context
                )
                
                if progress_result.get("progress_updated"):
                    print(f"DEBUG: 🎓 Tutor progress updated: {progress_result}")
                    
                    # Show achievements
                    achievements = progress_result.get("achievements", [])
                    for achievement in achievements:
                        st.success(f"🎉 {achievement}")
                        
        
        # Step 5: Enhanced tutor message with orchestrator metadata
        tutor_message = {
            "role": "tutor",
            "content": result['message'],
            "timestamp": datetime.now().isoformat(),
            "is_correct": result.get('is_correct', False),
            "scaffolding_level": result.get('scaffolding_level', 'medium'),
            "orchestrator_applied": result.get('orchestrator_applied', False)
        }
        
        st.session_state.tutor_messages.append(tutor_message)
        
        # Step 6: Check completion
        if result.get('session_complete', False):
            st.session_state.tutor_active = False
            st.balloons()
            st.success("🎉 Tutoring session completed with orchestrator guidance!")
        
        print(f"DEBUG: ✅ Orchestrator-enhanced tutor response complete")
        st.rerun()
        
    except Exception as e:
        print(f"ERROR: Enhanced tutor response failed: {e}")
        # Fallback to basic tutor processing
        submit_tutor_response_fallback(student_input)
        
def submit_answer(answer: str):
    """REPLACED: Now uses orchestrator-enhanced quiz submission"""
    # submit_answer_with_orchestrator(answer)
    # submit_answer_with_orchestrator_preserved(answer)
    submit_answer_with_background_motivation(answer)
    

def continue_to_next_question():
    """Continue to next question with progress verification"""
    print(f"DEBUG: ===== CONTINUE TO NEXT QUESTION =====")
    
    # Verify current progress
    verify_progress_after_quiz()
    
    quiz_system = get_quiz_system()
    if not quiz_system:
        st.error("Quiz system not available.")
        return
    
    # Clear feedback
    st.session_state.show_feedback = False
    st.session_state.current_feedback = None
    st.session_state.quiz_progress["current"] += 1
    
    print(f"DEBUG: Moving to question {st.session_state.quiz_progress['current']}")
    
    if st.session_state.quiz_progress["current"] > st.session_state.quiz_progress["total"]:
        print(f"DEBUG: Quiz completed!")
        end_quiz()
        return
    
    try:
        next_quiz_data = quiz_system.get_next_question(st.session_state.current_quiz_data)
        
        if next_quiz_data:
            st.session_state.current_quiz_data = next_quiz_data
            print(f"DEBUG: Next question loaded successfully")
        else:
            print(f"DEBUG: No more questions - ending quiz")
            end_quiz()
            return
        
        st.rerun()
        
    except Exception as e:
        print(f"ERROR: Failed to get next question: {e}")
        st.error("Failed to load next question.")
        
def start_quiz():
    """Start quiz function with duplicate prevention"""
    print(f"DEBUG: ===== START QUIZ =====")
    
    # Prevent duplicate quiz starts
    if st.session_state.quiz_active or st.session_state.current_quiz_data:
        print("DEBUG: Quiz already active, ignoring duplicate start request")
        return
    
    quiz_system = get_quiz_system()
    if not quiz_system:
        st.error("Quiz system not available.")
        return
    
    if not st.session_state.selected_course or not st.session_state.selected_week:
        st.error("Please select a course and week.")
        return
    
    try:
        # Set quiz as starting to prevent duplicate calls
        st.session_state.quiz_active = True

        # GO-based quiz generation strategy
        go_components = get_go_strategy_components()
        if go_components:
            enhanced_quiz_data = go_components["quiz_sequencer"].generate_week_quiz(
                st.session_state.selected_course,
                st.session_state.selected_week,
                st.session_state.username
            )
            
            if "error" not in enhanced_quiz_data:
                st.info(f"📊 **Quiz Strategy:** One question per learning objective")
                st.info(f"⭐ **Coverage:** {len(enhanced_quiz_data['go_coverage'])} specific skills")
                
                # Store GO mapping for enhanced scoring
                st.session_state.quiz_go_mapping = enhanced_quiz_data
                print(f"DEBUG: Enhanced quiz covers GOs: {enhanced_quiz_data['go_coverage']}")
            else:
                print(f"DEBUG: Enhanced quiz generation failed: {enhanced_quiz_data['error']}")
        else:
            print("DEBUG: GO components not available, using traditional quiz")
               
        quiz_data = quiz_system.start_quiz(
            course=st.session_state.selected_course,
            week=st.session_state.selected_week,
            username=st.session_state.username
        )
        
        if quiz_data:
            st.session_state.current_quiz_data = quiz_data
            st.session_state.quiz_progress = {
                "current": 1,
                "total": len(quiz_data.get("question_plan", [])),
                "correct": 0
            }
            st.session_state.quiz_results = []
            st.session_state.show_feedback = False
            st.session_state.quiz_completed = False
            
            # Initialize learning analytics for first question
            simple_analytics = get_simple_analytics()
            if simple_analytics:
                current_question = quiz_data.get("current_question", {})
                question_type = current_question.get("type", "multiple_choice")
                
                initial_analytics = simple_analytics.calculate_learning_metrics(
                    quiz_results=[],
                    question_number=1,
                    current_question_type=question_type
                )
                
                st.session_state["cognitive_load"] = {
                    "cl_value": initial_analytics['cognitive_load'],
                    "zpd_score": initial_analytics['zpd_score'],
                    "motivation": initial_analytics['motivation'],
                    "fatigue": initial_analytics['fatigue'],
                    "timestamp": time.time(),
                    "question_number": 1,
                    "formula_variables": {
                        "accuracy": initial_analytics['zpd_score'],
                        "difficulty": initial_analytics['difficulty'],
                        "interaction_count": 1,
                        "task_type": initial_analytics['task_type']
                    }
                }
            
            print(f"DEBUG: Quiz started - {st.session_state.quiz_progress['total']} questions")
            st.rerun()
        else:
            st.session_state.quiz_active = False  # Reset if failed
            st.error("Failed to start quiz.")
            
    except Exception as e:
        st.session_state.quiz_active = False  # Reset if failed
        print(f"ERROR: Quiz start failed: {e}")
        st.error(f"Failed to start quiz: {str(e)}")

def end_quiz():
    """End quiz function"""
    print(f"DEBUG: ===== END QUIZ =====")
    
    st.session_state.quiz_active = False
    st.session_state.quiz_completed = True
    
    total = len(st.session_state.quiz_results)
    correct = sum(1 for r in st.session_state.quiz_results if r.get("correct", False))
    accuracy = (correct / total * 100) if total > 0 else 0
    
    print(f"DEBUG: Quiz ended - {correct}/{total} correct ({accuracy:.1f}%)")
    st.rerun()

def render_quiz_results():
    """Show quiz results"""
    total = len(st.session_state.quiz_results)
    correct = sum(1 for r in st.session_state.quiz_results if r.get("correct", False))
    accuracy = (correct / total * 100) if total > 0 else 0
    
    st.balloons()
    st.success(f"🎉 Quiz Complete! Score: {correct}/{total} ({accuracy:.1f}%)")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Questions", total)
    with col2:
        st.metric("Correct", correct)
    with col3:
        st.metric("Accuracy", f"{accuracy:.1f}%")
    
    if accuracy >= 90:
        st.success("🌟 Excellent work!")
    elif accuracy >= 75:
        st.info("👍 Good job!")
    elif accuracy >= 60:
        st.warning("📚 Room for improvement.")
    else:
        st.error("🤔 More study needed.")

# TUTOR FUNCTIONS
def start_tutor_session():
    """Start a new tutoring session"""
    tutor_system = get_tutor_system()
    kc_loader = get_current_kc_loader()
    
    if not tutor_system or not kc_loader:
        st.error("Tutor system not available. Please check OpenAI API key.")
        return
    
    if not st.session_state.selected_course or not st.session_state.selected_week:
        st.error("Please select a course and week first.")
        return
    
    try:
        print(f"DEBUG: Starting tutor session for {st.session_state.username} - {st.session_state.selected_course} Week {st.session_state.selected_week}")

        # GO-based progression strategy
        go_components = get_go_strategy_components()
        if go_components:
            next_go = go_components["tutor_sequencer"].get_next_tutor_go(
                st.session_state.username, 
                st.session_state.selected_course, 
                st.session_state.selected_week
            )
            
            if next_go:
                st.info(f"🎯 **Next focus:** {next_go['skill_name']}")
                st.info(f"📊 **Current mastery:** {next_go['current_mastery']*100:.1f}%")
                st.info(f"💡 **Reason:** {next_go['reason']}")
                
                # Store in session state for tutor to use
                st.session_state.current_target_go = next_go
                print(f"DEBUG: Target GO set: {next_go['go_id']} - {next_go['skill_name']}")
            else:
                st.success("🎉 **All learning objectives for this week completed!**")
                st.info("You can review previous concepts or move to the next week.")
                return
        else:
            print("DEBUG: GO components not available, using traditional approach")
               
        week_content = kc_loader.get_week_content(st.session_state.selected_course, st.session_state.selected_week)
        
        go_list = []
        for lo in week_content.learning_objectives:
            for go in lo.granular_objectives:
                go_list.append({
                    "go_id": go.go_id,
                    "skill_name": go.skill_name,
                    "description": go.description,
                    "content_keywords": go.content_keywords
                })
        
        if not go_list:
            st.error("No learning objectives found for this week.")
            return
        
        session = tutor_system.start_tutoring_session(
            course=st.session_state.selected_course,
            week=st.session_state.selected_week,
            username=st.session_state.username,
            kc_loader=kc_loader,
            go_list=go_list
        )
        
        if session:
            st.session_state.tutor_session = session
            st.session_state.tutor_active = True
            st.session_state.tutor_messages = []
            
            if session.conversation_history:
                initial_message = session.conversation_history[-1]['content']
                initial_msg = {
                    "role": "tutor",
                    "content": initial_message,
                    "timestamp": datetime.now().isoformat()
                }
                st.session_state.tutor_messages.append(initial_msg)
                print(f"DEBUG: Added initial message to tutor_messages: {initial_message[:50]}...")
            
            st.success(f"Tutoring session started! We'll work through {len(go_list)} concepts together.")
            st.rerun()
        else:
            st.error("Failed to start tutoring session. Please try again.")
            
    except Exception as e:
        print(f"ERROR: Failed to start tutor session: {e}")
        st.error(f"Tutor session start failed: {str(e)}")

def submit_tutor_response(student_input: str):
    """REPLACED: Now uses orchestrator-enhanced tutor submission"""
    # submit_tutor_response_with_orchestrator(student_input)
    submit_tutor_response_with_background_motivation(student_input)
    

def submit_tutor_response_fallback(student_input: str):
    """Fallback tutor response when orchestrator fails"""
    tutor_system = get_tutor_system()
    if not tutor_system or not st.session_state.tutor_session:
        return
    
    try:
        rag_content = get_relevant_course_content(student_input)
        
        result = tutor_system.process_student_response(
            session=st.session_state.tutor_session,
            student_input=student_input,
            rag_content=rag_content
        )
        
        if result:
            st.session_state.tutor_messages.append({
                "role": "tutor",
                "content": result['message'],
                "timestamp": datetime.now().isoformat(),
                "is_correct": result.get('is_correct', False),
                "scaffolding_level": result.get('scaffolding_level', 'medium')
            })
            
            if result.get('session_complete', False):
                st.session_state.tutor_active = False
                st.balloons()
                st.success("🎉 Tutoring session completed! Great work!")
            
            st.rerun()
            
    except Exception as e:
        print(f"ERROR: Fallback tutor response failed: {e}")
        st.error("Sorry, I'm having trouble processing your response right now.")

def end_tutor_session():
    """End tutoring session"""
    if st.session_state.tutor_session:
        tutor_system = get_tutor_system()
        if tutor_system:
            summary = tutor_system.get_session_summary(st.session_state.tutor_session)
            print(f"DEBUG: Tutor session ended - Accuracy: {summary['accuracy']:.1%}, GOs completed: {summary['gos_completed']}/{summary['total_gos']}")
    
    st.session_state.tutor_active = False
    st.session_state.tutor_session = None
    st.rerun()

def get_relevant_course_content(query: str) -> str:
    """Retrieve relevant content from ChromaDB for the current course"""
    try:
        import chromadb
        import os
        
        if not st.session_state.selected_course:
            return "No course selected for content retrieval."
        
        chroma_path = f"./data/chroma_data/{st.session_state.selected_course}"
        
        if not os.path.exists(chroma_path):
            return f"No content database found for {st.session_state.selected_course}."
        
        client = chromadb.PersistentClient(path=chroma_path)
        collections = client.list_collections()
        
        if not collections:
            return f"No content collections found for {st.session_state.selected_course}."
        
        collection = collections[0]
        chat_system = get_chat_system()
        if not chat_system:
            return "Chat system not available for content retrieval."
        
        try:
            embedding_response = chat_system.embeddings.create(
                model="text-embedding-ada-002",
                input=query
            )
            query_embedding = embedding_response.data[0].embedding
            
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=3
            )
            
            content_pieces = []
            if results["documents"] and results["documents"][0]:
                for doc in results["documents"][0]:
                    if len(doc) > 50:
                        content_pieces.append(doc[:800])
            
            if content_pieces:
                return f"Relevant course content:\n" + "\n\n".join(content_pieces)
            else:
                return f"No relevant content found for '{query}' in {st.session_state.selected_course}."
                
        except Exception as e:
            print(f"ERROR: Embedding search failed: {e}")
            results = collection.query(
                query_texts=[query],
                n_results=3
            )
            
            content_pieces = []
            if results["documents"] and results["documents"][0]:
                for doc in results["documents"][0]:
                    if len(doc) > 50:
                        content_pieces.append(doc[:800])
            
            if content_pieces:
                return f"Relevant course content (text search):\n" + "\n\n".join(content_pieces)
            else:
                return f"No relevant content found for '{query}' in {st.session_state.selected_course}."
        
    except Exception as e:
        print(f"ERROR: Content retrieval failed: {e}")
        return f"Content retrieval failed: {str(e)}"

def clear_chat_history():
    """Clear the chat message history"""
    username = st.session_state.get("username", "user")
    conversation_key = f"conversation_{username}"
    if conversation_key in st.session_state:
        st.session_state[conversation_key] = []
    st.session_state.chat_session_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    st.rerun()

# DISPLAY AND ANALYTICS FUNCTIONS
def display_cognitive_load_in_sidebar():
    """ENHANCED: Display learning analytics with orchestrator integration"""
    if "cognitive_load" in st.session_state:
        cl_data = st.session_state["cognitive_load"]
        
        with st.sidebar:
            orchestrator_active = cl_data.get("orchestrator_active", False)
            title = "🧠 Adaptive Analytics" if orchestrator_active else "📱 Learning Analytics"
            
            with st.expander(title, expanded=True):
                try:
                    cl_value = cl_data.get("cl_value", 5.0)
                    zpd_score = cl_data.get("zpd_score", 0.5)
                    motivation = cl_data.get("motivation", 0.5)
                    
                    # Show orchestrator status
                    if orchestrator_active:
                        st.success("🧠 **Adaptive Mode Active**")
                        st.caption("Questions adapt to your cognitive state")
                    else:
                        st.info("📱 **Standard Analytics**")
                        st.caption("Basic performance tracking")
                    
                    # Show update status
                    if "timestamp" in cl_data:
                        last_update = cl_data["timestamp"]
                        time_diff = time.time() - last_update
                        question_num = cl_data.get("question_number", 1)
                        
                        if time_diff < 3:
                            st.success(f"🔄 Q{question_num} - Just updated!")
                        else:
                            st.info(f"📊 Q{question_num} - {time_diff:.0f}s ago")
                    
                    # Enhanced metrics display
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if 3.5 <= cl_value <= 6.5:
                            st.metric("Cognitive Load", f"{cl_value:.1f}/10", delta="Optimal 🎯")
                            st.caption("Perfect challenge level")
                        elif cl_value < 3.5:
                            st.metric("Cognitive Load", f"{cl_value:.1f}/10", delta="Too Easy 📈")
                            st.caption("You might be bored")
                        else:
                            st.metric("Cognitive Load", f"{cl_value:.1f}/10", delta="Too Hard 📉")
                            st.caption("Feeling overwhelmed?")
                    
                    with col2:
                        if 0.5 <= zpd_score <= 0.8:
                            st.metric("Challenge Level", f"{zpd_score:.2f}", delta="Good ✅")
                            st.caption("In the zone!")
                        elif zpd_score > 0.8:
                            st.metric("Challenge Level", f"{zpd_score:.2f}", delta="Too Easy 🔼")
                            st.caption("Need harder questions")
                        else:
                            st.metric("Challenge Level", f"{zpd_score:.2f}", delta="Too Hard 🔽")
                            st.caption("Struggling a bit")
                    
                    # Adaptive recommendations
                    if orchestrator_active:
                        st.write("**🎯 Adaptive Recommendations:**")
                        
                        if "scaffolding" in st.session_state:
                            scaffolding = st.session_state["scaffolding"]
                            intervention = scaffolding.get("intervention_type", "maintain_flow")
                            
                            if intervention == "immediate_support":
                                st.warning("📚 Providing extra support on next question")
                            elif intervention == "advanced_challenge":
                                st.info("🚀 Increasing challenge level")
                            elif intervention == "concept_review":
                                st.info("🔄 Will review key concepts")
                            else:
                                st.success("✅ Maintaining current approach")
                        
                        # Show formula if requested
                        if "formula_variables" in cl_data:
                            with st.expander("📊 Adaptive Formula", expanded=False):
                                vars = cl_data["formula_variables"]
                                st.write("**Cognitive Load Calculation:**")
                                st.code("CL = 0.5 + 1.0×Difficulty + 4.5×(1-Accuracy) + 0.1×Questions + 1.0×TaskType")
                                
                                accuracy = vars.get('accuracy', zpd_score)
                                difficulty = vars.get('difficulty', 0.5)
                                st.text(f"• Your accuracy: {accuracy:.2f}")
                                st.text(f"• Question difficulty: {difficulty:.2f}")
                                st.text(f"• Questions answered: {vars.get('interaction_count', 1)}")
                                st.text(f"• Task type: {'Open-ended' if vars.get('task_type', 0) > 0.5 else 'Structured'}")
                    
                    else:
                        # Basic recommendations
                        st.write("**💡 Learning Tips:**")
                        if cl_value > 7:
                            st.warning("Consider taking a short break!")
                        elif cl_value < 3:
                            st.info("You're doing great! Ready for more challenge?")
                        else:
                            st.success("Keep up the good work!")
                        
                except Exception as e:
                    st.error(f"Analytics display error: {e}")
                    print(f"DEBUG: Sidebar display error: {e}")
                    
    else:
        # Enhanced placeholder
        with st.sidebar:
            with st.expander("🧠 Learning Analytics", expanded=False):
                orchestrator = get_orchestrator()
                if orchestrator and hasattr(orchestrator, 'mcp_client'):
                    st.success("🧠 **Adaptive System Ready**")
                    st.caption("Start learning to see adaptive analytics!")
                    
                    st.write("**What adaptive mode tracks:**")
                    st.text("• Real-time cognitive load")
                    st.text("• Zone of Proximal Development")
                    st.text("• Motivation patterns")
                    st.text("• Personalized scaffolding")
                    st.text("• Learning strategy optimization")
                else:
                    st.info("📱 **Standard Analytics Available**")
                    st.caption("Start learning to see your analytics!")
                    
                    st.write("**What I'll track:**")
                    st.text("• Performance trends")
                    st.text("• Question difficulty")
                    st.text("• Study patterns")
                    st.text("• Progress indicators")

def display_system_status_in_sidebar():
    """Show current system capabilities in sidebar"""
    with st.sidebar:
        with st.expander("🔧 System Status", expanded=False):
            
            # Orchestrator status
            orchestrator = get_orchestrator()
            if orchestrator and hasattr(orchestrator, 'mcp_client'):
                st.success("🧠 **Full Orchestrator Active**")
                
                if hasattr(orchestrator, 'scaffolding_engine'):
                    st.success("✅ Advanced scaffolding engine")
                else:
                    st.warning("⚠️ Basic scaffolding only")
                
                if hasattr(orchestrator, 'decision_logger'):
                    st.success("✅ Decision logging active")
                    st.caption("Generating research data")
                else:
                    st.info("📊 No decision logging")
                
                # MCP tool status
                try:
                    tools_info = orchestrator.mcp_client.get_available_tools()
                    tool_count = tools_info.get("total_tools", 0)
                    st.info(f"🔧 {tool_count} MCP tools available")
                    
                    capabilities = tools_info.get("capabilities", {})
                    if capabilities.get("rag_retrieval"):
                        st.caption("✅ RAG content retrieval")
                    if capabilities.get("kc_models"):
                        st.caption("✅ Knowledge component models")
                    if capabilities.get("web_search"):
                        st.caption("✅ Web search integration")
                        
                except Exception as e:
                    st.caption(f"⚠️ Tool status check failed")
                    
            else:
                st.info("📱 **Basic System Mode**")
                st.caption("Limited adaptive capabilities")
            
            # Storage status
            auth_service = get_auth_service()
            if auth_service and auth_service.redis_client:
                st.success("✅ Redis storage active")
            else:
                st.warning("⚠️ File storage only")
            
            # Analytics status
            if "cognitive_load" in st.session_state and st.session_state["cognitive_load"].get("orchestrator_active"):
                st.success("✅ Adaptive analytics running")
            else:
                st.info("📊 Basic analytics only")

# STATUS FUNCTIONS FOR SIDEBAR
def get_chat_status() -> dict:
    """Get chat mode status for sidebar"""
    username = st.session_state.get("username", "user")
    conversation = get_conversation_history_safe(username)
    if conversation:
        user_messages = len([m for m in conversation if m.get("role") == "user"])
        return {
            "emoji": "💭",
            "text": f"({user_messages} msgs)"
        }
    else:
        return {"emoji": "💬", "text": ""}

def get_tutor_status() -> dict:
    """Get tutor mode status for sidebar"""
    if st.session_state.tutor_active and st.session_state.tutor_session:
        session = st.session_state.tutor_session
        progress = (session.current_go_index / len(session.go_list)) * 100
        return {
            "emoji": "📖",
            "text": f"({progress:.0f}%)"
        }
    elif st.session_state.tutor_session and not st.session_state.tutor_active:
        return {
            "emoji": "✅", 
            "text": "(Complete)"
        }
    else:
        return {"emoji": "🎓", "text": ""}

def get_quiz_status() -> dict:
    """Get quiz mode status for sidebar"""
    if st.session_state.quiz_active:
        progress = st.session_state.quiz_progress
        return {
            "emoji": "⏳",
            "text": f"({progress['current']}/{progress['total']})"
        }
    elif st.session_state.quiz_completed:
        total = len(st.session_state.quiz_results)
        correct = sum(1 for r in st.session_state.quiz_results if r.get("correct", False))
        accuracy = (correct/total*100) if total > 0 else 0
        return {
            "emoji": "✅",
            "text": f"({accuracy:.0f}%)"
        }
    else:
        return {"emoji": "⭐", "text": ""}

def switch_mode(new_mode: AppMode, confirm_switch: bool = False):
    """Handle mode switching with safety checks"""
    
    if not confirm_switch:
        if st.session_state.quiz_active:
            st.warning("⚠️ Quiz in progress! Are you sure you want to switch modes?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Yes, Switch", type="primary", key=f"confirm_switch_{new_mode.value}"):
                    switch_mode(new_mode, confirm_switch=True)
            with col2:
                if st.button("❌ Stay in Quiz", key=f"cancel_switch_{new_mode.value}"):
                    return
            return
    
    current_mode_str = get_current_mode_string()
    new_mode_str = new_mode.value
    
    if current_mode_str != new_mode_str:
        st.session_state.mode_history.append({
            'from': current_mode_str,
            'to': new_mode_str,
            'timestamp': datetime.now().isoformat()
        })
    
    st.session_state.current_mode = new_mode
    st.rerun()

def get_current_motivation_summary() -> Dict[str, Any]:
    """Get current motivation summary for analytics"""
    if "_motivation_analytics" not in st.session_state:
        return {"status": "inactive", "message": "No motivation data available"}
    
    analytics = st.session_state["_motivation_analytics"]
    motivation_metrics = analytics.get('motivation_metrics')
    
    summary = {
        "status": "active",
        "timestamp": analytics.get('timestamp'),
        "motivation_state": analytics.get('motivation_state', 'unknown'),
        "session_duration": time.time() - analytics.get('timestamp', time.time()),
        "username": st.session_state.get('username', 'unknown'),
        "course": st.session_state.get('selected_course', 'unknown'),
        "mode": st.session_state.get('current_mode', 'unknown')
    }
    
    if motivation_metrics:
        summary.update({
            "persistence_level": motivation_metrics.persistence_level,
            "affective_score": motivation_metrics.affective_score,
            "performance_score": motivation_metrics.performance_score,
            "session_completion_rate": motivation_metrics.session_completion_rate,
            "consecutive_correct": motivation_metrics.consecutive_correct,
            "consecutive_incorrect": motivation_metrics.consecutive_incorrect,
            "time_on_task": motivation_metrics.time_on_task,
            "help_seeking_frequency": motivation_metrics.help_seeking_frequency
        })
    
    return summary

def log_session_summary():
    """Log session summary on logout/exit"""
    try:
        if "_motivation_analytics" in st.session_state:
            summary = get_current_motivation_summary()
            
            # Log session end
            log_dir = Path("./data/motivation_logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            
            session_file = log_dir / f"session_summaries_{datetime.now().strftime('%Y%m')}.csv"
            
            # Write session summary
            file_exists = session_file.exists()
            with open(session_file, 'a', newline='') as f:
                if summary["status"] == "active":
                    writer = csv.DictWriter(f, fieldnames=summary.keys())
                    if not file_exists:
                        writer.writeheader()
                    writer.writerow(summary)
            
            print(f"DEBUG: 📊 Session motivation summary logged")
            
    except Exception as e:
        print(f"DEBUG: Failed to log session summary: {e}")

def get_current_mode_string():
    """Get current mode as string"""
    try:
        if hasattr(st.session_state.current_mode, 'value'):
            return st.session_state.current_mode.value
        else:
            return str(st.session_state.current_mode).lower()
    except:
        return "chat"

def debug_orchestrator_status():
    """Debug helper to check orchestrator status"""
    try:
        orchestrator = get_orchestrator()
        if orchestrator:
            st.sidebar.success("🤖 Orchestrator: Online")
            
            if "cognitive_load" in st.session_state:
                cl_value = st.session_state["cognitive_load"]["cl_value"]
                st.sidebar.info(f"Last CL: {cl_value:.1f}")
        else:
            st.sidebar.warning("🤖 Orchestrator: Offline")
            
    except Exception as e:
        st.sidebar.error(f"🤖 Orchestrator: Error ({str(e)[:30]}...)")

def debug_mastery_data():
    """Debug function to check current mastery data"""
    if st.sidebar.button("🧠 Check My Progress"):
        with st.sidebar.expander("My Learning Progress", expanded=True):
            mastery_tracker = get_mastery_tracker()
            if mastery_tracker:
                try:
                    username = st.session_state.get("username", "user")
                    course = st.session_state.get("selected_course", "DEMO101")
                    
                    mastery_data = mastery_tracker.get_mastery_summary(username, course)
                    
                    st.write("**📊 Current Mastery Levels:**")
                    if mastery_data.get('go_masteries'):
                        st.write(f"**Skills Tracked:** {len(mastery_data['go_masteries'])}")
                        for go_id, level in list(mastery_data['go_masteries'].items())[:5]:
                            st.write(f"• {go_id}: {level:.2f}")
                    else:
                        st.write("No skill mastery data yet")
                    
                    st.write(f"**Total Interactions:** {mastery_data.get('total_interactions', 0)}")
                    st.write(f"**Last Session:** {mastery_data.get('last_session', 'Never')}")
                    
                    averages = mastery_data.get('averages', {})
                    st.write(f"**Average GO Mastery:** {averages.get('go_mastery', 0.0):.2f}")
                    st.write(f"**Average LO Mastery:** {averages.get('lo_mastery', 0.0):.2f}")
                    st.write(f"**Average Week Mastery:** {averages.get('week_mastery', 0.0):.2f}")
                    
                except Exception as e:
                    st.error(f"Error checking progress: {e}")
            else:
                st.error("Mastery tracker not available")

def debug_motivation_state():
    """Debug current motivation assessment"""
    if st.sidebar.button("🧪 Test Motivation System"):
        orchestrator = get_orchestrator()
        if orchestrator and hasattr(orchestrator, 'mcp_client'):
            # Simulate a test interaction
            test_context = {
                'username': st.session_state.username,
                'course': st.session_state.selected_course,
                'interaction_count': 5,
                'session_completion_rate': 0.7,
                'recent_results': [True, False, True, True]
            }
            
            # This should trigger motivation assessment
            st.sidebar.json(test_context)
            st.sidebar.success("✅ Motivation system integration test")
        else:
            st.sidebar.error("❌ Advanced orchestrator not available")

# Add these functions to your streamlit_app_optimized.py

def store_motivation_metrics_background(orchestrator_result: Dict[str, Any]):
    """Store motivation metrics in background for analytics - NOT visible to students"""
    if orchestrator_result and orchestrator_result.get('processing_successful', False):
        # Store in session state for metrics collection
        st.session_state["_motivation_analytics"] = {
            'motivation_state': orchestrator_result.get('motivation_state', 'unknown'),
            'motivation_metrics': orchestrator_result.get('motivation_metrics'),
            'motivation_feedback': orchestrator_result.get('motivation_feedback', {}),
            'cognitive_state': orchestrator_result.get('cognitive_state'),
            'scaffolding_strategy': orchestrator_result.get('scaffolding_strategy', {}),
            'timestamp': time.time(),
            'session_id': st.session_state.get('current_session_id', 'unknown')
        }
        
        # Log to file for analytics
        log_motivation_metrics_to_file(orchestrator_result, st.session_state.username)
        
        print(f"DEBUG: 📊 Background motivation metrics stored - State: {orchestrator_result.get('motivation_state')}")

def log_motivation_metrics_to_file(orchestrator_result: Dict[str, Any], username: str):
    """Log motivation metrics to CSV file for analysis"""
    try:
        log_dir = Path("./data/motivation_logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / f"motivation_metrics_{datetime.now().strftime('%Y%m')}.csv"
        
        # Prepare log entry
        motivation_metrics = orchestrator_result.get('motivation_metrics')
        cognitive_state = orchestrator_result.get('cognitive_state')
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'username': username,
            'course': st.session_state.get('selected_course', 'unknown'),
            'week': st.session_state.get('selected_week', 0),
            'mode': st.session_state.get('current_mode', 'unknown'),
            'motivation_state': orchestrator_result.get('motivation_state', 'unknown'),
            'persistence_level': motivation_metrics.persistence_level if motivation_metrics else 'unknown',
            'affective_score': motivation_metrics.affective_score if motivation_metrics else 0.0,
            'performance_score': motivation_metrics.performance_score if motivation_metrics else 0.0,
            'session_completion_rate': motivation_metrics.session_completion_rate if motivation_metrics else 0.0,
            'consecutive_correct': motivation_metrics.consecutive_correct if motivation_metrics else 0,
            'consecutive_incorrect': motivation_metrics.consecutive_incorrect if motivation_metrics else 0,
            'time_on_task': motivation_metrics.time_on_task if motivation_metrics else 0.0,
            'help_seeking_frequency': motivation_metrics.help_seeking_frequency if motivation_metrics else 0.0,
            'cognitive_load': cognitive_state.cognitive_load if cognitive_state else 0.0,
            'zpd_score': cognitive_state.zpd_score if cognitive_state else 0.0,
            'motivation_score': cognitive_state.motivation_score if cognitive_state else 0.0,
            'fatigue_level': cognitive_state.fatigue_level if cognitive_state else 0.0
        }
        
        # Write to CSV
        file_exists = log_file.exists()
        with open(log_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=log_entry.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(log_entry)
            
    except Exception as e:
        print(f"DEBUG: Failed to log motivation metrics: {e}")

def apply_explicit_motivation_feedback(orchestrator_result: Dict[str, Any]) -> str:
    """Apply explicit motivation feedback to content generation - ENHANCED VERBIAGE"""
    if not orchestrator_result or not orchestrator_result.get('processing_successful', False):
        return ""
    
    motivation_feedback = orchestrator_result.get('motivation_feedback', {})
    motivation_state = orchestrator_result.get('motivation_state', 'unknown')
    
    # EXPLICIT feedback messages - more direct and clear
    explicit_feedback = {
        'cold_start': {
            'content_adjustment': "Welcome! I'm adjusting my teaching style to match your learning preferences. Take your time to explore.",
            'tone_modifier': "extra_welcoming",
            'system_message': "Providing initial support and positive reinforcement"
        },
        
        'motivation_drop': {
            'content_adjustment': "I notice you might be finding this challenging. Let me provide extra support and break this down into smaller, manageable steps.",
            'tone_modifier': "supportive_and_encouraging", 
            'system_message': "Detected decreased motivation - applying autonomy-supportive intervention"
        },
        
        'motivation_plateau': {
            'content_adjustment': "You're making steady progress! I'm focusing on celebrating your effort and strategic thinking.",
            'tone_modifier': "process_focused",
            'system_message': "Stable engagement detected - emphasizing growth mindset"
        },
        
        'maintained_high': {
            'content_adjustment': "Excellent engagement! I'm increasing the challenge level and offering advanced applications since you're ready for more.",
            'tone_modifier': "challenging_and_stretch",
            'system_message': "High motivation detected - escalating challenge level"
        }
    }
    
    feedback_config = explicit_feedback.get(motivation_state, explicit_feedback['motivation_plateau'])
    
    # Store for content generation systems
    st.session_state['_motivation_content_adjustments'] = {
        'message': feedback_config['content_adjustment'],
        'tone': feedback_config['tone_modifier'],
        'system_guidance': feedback_config['system_message'],
        'strategy': motivation_feedback.get('strategy', 'maintain_flow'),
        'challenge_level': motivation_feedback.get('challenge_level', 'maintain'),
        'emotional_support': motivation_feedback.get('emotional_support', False),
        'competence_celebration': motivation_feedback.get('competence_celebration', False),
        'system_adjustments': motivation_feedback.get('system_adjustments', {})
    }
    
    return feedback_config['content_adjustment']

# MODIFIED QUIZ SUBMISSION WITH BACKGROUND MOTIVATION

def submit_answer_with_background_motivation(answer: str):
    """Quiz submission with background motivation tracking"""
    print(f"DEBUG: 🎯 Quiz submission with background motivation analytics")
    
    if not st.session_state.quiz_active or not st.session_state.current_quiz_data:
        st.error("No active quiz session.")
        return
    
    quiz_system = get_quiz_system()
    orchestrator = get_orchestrator()
    
    if not quiz_system:
        st.error("Quiz system not available.")
        return
    
    try:
        # Build enhanced context for orchestrator
        enhanced_context = {
            'quiz_data': st.session_state.current_quiz_data,
            'selected_week': st.session_state.selected_week,
            'question_number': st.session_state.quiz_progress["current"],
            'total_questions': st.session_state.quiz_progress["total"],
            'current_score': st.session_state.quiz_progress["correct"],
            'quiz_history': st.session_state.quiz_results,
            'student_answer': answer.strip(),
            'course': st.session_state.selected_course,
            'username': st.session_state.username,
            'session_start_time': st.session_state.get('quiz_start_time', datetime.now()),
            'interaction_count': st.session_state.quiz_progress["current"],
            'completion_progress': st.session_state.quiz_progress["current"] / st.session_state.quiz_progress["total"],
            'recent_results': st.session_state.quiz_results[-5:] if len(st.session_state.quiz_results) >= 5 else st.session_state.quiz_results
        }
        
        # Get orchestrator analysis WITH motivation assessment (BACKGROUND ONLY)
        orchestrator_result = None
        if orchestrator:
            try:
                orchestrator_result = process_orchestrator_interaction(
                    orchestrator=orchestrator,
                    interaction_type="quiz",
                    student_input=answer.strip(),
                    session_context=enhanced_context
                )
                
                if orchestrator_result:
                    print(f"DEBUG: 🎯 Background motivation analysis complete - State: {orchestrator_result.get('motivation_state')}")
                    
                    # Store metrics in background (NOT visible to student)
                    store_motivation_metrics_background(orchestrator_result)
                    
                    # Apply explicit motivation feedback to content
                    explicit_feedback = apply_explicit_motivation_feedback(orchestrator_result)
                    
            except Exception as e:
                print(f"DEBUG: Orchestrator processing failed: {e}")
        
        # Evaluate quiz answer (ENHANCED with motivation context)
        if orchestrator_result:
            # Pass orchestrator context to quiz system for adaptive question generation
            enhanced_quiz_data = st.session_state.current_quiz_data.copy()
            enhanced_quiz_data['orchestrator_context'] = orchestrator_result
            result = quiz_system.submit_answer(enhanced_quiz_data, answer.strip())
        else:
            result = quiz_system.submit_answer(st.session_state.current_quiz_data, answer.strip())
        
        if not result:
            st.error("Failed to evaluate answer.")
            return
        
        # Update quiz state
        st.session_state.quiz_results.append(result)
        
        if result.get("correct", False):
            st.session_state.quiz_progress["correct"] += 1
        
        st.session_state.show_feedback = True
        st.session_state.current_feedback = result
        
        # Update mastery with motivation context
        enhanced_context['quiz_result'] = result
        enhanced_context['motivation_context'] = st.session_state.get("_motivation_analytics", {})
        update_mastery_after_quiz_answer(st.session_state.username, answer, result)
        
        print(f"DEBUG: ✅ Quiz submission with background motivation complete")
        st.rerun()
        
    except Exception as e:
        print(f"ERROR: Background motivation quiz submission failed: {e}")
        st.error(f"Submission failed: {str(e)}")

# MODIFIED TUTOR SUBMISSION WITH BACKGROUND MOTIVATION

def submit_tutor_response_with_background_motivation(student_input: str):
    """Tutor submission with background motivation tracking"""
    tutor_system = get_tutor_system()
    orchestrator = get_orchestrator()
    
    if not tutor_system or not st.session_state.tutor_session:
        st.error("No active tutoring session.")
        return
   
    try:
        print(f"DEBUG: 🎓 Tutor response with background motivation analytics")
        
        # Build enhanced session context
        enhanced_context = {
            'tutor_session': st.session_state.tutor_session,
            'selected_week': st.session_state.get("selected_week", 1),
            'current_mode': 'tutor',
            'interaction_count': len(st.session_state.tutor_messages),
            'session_progress': (st.session_state.tutor_session.current_go_index / 
                               len(st.session_state.tutor_session.go_list)) * 100,
            'current_go_id': st.session_state.tutor_session.go_list[st.session_state.tutor_session.current_go_index]['go_id'],
            'session_start_time': st.session_state.tutor_session.start_time,
            'recent_results': []  # Could track tutor interaction success
        }
        
        # Get orchestrator analysis (BACKGROUND ONLY)
        orchestrator_result = None
        if orchestrator:
            try:
                orchestrator_result = process_orchestrator_interaction(
                    orchestrator=orchestrator,
                    interaction_type="tutor",
                    student_input=student_input,
                    session_context=enhanced_context
                )
                
                if orchestrator_result:
                    print(f"DEBUG: 🎓 Background tutor motivation analysis complete")
                    
                    # Store metrics in background
                    store_motivation_metrics_background(orchestrator_result)
                    
                    # Apply explicit motivation feedback
                    explicit_feedback = apply_explicit_motivation_feedback(orchestrator_result)
                    
            except Exception as e:
                print(f"DEBUG: Tutor orchestrator processing failed: {e}")
        
        # Add student message to conversation
        st.session_state.tutor_messages.append({
            "role": "student",
            "content": student_input,
            "timestamp": datetime.now().isoformat(),
            "go_id": st.session_state.tutor_session.go_list[st.session_state.tutor_session.current_go_index]['go_id']
        })
        
        # Process with tutor system (ENHANCED with orchestrator context)
        rag_content = get_relevant_course_content(student_input)
        result = tutor_system.process_student_response(
            session=st.session_state.tutor_session,
            student_input=student_input,
            rag_content=rag_content,
            orchestrator_context=orchestrator_result  # Pass orchestrator context
        )
        
        # Enhanced tutor message with motivation-informed content
        tutor_message_content = result['message']
        
        # Apply explicit motivation adjustments to tutor response
        if '_motivation_content_adjustments' in st.session_state:
            adjustments = st.session_state['_motivation_content_adjustments']
            tutor_message_content = apply_motivation_to_tutor_content(tutor_message_content, adjustments)
        
        tutor_message = {
            "role": "tutor",
            "content": tutor_message_content,
            "timestamp": datetime.now().isoformat(),
            "is_correct": result.get('is_correct', False),
            "scaffolding_level": result.get('scaffolding_level', 'medium'),
            "motivation_applied": orchestrator_result is not None
        }
        
        st.session_state.tutor_messages.append(tutor_message)
        
        # Check completion
        if result.get('session_complete', False):
            st.session_state.tutor_active = False
            st.balloons()
            st.success("🎉 Tutoring session completed!")
        
        print(f"DEBUG: ✅ Background motivation tutor response complete")
        st.rerun()
        
    except Exception as e:
        print(f"ERROR: Background motivation tutor response failed: {e}")
        st.error(f"Processing failed: {str(e)}")

def apply_motivation_to_tutor_content(content: str, adjustments: Dict[str, Any]) -> str:
    """Apply motivation adjustments APPROPRIATELY based on performance"""
    
    tone = adjustments.get('tone', 'neutral')
    
    # Only add positive phrases if actually performing well
    performance_score = adjustments.get('performance_score', 0.5)
    
    # Don't add false praise for poor performance
    if performance_score < 0.5:
        # For struggling students, be supportive without false praise
        if tone == "supportive_and_encouraging":
            content = f"Let me help you understand this better. {content}"
        return content
    
    # Original positive reinforcement only for good performance
    if tone == "process_focused" and performance_score > 0.7:
        content = f"Great effort on your thinking process! {content}"
    
    return content
    

# ANALYTICS AND SIMULATION FUNCTIONS
def get_motivation_analytics_summary() -> Dict[str, Any]:
    """Get summary of motivation analytics for simulation"""
    if "_motivation_analytics" not in st.session_state:
        return {"status": "no_data"}
    
    analytics = st.session_state["_motivation_analytics"]
    motivation_metrics = analytics.get('motivation_metrics')
    
    return {
        "status": "active",
        "current_state": analytics.get('motivation_state', 'unknown'),
        "session_duration": time.time() - analytics.get('timestamp', time.time()),
        "persistence_level": motivation_metrics.persistence_level if motivation_metrics else 'unknown',
        "affective_score": motivation_metrics.affective_score if motivation_metrics else 0.0,
        "performance_score": motivation_metrics.performance_score if motivation_metrics else 0.0,
        "current_strategy": analytics.get('motivation_feedback', {}).get('strategy', 'unknown'),
        "interventions_applied": len(analytics.get('motivation_feedback', {}).get('system_adjustments', {}))
    }

def simulate_motivation_state_change(target_state: str):
    """Simulate motivation state change for testing"""
    if "_motivation_analytics" not in st.session_state:
        st.session_state["_motivation_analytics"] = {}
    
    st.session_state["_motivation_analytics"]['motivation_state'] = target_state
    st.session_state["_motivation_analytics"]['timestamp'] = time.time()
    
    print(f"DEBUG: 🧪 Simulated motivation state change to: {target_state}")


def debug_progress_integration():
    """Debug function to test progress integration"""
    username = st.session_state.get("username", "test_user")
    course = st.session_state.get("selected_course", "DEMO101")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔧 Debug Tools")
    
    if st.sidebar.button("🔍 Check Progress Integration"):
        with st.sidebar.expander("Progress Debug Info", expanded=True):
            try:
                # Check components
                auth_service = get_auth_service()
                mastery_tracker = get_mastery_tracker() 
                progress_bridge = get_progress_bridge()
                
                st.write("**Component Status:**")
                st.write(f"• AuthService: {'✅' if auth_service else '❌'}")
                st.write(f"• MasteryTracker: {'✅' if mastery_tracker else '❌'}")
                st.write(f"• ProgressBridge: {'✅' if progress_bridge else '❌'}")
                
                if progress_bridge:
                    # Test progress summary
                    summary = progress_bridge.get_progress_summary(username, course)
                    
                    st.write("**Current Progress:**")
                    st.json({
                        "current_week": summary.get("current_week"),
                        "week_completion": f"{summary.get('week_completion', 0)*100:.1f}%",
                        "overall_progress": f"{summary.get('overall_course_progress', 0)*100:.1f}%",
                        "total_interactions": summary.get("total_interactions"),
                        "ready_for_next": summary.get("ready_for_next_week")
                    })
                    
                    # Check Redis directly
                    if auth_service:
                        redis_progress = auth_service.redis_client.get_user_progress(username)
                        st.write("**Redis Progress Data:**")
                        st.json(redis_progress)
                        
                        # Check mastery data
                        mastery_data = mastery_tracker.get_mastery_summary(username, course)
                        st.write("**Mastery Summary:**")
                        st.json({
                            "go_count": len(mastery_data.get("go_masteries", {})),
                            "week_masteries": mastery_data.get("week_masteries", {}),
                            "total_interactions": mastery_data.get("total_interactions", 0)
                        })
                
            except Exception as e:
                st.error(f"Debug failed: {e}")
    
    if st.sidebar.button("🧪 Test Progress Update"):
        with st.sidebar.expander("Test Results", expanded=True):
            try:
                progress_bridge = get_progress_bridge()
                if progress_bridge:
                    # Simulate a quiz completion
                    test_context = {
                        'go_data': {
                            'go_id': f"GO_{st.session_state.selected_week:02d}_TEST_01",
                            'skill_name': "Test Skill"
                        },
                        'is_quiz': True,
                        'correct': True,
                        'score': 0.9,
                        'username': username
                    }
                    
                    result = progress_bridge.update_progress_from_mastery(
                        username, course, st.session_state.selected_week, test_context
                    )
                    
                    if result.get("progress_updated"):
                        st.success("✅ Progress update test successful!")
                        st.json(result)
                    else:
                        st.warning("⚠️ No progress update occurred")
                        st.json(result)
                else:
                    st.error("❌ Progress bridge not available")
                    
            except Exception as e:
                st.error(f"Test failed: {e}")

def debug_mastery_vs_progress():
    """Compare mastery data with progress data"""
    if st.sidebar.button("📊 Compare Mastery vs Progress"):
        username = st.session_state.get("username")
        course = st.session_state.get("selected_course")
        
        with st.sidebar.expander("Comparison Report", expanded=True):
            try:
                # Get mastery data
                mastery_tracker = get_mastery_tracker()
                mastery_data = mastery_tracker.get_mastery_summary(username, course)
                
                # Get progress data
                auth_service = get_auth_service()
                progress_data = auth_service.redis_client.get_user_progress(username)
                course_progress = progress_data.get(course, {})
                
                st.write("**Mastery System:**")
                st.write(f"• Total interactions: {mastery_data.get('total_interactions', 0)}")
                st.write(f"• GOs tracked: {len(mastery_data.get('go_masteries', {}))}")
                st.write(f"• Weeks with data: {list(mastery_data.get('week_masteries', {}).keys())}")
                
                st.write("**Progress System:**")
                st.write(f"• Current week: {course_progress.get('week', 'N/A')}")
                st.write(f"• Completion: {course_progress.get('completion', 0)*100:.1f}%")
                st.write(f"• Last updated: {course_progress.get('last_updated', 'Never')}")
                
                # Identify disconnection
                mastery_interactions = mastery_data.get('total_interactions', 0)
                progress_updated = course_progress.get('last_updated', 'Never')
                
                if mastery_interactions > 0 and progress_updated == 'Never':
                    st.error("🚨 DISCONNECTION DETECTED!")
                    st.write("Mastery is updating but progress is not.")
                elif mastery_interactions > 0:
                    st.success("✅ Both systems have data")
                else:
                    st.info("ℹ️ No learning activity detected yet")
                    
            except Exception as e:
                st.error(f"Comparison failed: {e}")

def render_debug_page():
    """EMERGENCY: Debug page to diagnose and fix progress integration issues"""
    
    st.title("🔧 LEA Debug & Repair Center")
    st.markdown("---")
    
    if not st.session_state.authenticated:
        st.error("Please log in first to access debug tools")
        return
    
    username = st.session_state.username
    course = st.session_state.selected_course
    
    st.info(f"🔍 Debugging for: **{username}** in **{course}**")
    
    # Tab-based debug interface
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Data Inspection", "🔧 Repair Tools", "🧪 Test Functions", "📋 Raw Data"])
    
    with tab1:
        st.header("📊 Data Inspection")
        
        if st.button("🔍 Full Data Inspection", type="primary"):
            inspect_user_data_streamlit(username, course)
    
    with tab2:
        st.header("🔧 Repair Tools")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔧 Repair Progress Integration", type="primary"):
                repair_progress_integration_streamlit(username, course)
        
        with col2:
            if st.button("🧪 Test Progress Update", type="secondary"):
                test_progress_update_streamlit(username, course)
        
        st.markdown("---")
        
        # Manual progress adjustment
        st.subheader("⚙️ Manual Progress Adjustment")
        
        with st.form("manual_progress_form"):
            new_completion = st.slider("Set Completion %", 0, 100, 0) / 100.0
            new_week = st.number_input("Set Week", min_value=1, max_value=12, value=1)
            
            if st.form_submit_button("🔧 Apply Manual Update"):
                manual_progress_update(username, course, new_week, new_completion)
    
    with tab3:
        st.header("🧪 Test Functions")
        
        if st.button("🧪 Test Mastery Tracker"):
            test_mastery_tracker_streamlit(username, course)
        
        if st.button("🧪 Test Progress Bridge"):
            test_progress_bridge_streamlit(username, course)
        
        if st.button("🧪 Simulate Quiz Completion"):
            simulate_quiz_completion_streamlit(username, course)
    
    with tab4:
        st.header("📋 Raw Data View")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📊 Show Progress Data"):
                show_raw_progress_data(username, course)
        
        with col2:
            if st.button("📊 Show Mastery Data"):
                show_raw_mastery_data(username, course)

def inspect_user_data_streamlit(username: str, course: str):
    """Streamlit version of comprehensive user data inspection"""
    
    st.subheader(f"🔍 Inspecting: {username} -> {course}")
    
    try:
        auth_service = get_auth_service()
        if not auth_service:
            st.error("❌ Auth service not available")
            return
        
        # 1. User Account Check
        st.markdown("### 1️⃣ User Account")
        try:
            user_data = auth_service.get_user_data(username)
            st.success("✅ User account exists")
            
            with st.expander("User Details"):
                st.json({
                    "username": username,
                    "enrolled_courses": user_data.get("enrolled_courses", []),
                    "progress": user_data.get("progress", {})
                })
                
        except Exception as e:
            st.error(f"❌ User account error: {e}")
        
        # 2. Progress Data Check
        st.markdown("### 2️⃣ Progress Data")
        try:
            progress_data = auth_service.redis_client.get_user_progress(username)
            course_progress = progress_data.get(course, {})
            
            if course_progress:
                st.success("✅ Progress data exists")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Week", course_progress.get("week", "N/A"))
                with col2:
                    completion = course_progress.get("completion", 0.0)
                    st.metric("Completion", f"{completion*100:.1f}%")
                with col3:
                    last_updated = course_progress.get("last_updated", "Never")
                    st.metric("Last Updated", "Recent" if "2025" in str(last_updated) else "Old")
                
                # Check for issues
                if completion == 0.0 and last_updated != "Never":
                    st.error("🚨 ISSUE: Zero completion despite updates!")
                
            else:
                st.error("❌ No progress data found")
                
        except Exception as e:
            st.error(f"❌ Progress data error: {e}")
        
        # 3. Mastery Data Check
        st.markdown("### 3️⃣ Mastery Data")
        try:
            mastery_tracker = get_mastery_tracker()
            if mastery_tracker:
                mastery_data = mastery_tracker.get_mastery_summary(username, course)
                
                if mastery_data and mastery_data.get("total_interactions", 0) > 0:
                    st.success("✅ Mastery data exists")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Interactions", mastery_data.get("total_interactions", 0))
                    with col2:
                        go_count = len(mastery_data.get("go_masteries", {}))
                        st.metric("GOs Tracked", go_count)
                    with col3:
                        week_count = len(mastery_data.get("week_masteries", {}))
                        st.metric("Weeks", week_count)
                    
                    # Show GO details
                    go_masteries = mastery_data.get("go_masteries", {})
                    if go_masteries:
                        with st.expander(f"GO Mastery Details ({len(go_masteries)} total)"):
                            for go_id, mastery_level in list(go_masteries.items())[:10]:
                                progress_bar_value = mastery_level if isinstance(mastery_level, float) else mastery_level.get("level", 0.0)
                                st.progress(progress_bar_value, text=f"{go_id}: {progress_bar_value:.2f}")
                    
                    # CRITICAL CHECK: Mastery vs Progress Disconnection
                    mastery_interactions = mastery_data.get("total_interactions", 0)
                    progress_completion = course_progress.get("completion", 0.0)
                    
                    if mastery_interactions > 0 and progress_completion == 0.0:
                        st.error("🚨 CRITICAL ISSUE DETECTED!")
                        st.error(f"Mastery system shows {mastery_interactions} interactions but progress is 0%")
                        st.error("This confirms the progress integration bug!")
                        
                        if st.button("🔧 Auto-Repair This Issue", type="primary"):
                            repair_progress_integration_streamlit(username, course)
                else:
                    st.warning("⚠️ No mastery data found")
            else:
                st.error("❌ Mastery tracker not available")
                
        except Exception as e:
            st.error(f"❌ Mastery data error: {e}")
            
    except Exception as e:
        st.error(f"❌ Inspection failed: {e}")

def repair_progress_integration_streamlit(username: str, course: str):
    """Streamlit version of progress integration repair"""
    
    st.subheader(f"🔧 Repairing Progress Integration: {username} -> {course}")
    
    try:
        progress_bridge = get_progress_bridge()
        mastery_tracker = get_mastery_tracker()
        auth_service = get_auth_service()
        
        if not all([progress_bridge, mastery_tracker, auth_service]):
            st.error("❌ Required services not available")
            return
        
        # Step 1: Get current state
        st.write("**Step 1: Analyzing current state...**")
        
        mastery_data = mastery_tracker.get_mastery_summary(username, course)
        progress_data = auth_service.redis_client.get_user_progress(username)
        
        mastery_interactions = mastery_data.get("total_interactions", 0)
        current_progress = progress_data.get(course, {}).get("completion", 0.0)
        
        st.info(f"Mastery interactions: {mastery_interactions}, Current progress: {current_progress*100:.1f}%")
        
        if mastery_interactions == 0:
            st.warning("⚠️ No mastery data to repair from. Complete some learning activities first.")
            return
        
        # Step 2: Calculate what progress should be
        st.write("**Step 2: Calculating correct progress...**")
        
        go_masteries = mastery_data.get("go_masteries", {})
        week_1_gos = []
        
        # Find Week 1 GOs using multiple patterns
        for go_id, mastery_info in go_masteries.items():
            if any(pattern in go_id for pattern in ["_01_", "GO_01", "W1_", "WEEK_1"]):
                mastery_level = mastery_info.get("level", 0.0) if isinstance(mastery_info, dict) else float(mastery_info)
                week_1_gos.append((go_id, mastery_level))
        
        if not week_1_gos:
            # Fallback: use first few GOs
            for go_id, mastery_info in list(go_masteries.items())[:5]:
                mastery_level = mastery_info.get("level", 0.0) if isinstance(mastery_info, dict) else float(mastery_info)
                week_1_gos.append((go_id, mastery_level))
        
        st.write(f"Found {len(week_1_gos)} GOs for Week 1:")
        for go_id, mastery_level in week_1_gos:
            st.write(f"  • {go_id}: {mastery_level:.3f}")
        
        # Calculate completion
        completed_gos = len([go for go_id, mastery in week_1_gos if mastery >= 0.8])
        total_gos = len(week_1_gos)
        
        if total_gos > 0:
            calculated_completion = completed_gos / total_gos
            st.success(f"Calculated completion: {completed_gos}/{total_gos} = {calculated_completion*100:.1f}%")
            
            # Step 3: Apply repair
            st.write("**Step 3: Applying repair...**")
            
            try:
                auth_service.redis_client.update_user_progress(
                    username=username,
                    course=course,
                    week=1,
                    completion=calculated_completion
                )
                
                # Verify repair
                updated_progress = auth_service.redis_client.get_user_progress(username)
                new_completion = updated_progress.get(course, {}).get("completion", 0.0)
                
                if abs(new_completion - calculated_completion) < 0.001:
                    st.success(f"✅ REPAIR SUCCESSFUL!")
                    st.success(f"Progress updated from {current_progress*100:.1f}% to {new_completion*100:.1f}%")
                    
                    # Force UI refresh
                    trigger_mastery_refresh()
                    st.balloons()
                    
                    # Show before/after
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Before Repair", f"{current_progress*100:.1f}%")
                    with col2:
                        st.metric("After Repair", f"{new_completion*100:.1f}%")
                else:
                    st.error(f"❌ Repair verification failed")
                    st.error(f"Expected: {calculated_completion:.3f}, Got: {new_completion:.3f}")
                    
            except Exception as e:
                st.error(f"❌ Repair failed: {e}")
        else:
            st.warning("⚠️ No GOs found to calculate progress from")
            
    except Exception as e:
        st.error(f"❌ Repair process failed: {e}")
        import traceback
        st.code(traceback.format_exc())

def test_progress_update_streamlit(username: str, course: str):
    """Test the progress update method in Streamlit"""
    
    st.subheader(f"🧪 Testing Progress Update: {username} -> {course}")
    
    try:
        auth_service = get_auth_service()
        if not auth_service:
            st.error("❌ Auth service not available")
            return
        
        # Get initial state
        initial_progress = auth_service.redis_client.get_user_progress(username)
        initial_completion = initial_progress.get(course, {}).get("completion", 0.0)
        
        st.info(f"Initial completion: {initial_completion*100:.1f}%")
        
        # Test increment
        test_increment = 0.05  # 5% increment
        st.write(f"**Testing increment of {test_increment*100:.1f}%...**")
        
        try:
            auth_service.redis_client.update_user_progress(
                username=username,
                course=course,
                week=1,
                increment_completion=test_increment
            )
            
            # Verify
            updated_progress = auth_service.redis_client.get_user_progress(username)
            new_completion = updated_progress.get(course, {}).get("completion", 0.0)
            actual_change = new_completion - initial_completion
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Expected Change", f"{test_increment*100:.1f}%")
            with col2:
                st.metric("Actual Change", f"{actual_change*100:.1f}%")
            with col3:
                st.metric("New Total", f"{new_completion*100:.1f}%")
            
            if abs(actual_change - test_increment) < 0.001:
                st.success("✅ Progress update method WORKS correctly!")
                
                # Force UI refresh
                trigger_mastery_refresh()
            else:
                st.error("❌ Progress update method FAILED!")
                st.error("This indicates a bug in the update_user_progress method")
                
        except Exception as e:
            st.error(f"❌ Update test failed: {e}")
            
    except Exception as e:
        st.error(f"❌ Test failed: {e}")

def simulate_quiz_completion_streamlit(username: str, course: str):
    """Simulate a quiz completion to test the full integration"""
    
    st.subheader(f"🧪 Simulating Quiz Completion: {username} -> {course}")
    
    try:
        # Create realistic test data
        mock_quiz_result = {
            "correct": True,
            "score": 1.0,
            "explanation": "Test question simulation"
        }
        
        mock_answer = "Test Answer"
        
        st.write("**Simulating quiz completion with enhanced integration...**")
        
        # Call the actual function
        result = update_mastery_after_quiz_answer(username, mock_answer, mock_quiz_result)
        
        if result:
            st.success("✅ Quiz completion simulation SUCCESSFUL!")
            st.success("The enhanced integration is working!")
            
            # Show updated progress
            auth_service = get_auth_service()
            if auth_service:
                updated_progress = auth_service.redis_client.get_user_progress(username)
                new_completion = updated_progress.get(course, {}).get("completion", 0.0)
                st.metric("Updated Progress", f"{new_completion*100:.1f}%")
        else:
            st.error("❌ Quiz completion simulation FAILED!")
            st.error("This indicates the integration is still broken")
            
    except Exception as e:
        st.error(f"❌ Simulation failed: {e}")
        import traceback
        st.code(traceback.format_exc())

def manual_progress_update(username: str, course: str, week: int, completion: float):
    """Manual progress update override"""
    
    try:
        auth_service = get_auth_service()
        if not auth_service:
            st.error("❌ Auth service not available")
            return
        
        auth_service.redis_client.update_user_progress(
            username=username,
            course=course,
            week=week,
            completion=completion
        )
        
        st.success(f"✅ Manual update applied!")
        st.success(f"Set {course} to Week {week}, {completion*100:.1f}% completion")
        
        trigger_mastery_refresh()
        
    except Exception as e:
        st.error(f"❌ Manual update failed: {e}")

def show_raw_progress_data(username: str, course: str):
    """Show raw progress data from Redis"""
    
    try:
        auth_service = get_auth_service()
        if not auth_service:
            st.error("❌ Auth service not available")
            return
        
        progress_data = auth_service.redis_client.get_user_progress(username)
        st.json(progress_data)
        
    except Exception as e:
        st.error(f"❌ Failed to get progress data: {e}")

def show_raw_mastery_data(username: str, course: str):
    """Show raw mastery data"""
    
    try:
        mastery_tracker = get_mastery_tracker()
        if not mastery_tracker:
            st.error("❌ Mastery tracker not available")
            return
        
        mastery_data = mastery_tracker.get_mastery_summary(username, course)
        st.json(mastery_data)
        
    except Exception as e:
        st.error(f"❌ Failed to get mastery data: {e}")

def test_mastery_tracker_streamlit(username: str, course: str):
    """Test mastery tracker functionality"""
    
    try:
        mastery_tracker = get_mastery_tracker()
        if not mastery_tracker:
            st.error("❌ Mastery tracker not available")
            return
        
        # Test getting data
        mastery_data = mastery_tracker.get_mastery_summary(username, course)
        
        if mastery_data:
            st.success("✅ Mastery tracker working")
            st.metric("Total Interactions", mastery_data.get("total_interactions", 0))
            st.metric("GOs Tracked", len(mastery_data.get("go_masteries", {})))
        else:
            st.warning("⚠️ No mastery data found")
            
    except Exception as e:
        st.error(f"❌ Mastery tracker test failed: {e}")

def test_progress_bridge_streamlit(username: str, course: str):
    """Test progress bridge functionality"""
    
    try:
        progress_bridge = get_progress_bridge()
        if not progress_bridge:
            st.error("❌ Progress bridge not available")
            return
        
        # Test getting summary
        summary = progress_bridge.get_progress_summary(username, course)
        
        if summary and not summary.get("error"):
            st.success("✅ Progress bridge working")
            st.json(summary)
        else:
            st.error(f"❌ Progress bridge error: {summary.get('error', 'Unknown')}")
            
    except Exception as e:
        st.error(f"❌ Progress bridge test failed: {e}")

# ADD THIS TO YOUR MAIN FUNCTION IN streamlit_app_optimized.py
# Add a debug mode check to your sidebar or create a new page

def add_debug_mode_to_sidebar():
    """Add debug mode toggle to sidebar"""
    
    with st.sidebar:
        st.markdown("---")
        
        # Debug mode toggle
        debug_mode = st.checkbox("🔧 Debug Mode", value=False, key="debug_mode_toggle")
        
        if debug_mode:
            if st.button("🔧 Open Debug Center", use_container_width=True, type="secondary"):
                st.session_state.show_debug_page = True
                st.rerun()

def display_background_motivation_metrics():
    """Display motivation metrics for admin/debug purposes only"""
    if "_motivation_analytics" in st.session_state:
        with st.expander("🔬 Background Motivation Analytics (Debug)", expanded=False):
            analytics = st.session_state["_motivation_analytics"]
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("State", analytics.get('motivation_state', 'unknown'))
            with col2:
                duration = time.time() - analytics.get('timestamp', time.time())
                st.metric("Duration", f"{duration:.0f}s")
            
            motivation_metrics = analytics.get('motivation_metrics')
            if motivation_metrics:
                st.caption(f"Persistence: {motivation_metrics.persistence_level}")
                st.caption(f"Affective: {motivation_metrics.affective_score:.2f}")
                st.caption(f"Performance: {motivation_metrics.performance_score:.2f}")
            
            if st.button("📊 Export Motivation Logs", key="export_motivation"):
                export_motivation_logs()

def export_motivation_logs():
    """Export motivation logs for analysis"""
    try:
        log_dir = Path("./data/motivation_logs")
        if log_dir.exists():
            log_files = list(log_dir.glob("motivation_metrics_*.csv"))
            if log_files:
                latest_log = max(log_files, key=lambda f: f.stat().st_mtime)
                st.success(f"Latest log: {latest_log.name}")
                
                # Show sample of data
                with open(latest_log, 'r') as f:
                    sample_lines = f.readlines()[:10]
                    st.code("".join(sample_lines))
            else:
                st.info("No motivation logs found")
        else:
            st.info("Motivation logs directory not found")
    except Exception as e:
        st.error(f"Export failed: {e}")

def render_sidebar():
    """Enhanced sidebar WITHOUT motivation display (background only)"""
    with st.sidebar:
        st.markdown("### 🧭 Command Center")
        
        auth_service = get_auth_service()
        kc_loader = get_kc_loader()
        quiz_system = get_quiz_system()
        
        if not all([auth_service, kc_loader, quiz_system]):
            st.error("⚠️ Some services not available")
            return
                
        # Course selection (existing code)
        if st.session_state.enrolled_courses:
            selected_course = st.selectbox(
                "Course:",
                st.session_state.enrolled_courses,
                index=st.session_state.enrolled_courses.index(st.session_state.selected_course) 
                    if st.session_state.selected_course in st.session_state.enrolled_courses else 0
            )
            
            if selected_course != st.session_state.selected_course:
                handle_course_change(selected_course)
        
        # Week selection (existing code)
        if st.session_state.course_weeks:
            week_options = list(st.session_state.course_weeks.keys())
            selected_week_display = st.selectbox("Week:", week_options)
            
            new_week = st.session_state.course_weeks[selected_week_display]["week_number"]
            if new_week != st.session_state.selected_week:
                st.session_state.selected_week = new_week
                st.session_state.quiz_active = False
                st.session_state.quiz_completed = False
                st.rerun()
                
        st.markdown("---")

        # Mode Navigation (existing code)
        st.markdown("### ✨ Learning Modes")
        
        mode_configs = {
            AppMode.CHAT: {
                "label": "💬 Chat Mode",
                "description": "Ask questions",
                "status": get_chat_status()
            },
            AppMode.TUTOR: { 
                "label": "🎓 Tutor Mode",
                "description": "Guided learning",
                "status": get_tutor_status()
            },
            AppMode.QUIZ: {
                "label": "⭐ Quiz Mode",
                "description": "Test knowledge",
                "status": get_quiz_status()
            }
        }
        current_mode_str = get_current_mode_string()
        
        for mode, config in mode_configs.items():
            is_current = (current_mode_str == mode.value)
            button_type = "primary" if is_current else "secondary"
            
            status_emoji = config["status"]["emoji"]
            status_text = config["status"]["text"]
            
            col1, col2 = st.columns([3, 1])
            with col1:
                if st.button(
                    f"{config['label']}", 
                    use_container_width=True,
                    type=button_type,
                    disabled=is_current,
                    key=f"mode_btn_{mode.value}"
                ):
                    switch_mode(mode)
            with col2:
                st.markdown(f"{status_emoji}")
            
            if is_current:
                st.caption(f"✨ {config['description']}")
            else:
                st.caption(f"{config['description']} {status_text}")
                
        
        # Logout button
        st.markdown("---")
        if st.button("Logout", use_container_width=True, key="logout_btn"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
            
def render_chat_sidebar_controls():
    """Chat-specific sidebar controls"""
    st.markdown("### 💬 Chat Controls")
    
    username = st.session_state.get("username", "user")
    conversation = get_conversation_history_safe(username)
    
    if conversation:
        total_messages = len(conversation)
        user_messages = len([m for m in conversation if m.get("role") == "user"])
        st.markdown(f"**Messages:** {total_messages} | **Questions:** {user_messages}")
    else:
        st.markdown("**Status:** Ready!")
    
    if st.session_state.selected_course:
        st.markdown(f"**Context:** {st.session_state.selected_course} W{st.session_state.selected_week}")
    
    if conversation:
        if st.button("🗑️ Clear Chat", use_container_width=True, key=f"clear_chat_btn_{username}"):
            clear_chat_history()
    
    with st.expander("💡 Tips", expanded=False):
        st.markdown("""
        **Ask about:** Course concepts, week materials, study questions
        
        **LEA helps with:** Course content search, context-aware answers, general knowledge
        """, unsafe_allow_html=True)

def render_quiz_sidebar_controls():
    """Quiz-specific sidebar controls with enhanced analytics"""
    st.markdown("### 📊 Quiz Info")
    
    # Always show learning analytics during quiz (expanded by default)
    display_cognitive_load_in_sidebar()
    
    if st.session_state.course_weeks and not st.session_state.quiz_active:
        for week_display, week_data in st.session_state.course_weeks.items():
            if week_data["week_number"] == st.session_state.selected_week:
                st.markdown(f"**Questions:** {week_data.get('total_questions', '?')}")
                st.markdown(f"**Topics:** {len(week_data.get('learning_objectives', []))}")
                break
    
    if st.session_state.quiz_active and not st.session_state.quiz_completed:
        progress = st.session_state.quiz_progress
        st.markdown("### 📈 Quiz Progress")
        
        # Current question info
        st.markdown(f"**Question:** {progress['current']}/{progress['total']}")
        st.markdown(f"**Correct So Far:** {progress['correct']}")
        
        # Calculate and show current accuracy
        if progress['current'] > 1:
            accuracy = (progress['correct'] / (progress['current']-1) * 100)
            st.markdown(f"**Current Accuracy:** {accuracy:.0f}%")
        
        # Progress bar
        if progress['total'] > 0:
            progress_pct = (progress['current'] - 1) / progress['total']
            st.progress(progress_pct)
            st.caption(f"{progress_pct*100:.0f}% Complete")
        
        # Question type info
        if st.session_state.current_quiz_data:
            current_question = st.session_state.current_quiz_data.get("current_question", {})
            question_type = current_question.get("type", "unknown")
            type_emoji = {
                "multiple_choice": "🔘",
                "true_false": "✅❌", 
                "fill_in_blank": "📝",
                "open_ended": "💭"
            }
            st.caption(f"{type_emoji.get(question_type, '❓')} {question_type.replace('_', ' ').title()}")

    if st.session_state.quiz_completed:
        total = len(st.session_state.quiz_results)
        correct = sum(1 for r in st.session_state.quiz_results if r.get("correct", False))
        st.markdown("### 🏆 Final Results") 
        
        if total > 0:
            accuracy = (correct/total*100)
            st.metric("Final Score", f"{correct}/{total}")
            st.metric("Final Accuracy", f"{accuracy:.0f}%")
            
            # Performance summary
            if accuracy >= 90:
                st.success("🌟 Outstanding!")
            elif accuracy >= 75:
                st.success("🎯 Great job!")
            elif accuracy >= 60:
                st.info("👍 Good effort!")
            else:
                st.info("📚 Keep practicing!")
        else:
            st.markdown("**Score:** 0/0 (0%)")

def render_tutor_sidebar_controls():
    """Tutor-specific sidebar controls"""
    st.markdown("### 🎓 Tutor Controls")
    
    if st.session_state.tutor_session:
        session = st.session_state.tutor_session
        progress = (session.current_go_index / len(session.go_list)) * 100
        current_go = session.go_list[session.current_go_index]['skill_name']
        
        st.markdown(f"**Progress:** {progress:.0f}%")
        st.markdown(f"**Current Topic:** {current_go}")
        st.markdown(f"**Scaffolding:** {session.scaffolding_level.title()}")
        
        accuracy = session.correct_count / max(session.interaction_count, 1)
        st.markdown(f"**Accuracy:** {accuracy:.0f}%")
        
        st.progress(progress / 100)
    
    if not st.session_state.tutor_active:
        if st.button("🎓 Start Tutoring", use_container_width=True, type="primary"):
            start_tutor_session()
    else:
        if st.button("❌ End Session", use_container_width=True):
            end_tutor_session()
    
    if st.session_state.tutor_active:
        with st.expander("💡 Scaffolding Info", expanded=False):
            current_level = st.session_state.tutor_session.scaffolding_level if st.session_state.tutor_session else "medium"
            st.markdown(f"""
            **Current Level:** {current_level.title()}
            
            **High:** Detailed explanations and hints
            **Medium:** Guided questions and support  
            **Low:** Open exploration and minimal help
            
            *Level adjusts automatically based on your performance!*
            """)

def render_main_content():
    """Main content rendering"""

    # Check if debug page should be shown
    if st.session_state.get("show_debug_page", False):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("⬅️ Back to Learning", use_container_width=True):
                st.session_state.show_debug_page = False
                st.rerun()
        
        render_debug_page()
        return
        
    
    mode_titles = {
        "chat": "💬 Chat with LEA", 
        "tutor": "📝 Flex Your Smarts",
        "quiz": "⭐ Quiz It Like You Mean It"
    }
    
    try:
        current_mode_value = get_current_mode_string()
        title = mode_titles.get(current_mode_value, "🌀 Learning Mode")
        st.markdown(f"# {title}")
        st.markdown(f"**{st.session_state.selected_course} - Week {st.session_state.selected_week}**")
        
    except Exception as e:
        st.error(f"Mode display error: {e}")
        st.markdown("Learning Mode")
    
    current_mode_str = get_current_mode_string()
    
    if current_mode_str == "chat":
        render_chat_interface()
    elif current_mode_str == "tutor":
        render_tutor_interface()
    elif current_mode_str == "quiz":
        render_quiz_interface()
    else:
        st.error(f"Unknown mode: {st.session_state.current_mode}")
        st.session_state.current_mode = AppMode.CHAT
        st.rerun()

def render_chat_interface():
    """Chat interface with custom avatars"""
    
    username = st.session_state.get("username", "user")
    conversation = get_conversation_history_safe(username, 50)
    
    # Get custom avatars
    student_initial = username[0] if username else "U"
    student_avatar = create_student_avatar(student_initial)
    lea_avatar = get_lea_avatar()
    
    if not conversation:
        st.chat_message("assistant", avatar=lea_avatar).write(
            f"Hey, I'm LEA 👋 Got questions on {st.session_state.selected_course} Week {st.session_state.selected_week}? I'm here to help!"
        )
    else:
        for msg in conversation:
            if msg["role"] == "user":
                st.chat_message("user", avatar=student_avatar).write(msg["message"])
            else:
                st.chat_message("assistant", avatar=lea_avatar).write(msg["message"])
    
    user_input = st.chat_input("Ask me anything about your course!")
    
    if user_input and user_input.strip():
        send_chat_message_with_orchestrator(user_input.strip())


def render_tutor_interface():
    """Tutor interface WITHOUT motivation display (background tracking only)"""
    
    st.markdown("---")
    
    if not st.session_state.tutor_active:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🎓 Start Tutoring Session", use_container_width=True, type="primary", key="main_start_tutor"):
                start_tutor_session_with_background_motivation()
                return
        
        render_tutor_week_info()
        return
    
    else:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("❌ End Tutoring Session", use_container_width=True, key="main_end_tutor"):
                end_tutor_session()
                return
    
    render_tutor_conversation()
    render_tutor_input_with_background_motivation()
    
def render_tutor_conversation():
    """Render tutor conversation area with custom avatars"""
    
    username = st.session_state.get("username", "user")
    student_initial = username[0] if username else "U"
    student_avatar = create_student_avatar(student_initial)
    lea_avatar = get_lea_avatar()
    
    if st.session_state.tutor_session:
        session = st.session_state.tutor_session
        current_go = session.go_list[session.current_go_index]['skill_name']
        progress = (session.current_go_index / len(session.go_list)) * 100
        
        st.markdown(f"""
        <div class="quiz-progress">
            Learning: {current_go} | Progress: {progress:.0f}% | 
            Scaffolding: {session.scaffolding_level.title()} Support
        </div>
        """, unsafe_allow_html=True)
    
    messages_displayed = False
    
    if st.session_state.tutor_messages:
        for message in st.session_state.tutor_messages:
            if message["role"] == "student":
                st.chat_message("user", avatar=student_avatar).write(message["content"])
            else:
                st.chat_message("assistant", avatar=lea_avatar).write(message["content"])
        messages_displayed = True
    
    elif st.session_state.tutor_session and st.session_state.tutor_session.conversation_history:
        for msg in st.session_state.tutor_session.conversation_history:
            if msg["role"] == "student":
                st.chat_message("user", avatar=student_avatar).write(msg["content"])
            else:
                st.chat_message("assistant", avatar=lea_avatar).write(msg["content"])
        messages_displayed = True
    
    if not messages_displayed:
        st.chat_message("assistant", avatar=lea_avatar).write("Hi! I'm ready to help you learn. Let's get started!")
        
        if st.session_state.tutor_session:
            fallback_msg = {
                "role": "tutor",
                "content": "Hi! I'm ready to help you learn. Let's get started!",
                "timestamp": datetime.now().isoformat()
            }
            st.session_state.tutor_messages.append(fallback_msg)
            

def start_tutor_session_with_background_motivation():
    """Start tutor session with background motivation tracking"""
    tutor_system = get_tutor_system()
    kc_loader = get_current_kc_loader()
    orchestrator = get_orchestrator()
    
    if not tutor_system or not kc_loader:
        st.error("Tutor system not available. Please check OpenAI API key.")
        return
    
    if not st.session_state.selected_course or not st.session_state.selected_week:
        st.error("Please select a course and week first.")
        return
    
    try:
        print(f"DEBUG: Starting tutor session with background motivation tracking")
               
        # Get initial orchestrator context
        initial_orchestrator_context = None
        if orchestrator and hasattr(orchestrator, 'mcp_client'):
            try:
                baseline_context = {
                    'username': st.session_state.username,
                    'course': st.session_state.selected_course,
                    'week': st.session_state.selected_week,
                    'session_start_time': datetime.now(),
                    'tutor_starting': True,
                    'interaction_count': 0
                }
                
                initial_orchestrator_context = process_orchestrator_interaction(
                    orchestrator=orchestrator,
                    interaction_type="tutor",
                    student_input="Starting tutor session",
                    session_context=baseline_context
                )
                
                if initial_orchestrator_context:
                    store_motivation_metrics_background(initial_orchestrator_context)
                    print(f"DEBUG: 🎯 Initial tutor motivation context captured")
                    
            except Exception as e:
                print(f"DEBUG: Initial tutor orchestrator context failed: {e}")
        
        # Get week content and GO list
        week_content = kc_loader.get_week_content(st.session_state.selected_course, st.session_state.selected_week)
        
        go_list = []
        for lo in week_content.learning_objectives:
            for go in lo.granular_objectives:
                go_list.append({
                    "go_id": go.go_id,
                    "skill_name": go.skill_name,
                    "description": go.description,
                    "content_keywords": go.content_keywords
                })
        
        if not go_list:
            st.error("No learning objectives found for this week.")
            return
        
        # Start session with motivation context
        session = tutor_system.start_tutoring_session(
            course=st.session_state.selected_course,
            week=st.session_state.selected_week,
            username=st.session_state.username,
            kc_loader=kc_loader,
            go_list=go_list,
            orchestrator_context=initial_orchestrator_context
        )
        
        if session:
            st.session_state.tutor_session = session
            st.session_state.tutor_active = True
            st.session_state.tutor_messages = []
            
            if session.conversation_history:
                initial_message = session.conversation_history[-1]['content']
                initial_msg = {
                    "role": "tutor",
                    "content": initial_message,
                    "timestamp": datetime.now().isoformat(),
                    "motivation_informed": initial_orchestrator_context is not None
                }
                st.session_state.tutor_messages.append(initial_msg)
            
            st.success(f"Tutoring session started! We'll work through {len(go_list)} concepts together.")
            st.rerun()
        else:
            st.error("Failed to start tutoring session. Please try again.")
            
    except Exception as e:
        print(f"ERROR: Failed to start tutor session with background motivation: {e}")
        st.error(f"Tutor session start failed: {str(e)}")

def render_tutor_input_with_background_motivation():
    """Render tutor input with background motivation tracking"""
    if not st.session_state.tutor_active or not st.session_state.tutor_session:
        return
        
    user_input = st.chat_input("Share your thoughts, ask questions, or work through the problem...")
    
    if user_input and user_input.strip():
        submit_tutor_response_with_background_motivation(user_input.strip())


def render_tutor_input():
    """Render tutor input area"""
    if not st.session_state.tutor_active or not st.session_state.tutor_session:
        return
        
    user_input = st.chat_input("Share your thoughts, ask questions, or work through the problem...")
    
    if user_input and user_input.strip():
        submit_tutor_response(user_input.strip())

def render_tutor_week_info():
    """Render week info when tutor not started"""
    if st.session_state.course_weeks and st.session_state.selected_week:
        for week_display, week_data in st.session_state.course_weeks.items():
            if week_data["week_number"] == st.session_state.selected_week:
                # Get LEA avatar for header
                lea_avatar = get_lea_avatar()
                avatar_b64 = pil_image_to_base64(lea_avatar)
                
                # Custom header with LEA avatar (smaller size for inline use)
                st.markdown(f"""
                ### <img src="{avatar_b64}" style="width: 30px; height: 30px; vertical-align: middle; margin-right: 8px;">Ready to Learn: {week_display}
                """, unsafe_allow_html=True)
                
                st.markdown(f"**Learning Objectives:** {len(week_data.get('learning_objectives', []))}")
                st.markdown(f"**Concepts to Master:** {week_data.get('total_questions', 'Unknown')}")
                
                # st.info("💡 Your AI tutor will adapt to your learning style, providing more or less support based on how you're doing!")
                
                with st.expander("📚 What We'll Cover"):
                    for lo in week_data.get('learning_objectives', []):
                        st.markdown(f"- **{lo['title']}** ({lo['granular_count']} concepts)")
                break
                

def main():
    """Main application entry point"""
    initialize_session_state()
    
    auth_service = get_auth_service()
    kc_loader = get_kc_loader()
    quiz_system = get_quiz_system()
    chat_system = get_chat_system()
    tutor_system = get_tutor_system() 

    # Start memory worker after services are initialized
    if 'memory_worker_started' not in st.session_state:
        if start_memory_worker():
            st.session_state['memory_worker_started'] = True
            print("DEBUG: Memory system active")
    
    if not all([auth_service, kc_loader, quiz_system]):
        st.error("⚠️ System initialization failed. Please check configuration.")
        st.info("Common issues: Missing OpenAI API key, Redis connection problems, or ChromaDB embedding dimension mismatch.")
        st.stop()

    if not st.session_state.authenticated:
        render_login_page()
    else:
        render_sidebar()
        render_main_content()

if __name__ == "__main__":
    main()

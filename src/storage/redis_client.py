# File: src/storage/redis_client.py
"""
Redis Client Module for LEA Tutor - CORRECTED VERSION
This is the extended version with pedagogical features
"""
import os
import sys
import json
import time
import redis
import secrets
import hashlib
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

# Load environment - consistent with existing code
def load_env():
    env_file = Path('.env')
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

# Load environment variables
load_env()

# Import the schemas with proper error handling
try:
    from src.storage.enhanced_redis_schemas import LEAPedagogicalSchemas as EnhancedRedisSchemas
except ImportError:
    print("Warning: Enhanced Redis Schemas not found, using basic schemas")
    class EnhancedRedisSchemas:
        @staticmethod
        def get_cognitive_load_key(username: str, session_id: str = None) -> str:
            if session_id:
                return f"cognitive_load:{username}:{session_id}"
            return f"cognitive_load:{username}:current"
        
        @staticmethod
        def create_cognitive_load_entry() -> Dict[str, Any]:
            return {
                "baseline": {},
                "current": {"load_level": 0.5}
            }

try:
    from src.storage.memory_schemas import MemorySchemas
except ImportError:
    print("Warning: Memory Schemas not found, creating fallback")
    class MemorySchemas:
        @staticmethod
        def get_short_term_key(username: str, session_id: str) -> str:
            return f"memory:short:{username}:{session_id}"
        
        @staticmethod
        def get_long_term_key(username: str, course: str = None) -> str:
            if course:
                return f"memory:long:{username}:{course}"
            return f"memory:long:{username}:general"
        
        @staticmethod
        def get_consolidation_queue_key() -> str:
            return "memory:consolidation:queue"
        
        @staticmethod
        def get_active_session_key(username: str) -> str:
            return f"memory:session:active:{username}"
        
        @staticmethod
        def create_short_term_entry(interaction_type: str, content: Dict[str, Any], metadata: Dict[str, Any] = None) -> Dict[str, Any]:
            return {
                "timestamp": datetime.now().isoformat(),
                "type": interaction_type,
                "content": content,
                "metadata": metadata or {},
                "processed": False
            }
        
        @staticmethod
        def create_consolidation_task(username: str, session_id: str, priority: int = 1) -> Dict[str, Any]:
            return {
                "username": username,
                "session_id": session_id,
                "queued_at": datetime.now().isoformat(),
                "priority": priority,
                "attempts": 0
            }

class LEARedisClient:
    """Enhanced Redis client with full LEA functionality"""
    
    def __init__(self, redis_url=None):
        """Initialize Redis client - consistent with existing code"""
        # Use provided URL or get from environment with default
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        
        self.redis_client = None
        self.schemas = EnhancedRedisSchemas()
        self.memory_schemas = MemorySchemas()
        self.user_management_enabled = True
        self.session_timeout_hours = 8
        
        # Connect to Redis
        self._connect()
        print("DEBUG: Memory schemas initialized")
        

    def _connect(self):
        """Connect to Redis with better error handling"""
        try:
            # Ensure we have a valid URL
            if not self.redis_url:
                self.redis_url = "redis://localhost:6379"
            
            print(f"DEBUG: Attempting to connect to Redis at: {self.redis_url}")
            
            # Create Redis connection
            self.redis_client = redis.Redis.from_url(
                self.redis_url, 
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            
            # Test connection
            self.redis_client.ping()
            print(f"DEBUG: Successfully connected to Redis")
            
        except redis.ConnectionError as e:
            print(f"DEBUG: Redis connection failed (server may be down): {e}")
            print("DEBUG: Please ensure Redis is running with: redis-server")
            self.redis_client = None
        except Exception as e:
            print(f"DEBUG: Redis connection failed: {e}")
            self.redis_client = None
            
    def get_redis(self):
            """Get the Redis connection object"""
            if not self.redis_client:
                # Try to reconnect if connection was lost
                self._connect()
            return self.redis_client
        
    
    # User Authentication Methods   
    def create_user(self, username: str, password: str, full_name: str, 
                   enrolled_courses: List[str] = None) -> Tuple[bool, str]:
        """Create a new user account with course enrollments"""
        try:
            print(f"DEBUG: create_user called with enrolled_courses={enrolled_courses}")
            redis_conn = self.get_redis()
            
            user_key = f"user:{username}"
            if redis_conn.exists(user_key):
                return False, "Username already exists"
            
            salt = secrets.token_hex(32)
            password_hash = self._hash_password(password, salt)
            
            if enrolled_courses is None:
                enrolled_courses = ["CMP511", "PSY555", "CMP202"]
            
            user_data = {
                "username": username,
                "full_name": full_name,
                "password_hash": password_hash,
                "salt": salt,
                "created_at": datetime.now().isoformat(),
                "last_login": "",
                "is_active": "true",
                "enrolled_courses": json.dumps(enrolled_courses)
            }
            
            redis_conn.hset(user_key, mapping=user_data)
            self._initialize_course_progress(username, enrolled_courses)
            
            print(f"DEBUG: User {username} created successfully with courses: {enrolled_courses}")
            return True, "User created successfully"
            
        except Exception as e:
            print(f"DEBUG: User creation error for {username}: {e}")
            return False, f"Registration failed: {str(e)}"
    
    def authenticate_user(self, username: str, password: str) -> Tuple[bool, Optional[str]]:
        """Authenticate user and create session"""
        try:
            redis_conn = self.get_redis()
            user_key = f"user:{username}"
            
            user_data = redis_conn.hgetall(user_key)
            if not user_data:
                print(f"DEBUG: User {username} not found")
                return False, None
            
            if user_data.get("is_active", "true").lower() != "true":
                print(f"DEBUG: User {username} account is inactive")
                return False, None
            
            stored_hash = user_data.get("password_hash")
            salt = user_data.get("salt")
            
            if not stored_hash or not salt:
                print(f"DEBUG: Invalid password data for {username}")
                return False, None
            
            computed_hash = self._hash_password(password, salt)
            
            if computed_hash != stored_hash:
                print(f"DEBUG: Invalid password for {username}")
                return False, None
            
            session_id = self._create_session(username)
            redis_conn.hset(user_key, "last_login", datetime.now().isoformat())
            
            print(f"DEBUG: User {username} authenticated successfully, session: {session_id}")
            return True, session_id
            
        except Exception as e:
            print(f"DEBUG: Authentication error for {username}: {e}")
            return False, None
    
    def _create_session(self, username: str) -> str:
        """Create a session for authenticated user"""
        redis_conn = self.get_redis()
        session_id = secrets.token_hex(32)
        session_key = f"session:{session_id}"
        session_timeout_seconds = self.session_timeout_hours * 3600
        redis_conn.setex(session_key, session_timeout_seconds, username)
        print(f"DEBUG: Created session {session_id} for user {username}")
        return session_id
    
    def validate_session(self, session_id: str) -> Optional[str]:
        """Validate session and return username if valid"""
        if not session_id:
            return None
        
        try:
            redis_conn = self.get_redis()
            session_key = f"session:{session_id}"
            username = redis_conn.get(session_key)
            
            if username:
                print(f"DEBUG: Valid session {session_id} for user {username}")
                return username
            else:
                print(f"DEBUG: Invalid or expired session {session_id}")
                return None
                
        except Exception as e:
            print(f"DEBUG: Session validation error: {e}")
            return None
    
    def _hash_password(self, password: str, salt: str) -> str:
        """Create a secure hash of the password using PBKDF2 with HMAC-SHA256"""
        try:
            password_bytes = password.encode('utf-8')
            salt_bytes = salt.encode('utf-8')
            
            hash_bytes = hashlib.pbkdf2_hmac(
                'sha256',
                password_bytes,
                salt_bytes,
                100000
            )
            
            hash_hex = hash_bytes.hex()
            print(f"DEBUG: Generated secure password hash ({len(hash_hex)} characters)")
            return hash_hex
            
        except Exception as e:
            print(f"DEBUG: Password hashing failed: {e}")
            raise ValueError(f"Could not hash password: {e}")
    
    # Cognitive Load Methods
    
    def init_cognitive_load_tracking(self, username: str) -> bool:
        """Initialize cognitive load tracking for a user"""
        try:
            redis_conn = self.get_redis()
            key = self.schemas.get_cognitive_load_key(username)
            load_data = self.schemas.create_cognitive_load_entry()
            redis_conn.set(key, json.dumps(load_data))
            print(f"DEBUG: Initialized cognitive load tracking for {username}")
            return True
        except Exception as e:
            print(f"DEBUG: Error initializing cognitive load tracking: {e}")
            return False
    
    def update_cognitive_load(self, username: str, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Update cognitive load based on interaction metrics"""
        try:
            redis_conn = self.get_redis()
            key = self.schemas.get_cognitive_load_key(username)
            
            current_data = redis_conn.get(key)
            if not current_data:
                self.init_cognitive_load_tracking(username)
                current_data = redis_conn.get(key)
            
            load_data = json.loads(current_data)
            
            if load_data["baseline"]["sample_size"] < 10:
                self._update_baseline(load_data, metrics)
            
            current = load_data["current"]
            current["response_time"] = metrics.get("response_time", 0)
            current["timestamp"] = datetime.now().isoformat()
            
            if "accuracy" in metrics:
                current["accuracy_trend"].append(1.0 if metrics["accuracy"] else 0.0)
                if len(current["accuracy_trend"]) > 5:
                    current["accuracy_trend"].pop(0)
            
            if metrics.get("help_requested", False):
                current["help_requests"] += 1
            
            if "self_report" in metrics:
                current["self_report"] = metrics["self_report"]
            
            load_level = self._calculate_cognitive_load(load_data, metrics)
            current["load_level"] = load_level
            
            indicators = load_data["indicators"]
            indicators["struggling_pattern"] = load_level > 0.8
            indicators["optimal_challenge"] = 0.4 <= load_level <= 0.7
            indicators["overloaded"] = load_level > 0.9
            
            redis_conn.set(key, json.dumps(load_data))
            
            return {
                "load_level": load_level,
                "indicators": indicators,
                "recommendation": self._get_load_recommendation(load_level)
            }
            
        except Exception as e:
            print(f"DEBUG: Error updating cognitive load: {e}")
            return {"load_level": 0.5, "indicators": {}, "recommendation": "continue"}
    
    def _update_baseline(self, load_data: Dict, metrics: Dict):
        """Update cognitive load baseline with new metrics"""
        baseline = load_data["baseline"]
        
        if metrics.get("response_time"):
            if baseline["response_time_avg"] is None:
                baseline["response_time_avg"] = metrics["response_time"]
            else:
                n = baseline["sample_size"]
                baseline["response_time_avg"] = (
                    (baseline["response_time_avg"] * n + metrics["response_time"]) / (n + 1)
                )
        
        if "accuracy" in metrics:
            if baseline["accuracy_rate"] is None:
                baseline["accuracy_rate"] = 1.0 if metrics["accuracy"] else 0.0
            else:
                n = baseline["sample_size"]
                new_accuracy = 1.0 if metrics["accuracy"] else 0.0
                baseline["accuracy_rate"] = (
                    (baseline["accuracy_rate"] * n + new_accuracy) / (n + 1)
                )
        
        baseline["sample_size"] += 1
        if baseline["established_at"] is None:
            baseline["established_at"] = datetime.now().isoformat()
    
    def _calculate_cognitive_load(self, load_data: Dict, metrics: Dict) -> float:
        """Calculate cognitive load level (0.0-1.0) based on multiple factors"""
        load_factors = []
        weights = []
        
        baseline_rt = load_data["baseline"]["response_time_avg"]
        if baseline_rt and metrics.get("response_time"):
            rt_ratio = metrics["response_time"] / baseline_rt
            rt_load = min(1.0, max(0.0, (rt_ratio - 0.5) / 1.0))
            load_factors.append(rt_load)
            weights.append(0.3)
        
        accuracy_trend = load_data["current"]["accuracy_trend"]
        if len(accuracy_trend) >= 3:
            recent_accuracy = sum(accuracy_trend[-3:]) / 3
            accuracy_load = 1.0 - recent_accuracy
            load_factors.append(accuracy_load)
            weights.append(0.3)
        
        help_requests = load_data["current"]["help_requests"]
        # Fixed indentation here - this line was causing the error
        help_load = min(1.0, help_requests / 3.0)
        load_factors.append(help_load)
        weights.append(0.2)
        
        self_report = load_data["current"]["self_report"]
        if self_report:
            sr_load = (self_report - 1) / 8.0
            load_factors.append(sr_load)
            weights.append(0.2)
        
        if load_factors:
            total_weight = sum(weights)
            weighted_sum = sum(f * w for f, w in zip(load_factors, weights))
            return weighted_sum / total_weight
        else:
            return 0.5
    
    def _get_load_recommendation(self, load_level: float) -> str:
        """Get recommendation based on cognitive load level"""
        if load_level < 0.3:
            return "increase_difficulty"
        elif load_level > 0.8:
            return "decrease_difficulty"
        elif load_level > 0.9:
            return "provide_break"
        else:
            return "maintain_current"
    
    # Conversation History Methods
    
    def make_history_entry(self, username: str, role: str, message: str) -> int:
        """Store conversation entry for user"""
        try:
            redis_conn = self.get_redis()
            entry = {
                "timestamp": time.time(),
                "datetime": datetime.now().isoformat(),
                "role": role,
                "message": message,
                "username": username
            }
            history_key = f"history:{username}"
            redis_conn.rpush(history_key, json.dumps(entry))
            total_messages = redis_conn.llen(history_key)
            print(f"DEBUG: Stored {role} message for {username}, total messages: {total_messages}")
            return total_messages
        except Exception as e:
            print(f"DEBUG: Error storing conversation entry: {e}")
            return 0
    
    def get_conversation_history(self, username: str, limit: int = 50) -> List[Dict]:
        """Retrieve conversation history for user"""
        try:
            redis_conn = self.get_redis()
            history_key = f"history:{username}"
            raw_messages = redis_conn.lrange(history_key, -limit, -1)
            
            messages = []
            for raw_msg in raw_messages:
                try:
                    entry = json.loads(raw_msg)
                    messages.append(entry)
                except json.JSONDecodeError as e:
                    print(f"DEBUG: Could not parse message: {e}")
                    continue
            
            print(f"DEBUG: Retrieved {len(messages)} messages for {username}")
            return messages
            
        except Exception as e:
            print(f"DEBUG: Error retrieving conversation history: {e}")
            return []
    
    # Course and Progress Management Methods
    
    def get_user_courses(self, username: str) -> List[str]:
        """Get list of courses user is enrolled in"""
        try:
            redis_conn = self.get_redis()
            user_key = f"user:{username}"
            enrolled_courses_json = redis_conn.hget(user_key, "enrolled_courses")
            print(f"DEBUG: Raw enrolled_courses from Redis for {username}: {enrolled_courses_json}")
                    
            if enrolled_courses_json:
                courses = json.loads(enrolled_courses_json)
                print(f"DEBUG: User {username} enrolled in courses: {courses}")
                return courses
            else:
                default_courses = ["CMP511", "PSY555", "CMP202"]
                print(f"DEBUG: No courses found for {username}, using defaults")
                return default_courses
                
        except Exception as e:
            print(f"DEBUG: Error retrieving courses for {username}: {e}")
            return ["CMP511", "PSY555"]
    
    def get_user_progress(self, username: str) -> Dict[str, Dict]:
        """Get user's progress across all enrolled courses"""
        try:
            redis_conn = self.get_redis()
            progress_key = f"progress:{username}"
            progress_data = redis_conn.hgetall(progress_key)
            
            if progress_data:
                parsed_progress = {}
                for course, progress_json in progress_data.items():
                    try:
                        parsed_progress[course] = json.loads(progress_json)
                    except json.JSONDecodeError:
                        parsed_progress[course] = {"week": 1, "completion": 0.0}
                
                print(f"DEBUG: Retrieved progress for {username}: {parsed_progress}")
                return parsed_progress
            else:
                print(f"DEBUG: No progress found for {username}, initializing defaults")
                courses = self.get_user_courses(username)
                return self._create_default_progress(courses)
                
        except Exception as e:
            print(f"DEBUG: Error retrieving progress for {username}: {e}")
            return self._create_default_progress(["Mathematics", "Programming"])
   
    # Mastery Tracking Methods - REAL-TIME UPDATES  
    def save_mastery_data(self, username: str, course: str, mastery_data: Dict[str, Any], 
                          real_time: bool = True) -> bool:
        """Save mastery data with real-time updates support"""
        try:
            redis_conn = self.get_redis()
            key = f"mastery:{username}:{course}"
            json_data = json.dumps(mastery_data)
            
            # Regular save (14 days)
            redis_conn.setex(key, 86400 * 14, json_data)
            
            # 🔥 REAL-TIME: Latest version for immediate updates (5 minutes)
            if real_time:
                latest_key = f"{key}:latest"
                redis_conn.setex(latest_key, 300, json_data)  # 5 minutes TTL
                print(f"DEBUG: ⚡ Saved mastery with real-time update for {username}")
            
            return True
            
        except Exception as e:
            print(f"DEBUG: Error saving mastery data: {e}")
            return False
    
    def load_mastery_data(self, username: str, course: str, prefer_latest: bool = True) -> Optional[Dict[str, Any]]:
        """Load mastery data with preference for latest real-time version"""
        try:
            redis_conn = self.get_redis()
            key = f"mastery:{username}:{course}"
            
            # 🔥 REAL-TIME: Try latest version first
            if prefer_latest:
                latest_key = f"{key}:latest"
                latest_data = redis_conn.get(latest_key)
                if latest_data:
                    print(f"DEBUG: ⚡ Loaded latest mastery data for {username}")
                    return json.loads(latest_data)
            
            # Fallback to regular version
            regular_data = redis_conn.get(key)
            if regular_data:
                print(f"DEBUG: Loaded regular mastery data for {username}")
                return json.loads(regular_data)
            
            return None
            
        except Exception as e:
            print(f"DEBUG: Error loading mastery data: {e}")
            return None
    
    def update_go_progress(self, username: str, course: str, week: int, 
                          go_progress_data: Dict[str, Any]) -> bool:
        """Update GO progress with real-time persistence"""
        try:
            redis_conn = self.get_redis()
            key = f"go_progress:{username}:{course}:week_{week}"
            json_data = json.dumps(go_progress_data)
            
            # Save with 30 day expiry
            redis_conn.setex(key, 86400 * 30, json_data)
            
            # 🔥 REAL-TIME: Also save latest version
            latest_key = f"{key}:latest"
            redis_conn.setex(latest_key, 600, json_data)  # 10 minutes
            
            print(f"DEBUG: ⚡ Updated GO progress for {username} week {week}")
            return True
            
        except Exception as e:
            print(f"DEBUG: Error updating GO progress: {e}")
            return False
    
    def get_go_progress(self, username: str, course: str, week: int) -> Dict[str, Any]:
        """Get GO progress data with latest preference"""
        try:
            redis_conn = self.get_redis()
            key = f"go_progress:{username}:{course}:week_{week}"
            
            # Try latest version first
            latest_key = f"{key}:latest"
            latest_data = redis_conn.get(latest_key)
            if latest_data:
                return json.loads(latest_data)
            
            # Fallback to regular version
            regular_data = redis_conn.get(key)
            if regular_data:
                return json.loads(regular_data)
            
            return {}
            
        except Exception as e:
            print(f"DEBUG: Error getting GO progress: {e}")
            return {}
    
    def set_mastery_update_flag(self, username: str, course: str, update_data: Dict[str, Any]):
        """Set flag for real-time mastery updates"""
        try:
            redis_conn = self.get_redis()
            flag_key = f"mastery_update:{username}:{course}"
            
            flag_data = {
                "timestamp": time.time(),
                "update_data": update_data,
                "triggered_by": "quiz_answer"  # or "tutor_interaction"
            }
            
            # Short TTL for update flags (1 minute)
            redis_conn.setex(flag_key, 60, json.dumps(flag_data))
            print(f"DEBUG: ⚡ Set mastery update flag for {username}")
            
        except Exception as e:
            print(f"DEBUG: Error setting mastery update flag: {e}")
    
    def get_mastery_update_flag(self, username: str, course: str) -> Optional[Dict[str, Any]]:
        """Check for real-time mastery update flags"""
        try:
            redis_conn = self.get_redis()
            flag_key = f"mastery_update:{username}:{course}"
            flag_data = redis_conn.get(flag_key)
            
            if flag_data:
                return json.loads(flag_data)
            return None
            
        except Exception as e:
            print(f"DEBUG: Error getting mastery update flag: {e}")
            return None
    
    def update_user_progress(self, username: str, course: str, week: int = None, 
                           completion: float = None, increment_completion: float = None):
        """Update user's progress in a specific course"""
        try:
            redis_conn = self.get_redis()
            progress_key = f"progress:{username}"
            
            current_progress_json = redis_conn.hget(progress_key, course)
            if current_progress_json:
                current_progress = json.loads(current_progress_json)
            else:
                current_progress = {"week": 1, "completion": 0.0}
            
            if week is not None:
                current_progress["week"] = week
            
            if completion is not None:
                current_progress["completion"] = max(0.0, min(1.0, completion))
            
            if increment_completion is not None:
                new_completion = current_progress["completion"] + increment_completion
                current_progress["completion"] = max(0.0, min(1.0, new_completion))
            
            current_progress["last_updated"] = datetime.now().isoformat()
            redis_conn.hset(progress_key, course, json.dumps(current_progress))
            
            print(f"DEBUG: Updated progress for {username} in {course}: {current_progress}")
            
        except Exception as e:
            print(f"DEBUG: Error updating progress for {username}: {e}")
    
    
    def create_memory_session(self, username: str) -> str:
        """Create a new memory session for user"""
        try:
            redis_conn = self.get_redis()
            if not redis_conn:
                raise ConnectionError("No Redis connection")
                
            session_id = f"mem_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
            
            # Store active session reference
            active_key = self.memory_schemas.get_active_session_key(username)
            redis_conn.setex(active_key, 3600, session_id)  # 1 hour expiry
            
            print(f"DEBUG: Created memory session {session_id} for {username}")
            return session_id
            
        except Exception as e:
            print(f"ERROR: Failed to create memory session: {e}")
            return f"mem_{username}_fallback_{uuid.uuid4().hex[:8]}"
    
    def get_active_session(self, username: str) -> Optional[str]:
        """Get active memory session for user"""
        try:
            redis_conn = self.get_redis()
            if not redis_conn:
                return None
                
            active_key = self.memory_schemas.get_active_session_key(username)
            session_id = redis_conn.get(active_key)
            
            if not session_id:
                # Create new session if none exists
                session_id = self.create_memory_session(username)
            
            return session_id
            
        except Exception as e:
            print(f"ERROR: Failed to get active session: {e}")
            return None
    
    def store_short_term_memory(
        self, 
        username: str, 
        interaction_type: str, 
        content: Dict[str, Any],
        session_id: str = None
    ) -> bool:
        """Store interaction in short-term memory"""
        try:
            redis_conn = self.get_redis()
            if not redis_conn:
                return False
            
            # Get or create session
            if not session_id:
                session_id = self.get_active_session(username)
            
            # Create memory entry
            memory_entry = self.memory_schemas.create_short_term_entry(
                interaction_type=interaction_type,
                content=content,
                metadata={
                    "cognitive_load": self.get_current_cognitive_load(username),
                    "course": content.get("course", "unknown"),
                    "week": content.get("week", 0)
                }
            )
            
            # Store in Redis
            key = self.memory_schemas.get_short_term_key(username, session_id)
            redis_conn.rpush(key, json.dumps(memory_entry))
            redis_conn.expire(key, 86400)  # 24 hour expiry
            
            # Queue for consolidation if enough memories
            memory_count = redis_conn.llen(key)
            if memory_count >= 5:  # Consolidate after 5 interactions
                self.queue_for_consolidation(username, session_id)
            
            print(f"DEBUG: Stored {interaction_type} memory for {username} (count: {memory_count})")
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to store short-term memory: {e}")
            return False
    
    def queue_for_consolidation(self, username: str, session_id: str, priority: int = 1) -> bool:
        """Add session to consolidation queue"""
        try:
            redis_conn = self.get_redis()
            if not redis_conn:
                return False
            
            # Create consolidation task
            task = self.memory_schemas.create_consolidation_task(
                username=username,
                session_id=session_id,
                priority=priority
            )
            
            # Add to queue
            queue_key = self.memory_schemas.get_consolidation_queue_key()
            redis_conn.rpush(queue_key, json.dumps(task))
            
            print(f"DEBUG: Queued session {session_id} for consolidation")
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to queue for consolidation: {e}")
            return False
    
    def get_short_term_memories(
        self, 
        username: str, 
        session_id: str = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Retrieve short-term memories"""
        try:
            redis_conn = self.get_redis()
            if not redis_conn:
                return []
            
            if not session_id:
                session_id = self.get_active_session(username)
            
            if not session_id:
                return []
            
            key = self.memory_schemas.get_short_term_key(username, session_id)
            raw_memories = redis_conn.lrange(key, -limit, -1)
            
            memories = []
            for raw_mem in raw_memories:
                try:
                    memories.append(json.loads(raw_mem))
                except json.JSONDecodeError:
                    continue
            
            print(f"DEBUG: Retrieved {len(memories)} short-term memories for {username}")
            return memories
            
        except Exception as e:
            print(f"ERROR: Failed to retrieve short-term memories: {e}")
            return []
    
    def get_long_term_memories(
        self, 
        username: str, 
        course: str = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Retrieve long-term memories"""
        try:
            redis_conn = self.get_redis()
            if not redis_conn:
                return []
            
            key = self.memory_schemas.get_long_term_key(username, course)
            raw_memories = redis_conn.lrange(key, -limit, -1)
            
            memories = []
            for raw_mem in raw_memories:
                try:
                    memory = json.loads(raw_mem)
                    memory["retrieval_count"] = memory.get("retrieval_count", 0) + 1
                    memories.append(memory)
                except json.JSONDecodeError:
                    continue
            
            print(f"DEBUG: Retrieved {len(memories)} long-term memories for {username}")
            return memories
            
        except Exception as e:
            print(f"ERROR: Failed to retrieve long-term memories: {e}")
            return []
    
    def get_current_cognitive_load(self, username: str) -> float:
        """Helper to get current cognitive load for memory metadata"""
        try:
            redis_conn = self.get_redis()
            if not redis_conn:
                return 0.5
                
            key = f"cognitive_load:{username}:current"
            data = redis_conn.get(key)
            if data:
                load_data = json.loads(data)
                return load_data.get("current", {}).get("load_level", 0.5)
        except:
            pass
        return 0.5  # Default moderate load
    
    def _initialize_course_progress(self, username: str, courses: List[str]):
        """Initialize progress tracking for a new user's enrolled courses"""
        try:
            redis_conn = self.get_redis()
            progress_key = f"progress:{username}"
            
            for course in courses:
                initial_progress = {
                    "week": 1,
                    "completion": 0.0,
                    "started_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat()
                }
                redis_conn.hset(progress_key, course, json.dumps(initial_progress))
            
            print(f"DEBUG: Initialized progress for {username} in courses: {courses}")
            
        except Exception as e:
            print(f"DEBUG: Error initializing progress for {username}: {e}")
    
    def _create_default_progress(self, courses: List[str]) -> Dict[str, Dict]:
        """Create default progress structure for courses"""
        default_progress = {}
        for course in courses:
            default_progress[course] = {
                "week": 1,
                "completion": 0.0,
                "last_updated": datetime.now().isoformat()
            }
        return default_progress
    
    # Mastery and Engagement Methods (stubs for now - implement as needed)
    
    def update_mastery(self, username: str, course: str, 
                      knowledge_component: str, success: bool,
                      learning_objective: str = None) -> Dict[str, float]:
        """Update mastery based on interaction with a knowledge component"""
        # This is a stub - implement based on your mastery tracking needs
        return {"kc_mastery": 0.5, "lo_mastery": 0.5, "course_mastery": 0.5}
    
    def update_engagement(self, username: str, course: str, 
                         engagement_event: Dict[str, Any]) -> Dict[str, Any]:
        """Update engagement metrics based on user interaction"""
        # This is a stub - implement based on your engagement tracking needs
        return {"interaction_frequency": 1, "emotional_state": "neutral", "engagement_level": "moderate"}
    
    def record_scaffolding(self, username: str, course: str, 
                          scaffolding_event: Dict[str, Any]) -> bool:
        """Record a scaffolding event and its effectiveness"""
        # This is a stub - implement based on your scaffolding tracking needs
        return True
    
    def get_scaffolding_preferences(self, username: str, course: str) -> Dict[str, Any]:
        """Get user's scaffolding preferences and effectiveness data"""
        # This is a stub - implement based on your scaffolding preference needs
        return {"preferred_types": [], "effectiveness": {}, "optimal_timing": "immediate", "fading_rate": "moderate"}

    def lpush(self, key: str, *values) -> int:
        """Left push values to a Redis list"""
        try:
            return self.redis_client.lpush(key, *values)
        except Exception as e:
            print(f"DEBUG: Redis lpush failed: {e}")
            return 0
    
    def ltrim(self, key: str, start: int, end: int) -> bool:
        """Trim a Redis list to the specified range"""
        try:
            return self.redis_client.ltrim(key, start, end)
        except Exception as e:
            print(f"DEBUG: Redis ltrim failed: {e}")
            return False
    
    def lrange(self, key: str, start: int, end: int) -> List[str]:
        """Get a range of elements from a Redis list"""
        try:
            return self.redis_client.lrange(key, start, end)
        except Exception as e:
            print(f"DEBUG: Redis lrange failed: {e}")
            return []
    

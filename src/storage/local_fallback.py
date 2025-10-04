# File: src/storage/local_fallback.py

"""
Local File-Based Authentication Fallback
Provides authentication functionality using local files when Redis is unavailable

This fallback system maintains the same interface as the Redis-based authentication
but stores data in local JSON files instead of a remote database.
"""

import json
import os
import hashlib
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

class LocalAuthFallback:
    """
    Local file-based authentication system for development and testing.
    
    This class provides the same interface as your Redis authentication system
    but stores all data in local JSON files, allowing development to continue
    even when Redis connectivity is unavailable.
    """
    
    def __init__(self, data_dir: str = "local_auth_data"):
        """
        Initialize the local authentication system.
        
        Args:
            data_dir (str): Directory to store authentication data files
        """
        self.data_dir = data_dir
        self.users_file = os.path.join(data_dir, "users.json")
        self.sessions_file = os.path.join(data_dir, "sessions.json")
        self.conversations_file = os.path.join(data_dir, "conversations.json")
        self.progress_file = os.path.join(data_dir, "progress.json")
        
        # Create data directory if it doesn't exist
        os.makedirs(data_dir, exist_ok=True)
        
        # Initialize data files if they don't exist
        self._initialize_data_files()
        
        print(f"DEBUG: Local auth fallback initialized in {data_dir}")
    
    def _initialize_data_files(self):
        """Create empty data files if they don't exist"""
        for file_path in [self.users_file, self.sessions_file, self.conversations_file, self.progress_file]:
            if not os.path.exists(file_path):
                with open(file_path, 'w') as f:
                    json.dump({}, f)
                print(f"DEBUG: Created {file_path}")
    
    def _load_data(self, file_path: str) -> Dict:
        """Load data from a JSON file with error handling"""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _save_data(self, file_path: str, data: Dict):
        """Save data to a JSON file with error handling"""
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"DEBUG: Error saving data to {file_path}: {e}")
    
    def _hash_password(self, password: str, salt: str) -> str:
        """Hash password using the same method as your Redis system"""
        try:
            password_bytes = password.encode('utf-8')
            salt_bytes = salt.encode('utf-8')
            
            hash_bytes = hashlib.pbkdf2_hmac('sha256', password_bytes, salt_bytes, 100000)
            hash_hex = hash_bytes.hex()
            
            return hash_hex
        except Exception as e:
            raise ValueError(f"Password hashing failed: {e}")
    
    def create_user(self, username: str, password: str, full_name: str, enrolled_courses: List[str] = None) -> Tuple[bool, str]:
        """Create a new user account (same interface as Redis version)"""
        try:
            users_data = self._load_data(self.users_file)
            
            # Check if username already exists
            if username in users_data:
                return False, "Username already exists"
            
            # Set default courses if none provided
            if enrolled_courses is None:
                enrolled_courses = ["Mathematics", "Programming", "AI/ML", "Game Design", "Psychology"]
            
            # Generate secure password hash
            salt = secrets.token_hex(32)
            password_hash = self._hash_password(password, salt)
            
            # Create user record
            users_data[username] = {
                "username": username,
                "full_name": full_name,
                "password_hash": password_hash,
                "salt": salt,
                "created_at": datetime.now().isoformat(),
                "last_login": None,
                "is_active": True,
                "enrolled_courses": enrolled_courses
            }
            
            # Save updated user data
            self._save_data(self.users_file, users_data)
            
            # Initialize progress tracking
            self._initialize_user_progress(username, enrolled_courses)
            
            print(f"DEBUG: Local user {username} created successfully")
            return True, "User created successfully"
            
        except Exception as e:
            print(f"DEBUG: Local user creation error: {e}")
            return False, f"Registration failed: {str(e)}"
    
    def authenticate_user(self, username: str, password: str) -> Tuple[bool, Optional[str]]:
        """Authenticate user and create session (same interface as Redis version)"""
        try:
            users_data = self._load_data(self.users_file)
            
            # Check if user exists
            if username not in users_data:
                print(f"DEBUG: Local user {username} not found")
                return False, None
            
            user_data = users_data[username]
            
            # Check if account is active
            if not user_data.get("is_active", True):
                print(f"DEBUG: Local user {username} account is inactive")
                return False, None
            
            # Verify password
            stored_hash = user_data.get("password_hash")
            salt = user_data.get("salt")
            
            if not stored_hash or not salt:
                print(f"DEBUG: Invalid password data for local user {username}")
                return False, None
            
            computed_hash = self._hash_password(password, salt)
            
            if computed_hash != stored_hash:
                print(f"DEBUG: Invalid password for local user {username}")
                return False, None
            
            # Create session
            session_id = self._create_session(username)
            
            # Update last login
            user_data["last_login"] = datetime.now().isoformat()
            self._save_data(self.users_file, users_data)
            
            print(f"DEBUG: Local user {username} authenticated successfully")
            return True, session_id
            
        except Exception as e:
            print(f"DEBUG: Local authentication error: {e}")
            return False, None
    
    def _create_session(self, username: str) -> str:
        """Create a session for authenticated user"""
        sessions_data = self._load_data(self.sessions_file)
        
        session_id = secrets.token_hex(32)
        expiry_time = (datetime.now() + timedelta(hours=24)).isoformat()
        
        sessions_data[session_id] = {
            "username": username,
            "created_at": datetime.now().isoformat(),
            "expires_at": expiry_time
        }
        
        self._save_data(self.sessions_file, sessions_data)
        return session_id
    
    def validate_session(self, session_id: str) -> Optional[str]:
        """Validate session and return username if valid"""
        try:
            sessions_data = self._load_data(self.sessions_file)
            
            if session_id not in sessions_data:
                return None
            
            session_data = sessions_data[session_id]
            expires_at = datetime.fromisoformat(session_data["expires_at"])
            
            if datetime.now() > expires_at:
                # Session expired, remove it
                del sessions_data[session_id]
                self._save_data(self.sessions_file, sessions_data)
                return None
            
            return session_data["username"]
            
        except Exception as e:
            print(f"DEBUG: Session validation error: {e}")
            return None
    
    def get_user_courses(self, username: str) -> List[str]:
        """Get list of courses user is enrolled in"""
        try:
            users_data = self._load_data(self.users_file)
            
            if username in users_data:
                return users_data[username].get("enrolled_courses", ["Mathematics", "Programming"])
            else:
                return ["Mathematics", "Programming"]
                
        except Exception as e:
            print(f"DEBUG: Error retrieving courses: {e}")
            return ["Mathematics", "Programming"]
    
    def get_user_progress(self, username: str) -> Dict[str, Dict]:
        """Get user's progress across all enrolled courses"""
        try:
            progress_data = self._load_data(self.progress_file)
            
            if username in progress_data:
                return progress_data[username]
            else:
                # Initialize default progress
                courses = self.get_user_courses(username)
                default_progress = {}
                for course in courses:
                    default_progress[course] = {"week": 1, "completion": 0.0}
                return default_progress
                
        except Exception as e:
            print(f"DEBUG: Error retrieving progress: {e}")
            return {"Mathematics": {"week": 1, "completion": 0.0}}
    
    def _initialize_user_progress(self, username: str, courses: List[str]):
        """Initialize progress tracking for a new user"""
        try:
            progress_data = self._load_data(self.progress_file)
            
            progress_data[username] = {}
            for course in courses:
                progress_data[username][course] = {
                    "week": 1,
                    "completion": 0.0,
                    "started_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat()
                }
            
            self._save_data(self.progress_file, progress_data)
            print(f"DEBUG: Initialized local progress for {username}")
            
        except Exception as e:
            print(f"DEBUG: Error initializing progress: {e}")
    
    def make_history_entry(self, username: str, role: str, message: str) -> int:
        """Store conversation entry for user"""
        try:
            conversations_data = self._load_data(self.conversations_file)
            
            if username not in conversations_data:
                conversations_data[username] = []
            
            entry = {
                "timestamp": time.time(),
                "datetime": datetime.now().isoformat(),
                "role": role,
                "message": message,
                "username": username
            }
            
            conversations_data[username].append(entry)
            self._save_data(self.conversations_file, conversations_data)
            
            return len(conversations_data[username])
            
        except Exception as e:
            print(f"DEBUG: Error storing conversation: {e}")
            return 0
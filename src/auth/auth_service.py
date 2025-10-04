# File: src/auth/auth_service.py

"""
Authentication Service for LEA Tutor
High-level authentication interface for Streamlit integration
"""

from typing import Optional, Tuple, Dict, List
from src.storage.redis_client import LEARedisClient
from src.storage.local_fallback import LocalAuthFallback

class AuthService:
    """
    High-level authentication service for LEA Tutor.
    
    This class provides simple methods that Streamlit can use for authentication,
    hiding the complexity of Redis operations and providing educational-specific functionality.
    """
    
    def __init__(self, redis_url: str):
        """
        Initialize authentication service with Redis connection.
        
        Args:
            redis_url (str): Redis connection URL
        """
        self.redis_client = LEARedisClient(redis_url)
        print("DEBUG: AuthService initialized with Redis connection")
    
    def login_user(self, username: str, password: str) -> Tuple[bool, Optional[str], str]:
        """
        Authenticate user and return session information.
        Simple interface for Streamlit login handling.
        
        Args:
            username (str): Username to authenticate
            password (str): Password to verify
            
        Returns:
            Tuple[bool, Optional[str], str]: (success, session_id, message)
        """
        success, session_id = self.redis_client.authenticate_user(username, password)
        
        if success:
            message = f"Welcome back, {username}!"
            print(f"DEBUG: Login successful for {username}")
        else:
            message = "Invalid username or password"
            print(f"DEBUG: Login failed for {username}")
            
        return success, session_id, message
    
    def register_user(self, username: str, password: str, full_name: str, 
                     selected_courses: List[str] = None) -> Tuple[bool, str]:
        """
        Register a new user account.
        Simple interface for Streamlit registration handling.
        
        Args:
            username (str): Desired username
            password (str): User's password
            full_name (str): User's full name
            selected_courses (List[str], optional): Courses to enroll in
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        # return self.redis_client.create_user(username, password, full_name, selected_courses)
        return self.redis_client.create_user(username, password, full_name, enrolled_courses=selected_courses)
    
    def validate_session(self, session_id: str) -> Optional[str]:
        """
        Check if session is valid and return username.
        Simple interface for Streamlit session validation.
        
        Args:
            session_id (str): Session ID to validate
            
        Returns:
            Optional[str]: Username if session valid, None otherwise
        """
        return self.redis_client.validate_session(session_id)
    
    def get_user_data(self, username: str) -> Dict:
        """
        Get complete user data for dashboard display.
        Combines courses and progress into one convenient call.
        
        Args:
            username (str): Username to get data for
            
        Returns:
            Dict: User data including courses and progress
        """
        try:
            courses = self.redis_client.get_user_courses(username)
            progress = self.redis_client.get_user_progress(username)
            
            user_data = {
                "username": username,
                "enrolled_courses": courses,
                "progress": progress
            }
            
            print(f"DEBUG: Retrieved complete user data for {username}")
            return user_data
            
        except Exception as e:
            print(f"DEBUG: Error getting user data for {username}: {e}")
            return {
                "username": username,
                "enrolled_courses": ["CMP511", "PSY555"],
                "progress": {"CMP511": {"week": 1, "completion": 0}}
            }
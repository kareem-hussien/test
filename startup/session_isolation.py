"""
Session Isolation module for Travian Whispers application.
This module handles browser session isolation and management for user isolation.
"""
import logging
import os
import random
import shutil
import string
import time
import tempfile
from datetime import datetime, timedelta
import threading
from pathlib import Path

# Configure logger
logger = logging.getLogger(__name__)

class SessionManager:
    """
    Manages isolated browser sessions for users.
    Creates separate Chrome user data directories for each session.
    """
    
    def __init__(self, base_dir=None):
        """
        Initialize the Session Manager.
        
        Args:
            base_dir (str, optional): Base directory for storing sessions
        """
        # Use specified base directory or create a default one
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            app_data_dir = Path.home() / "travian-whispers-sessions"
            self.base_dir = app_data_dir
        
        # Create base directory if it doesn't exist
        if not self.base_dir.exists():
            self.base_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created session base directory: {self.base_dir}")
        
        # Dictionary to track active sessions
        self.active_sessions = {}
        
        # Lock for thread safety
        self.lock = threading.RLock()
        
        logger.info(f"Session Manager initialized with base directory: {self.base_dir}")
    
    def get_session_for_user(self, user_id, create=True):
        """
        Get or create a session directory for a user.
        
        Args:
            user_id (str): The user ID
            create (bool): Create a new session if none exists
            
        Returns:
            str: Path to session directory or None if creation fails
        """
        with self.lock:
            # Check if user already has an active session
            if user_id in self.active_sessions:
                session_path = self.active_sessions[user_id]["path"]
                
                # Check if the directory still exists
                if os.path.exists(session_path):
                    logger.debug(f"Retrieved existing session for user {user_id}: {session_path}")
                    return session_path
                else:
                    # Directory was deleted, remove from active sessions
                    logger.warning(f"Session directory for user {user_id} no longer exists: {session_path}")
                    del self.active_sessions[user_id]
            
            # Create a new session if requested
            if create:
                return self._create_new_session(user_id)
            
            return None
    
    def _create_new_session(self, user_id):
        """
        Create a new session directory for a user.
        
        Args:
            user_id (str): The user ID
            
        Returns:
            str: Path to session directory or None if creation fails
        """
        try:
            # Generate a unique session ID
            session_id = f"session_{user_id}_{int(time.time())}_{self._random_string(8)}"
            
            # Create session directory
            session_dir = self.base_dir / session_id
            session_dir.mkdir(parents=True, exist_ok=True)
            
            # Create Chrome subdirectories
            for subdir in ["Default", "Default/Cache", "Default/Cookies"]:
                (session_dir / subdir).mkdir(parents=True, exist_ok=True)
            
            # Track the session
            self.active_sessions[user_id] = {
                "id": session_id,
                "path": str(session_dir),
                "created_at": datetime.now()
            }
            
            logger.info(f"Created new session for user {user_id}: {session_dir}")
            return str(session_dir)
        except Exception as e:
            logger.error(f"Error creating session for user {user_id}: {e}")
            return None
    
    def _random_string(self, length=8):
        """
        Generate a random string of specified length.
        
        Args:
            length (int): Length of the string
            
        Returns:
            str: Random string
        """
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
    
    def rotate_user_session(self, user_id):
        """
        Rotate a user's session (create a new one and delete the old one).
        
        Args:
            user_id (str): The user ID
            
        Returns:
            str: Path to new session directory or None if rotation fails
        """
        with self.lock:
            # Get the existing session path
            old_session_path = None
            if user_id in self.active_sessions:
                old_session_path = self.active_sessions[user_id]["path"]
            
            # Create a new session
            new_session_path = self._create_new_session(user_id)
            
            if not new_session_path:
                logger.error(f"Failed to create new session for user {user_id}")
                return None
            
            # Delete the old session asynchronously to avoid blocking
            if old_session_path:
                threading.Thread(target=self._delete_session_dir, args=(old_session_path,)).start()
            
            return new_session_path
    
    def _delete_session_dir(self, session_path):
        """
        Delete a session directory.
        
        Args:
            session_path (str): Path to session directory
        """
        try:
            # Safety checks
            if not session_path or not os.path.exists(session_path):
                return
            
            # Verify the path is under our base directory
            session_path = Path(session_path)
            if self.base_dir not in session_path.parents and self.base_dir != session_path.parent:
                logger.warning(f"Refusing to delete directory outside session base: {session_path}")
                return
            
            # Delete the directory
            shutil.rmtree(session_path, ignore_errors=True)
            logger.info(f"Deleted session directory: {session_path}")
        except Exception as e:
            logger.error(f"Error deleting session directory {session_path}: {e}")
    
    def clear_user_session(self, user_id):
        """
        Clear a user's session.
        
        Args:
            user_id (str): The user ID
            
        Returns:
            bool: True if cleared successfully, False otherwise
        """
        with self.lock:
            if user_id not in self.active_sessions:
                logger.warning(f"No active session found for user {user_id}")
                return False
            
            session_path = self.active_sessions[user_id]["path"]
            
            # Remove from active sessions
            del self.active_sessions[user_id]
            
            # Delete session directory
            self._delete_session_dir(session_path)
            
            return True
    
    def clean_old_sessions(self, max_age_hours=24):
        """
        Clean up old session directories.
        
        Args:
            max_age_hours (int): Maximum session age in hours
            
        Returns:
            int: Number of sessions cleaned up
        """
        cleaned_count = 0
        
        try:
            # Calculate cutoff time
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            
            with self.lock:
                # Check active sessions
                users_to_remove = []
                
                for user_id, session_info in self.active_sessions.items():
                    if session_info["created_at"] < cutoff_time:
                        users_to_remove.append(user_id)
                
                # Remove old sessions
                for user_id in users_to_remove:
                    session_path = self.active_sessions[user_id]["path"]
                    del self.active_sessions[user_id]
                    self._delete_session_dir(session_path)
                    cleaned_count += 1
                
                # Also check for any directories not in active_sessions
                for session_dir in self.base_dir.iterdir():
                    if not session_dir.is_dir():
                        continue
                    
                    # Check if the directory is an active session
                    is_active = False
                    for session_info in self.active_sessions.values():
                        if session_info["path"] == str(session_dir):
                            is_active = True
                            break
                    
                    if not is_active:
                        # Check directory creation time
                        try:
                            creation_time = datetime.fromtimestamp(session_dir.stat().st_ctime)
                            if creation_time < cutoff_time:
                                self._delete_session_dir(str(session_dir))
                                cleaned_count += 1
                        except Exception as e:
                            logger.error(f"Error checking session directory age: {e}")
            
            logger.info(f"Cleaned up {cleaned_count} old sessions (older than {max_age_hours} hours)")
            return cleaned_count
        except Exception as e:
            logger.error(f"Error cleaning old sessions: {e}")
            return cleaned_count


class BrowserIsolationManager:
    """
    Coordinates IP and session management for browser isolation.
    """
    
    def __init__(self, session_base_dir=None):
        """
        Initialize the Browser Isolation Manager.
        
        Args:
            session_base_dir (str, optional): Base directory for storing sessions
        """
        # Initialize session manager
        self.session_manager = SessionManager(session_base_dir)
        
        # Initialize IP manager
        from startup.ip_manager import IPManager
        self.ip_manager = IPManager()
        self.ip_manager.initialize()
        
        # Track user-agent rotations
        self.user_agents = self._load_user_agents()
        self.user_agent_map = {}
        
        logger.info("Browser Isolation Manager initialized")
    
    def _load_user_agents(self):
        """
        Load a list of user agents for rotation.
        
        Returns:
            list: List of user agents
        """
        # Default set of common user agents
        default_agents = [
            # Chrome Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
            # Chrome Mac
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
            # Firefox Windows
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            # Firefox Mac
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:90.0) Gecko/20100101 Firefox/90.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0",
            # Edge
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36 Edg/92.0.902.55"
        ]
        
        # Try to load from file if exists
        user_agents_file = os.path.join(os.path.dirname(__file__), "user_agents.txt")
        try:
            if os.path.exists(user_agents_file):
                with open(user_agents_file, "r") as f:
                    agents = [line.strip() for line in f if line.strip()]
                    if agents:
                        return agents
        except Exception as e:
            logger.warning(f"Error loading user agents from file: {e}")
        
        return default_agents
    
    def get_user_agent_for_user(self, user_id):
        """
        Get a consistent user agent for a user.
        
        Args:
            user_id (str): The user ID
            
        Returns:
            str: User agent string
        """
        if user_id not in self.user_agent_map:
            # Assign a random user agent
            self.user_agent_map[user_id] = random.choice(self.user_agents)
        
        return self.user_agent_map[user_id]
    
    def rotate_user_agent(self, user_id):
        """
        Rotate a user's user agent.
        
        Args:
            user_id (str): The user ID
            
        Returns:
            str: New user agent
        """
        # Select a new user agent that's different from the current one
        current_agent = self.user_agent_map.get(user_id)
        
        if current_agent:
            available_agents = [agent for agent in self.user_agents if agent != current_agent]
        else:
            available_agents = self.user_agents
        
        new_agent = random.choice(available_agents or self.user_agents)
        self.user_agent_map[user_id] = new_agent
        
        return new_agent
    
    def get_browser_config_for_user(self, user_id):
        """
        Get browser configuration for a user.
        
        Args:
            user_id (str): The user ID
            
        Returns:
            dict: Browser configuration
        """
        # Get user's IP
        ip_info = self.ip_manager.get_ip_for_user(user_id)
        
        # Get user's session
        session_path = self.session_manager.get_session_for_user(user_id)
        
        # Get user agent
        user_agent = self.get_user_agent_for_user(user_id)
        
        # Build configuration
        config = {
            "user_data_dir": session_path,
            "user_agent": user_agent,
            "ip_info": ip_info,
            "proxy_settings": None
        }
        
        # Add proxy settings if IP is available
        if ip_info:
            # Build proxy settings based on IP information
            proxy_url = ip_info.get("proxy_url")
            
            if proxy_url:
                config["proxy_settings"] = {
                    "proxy_type": ip_info.get("proxy_type", "http"),
                    "proxy_url": proxy_url,
                    "proxy_address": ip_info.get("ip_address"),
                    "proxy_port": ip_info.get("port"),
                    "proxy_username": ip_info.get("username"),
                    "proxy_password": ip_info.get("password")
                }
        
        return config
    
    def get_chrome_options(self, user_id, headless=True):
        """
        Get Chrome options for a user with proper isolation.
        
        Args:
            user_id (str): The user ID
            headless (bool): Whether to run in headless mode
            
        Returns:
            webdriver.chrome.options.Options: Chrome options
        """
        from selenium.webdriver.chrome.options import Options
        
        # Get browser configuration
        config = self.get_browser_config_for_user(user_id)
        
        # Create options
        chrome_options = Options()
        
        # Set user data directory
        if config.get("user_data_dir"):
            chrome_options.add_argument(f"--user-data-dir={config['user_data_dir']}")
        
        # Set user agent
        if config.get("user_agent"):
            chrome_options.add_argument(f"--user-agent={config['user_agent']}")
        
        # Set proxy if available
        proxy_settings = config.get("proxy_settings")
        if proxy_settings:
            proxy_url = proxy_settings["proxy_url"]
            if proxy_url:
                chrome_options.add_argument(f"--proxy-server={proxy_url}")
        
        # Set headless mode if requested
        if headless:
            chrome_options.add_argument("--headless")
        
        # Set other important options for stability and reduced detection
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Disable images to save bandwidth and improve speed
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        
        # Disable extensions
        chrome_options.add_argument("--disable-extensions")
        
        # Set experimental options to avoid detection
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        return chrome_options
    
    def rotate_user_identity(self, user_id):
        """
        Rotate a user's entire digital identity (IP and browser session).
        
        Args:
            user_id (str): The user ID
            
        Returns:
            dict: New browser configuration
        """
        # Rotate session
        session_path = self.session_manager.rotate_user_session(user_id)
        
        # Rotate IP
        ip_info = self.ip_manager.rotate_ip_for_user(user_id)
        
        # Rotate user agent
        user_agent = self.rotate_user_agent(user_id)
        
        # Log the rotation
        if session_path and ip_info:
            logger.info(f"Rotated identity for user {user_id}: Session={session_path}, IP={ip_info['ip_address']}")
            return self.get_browser_config_for_user(user_id)
        else:
            logger.error(f"Failed to rotate identity for user {user_id}")
            return None
    
    def handle_detection_risk(self, user_id, risk_level, context=None):
        """
        Handle a detection risk by taking appropriate action.
        
        Args:
            user_id (str): The user ID
            risk_level (str): Risk level (low, medium, high, critical)
            context (dict, optional): Context information
            
        Returns:
            dict: Action taken
        """
        context = context or {}
        logger.warning(f"Detection risk for user {user_id}: {risk_level} - {context}")
        
        # Define actions based on risk level
        if risk_level == "critical":
            # Rotate identity and report IP ban
            ip_info = self.ip_manager.get_ip_for_user(user_id)
            if ip_info:
                self.ip_manager.report_ip_failure(
                    ip_info["_id"],
                    "suspected_ban",
                    f"Critical detection risk: {context.get('reason', 'Unknown')}"
                )
            
            # Force complete identity rotation
            new_config = self.rotate_user_identity(user_id)
            
            return {
                "action": "identity_rotation",
                "message": "Critical detection risk - rotated entire identity",
                "config": new_config
            }
        elif risk_level == "high":
            # Rotate session and IP
            new_config = self.rotate_user_identity(user_id)
            
            return {
                "action": "identity_rotation",
                "message": "High detection risk - rotated identity",
                "config": new_config
            }
        elif risk_level == "medium":
            # Rotate just the IP
            ip_info = self.ip_manager.rotate_ip_for_user(user_id)
            
            return {
                "action": "ip_rotation",
                "message": "Medium detection risk - rotated IP address",
                "ip_info": ip_info
            }
        else:  # "low"
            # Just rotate the user agent
            new_agent = self.rotate_user_agent(user_id)
            
            return {
                "action": "user_agent_rotation",
                "message": "Low detection risk - rotated user agent",
                "user_agent": new_agent
            }
    
    def cleanup(self):
        """
        Clean up resources used by the Browser Isolation Manager.
        
        Returns:
            bool: True if cleanup successful, False otherwise
        """
        try:
            # Clean up sessions
            self.session_manager.clean_old_sessions()
            
            # Do any other cleanup needed
            
            return True
        except Exception as e:
            logger.error(f"Error during Browser Isolation Manager cleanup: {e}")
            return FalseNone):
        """
        Initialize the Browser Isolation Manager.
        
        Args:
            session_base_dir (
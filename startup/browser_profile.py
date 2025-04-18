import time
import os
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from startup.session_isolation import BrowserIsolationManager

# Configure logger
logger = logging.getLogger(__name__)

# Default Travian server URL
LOGIN_URL = "https://ts1.x1.international.travian.com"

def setup_browser(user_id=None):
    """
    Set up a Chrome browser with proper configuration for Travian.
    
    Args:
        user_id (str, optional): User ID for session isolation
        
    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance
    """
    try:
        # Configure Chrome options
        chrome_options = Options()
        
        # Essential settings for stability
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        
        # Important for Travian - enable JavaScript and cookies
        chrome_options.add_argument("--enable-javascript")
        chrome_options.add_experimental_option("excludeSwitches", ["disable-popup-blocking"])
        
        # Add user agent to appear as a regular browser
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        # If running in headless mode (no UI)
        # chrome_options.add_argument("--headless")
        
        # Enable logging
        chrome_options.add_argument("--enable-logging")
        chrome_options.add_argument("--log-level=0")  # INFO level
        
        # Session isolation if user_id is provided
        if user_id:
            # Create user data directory if session isolation is needed
            user_data_dir = f"selenium_profiles/{user_id}"
            os.makedirs(user_data_dir, exist_ok=True)
            chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
        
        # Create and return the driver
        driver = webdriver.Chrome(options=chrome_options)
        
        # Set page load timeout (30 seconds)
        driver.set_page_load_timeout(30)
        
        # Add certain cookies that might be needed for Travian
        return driver
        
    except Exception as e:
        logger.error(f"Error setting up browser: {str(e)}")
        return None

def login(driver, username, password, server_url=None):
    """
    Logs in with the provided credentials and returns True if successful.
    
    Args:
        driver (webdriver.Chrome): Chrome WebDriver instance
        username (str): Travian username
        password (str): Travian password
        server_url (str, optional): Travian server URL, defaults to LOGIN_URL
    
    Returns:
        bool: True if login was successful, False otherwise
    """
    # Use the provided server URL or default
    url = server_url if server_url else LOGIN_URL
    
    try:
        logger.info(f"Navigating to login page: {url}")
        driver.get(url)
        time.sleep(3)
        
        # Wait for username field
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "name")))
        
        # Enter credentials
        driver.find_element(By.NAME, "name").send_keys(username)
        driver.find_element(By.NAME, "password").send_keys(password)
        
        # Submit login form
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        time.sleep(5)
        
        # Debug information
        logger.debug(f"Current page URL after login: {driver.current_url}")
        
        # Check for CAPTCHA
        try:
            captcha_element = driver.find_element(By.CLASS_NAME, "recaptcha-checkbox")
            logger.warning("CAPTCHA detected! Please solve it manually.")
            
            # In automated settings, we might need to handle this differently
            # For now, we'll assume manual intervention is possible
            input("Press Enter after solving CAPTCHA...")
        except:
            logger.info("No CAPTCHA detected.")
        
        # Wait for successful login (topBar presence indicates logged in state)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "topBar")))
        
        logger.info("Logged in successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Login failed: {e}")
        return False

def update_profile(driver, profile_path="info/profile/tribe.txt"):
    """
    Navigates to the profile edit page, clicks the Overview tab,
    waits for the URL to update (e.g. .../profile/4662), and extracts the tribe.
    Saves tribe & profile ID to 'info/profile/tribe.txt' if confirmed.
    
    Args:
        driver (webdriver.Chrome): Chrome WebDriver instance
        profile_path (str, optional): Path to save profile information
        
    Returns:
        tuple: (detected_tribe, profile_id) if successful, else None
    """
    profile_edit_url = "https://ts1.x1.international.travian.com/profile/edit"
    logger.info("Navigating to the profile edit page for profile update...")
    
    try:
        driver.get(profile_edit_url)

        # Click the "Overview" tab
        try:
            overview_tab = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//a[@data-tab='1' and contains(.,'Overview')]"))
            )
            overview_tab.click()
        except Exception as e:
            logger.error(f"Could not click Overview tab: {e}")
            return None

        # Wait until the URL changes to .../profile/xxxx
        try:
            WebDriverWait(driver, 10).until(lambda d: "/profile/" in d.current_url and d.current_url != profile_edit_url)
            current_url = driver.current_url
            logger.info(f"Redirected URL: {current_url}")
            profile_id = current_url.rstrip("/").split("/")[-1]
        except Exception as e:
            logger.error(f"Could not retrieve profile id from URL: {e}")
            profile_id = None

        # Detect tribe from the table
        try:
            tribe_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//tr[th[text()='Tribe']]/td"))
            )
            detected_tribe = tribe_element.text.strip()
            logger.info(f"Detected tribe: {detected_tribe}")
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(profile_path), exist_ok=True)
            
            # Save to file
            with open(profile_path, "w") as file:
                file.write(f"{detected_tribe},{profile_id}")
            logger.info("Tribe and profile ID saved.")
            
            return (detected_tribe, profile_id)
            
        except Exception as e:
            logger.error(f"Could not detect tribe: {e}")
            return None
            
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        return None

def check_for_captcha(driver):
    """
    Checks if a CAPTCHA is present on the current page.
    
    Args:
        driver (webdriver.Chrome): Chrome WebDriver instance
        
    Returns:
        bool: True if CAPTCHA detected, False otherwise
    """
    try:
        captcha_element = driver.find_element(By.CLASS_NAME, "recaptcha-checkbox")
        logger.warning("CAPTCHA detected!")
        return True
    except:
        return False

def check_for_ban(driver):
    """
    Checks if the current page indicates an account ban or IP ban.
    
    Args:
        driver (webdriver.Chrome): Chrome WebDriver instance
        
    Returns:
        tuple: (banned, reason) - banned is True if ban detected, reason contains details
    """
    # Common ban indicators in Travian
    ban_indicators = [
        "//div[contains(text(), 'banned')]",
        "//div[contains(text(), 'suspended')]",
        "//div[contains(text(), 'violation')]",
        "//div[contains(text(), 'account has been')]"
    ]
    
    for indicator in ban_indicators:
        try:
            element = driver.find_element(By.XPATH, indicator)
            if element:
                logger.critical(f"Ban detected: {element.text}")
                return (True, element.text)
        except:
            pass
    
    # Check for unusual redirects that might indicate IP blocking
    if "blocked" in driver.current_url or "ban" in driver.current_url:
        logger.critical(f"Ban detected from URL: {driver.current_url}")
        return (True, f"Banned URL: {driver.current_url}")
    
    return (False, None)

def handle_detection_event(driver, user_id, event_type, context=None):
    """
    Handles detection events such as CAPTCHA or potential bans.
    
    Args:
        driver (webdriver.Chrome): Chrome WebDriver instance
        user_id (str): User ID
        event_type (str): Type of event ('captcha', 'ban', 'suspicious')
        context (dict, optional): Additional context about the event
        
    Returns:
        dict: Action taken to handle the event
    """
    if not user_id:
        logger.warning(f"Detection event ({event_type}) but no user_id provided")
        return {"action": "none", "message": "No user ID provided"}
    
    # Initialize isolation manager
    isolation_manager = BrowserIsolationManager()
    
    # Determine risk level based on event type
    risk_level = "low"
    if event_type == "captcha":
        risk_level = "medium"
    elif event_type == "ban" or event_type == "ip_block":
        risk_level = "high"
    elif event_type == "suspicious":
        risk_level = "medium"
    
    # Handle the detection risk
    result = isolation_manager.handle_detection_risk(user_id, risk_level, context)
    
    # If action requires browser restart, we should inform the caller
    if result["action"] in ["session_rotation", "full_rotation"]:
        result["requires_restart"] = True
    
    return result

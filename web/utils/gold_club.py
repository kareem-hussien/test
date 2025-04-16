"""
Gold Club membership verification utility module.
This file should be placed in web/utils/gold_club.py
"""
import logging
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Initialize logger
logger = logging.getLogger(__name__)

def verify_gold_club_membership(username, password, server_url):
    """
    Verify if a user is a Gold Club member by checking cropfinder.php.
    
    Args:
        username (str): Travian username
        password (str): Travian password
        server_url (str): Travian server URL
        
    Returns:
        dict: Result dictionary with keys 'success', 'is_gold_member', and 'message'
    """
    driver = None
    
    try:
        logger.info(f"Starting Gold Club verification for user {username}")
        
        # Ensure server URL has protocol
        if not server_url.startswith(('http://', 'https://')):
            server_url = f"https://{server_url}"
            
        # Configure Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Initialize the WebDriver
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(30)
        except Exception as e:
            logger.error(f"Error initializing Chrome driver: {e}")
            return {
                'success': False,
                'is_gold_member': False,
                'message': f"Error initializing browser: {str(e)}"
            }
        
        # Login to Travian
        try:
            logger.info(f"Logging in to Travian at {server_url}")
            
            # Navigate to login page
            driver.get(server_url)
            time.sleep(2)
            
            # Check if we need to navigate to login page
            if "login" not in driver.current_url.lower():
                try:
                    # Try to find and click login link
                    login_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'login')]")
                    if login_links:
                        login_links[0].click()
                        time.sleep(2)
                    else:
                        # Direct navigation as fallback
                        driver.get(f"{server_url}/login.php")
                        time.sleep(2)
                except:
                    # Direct navigation as fallback
                    driver.get(f"{server_url}/login.php")
                    time.sleep(2)
            
            # Find and fill login form
            username_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "name"))
            )
            password_field = driver.find_element(By.NAME, "password")
            
            # Enter credentials
            username_field.clear()
            username_field.send_keys(username)
            password_field.clear()
            password_field.send_keys(password)
            
            # Submit form
            submit_buttons = driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
            if submit_buttons:
                submit_buttons[0].click()
            else:
                # Try alternate button locators
                alt_buttons = driver.find_elements(By.XPATH, "//button[contains(.,'Login') or contains(.,'Sign in')]")
                if alt_buttons:
                    alt_buttons[0].click()
                else:
                    # Last resort - try by form submission
                    form = driver.find_element(By.TAG_NAME, "form")
                    if form:
                        form.submit()
            
            # Wait for login to complete
            time.sleep(3)
            
            # Check if login was successful
            login_successful = False
            
            try:
                # Check for elements that indicate successful login
                WebDriverWait(driver, 10).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.ID, "navigation")),
                        EC.presence_of_element_located((By.ID, "resources")),
                        EC.presence_of_element_located((By.CLASS_NAME, "villageList")),
                        EC.presence_of_element_located((By.ID, "sidebarBoxVillagelist")),
                        EC.presence_of_element_located((By.ID, "village_map")),
                        EC.presence_of_element_located((By.ID, "villageNameField"))
                    )
                )
                login_successful = True
                logger.info(f"Successfully logged in to Travian account")
            except TimeoutException:
                logger.warning(f"Login timeout for user {username}")
                return {
                    'success': False,
                    'is_gold_member': False,
                    'message': "Login timeout. Please check your credentials and try again."
                }
            
            if not login_successful:
                logger.warning(f"Login failed for user {username}")
                return {
                    'success': False,
                    'is_gold_member': False,
                    'message': "Login failed. Please check your credentials and try again."
                }
                
            # Navigate to cropfinder.php (Gold Club exclusive page)
            logger.info(f"Navigating to cropfinder.php to check Gold Club membership")
            driver.get(f"{server_url}/cropfinder.php")
            time.sleep(3)
            
            # Check for Gold Club content
            try:
                # First check if the content element exists
                content_div = driver.find_element(By.ID, "content")
                
                # Get the HTML content
                content_html = content_div.get_attribute("innerHTML").strip()
                
                # Log first few characters of HTML content for debugging
                logger.info(f"Cropfinder content first 100 chars: {content_html[:100]}...")
                
                # Check if the content is meaningful
                # Gold Club members will have actual content in this element
                if content_html and len(content_html) > 50:
                    logger.info(f"Gold Club membership confirmed for user {username}")
                    return {
                        'success': True,
                        'is_gold_member': True,
                        'message': "Gold Club membership confirmed"
                    }
                else:
                    logger.info(f"User {username} is not a Gold Club member")
                    return {
                        'success': True,
                        'is_gold_member': False,
                        'message': "You are not a Gold Club member"
                    }
            except NoSuchElementException:
                # If content element doesn't exist, user is not Gold Club member
                logger.info(f"User {username} is not a Gold Club member (element not found)")
                return {
                    'success': True,
                    'is_gold_member': False,
                    'message': "You are not a Gold Club member"
                }
                
        except Exception as e:
            logger.error(f"Error during login or Gold Club verification: {e}")
            return {
                'success': False,
                'is_gold_member': False,
                'message': f"Error during verification: {str(e)}"
            }
            
    except Exception as e:
        logger.error(f"Unexpected error during Gold Club verification: {e}")
        return {
            'success': False,
            'is_gold_member': False,
            'message': f"Unexpected error: {str(e)}"
        }
    finally:
        # Close the browser
        if driver:
            driver.quit()
            logger.info("Closed browser")

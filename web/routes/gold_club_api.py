"""
Gold Club membership verification API for Travian Whispers.
This module provides an API endpoint to verify Gold Club membership.
"""
import logging
import time
from flask import Blueprint, request, jsonify, session
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from web.utils.decorators import login_required, api_error_handler
from database.models.user import User
from database.models.activity_log import ActivityLog

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
gold_club_api_bp = Blueprint('gold_club_api', __name__, url_prefix='/api/user')

@gold_club_api_bp.route('/verify-gold-club', methods=['POST'])
@api_error_handler
@login_required
def verify_gold_club_membership():
    """API endpoint to verify Gold Club membership."""
    # Get user data
    user_model = User()
    user = user_model.get_user_by_id(session['user_id'])
    
    if not user:
        return jsonify({
            'success': False,
            'message': 'User not found'
        }), 404
    
    # Get credentials from request
    data = request.get_json()
    logger.info(f"Received verify-gold-club request with data: {data}")
    
    username = data.get('username')
    password = data.get('password')
    server_url = data.get('server')
    
    # If password is null or empty, use existing password
    if not password or password == '********':
        password = user['travianCredentials'].get('password', '')
    
    # Validate inputs
    if not username:
        return jsonify({
            'success': False,
            'message': 'Username is required'
        }), 400
    
    if not password:
        return jsonify({
            'success': False,
            'message': 'Password is required'
        }), 400
    
    if not server_url:
        return jsonify({
            'success': False,
            'message': 'Server URL is required'
        }), 400
    
    # Ensure server URL has protocol
    if not server_url.startswith(('http://', 'https://')):
        server_url = f"https://{server_url}"
    
    logger.info(f"Verifying Gold Club membership for user {username} at server {server_url}")
    
    # Verify Gold Club membership
    try:
        is_gold_club_member = check_gold_club_membership(username, password, server_url)
        
        # Log the activity
        activity_model = ActivityLog()
        if is_gold_club_member:
            activity_model.log_activity(
                user_id=session['user_id'],
                activity_type='gold-club-verification',
                details='Gold Club membership verified successfully',
                status='success'
            )
            
            # Update user's travian credentials with gold club status
            user_model.update_user(session['user_id'], {
                'travianCredentials.gold_club_member': True
            })
            
            logger.info(f"Gold Club membership verified for user {username}")
            return jsonify({
                'success': True,
                'message': 'Gold Club membership verified successfully'
            })
        else:
            activity_model.log_activity(
                user_id=session['user_id'],
                activity_type='gold-club-verification',
                details='Gold Club membership verification failed',
                status='warning'
            )
            
            # Update user's travian credentials with gold club status
            user_model.update_user(session['user_id'], {
                'travianCredentials.gold_club_member': False
            })
            
            logger.info(f"User {username} is not a Gold Club member")
            return jsonify({
                'success': False,
                'message': 'You are not a Gold Club member'
            })
    except Exception as e:
        logger.error(f"Error verifying Gold Club membership: {e}")
        
        # Log the error
        activity_model = ActivityLog()
        activity_model.log_activity(
            user_id=session['user_id'],
            activity_type='gold-club-verification',
            details=f"Error verifying Gold Club membership: {str(e)}",
            status='error'
        )
        
        return jsonify({
            'success': False,
            'message': f"Error verifying Gold Club membership: {str(e)}"
        }), 500

def check_gold_club_membership(username, password, server_url):
    """
    Check if the user is a Gold Club member by navigating to the cropfinder.php page.
    
    Args:
        username (str): Travian username
        password (str): Travian password
        server_url (str): Travian server URL
        
    Returns:
        bool: True if user is a Gold Club member, False otherwise
    """
    driver = None
    try:
        logger.info("Setting up WebDriver for Gold Club verification")
        # Configure Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Initialize the WebDriver
        try:
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            
            logger.info("Using ChromeDriverManager to setup WebDriver")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            logger.warning(f"Error with ChromeDriverManager: {e}, trying direct Chrome initialization")
            driver = webdriver.Chrome(options=chrome_options)
        
        # Set page load timeout
        driver.set_page_load_timeout(30)
        
        # Log navigation start
        logger.info(f"Navigating to server URL: {server_url}")
        
        # Navigate to login page
        driver.get(server_url)
        time.sleep(2)
        
        # Check if we're redirected to a login page
        if "login" not in driver.current_url.lower() and "dorf1.php" not in driver.current_url.lower():
            # Navigate to the login page
            try:
                logger.info("Looking for login link")
                login_link = driver.find_element(By.XPATH, "//a[contains(@href, 'login.php')]")
                login_link.click()
                time.sleep(2)
            except NoSuchElementException:
                # If we can't find a login link, try direct login URL
                logger.info("Login link not found, navigating directly to login.php")
                driver.get(f"{server_url}/login.php")
                time.sleep(2)
        
        # Locate username and password fields
        try:
            logger.info("Looking for login form elements")
            username_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "name"))
            )
            password_field = driver.find_element(By.NAME, "password")
            
            # Enter credentials
            logger.info("Entering credentials")
            username_field.send_keys(username)
            password_field.send_keys(password)
            
            # Find and click the login button
            login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
            login_button.click()
            
            # Wait for login to complete
            logger.info("Waiting for login to complete")
            WebDriverWait(driver, 10).until(
                lambda d: "dorf1.php" in d.current_url or 
                           "village" in d.current_url or 
                           "game.php" in d.current_url
            )
            
            # Check if login was successful
            if "dorf1.php" in driver.current_url or "village" in driver.current_url or "game.php" in driver.current_url:
                logger.info(f"Successfully logged in to Travian account for {username}")
                
                # Navigate to cropfinder.php
                cropfinder_url = f"{server_url}/cropfinder.php"
                logger.info(f"Navigating to cropfinder: {cropfinder_url}")
                driver.get(cropfinder_url)
                time.sleep(3)
                
                # Check if content div has any children
                try:
                    logger.info("Looking for cropfinder content div")
                    content_div = driver.find_element(By.CSS_SELECTOR, "div.contentContainer div#content.cropfinder")
                    
                    # Log the HTML content for debugging
                    html_content = content_div.get_attribute("innerHTML").strip()
                    logger.info(f"Cropfinder content HTML: {html_content[:100]}...")  # Log first 100 chars
                    
                    # Check if the content div is empty
                    if html_content:
                        logger.info(f"User {username} is a Gold Club member, content found")
                        return True
                    else:
                        logger.info(f"User {username} is not a Gold Club member, content div is empty")
                        return False
                except NoSuchElementException:
                    logger.warning(f"Cropfinder content div not found for user {username}")
                    return False
            else:
                logger.warning(f"Login failed for user {username}")
                return False
        except Exception as e:
            logger.error(f"Error during login or verification: {e}")
            return False
    finally:
        # Clean up browser
        if driver:
            logger.info("Closing WebDriver")
            driver.quit()

def register_routes(app):
    """Register Gold Club API routes with the application."""
    logger.info("Registering Gold Club API routes")
    app.register_blueprint(gold_club_api_bp)

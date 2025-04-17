"""
Gold Club membership verification utility module.
This file should be placed in web/utils/gold_club.py
"""
import logging

# Initialize logger
logger = logging.getLogger(__name__)

def check_gold_club_membership(driver):
    """
    Check if a user is a Gold Club member by checking cropfinder.php content.
    
    Args:
        driver: WebDriver instance that's already logged in
        
    Returns:
        bool: True if user is a Gold Club member, False otherwise
    """
    try:
        logger.info("Checking Gold Club membership")
        
        # Navigate to cropfinder.php (Gold Club exclusive page)
        driver.get(driver.current_url.split('/dorf1.php')[0] + '/cropfinder.php')
        
        # Wait for page to load
        import time
        time.sleep(3)
        
        # Check for Gold Club content
        from selenium.webdriver.common.by import By
        from selenium.common.exceptions import NoSuchElementException
        
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
                logger.info("Gold Club membership confirmed")
                return True
            else:
                logger.info("User is not a Gold Club member")
                return False
        except NoSuchElementException:
            # If content element doesn't exist, user is not Gold Club member
            logger.info("User is not a Gold Club member (element not found)")
            return False
            
    except Exception as e:
        logger.error(f"Error during Gold Club verification: {e}")
        return False
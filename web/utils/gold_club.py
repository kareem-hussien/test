"""
Utility for checking Gold Club membership in Travian.
This module provides functions to verify if a user has Gold Club membership.
"""
import logging
import re
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Initialize logger
logger = logging.getLogger(__name__)

def check_gold_club_membership(driver):
    """
    Check if the user has Gold Club membership in Travian.
    
    Args:
        driver (WebDriver): Selenium WebDriver instance that is logged into Travian
        
    Returns:
        bool: True if the user has Gold Club membership, False otherwise
    """
    try:
        logger.info("Checking for Gold Club membership")
        
        # Method 1: Look for Gold Club membership indicator in the menu
        try:
            # Try to find Gold Club in the left sidebar menu
            gold_menu = driver.find_elements(By.XPATH, "//a[contains(@href, 'goldclub')]")
            if gold_menu:
                for menu_item in gold_menu:
                    # If we find a gold menu with class indicating active
                    if "active" in menu_item.get_attribute("class") or "opened" in menu_item.get_attribute("class"):
                        logger.info("Found active Gold Club menu item - user is a Gold Club member")
                        return True
        except Exception as e:
            logger.debug(f"Error checking gold menu: {e}")
        
        # Method 2: Look for Gold Club icon in header
        try:
            gold_icons = driver.find_elements(By.CSS_SELECTOR, ".gold, .premium-icon, img[src*='gold']")
            if gold_icons:
                for icon in gold_icons:
                    # Check if the icon is not part of a "buy gold" button
                    parent_text = icon.find_element(By.XPATH, "..").text.lower()
                    if not ("buy" in parent_text or "purchase" in parent_text):
                        logger.info("Found Gold Club icon - user is a Gold Club member")
                        return True
        except Exception as e:
            logger.debug(f"Error checking gold icons: {e}")
        
        # Method 3: Navigate to Profile page and check for Gold Club indicators
        try:
            # Store current URL to return to it
            current_url = driver.current_url
            
            # Navigate to profile page
            profile_link = driver.find_element(By.XPATH, "//a[contains(@href, 'profile')]")
            profile_link.click()
            
            # Wait for page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Check for Gold Club indicators on profile page
            page_source = driver.page_source.lower()
            gold_phrases = ["gold club", "goldclub", "premium account", "gold member"]
            
            for phrase in gold_phrases:
                if phrase in page_source:
                    logger.info(f"Found Gold Club indicator on profile page: '{phrase}'")
                    
                    # Return to original page
                    driver.get(current_url)
                    return True
            
            # Return to original page
            driver.get(current_url)
        except Exception as e:
            logger.debug(f"Error checking profile page: {e}")
            # Try to return to original page if available
            try:
                if current_url:
                    driver.get(current_url)
            except:
                pass
        
        # Method 4: Try to check if Farm List feature is available
        # (Gold Club usually includes access to Farm List feature)
        try:
            farm_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'farm') or contains(@href, 'list')]")
            if farm_links:
                for link in farm_links:
                    link_text = link.text.lower()
                    if "farm" in link_text and "list" in link_text:
                        logger.info("Found Farm List feature - user likely has Gold Club")
                        return True
        except Exception as e:
            logger.debug(f"Error checking farm list: {e}")
        
        # If we've tried all methods and found no evidence of Gold Club
        logger.info("No Gold Club indicators found - user is not a Gold Club member")
        return False
        
    except Exception as e:
        logger.error(f"Error checking Gold Club membership: {e}")
        return False

def has_farm_list_feature(driver):
    """
    Check if the user has access to the Farm List feature, which requires Gold Club.
    
    Args:
        driver (WebDriver): Selenium WebDriver instance that is logged into Travian
        
    Returns:
        bool: True if the Farm List feature is available, False otherwise
    """
    try:
        logger.info("Checking for Farm List feature")
        
        # Store current URL
        current_url = driver.current_url
        
        # Look for Farm List link in the menu
        farm_list_links = driver.find_elements(By.XPATH, 
            "//a[contains(@href, 'farmList') or (contains(text(), 'Farm') and contains(text(), 'List'))]")
        
        if farm_list_links:
            # Try to navigate to the Farm List page
            farm_list_links[0].click()
            
            # Wait for page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Check if we're on the Farm List page
            try:
                # Look for elements that indicate Farm List page
                farm_elements = driver.find_elements(By.XPATH, 
                    "//*[contains(text(), 'Farm List') or contains(@class, 'farmList')]")
                
                if farm_elements:
                    logger.info("Farm List feature is available - user has Gold Club")
                    
                    # Return to original page
                    driver.get(current_url)
                    return True
            except Exception as e:
                logger.debug(f"Error checking farm list page: {e}")
            
            # Return to original page
            driver.get(current_url)
        
        logger.info("Farm List feature not available - user likely doesn't have Gold Club")
        return False
        
    except Exception as e:
        logger.error(f"Error checking Farm List feature: {e}")
        
        # Try to return to original page if available
        try:
            if current_url:
                driver.get(current_url)
        except:
            pass
            
        return False
    
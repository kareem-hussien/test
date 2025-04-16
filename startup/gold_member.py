import time
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def check_gold_club_membership(driver):
    """
    Prompts the user whether they are a Gold Club member.
    If yes, checks the content of the specific URL.
    Returns True if the user is a Gold Club member, False otherwise.
    """
    user_input = input("Are you a Gold Club member? (yes/no): ").strip().lower()
    if user_input not in ["y", "yes"]:
        logging.info("User indicated they are not a Gold Club member.")
        return False

    # Navigate to the Cropfinder page and check the content
    url = "https://ts6.x1.international.travian.com/cropfinder.php"
    driver.get(url)
    time.sleep(3)  # Wait for the page to load
    
    try:
        content_div = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "content"))
        )
        content_text = content_div.text.strip()

        if content_text == "":
            logging.info("You are not a Gold Club member.")
            return False
        else:
            logging.info("Gold Club membership confirmed.")
            return True
    except Exception as e:
        logging.error(f"Error checking Gold Club membership: {e}")
        return False

def save_gold_member_status(is_gold_member, file_path):
    """
    Saves the Gold Club membership status (yes or no) to a text file.
    """
    status = "Gold Club member" if is_gold_member else "Not a Gold Club member"
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(status + "\n")
        logging.info(f"Gold Club membership status saved to {file_path}")
    except Exception as e:
        logging.error(f"Error saving Gold Club membership status: {e}")

def run_gold_member_check(driver):
    """
    Runs the Gold Club membership check and saves the result to a file.
    """
    logging.info("Starting Gold Club membership check...")
    
    is_gold_member = check_gold_club_membership(driver)
    save_gold_member_status(is_gold_member, "info/profile/gold_member.txt")
    
    logging.info("Gold Club membership check completed.")

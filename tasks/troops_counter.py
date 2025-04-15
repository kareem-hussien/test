import time
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def navigate_to_troops_page(driver):
    """
    Navigates to the troops statistics page.
    """
    url = "https://ts1.x1.international.travian.com/village/statistics/troops"
    driver.get(url)
    time.sleep(3)

def scrape_troops(driver):
    """
    Scrapes the troops data per village from the troops statistics page.
    Returns a list of dictionaries. Each dictionary contains:
        - village_name: the name of the village,
        - newdid: the ID extracted from the link,
        - troops: a dictionary mapping each unit name to its count.
    """
    villages = []
    try:
        # Wait for the table with id "troops" to load.
        table = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "troops"))
        )
        
        # Get unit names from the header row (skip the first cell which is "Village").
        header_images = table.find_elements(By.CSS_SELECTOR, "thead tr td.unit img")
        unit_names = []
        for img in header_images:
            alt_text = img.get_attribute("alt")
            if alt_text:
                unit_names.append(alt_text.strip())
        
        # Locate the tbody that contains village rows.
        tbody = table.find_element(By.TAG_NAME, "tbody")
        rows = tbody.find_elements(By.TAG_NAME, "tr")
        
        for row in rows:
            row_class = row.get_attribute("class")
            if "sum" in row_class or "empty" in row_class:
                continue  # Skip aggregate or empty rows.
            
            cells = row.find_elements(By.TAG_NAME, "td")
            # Expect number of cells to be at least 1 (village name) + len(unit_names)
            if len(cells) < 1 + len(unit_names):
                continue

            # Extract village name and newdid from the first cell.
            try:
                village_cell = cells[0]
                anchor = village_cell.find_element(By.TAG_NAME, "a")
                village_name = anchor.text.strip()
                href = anchor.get_attribute("href")
                # Extract newdid from href assuming pattern ...newdid=XYZ&...
                newdid = ""
                if "newdid=" in href:
                    newdid = href.split("newdid=")[1].split("&")[0]
            except Exception as e:
                logging.error(f"Error extracting village name or newdid: {e}")
                continue
            
            # Extract troop counts from remaining cells
            troops = {}
            for i, unit in enumerate(unit_names):
                try:
                    cell = cells[i + 1]
                    count_text = cell.text.strip()
                    # Handle the case when text is empty or "none"
                    if not count_text or count_text.lower() == "none":
                        count = 0
                    else:
                        count = int(count_text.replace(',', ''))
                except Exception as e:
                    logging.error(f"Error parsing troop count for unit {unit}: {e}")
                    count = 0
                troops[unit] = count
            
            village_info = {
                "village_name": village_name,
                "newdid": newdid,
                "troops": troops
            }
            villages.append(village_info)
    except Exception as e:
        logging.error(f"Error while scraping village troop data: {e}")
    return villages

def save_troop_count(villages_data, file_path):
    """
    Exports the troop counts per village to a text file.
    Each line in the file contains the village name, newdid and its troops dictionary.
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            for village in villages_data:
                line = (f"Village: {village['village_name']}, newdid: {village['newdid']}, "
                        f"Troops: {village['troops']}\n")
                f.write(line)
        logging.info(f"Troop count exported to {file_path}")
    except Exception as e:
        logging.error(f"Error saving troop count: {e}")

def run_troops_counter(driver):
    """
    Main function for the Troops Counter feature.
    1. Asks the user to confirm they have a Travian Plus account.
    2. If confirmed, navigates to the troops statistics page, scrapes per-village troop data,
       and writes the data to a text file.
    """
    logging.info("Starting Troops Counter process...")

    user_input = input("This feature requires a Travian Plus account. Do you have a Plus account? (y/n): ").strip().lower()
    if user_input not in ["y", "yes"]:
        logging.info("User indicated they do not have a Plus account. Skipping troops count update.")
        return

    navigate_to_troops_page(driver)
    villages_data = scrape_troops(driver)

    if not villages_data:
        logging.warning("No village troop data found. The exported file will be empty.")
    else:
        logging.info(f"Scraped data for {len(villages_data)} villages.")

    save_troop_count(villages_data, "info/profile/troops_count.txt")
    logging.info("Troops counter process completed.")

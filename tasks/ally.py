import re
import logging
import json
import time
import os
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

class AllyTask:
    """
    AllyTask performs the following actions:
      1. Uses Selenium to click the alliance link on the main page; if active, it scrapes 
         alliance details (from a table with class 'transparent details') and exports them to 
         info/ally/ally_info.txt.
      2. Navigates to the statistics page and processes the "Military strength rank" panel 
         (ID "militaryStrengthRank"). It extracts for both Offensive and Defensive tabs:
             - Game world rank and Alliance rank (from the .ServerAllianceRank block)
             - The villages list (village name and strength points) from the table with class "villageList transparent"
         The resulting data are stored under keys:
             OffensiveWorldRank, OffensiveAllyRank, OffensiveVillages,
             DefensiveWorldRank, DefensiveAllyRank, DefensiveVillages,
         and exported to the file specified by stats_output_file.
      3. After exporting the stats data, the task reads the villages profile file from 
         info/profile/villages_list.txt (a CSV‑like text file with each line having:
         village_name,newdid,x,y).
         Then, it compares the village names in the stats data with those in the profile file.
         For any matching village (ignoring case), it copies over "newdid", "x", and "y" 
         from the profile into the corresponding stats record. The updated stats data is then
         re‑exported.
      4. After finishing all processing, the task automatically redirects back to the tasks menu.
    """

    def __init__(self,
                 statistics_url="https://ts1.x1.international.travian.com/statistics/general",
                 alliance_output_file='info/ally/ally_info.txt',
                 stats_output_file='info/ally/militry.txt'):
        self.statistics_url = statistics_url
        self.alliance_output_file = alliance_output_file
        self.stats_output_file = stats_output_file

    def _parse_alliance_data(self, html):
        """
        Parse alliance data from the alliance page HTML.
        Expects a <table> with class 'transparent details'.
        Returns a dictionary of alliance information.
        """
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table', class_="transparent details")
        if not table:
            logging.warning("Alliance details table not found.")
            return None

        alliance_info = {}
        rows = table.find_all('tr')
        for row in rows:
            header = row.find('th')
            cells = row.find_all('td')
            if header and cells:
                key = header.get_text(strip=True).rstrip(':')
                value = " ".join(cell.get_text(strip=True) for cell in cells)
                alliance_info[key] = value
            elif len(row.find_all(['th', 'td'])) > 1:
                cells = row.find_all(['th', 'td'])
                key = cells[0].get_text(strip=True).rstrip(':')
                value = " ".join(cell.get_text(strip=True) for cell in cells[1:])
                alliance_info[key] = value
        return alliance_info

    def write_output(self, data, filename):
        """
        Write the provided data to a file in JSON format.
        Ensures the target directory exists before writing.
        """
        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            logging.info(f"Data successfully written to {filename}")
        except IOError as e:
            logging.error(f"Error writing to {filename}: {e}")

    def _parse_military_rank_data(self, container_html):
        """
        Given the inner HTML of the militaryStrengthRank container,
        parse out the Game world rank and Alliance rank from the .ServerAllianceRank element.
        Returns: (world_rank, alliance_rank) as integers or (None, None) if parsing fails.
        """
        soup = BeautifulSoup(container_html, "html.parser")
        rank_div = soup.select_one(".ServerAllianceRank")
        if not rank_div:
            return None, None

        wrappers = rank_div.find_all("div", class_="typeWrapper")
        if len(wrappers) < 2:
            return None, None

        def parse_rank(div_elem):
            if not div_elem:
                return None
            txt = div_elem.get_text(strip=True)
            txt = re.sub(r'[\u202D\u202C]', '', txt)  # Remove directional characters
            txt = txt.replace(",", "")                # Remove commas
            try:
                return int(txt)
            except ValueError:
                return None

        world_div = wrappers[0].find("div", class_="rankDisplay")
        alliance_div = wrappers[1].find("div", class_="rankDisplay")
        world_rank = parse_rank(world_div)
        alliance_rank = parse_rank(alliance_div)
        return world_rank, alliance_rank

    def _parse_villages_data(self, container_html):
        """
        Parse the villages list from the militaryStrengthRank container.
        Expects a table with class "villageList transparent" containing the villages data.
        Returns a list of dictionaries, each with keys: "name" and "points".
        """
        villages = []
        soup = BeautifulSoup(container_html, "html.parser")
        table = soup.find("table", class_="villageList transparent")
        if not table:
            logging.warning("Villages list table not found.")
            return villages

        tbody = table.find("tbody")
        if not tbody:
            return villages

        rows = tbody.find_all("tr")
        for row in rows:
            name_td = row.find("td", class_="name")
            strength_td = row.find("td", class_="strength")
            if name_td and strength_td:
                name = name_td.get_text(strip=True)
                strength_text = strength_td.get_text(strip=True)
                strength_text = re.sub(r'[\u202D\u202C]', '', strength_text).replace(",", "")
                try:
                    points = int(strength_text)
                except ValueError:
                    points = None
                villages.append({"name": name, "points": points})
        return villages

    def scrape_military_strength_rank(self, driver):
        """
        Navigate to the statistics page, ensure the "Military strength rank" panel is open,
        and extract rank data and villages list for both Offensive and Defensive tabs.
        Returns a dictionary with the following keys:
            - OffensiveWorldRank, OffensiveAllyRank, OffensiveVillages
            - DefensiveWorldRank, DefensiveAllyRank, DefensiveVillages
        """
        stats_data = {
            "OffensiveWorldRank": None,
            "OffensiveAllyRank": None,
            "OffensiveVillages": [],
            "DefensiveWorldRank": None,
            "DefensiveAllyRank": None,
            "DefensiveVillages": []
        }

        # Navigate to the statistics page
        driver.get(self.statistics_url)
        time.sleep(3)  # Allow the page to load

        try:
            # Locate the Military strength rank container by its ID
            military_div = driver.find_element(By.ID, "militaryStrengthRank")

            # If collapsed, click the toggle to open it
            try:
                toggle = military_div.find_element(By.CSS_SELECTOR, ".openedClosedSwitch")
                if "switchOpened" not in toggle.get_attribute("class"):
                    toggle.click()
                    time.sleep(2)
            except Exception as e:
                logging.warning(f"Could not toggle Military Strength Rank section: {e}")

            # Find the Offensive and Defensive tabs within this container
            tabs = military_div.find_elements(By.CSS_SELECTOR, ".legendTabs .tab")
            offensive_tab = None
            defensive_tab = None
            for tab in tabs:
                tab_text = tab.text.strip().lower()
                if "offensive" in tab_text:
                    offensive_tab = tab
                elif "defensive" in tab_text:
                    defensive_tab = tab

            # Helper function: click a tab and extract its rank and villages data
            def click_and_extract_tab_data(tab_element):
                tab_element.click()
                time.sleep(2)  # Allow content to update
                inner_html = military_div.get_attribute("innerHTML")
                world_rank, alliance_rank = self._parse_military_rank_data(inner_html)
                villages = self._parse_villages_data(inner_html)
                return world_rank, alliance_rank, villages

            # Extract Offensive data
            if offensive_tab:
                off_world, off_ally, off_villages = click_and_extract_tab_data(offensive_tab)
                stats_data["OffensiveWorldRank"] = off_world
                stats_data["OffensiveAllyRank"] = off_ally
                stats_data["OffensiveVillages"] = off_villages
                logging.info(f"Offensive: World {off_world}, Alliance {off_ally}, Villages: {off_villages}")
            else:
                logging.warning("Offensive tab not found in Military Strength Rank section.")

            # Extract Defensive data
            if defensive_tab:
                def_world, def_ally, def_villages = click_and_extract_tab_data(defensive_tab)
                stats_data["DefensiveWorldRank"] = def_world
                stats_data["DefensiveAllyRank"] = def_ally
                stats_data["DefensiveVillages"] = def_villages
                logging.info(f"Defensive: World {def_world}, Alliance {def_ally}, Villages: {def_villages}")
            else:
                logging.warning("Defensive tab not found in Military Strength Rank section.")

        except Exception as e:
            logging.error(f"Error scraping Military Strength Rank data: {e}")

        return stats_data

    def merge_villages_profile(self, stats_data):
        """
        Reads the villages profile file (info/profile/villages_list.txt), which is in CSV format,
        and compares the village names with those in stats_data ("OffensiveVillages" and "DefensiveVillages").
        For a matching name (case-insensitive), copies over "newdid", "x", and "y" into the respective village record.
        The villages profile file is expected to have lines of the format:
            village_name,newdid,x,y
        """
        profile_file = "info/profile/villages_list.txt"
        try:
            # Check if file exists and is non-empty
            if not os.path.exists(profile_file) or os.path.getsize(profile_file) == 0:
                logging.warning("Profile file is missing or empty; skipping merge of villages profile data.")
                return stats_data

            # Read and parse CSV lines from the profile file
            profile_data = []
            with open(profile_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Split the line by comma into at least 4 parts
                parts = line.split(',')
                if len(parts) < 4:
                    continue
                record = {
                    "name": parts[0].strip(),
                    "newdid": parts[1].strip(),
                    "x": parts[2].strip(),
                    "y": parts[3].strip()
                }
                profile_data.append(record)
            
            # Create a lookup dictionary from village name (lowercase) to profile record
            profile_lookup = { entry["name"].lower(): entry for entry in profile_data if "name" in entry }

            # Function to update a village record with profile info
            def update_village(village):
                name = village.get("name", "").lower()
                if name in profile_lookup:
                    prof = profile_lookup[name]
                    village["newdid"] = prof.get("newdid")
                    village["x"] = prof.get("x")
                    village["y"] = prof.get("y")
                return village

            for key in ["OffensiveVillages", "DefensiveVillages"]:
                updated_list = []
                for village in stats_data.get(key, []):
                    updated_list.append(update_village(village))
                stats_data[key] = updated_list

            logging.info("Villages profile data merged successfully.")
        except Exception as e:
            logging.error(f"Error merging villages profile data: {e}")
        return stats_data

    def run(self, driver):
        """
        Execute the AllyTask:
          1. Use Selenium to click the alliance link on the main page; if available,
             parse and export alliance details.
          2. Navigate to the statistics page and scrape the "Military strength rank" panel,
             extracting both Offensive and Defensive rank data along with villages list.
          3. Export both alliance data and statistics data to their respective output files.
          4. Merge the villages profile data (from info/profile/villages_list.txt) into the stats data,
             then update the stats file.
          5. After finishing, redirect back to the tasks menu.
        
        Returns:
            Tuple (alliance_data, stats_data)
        """
        logging.info("Starting AllyTask...")

        # --- Step 1: Process alliance page ---
        alliance_data = None
        try:
            alliance_link = driver.find_element(By.CSS_SELECTOR, 
                "a.layoutButton.buttonFramed.withIcon.round.alliance.green")
            if alliance_link.is_enabled():
                logging.info("Alliance link is active. Clicking the alliance button.")
                alliance_link.click()
                time.sleep(3)  # Wait for the alliance page to load
                alliance_html = driver.page_source
                alliance_data = self._parse_alliance_data(alliance_html)
                if alliance_data:
                    logging.info("Alliance data scraped successfully.")
                    self.write_output(alliance_data, self.alliance_output_file)
                else:
                    logging.error("Failed to scrape alliance data from the alliance page.")
            else:
                print("You are not in alliance")
                logging.info("Alliance link is inactive. User is not in alliance.")
        except Exception as e:
            print("You are not in alliance")
            logging.error(f"Alliance link element error: {e}")

        # --- Step 2: Process Military Strength Rank section ---
        stats_data = {}
        try:
            stats_data = self.scrape_military_strength_rank(driver)
            if any(val is not None for val in stats_data.values()):
                logging.info("Military Strength Rank data scraped successfully.")
                self.write_output(stats_data, self.stats_output_file)
            else:
                logging.error("Failed to scrape any Military Strength Rank data.")
        except Exception as ex:
            logging.error(f"Error navigating to statistics page: {ex}")

        # --- Step 3: Merge villages profile data ---
        try:
            stats_data = self.merge_villages_profile(stats_data)
            # Update the stats file with merged data
            self.write_output(stats_data, self.stats_output_file)
        except Exception as e:
            logging.error(f"Error merging villages profile data: {e}")

        # --- Step 4: Redirect to Tasks List ---
        try:
            from startup.tasks import run_task_menu
            logging.info("Redirecting to tasks list...")
            run_task_menu(driver)
        except Exception as e:
            logging.error(f"Error redirecting to tasks list: {e}")

        return alliance_data, stats_data

# For direct testing:
if __name__ == "__main__":
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service as ChromeService
    from webdriver_manager.chrome import ChromeDriverManager

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()))
    driver.get("https://ts1.x1.international.travian.com/")
    task = AllyTask()
    alliance_data, stats_data = task.run(driver)
    print("Alliance Data:", alliance_data)
    print("Military Strength Rank Data:", stats_data)
    driver.quit()

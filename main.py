import toml
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from playsound import playsound
import random
import json

# --- Configuration ---

def load_config(filename="config.toml"):
    """Loads configuration from a TOML file."""
    try:
        with open(filename, 'r') as f:
            return toml.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file '{filename}' not found.")
        exit(1)

# --- Web Scraping ---

def setup_driver():
    """Sets up the Selenium WebDriver."""
    options = webdriver.ChromeOptions()
    #options.add_argument("--headless")
    options.add_argument("--log-level=3")
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def fetch_html(driver, url):
    """Fetches HTML content from a URL using Selenium."""
    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "tr.selling"))
        )
        return driver.page_source
    except TimeoutException:
        return None
    except Exception as e:
        return None

def _strip_recursive(obj):
    """Recursively strips whitespace from keys and values in a dictionary."""
    if isinstance(obj, dict):
        return {k.strip(): _strip_recursive(v.strip() if isinstance(v, str) else v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_strip_recursive(i) for i in obj]
    return obj

def parse_listings(html: str):
    """
    Parses HTML to find listings.
    """
    if not html:
        return []

    prices = []
    soup = BeautifulSoup(html, 'html.parser')
    
    listings_table = soup.find('table', class_='list_tb')
    if not listings_table:
        return []
        
    selling_rows = listings_table.find_all('tr', class_='selling')
    
    for row in selling_rows:
        goods_info_str = row.get('data-goods-info')
        if goods_info_str:
            # Clean up the string for JSON parsing
            cleaned_str = goods_info_str.replace('&quot;', '"').replace(';', '')
            try:
                data = json.loads(cleaned_str)
                stripped_data = _strip_recursive(data)
                
                if 'sell_min_price' in stripped_data:
                    prices.append(float(stripped_data['sell_min_price']))
            except (json.JSONDecodeError, ValueError, TypeError):
                # Ignore rows with invalid data
                continue
    
    return prices

# --- Sound ---

def play_alarm_sound(sound_file="ding.mp3"):
    """Plays an alarm sound."""
    try:
        playsound(sound_file)
    except Exception as e:
        # You might need to install platform-specific libraries for playsound
        # on Linux (e.g., pygobject).
        pass

# --- Console Display ---

def generate_layout(items_data, active_alarms):
    """Generates the layout for the console display."""
    layout = Layout()

    layout.split(
        Layout(name="main", ratio=1),
        Layout(size=len(active_alarms) + 4, name="footer")
    )

    # Main table
    table = Table(title="Buff Market Listings")
    table.add_column("Display Name", style="cyan", no_wrap=True)
    table.add_column("Lowest Price", style="magenta")
    table.add_column("Last Updated", style="green")

    for item in items_data:
        price_str = f"¥{item['lowest_price']:.2f}" if item['lowest_price'] is not None else "N/A"
        time_str = item['last_updated'].strftime("%H:%M:%S") if item['last_updated'] else "N/A"
        table.add_row(item['display_name'], price_str, time_str)
        
    layout["main"].update(Panel(table, border_style="bold blue"))

    # Active alarms
    alarm_str = ""
    if active_alarms:
        for alarm_item_name in sorted(list(active_alarms)):
            item_data = next((item for item in items_data if item["display_name"] == alarm_item_name), None)
            if item_data and item_data['lowest_price']:
                 alarm_str += f"[bold red] - {alarm_item_name}: ¥{item_data['lowest_price']:.2f}\n"

    layout["footer"].update(Panel(alarm_str, title="[bold red]Active Alarms", border_style="bold red"))
    
    return layout


# --- Main Application Logic ---

def main():
    """Main function to run the application."""
    config = load_config()
    console = Console()
    
    items_data = [
        {
            "display_name": item["display_name"],
            "url": item["url"],
            "alarm_price": item["alarm_price"],
            "lowest_price": None,
            "last_updated": None,
        }
        for item in config.get("items", [])
    ]
    
    active_alarms = set()

    console.print("Starting Buff Market watcher...", style="bold green")
    driver = setup_driver()

    try:
        with Live(generate_layout(items_data, active_alarms), console=console, screen=True, auto_refresh=False) as live:
            while True:
                for item in items_data:
                    html = fetch_html(driver, item["url"])
                    prices = parse_listings(html)
                    
                    if prices:
                        lowest_price = min(prices)
                        item["lowest_price"] = lowest_price
                        item["last_updated"] = datetime.now()

                        is_in_alarm = item['display_name'] in active_alarms
                        
                        if lowest_price <= item["alarm_price"]:
                            if not is_in_alarm:
                                play_alarm_sound()
                                active_alarms.add(item['display_name'])
                        else:
                            if is_in_alarm:
                                active_alarms.remove(item['display_name'])
                    
                    # Refresh display after each item update
                    live.update(generate_layout(items_data, active_alarms), refresh=True)

                # Wait for a bit before the next full refresh cycle
                time.sleep(10) # Refresh all items every 10 seconds
    finally:
        driver.quit()
        console.print("Watcher stopped.", style="bold red")

if __name__ == "__main__":
    main()

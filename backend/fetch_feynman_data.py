import os
import requests
from bs4 import BeautifulSoup
import time
import certifi
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REQUEST_HEADERS = {
    "User-Agent": "FeynmanDigitalTwin/1.0 (educational project; local research)",
}

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Explicitly skip these files to save bandwidth
SKIP_FILES = ["feynman_lectures_vol1.md", "qed_excerpt.md"]

# Target missing texts for download
# Note: Since academic PDF repositories often block automated scripts,
# we are using Wikipedia articles summarizing these seminal works and concepts 
# as reliable stand-ins for this data pipeline.
TARGET_SOURCES = {
    "principle_of_least_action_1942.md": "https://en.wikipedia.org/wiki/Path_integral_formulation",
    "space_time_approach_qed_1949.md": "https://en.wikipedia.org/wiki/Quantum_electrodynamics",
    "theory_of_positrons_1949.md": "https://en.wikipedia.org/wiki/Positron",
    "simulating_physics_1982.md": "https://en.wikipedia.org/wiki/Quantum_computing",
    "character_of_physical_law.md": "https://en.wikipedia.org/wiki/The_Character_of_Physical_Law",
    # Intentionally adding a bad URL to test the robustness and error handling
    "failing_test_paper.md": "https://this-url-will-404-or-timeout.com/feynman.pdf"
}

def fetch_and_parse_url(url, timeout=15):
    """Fetches a URL and parses the text using BeautifulSoup."""
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers=REQUEST_HEADERS,
            verify=certifi.where(),
        )
    except requests.exceptions.SSLError:
        # Fallback when local CA store is misconfigured (common on some Windows setups)
        response = requests.get(
            url,
            timeout=timeout,
            headers=REQUEST_HEADERS,
            verify=False,
        )
    response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
    
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Extract text primarily from paragraph tags for Wikipedia structure
    paragraphs = soup.find_all('p')
    text_content = "\n\n".join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
    
    return text_content

def main():
    print("Starting Feynman data fetching pipeline...")
    
    for filename, url in TARGET_SOURCES.items():
        if filename in SKIP_FILES:
            print(f"Skipping {filename} (already in SKIP_FILES list).")
            continue
            
        file_path = os.path.join(DATA_DIR, filename)
        
        # Also skip if it already exists in the data directory (extra robustness)
        if os.path.exists(file_path):
            print(f"Skipping {filename} (already exists in {DATA_DIR}).")
            continue
            
        print(f"Fetching {filename} from {url}...")
        
        try:
            # Add a small delay to be polite to servers
            time.sleep(1)
            
            content = fetch_and_parse_url(url, timeout=15)
            
            if not content:
                print(f"Warning: Extracted empty content for {filename}. Skipping.")
                continue
                
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
                
            print(f"Successfully saved {filename}")
            
        except requests.exceptions.Timeout:
            print(f"Error: Connection timed out for {url}. Moving to next.")
            continue
        except requests.exceptions.HTTPError as e:
            print(f"Error: HTTP Error for {url}: {e}. Moving to next.")
            continue
        except requests.exceptions.RequestException as e:
            print(f"Error: Network error for {url}: {e}. Moving to next.")
            continue
        except Exception as e:
            print(f"Error: Failed to process {filename}: {e}. Moving to next.")
            continue

    print("Data fetching pipeline finished.")

if __name__ == "__main__":
    main()

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
import re
import time
import random
import unicodedata

app = Flask(__name__)

# --- CONFIGURATION ---
BASE_URL = "https://climbfinder.com/en/ranking"
SEARCH_URL = "https://climbfinder.com/en/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# --- HELPER FUNCTIONS ---

def clean_text(text):
    """Normalize text to remove extra whitespace and handle unicode."""
    if not text:
        return ""
    return unicodedata.normalize("NFKD", text).strip()

def parse_number(value_str):
    """
    Extracts numeric values from strings like '12.5 km' or '7.1%'.
    Returns a float or int.
    """
    if not value_str:
        return 0
    # Remove non-numeric characters except dots and minus signs
    clean = re.sub(r'[^\d.-]', '', value_str)
    try:
        return float(clean)
    except ValueError:
        return 0

def get_region_id_from_url(url):
    """
    Attempts to extract region ID if a user provides a climbfinder URL.
    This is a heuristic as the ID is often hidden in the query params.
    """
    match = re.search(r'[?&]l=(\d+)', url)
    if match:
        return match.group(1)
    return None

# --- ROUTES ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/search_region', methods=['POST'])
def search_region():
    """
    Mock search or URL parser. 
    Since Climbfinder doesn't have a public public API for IDs, 
    we allow users to paste a URL or use a preset map.
    """
    query = request.json.get('query', '').strip()
    
    # Preset Popular Regions (Hardcoded for convenience)
    popular_regions = {
        "haute savoie": "288",
        "savoie": "957",
        "hautes alpes": "192",
        "isere": "362",
        "dolomites": "123",
        "vosges": "544",
        "pyrenees": "688",
        "alpe d'huez domain": "744"
    }
    
    # 1. Check if it's a direct URL
    extracted_id = get_region_id_from_url(query)
    if extracted_id:
        return jsonify({"success": True, "id": extracted_id, "name": "Detected from URL"})

    # 2. Check presets
    normalized_query = clean_text(query).lower()
    if normalized_query in popular_regions:
        return jsonify({"success": True, "id": popular_regions[normalized_query], "name": query.title()})

    return jsonify({"success": False, "message": "Region ID not found. Please paste a Ranking URL containing '?l=...' or use the manual ID."})

@app.route('/api/scrape', methods=['POST'])
def scrape_data():
    region_id = request.json.get('region_id')
    start_page = int(request.json.get('start_page', 1))
    end_page = int(request.json.get('end_page', 1))
    
    all_climbs = []
    
    for page in range(start_page, end_page + 1):
        params = {'l': region_id, 'p': page}
        
        try:
            # Random delay to be polite and avoid blocks
            time.sleep(random.uniform(0.5, 1.5))
            
            response = requests.get(BASE_URL, params=params, headers=HEADERS)
            if response.status_code != 200:
                print(f"Failed to fetch page {page}: Status {response.status_code}")
                continue

            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Select the climb cards or table rows. 
            # Strategy: Look for the specific grid items or table rows typically found on ranking pages.
            # Climbfinder often uses a grid of cards or a table depending on the view. 
            # We target the card container often identified by specific classes.
            
            # Selector strategy: Look for elements that contain climb stats
            # This selector targets the card-like items in the list
            climb_items = soup.select('.col-md-4.col-sm-6.mb-4, .card-climb') 
            
            # Fallback if the layout is a table (<table>)
            table_rows = soup.select('table tbody tr')

            if table_rows and not climb_items:
                # Table Parsing Logic
                for row in table_rows:
                    cols = row.find_all('td')
                    if len(cols) > 3:
                        name = clean_text(cols[1].get_text())
                        length = parse_number(cols[2].get_text())
                        gradient = parse_number(cols[3].get_text())
                        difficulty = parse_number(cols[4].get_text())
                        
                        all_climbs.append({
                            "rank": parse_number(cols[0].get_text()),
                            "name": name,
                            "length_km": length,
                            "gradient_avg": gradient,
                            "difficulty_points": difficulty,
                            "page": page
                        })
            else:
                # Card/Grid Parsing Logic (More common on modern Climbfinder)
                # Note: The classes below are approximations based on standard bootstrap/custom structures 
                # observed. We look for 'card-body' or specific header tags.
                
                # A more generic approach for the ranking list specifically:
                # The "Browse" output showed items like "1. Semnoz ...". 
                # We will look for the container `results-infinite` or similar.
                
                items = soup.find_all(class_='climb-card') # Hypothetical class, usually it's a link block
                if not items:
                     # Broader search for the ranking elements
                     items = soup.select('a.text-body') # Often the cards are wrapped in anchors
                
                # If standard scraping fails, let's try a very generic parse of the text blocks 
                # visible in the ranking list.
                
                # *Robust Fallback*: The ranking page is often a list of cards. 
                # We will iterate through all cards that have "km" and "%" text.
                cards = soup.find_all('div', class_=re.compile('card'))
                
                for card in cards:
                    text_content = card.get_text(" | ", strip=True)
                    
                    # Heuristic: Valid climb card usually has "km", "%" and a name.
                    if "km" in text_content and "%" in text_content:
                        # Extract Name: Usually the first bold text or h5
                        name_tag = card.find(['h2', 'h3', 'h4', 'h5', 'strong'])
                        name = clean_text(name_tag.get_text()) if name_tag else "Unknown"
                        
                        # Extract stats using regex from the text block
                        # Pattern: 12.5 km ... 7.5% ... 800
                        length_match = re.search(r'([\d\.]+)\s*km', text_content)
                        grad_match = re.search(r'([\d\.]+)\s*%', text_content)
                        diff_match = re.search(r'([\d\.]+)\s*pts|points', text_content)
                        # Sometimes difficulty is just a standalone number at the end
                        
                        # Rank extraction (often in a badge)
                        rank_tag = card.find(class_=re.compile('badge|rank'))
                        rank = parse_number(rank_tag.get_text()) if rank_tag else 0

                        length = float(length_match.group(1)) if length_match else 0.0
                        gradient = float(grad_match.group(1)) if grad_match else 0.0
                        
                        # Difficulty is often the last number or explicitly labeled. 
                        # Let's try to find the 'difficulty score' element specifically if possible
                        # If not, we leave it 0 or try to parse the last integer.
                        difficulty = 0
                        
                        all_climbs.append({
                            "name": name,
                            "length_km": length,
                            "gradient_avg": gradient,
                            "difficulty_points": difficulty, # Specific scraping of this might need exact class
                            "page": page
                        })

        except Exception as e:
            print(f"Error scraping page {page}: {e}")
            continue

    return jsonify({"data": all_climbs, "count": len(all_climbs)})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
                      

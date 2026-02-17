import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import random
import unicodedata
from io import BytesIO

# --- CONFIGURATIE ---
st.set_page_config(page_title="Climbfinder Scraper", page_icon="🚲", layout="wide")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# --- HULPFUNCTIES ---
def clean_text(text):
    if not text: return ""
    return unicodedata.normalize("NFKD", text).strip()

def extract_number(text, pattern):
    match = re.search(pattern, text)
    if match:
        return float(match.group(1))
    return 0.0

def get_region_id(url_input):
    match = re.search(r'[?&]l=(\d+)', url_input)
    if match:
        return match.group(1)
    if url_input.isdigit():
        return url_input
    return None

def is_valid_name(text):
    """Check of de tekst een geldige naam kan zijn (geen afstand/stats)"""
    if not text: return False
    text = text.strip()
    if len(text) < 3: return False
    # Mag niet beginnen met een cijfer
    if text[0].isdigit(): return False
    # Mag geen 'km' of '%' bevatten als los woord
    if "km" in text.lower() or "%" in text: return False
    # Filter teksten als 'your best attempt'
    if "attempt" in text.lower() or "poging" in text.lower(): return False
    return True

# --- SCRAPER LOGICA ---
def scrape_data(region_id, start_p, end_p):
    all_climbs = []
    base_url = "https://climbfinder.com/en/ranking"
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_pages = end_p - start_p + 1

    for idx, page in enumerate(range(start_p, end_p + 1)):
        status_text.text(f"Scraping pagina {page} van {end_p}...")
        params = {'l': region_id, 'p': page, 's': 'popular'}
        
        try:
            time.sleep(random.uniform(0.5, 1.2))
            response = requests.get(base_url, params=params, headers=HEADERS)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Zoek elementen die op kaarten lijken
            cards = soup.find_all('div', class_=lambda x: x and 'card' in x)
            if not cards: cards = soup.find_all('a', class_=lambda x: x and 'card' in x)
            if not cards: cards = soup.select('.list-group-item')
            if not cards: cards = soup.select('tr') 

            for card in cards:
                full_text = card.get_text(" | ", strip=True)
                
                # Check of er data in zit
                if "km" not in full_text: continue

                # --- 1. NAAM ZOEKEN (STRIKT) ---
                name = "Unknown"
                
                # A. Probeer headers
                headers = card.find_all(['h2', 'h3', 'h4', 'strong', 'b', 'a'])
                for h in headers:
                    cand = h.get_text(strip=True)
                    if is_valid_name(cand):
                        name = cand
                        break
                
                # B. Probeer Image Alt
                if name == "Unknown":
                    img = card.find('img')
                    if img and img.get('alt'):
                        cand = img.get('alt').replace(" profile", "").replace(" profiel", "")
                        if is_valid_name(cand):
                            name = cand

                # C. Probeer tekst te splitsen
                if name == "Unknown":
                    parts = full_text.split("|")
                    for part in parts:
                        if is_valid_name(part):
                            name = part
                            break
                
                if name == "Unknown": continue

                # --- 2. STATS EXTRACTIE ---
                length = extract_number(full_text, r'(\d+\.?\d*)\s*km')
                gradient = extract_number(full_text, r'(\d+\.?\d*)\s*%')
                elevation = int(length * gradient * 10)
                
                # --- 3. DIFFICULTY ---
                difficulty = 0
                numbers = re.findall(r'\b\d+\b', full_text)
                if numbers:
                    candidates = []
                    for n in numbers:
                        val = float(n)
                        if val > 20 and val != length and val != gradient:
                            candidates.append(val)
                    if candidates: difficulty = int(max(candidates))

                all_climbs.append({
                    "Naam": name,
                    "Afstand (km)": length,
                    "Steiging (%)": gradient,
                    "Hoogtemeters (m)": elevation,
                    "Punten": difficulty,
                    "Pagina": page
                })
            
        except Exception as e:
            st.error(f"Fout op pagina {page}: {e}")
        
        progress_bar.progress((idx + 1) / total_pages)

    status_text.empty()
    progress_bar.empty()
    return pd.DataFrame(all_climbs)

# --- UI WEERGAVE ---
st.title("🚲 Climbfinder Aggregator")
st.markdown("Download ranglijsten direct naar Excel.")

with st.sidebar:
    st.header("Instellingen")
    url_input = st.text_input("Climbfinder URL / ID", value="288")
    col1, col2 = st.columns(2)
    with col1: start_p = st.number_input("Van Pagina", 1, 100, 1)
    with col2: end_p = st.number_input("Tot Pagina", 1, 100, 2)
    scrape_btn = st.button("Start Scraping", type="primary", use_container_width=True)

if scrape_btn:
    region_id = get_region_id(url_input)
    if not region_id:
        st.error("❌ Geen geldig ID.")
    else:
        st.success(f"Regio {region_id} gevonden. Bezig met ophalen...")
        df = scrape_data(region_id, start_p, end_p)
        
        if not df.empty:
            st.write(f"### 🎉 {len(df)} Beklimmingen")
            
            # HIER IS DE WIJZIGING: hide_index=True
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Knoppen voor download
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Climbs')
            
            st.download_button("📥 Download Excel", buf, f"climbfinder_{region_id}.xlsx", "application/vnd.ms-excel", use_container_width=True)
        else:
            st.warning("Geen data gevonden.")
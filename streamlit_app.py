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

# --- FUNCTIES ---
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

def scrape_data(region_id, start_p, end_p):
    all_climbs = []
    base_url = "https://climbfinder.com/en/ranking"
    
    # Progress bar setup
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_pages = end_p - start_p + 1

    for idx, page in enumerate(range(start_p, end_p + 1)):
        status_text.text(f"Scraping pagina {page} van {end_p}...")
        params = {'l': region_id, 'p': page, 's': 'popular'}
        
        try:
            time.sleep(random.uniform(0.5, 1.2)) # Beleefde pauze
            response = requests.get(base_url, params=params, headers=HEADERS)
            
            if response.status_code != 200:
                st.warning(f"Pagina {page} overgeslagen (Status: {response.status_code})")
                continue

            soup = BeautifulSoup(response.content, 'html.parser')
            
            # --- SELECTOR STRATEGIE ---
            # We zoeken breed naar elementen die op een kaart lijken
            cards = soup.find_all('div', class_=lambda x: x and 'card' in x)
            if not cards: cards = soup.find_all('a', class_=lambda x: x and 'card' in x)
            if not cards: cards = soup.select('.list-group-item')

            page_climbs = 0
            for card in cards:
                full_text = card.get_text(" | ", strip=True)
                
                # Check of het data bevat
                if "km" not in full_text or "%" not in full_text:
                    continue

                # 1. Naam Extractie
                name = "Unknown"
                img = card.find('img')
                if img and img.get('alt'):
                    name = img.get('alt').replace(" profile", "").replace(" profiel", "")
                
                if name == "Unknown":
                    header = card.find(['h2', 'h3', 'h4', 'strong', 'b'])
                    if header: name = header.get_text(strip=True)
                
                if name == "Unknown" and "|" in full_text:
                    name = full_text.split("|")[0].strip()

                # 2. Getallen
                length = extract_number(full_text, r'(\d+\.?\d*)\s*km')
                gradient = extract_number(full_text, r'(\d+\.?\d*)\s*%')
                
                # 3. Berekeningen
                # Hoogtemeters = km * 10 * % (Is een goede benadering als data mist)
                elevation = int(length * gradient * 10)
                
                # 4. Difficulty Points (Gok op basis van max getal)
                difficulty = 0
                numbers = re.findall(r'\b\d+\b', full_text)
                if numbers:
                    candidates = []
                    for n in numbers:
                        n_float = float(n)
                        # Punten zijn vaak hoger dan 20, en niet gelijk aan afstand/perc
                        if n_float > 20 and n_float != length and n_float != gradient:
                            candidates.append(n_float)
                    if candidates: difficulty = int(max(candidates))

                if length > 0:
                    all_climbs.append({
                        "Naam": name,
                        "Afstand (km)": length,
                        "Steiging (%)": gradient,
                        "Hoogtemeters (m)": elevation,
                        "Punten": difficulty,
                        "Pagina": page
                    })
                    page_climbs += 1
            
        except Exception as e:
            st.error(f"Fout op pagina {page}: {e}")
        
        # Update balk
        progress_bar.progress((idx + 1) / total_pages)

    status_text.empty()
    progress_bar.empty()
    return pd.DataFrame(all_climbs)

# --- UI LAYOUT ---
st.title("🚲 Climbfinder Aggregator")
st.markdown("Download ranglijsten direct naar Excel.")

# Sidebar Input
with st.sidebar:
    st.header("Instellingen")
    url_input = st.text_input("Climbfinder URL / ID", 
                              value="288",
                              help="Plak de URL (met ?l=...) of vul het ID in (bv. 288 voor Haute Savoie).")
    
    col1, col2 = st.columns(2)
    with col1:
        start_p = st.number_input("Van Pagina", 1, 100, 1)
    with col2:
        end_p = st.number_input("Tot Pagina", 1, 100, 2)
    
    scrape_btn = st.button("Start Scraping", type="primary", use_container_width=True)

# Main Area
if scrape_btn:
    region_id = get_region_id(url_input)
    
    if not region_id:
        st.error("❌ Geen geldig Regio ID gevonden. Controleer de URL.")
    else:
        st.success(f"Regio {region_id} gevonden. Bezig met ophalen...")
        
        df = scrape_data(region_id, start_p, end_p)
        
        if not df.empty:
            st.write(f"### 🎉 {len(df)} Beklimmingen Gevonden")
            st.dataframe(df, use_container_width=True)
            
            # --- DOWNLOAD KNOPPEN ---
            col_d1, col_d2 = st.columns(2)
            
            # Excel Logic
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Climbs')
                
            with col_d1:
                st.download_button(
                    label="📥 Download Excel",
                    data=buffer,
                    file_name=f"climbfinder_{region_id}.xlsx",
                    mime="application/vnd.ms-excel",
                    use_container_width=True
                )
                
            # CSV Logic
            csv = df.to_csv(index=False).encode('utf-8')
            with col_d2:
                st.download_button(
                    label="📄 Download CSV",
                    data=csv,
                    file_name=f"climbfinder_{region_id}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        else:
            st.warning("Geen data gevonden. Misschien zijn er geen beklimmingen op deze pagina's?")
      

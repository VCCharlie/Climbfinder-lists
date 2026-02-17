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
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_pages = end_p - start_p + 1

    for idx, page in enumerate(range(start_p, end_p + 1)):
        status_text.text(f"Scraping pagina {page} van {end_p}...")
        params = {'l': region_id, 'p': page, 's': 'popular'}
        
        try:
            time.sleep(random.uniform(0.5, 1.2))
            response = requests.get(base_url, params=params, headers=HEADERS)
            
            if response.status_code != 200:
                st.warning(f"Pagina {page} overgeslagen (Status: {response.status_code})")
                continue

            soup = BeautifulSoup(response.content, 'html.parser')
            
            # --- STRATEGIE 1: TABEL (Meest waarschijnlijk op rankings) ---
            rows = soup.select('table tbody tr')
            
            # --- STRATEGIE 2: KAARTEN (Fallback) ---
            cards = []
            if not rows:
                cards = soup.find_all('div', class_=lambda x: x and 'card' in x)
                if not cards: cards = soup.select('.list-group-item')

            # --- VERWERKEN TABEL ---
            if rows:
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 3: continue
                    
                    # Kolom 2 is meestal de naam (index 1), Kolom 3 afstand (index 2), etc.
                    # We zoeken de <a> tag in de naam-kolom voor de schoonste tekst
                    name_col = cols[1]
                    link = name_col.find('a')
                    name = link.get_text(strip=True) if link else name_col.get_text(strip=True)
                    
                    # Als naam leeg is of rare tekst bevat
                    if not name or name[0].isdigit():
                        # Probeer image alt
                        img = name_col.find('img')
                        if img and img.get('alt'):
                             name = img.get('alt').replace(" profile", "")

                    full_row_text = row.get_text(" ", strip=True)
                    
                    length = extract_number(full_row_text, r'(\d+\.?\d*)\s*km')
                    gradient = extract_number(full_row_text, r'(\d+\.?\d*)\s*%')
                    
                    # Difficulty uit laatste kolom proberen te halen
                    difficulty = 0
                    try:
                        # Zoek laatste getal in de rij
                        numbers = re.findall(r'\b\d+\b', full_row_text)
                        if numbers:
                             # Pak grootste getal dat geen afstand/perc is
                             candidates = [float(n) for n in numbers if float(n) > 20 and float(n) != length]
                             if candidates: difficulty = int(max(candidates))
                    except: pass
                    
                    elevation = int(length * gradient * 10)
                    
                    all_climbs.append({
                        "Naam": name,
                        "Afstand (km)": length,
                        "Steiging (%)": gradient,
                        "Hoogtemeters (m)": elevation,
                        "Punten": difficulty,
                        "Pagina": page
                    })

            # --- VERWERKEN KAARTEN (Als er geen tabel is) ---
            elif cards:
                for card in cards:
                    full_text = card.get_text(" | ", strip=True)
                    if "km" not in full_text: continue

                    # Naam Extractie (Verbeterd)
                    name = "Unknown"
                    
                    # 1. Zoek naar specifieke titels
                    header = card.find(['h2', 'h3', 'h4', 'strong', 'b', 'a'])
                    if header:
                         # Filter "Your best attempt" en dat soort teksten eruit
                         candidate = header.get_text(strip=True)
                         if "attempt" not in candidate.lower() and not candidate[0].isdigit():
                             name = candidate
                    
                    # 2. Image alt fallback
                    if name == "Unknown":
                        img = card.find('img')
                        if img and img.get('alt'):
                            name = img.get('alt').replace(" profile", "")

                    # 3. Text split fallback (maar filter nummers)
                    if name == "Unknown":
                        parts = full_text.split("|")
                        for part in parts:
                            clean_part = part.strip()
                            # Pak het eerste stuk dat geen getal is en geen 'km' heeft
                            if clean_part and not clean_part[0].isdigit() and "km" not in clean_part:
                                name = clean_part
                                break

                    length = extract_number(full_text, r'(\d+\.?\d*)\s*km')
                    gradient = extract_number(full_text, r'(\d+\.?\d*)\s*%')
                    elevation = int(length * gradient * 10)
                    
                    difficulty = 0
                    numbers = re.findall(r'\b\d+\b', full_text)
                    if numbers:
                        candidates = [float(n) for n in numbers if float(n) > 20 and float(n) != length]
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
            
            col_d1, col_d2 = st.columns(2)
            
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Climbs')
                
            with col_d1:
                st.download_button("📥 Download Excel", buffer, f"climbfinder_{region_id}.xlsx", "application/vnd.ms-excel", use_container_width=True)
                
            csv = df.to_csv(index=False).encode('utf-8')
            with col_d2:
                st.download_button("📄 Download CSV", csv, f"climbfinder_{region_id}.csv", "text/csv", use_container_width=True)
        else:
            st.warning("Geen data gevonden. Check of de regio correct is.")

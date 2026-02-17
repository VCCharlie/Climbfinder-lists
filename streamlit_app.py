import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import io
import json

# ---------------------------------------------------------------------------
# CONFIGURATIE & REGIO'S
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Climbfinder Aggregator", page_icon="🚲", layout="wide")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Populaire regio's mapping (ingekort voor overzicht, werkt hetzelfde)
REGIONS_BY_COUNTRY = {
    "France": [
        {"name": "Haute-Savoie", "id": 288}, {"name": "Savoie", "id": 957},
        {"name": "Hautes-Alpes", "id": 192}, {"name": "Isère", "id": 291},
        {"name": "Drôme", "id": 292}, {"name": "Vosges", "id": 295},
        {"name": "Pyrenees (All)", "id": 688}, {"name": "Provence", "id": 380}
    ],
    "Italy": [
        {"name": "Dolomites", "id": 123}, {"name": "Bormio / Stelvio", "id": 318},
        {"name": "Aosta Valley", "id": 317}, {"name": "Tuscany", "id": 325}
    ],
    "Spain": [
        {"name": "Mallorca", "id": 153}, {"name": "Tenerife", "id": 156},
        {"name": "Costa Blanca", "id": 157}, {"name": "Girona", "id": 163}
    ],
    "Netherlands": [
        {"name": "Limburg", "id": 233}, {"name": "Gelderland", "id": 230}
    ],
    "Belgium": [
        {"name": "Ardennes", "id": 239}, {"name": "Flemish Ardennes", "id": 244}
    ]
}

ALL_REGIONS = []
for country, regions in REGIONS_BY_COUNTRY.items():
    for r in regions:
        ALL_REGIONS.append({"country": country, "name": r["name"], "id": r["id"],
                            "label": f"{r['name']}, {country}"})
ALL_REGIONS.sort(key=lambda x: x["label"])

# ---------------------------------------------------------------------------
# HULPFUNCTIES (PARSING LOGICA)
# ---------------------------------------------------------------------------

def extract_number(text, pattern):
    """Haalt een getal uit tekst op basis van regex patroon."""
    if not text: return 0.0
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1).replace(',', '.'))
        except:
            return 0.0
    return 0.0

def calculate_elevation(length_km, gradient_pct):
    """Berekent hoogtemeters: km * 10 * %"""
    if length_km and gradient_pct:
        return int(length_km * gradient_pct * 10)
    return 0

def parse_html_content(html, page_number):
    """Slimme parser die zowel tabellen als kaarten aankan."""
    soup = BeautifulSoup(html, "html.parser")
    climbs = []

    # Zoek naar rijen in een tabel OF kaarten (cards)
    # Climbfinder gebruikt soms <tr> en soms <div class="card">
    items = soup.select('table tbody tr')
    if not items:
        items = soup.find_all('div', class_=lambda x: x and 'card' in x)
    if not items:
        items = soup.select('.list-group-item')

    for item in items:
        full_text = item.get_text(" ", strip=True)
        
        # Basis validatie: moet 'km' en '%' bevatten
        if "km" not in full_text.lower() or "%" not in full_text:
            continue

        # --- 1. NAAM EXTRACTIE ---
        name = "Unknown"
        # Probeer link tekst (meest betrouwbaar)
        link = item.find('a')
        if link:
            name_candidate = link.get_text(strip=True)
            # Filter rare teksten
            if len(name_candidate) > 2 and not name_candidate[0].isdigit():
                name = name_candidate
        
        # Fallback: Image alt text
        if name == "Unknown":
            img = item.find('img')
            if img and img.get('alt'):
                name = img.get('alt').replace(" profile", "").replace(" profiel", "")
        
        # Fallback: Headers
        if name == "Unknown":
            header = item.find(['h2', 'h3', 'h4', 'strong'])
            if header: name = header.get_text(strip=True)

        if name == "Unknown" or "attempt" in name.lower():
            # Laatste redmiddel: splitten op pipe |
            parts = full_text.split('|')
            if parts: name = parts[0].strip()

        # --- 2. DATA EXTRACTIE (REGEX) ---
        # Dit lost het probleem op van verschuivende kolommen
        length_km = extract_number(full_text, r'(\d+\.?\d*)\s*km')
        gradient_pct = extract_number(full_text, r'(\d+\.?\d*)\s*%')
        
        # --- 3. DIFFICULTY EXTRACTIE ---
        # Punten zijn vaak een groot geheel getal, dat GEEN lengte of percentage is.
        # We zoeken alle getallen in de tekst.
        difficulty = 0
        all_numbers = re.findall(r'\b\d+\b', full_text)
        
        candidates = []
        for n in all_numbers:
            val = float(n)
            # Filter logica:
            # - Moet groter zijn dan 20 (om kleine percentages/afstanden uit te sluiten)
            # - Mag niet exact gelijk zijn aan de lengte (soms staat lengte er 2x in)
            # - Mag niet het jaartal zijn (bv 2026)
            if val > 20 and val < 3000 and val != length_km:
                candidates.append(int(val))
        
        if candidates:
            difficulty = max(candidates) # De punten zijn meestal het hoogste getal

        # --- 4. HOOGTEMETERS ---
        elevation = calculate_elevation(length_km, gradient_pct)

        climbs.append({
            "Climb Name": name,
            "Length (km)": length_km,
            "Avg Gradient (%)": gradient_pct,
            "Difficulty Points": difficulty,
            "Elev. Gain (m)": elevation,
            "Page": page_number
        })

    return climbs

def scrape_page_requests(region_id, page):
    url = f"https://climbfinder.com/en/ranking?l={region_id}&p={page}&s=popular"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://climbfinder.com/"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return parse_html_content(r.text, page), None
        return [], f"Status {r.status_code}"
    except Exception as e:
        return [], str(e)

# ---------------------------------------------------------------------------
# STREAMLIT UI
# ---------------------------------------------------------------------------
st.title("Climbfinder Ranking Aggregator")
st.markdown("Haal klimgegevens op, inclusief **berekende hoogtemeters**.")

# --- SIDEBAR ---
with st.sidebar:
    st.header("Instellingen")
    
    # Regio Kiezer
    country = st.selectbox("Land", ["Alles"] + sorted(REGIONS_BY_COUNTRY.keys()))
    if country == "Alles":
        opts = ALL_REGIONS
    else:
        opts = [r for r in ALL_REGIONS if r["country"] == country]
    
    selected_region = st.selectbox("Kies Regio", opts, format_func=lambda x: x['label'])
    
    st.markdown("---")
    custom_id = st.text_input("Of vul Regio ID in", value=str(selected_region['id']) if selected_region else "")
    
    col1, col2 = st.columns(2)
    start_p = col1.number_input("Start Pagina", 1, 100, 1)
    end_p = col2.number_input("Eind Pagina", 1, 100, 1) # Default 1 pagina voor test
    
    btn = st.button("Start Scraping", type="primary", use_container_width=True)

# --- HOOFDSCHERM ---
if btn:
    rid = custom_id if custom_id else str(selected_region['id'])
    
    st.info(f"Bezig met ophalen Regio {rid} (Pagina {start_p} t/m {end_p})...")
    
    all_data = []
    progress = st.progress(0)
    total = end_p - start_p + 1
    
    for i, p in enumerate(range(start_p, end_p + 1)):
        data, err = scrape_page_requests(rid, p)
        if data:
            all_data.extend(data)
        elif err:
            st.error(f"Fout op pagina {p}: {err}")
        
        progress.progress((i + 1) / total)
        time.sleep(0.5) # Even wachten om server niet te boos te maken
    
    progress.empty()
    
    if all_data:
        df = pd.DataFrame(all_data)
        
        # Zorg dat kolommen in de juiste volgorde staan
        cols = ["Climb Name", "Length (km)", "Avg Gradient (%)", "Difficulty Points", "Elev. Gain (m)", "Page"]
        df = df[cols]
        
        st.success(f"Klaar! **{len(df)}** beklimmingen gevonden.")
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Download Knoppen
        c1, c2 = st.columns(2)
        
        # Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name="Climbs")
        c1.download_button("📥 Download Excel", buffer, "climbs.xlsx", "application/vnd.ms-excel", use_container_width=True)
        
        # CSV
        csv = df.to_csv(index=False).encode('utf-8')
        c2.download_button("📄 Download CSV", csv, "climbs.csv", "text/csv", use_container_width=True)
        
    else:
        st.warning("Geen data gevonden. Controleer het ID.")
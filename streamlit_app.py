import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import io
import unicodedata

# ---------------------------------------------------------------------------
# CONFIGURATIE
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Climbfinder Aggregator", page_icon="🚲", layout="wide")

# Headers om een echte browser te simuleren
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://climbfinder.com/"
}

# Regio mapping (idem als voorheen)
REGIONS_BY_COUNTRY = {
    "France": [
        {"name": "Haute-Savoie", "id": 288}, {"name": "Savoie", "id": 957},
        {"name": "Hautes-Alpes", "id": 192}, {"name": "Alpes-de-Haute-Provence", "id": 290},
        {"name": "Alpes-Maritimes", "id": 379}, {"name": "Isère", "id": 291},
        {"name": "Drôme", "id": 292}, {"name": "Vosges", "id": 295},
        {"name": "Pyrénées-Atlantiques", "id": 186}, {"name": "Hautes-Pyrénées", "id": 187},
        {"name": "Pyrénées-Orientales", "id": 188}, {"name": "Ariège", "id": 189},
        {"name": "Haute-Garonne", "id": 190}, {"name": "Aude", "id": 191},
        {"name": "Hérault", "id": 193}, {"name": "Gard", "id": 194},
        {"name": "Ardèche", "id": 195}, {"name": "Loire", "id": 196},
        {"name": "Puy-de-Dôme", "id": 197}, {"name": "Cantal", "id": 198},
        {"name": "Aveyron", "id": 199}, {"name": "Lozère", "id": 200},
        {"name": "Var", "id": 380}, {"name": "Vaucluse", "id": 381},
        {"name": "Bouches-du-Rhône", "id": 382}, {"name": "Ain", "id": 293},
        {"name": "Jura", "id": 294}, {"name": "Doubs", "id": 296},
        {"name": "Bas-Rhin", "id": 297}, {"name": "Haut-Rhin", "id": 298},
        {"name": "Corse-du-Sud", "id": 383}, {"name": "Haute-Corse", "id": 384},
    ],
    "Italy": [
        {"name": "Dolomites", "id": 123}, {"name": "Aosta Valley", "id": 317},
        {"name": "Lombardy", "id": 318}, {"name": "Piedmont", "id": 319},
        {"name": "Trentino", "id": 320}, {"name": "South Tyrol (Alto Adige)", "id": 321},
        {"name": "Veneto", "id": 322}, {"name": "Friuli Venezia Giulia", "id": 323},
        {"name": "Liguria", "id": 324}, {"name": "Tuscany", "id": 325},
        {"name": "Emilia-Romagna", "id": 326}, {"name": "Lazio", "id": 327},
        {"name": "Sardinia", "id": 328}, {"name": "Sicily", "id": 329},
        {"name": "Campania", "id": 330},
    ],
    "Spain": [
        {"name": "Mallorca", "id": 153}, {"name": "Tenerife", "id": 156},
        {"name": "Catalonia", "id": 150}, {"name": "Andalusia", "id": 151},
        {"name": "Basque Country", "id": 152}, {"name": "Asturias", "id": 154},
        {"name": "Cantabria", "id": 155}, {"name": "Valencia", "id": 157},
        {"name": "Aragon", "id": 158}, {"name": "Navarra", "id": 159},
        {"name": "Castilla y León", "id": 160}, {"name": "Gran Canaria", "id": 161},
        {"name": "La Palma", "id": 162}, {"name": "Girona", "id": 163},
    ],
    "Netherlands": [
        {"name": "Limburg", "id": 233}, {"name": "Gelderland", "id": 230},
        {"name": "Utrecht", "id": 231}, {"name": "Overijssel", "id": 232},
        {"name": "North Brabant", "id": 234},
    ],
    "Belgium": [
        {"name": "Ardennes", "id": 239}, {"name": "Liège", "id": 240},
        {"name": "Namur", "id": 241}, {"name": "Luxembourg (BE)", "id": 242},
        {"name": "Hainaut", "id": 243}, {"name": "East Flanders", "id": 244},
        {"name": "West Flanders", "id": 245}, {"name": "Flemish Brabant", "id": 246},
        {"name": "Antwerp", "id": 247},
    ],
    "Switzerland": [
        {"name": "Valais", "id": 365}, {"name": "Graubünden", "id": 366},
        {"name": "Ticino", "id": 367}, {"name": "Bern", "id": 368},
        {"name": "Uri", "id": 369}, {"name": "Schwyz", "id": 370},
        {"name": "Lucerne", "id": 371}, {"name": "Vaud", "id": 372},
        {"name": "Fribourg", "id": 373}, {"name": "Glarus", "id": 374},
        {"name": "St. Gallen", "id": 375}, {"name": "Obwalden", "id": 376},
        {"name": "Nidwalden", "id": 377},
    ],
    "Austria": [
        {"name": "Tyrol", "id": 358}, {"name": "Salzburg", "id": 359},
        {"name": "Vorarlberg", "id": 360}, {"name": "Carinthia", "id": 361},
        {"name": "Styria", "id": 362}, {"name": "Upper Austria", "id": 363},
        {"name": "Lower Austria", "id": 364},
    ],
    "Germany": [
        {"name": "Bavaria", "id": 340}, {"name": "Baden-Württemberg", "id": 341},
        {"name": "Hesse", "id": 342}, {"name": "Rhineland-Palatinate", "id": 343},
        {"name": "Saarland", "id": 344}, {"name": "North Rhine-Westphalia", "id": 345},
        {"name": "Thuringia", "id": 346}, {"name": "Saxony", "id": 347},
    ],
    "United Kingdom": [
        {"name": "England", "id": 77}, {"name": "Wales", "id": 78},
        {"name": "Scotland", "id": 79}, {"name": "Yorkshire", "id": 80},
        {"name": "Lake District", "id": 81}, {"name": "Peak District", "id": 82},
        {"name": "Surrey Hills", "id": 83},
    ],
    "Portugal": [
        {"name": "Algarve", "id": 170}, {"name": "Serra da Estrela", "id": 171},
        {"name": "Minho", "id": 172}, {"name": "Madeira", "id": 173},
    ],
    "Andorra": [{"name": "Andorra", "id": 180}],
    "Slovenia": [{"name": "Slovenia", "id": 390}, {"name": "Julian Alps", "id": 391}],
    "Croatia": [{"name": "Croatia", "id": 395}],
    "Norway": [{"name": "Western Norway", "id": 400}, {"name": "Northern Norway", "id": 401}],
    "USA": [{"name": "California", "id": 410}, {"name": "Colorado", "id": 411}, {"name": "Utah", "id": 412}],
    "Colombia": [{"name": "Boyacá", "id": 420}, {"name": "Antioquia", "id": 421}],
}


ALL_REGIONS = []
for country, regions in REGIONS_BY_COUNTRY.items():
    for r in regions:
        ALL_REGIONS.append({"country": country, "name": r["name"], "id": r["id"],
                            "label": f"{r['name']}, {country}"})
ALL_REGIONS.sort(key=lambda x: x["label"])

# ---------------------------------------------------------------------------
# PARSING LOGICA (VERBETERD)
# ---------------------------------------------------------------------------

def extract_number(text, pattern):
    if not text: return 0.0
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1).replace(',', '.'))
        except:
            return 0.0
    return 0.0

def clean_name(text):
    """
    Maakt de naam schoon.
    Als tekst is: 'Col du Galibier 34.8km 6%', wordt het: 'Col du Galibier'
    """
    if not text: return "Unknown"
    
    # Stap 1: Normaliseer (verwijder rare tekens)
    text = unicodedata.normalize("NFKD", text).strip()
    
    # Stap 2: Alles voor het eerste getal pakken (als er een getal in staat)
    # Regex zoekt naar het eerste cijfer dat gevolgd wordt door een punt of spatie
    split_match = re.split(r'\d', text, maxsplit=1)
    if split_match:
        candidate = split_match[0].strip()
        # Als wat overblijft langer is dan 2 letters, is dat wss de naam
        if len(candidate) > 2:
            return candidate.strip(" -|")
            
    return text

def parse_html_content(html, page_number):
    soup = BeautifulSoup(html, "html.parser")
    climbs = []

    # Probeer specifieke items te vinden
    items = soup.find_all('div', class_=lambda x: x and 'card' in x)
    if not items: items = soup.select('.list-group-item')
    if not items: items = soup.select('tr') # Fallback voor tabellen

    for item in items:
        full_text = item.get_text(" ", strip=True)
        
        # Basischeck: Moet stats bevatten
        if "km" not in full_text.lower():
            continue

        # --- 1. NAAM EXTRACTIE (PRIORITEIT: AFBEELDING) ---
        name = "Unknown"
        
        # A. Check Alt tag van plaatje (Dit is de veiligste methode!)
        img = item.find('img')
        if img and img.get('alt'):
            raw_alt = img.get('alt')
            # Verwijder termen als 'profile' of 'profiel'
            name = re.sub(r'\s+profile|\s+profiel', '', raw_alt, flags=re.IGNORECASE).strip()

        # B. Als geen plaatje, zoek headers (h2, h3, h5, bold)
        if name == "Unknown":
            header = item.find(['h2', 'h3', 'h4', 'h5', 'strong', 'b'])
            if header:
                name = clean_name(header.get_text(strip=True))

        # C. Fallback: Als naam nog steeds "Unknown" is of op stats lijkt
        if name == "Unknown" or any(char.isdigit() for char in name[:2]):
            # Split de tekst op '|' of enter
            parts = full_text.split('|')
            name = clean_name(parts[0])

        # Laatste check: als de naam 'km' bevat, is het mislukt
        if "km" in name.lower() or len(name) < 3:
            continue

        # --- 2. DATA EXTRACTIE ---
        length_km = extract_number(full_text, r'(\d+\.?\d*)\s*km')
        gradient_pct = extract_number(full_text, r'(\d+\.?\d*)\s*%')
        
        # --- 3. DIFFICULT POINTS (Grootste getal > 20) ---
        difficulty = 0
        all_numbers = re.findall(r'\b\d+\b', full_text)
        candidates = []
        for n in all_numbers:
            val = float(n)
            if val > 20 and val < 5000 and val != length_km:
                candidates.append(int(val))
        if candidates:
            difficulty = max(candidates)

        # --- 4. HOOGTEMETERS (Berekenen) ---
        elevation = int(length_km * gradient_pct * 10)

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
    # s=popular is belangrijk voor consistente sortering
    url = f"https://climbfinder.com/en/ranking?l={region_id}&p={page}&s=popular"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return parse_html_content(r.text, page), None
        return [], f"Status {r.status_code}"
    except Exception as e:
        return [], str(e)

# ---------------------------------------------------------------------------
# UI LOGICA
# ---------------------------------------------------------------------------
st.title("Climbfinder Aggregator 2.0")

with st.sidebar:
    st.header("Instellingen")
    
    country = st.selectbox("Land", ["Alles"] + sorted(REGIONS_BY_COUNTRY.keys()))
    if country == "Alles":
        opts = ALL_REGIONS
    else:
        opts = [r for r in ALL_REGIONS if r["country"] == country]
    
    selected_region = st.selectbox("Kies Regio", opts, format_func=lambda x: x['label'])
    
    st.markdown("---")
    custom_id = st.text_input("Of vul ID in", value=str(selected_region['id']) if selected_region else "")
    
    col1, col2 = st.columns(2)
    start_p = col1.number_input("Start Pagina", 1, 100, 1)
    end_p = col2.number_input("Eind Pagina", 1, 100, 1)
    
    btn = st.button("Start Scraping", type="primary")

if btn:
    rid = custom_id if custom_id else str(selected_region['id'])
    
    st.info(f"Ophalen Regio {rid}...")
    
    all_data = []
    progress = st.progress(0)
    
    for i, p in enumerate(range(start_p, end_p + 1)):
        data, err = scrape_page_requests(rid, p)
        if data: all_data.extend(data)
        
        progress.progress((i + 1) / (end_p - start_p + 1))
        time.sleep(0.5)
    
    progress.empty()
    
    if all_data:
        df = pd.DataFrame(all_data)
        # Volgorde kolommen dwingen
        df = df[["Climb Name", "Length (km)", "Avg Gradient (%)", "Difficulty Points", "Elev. Gain (m)", "Page"]]
        
        st.success(f"{len(df)} klimmen gevonden!")
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Excel Export
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
            
        st.download_button("📥 Download Excel", buffer, "climbs.xlsx", "application/vnd.ms-excel")
    else:
        st.error("Geen data. Check ID.")

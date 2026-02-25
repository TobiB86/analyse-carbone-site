import requests
from bs4 import BeautifulSoup
import tldextract
import re
import pandas as pd
from urllib.parse import urljoin, urlparse

import streamlit as st

# ----------------------------
# CONFIG GLOBALE
# ----------------------------

RSE_KEYWORDS = [
    "rse", "responsabilité sociétale", "responsabilité sociale",
    "responsabilite sociétale", "responsabilite sociale",
    "développement durable", "developpement durable", "durable",
    "environnement", "environnemental", "impact environnemental",
    "transition écologique", "transition ecologique", "transition énergétique",
    "transition energetique",
    "esg", "csr", "sustainability", "sustainable", "sustainable development"
]

CARBON_KEYWORDS = [
    "bilan carbone", "empreinte carbone", "émissions de co2",
    "emissions de co2", "émissions carbone", "emissions carbone",
    "gaz à effet de serre", "gaz a effet de serre",
    "co2", "réduction des émissions", "reduction des emissions",
    "neutralité carbone", "neutralite carbone",
    "décarbonation", "decarbonation",
    "scope 1", "scope 2", "scope 3"
]

GREEN_IT_KEYWORDS = [
    "numérique responsable", "numerique responsable",
    "éco-conception", "eco-conception", "eco conception",
    "site éco-conçu", "site eco-concu",
    "green it",
    "hébergement vert", "hebergement vert",
    "hébergement écologique", "hebergement ecologique",
    "data center vert",
    "sobriété numérique", "sobriete numerique"
]

MAX_PAGES = 20
REQUEST_TIMEOUT = 10
USER_AGENT = "CarbonPOCBot/0.1 (+for research & prospecting)"

DEFAULT_WEIGHT_MULTIPLIER = 3.0
DEFAULT_ENERGY_PER_GB_KWH = 0.5
DEFAULT_CARBON_INTENSITY_G_PER_KWH = 300.0


# ----------------------------
# FONCTIONS TECHNIQUES
# ----------------------------

def normalize_base_url(url: str) -> str:
    if not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return base


def is_internal_link(link: str, base_domain: str) -> bool:
    if not link:
        return False
    parsed = urlparse(link)
    if not parsed.netloc:
        return True
    ext = tldextract.extract(parsed.netloc)
    domain = f"{ext.domain}.{ext.suffix}"
    return domain == base_domain


def fetch_page(url: str) -> str | None:
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
            return resp.text
    except Exception:
        pass
    return None


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_candidate_links(base_url: str, html: str, max_links: int = 30):
    soup = BeautifulSoup(html, "html.parser")
    ext = tldextract.extract(base_url)
    base_domain = f"{ext.domain}.{ext.suffix}"

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(base_url, href)
        if not is_internal_link(full_url, base_domain):
            continue

        text = (a.get_text() or "").lower()
        url_lower = full_url.lower()

        score = 0
        for kw in ["rse", "responsabilite", "responsabilité",
                   "developpement-durable", "developpement durable",
                   "durable", "environnement", "carbone", "co2",
                   "csr", "sustainab"]:
            if kw in url_lower or kw in text:
                score += 5

        links.append((full_url, score))

    links = sorted(links, key=lambda x: x[1], reverse=True)
    seen = set()
    ranked_links = []
    for url, sc in links:
        if url not in seen:
            ranked_links.append(url)
            seen.add(url)
        if len(ranked_links) >= max_links:
            break

    return ranked_links


def count_keywords(text: str, keywords: list) -> int:
    text_lower = text.lower()
    count = 0
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in text_lower:
            count += text_lower.count(kw_lower)
    return count


def analyze_text(text: str):
    rse_hits = count_keywords(text, RSE_KEYWORDS)
    carbon_hits = count_keywords(text, CARBON_KEYWORDS)
    green_it_hits = count_keywords(text, GREEN_IT_KEYWORDS)

    def score_from_hits(hits: int, max_hits: int = 20):
        if hits <= 0:
            return 0
        if hits >= max_hits:
            return 100
        return int(hits / max_hits * 100)

    scores = {
        "rse_hits": rse_hits,
        "carbon_hits": carbon_hits,
        "green_it_hits": green_it_hits,
        "rse_score": score_from_hits(rse_hits),
        "carbon_score": score_from_hits(carbon_hits),
        "green_it_score": score_from_hits(green_it_hits)
    }
    return scores


def analyze_page(html: str, url: str):
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else ""

    headings_h1 = len(soup.find_all("h1"))
    headings_h2 = len(soup.find_all("h2"))
    headings_h3 = len(soup.find_all("h3"))

    images = soup.find_all("img")
    scripts = soup.find_all("script")
    stylesheets = [l for l in soup.find_all("link", rel=True)
                   if "stylesheet" in [r.lower() for r in l.get("rel", [])]]

    num_images = len(images)
    num_scripts = len(scripts)
    num_stylesheets = len(stylesheets)

    html_bytes = len(html.encode("utf-8"))
    html_kb = round(html_bytes / 1024, 1)

    font_families = set()
    for tag in soup.find_all(style=True):
        style = tag["style"].lower()
        match = re.search(r"font-family\s*:\s*([^;]+)", style)
        if match:
            font_families.add(match.group(1).strip())

    font_resources = []
    for link in soup.find_all("link", href=True):
        href = link["href"].lower()
        if "fonts.googleapis.com" in href or "font" in href:
            font_resources.append(link["href"])

    num_inline_fonts = len(font_families)
    font_resources = list(set(font_resources))

    text = extract_text(html)
    text_scores = analyze_text(text)

    page_info = {
        "url": url,
        "title": title,
        "html_kb": html_kb,
        "num_images": num_images,
        "num_scripts": num_scripts,
        "num_stylesheets": num_stylesheets,
        "headings_h1": headings_h1,
        "headings_h2": headings_h2,
        "headings_h3": headings_h3,
        "num_inline_fonts": num_inline_fonts,
        "font_resources": font_resources,
        "text": text,
        **text_scores
    }

    return page_info


def analyze_website(url: str, max_pages: int = MAX_PAGES):
    base_url = normalize_base_url(url)

    html_home = fetch_page(base_url)
    if not html_home:
        return {
            "domain": urlparse(base_url).netloc,
            "url": base_url,
            "error": "Impossible de récupérer la page d'accueil",
            "pages_details": []
        }

    ext = tldextract.extract(base_url)
    domain = f"{ext.domain}.{ext.suffix}"

    home_info = analyze_page(html_home, base_url)
    candidate_links = find_candidate_links(base_url, html_home, max_links=50)

    visited = set([base_url])
    pages_data = [home_info]

    for link in candidate_links:
        if len(pages_data) >= max_pages:
            break
        if link in visited:
            continue
        visited.add(link)

        html = fetch_page(link)
        if not html:
            continue

        page_info = analyze_page(html, link)
        pages_data.append(page_info)

    total_rse_hits = sum(p["rse_hits"] for p in pages_data)
    total_carbon_hits = sum(p["carbon_hits"] for p in pages_data)
    total_green_it_hits = sum(p["green_it_hits"] for p in pages_data)

    has_bilan_carbone_explicit = any("bilan carbone" in p["text"].lower() for p in pages_data)
    has_rse_content = total_rse_hits > 0
    has_carbon_mentions = total_carbon_hits > 0
    has_green_it = total_green_it_hits > 0

    global_rse_score = max(p["rse_score"] for p in pages_data)
    global_carbon_score = max(p["carbon_score"] for p in pages_data)
    global_green_it_score = max(p["green_it_score"] for p in pages_data)

    pages_scanned = len(pages_data)
    total_html_kb = sum(p["html_kb"] for p in pages_data)
    avg_html_kb = round(total_html_kb / pages_scanned, 1) if pages_scanned > 0 else 0.0

    total_images = sum(p["num_images"] for p in pages_data)
    total_scripts = sum(p["num_scripts"] for p in pages_data)
    total_stylesheets = sum(p["num_stylesheets"] for p in pages_data)

    total_h1 = sum(p["headings_h1"] for p in pages_data)
    total_h2 = sum(p["headings_h2"] for p in pages_data)
    total_h3 = sum(p["headings_h3"] for p in pages_data)

    all_font_resources = set()
    for p in pages_data:
        for fr in p.get("font_resources", []):
            all_font_resources.add(fr)
    num_font_resources = len(all_font_resources)

    summary_parts = []
    if has_rse_content:
        summary_parts.append("L'entreprise communique sur la RSE / l'environnement.")
    else:
        summary_parts.append("Aucun contenu RSE clair trouvé sur les pages analysées.")

    if has_carbon_mentions:
        if has_bilan_carbone_explicit:
            summary_parts.append("Mention explicite d'un bilan carbone.")
        else:
            summary_parts.append("Mention d'émissions carbone / CO2, sans bilan carbone clairement identifié.")
    else:
        summary_parts.append("Aucune mention significative de carbone / CO2 trouvée.")

    if has_green_it:
        summary_parts.append("Des éléments de numérique responsable / green IT sont mentionnés.")
    else:
        summary_parts.append("Pas de mention de numérique responsable / site éco-conçu détectée.")

    summary_parts.append(
        f"Crawl de {pages_scanned} pages pour {total_html_kb:.1f} Ko de HTML (moyenne {avg_html_kb:.1f} Ko/page)."
    )
    summary = " ".join(summary_parts)

    result = {
        "domain": domain,
        "url": base_url,
        "pages_scanned": pages_scanned,
        "has_rse_content": has_rse_content,
        "has_carbon_mentions": has_carbon_mentions,
        "has_bilan_carbone_explicit": has_bilan_carbone_explicit,
        "has_green_it": has_green_it,
        "global_rse_score": global_rse_score,
        "global_carbon_score": global_carbon_score,
        "global_green_it_score": global_green_it_score,
        "total_rse_hits": total_rse_hits,
        "total_carbon_hits": total_carbon_hits,
        "total_green_it_hits": total_green_it_hits,
        "total_html_kb": total_html_kb,
        "avg_html_kb": avg_html_kb,
        "total_images": total_images,
        "total_scripts": total_scripts,
        "total_stylesheets": total_stylesheets,
        "total_h1": total_h1,
        "total_h2": total_h2,
        "total_h3": total_h3,
        "num_font_resources": num_font_resources,
        "summary": summary,
        "pages_details": pages_data
    }

    return result


def estimate_site_carbon(site_result: dict,
                         monthly_page_views: int,
                         weight_multiplier: float = DEFAULT_WEIGHT_MULTIPLIER,
                         energy_per_gb_kwh: float = DEFAULT_ENERGY_PER_GB_KWH,
                         carbon_intensity_g_per_kwh: float = DEFAULT_CARBON_INTENSITY_G_PER_KWH):
    avg_html_kb = site_result.get("avg_html_kb")
    if avg_html_kb is None:
        raise ValueError("Le résultat du site ne contient pas 'avg_html_kb'.")

    avg_kb_per_page = avg_html_kb * weight_multiplier
    gb_per_view = avg_kb_per_page / (1024 * 1024)
    kwh_per_view = gb_per_view * energy_per_gb_kwh
    gco2_per_view = kwh_per_view * carbon_intensity_g_per_kwh

    monthly_gco2 = gco2_per_view * monthly_page_views
    monthly_kgco2 = monthly_gco2 / 1000
    yearly_kgco2 = monthly_kgco2 * 12

    return {
        "avg_kb_per_page": round(avg_kb_per_page, 1),
        "gco2_per_page_view": round(gco2_per_view, 4),
        "monthly_kgco2": round(monthly_kgco2, 2),
        "yearly_kgco2": round(yearly_kgco2, 2),
        "assumptions": {
            "monthly_page_views": monthly_page_views,
            "weight_multiplier": weight_multiplier,
            "energy_per_gb_kwh": energy_per_gb_kwh,
            "carbon_intensity_g_per_kwh": carbon_intensity_g_per_kwh
        }
    }


# ----------------------------
# INTERFACE STREAMLIT
# ----------------------------

st.set_page_config(
    page_title="Analyse carbone d'un site web",
    page_icon="🌱",
    layout="centered"
)

st.title("🌱 Analyse carbone d'un site web")
st.write(
    "Entrez l'URL d'un site d'entreprise pour analyser : "
    "son discours RSE / climat et une estimation de l'empreinte carbone numérique (POC)."
)

with st.form("analyse_form"):
    url_input = st.text_input("URL du site", placeholder="https://www.exemple.com")
    monthly_views = st.number_input(
        "Pages vues mensuelles estimées",
        min_value=100,
        max_value=1_000_000,
        value=10_000,
        step=1000
    )
    submitted = st.form_submit_button("Analyser le site")

if submitted:
    if not url_input.strip():
        st.error("Merci d'indiquer une URL valide.")
    else:
        with st.spinner("Analyse en cours..."):
            site_result = analyze_website(url_input)

        if "error" in site_result and site_result["pages_details"] == []:
            st.error(site_result["error"])
        else:
            carbon = estimate_site_carbon(site_result, monthly_page_views=monthly_views)

            st.subheader("Résumé global")
            st.write(site_result["summary"])

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Score RSE", site_result["global_rse_score"])
            with col2:
                st.metric("Score climat / CO₂", site_result["global_carbon_score"])
            with col3:
                st.metric("Score numérique responsable", site_result["global_green_it_score"])

            st.markdown("---")
            st.subheader("Structure & ressources (échantillon)")

            col4, col5, col6 = st.columns(3)
            with col4:
                st.metric("Pages analysées", site_result["pages_scanned"])
                st.metric("Total HTML (Ko)", round(site_result["total_html_kb"], 1))
            with col5:
                st.metric("Taille moyenne page (Ko)", site_result["avg_html_kb"])
                st.metric("Images totales", site_result["total_images"])
            with col6:
                st.metric("Scripts JS", site_result["total_scripts"])
                st.metric("Feuilles de style", site_result["total_stylesheets"])

            st.markdown("---")
            st.subheader("Estimation carbone (POC)")

            st.write(
                f"Sur la base d'un poids moyen estimé de **{carbon['avg_kb_per_page']} Ko/page** "
                f"(HTML + CSS + JS + images) et d'environ **{monthly_views} pages vues / mois** :"
            )

            col7, col8, col9 = st.columns(3)
            with col7:
                st.metric("gCO₂ par page vue", carbon["gco2_per_page_view"])
            with col8:
                st.metric("kgCO₂ par mois", carbon["monthly_kgco2"])
            with col9:
                st.metric("kgCO₂ par an", carbon["yearly_kgco2"])

            st.caption(
                "⚠️ Estimation simplifiée, à considérer comme un ordre de grandeur "
                "pour comparer et prioriser, pas comme un bilan carbone officiel."
            )

            st.markdown("---")
            st.subheader("Détails des pages analysées")

            pages_df = pd.DataFrame(site_result["pages_details"])
            st.dataframe(
                pages_df[[
                    "url", "html_kb", "num_images", "num_scripts",
                    "num_stylesheets", "headings_h1", "headings_h2",
                    "headings_h3", "rse_score", "carbon_score", "green_it_score"
                ]]
            )

            csv_export = pages_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Télécharger les détails en CSV",
                data=csv_export,
                file_name=f"analyse_pages_{site_result['domain']}.csv",
                mime="text/csv"
            )

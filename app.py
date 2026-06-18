import streamlit as st
import anthropic
import json
import tempfile
import os
import hashlib
import requests
from pathlib import Path

st.set_page_config(
    page_title="NavDiagram – Tekhat Şeması",
    page_icon="🚢",
    layout="wide"
)

st.title("🚢 Navigasyon Tekhat Şeması Üreteci")
st.caption("Malzeme listesinden otomatik Promar formatında tekhat şeması")

# ─── API Keys ───────────────────────────────────────────────────────────────
def get_secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return None

api_key = get_secret("ANTHROPIC_API_KEY")
serpapi_key = get_secret("SERPAPI_KEY")

# ─── Görsel önbellek (session'da tutulur) ────────────────────────────────────
if "image_cache" not in st.session_state:
    st.session_state["image_cache"] = {}

CACHE_DIR = Path(tempfile.gettempdir()) / "navdiagram_images"
CACHE_DIR.mkdir(exist_ok=True)


def search_device_image(device_key, query, serp_key):
    """SerpAPI ile cihaz görseli ara. Önbellekte varsa onu döndür."""
    cache = st.session_state["image_cache"]
    if device_key in cache and Path(cache[device_key]).exists():
        return cache[device_key], True  # True = önbellekten

    if not serp_key:
        return None, False

    try:
        params = {
            "engine": "google_images",
            "q": query,
            "api_key": serp_key,
            "num": 5,
        }
        resp = requests.get("https://serpapi.com/search", params=params, timeout=15)
        data = resp.json()
        results = data.get("images_results", [])
        for r in results[:5]:
            url = r.get("original")
            if not url:
                continue
            path = download_image(url, device_key)
            if path:
                cache[device_key] = path
                return path, False  # False = yeni arama
    except Exception as e:
        st.warning(f"Arama hatası ({query}): {e}")
    return None, False


def download_image(url, device_key):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200 or "image" not in resp.headers.get("content-type", ""):
            return None
        ext = "png" if "png" in resp.headers["content-type"] else "jpg"
        fname = CACHE_DIR / f"{device_key}.{ext}"
        with open(fname, "wb") as f:
            f.write(resp.content)
        # Geçerli boyut kontrolü
        from PIL import Image
        img = Image.open(fname)
        if img.size[0] < 80 or img.size[1] < 80:
            fname.unlink()
            return None
        return str(fname)
    except Exception:
        return None


# ─── Sidebar ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Ayarlar")
    if api_key:
        st.success("✅ Claude API key yüklü")
    else:
        st.warning("Claude API key yok")
        api_key = st.text_input("Anthropic API Key", type="password")
    if serpapi_key:
        st.success("✅ SerpAPI key yüklü")
    else:
        st.warning("SerpAPI key yok")
    st.divider()
    st.info("""
    **Adımlar:**
    1. Excel yükle
    2. Cihazları çıkar (Claude)
    3. Görselleri bul (SerpAPI)
    4. Şemayı oluştur
    """)

# ─── Adım 1: Excel + Claude analizi ──────────────────────────────────────────
st.header("📋 Adım 1 — Malzeme Listesi Yükle")

col1, col2 = st.columns([2, 1])
with col1:
    uploaded = st.file_uploader("Excel malzeme listesi", type=["xlsx", "xls"])
    vessel = st.text_input("Gemi adı", placeholder="Örn: MAGNOLIA 40MT")
    project_no = st.text_input("Proje no", placeholder="Örn: 000157")
with col2:
    st.info("**Excel:** Malzeme Kodu | Malzeme | Birim | Miktar")

if st.button("🤖 Claude ile Analiz Et", type="primary", disabled=(not uploaded or not api_key)):
    with st.spinner("Excel okunuyor..."):
        import openpyxl
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name
        wb = openpyxl.load_workbook(tmp_path, data_only=True)
        ws = wb.active
        rows_text = ""
        for row in ws.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if cells:
                rows_text += " | ".join(cells) + "\n"
        os.unlink(tmp_path)

    with st.spinner("Claude analiz ediyor..."):
        try:
            client = anthropic.Anthropic(api_key=api_key)
            prompt = f"""Sen bir denizcilik navigasyon sistemleri uzmanisin.
Promar Deniz Malzemeleri sirketinin tekhat semalarini ciziyorsun.

GEMI: {vessel}
PROJE NO: {project_no}

MALZEME LISTESI:
{rows_text}

ONEMLI FILTRELEME: Kablolari, konnektorleri (T-Piece, Connector, Joiner, Terminator),
NMEA2000 kitlerini (Starter Kit, Backbone, Micro-C, Drop Cable), montaj malzemelerini
(Mount Kit, Bracket, Pole Mount), adaptorleri, yedek aksesuarlari (Sun Cover, Magazines,
Correctors), DC/DC converter ve guc kablolarini LISTEYE EKLEME.
SADECE GERCEK CIHAZLARI listele.

Her cihaz icin dogru marka adini kullan (Cassens & Plath, Simrad, Sailor, Navico, ComNav,
Furuno, B&G, Airmar, Intellian, FLIR, Actisense, Jotron, Phontech).

Lokasyonlar:
- MAST: Radarlar, antenler, GPS anten, hava istasyonu, uydu kubbesi, termal kamera
- BRIDGE_CONSOLE: Ekranlar, AIS, VHF, kontrol panelleri, otopilot paneli, ECDIS, navtex, pusula
- TECHNICAL_AREA: Radar islemcisi, ECDIS bilgisayari, junction box, NMEA buffer, sonar modulu, NEP
- STEERING_ROOM: Otopilot bilgisayari (AC80S/AC80A/NAC-2), rudder feedback (RF45X/RF40)
- PORT_WING / STBD_WING: Kanat ekranlari (IS42), FU80, QS80
- CREWMESS: Salon ekrani
- CPT_CABIN: Kaptan kabini ekrani
- HULL: Transducer, speed log sensoru

Her cihaz icin gorsel arama sorgusu olustur (Ingilizce, "front view" ekle).

Sadece gecerli JSON dondur:
{{
  "proje": {{"gemi": "{vessel}", "proje_no": "{project_no}"}},
  "cihazlar": [
    {{"id": "kisa_id", "marka": "SIMRAD", "model": "NSS12 evo3S",
      "etiket": "NSS12 evo3S", "lokasyon": "BRIDGE_CONSOLE", "guc": "+24V",
      "adet": 1, "gorsel_sorgu": "Simrad NSS12 evo3S chartplotter front view"}}
  ]
}}"""
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = message.content[0].text.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            data = json.loads(raw)
            st.session_state["layout_data"] = data
            st.success(f"✅ {len(data.get('cihazlar', []))} cihaz tespit edildi!")
            st.rerun()
        except Exception as e:
            st.error(f"Hata: {e}")
            if 'raw' in locals():
                st.code(raw)

# ─── Adım 2: Cihazları göster ─────────────────────────────────────────────
if "layout_data" in st.session_state:
    data = st.session_state["layout_data"]
    cihazlar = data.get("cihazlar", [])

    st.divider()
    st.header("🔍 Adım 2 — Cihazları Gözden Geçir")

    lok_sirasi = ["MAST", "BRIDGE_CONSOLE", "TECHNICAL_AREA", "STEERING_ROOM",
                  "PORT_WING", "STBD_WING", "CREWMESS", "CPT_CABIN", "HULL"]
    lok_options = lok_sirasi + ["WHEELHOUSE", "EXTERIOR"]
    ikonlar = {"MAST": "🔵", "BRIDGE_CONSOLE": "🟢", "TECHNICAL_AREA": "🟡",
               "STEERING_ROOM": "🟣", "PORT_WING": "🔵", "STBD_WING": "🔵",
               "CREWMESS": "⚪", "CPT_CABIN": "⚪", "HULL": "🟤"}

    lokasyonlar = {}
    for c in cihazlar:
        lokasyonlar.setdefault(c.get("lokasyon", "BRIDGE_CONSOLE"), []).append(c)

    for lok in lok_sirasi:
        if lok not in lokasyonlar:
            continue
        st.subheader(f"{ikonlar.get(lok,'⚫')} {lok} ({len(lokasyonlar[lok])})")
        for i, c in enumerate(lokasyonlar[lok]):
            cols = st.columns([3, 1, 2])
            cols[0].write(f"**{c.get('marka','')} {c.get('model','')}**")
            cols[1].write(c.get('guc', '-'))
            cur = c.get('lokasyon', 'BRIDGE_CONSOLE')
            new = cols[2].selectbox(
                f"lok_{c.get('id', i)}_{lok}", lok_options,
                index=lok_options.index(cur) if cur in lok_options else 1,
                label_visibility="collapsed"
            )
            c["lokasyon"] = new

    st.session_state["layout_data"] = data

    # ─── Adım 3: Görsel arama ──────────────────────────────────────────────
    st.divider()
    st.header("🖼️ Adım 3 — Cihaz Görsellerini Bul")

    if not serpapi_key:
        st.warning("SerpAPI key bulunamadı. Görseller aranamaz.")
    else:
        if st.button("🔍 Görselleri Ara (SerpAPI)", type="primary"):
            cache = st.session_state["image_cache"]
            yeni_arama = 0
            onbellekten = 0
            progress = st.progress(0)
            status = st.empty()

            for idx, c in enumerate(cihazlar):
                device_key = c.get("id", c.get("model", f"dev{idx}")).replace(" ", "_").lower()
                query = c.get("gorsel_sorgu", f"{c.get('marka','')} {c.get('model','')} front view")
                status.write(f"Aranıyor: {c.get('marka','')} {c.get('model','')}")
                path, from_cache = search_device_image(device_key, query, serpapi_key)
                if path:
                    c["gorsel"] = path
                    if from_cache:
                        onbellekten += 1
                    else:
                        yeni_arama += 1
                progress.progress((idx + 1) / len(cihazlar))

            status.empty()
            st.session_state["layout_data"] = data
            st.success(f"✅ Tamamlandı! {yeni_arama} yeni arama, {onbellekten} önbellekten (bedava)")
            st.info(f"Bu projede {yeni_arama} SerpAPI araması harcandı (250'den).")

    # Görselleri göster
    bulunan = [c for c in cihazlar if c.get("gorsel")]
    if bulunan:
        st.write(f"**{len(bulunan)} cihaz görseli bulundu:**")
        img_cols = st.columns(4)
        for i, c in enumerate(bulunan):
            with img_cols[i % 4]:
                try:
                    st.image(c["gorsel"], caption=f"{c.get('marka','')} {c.get('model','')}", width=130)
                except Exception:
                    st.caption(f"❌ {c.get('model','')}")

    with st.expander("🔧 Ham JSON"):
        st.json(data)

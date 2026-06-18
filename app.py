import streamlit as st
import anthropic
import json
import tempfile
import os
import requests
from pathlib import Path

st.set_page_config(page_title="NavDiagram – Tekhat Şeması", page_icon="🚢", layout="wide")
st.title("🚢 Navigasyon Tekhat Şeması Üreteci")
st.caption("Malzeme listesinden otomatik Promar formatında tekhat şeması")

def get_secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return None

api_key = get_secret("ANTHROPIC_API_KEY")
serpapi_key = get_secret("SERPAPI_KEY")

if "image_cache" not in st.session_state:
    st.session_state["image_cache"] = {}

CACHE_DIR = Path(tempfile.gettempdir()) / "navdiagram_images"
CACHE_DIR.mkdir(exist_ok=True)


def serp_search_urls(query, serp_key, n=8):
    """SerpAPI'den görsel URL listesi döndür."""
    try:
        params = {"engine": "google_images", "q": query, "api_key": serp_key, "num": n}
        resp = requests.get("https://serpapi.com/search", params=params, timeout=15)
        data = resp.json()
        return [r.get("original") for r in data.get("images_results", [])[:n] if r.get("original")]
    except Exception as e:
        st.warning(f"Arama hatası: {e}")
        return []


def download_image(url, device_key, suffix=""):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200 or "image" not in resp.headers.get("content-type", ""):
            return None
        ext = "png" if "png" in resp.headers["content-type"] else "jpg"
        fname = CACHE_DIR / f"{device_key}{suffix}.{ext}"
        with open(fname, "wb") as f:
            f.write(resp.content)
        from PIL import Image
        img = Image.open(fname)
        if img.size[0] < 80 or img.size[1] < 80:
            fname.unlink()
            return None
        return str(fname)
    except Exception:
        return None


def find_image(device_key, query, serp_key):
    """Önbellekte varsa onu, yoksa ara."""
    cache = st.session_state["image_cache"]
    if device_key in cache and Path(cache[device_key]).exists():
        return cache[device_key], True
    if not serp_key:
        return None, False
    for url in serp_search_urls(query, serp_key):
        path = download_image(url, device_key)
        if path:
            cache[device_key] = path
            return path, False
    return None, False


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
    st.info("**Adımlar:**\n1. Excel yükle\n2. Cihazları çıkar\n3. Görselleri bul\n4. Şema oluştur")

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
NMEA2000 kitlerini, montaj malzemelerini (Mount Kit, Bracket, Pole Mount), adaptorleri,
yedek aksesuarlari (Sun Cover, Magazines, Correctors), DC/DC converter ve guc kablolarini
LISTEYE EKLEME. SADECE GERCEK CIHAZLARI listele.

Dogru marka adini kullan: Cassens & Plath, Simrad, Sailor, Navico, ComNav, Furuno,
B&G, Airmar, Intellian, FLIR, Actisense, Jotron, Phontech, Shakespeare.
ASLA "PROJECTOR" yazma. Overhead Compass = Cassens & Plath markasidir.

Lokasyonlar:
- MAST: Radarlar, antenler, GPS anten, hava istasyonu, uydu kubbesi, termal kamera
- BRIDGE_CONSOLE: Ekranlar, AIS, VHF, kontrol panelleri, otopilot paneli, ECDIS, navtex, pusula
- TECHNICAL_AREA: Radar islemcisi, ECDIS bilgisayari, junction box, NMEA buffer, sonar modulu, NEP
- STEERING_ROOM: Otopilot bilgisayari (AC80S/AC80A/NAC-2), rudder feedback (RF45X/RF40)
- PORT_WING / STBD_WING: Kanat ekranlari (IS42), FU80, QS80
- CREWMESS: Salon ekrani
- CPT_CABIN: Kaptan kabini ekrani
- HULL: Transducer, speed log sensoru

GORSEL SORGUSU KURALLARI (cok onemli, dogru gorsel bulunmasi icin):
- Cihazin TIPINI mutlaka ekle. Ornekler:
  * Transducer ise: "Simrad XSONIC SS60 thru-hull transducer marine sensor"
  * Radar ise: "Simrad HALO 20 radar dome"
  * Ekran ise: "Simrad NSS12 evo3S chartplotter display"
  * Anten ise: "Shakespeare CX4 VHF marine antenna"
  * Otopilot bilgisayari: "Simrad AC80A autopilot computer black box"
  * GPS compass: "Simrad HS75 GPS compass antenna"
- Ingilizce yaz, sonuna "front view product" ekle
- Transducer, sensor, anten gibi cihazlarda ASLA sadece model adi yazma (ekran cikar)

Sadece gecerli JSON dondur:
{{
  "proje": {{"gemi": "{vessel}", "proje_no": "{project_no}"}},
  "cihazlar": [
    {{"id": "kisa_id", "marka": "SIMRAD", "model": "NSS12 evo3S",
      "etiket": "NSS12 evo3S", "lokasyon": "BRIDGE_CONSOLE", "guc": "+24V",
      "adet": 1, "gorsel_sorgu": "Simrad NSS12 evo3S chartplotter display front view product"}}
  ]
}}"""
            message = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=8000,
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
            new = cols[2].selectbox(f"lok_{c.get('id', i)}_{lok}", lok_options,
                index=lok_options.index(cur) if cur in lok_options else 1,
                label_visibility="collapsed")
            c["lokasyon"] = new

    st.session_state["layout_data"] = data

    st.divider()
    st.header("🖼️ Adım 3 — Cihaz Görsellerini Bul")

    if not serpapi_key:
        st.warning("SerpAPI key bulunamadı.")
    else:
        if st.button("🔍 Tüm Görselleri Ara (SerpAPI)", type="primary"):
            yeni, onb = 0, 0
            progress = st.progress(0)
            status = st.empty()
            for idx, c in enumerate(cihazlar):
                dk = c.get("id", c.get("model", f"dev{idx}")).replace(" ", "_").lower()
                q = c.get("gorsel_sorgu", f"{c.get('marka','')} {c.get('model','')} front view")
                status.write(f"Aranıyor: {c.get('marka','')} {c.get('model','')}")
                path, from_cache = find_image(dk, q, serpapi_key)
                if path:
                    c["gorsel"] = path
                    onb += 1 if from_cache else 0
                    yeni += 0 if from_cache else 1
                progress.progress((idx + 1) / len(cihazlar))
            status.empty()
            st.session_state["layout_data"] = data
            st.success(f"✅ {yeni} yeni arama, {onb} önbellekten (bedava)")
            st.rerun()

        # Görselleri göster + düzeltme araçları
        st.write("**Her cihazın görselini kontrol et. Yanlışsa: Yeniden Ara veya Manuel Yükle.**")

        for idx, c in enumerate(cihazlar):
            dk = c.get("id", c.get("model", f"dev{idx}")).replace(" ", "_").lower()
            with st.container():
                gc = st.columns([1, 2, 2, 2])
                # Görsel
                with gc[0]:
                    if c.get("gorsel") and Path(c["gorsel"]).exists():
                        st.image(c["gorsel"], width=90)
                    else:
                        st.caption("❌ Yok")
                # İsim
                gc[1].write(f"**{c.get('marka','')}**\n\n{c.get('model','')}")
                # Yeniden ara (özel sorgu ile)
                with gc[2]:
                    yeni_sorgu = st.text_input("Arama sorgusu", value=c.get("gorsel_sorgu", ""),
                        key=f"q_{dk}_{idx}", label_visibility="collapsed")
                    if st.button("🔄 Yeniden Ara", key=f"re_{dk}_{idx}"):
                        # Önbellekten sil, yeniden ara
                        st.session_state["image_cache"].pop(dk, None)
                        for url in serp_search_urls(yeni_sorgu, serpapi_key):
                            path = download_image(url, dk, suffix="_re")
                            if path:
                                c["gorsel"] = path
                                st.session_state["image_cache"][dk] = path
                                break
                        st.session_state["layout_data"] = data
                        st.rerun()
                # Manuel yükle
                with gc[3]:
                    up = st.file_uploader("Manuel", type=["jpg", "jpeg", "png", "webp"],
                        key=f"up_{dk}_{idx}", label_visibility="collapsed")
                    if up:
                        fname = CACHE_DIR / f"{dk}_manual.png"
                        with open(fname, "wb") as f:
                            f.write(up.read())
                        c["gorsel"] = str(fname)
                        st.session_state["image_cache"][dk] = str(fname)
                        st.session_state["layout_data"] = data
                        st.success("✅ Yüklendi")
                        st.rerun()
            st.divider()

    with st.expander("🔧 Ham JSON"):
        st.json(data)

# ============================================================================
# NavDiagram - Navigasyon Tekhat Şeması Üreteci
# ============================================================================
# Bölümler:
#   1. Kurulum ve API anahtarları
#   2. Yardımcı fonksiyonlar (GitHub hafıza, görsel arama, arka plan)
#   3. Sidebar (ayarlar + hafıza yönetimi)
#   4. Adım 1: Excel yükleme + Claude analizi
#   5. Adım 2: Cihaz listesi (düzenle, sil, lokasyon)
#   6. Adım 3: Görsel arama (ara, yeniden ara, manuel, arka plan, kaydet)
# ============================================================================

import streamlit as st
import anthropic
import json
import tempfile
import os
import base64
import requests
from pathlib import Path

st.set_page_config(page_title="Promar NavDiagram", page_icon="🚢", layout="wide")

# ─── Kurumsal denizcilik teması (CSS) ───────────────────────────────────────
st.markdown("""
<style>
    /* Ana renk paleti - denizci lacivert/mavi */
    :root {
        --promar-lacivert: #1B2A4A;
        --promar-mavi: #2C5697;
        --promar-acik-mavi: #4A90D9;
        --promar-gri: #F4F6F9;
    }
    /* Uygulama arka plani */
    .stApp {
        background: linear-gradient(180deg, #F4F6F9 0%, #E8EEF5 100%);
    }
    /* Ust logo bandi */
    .promar-header {
        text-align: center;
        padding: 10px 0 0 0;
    }
    .promar-title {
        text-align: center;
        color: #1B2A4A;
        font-size: 30px;
        font-weight: 800;
        letter-spacing: 0.5px;
        margin: 8px 0 2px 0;
    }
    .promar-subtitle {
        text-align: center;
        color: #2C5697;
        font-size: 15px;
        margin-bottom: 6px;
    }
    .promar-divider {
        height: 3px;
        background: linear-gradient(90deg, transparent, #2C5697, #4A90D9, #2C5697, transparent);
        border: none;
        margin: 10px 0 24px 0;
        border-radius: 2px;
    }
    /* Baslıklar */
    h2, h3 {
        color: #1B2A4A !important;
    }
    /* Butonlar */
    .stButton button[kind="primary"] {
        background: linear-gradient(135deg, #2C5697 0%, #4A90D9 100%);
        border: none;
        font-weight: 600;
    }
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1B2A4A 0%, #2C5697 100%);
    }
    section[data-testid="stSidebar"] * {
        color: #FFFFFF;
    }
    section[data-testid="stSidebar"] .stAlert {
        background: rgba(255,255,255,0.12);
        border-radius: 8px;
    }
    /* Sidebar basliklari (Ayarlar, Adimlar vb.) beyaz ve net */
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label {
        color: #FFFFFF !important;
    }
    section[data-testid="stSidebar"] .stMetric label,
    section[data-testid="stSidebar"] [data-testid="stMetricValue"] {
        color: #FFFFFF !important;
    }
</style>
""", unsafe_allow_html=True)

# ─── Ust logo + baslik ──────────────────────────────────────────────────────
import os as _os
LOGO_PATH = "promar_logo.png"
_logo_col1, _logo_col2, _logo_col3 = st.columns([0.6, 2.5, 1])
with _logo_col2:
    if _os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, use_container_width=True)
st.markdown('<div class="promar-title">⚓ Navigasyon Tekhat Şeması Üreteci</div>', unsafe_allow_html=True)
st.markdown('<hr class="promar-divider">', unsafe_allow_html=True)

def get_secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return None

api_key = get_secret("ANTHROPIC_API_KEY")
serpapi_key = get_secret("SERPAPI_KEY")
github_token = get_secret("GITHUB_TOKEN")
github_repo = get_secret("GITHUB_REPO")
github_branch = get_secret("GITHUB_BRANCH") or "main"

CACHE_DIR = Path(tempfile.gettempdir()) / "navdiagram_images"
CACHE_DIR.mkdir(exist_ok=True)

if "image_cache" not in st.session_state:
    st.session_state["image_cache"] = {}


def cihaz_anahtari(c):
    """Cihaz icin sabit, tutarli anahtar uret. Yazim farklarini yok sayar.
    Ornek: 'NSS12 evo3S', 'NSS12 EVO3S MFD', 'NSS-12 evo3s display' -> ayni anahtar."""
    import re
    marka = str(c.get("marka", "")).strip().lower()
    model = str(c.get("model", "")).strip().lower()

    # Gereksiz kelimeleri temizle (cihaz tipini belirten ama modeli degistirmeyen ekler)
    cop_kelimeler = [
        "mfd", "display", "unit", "system", "kit", "with", "w/", "and",
        "monitor", "screen", "transducer", "antenna", "anten", "control",
        "controller", "computer", "module", "sensor", "processor", "pack",
        "class", "imo", "marine", "new", "set", "package", "adet", "pcs",
        "compass", "radar", "gps", "vhf", "ais", "echosounder", "sounder",
        "thru-hull", "thru", "hull", "dome", "compact", "ultrasonic",
        "weather", "station", "autopilot", "chartplotter", "digital",
        "instrument", "remote", "pulse", "compression"
    ]

    metin = f"{marka} {model}"
    # Noktalama -> bosluk
    metin = re.sub(r"[^a-z0-9]+", " ", metin)
    kelimeler = [k for k in metin.split() if k and k not in cop_kelimeler]
    anahtar = "_".join(kelimeler)
    return anahtar or "bilinmeyen"


def _benzerlik(a, b):
    """Iki anahtar arasi benzerlik orani (0-1)."""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def hafizada_bul(device_key, mem):
    """Hafizada tam veya benzer anahtar ara. Bulursa (anahtar, gh_path) doner."""
    # 1. Tam eslesme
    if device_key in mem:
        return device_key, mem[device_key]
    # 2. Benzer eslesme (yazim farklarini tolere et)
    en_iyi = None
    en_iyi_oran = 0.0
    for k in mem.keys():
        oran = _benzerlik(device_key, k)
        if oran > en_iyi_oran:
            en_iyi_oran = oran
            en_iyi = k
    # %75 ustu benzerlik = ayni cihaz say
    if en_iyi and en_iyi_oran >= 0.75:
        return en_iyi, mem[en_iyi]
    return None, None


def github_headers():
    return {"Authorization": f"token {github_token}",
            "Accept": "application/vnd.github+json"}


@st.cache_data(ttl=300)
def load_device_memory():
    if not github_token or not github_repo:
        return {}
    try:
        url = f"https://api.github.com/repos/{github_repo}/contents/device_images/device_memory.json"
        resp = requests.get(url, headers=github_headers(), params={"ref": github_branch}, timeout=10)
        if resp.status_code == 200:
            content = base64.b64decode(resp.json()["content"]).decode("utf-8")
            return json.loads(content)
    except Exception:
        pass
    return {}


def github_get_sha(path):
    try:
        url = f"https://api.github.com/repos/{github_repo}/contents/{path}"
        resp = requests.get(url, headers=github_headers(), params={"ref": github_branch}, timeout=10)
        if resp.status_code == 200:
            return resp.json()["sha"]
    except Exception:
        pass
    return None


def github_upload(path, content_bytes, message):
    if not github_token:
        st.error("❌ GITHUB_TOKEN secrets'ta bulunamadı!")
        return False
    if not github_repo:
        st.error("❌ GITHUB_REPO secrets'ta bulunamadı!")
        return False
    try:
        url = f"https://api.github.com/repos/{github_repo}/contents/{path}"
        b64 = base64.b64encode(content_bytes).decode("utf-8")
        payload = {"message": message, "content": b64, "branch": github_branch}
        sha = github_get_sha(path)
        if sha:
            payload["sha"] = sha
        resp = requests.put(url, headers=github_headers(), json=payload, timeout=20)
        if resp.status_code in (200, 201):
            return True
        else:
            st.error(f"❌ GitHub hatası {resp.status_code}: {resp.text[:300]}")
            return False
    except Exception as e:
        st.error(f"❌ GitHub yükleme exception: {e}")
        return False


def github_delete_file(path, message):
    """GitHub'dan dosya sil."""
    if not github_token:
        return False
    try:
        sha = github_get_sha(path)
        if not sha:
            return True  # zaten yok
        url = f"https://api.github.com/repos/{github_repo}/contents/{path}"
        payload = {"message": message, "sha": sha, "branch": github_branch}
        resp = requests.delete(url, headers=github_headers(), json=payload, timeout=20)
        return resp.status_code in (200, 201)
    except Exception as e:
        st.error(f"❌ Silme hatasi: {e}")
        return False


def delete_device_from_memory(device_key):
    """Bir cihazi kalici hafizadan tamamen sil (gorsel + memory kaydi)."""
    mem = load_device_memory()
    if device_key not in mem:
        return False
    gh_path = mem[device_key]
    # 1. Gorseli sil
    github_delete_file(gh_path, f"Delete device image: {device_key}")
    # 2. Memory'den cikar
    del mem[device_key]
    github_upload("device_images/device_memory.json",
                  json.dumps(mem, indent=2).encode("utf-8"),
                  f"Remove from memory: {device_key}")
    load_device_memory.clear()
    return True


def _upload_image_only(device_key, local_path):
    """Sadece gorseli yukle, memory'ye DOKUNMA. (gh_path doner veya None)"""
    if not github_token:
        return None
    p = Path(local_path)
    if not p.exists():
        return None
    ext = p.suffix.lstrip(".").lower() or "png"
    if ext == "jpeg":
        ext = "jpg"
    gh_path = f"device_images/{device_key}.{ext}"
    with open(local_path, "rb") as f:
        file_content = f.read()
    if len(file_content) == 0:
        return None
    if github_upload(gh_path, file_content, f"Add device image: {device_key}"):
        return gh_path
    return None


def _update_memory(yeni_kayitlar):
    """memory.json'u TEK SEFERDE guncelle (cakisma onlemi)."""
    mem = load_device_memory()
    mem.update(yeni_kayitlar)
    ok = github_upload("device_images/device_memory.json",
                       json.dumps(mem, indent=2).encode("utf-8"),
                       f"Update memory ({len(yeni_kayitlar)} cihaz)")
    load_device_memory.clear()
    return ok


def save_device_image_to_github(device_key, local_path):
    """Tek cihaz kaydet (gorsel + memory)."""
    gh_path = _upload_image_only(device_key, local_path)
    if gh_path:
        _update_memory({device_key: gh_path})
        return True
    return False


def get_image_from_github(gh_path, device_key):
    try:
        url = f"https://raw.githubusercontent.com/{github_repo}/{github_branch}/{gh_path}"
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            ext = Path(gh_path).suffix or ".png"
            fname = CACHE_DIR / f"{device_key}_gh{ext}"
            with open(fname, "wb") as f:
                f.write(resp.content)
            return str(fname)
    except Exception:
        pass
    return None


def serp_search_urls(query, serp_key, n=8):
    try:
        params = {"engine": "google_images", "q": query, "api_key": serp_key, "num": n}
        resp = requests.get("https://serpapi.com/search", params=params, timeout=15)
        return [r.get("original") for r in resp.json().get("images_results", [])[:n] if r.get("original")]
    except Exception as e:
        st.warning(f"Arama hatasi: {e}")
        return []


def gecerli_gorsel_mi(path):
    """Dosya gercekten acilabilir bir resim mi?"""
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


def guvenli_goster(path, width=85):
    """Gorseli guvenli goster, bozuksa çökme."""
    try:
        if path and Path(path).exists() and gecerli_gorsel_mi(path):
            st.image(path, width=width)
            return True
    except Exception:
        pass
    st.caption("⚠️ Görsel geçersiz")
    return False


def download_image(url, device_key, suffix=""):
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if resp.status_code != 200 or "image" not in resp.headers.get("content-type", ""):
            return None
        ext = "png" if "png" in resp.headers["content-type"] else "jpg"
        fname = CACHE_DIR / f"{device_key}{suffix}.{ext}"
        with open(fname, "wb") as f:
            f.write(resp.content)
        from PIL import Image
        img = Image.open(fname)
        img.verify()  # bozuk mu kontrol
        img = Image.open(fname)  # verify sonrasi tekrar ac
        if img.size[0] < 80 or img.size[1] < 80:
            fname.unlink()
            return None
        # RGBA/RGB'ye cevir (palette transparency uyarisini onler)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
            img.save(fname)
        return str(fname)
    except Exception:
        return None


def remove_background(image_path):
    """rembg ile arka plani sil, seffaf PNG dondur."""
    try:
        from rembg import remove
        from PIL import Image
        inp = Path(image_path)
        outp = inp.parent / (inp.stem + "_nobg.png")
        if outp.exists():
            return str(outp)
        with open(image_path, "rb") as f:
            data_in = f.read()
        data_out = remove(data_in)
        with open(outp, "wb") as f:
            f.write(data_out)
        return str(outp)
    except Exception as e:
        st.warning(f"Arka plan silme hatasi: {e}")
        return None


def find_image(device_key, query, serp_key):
    cache = st.session_state["image_cache"]
    if device_key in cache and Path(cache[device_key]).exists():
        return cache[device_key], "session"
    mem = load_device_memory()
    bulunan_anahtar, gh_path = hafizada_bul(device_key, mem)
    if gh_path:
        path = get_image_from_github(gh_path, device_key)
        if path:
            cache[device_key] = path
            return path, "github"
    if not serp_key:
        return None, "yok"
    for url in serp_search_urls(query, serp_key):
        path = download_image(url, device_key)
        if path:
            cache[device_key] = path
            return path, "serpapi"
    return None, "yok"


with st.sidebar:
    st.header("⚙️ Ayarlar")
    if api_key:
        st.success("✅ Claude")
    else:
        st.warning("Claude yok")
    if serpapi_key:
        st.success("✅ SerpAPI")
    else:
        st.warning("SerpAPI yok")
    if github_token:
        st.success("✅ GitHub hafiza")
    else:
        st.warning("GitHub hafiza yok")
    st.divider()
    mem = load_device_memory()
    st.metric("Kalici hafizada cihaz", len(mem))

    # Kalici Hafiza Yonetimi
    if github_token and len(mem) > 0:
        with st.expander("🗑️ Hafıza Yönetimi"):
            st.caption("Bir cihazı kalıcı hafızadan silmek için 🗑️ butonuna basın.")
            for mdk in sorted(mem.keys()):
                mc1, mc2 = st.columns([3, 1])
                mc1.write(mdk)
                if mc2.button("🗑️", key=f"memdel_{mdk}"):
                    if delete_device_from_memory(mdk):
                        st.success(f"✅ {mdk} silindi")
                        st.rerun()
                    else:
                        st.error("Silinemedi")

    st.info("**Adimlar:**\n1. Excel yukle\n2. Cihazlari cikar\n3. Gorselleri bul\n4. Sema olustur")

st.header("📋 Adım 1 — Malzeme Listesi Yükle")
col1, col2 = st.columns([2, 1])
with col1:
    uploaded = st.file_uploader("Excel malzeme listesi", type=["xlsx", "xls"])
    vessel = st.text_input("Gemi adi", placeholder="Örn: MAGNOLIA 40MT")
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
ASLA PROJECTOR yazma. Overhead Compass = Cassens & Plath markasidir.

Lokasyonlar:
- MAST: Radarlar, antenler, GPS anten, hava istasyonu, uydu kubbesi, termal kamera
- BRIDGE_CONSOLE: Ekranlar, AIS, VHF, kontrol panelleri, otopilot paneli, ECDIS, navtex, pusula
- TECHNICAL_AREA: Radar islemcisi, ECDIS bilgisayari, junction box, NMEA buffer, sonar modulu, NEP
- STEERING_ROOM: Otopilot bilgisayari (AC80S/AC80A/NAC-2), rudder feedback (RF45X/RF40)
- PORT_WING / STBD_WING: Kanat ekranlari (IS42), FU80, QS80
- CREWMESS: Salon ekrani
- CPT_CABIN: Kaptan kabini ekrani
- HULL: Transducer, speed log sensoru

GORSEL SORGUSU: Cihaz tipini ekle (transducer/radar/display/antenna/computer).
Ingilizce, sonuna "front view product". Transducer/anten/sensorde asla sadece model yazma.

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

    # Manuel yuklenen gorselleri geri uygula (rerun sonrasi korunsun)
    if "manual_images" in st.session_state:
        for _idx, _c in enumerate(cihazlar):
            _dk = cihaz_anahtari(_c)
            if _dk in st.session_state["manual_images"]:
                _mp = st.session_state["manual_images"][_dk]
                if Path(_mp).exists():
                    _c["gorsel"] = _mp

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
    silinecek_id = None
    for lok in lok_sirasi:
        if lok not in lokasyonlar:
            continue
        st.subheader(f"{ikonlar.get(lok,'⚫')} {lok} ({len(lokasyonlar[lok])})")
        for i, c in enumerate(lokasyonlar[lok]):
            cols = st.columns([3, 1, 2, 1])
            cols[0].write(f"**{c.get('marka','')} {c.get('model','')}**")
            cols[1].write(c.get('guc', '-'))
            cur = c.get('lokasyon', 'BRIDGE_CONSOLE')
            cid = c.get('id', f"{lok}_{i}")
            new = cols[2].selectbox(f"lok_{cid}_{lok}", lok_options,
                index=lok_options.index(cur) if cur in lok_options else 1,
                label_visibility="collapsed")
            c["lokasyon"] = new
            if cols[3].button("🗑️ Sil", key=f"del_{cid}_{lok}_{i}"):
                silinecek_id = id(c)  # bu cihaz nesnesini isaretle

    # Silme islemi
    if silinecek_id is not None:
        data["cihazlar"] = [x for x in cihazlar if id(x) != silinecek_id]
        st.session_state["layout_data"] = data
        st.rerun()

    st.session_state["layout_data"] = data

    st.divider()
    st.header("🖼️ Adım 3 — Cihaz Görsellerini Bul")

    if not serpapi_key:
        st.warning("SerpAPI key bulunamadi.")
    else:
        if st.button("🔍 Tüm Görselleri Ara", type="primary"):
            yeni, gh, sess = 0, 0, 0
            progress = st.progress(0)
            status = st.empty()
            for idx, c in enumerate(cihazlar):
                dk = cihaz_anahtari(c)
                q = c.get("gorsel_sorgu", f"{c.get('marka','')} {c.get('model','')} front view")
                status.write(f"Araniyor: {c.get('marka','')} {c.get('model','')}")
                path, kaynak = find_image(dk, q, serpapi_key)
                if path:
                    c["gorsel"] = path
                    c["kaynak"] = kaynak  # nereden geldigini kaydet
                    if kaynak == "serpapi":
                        yeni += 1
                    elif kaynak == "github":
                        gh += 1
                    else:
                        sess += 1
                progress.progress((idx + 1) / len(cihazlar))
            status.empty()
            st.session_state["layout_data"] = data
            st.success(f"✅ {yeni} yeni arama · {gh} kalici hafizadan (bedava) · {sess} oturumdan")
            st.rerun()

        # Arka plan silme
        col_bg1, col_bg2 = st.columns(2)
        with col_bg1:
            if st.button("✂️ Tüm Arka Planları Sil", type="secondary"):
                progress = st.progress(0)
                status = st.empty()
                silindi = 0
                for idx, c in enumerate(cihazlar):
                    if c.get("gorsel") and Path(c["gorsel"]).exists() and "_nobg" not in c["gorsel"]:
                        status.write(f"Temizleniyor: {c.get('marka','')} {c.get('model','')}")
                        nobg = remove_background(c["gorsel"])
                        if nobg:
                            c["gorsel"] = nobg
                            dk = cihaz_anahtari(c)
                            st.session_state["image_cache"][dk] = nobg
                            silindi += 1
                    progress.progress((idx + 1) / len(cihazlar))
                status.empty()
                st.session_state["layout_data"] = data
                st.success(f"✅ {silindi} görselin arka planı silindi!")
                st.rerun()

        st.write("**Görseli kontrol et. Doğruysa Kaydet. Yanlışsa yeniden ara veya manuel yükle.**")

        for idx, c in enumerate(cihazlar):
            dk = cihaz_anahtari(c)
            gc = st.columns([1, 2, 2, 2, 1, 1])
            with gc[0]:
                if c.get("gorsel"):
                    guvenli_goster(c["gorsel"], width=85)
                else:
                    st.caption("❌")
            kaynak_etiket = {
                "github": "💚 Hafızadan (bedava)",
                "serpapi": "🔍 Yeni arama (token harcandı)",
                "manuel": "📁 Manuel yüklendi",
                "session": "⚡ Oturumdan",
            }.get(c.get("kaynak", ""), "")
            gc[1].write(f"**{c.get('marka','')}**\n\n{c.get('model','')}\n\n{kaynak_etiket}")
            with gc[2]:
                ysorgu = st.text_input("sorgu", value=c.get("gorsel_sorgu", ""),
                    key=f"q_{dk}_{idx}", label_visibility="collapsed")
                if st.button("🔄 Yeniden Ara", key=f"re_{dk}_{idx}"):
                    # URL listesini bir kez cek ve sakla (sayac ile sirayla gez)
                    urls_key = f"re_urls_{dk}"
                    sayac_key = f"re_sayac_{dk}"
                    # Ilk basista veya liste yoksa yeni arama yap
                    if urls_key not in st.session_state:
                        guclu_sorgu = f"{ysorgu} single product white background front view isolated"
                        st.session_state[urls_key] = serp_search_urls(guclu_sorgu, serpapi_key, n=15)
                        st.session_state[sayac_key] = -1
                    urls = st.session_state[urls_key]
                    # Bu cihazin eski izlerini temizle
                    st.session_state["image_cache"].pop(dk, None)
                    if "manual_images" in st.session_state:
                        st.session_state["manual_images"].pop(dk, None)
                    bulundu = False
                    if urls:
                        # Siradaki url'yi dene, sonuna gelince basa don
                        denenecek = len(urls)
                        for _ in range(denenecek):
                            st.session_state[sayac_key] = (st.session_state.get(sayac_key, -1) + 1) % len(urls)
                            i = st.session_state[sayac_key]
                            path = download_image(urls[i], dk, suffix=f"_re{i}")
                            if path:
                                c["gorsel"] = path
                                c["kaynak"] = "serpapi"
                                st.session_state["image_cache"][dk] = path
                                bulundu = True
                                break
                    st.session_state["layout_data"] = data
                    if bulundu:
                        st.rerun()
                    else:
                        st.warning("Baska gorsel bulunamadi, sorguyu degistirip tekrar deneyin")
            with gc[3]:
                up = st.file_uploader("yukle", type=["jpg", "jpeg", "png", "webp"],
                    key=f"up_{dk}_{idx}", label_visibility="collapsed")
                if up is not None:
                    import hashlib
                    raw_bytes = up.getvalue()
                    h = hashlib.md5(raw_bytes).hexdigest()[:8]
                    ext = Path(up.name).suffix.lower() or ".png"
                    fname = CACHE_DIR / f"{dk}_manual_{h}{ext}"
                    # Ayni dosya zaten islendiyse tekrar rerun yapma (sonsuz dongu onlemi)
                    onceki = st.session_state.get("manual_images", {}).get(dk)
                    if onceki != str(fname):
                        with open(fname, "wb") as f:
                            f.write(raw_bytes)
                        if "manual_images" not in st.session_state:
                            st.session_state["manual_images"] = {}
                        st.session_state["manual_images"][dk] = str(fname)
                        c["gorsel"] = str(fname)
                        c["kaynak"] = "manuel"
                        st.session_state["image_cache"][dk] = str(fname)
                        st.session_state["layout_data"] = data
                        st.rerun()
            with gc[4]:
                if c.get("gorsel") and github_token:
                    if st.button("💾 Kaydet", key=f"sv_{dk}_{idx}"):
                        if Path(c["gorsel"]).exists():
                            if save_device_image_to_github(dk, c["gorsel"]):
                                load_device_memory.clear()
                                st.success("✅ Kaydedildi")
                            else:
                                st.error("❌ Hata")
                        else:
                            st.error("❌ Görsel dosyası yok")
            with gc[5]:
                if c.get("gorsel") and "_nobg" not in str(c.get("gorsel", "")):
                    if st.button("✂️ BG", key=f"bg_{dk}_{idx}"):
                        nobg = remove_background(c["gorsel"])
                        if nobg:
                            c["gorsel"] = nobg
                            st.session_state["image_cache"][dk] = nobg
                            st.session_state["layout_data"] = data
                            st.rerun()

        st.divider()
        if st.button("💾 Tüm Görselleri Kalıcı Hafızaya Kaydet", type="primary"):
            gorselli = [c for c in cihazlar if c.get("gorsel") and Path(c["gorsel"]).exists()]
            if not github_token:
                st.error("❌ GitHub token yok!")
            elif len(gorselli) == 0:
                st.error("❌ Kaydedilecek görsel yok. Önce 'Tüm Görselleri Ara' yapın.")
            else:
                sayac = 0
                hata = 0
                yeni_kayitlar = {}
                kayit_durumu = st.empty()
                # 1) Once tum gorselleri yukle (memory'ye dokunmadan)
                for idx, c in enumerate(cihazlar):
                    if c.get("gorsel") and Path(c["gorsel"]).exists():
                        dk = cihaz_anahtari(c)
                        kayit_durumu.write(f"Kaydediliyor: {c.get('marka','')} {c.get('model','')}...")
                        gh_path = _upload_image_only(dk, c["gorsel"])
                        if gh_path:
                            yeni_kayitlar[dk] = gh_path
                            sayac += 1
                        else:
                            hata += 1
                # 2) memory.json'u TEK SEFERDE guncelle (cakisma yok)
                if yeni_kayitlar:
                    _update_memory(yeni_kayitlar)
                kayit_durumu.empty()
                if sayac > 0:
                    st.success(f"✅ {sayac} görsel kalıcı hafızaya kaydedildi!")
                if hata > 0:
                    st.warning(f"⚠️ {hata} görsel kaydedilemedi.")

    with st.expander("🔧 Ham JSON"):
        st.json(data)

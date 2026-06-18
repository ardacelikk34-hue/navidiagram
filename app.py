import streamlit as st
import anthropic
import json
import tempfile
import os
import base64
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
github_token = get_secret("GITHUB_TOKEN")
github_repo = get_secret("GITHUB_REPO")
github_branch = get_secret("GITHUB_BRANCH") or "main"

CACHE_DIR = Path(tempfile.gettempdir()) / "navdiagram_images"
CACHE_DIR.mkdir(exist_ok=True)

if "image_cache" not in st.session_state:
    st.session_state["image_cache"] = {}


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
    if not github_token or not github_repo:
        return False
    try:
        url = f"https://api.github.com/repos/{github_repo}/contents/{path}"
        b64 = base64.b64encode(content_bytes).decode("utf-8")
        payload = {"message": message, "content": b64, "branch": github_branch}
        sha = github_get_sha(path)
        if sha:
            payload["sha"] = sha
        resp = requests.put(url, headers=github_headers(), json=payload, timeout=20)
        return resp.status_code in (200, 201)
    except Exception as e:
        st.warning(f"GitHub yukleme hatasi: {e}")
        return False


def save_device_image_to_github(device_key, local_path):
    if not github_token:
        return False
    ext = Path(local_path).suffix.lstrip(".") or "png"
    gh_path = f"device_images/{device_key}.{ext}"
    with open(local_path, "rb") as f:
        content = f.read()
    if github_upload(gh_path, content, f"Add device image: {device_key}"):
        mem = load_device_memory()
        mem[device_key] = gh_path
        github_upload("device_images/device_memory.json",
                      json.dumps(mem, indent=2).encode("utf-8"),
                      f"Update memory: {device_key}")
        load_device_memory.clear()
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
        if img.size[0] < 80 or img.size[1] < 80:
            fname.unlink()
            return None
        return str(fname)
    except Exception:
        return None


def find_image(device_key, query, serp_key):
    cache = st.session_state["image_cache"]
    if device_key in cache and Path(cache[device_key]).exists():
        return cache[device_key], "session"
    mem = load_device_memory()
    if device_key in mem:
        path = get_image_from_github(mem[device_key], device_key)
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
        st.warning("SerpAPI key bulunamadi.")
    else:
        if st.button("🔍 Tüm Görselleri Ara", type="primary"):
            yeni, gh, sess = 0, 0, 0
            progress = st.progress(0)
            status = st.empty()
            for idx, c in enumerate(cihazlar):
                dk = c.get("id", c.get("model", f"dev{idx}")).replace(" ", "_").lower()
                q = c.get("gorsel_sorgu", f"{c.get('marka','')} {c.get('model','')} front view")
                status.write(f"Araniyor: {c.get('marka','')} {c.get('model','')}")
                path, kaynak = find_image(dk, q, serpapi_key)
                if path:
                    c["gorsel"] = path
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

        st.write("**Görseli kontrol et. Doğruysa Kaydet. Yanlışsa yeniden ara veya manuel yükle.**")

        for idx, c in enumerate(cihazlar):
            dk = c.get("id", c.get("model", f"dev{idx}")).replace(" ", "_").lower()
            gc = st.columns([1, 2, 2, 2, 1])
            with gc[0]:
                if c.get("gorsel") and Path(c["gorsel"]).exists():
                    st.image(c["gorsel"], width=85)
                else:
                    st.caption("❌")
            gc[1].write(f"**{c.get('marka','')}**\n\n{c.get('model','')}")
            with gc[2]:
                ysorgu = st.text_input("sorgu", value=c.get("gorsel_sorgu", ""),
                    key=f"q_{dk}_{idx}", label_visibility="collapsed")
                if st.button("🔄 Yeniden Ara", key=f"re_{dk}_{idx}"):
                    st.session_state["image_cache"].pop(dk, None)
                    for url in serp_search_urls(ysorgu, serpapi_key):
                        path = download_image(url, dk, suffix="_re")
                        if path:
                            c["gorsel"] = path
                            st.session_state["image_cache"][dk] = path
                            break
                    st.session_state["layout_data"] = data
                    st.rerun()
            with gc[3]:
                up = st.file_uploader("yukle", type=["jpg", "jpeg", "png", "webp"],
                    key=f"up_{dk}_{idx}", label_visibility="collapsed")
                if up:
                    fname = CACHE_DIR / f"{dk}_manual.png"
                    with open(fname, "wb") as f:
                        f.write(up.read())
                    c["gorsel"] = str(fname)
                    st.session_state["image_cache"][dk] = str(fname)
                    st.session_state["layout_data"] = data
                    st.rerun()
            with gc[4]:
                if c.get("gorsel") and github_token:
                    if st.button("💾 Kaydet", key=f"sv_{dk}_{idx}"):
                        if save_device_image_to_github(dk, c["gorsel"]):
                            st.success("✅")
                        else:
                            st.error("Hata")

        if github_token and st.button("💾 Tüm Görselleri Kalıcı Hafızaya Kaydet", type="secondary"):
            sayac = 0
            for idx, c in enumerate(cihazlar):
                if c.get("gorsel"):
                    dk = c.get("id", c.get("model", f"dev{idx}")).replace(" ", "_").lower()
                    if save_device_image_to_github(dk, c["gorsel"]):
                        sayac += 1
            st.success(f"✅ {sayac} gorsel kalici hafizaya kaydedildi!")

    with st.expander("🔧 Ham JSON"):
        st.json(data)

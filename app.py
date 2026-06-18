import streamlit as st
import anthropic
import json
import tempfile
import os
from pathlib import Path

st.set_page_config(
    page_title="NavDiagram – Tekhat Şeması",
    page_icon="🚢",
    layout="wide"
)

st.title("🚢 Navigasyon Tekhat Şeması Üreteci")
st.caption("Malzeme listesinden otomatik Promar formatında tekhat şeması")

def get_api_key():
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        return None

api_key = get_api_key()

with st.sidebar:
    st.header("⚙️ Ayarlar")
    if api_key:
        st.success("✅ API key yüklü")
    else:
        st.warning("API key bulunamadı")
        api_key = st.text_input("Anthropic API Key", type="password")
    st.divider()
    st.info("""
    **Nasıl kullanılır:**
    1. Excel malzeme listesini yükle
    2. Analiz et
    3. Cihazları gözden geçir
    4. Şemayı oluştur
    """)

st.header("📋 Adım 1 — Malzeme Listesi Yükle")

col1, col2 = st.columns([2, 1])
with col1:
    uploaded = st.file_uploader(
        "Excel malzeme listesi",
        type=["xlsx", "xls"],
        help="Malzeme Kodu | Malzeme | Birim | Miktar formatında"
    )
    vessel = st.text_input("Gemi adı", placeholder="Örn: MAGNOLIA 40MT")
    project_no = st.text_input("Proje no", placeholder="Örn: 000157")

with col2:
    st.info("""
    **Excel formatı:**
    - Malzeme Kodu
    - Malzeme (model adı)
    - Birim
    - Miktar
    """)

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

            prompt = f"""Sen bir denizcilik navigasyon sistemleri uzmanısın.
Promar Deniz Malzemeleri şirketinin tekhat şemalarını çiziyorsun.

GEMİ: {vessel}
PROJE NO: {project_no}

MALZEME LİSTESİ:
{rows_text}

Her cihaz için lokasyon belirle:
- MAST: Radarlar, antenler, GPS anten, hava istasyonu, uydu kubbesi, termal kamera
- BRIDGE_CONSOLE: Ekranlar, AIS, VHF, kontrol panelleri, otopilot kontrol paneli, ECDIS, navtex
- TECHNICAL_AREA: Radar islemcisi, ECDIS bilgisayari, junction box, NMEA buffer, sonar modulu, DC/DC converter
- STEERING_ROOM: Otopilot bilgisayari (AC80S/NAC-2), rudder feedback (RF45X/RF40)
- PORT_WING / STBD_WING: Kanat ekranlari (IS42), FU80
- CREWMESS: Salon ekrani
- CPT_CABIN: Kaptan kabini ekrani
- HULL: Transducer, speed log sensoru

Kablo turleri: ethernet, display, nmea2000, nmea0183, simnet, coax

Sadece gecerli JSON dondur, baska aciklama ekleme:
{{
  "proje": {{"gemi": "{vessel}", "proje_no": "{project_no}"}},
  "cihazlar": [
    {{
      "id": "kisa_id",
      "marka": "SIMRAD",
      "model": "NSO evo3S",
      "etiket": "NSO evo3S",
      "lokasyon": "TECHNICAL_AREA",
      "guc": "+24V",
      "adet": 1,
      "baglantilar": [{{"hedef": "diger_id", "kablo": "ethernet"}}]
    }}
  ]
}}"""

            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4000,
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

    lokasyonlar = {}
    for c in cihazlar:
        lok = c.get("lokasyon", "BRIDGE_CONSOLE")
        lokasyonlar.setdefault(lok, []).append(c)

    lok_sirasi = ["MAST", "BRIDGE_CONSOLE", "TECHNICAL_AREA", "STEERING_ROOM",
                  "PORT_WING", "STBD_WING", "CREWMESS", "CPT_CABIN", "HULL"]
    lok_options = lok_sirasi + ["WHEELHOUSE", "EXTERIOR"]
    ikonlar = {"MAST": "🔵", "BRIDGE_CONSOLE": "🟢", "TECHNICAL_AREA": "🟡",
               "STEERING_ROOM": "🟣", "PORT_WING": "🔵", "STBD_WING": "🔵",
               "CREWMESS": "⚪", "CPT_CABIN": "⚪", "HULL": "🟤"}

    guncel = []
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
                f"lok_{c.get('id', i)}_{lok}",
                lok_options,
                index=lok_options.index(cur) if cur in lok_options else 1,
                label_visibility="collapsed"
            )
            c["lokasyon"] = new
            guncel.append(c)

    data["cihazlar"] = guncel
    st.session_state["layout_data"] = data

    with st.expander("🔧 Ham JSON"):
        st.json(data)

    st.info("✅ Adım 1 tamamlandı! Çizim motoru (Adım 3) bir sonraki güncellemede eklenecek.")

import streamlit as st
import google.generativeai as genai
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

# Sidebar - API Key
with st.sidebar:
    st.header("⚙️ Ayarlar")
    gemini_key = st.text_input("Gemini API Key", type="password")
    st.divider()
    st.info("""
    **Nasıl kullanılır:**
    1. Gemini API key gir
    2. Malzeme listesini yükle
    3. Analiz et
    4. Şemayı indir
    """)

# Ana içerik
st.header("📋 Adım 1 — Malzeme Listesi Yükle")

col1, col2 = st.columns([2,1])
with col1:
    uploaded = st.file_uploader("PDF veya Excel malzeme listesi", type=["pdf","xlsx","xls"])
    vessel = st.text_input("Gemi adı", placeholder="Örn: MAGNOLIA 40MT")
    project_no = st.text_input("Proje no", placeholder="Örn: P19910-23-2500-01")

with col2:
    st.info("""
    **Desteklenen sistemler:**
    - SIMRAD, SAILOR
    - NAVICO, COMNAV  
    - PHONTECH, JOTRON
    - INTELLIAN, FLIR
    """)

if st.button("🤖 AI ile Analiz Et", type="primary", disabled=(not uploaded or not gemini_key)):
    with st.spinner("Malzeme listesi okunuyor..."):
        # PDF oku
        text = ""
        suffix = Path(uploaded.name).suffix.lower()
        
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name
        
        try:
            if suffix == ".pdf":
                import pdfplumber
                with pdfplumber.open(tmp_path) as pdf:
                    for page in pdf.pages:
                        t = page.extract_text()
                        if t:
                            text += t + "\n"
            else:
                import openpyxl
                wb = openpyxl.load_workbook(tmp_path, data_only=True)
                ws = wb.active
                for row in ws.iter_rows(values_only=True):
                    if any(row):
                        text += " | ".join(str(c) for c in row if c) + "\n"
        finally:
            os.unlink(tmp_path)

    with st.spinner("Gemini AI analiz ediyor..."):
        try:
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-2.0-flash-lite")
            
            prompt = f"""Sen bir denizcilik navigasyon sistemleri uzmanısın. 
Aşağıdaki malzeme listesini analiz et.

GEMİ: {vessel}
PROJE NO: {project_no}

MALZEME LİSTESİ:
{text[:8000]}

Her cihaz için lokasyon belirle:
- MAST: Radarlar, antenler, GPS anten, hava istasyonu
- BRIDGE_CONSOLE: Ekranlar, AIS, VHF, kontrol panelleri, otopilot paneli
- TECHNICAL_AREA: Radar işlemcisi, ECDIS bilgisayarı, junction box, NMEA buffer
- STEERING_ROOM: Otopilot bilgisayarı (AC80S), rudder feedback (RF45X)
- PORT_WING / STBD_WING: Kanat ekranları, FU80
- CREWMESS: Salon ekranı
- CPT_CABIN: Kaptan kabini ekranı
- HULL: Transducer, speed log sensörü

Kablo türleri:
- ethernet: Yeşil
- display: Sarı
- nmea2000: Mor
- nmea0183: Kırmızı
- simnet: Turuncu

Sadece JSON döndür, başka metin ekleme:
{{
  "proje": {{
    "gemi": "{vessel}",
    "proje_no": "{project_no}"
  }},
  "cihazlar": [
    {{
      "id": "benzersiz_id",
      "marka": "SIMRAD",
      "model": "R5024",
      "etiket": "12KW RADAR\\nSCANNER",
      "lokasyon": "MAST",
      "guc": "+24V",
      "baglantilar": [
        {{"hedef": "diger_cihaz_id", "kablo": "ethernet"}}
      ]
    }}
  ]
}}"""

            response = model.generate_content(prompt)
            raw = response.text.strip()
            
            # JSON çıkar
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            
            data = json.loads(raw)
            st.session_state["layout_data"] = data
            st.session_state["raw_text"] = text
            st.success(f"✅ {len(data.get('cihazlar', []))} cihaz tespit edildi!")
            st.rerun()
            
        except Exception as e:
            st.error(f"Hata: {e}")
            st.code(raw if 'raw' in locals() else "")

# Sonuç göster
if "layout_data" in st.session_state:
    data = st.session_state["layout_data"]
    cihazlar = data.get("cihazlar", [])
    
    st.divider()
    st.header("🔍 Adım 2 — Cihazları Gözden Geçir")
    
    # Lokasyona göre grupla
    lokasyonlar = {}
    for c in cihazlar:
        lok = c.get("lokasyon", "BRIDGE_CONSOLE")
        if lok not in lokasyonlar:
            lokasyonlar[lok] = []
        lokasyonlar[lok].append(c)
    
    lok_sirasi = ["MAST", "BRIDGE_CONSOLE", "TECHNICAL_AREA", 
                  "STEERING_ROOM", "PORT_WING", "STBD_WING", 
                  "CREWMESS", "CPT_CABIN", "HULL"]
    
    lok_renkleri = {
        "MAST": "🔵", "BRIDGE_CONSOLE": "🟢", "TECHNICAL_AREA": "🟡",
        "STEERING_ROOM": "🟣", "PORT_WING": "🔵", "STBD_WING": "🔵",
        "CREWMESS": "⚪", "CPT_CABIN": "⚪", "HULL": "🟤"
    }
    
    lok_options = lok_sirasi + ["EXTERIOR"]
    
    guncellenmis = []
    for lok in lok_sirasi:
        if lok not in lokasyonlar:
            continue
        st.subheader(f"{lok_renkleri.get(lok,'⚫')} {lok} ({len(lokasyonlar[lok])} cihaz)")
        
        cols = st.columns([2, 2, 1, 2])
        cols[0].write("**Marka/Model**")
        cols[1].write("**Etiket**")
        cols[2].write("**Güç**")
        cols[3].write("**Lokasyon**")
        
        for i, c in enumerate(lokasyonlar[lok]):
            cols = st.columns([2, 2, 1, 2])
            cols[0].write(f"{c.get('marka','')} {c.get('model','')}")
            cols[1].write(c.get('etiket','').replace('\n', ' '))
            cols[2].write(c.get('guc', '-'))
            
            cur_lok = c.get('lokasyon', 'BRIDGE_CONSOLE')
            new_lok = cols[3].selectbox(
                f"l_{c.get('id',i)}",
                lok_options,
                index=lok_options.index(cur_lok) if cur_lok in lok_options else 1,
                label_visibility="collapsed"
            )
            c["lokasyon"] = new_lok
            guncellenmis.append(c)
    
    data["cihazlar"] = guncellenmis
    st.session_state["layout_data"] = data
    
    st.divider()
    st.header("📐 Adım 3 — Şema Oluştur")
    
    if st.button("🚀 PPTX Şeması Oluştur", type="primary"):
        with st.spinner("Şema oluşturuluyor..."):
            try:
                from pptx import Presentation
                from pptx.util import Cm, Pt, Emu
                from pptx.dml.color import RGBColor
                from pptx.enum.text import PP_ALIGN
                from lxml import etree
                from pptx.oxml.ns import qn
                
                prs = Presentation()
                prs.slide_width = Cm(42)
                prs.slide_height = Cm(29.7)
                
                slide = prs.slides.add_slide(prs.slide_layouts[6])
                
                # Lokasyon bölgeleri
                zones = {
                    "MAST":           (0.8, 0.5,  32,  5.0, "MAST"),
                    "BRIDGE_CONSOLE": (0.8, 6.0,  22, 11.0, "BRIDGE CONSOLE"),
                    "TECHNICAL_AREA": (0.8, 17.5, 22,  6.5, "TECHNICAL AREA"),
                    "STEERING_ROOM":  (8.0, 24.5, 14,  3.5, "STEERING ROOM"),
                    "PORT_WING":      (24,  6.0,   8,  4.5, "PORT WING"),
                    "STBD_WING":      (33,  6.0,   8,  4.5, "STDB WING"),
                    "CREWMESS":       (24, 11.0,   8,  4.5, "CREWMESS"),
                    "CPT_CABIN":      (33, 11.0,   8,  4.5, "CPT. CABIN"),
                    "HULL":           (0.8,24.5,   7,  3.5, "HULL"),
                }
                
                MAVI = RGBColor(0x00, 0x70, 0xC0)
                SIYAH = RGBColor(0, 0, 0)
                KIRMIZI = RGBColor(0xCC, 0, 0)
                BEYAZ = RGBColor(0xFF, 0xFF, 0xFF)
                GRI = RGBColor(0xF0, 0xF0, 0xF0)
                
                # Her lokasyon için kutu çiz
                for lok, (lx, ly, lw, lh, label) in zones.items():
                    cihaz_listesi = [c for c in data["cihazlar"] if c.get("lokasyon") == lok]
                    if not cihaz_listesi:
                        continue
                    
                    # Dashed çerçeve
                    shape = slide.shapes.add_shape(1, Cm(lx), Cm(ly), Cm(lw), Cm(lh))
                    shape.fill.background()
                    shape.line.color.rgb = MAVI
                    shape.line.width = Pt(1.0)
                    ln = shape.line._ln
                    pd = etree.SubElement(ln, qn('a:prstDash'))
                    pd.set('val', 'dash')
                    
                    # Lokasyon etiketi
                    tb = slide.shapes.add_textbox(Cm(lx+0.1), Cm(ly-0.4), Cm(6), Cm(0.5))
                    tf = tb.text_frame
                    p = tf.paragraphs[0]
                    run = p.add_run()
                    run.text = label
                    run.font.size = Pt(8)
                    run.font.bold = True
                    run.font.color.rgb = MAVI
                    
                    # Cihazları yerleştir
                    max_col = max(1, int((lw - 0.4) / 3.4))
                    cx = lx + 0.3
                    cy = ly + 0.8
                    col_idx = 0
                    
                    for cihaz in cihaz_listesi:
                        if col_idx >= max_col:
                            col_idx = 0
                            cx = lx + 0.3
                            cy += 4.0
                        
                        # Cihaz kutusu (gri)
                        box = slide.shapes.add_shape(1, Cm(cx), Cm(cy), Cm(3.0), Cm(2.8))
                        box.fill.solid()
                        box.fill.fore_color.rgb = GRI
                        box.line.color.rgb = RGBColor(0xCC, 0xCC, 0xCC)
                        box.line.width = Pt(0.5)
                        
                        # Model adı
                        tf2 = box.text_frame
                        tf2.word_wrap = True
                        p2 = tf2.paragraphs[0]
                        p2.alignment = PP_ALIGN.CENTER
                        r2 = p2.add_run()
                        model_text = f"{cihaz.get('marka','')}\n{cihaz.get('model','')}"
                        r2.text = model_text[:30]
                        r2.font.size = Pt(6)
                        r2.font.bold = True
                        r2.font.color.rgb = SIYAH
                        
                        # Güç etiketi
                        guc = cihaz.get("guc", "")
                        if guc:
                            gtb = slide.shapes.add_shape(
                                1, Cm(cx+0.6), Cm(cy+2.2), Cm(1.8), Cm(0.45)
                            )
                            gtb.fill.solid()
                            gtb.fill.fore_color.rgb = KIRMIZI
                            gtb.line.fill.background()
                            gtf = gtb.text_frame
                            gp = gtf.paragraphs[0]
                            gp.alignment = PP_ALIGN.CENTER
                            gr = gp.add_run()
                            gr.text = guc
                            gr.font.size = Pt(5)
                            gr.font.bold = True
                            gr.font.color.rgb = BEYAZ
                        
                        # Etiket (altında)
                        etiket = cihaz.get("etiket", cihaz.get("model", ""))
                        etb = slide.shapes.add_textbox(Cm(cx), Cm(cy+2.7), Cm(3.0), Cm(0.7))
                        etf = etb.text_frame
                        etf.word_wrap = True
                        ep = etf.paragraphs[0]
                        ep.alignment = PP_ALIGN.CENTER
                        er = ep.add_run()
                        er.text = etiket.replace('\n', ' ')[:25]
                        er.font.size = Pt(5)
                        er.font.color.rgb = SIYAH
                        
                        cx += 3.2
                        col_idx += 1
                
                # Legend
                legend_x, legend_y = 33.5, 17.0
                lg_bg = slide.shapes.add_shape(1, Cm(legend_x), Cm(legend_y), Cm(7.5), Cm(5.5))
                lg_bg.fill.solid()
                lg_bg.fill.fore_color.rgb = BEYAZ
                lg_bg.line.color.rgb = SIYAH
                lg_bg.line.width = Pt(0.5)
                
                kablolar = [
                    (RGBColor(0,0x88,0),    "Ethernet Cable"),
                    (RGBColor(0xFF,0xB8,0), "Display Cable"),
                    (RGBColor(0xFF,0x66,0), "Simnet Cable"),
                    (RGBColor(0xCC,0,0xCC), "NMEA2000 Cable"),
                    (RGBColor(0xCC,0,0),    "NMEA0183 Cable"),
                    (RGBColor(0x22,0x22,0x22), "Coax/LIYCY Cable"),
                ]
                
                for i, (renk, etiket) in enumerate(kablolar):
                    iy = legend_y + 0.5 + i * 0.75
                    cizgi = slide.shapes.add_shape(1, Cm(legend_x+0.3), Cm(iy+0.25), Cm(1.5), Cm(0.1))
                    cizgi.fill.solid()
                    cizgi.fill.fore_color.rgb = renk
                    cizgi.line.fill.background()
                    
                    ltb = slide.shapes.add_textbox(Cm(legend_x+2.1), Cm(iy), Cm(5), Cm(0.6))
                    ltf = ltb.text_frame
                    lp = ltf.paragraphs[0]
                    lr = lp.add_run()
                    lr.text = etiket
                    lr.font.size = Pt(7)
                    lr.font.color.rgb = SIYAH
                
                # Başlık bloğu
                blok_y = 27.8
                blok = slide.shapes.add_shape(1, Cm(0), Cm(blok_y), Cm(42), Cm(1.8))
                blok.fill.background()
                blok.line.color.rgb = SIYAH
                blok.line.width = Pt(0.75)
                
                bilgiler = [
                    (0, 7, data["proje"].get("gemi", vessel), 8),
                    (7, 7, data["proje"].get("proje_no", project_no), 7),
                    (14, 14, "SIMRAD NAVIGATION SYSTEM LAYOUT", 9),
                    (28, 7, "PROMAR DENİZ MALZEMELERİ", 7),
                    (35, 7, "", 7),
                ]
                
                for bx, bw, metin, bfs in bilgiler:
                    btb = slide.shapes.add_textbox(Cm(bx+0.2), Cm(blok_y+0.1), Cm(bw), Cm(1.6))
                    btf = btb.text_frame
                    bp = btf.paragraphs[0]
                    bp.alignment = PP_ALIGN.CENTER
                    br = bp.add_run()
                    br.text = metin
                    br.font.size = Pt(bfs)
                    br.font.color.rgb = SIYAH
                
                # Kaydet
                out_path = tempfile.mktemp(suffix=".pptx")
                prs.save(out_path)
                
                with open(out_path, "rb") as f:
                    pptx_data = f.read()
                os.unlink(out_path)
                
                st.success("✅ PPTX hazır!")
                st.download_button(
                    "⬇️ PPTX İndir",
                    pptx_data,
                    file_name=f"{vessel.replace(' ','_')}_NAV_LAYOUT.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    type="primary"
                )
                
            except Exception as e:
                st.error(f"PPTX oluşturma hatası: {e}")
                import traceback
                st.code(traceback.format_exc())
    
    # JSON görüntüle
    with st.expander("🔧 Ham JSON verisi"):
        st.json(data)

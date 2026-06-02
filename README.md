# 🚢 NavDiagram

> AI-powered navigation single-line diagram generator for marine systems.

NavDiagram is a Streamlit web application that reads a vessel's equipment list (PDF or Excel) and automatically generates a professional **Promar-format navigation layout diagram** in PowerPoint — powered by Google Gemini AI.

---

## ✨ Features

- 📄 **PDF & Excel support** — Upload any material list format
- 🤖 **AI-powered analysis** — Google Gemini detects and classifies each device automatically
- 🗺️ **Zone-based layout** — Devices are placed by location: Mast, Bridge Console, Technical Area, Steering Room, Wings, Hull, and more
- 🎨 **Color-coded cable legend** — Ethernet, NMEA2000, NMEA0183, SimNet, Display cables
- 📊 **Editable before export** — Review and correct device locations before generating the diagram
- 📥 **PPTX export** — Download a ready-to-use PowerPoint diagram in Promar format

---

## 🖥️ Supported Equipment Brands

| Brand | Brand | Brand |
|-------|-------|-------|
| SIMRAD | SAILOR | NAVICO |
| COMNAV | PHONTECH | JOTRON |
| INTELLIAN | FLIR | and more |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- A [Google Gemini API key](https://aistudio.google.com/app/apikey)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/ardacelikk34-hue/navidiagram.git
cd navidiagram

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
streamlit run app.py
```

### Usage

1. Open the app in your browser (default: `http://localhost:8501`)
2. Enter your **Gemini API Key** in the sidebar
3. Upload a **PDF or Excel** equipment list
4. Enter the **vessel name** and **project number**
5. Click **"AI ile Analiz Et"** to detect devices
6. Review and adjust device locations if needed
7. Click **"PPTX Şeması Oluştur"** and download your diagram

---

## 📁 Project Structure

```
navidiagram/
├── app.py              # Main Streamlit application
├── requirements.txt    # Python dependencies
└── README.md
```

---

## 🤝 Contributing

Contributions are welcome! Here's how to get started:

1. **Fork** this repository
2. **Create a branch** for your feature
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** and commit them
   ```bash
   git add .
   git commit -m "Add: describe your change"
   ```
4. **Push** to your fork
   ```bash
   git push origin feature/your-feature-name
   ```
5. Open a **Pull Request** on GitHub

### Contribution Ideas

- [ ] Support for more equipment brands
- [ ] Auto-cable detection between devices
- [ ] Export to PDF format
- [ ] English / Turkish UI toggle
- [ ] Dark mode support

---

## 📋 Requirements

See [`requirements.txt`](requirements.txt) for the full list. Key dependencies:

| Package | Purpose |
|---------|---------|
| `streamlit` | Web UI framework |
| `google-generativeai` | Gemini AI integration |
| `pdfplumber` | PDF text extraction |
| `openpyxl` | Excel file reading |
| `python-pptx` | PowerPoint diagram generation |

---

## 📄 License

This project is intended for use by marine equipment companies and integrators. All rights reserved © 2025 ardacelikk34-hue.

---

## 👤 Author

**Arda Çelik**
- GitHub: [@ardacelikk34-hue](https://github.com/ardacelikk34-hue)

---

> Built for marine navigation professionals 🌊

# 💊 Pharma Knowledge Hub

A comprehensive pharmaceutical knowledge portal built with Streamlit, featuring real-time data from multiple verified APIs.

![Python](https://img.shields.io/badge/python-v3.8+-blue.svg)
![Streamlit](https://img.shields.io/badge/streamlit-v1.32+-red.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## 🌟 Features

### 📰 **Pharma News**
- Latest pharmaceutical industry news from NewsAPI
- Search and filter by keywords
- Real-time updates from global sources

### 📚 **Research Papers**
- Search PubMed database for scientific papers
- Access abstracts and citations
- Links to full-text articles

### 📊 **Analytics Dashboard**
- Real-time KPIs (FDA approvals, clinical trials, research papers)
- Interactive charts and visualizations
- Daily pharmaceutical industry metrics

### 💊 **Drug Information**
- Comprehensive drug data from FDA OpenFDA
- Search by brand or generic names
- Side effects, indications, warnings, and manufacturer info

### 🔬 **Clinical Trials**
- Search ClinicalTrials.gov database
- Filter by condition, phase, and status
- Direct links to trial details

### 🛡️ **Regulatory Updates**
- FDA recalls and enforcement actions
- Color-coded by severity (Class I/II/III)
- Real-time regulatory alerts

### 🏢 **Company News**
- Track 16 major pharmaceutical companies
- Company-specific news feeds
- Quick-access buttons for top pharma companies

### 📅 **Events & Opportunities**
- **Optimized Fetching**: Advanced single-pass queries for Hackathons, Conferences, and Workshops
- **Smart Scoring AI**: Ranks events by dates, actionability (e.g., "register"), and relevance
- **Auto-Fallback**: Ensures no empty tabs by gracefully degrading to recent news

### 🏢 **Company Knowledge (Agentic RAG)**
- Upload company PDF/TXT documents and ask questions via AI
- **Agentic RAG pipeline**: query rewrite → retrieval → relevance gate → answer
- **Retrieval stack**: Neo4j vector index + hybrid fallback + context expansion
- **Embedding model**: `sentence-transformers/all-MiniLM-L6-v2`
- **Groq LLM**: uses Llama 3.3 70B for context-grounded answers
- Prioritizes uploaded-document grounding and shows retrieval trace in UI
- Chat-style interface with conversation history

### 💬 **AI Chatbot**
- Powered by Groq AI (Llama 3.1 70B)
- Pharma domain expertise
- Ask questions about drugs, trials, regulations, and more

## 🎨 Premium UI/UX

- **Dark/Light Theme Toggle** - Instant theme switching
- **Gradient Design** - Modern indigo/purple gradients
- **Glassmorphism Effects** - Beautiful transparent cards
- **Smooth Animations** - Hover effects and fade-ins
- **Responsive Layout** - Mobile-friendly design
- **Interactive Charts** - Plotly visualizations

## 🚀 Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Setup

1. **Clone the repository**
```bash
git clone https://github.com/ThanusreeJ/Pharma_knowledge_portal.git
cd Pharma_knowledge_portal
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure API keys (Optional but recommended)**

Create a `.env` file in the project root:
```env
NEWSAPI_KEY=your_newsapi_key_here
OPENFDA_KEY=your_openfda_key_here
GROQ_API_KEY=your_groq_api_key_here
```

**Get free API keys:**
- **NewsAPI**: https://newsapi.org/register
- **OpenFDA**: https://open.fda.gov/apis/authentication/
- **Groq AI**: https://console.groq.com/

> **Note**: The app works without API keys but has lower rate limits. NewsAPI key is recommended for better news coverage. Groq API key is required for the chatbot feature.

4. **Run the application**
```bash
streamlit run app.py
```

The app will open automatically at **http://localhost:8501**

## 📁 Project Structure

```
Pharma_knowledge_portal/
├── app.py                      # Main Streamlit application
├── config.py                   # Configuration & API endpoints
├── requirements.txt            # Python dependencies
├── .env.example               # API keys template
├── .gitignore                 # Git ignore rules
├── README.md                  # This file
│
├── tabs/                      # Dashboard tabs/pages
│   ├── pharma_news.py        # Pharma News tab
│   ├── research_papers.py    # Research Papers tab
│   ├── analytics.py          # Analytics Dashboard
│   ├── drug_info.py          # Drug Information tab
│   ├── clinical_trials.py    # Clinical Trials tab
│   ├── regulatory.py         # Regulatory Updates tab
│   ├── company_news.py       # Company News tab
│   ├── events.py             # Events & Opportunities
│   ├── company_knowledge.py  # Company Knowledge (RAG Q&A)
│   └── chatbot.py            # AI Chatbot tab
│
├── utils/                     # Utility functions
│   ├── api_client.py         # HTTP client with retry logic
│   ├── data_fetchers.py      # API data fetchers (cached)
│   └── formatters.py         # Data formatting utilities
│
├── components/                # Reusable UI components
│   └── cards.py              # KPI, news, paper, event cards
│
├── styles/                    # Custom styling
│   └── custom.css            # Premium dark/light themes
│
└── data/                      # Static data
    └── events.json           # Curated pharma events
```

## 🔌 Data Sources

| Source | Purpose | Status |
|--------|---------|--------|
| **NewsAPI** | Pharmaceutical news | ✅ Working |
| **OpenFDA** | Drug information & regulatory data | ✅ Working |
| **ClinicalTrials.gov** | Clinical trials database | ✅ Working |
| **PubMed E-utilities** | Research papers | ✅ Working |
| **Groq AI** | Chatbot & Agentic RAG answers | ✅ Working |
| **Neo4j** | Document graph + vector similarity retrieval | ✅ Working |
| **Sentence Transformers** | Embeddings (`all-MiniLM-L6-v2`) | ✅ Working |

All APIs are free and publicly accessible. Optional API keys provide higher rate limits.

## 🎯 Usage

### Navigation
Use the sidebar menu to switch between tabs:
- Click any icon to navigate to that section
- All data loads dynamically from live APIs

### Theme Switching
- Click **🌙 Dark** for dark mode
- Click **☀️ Light** for light mode
- Changes apply instantly

### Search & Filters
- Each tab has specific search/filter options
- Results update in real-time
- Cached for optimal performance

### Company Knowledge (Agentic RAG)
- Upload a PDF or TXT document via the sidebar
- Ask questions in the chat with agentic retrieval and relevance checks
- Clear context anytime with the sidebar button
- Requires Groq API key

### Chatbot
- Ask questions in natural language
- Get pharma domain-specific answers
- Requires Groq API key

## 🛠️ Technologies Used

- **Streamlit** - Web framework
- **Python 3.8+** - Backend language
- **Requests** - HTTP client
- **Pandas** - Data manipulation
- **Plotly** - Interactive visualizations
- **Groq AI** - Language model for chatbot & RAG
- **Neo4j** - Graph database + vector index retrieval for Company Knowledge
- **Sentence Transformers** - Document and query embeddings (`all-MiniLM-L6-v2`)
- **langchain-text-splitters** - Document chunking utility
- **NewsAPI** - News aggregation
- **OpenFDA** - FDA data access
- **PubMed E-utilities** - Biomedical literature

## 📝 License

MIT License - see LICENSE file for details

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## ⚠️ Disclaimer

This application is for informational and educational purposes only. Always consult healthcare professionals for medical advice. Data is sourced from official APIs but should not be used for clinical decision-making.

## 📧 Contact

**Developer**: Thanusree J  
**Repository**: https://github.com/ThanusreeJ/Pharma_knowledge_portal

---

⭐ **Star this repository if you find it helpful!**

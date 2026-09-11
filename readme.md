# CV Extractor — Frontend

Frontend application for extracting structured information from CV/Resume PDF files using **Streamlit**.

## Links

- **Website:** [CV Extractor](https://cv-extractor-by-derbi.streamlit.app)
- **Backend:** [Hugging Face Backend](https://huggingface.co/spaces/quinderbi/cv-extractor)

## Flow

```text
PDF Upload
    ↓
Extract Raw Text
    ↓
Gradio Client
    ↓
Hugging Face Backend
    ↓
Structured CV Data
    ↓
Display in Form
```

## Tech Stack

- **Streamlit** — Web application
- **Python** — Application development
- **PDF Parser** — Extract text from PDF
- **Gradio Client** — Connect to backend
- **Hugging Face** — Backend hosting

## Installation

```bash
git clone https://github.com//quinderbi/cv-extractor.git
cd cv-extracttor

pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

## Architecture

This repository contains the **frontend** only.  
The CV extraction model and inference process are handled by a separate **Gradio backend hosted on Hugging Face**.

```text
Streamlit Frontend
       │
       │ Gradio Client
       ▼
Hugging Face Backend
       │
       ▼
CV Extraction Model
```

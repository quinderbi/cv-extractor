import streamlit as st
from gradio_client import Client

API_URL = "quinderbi/cv-extractor"

def extract_cv_text(cv_text):
    try:
        client = Client(API_URL)
        result = client.predict(cv_text, api_name="/generate_cv_json")
        return result
    except Exception as e:
        raise RuntimeError(f"Failed to extract text from CV: {e}")
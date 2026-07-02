from __future__ import annotations

import os
from pathlib import Path

import requests
import streamlit as st

BACKEND_URL = os.getenv("KIDSPARK_BACKEND_URL", "http://localhost:8001")
OPENAI_KEY_FILE = Path(__file__).resolve().parent / "openai.key"

st.set_page_config(page_title="BrickSmart", page_icon=":bricks:", layout="wide")

st.markdown(
    """
    <style>
    [data-testid="stSidebarNav"] { display: none; }
    .home-title {
        font-size: 2.2rem;
        font-weight: 900;
        letter-spacing: 0;
        margin-bottom: .25rem;
    }
    .home-subtitle {
        color: #657080;
        font-size: 1.02rem;
        margin-bottom: 2rem;
    }
    .home-card {
        border: 1px solid #dfe7ef;
        border-radius: 8px;
        padding: 1.25rem;
        background: #ffffff;
    }
    div[data-testid="stButton"] button {
        border-radius: 8px;
        font-weight: 800;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def masked_key(value: str) -> str:
    if not value:
        return "Not configured"
    return f"{value[:7]}...{value[-4:]}" if len(value) > 12 else "Configured"


def read_key() -> str:
    if OPENAI_KEY_FILE.exists():
        try:
            return OPENAI_KEY_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return ""


def backend_key_status() -> dict:
    try:
        response = requests.get(f"{BACKEND_URL}/api/v1/settings/openai-key", timeout=8)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return {"configured": False, "masked": ""}


def save_key(value: str) -> None:
    key = value.strip()
    if not key:
        st.warning("Paste an OpenAI API key before saving.")
        return
    OPENAI_KEY_FILE.write_text(key, encoding="utf-8")
    try:
        requests.post(f"{BACKEND_URL}/api/v1/settings/openai-key", json={"api_key": key}, timeout=15).raise_for_status()
    except requests.RequestException:
        st.warning("Saved locally. Restart or reconnect the backend to use the new key there.")
    else:
        st.success("OpenAI key saved for BrickSmart.")


st.markdown("<div class='home-title'>BrickSmart</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='home-subtitle'>Set your OpenAI key once, then start the KidSpark teacher workflow.</div>",
    unsafe_allow_html=True,
)

left, right = st.columns([1, 1])
with left:
    st.markdown("<div class='home-card'>", unsafe_allow_html=True)
    st.subheader("OpenAI API Key")
    current = read_key()
    backend_status = backend_key_status()
    status_text = masked_key(current) if current else backend_status.get("masked") or "Not configured"
    st.caption(f"Status: {status_text}")
    entered = st.text_input("OpenAI API key", value=current, type="password", placeholder="sk-...")
    if st.button("Save OpenAI Key", type="primary", use_container_width=True):
        save_key(entered)
    st.markdown("</div>", unsafe_allow_html=True)

with right:
    st.markdown("<div class='home-card'>", unsafe_allow_html=True)
    st.subheader("KidSpark AI")
    st.write("Turn a story into a teacher-reviewed BrickSmart build, lesson plan, activity guide, and slide companion.")
    st.page_link("pages/kidspark.py", label="Open KidSpark", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

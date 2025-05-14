import streamlit as st
from utils import configure_llm, configure_user_session

st.set_page_config(
    page_title="BrickSmart",
    page_icon='🧱',
    layout='wide'
)

st.header("🧱 BrickSmart")
st.write("""
欢迎来到 BrickSmart！
""")
configure_user_session()
configure_llm()


st.page_link('./pages/step1.py', label='点击这里开始!', icon="🔥", use_container_width=True)
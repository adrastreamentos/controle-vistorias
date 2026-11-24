import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Teste Conexão Supabase")
st.title("Controle de Vistorias - Teste Supabase")

url = st.secrets.get("SUPABASE_URL", "").strip()
key = st.secrets.get("SUPABASE_KEY", "").strip()

if not url or not key:
    st.error("Faltam SUPABASE_URL ou SUPABASE_KEY nos Secrets.")
else:
    try:
        supabase = create_client(url, key)
        st.success(f"Cliente Supabase criado com sucesso para: {url}")
    except Exception as e:
        st.error(f"Erro ao conectar: {e}")

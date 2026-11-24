url_lida = st.secrets.get("SUPABASE_URL", "")
chave_lida = st.secrets.get("SUPABASE_KEY", "")

st.write("URL lida:", repr(url_lida))
st.write("Tamanho da chave:", len(chave_lida))

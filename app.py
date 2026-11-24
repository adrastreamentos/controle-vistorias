import io
import uuid
from datetime import date, datetime
import pandas as pd
from PIL import Image
from fpdf import FPDF
import streamlit as st
from supabase import create_client, Client

st.set_page_config(
    page_title="Controle de Vistorias",
    page_icon="🚗",
    layout="wide",
)

ROXO = "#3B185F"
VERMELHO = "#8E1616"
CINZA_CLARO = "#F4F5F7"

st.markdown(
    f"""
    <style>
        .stApp {{
            background-color: {CINZA_CLARO};
        }}
        h1, h2, h3 {{
            color: {ROXO};
        }}
        .stButton>button[kind="primary"] {{
            background-color: {ROXO};
            border-color: {ROXO};
        }}
        .stButton>button[kind="primary"]:hover {{
            background-color: {VERMELHO};
            border-color: {VERMELHO};
        }}
    </style>
    """,
    unsafe_allow_html=True,
)

BUCKET_FOTOS = "fotos-vistorias"


@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


def carregar_tabela(nome_tabela: str) -> pd.DataFrame:
    sb = get_supabase()
    resp = sb.table(nome_tabela).select("*").execute()
    dados = resp.data or []
    return pd.DataFrame(dados)


def upload_foto_vistoria(arquivo_uploaded, prefixo: str) -> str | None:
    if arquivo_uploaded is None:
        return None
    sb = get_supabase()
    img = Image.open(arquivo_uploaded)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.thumbnail((1600, 1600))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    conteudo = buf.getvalue()

    nome_arquivo = f"{prefixo}_{date.today().isoformat()}_{uuid.uuid4().hex[:8]}.jpg"
    sb.storage.from_(BUCKET_FOTOS).upload(
        path=nome_arquivo,
        file=conteudo,
        file_options={"content-type": "image/jpeg", "upsert": "true"},
    )
    return sb.storage.from_(BUCKET_FOTOS).get_public_url(nome_arquivo)


def gerar_pdf_os(os_row: dict, fotos_urls: list[str]) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "RELATORIO DE VISTORIA - OS", ln=True)

    pdf.set_font("Helvetica", "", 10)
    for k, v in os_row.items():
        if v is not None and str(v).strip() != "":
            linha = f"{k}: {v}".encode("latin-1", "replace").decode("latin-1")
            pdf.cell(0, 6, linha, ln=True)

    for url in fotos_urls:
        if url:
            pdf.ln(3)
            pdf.cell(0, 6, f"Foto: {url}".encode("latin-1", "replace").decode("latin-1"), ln=True)

    out = pdf.output()
    return bytes(out) if isinstance(out, (bytes, bytearray)) else out.encode("latin-1")


st.title("Controle de Vistorias")

menu = st.sidebar.radio(
    "Navegação",
    ["Agenda", "Ordens de Serviço (OS)", "Empresas Parceiras", "Financeiro & PDF"],
)

try:
    df_empresas = carregar_tabela("vistoria_empresas")
    df_agenda = carregar_tabela("vistoria_agenda")
    df_os = carregar_tabela("vistoria_os")
except Exception as e:
    st.error(f"Erro ao conectar ao Supabase: {e}")
    st.info("Configure SUPABASE_URL e SUPABASE_KEY em .streamlit/secrets.toml ou nos Secrets do app.")
    st.stop()

if menu == "Agenda":
    st.subheader("Agenda de Vistorias")
    if df_agenda.empty:
        st.info("Nenhum agendamento encontrado em `vistoria_agenda`.")
    else:
        st.dataframe(df_agenda, use_container_width=True)

elif menu == "Ordens de Serviço (OS)":
    st.subheader("Ordens de Serviço e Fotos")
    if df_os.empty:
        st.info("Nenhuma OS encontrada em `vistoria_os`.")
    else:
        st.dataframe(df_os, use_container_width=True)

    st.markdown("### Enviar Foto de Vistoria")
    col_a, col_b = st.columns(2)
    with col_a:
        ref_os = st.text_input("Referência / Placa / ID da OS", placeholder="Ex: ABC1D23 ou OS-102")
    with col_b:
        foto = st.file_uploader("Selecionar imagem", type=["jpg", "jpeg", "png", "webp"])

    if st.button("Enviar Foto para o Bucket", type="primary"):
        if not ref_os.strip() or foto is None:
            st.warning("Informe a referência da OS e selecione uma foto.")
        else:
            url_foto = upload_foto_vistoria(foto, ref_os.strip().replace(" ", "_"))
            st.success("Foto enviada com sucesso!")
            st.image(url_foto, caption=ref_os.strip(), width=360)
            st.code(url_foto, language="text")

elif menu == "Empresas Parceiras":
    st.subheader("Empresas Parceiras (`vistoria_empresas`)")
    if df_empresas.empty:
        st.info("Nenhuma empresa cadastrada em `vistoria_empresas`.")
    else:
        st.dataframe(df_empresas, use_container_width=True)

elif menu == "Financeiro & PDF":
    st.subheader("Acompanhamento Financeiro e Exportação em PDF")
    if df_os.empty:
        st.info("Sem registros de OS para exibir ou exportar.")
    else:
        st.dataframe(df_os, use_container_width=True)
        indices_sel = st.multiselect(
            "Selecione os índices das OS para gerar PDF individual/lote",
            options=list(df_os.index),
        )
        if st.button("Gerar PDF Selecionado", type="primary") and indices_sel:
            for idx in indices_sel:
                registro = df_os.loc[idx].to_dict()
                pdf_bytes = gerar_pdf_os(registro, [])
                st.download_button(
                    label=f"Baixar PDF — linha {idx}",
                    data=pdf_bytes,
                    file_name=f"vistoria_os_{idx}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf",
                    key=f"dl_{idx}",
                )

import base64
import io
import os
import re
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import quote

import streamlit as st
from PIL import Image
from supabase import Client, create_client

try:
    from fpdf import FPDF
    PDF_DISPONIVEL = True
except ImportError:
    PDF_DISPONIVEL = False


# =========================================================
# CONFIGURAÇÃO DA PÁGINA, FUSO HORÁRIO (BRASIL) E LOGIN
# =========================================================
st.set_page_config(
    page_title="Controle de Vistorias",
    page_icon="🚗",
    layout="centered",
    initial_sidebar_state="collapsed",
)

FUSO_BR = timezone(timedelta(hours=-3))


def agora_br() -> datetime:
    return datetime.now(FUSO_BR)


def hoje_br() -> date:
    return agora_br().date()


LOGIN_USUARIO = "AD Vistoria"
LOGIN_SENHA = "55496449100084"

MESES_PT = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


# =========================================================
# ESTADO INICIAL DA SESSÃO
# =========================================================
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "tema" not in st.session_state:
    st.session_state.tema = "claro"
if "pagina" not in st.session_state:
    st.session_state.pagina = "Agenda"
if "os_importada" not in st.session_state:
    st.session_state.os_importada = None
if "tipo_vistoria_os" not in st.session_state:
    st.session_state.tipo_vistoria_os = "Nova"
if "fin_mes" not in st.session_state:
    st.session_state.fin_mes = hoje_br().month
if "fin_ano" not in st.session_state:
    st.session_state.fin_ano = hoje_br().year
if "agenda_filtro" not in st.session_state:
    st.session_state.agenda_filtro = "Hoje"
if "agenda_data_busca" not in st.session_state:
    st.session_state.agenda_data_busca = None
if "form_emp_ver" not in st.session_state:
    st.session_state.form_emp_ver = 0
if "form_ag_ver" not in st.session_state:
    st.session_state.form_ag_ver = 0
if "form_os_ver" not in st.session_state:
    st.session_state.form_os_ver = 0
if "aviso_sucesso" not in st.session_state:
    st.session_state.aviso_sucesso = None


# =========================================================
# TEMA DINÂMICO (MODO CLARO E MODO ESCURO)
# =========================================================
def aplicar_tema(modo: str):
    if modo == "escuro":
        cores = {
            "bg": "#0F1117",
            "surface": "#191C26",
            "border": "#2E3345",
            "text": "#F3F4F6",
            "muted": "#9CA3AF",
            "input_bg": "#131620",
            "purple": "#5E2285",
            "purple_hover": "#4B1A6B",
            "purple_soft_bg": "#2B193D",
            "purple_soft_text": "#E9D5FF",
            "purple_soft_border": "#4C2570",
            "red": "#C8102E",
            "red_hover": "#A50D26",
            "red_soft_bg": "#3A1820",
            "red_soft_text": "#FCA5A5",
            "green": "#22B85E",
            "green_hover": "#199A4C",
            "green_card_bg": "#10281E",
            "green_card_border": "#1F573C",
            "green_card_text": "#A7F3D0",
            "green_badge_bg": "#153D2A",
            "green_badge_text": "#6EE7B7",
            "sec_btn_bg": "#222634",
            "sec_btn_text": "#E5E7EB",
            "sec_btn_border": "#363C52",
            "shadow": "0 4px 14px rgba(0, 0, 0, 0.35)",
        }
    else:
        cores = {
            "bg": "#F4F5F7",
            "surface": "#FFFFFF",
            "border": "#E5E7EB",
            "text": "#1F2937",
            "muted": "#6B7280",
            "input_bg": "#F9FAFB",
            "purple": "#4E1A6B",
            "purple_hover": "#3D1355",
            "purple_soft_bg": "#EFE6F8",
            "purple_soft_text": "#4E1A6B",
            "purple_soft_border": "#D8C2EE",
            "red": "#C41230",
            "red_hover": "#A10E27",
            "red_soft_bg": "#FDE8EC",
            "red_soft_text": "#B91C1C",
            "green": "#28B85B",
            "green_hover": "#1E9B4B",
            "green_card_bg": "#EAF8EF",
            "green_card_border": "#BCE8CC",
            "green_card_text": "#065F46",
            "green_badge_bg": "#D1FAE5",
            "green_badge_text": "#047857",
            "sec_btn_bg": "#FFFFFF",
            "sec_btn_text": "#374151",
            "sec_btn_border": "#D1D5DB",
            "shadow": "0 2px 10px rgba(17, 24, 39, 0.06)",
        }

    st.markdown(
        f"""
        <style>
        :root {{
            --bg: {cores['bg']};
            --surface: {cores['surface']};
            --border: {cores['border']};
            --text: {cores['text']};
            --muted: {cores['muted']};
            --input-bg: {cores['input_bg']};
            --purple: {cores['purple']};
            --purple-hover: {cores['purple_hover']};
            --purple-soft-bg: {cores['purple_soft_bg']};
            --purple-soft-text: {cores['purple_soft_text']};
            --purple-soft-border: {cores['purple_soft_border']};
            --red: {cores['red']};
            --red-hover: {cores['red_hover']};
            --red-soft-bg: {cores['red_soft_bg']};
            --red-soft-text: {cores['red_soft_text']};
            --green: {cores['green']};
            --green-hover: {cores['green_hover']};
            --green-card-bg: {cores['green_card_bg']};
            --green-card-border: {cores['green_card_border']};
            --green-card-text: {cores['green_card_text']};
            --green-badge-bg: {cores['green_badge_bg']};
            --green-badge-text: {cores['green_badge_text']};
            --sec-btn-bg: {cores['sec_btn_bg']};
            --sec-btn-text: {cores['sec_btn_text']};
            --sec-btn-border: {cores['sec_btn_border']};
            --shadow: {cores['shadow']};
        }}

        .stApp, [data-testid="stAppViewContainer"] {{
            background-color: var(--bg) !important;
            color: var(--text) !important;
        }}
        [data-testid="stHeader"] {{
            background-color: transparent !important;
            height: 2.8rem !important;
        }}
        .block-container {{
            max-width: 900px !important;
            padding-top: 4.2rem !important;
            padding-bottom: 3rem !important;
        }}

        h1, h2, h3, h4, h5, h6,
        .stMarkdown p, .stMarkdown li,
        label, [data-testid="stWidgetLabel"] p,
        [data-testid="stCheckbox"] label p,
        [data-testid="stRadio"] label p {{
            color: var(--text) !important;
        }}
        .stCaption, [data-testid="stCaptionContainer"] p {{
            color: var(--muted) !important;
        }}

        [data-testid="stForm"] {{
            background-color: var(--surface) !important;
            border: 1px solid var(--border) !important;
            border-radius: 18px !important;
            padding: 18px 18px 16px 18px !important;
            box-shadow: var(--shadow) !important;
        }}

        [data-testid="stVerticalBlockBorderWrapper"] {{
            background-color: var(--surface) !important;
            border-color: var(--border) !important;
            border-radius: 18px !important;
            box-shadow: var(--shadow) !important;
        }}

        [data-baseweb="input"],
        [data-baseweb="base-input"],
        [data-baseweb="select"] > div,
        [data-testid="stFileUploader"] section {{
            background-color: var(--input-bg) !important;
            border-color: var(--border) !important;
            border-radius: 10px !important;
            color: var(--text) !important;
        }}
        input, textarea, [data-baseweb="select"] span {{
            color: var(--text) !important;
            -webkit-text-fill-color: var(--text) !important;
        }}

        [data-testid="stExpander"] {{
            background-color: var(--surface) !important;
            border: 1px solid var(--border) !important;
            border-radius: 14px !important;
            margin-bottom: 10px;
            box-shadow: var(--shadow);
        }}
        [data-testid="stExpander"] summary p {{
            color: var(--text) !important;
            font-weight: 700;
        }}

        .cv-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 15px 18px;
            margin-bottom: 10px;
            box-shadow: var(--shadow);
        }}
        .cv-card-title {{
            font-weight: 700;
            font-size: 1.02rem;
            color: var(--text);
        }}
        .cv-card-sub {{
            color: var(--muted);
            font-size: 0.86rem;
            margin-top: 3px;
        }}
        .cv-card-green {{
            background: var(--green-card-bg);
            border: 1px solid var(--green-card-border);
            border-radius: 16px;
            padding: 15px 18px;
            margin-bottom: 10px;
        }}
        .cv-card-green-title {{
            font-weight: 700;
            font-size: 1.02rem;
            color: var(--green-card-text);
        }}
        .cv-card-green-sub {{
            color: var(--green-card-text);
            opacity: 0.88;
            font-size: 0.86rem;
            margin-top: 4px;
        }}

        .cv-hero-purple {{
            background: linear-gradient(135deg, #3D1259 0%, #561D7A 55%, #6E2899 100%);
            color: #FFFFFF;
            border-radius: 18px;
            padding: 20px 22px;
            margin: 12px 0 16px 0;
            box-shadow: 0 8px 22px rgba(78, 26, 107, 0.30);
        }}
        .cv-hero-label {{
            font-size: 0.92rem;
            color: rgba(255, 255, 255, 0.92);
            margin-bottom: 2px;
        }}
        .cv-hero-value {{
            font-size: 2.15rem;
            font-weight: 800;
            letter-spacing: -0.5px;
            color: #FFFFFF;
            margin: 2px 0 4px 0;
        }}
        .cv-hero-sub {{
            font-size: 0.85rem;
            color: rgba(255, 255, 255, 0.86);
            margin-bottom: 12px;
        }}
        .cv-pill-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .cv-pill-light {{
            background: #F3E8FF;
            color: #4E1A6B;
            font-weight: 700;
            font-size: 0.8rem;
            padding: 4px 12px;
            border-radius: 999px;
            display: inline-block;
        }}
        .cv-pill-green {{
            background: #28B85B;
            color: #FFFFFF;
            font-weight: 700;
            font-size: 0.8rem;
            padding: 4px 12px;
            border-radius: 999px;
            display: inline-block;
        }}

        .cv-badge-purple {{
            background: var(--purple-soft-bg);
            color: var(--purple-soft-text);
            font-weight: 700;
            font-size: 0.77rem;
            padding: 3px 10px;
            border-radius: 999px;
            display: inline-block;
        }}
        .cv-badge-red {{
            background: var(--red-soft-bg);
            color: var(--red-soft-text);
            font-weight: 700;
            font-size: 0.77rem;
            padding: 3px 10px;
            border-radius: 999px;
            display: inline-block;
        }}
        .cv-badge-green {{
            background: var(--green-badge-bg);
            color: var(--green-badge-text);
            font-weight: 700;
            font-size: 0.77rem;
            padding: 3px 10px;
            border-radius: 999px;
            display: inline-block;
        }}

        .cv-banner-import {{
            background: var(--purple-soft-bg);
            color: var(--purple-soft-text);
            border: 1px solid var(--purple-soft-border);
            border-radius: 12px;
            padding: 11px 14px;
            font-weight: 700;
            margin-bottom: 12px;
        }}

        .cv-month-bar {{
            text-align: center;
            font-weight: 700;
            font-size: 1.08rem;
            padding: 7px 10px;
            background: var(--surface);
            color: var(--text);
            border: 1px solid var(--border);
            border-radius: 12px;
            box-shadow: var(--shadow);
        }}

        .login-box {{
            text-align: center;
            padding: 8px 0 12px 0;
        }}
        .login-icon {{
            width: 68px;
            height: 68px;
            background: var(--purple-soft-bg);
            border: 2px solid var(--purple-soft-border);
            border-radius: 18px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 32px;
            margin-bottom: 10px;
        }}
        .login-title {{
            color: var(--purple-soft-text) !important;
            font-size: 1.65rem;
            font-weight: 800;
            margin: 0;
        }}
        .login-sub-title {{
            color: var(--text);
            font-size: 1.15rem;
            font-weight: 700;
            margin-top: 10px;
        }}
        .login-sub {{
            color: var(--muted);
            font-size: 0.9rem;
            margin-top: 2px;
        }}

        /* Botões Principais (Roxo Fechado) */
        div.stButton > button[kind="primary"],
        div.stFormSubmitButton > button[kind="primary"],
        div.stDownloadButton > button[kind="primary"] {{
            background-color: var(--purple) !important;
            border: 1px solid var(--purple) !important;
            color: #FFFFFF !important;
            border-radius: 11px !important;
            font-weight: 700 !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }}
        div.stButton > button[kind="primary"] p,
        div.stFormSubmitButton > button[kind="primary"] p,
        div.stDownloadButton > button[kind="primary"] p {{
            color: #FFFFFF !important;
            white-space: nowrap !important;
        }}
        div.stButton > button[kind="primary"]:hover,
        div.stFormSubmitButton > button[kind="primary"]:hover {{
            background-color: var(--purple-hover) !important;
            border-color: var(--purple-hover) !important;
        }}

        /* Botões Secundários */
        div.stButton > button[kind="secondary"],
        div.stFormSubmitButton > button[kind="secondary"],
        div.stDownloadButton > button[kind="secondary"] {{
            background-color: var(--sec-btn-bg) !important;
            border: 1px solid var(--sec-btn-border) !important;
            color: var(--sec-btn-text) !important;
            border-radius: 11px !important;
            font-weight: 600 !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }}
        div.stButton > button[kind="secondary"] p,
        div.stFormSubmitButton > button[kind="secondary"] p,
        div.stDownloadButton > button[kind="secondary"] p {{
            color: var(--sec-btn-text) !important;
            white-space: nowrap !important;
        }}

        /* Botão VERMELHO específico (Concluir Ordem de Serviço) */
        div[data-testid="stElementContainer"]:has(.marker-red) + div[data-testid="stElementContainer"] button,
        div.element-container:has(.marker-red) + div.element-container button {{
            background-color: var(--red) !important;
            border: 1px solid var(--red) !important;
            color: #FFFFFF !important;
            border-radius: 11px !important;
            font-weight: 700 !important;
            padding-top: 0.6rem !important;
            padding-bottom: 0.6rem !important;
        }}
        div[data-testid="stElementContainer"]:has(.marker-red) + div[data-testid="stElementContainer"] button p,
        div.element-container:has(.marker-red) + div.element-container button p {{
            color: #FFFFFF !important;
        }}
        div[data-testid="stElementContainer"]:has(.marker-red) + div[data-testid="stElementContainer"] button:hover,
        div.element-container:has(.marker-red) + div.element-container button:hover {{
            background-color: var(--red-hover) !important;
            border-color: var(--red-hover) !important;
        }}

        /* Botão VERDE específico (Marcar como Recebido) */
        div[data-testid="stElementContainer"]:has(.marker-green) + div[data-testid="stElementContainer"] button,
        div.element-container:has(.marker-green) + div.element-container button {{
            background-color: var(--green) !important;
            border: 1px solid var(--green) !important;
            color: #FFFFFF !important;
            border-radius: 11px !important;
            font-weight: 700 !important;
        }}
        div[data-testid="stElementContainer"]:has(.marker-green) + div[data-testid="stElementContainer"] button p,
        div.element-container:has(.marker-green) + div.element-container button p {{
            color: #FFFFFF !important;
        }}
        div[data-testid="stElementContainer"]:has(.marker-green) + div[data-testid="stElementContainer"] button:hover,
        div.element-container:has(.marker-green) + div.element-container button:hover {{
            background-color: var(--green-hover) !important;
            border-color: var(--green-hover) !important;
        }}

        .wa-btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 5px;
            background-color: #25D366;
            color: #FFFFFF !important;
            text-decoration: none !important;
            font-weight: 700;
            font-size: 0.82rem;
            padding: 6px 12px;
            border-radius: 999px;
            white-space: nowrap;
        }}
        .wa-btn:hover {{
            background-color: #1EBE5D;
            color: #FFFFFF !important;
        }}

        .brand-bar {{
            font-weight: 800;
            font-size: 1.25rem;
            color: var(--purple-soft-text);
            padding-top: 6px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


aplicar_tema(st.session_state.tema)


# =========================================================
# CONEXÃO SUPABASE E FUNÇÕES AUXILIARES
# =========================================================
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL", "").strip()
    key = st.secrets.get("SUPABASE_KEY", "").strip()
    if not url or not key:
        st.error("Configure SUPABASE_URL e SUPABASE_KEY nos Secrets do Streamlit.")
        st.stop()
    return create_client(url, key)


supabase = get_supabase()


def fmt_moeda(valor: float) -> str:
    try:
        v = float(valor or 0)
    except (TypeError, ValueError):
        v = 0.0
    texto = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def fmt_data_br(data_str: str) -> str:
    if not data_str:
        return "-"
    try:
        return datetime.strptime(str(data_str)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(data_str)


def fmt_data_curta(data_str: str) -> str:
    if not data_str:
        return "-"
    try:
        return datetime.strptime(str(data_str)[:10], "%Y-%m-%d").strftime("%d/%m")
    except ValueError:
        return str(data_str)


def link_whatsapp(telefone: str, mensagem: str = "") -> str:
    digitos = re.sub(r"\D", "", str(telefone or ""))
    if not digitos:
        return ""
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    if mensagem:
        return f"https://wa.me/{digitos}?text={quote(mensagem)}"
    return f"https://wa.me/{digitos}"


def comprimir_imagem_para_base64(arquivo_upload) -> str:
    img = Image.open(arquivo_upload)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.thumbnail((900, 900))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=72, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def base64_para_bytes(b64_str: str) -> bytes:
    return base64.b64decode(b64_str)


def limpar_latin1(texto: str) -> str:
    return str(texto or "").encode("latin-1", "replace").decode("latin-1")


def mostrar_aviso_pendente():
    if st.session_state.aviso_sucesso:
        st.success(st.session_state.aviso_sucesso)
        st.session_state.aviso_sucesso = None


# =========================================================
# CONSULTAS AO BANCO DE DADOS (APENAS TABELAS DE VISTORIAS)
# =========================================================
def carregar_empresas():
    try:
        res = supabase.table("vistorias_empresas").select("*").order("nome").execute()
        return res.data or []
    except Exception as e:
        st.error(f"Erro ao carregar empresas: {e}")
        return []


def carregar_agendamentos(apenas_agendadas=True):
    try:
        q = supabase.table("agendamentos").select("*")
        if apenas_agendadas:
            q = q.eq("status", "Agendada")
        res = q.order("data_agendamento").order("hora_agendamento").execute()
        return res.data or []
    except Exception as e:
        st.error(f"Erro ao carregar agendamentos: {e}")
        return []


def carregar_vistorias(ano=None, mes=None):
    try:
        q = supabase.table("vistorias").select("*")
        if ano and mes:
            inicio = date(ano, mes, 1)
            fim = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
            q = q.gte("data_vistoria", inicio.isoformat()).lt("data_vistoria", fim.isoformat())
        res = q.order("data_vistoria", desc=True).order("id", desc=True).execute()
        return res.data or []
    except Exception as e:
        st.error(f"Erro ao carregar vistorias: {e}")
        return []


# =========================================================
# GERADORES DE PDF (INDIVIDUAL E EM LOTE)
# =========================================================
def gerar_pdf_individual(vistoria: dict) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_fill_color(78, 26, 107)
    pdf.rect(0, 0, 210, 28, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(12, 8)
    pdf.cell(0, 8, limpar_latin1("CONTROLE DE VISTORIAS - ORDEM DE SERVIÇO"), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(12)
    pdf.cell(0, 6, limpar_latin1(f"Relatório Individual | OS #{vistoria.get('id', '')}"), ln=True)

    pdf.set_text_color(31, 41, 55)
    pdf.ln(12)

    campos = [
        ("Empresa Parceira", vistoria.get("empresa_nome", "-")),
        ("Cliente / Segurado", vistoria.get("cliente_nome") or "-"),
        ("Veículo", vistoria.get("veiculo", "-")),
        ("Placa", vistoria.get("placa", "-")),
        ("Data da Vistoria", fmt_data_br(vistoria.get("data_vistoria"))),
        ("Tipo de Vistoria", vistoria.get("tipo_vistoria", "Nova")),
        ("Valor do Serviço", fmt_moeda(vistoria.get("valor", 0))),
        ("Status Financeiro", vistoria.get("status_pagamento", "Pendente")),
    ]
    if vistoria.get("data_recebimento"):
        campos.append(("Data do Recebimento", fmt_data_br(vistoria.get("data_recebimento"))))

    for rotulo, valor in campos:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(52, 8, limpar_latin1(f"{rotulo}:"), border=0)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 8, limpar_latin1(str(valor)), border=0, ln=True)

    if vistoria.get("foto_base64"):
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, limpar_latin1("Registro Fotográfico do Veículo"), ln=True)
        tmp_path = None
        try:
            img_bytes = base64_para_bytes(vistoria["foto_base64"])
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                tmp.write(img_bytes)
                tmp_path = tmp.name
            pdf.image(tmp_path, x=15, w=130)
        except Exception:
            pdf.set_font("Helvetica", "I", 10)
            pdf.cell(0, 8, limpar_latin1("Não foi possível embutir a imagem no PDF."), ln=True)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    pdf.set_y(-20)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(107, 114, 128)
    pdf.cell(
        0,
        8,
        limpar_latin1(f"Emitido em {agora_br().strftime('%d/%m/%Y %H:%M')} - Controle de Vistorias"),
        align="C",
    )
    return bytes(pdf.output())


def gerar_pdf_lote(vistorias: list, titulo_periodo: str, empresa_filtro: str = "Todas") -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.set_fill_color(78, 26, 107)
    pdf.rect(0, 0, 210, 28, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_xy(12, 8)
    pdf.cell(0, 8, limpar_latin1("CONTROLE DE VISTORIAS - RELATÓRIO EM LOTE"), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(12)
    pdf.cell(0, 6, limpar_latin1(f"Período: {titulo_periodo} | Empresa: {empresa_filtro}"), ln=True)

    pdf.set_text_color(31, 41, 55)
    pdf.ln(12)

    total_geral = sum(float(v.get("valor") or 0) for v in vistorias)
    total_recebido = sum(
        float(v.get("valor") or 0) for v in vistorias if v.get("status_pagamento") == "Recebido"
    )
    total_pendente = total_geral - total_recebido

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(
        0,
        7,
        limpar_latin1(
            f"Qtd. Vistorias: {len(vistorias)}   |   Total Geral: {fmt_moeda(total_geral)}   |   "
            f"Recebido: {fmt_moeda(total_recebido)}   |   Pendente: {fmt_moeda(total_pendente)}"
        ),
        ln=True,
    )
    pdf.ln(4)

    pdf.set_fill_color(239, 230, 248)
    pdf.set_text_color(78, 26, 107)
    pdf.set_font("Helvetica", "B", 9)
    colunas = [
        ("Data", 22),
        ("Empresa", 42),
        ("Veículo", 44),
        ("Placa", 22),
        ("Tipo", 20),
        ("Status", 20),
        ("Valor", 20),
    ]
    for nome_col, largura in colunas:
        pdf.cell(largura, 8, limpar_latin1(nome_col), border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_text_color(31, 41, 55)
    pdf.set_font("Helvetica", "", 8.5)
    for v in vistorias:
        pdf.cell(22, 7, limpar_latin1(fmt_data_br(v.get("data_vistoria"))), border=1, align="C")
        pdf.cell(42, 7, limpar_latin1(str(v.get("empresa_nome", ""))[:22]), border=1)
        pdf.cell(44, 7, limpar_latin1(str(v.get("veiculo", ""))[:24]), border=1)
        pdf.cell(22, 7, limpar_latin1(str(v.get("placa", "")).upper()[:10]), border=1, align="C")
        pdf.cell(20, 7, limpar_latin1(str(v.get("tipo_vistoria", "Nova"))[:10]), border=1, align="C")
        pdf.cell(20, 7, limpar_latin1(str(v.get("status_pagamento", "Pendente"))[:10]), border=1, align="C")
        pdf.cell(20, 7, limpar_latin1(fmt_moeda(v.get("valor", 0))), border=1, align="R")
        pdf.ln()

    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, limpar_latin1(f"Total Líquido do Relatório: {fmt_moeda(total_geral)}"), align="R")

    return bytes(pdf.output())


# =========================================================
# BOTÃO CLARO / ESCURO
# =========================================================
def botao_alternar_tema(key_suffix: str = "topo"):
    label_tema = "🌙 Escuro" if st.session_state.tema == "claro" else "☀️ Claro"
    if st.button(label_tema, key=f"toggle_tema_{key_suffix}", use_container_width=True):
        st.session_state.tema = "escuro" if st.session_state.tema == "claro" else "claro"
        st.rerun()


# =========================================================
# TELA 1: ACESSO / LOGIN
# =========================================================
def tela_login():
    t1, t2 = st.columns([3.5, 1.5])
    with t2:
        botao_alternar_tema("login")

    st.markdown(
        """
        <div class="login-box">
            <div class="login-icon">🚗</div>
            <h1 class="login-title">Controle de Vistorias</h1>
            <div class="login-sub-title">Acesso / Login</div>
            <div class="login-sub">Entre com as suas credenciais para continuar</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_esq, col_centro, col_dir = st.columns([0.1, 0.8, 0.1])
    with col_centro:
        with st.form("form_login"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            st.checkbox("Lembrar de mim", value=True)
            entrar = st.form_submit_button("Entrar →", type="primary", use_container_width=True)

            if entrar:
                if (
                    usuario.strip().lower() == LOGIN_USUARIO.lower()
                    and senha.strip() == LOGIN_SENHA
                ):
                    st.session_state.autenticado = True
                    st.session_state.pagina = "Agenda"
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos. Verifique e tente novamente.")

        st.markdown(
            "<p style='text-align:center;color:var(--muted);font-size:0.8rem;margin-top:16px;'>"
            "Vistorias Pro • AD Vistoria</p>",
            unsafe_allow_html=True,
        )


# =========================================================
# TELA 2: EMPRESAS PARCEIRAS
# =========================================================
def tela_empresas():
    st.markdown("### 🤝 Empresas Parceiras")
    mostrar_aviso_pendente()

    ver = st.session_state.form_emp_ver
    with st.expander("➕ Adicionar Nova Empresa", expanded=False):
        with st.form(f"form_nova_empresa_{ver}", clear_on_submit=True):
            nome = st.text_input("Nome da Empresa", key=f"emp_nome_{ver}")
            responsavel = st.text_input("Nome do Responsável", key=f"emp_resp_{ver}")
            whatsapp = st.text_input("Celular (WhatsApp)", key=f"emp_wa_{ver}")
            c1, c2 = st.columns(2)
            with c1:
                dia_pagamento = st.number_input(
                    "Dia do Pagamento",
                    min_value=1,
                    max_value=31,
                    value=15,
                    step=1,
                    key=f"emp_dia_{ver}",
                )
            with c2:
                valor_padrao = st.number_input(
                    "Valor Padrão (R$)",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                    format="%.2f",
                    key=f"emp_val_{ver}",
                )
            salvar = st.form_submit_button("+ Salvar Empresa", type="primary", use_container_width=True)

            if salvar:
                if not nome.strip():
                    st.warning("Informe o nome da empresa.")
                else:
                    try:
                        supabase.table("vistorias_empresas").insert(
                            {
                                "nome": nome.strip(),
                                "responsavel": responsavel.strip(),
                                "whatsapp": whatsapp.strip(),
                                "dia_pagamento": int(dia_pagamento),
                                "valor_padrao": float(valor_padrao),
                            }
                        ).execute()
                        st.session_state.form_emp_ver += 1
                        st.session_state.aviso_sucesso = f"Empresa '{nome.strip()}' cadastrada com sucesso!"
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar empresa: {e}")

    empresas = carregar_empresas()
    st.markdown(f"#### Empresas Cadastradas ({len(empresas)})")

    if not empresas:
        st.info("Nenhuma empresa cadastrada ainda. Clique em 'Adicionar Nova Empresa' acima.")
        return

    for emp in empresas:
        wa_url = link_whatsapp(emp.get("whatsapp", ""))
        wa_html = (
            f'<a class="wa-btn" href="{wa_url}" target="_blank">💬 WhatsApp</a>'
            if wa_url
            else '<span style="color:var(--muted);font-size:0.8rem;">Sem WhatsApp</span>'
        )
        st.markdown(
            f"""
            <div class="cv-card">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
                    <div>
                        <div class="cv-card-title">🏢 {emp['nome']}</div>
                        <div class="cv-card-sub">
                            Resp.: {emp.get('responsavel') or '-'} • Paga dia {int(emp.get('dia_pagamento') or 15):02d} • Padrão: {fmt_moeda(emp.get('valor_padrao', 0))}
                        </div>
                    </div>
                    <div>{wa_html}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander(f"Detalhar / Editar / Excluir — {emp['nome']}"):
            with st.form(f"edit_emp_{emp['id']}_{ver}"):
                e_nome = st.text_input("Nome da Empresa", value=emp["nome"])
                e_resp = st.text_input("Nome do Responsável", value=emp.get("responsavel") or "")
                e_wa = st.text_input("Celular (WhatsApp)", value=emp.get("whatsapp") or "")
                ec1, ec2 = st.columns(2)
                with ec1:
                    e_dia = st.number_input(
                        "Dia do Pagamento", 1, 31, int(emp.get("dia_pagamento") or 15)
                    )
                with ec2:
                    e_val = st.number_input(
                        "Valor Padrão (R$)",
                        min_value=0.0,
                        value=float(emp.get("valor_padrao") or 0.0),
                        step=1.0,
                        format="%.2f",
                    )
                b1, b2 = st.columns(2)
                with b1:
                    atualizar = st.form_submit_button(
                        "Salvar Alterações", type="primary", use_container_width=True
                    )
                with b2:
                    excluir = st.form_submit_button("Excluir Empresa", use_container_width=True)

                if atualizar:
                    supabase.table("vistorias_empresas").update(
                        {
                            "nome": e_nome.strip(),
                            "responsavel": e_resp.strip(),
                            "whatsapp": e_wa.strip(),
                            "dia_pagamento": int(e_dia),
                            "valor_padrao": float(e_val),
                        }
                    ).eq("id", emp["id"]).execute()
                    st.session_state.form_emp_ver += 1
                    st.session_state.aviso_sucesso = f"Alterações de '{e_nome.strip()}' salvas!"
                    st.rerun()
                if excluir:
                    supabase.table("vistorias_empresas").delete().eq("id", emp["id"]).execute()
                    st.session_state.form_emp_ver += 1
                    st.session_state.aviso_sucesso = f"Empresa '{emp['nome']}' removida."
                    st.rerun()


# =========================================================
# TELA 3: AGENDA DE VISTORIAS
# =========================================================
def tela_agenda():
    st.markdown("### 📅 Agenda de Vistorias")
    mostrar_aviso_pendente()

    empresas = carregar_empresas()
    nomes_empresas = [e["nome"] for e in empresas]
    mapa_empresas = {e["nome"]: e for e in empresas}
    hoje = hoje_br()
    amanha = hoje + timedelta(days=1)
    ver = st.session_state.form_ag_ver

    with st.form(f"form_novo_agendamento_{ver}", clear_on_submit=True):
        st.markdown("**📅 Novo Agendamento**")
        if nomes_empresas:
            empresa_sel = st.selectbox("Empresa", nomes_empresas, key=f"ag_emp_{ver}")
        else:
            empresa_sel = st.text_input("Empresa", key=f"ag_emp_txt_{ver}")

        c1, c2 = st.columns(2)
        with c1:
            cliente_nome = st.text_input("Cliente", key=f"ag_cli_{ver}")
        with c2:
            cliente_wa = st.text_input("WhatsApp do Cliente", key=f"ag_wa_{ver}")

        v1, v2 = st.columns([2, 1])
        with v1:
            veiculo = st.text_input("Veículo", key=f"ag_veic_{ver}")
        with v2:
            placa = st.text_input("Placa", key=f"ag_placa_{ver}")

        d1, d2 = st.columns(2)
        with d1:
            data_ag = st.date_input("Data", value=hoje, format="DD/MM/YYYY", key=f"ag_data_{ver}")
        with d2:
            hora_ag = st.time_input("Horário", value=time(9, 0), key=f"ag_hora_{ver}")

        salvar_ag = st.form_submit_button("📅 Salvar na Agenda", type="primary", use_container_width=True)
        if salvar_ag:
            if not empresa_sel or not cliente_nome.strip() or not veiculo.strip() or not placa.strip():
                st.warning("Preencha Empresa, Cliente, Veículo e Placa.")
            else:
                try:
                    supabase.table("agendamentos").insert(
                        {
                            "empresa_id": None,
                            "empresa_nome": empresa_sel.strip(),
                            "cliente_nome": cliente_nome.strip(),
                            "cliente_whatsapp": cliente_wa.strip(),
                            "veiculo": veiculo.strip(),
                            "placa": placa.strip().upper(),
                            "data_agendamento": data_ag.isoformat(),
                            "hora_agendamento": hora_ag.strftime("%H:%M"),
                            "status": "Agendada",
                        }
                    ).execute()
                    st.session_state.form_ag_ver += 1
                    # Direciona automaticamente o filtro para a data agendada
                    if data_ag == hoje:
                        st.session_state.agenda_filtro = "Hoje"
                        st.session_state.agenda_data_busca = None
                    elif data_ag == amanha:
                        st.session_state.agenda_filtro = "Amanhã"
                        st.session_state.agenda_data_busca = None
                    else:
                        st.session_state.agenda_filtro = "Data"
                        st.session_state.agenda_data_busca = data_ag
                    st.session_state.aviso_sucesso = (
                        f"Agendamento salvo para {data_ag.strftime('%d/%m/%Y')} às {hora_ag.strftime('%H:%M')}!"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar agendamento: {e}")

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # Filtros: Hoje, Amanhã, Esta Semana
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    fim_semana = inicio_semana + timedelta(days=6)

    fc1, fc2, fc3 = st.columns(3)
    for col, nome_f in [(fc1, "Hoje"), (fc2, "Amanhã"), (fc3, "Esta Semana")]:
        with col:
            ativo = st.session_state.agenda_filtro == nome_f
            if st.button(
                nome_f,
                key=f"flt_{nome_f}",
                type="primary" if ativo else "secondary",
                use_container_width=True,
            ):
                st.session_state.agenda_filtro = nome_f
                st.session_state.agenda_data_busca = None
                st.rerun()

    # Pesquisa direta por data no calendário
    with st.container(border=True):
        pc1, pc2 = st.columns([2.4, 1.2])
        with pc1:
            valor_cal = st.session_state.agenda_data_busca or hoje
            data_pesquisa = st.date_input(
                "Pesquisar uma data no calendário",
                value=valor_cal,
                format="DD/MM/YYYY",
                key="cal_pesquisa_agenda",
            )
        with pc2:
            st.markdown("<div style='height:27px;'></div>", unsafe_allow_html=True)
            if st.button("🔍 Ver Data", key="btn_ver_data_cal", type="primary", use_container_width=True):
                st.session_state.agenda_filtro = "Data"
                st.session_state.agenda_data_busca = data_pesquisa
                st.rerun()

    agendamentos = carregar_agendamentos(apenas_agendadas=True)

    filtrados = []
    if st.session_state.agenda_filtro == "Hoje":
        titulo_lista = f"Hoje ({hoje.strftime('%d/%m/%Y')})"
        filtrados = [ag for ag in agendamentos if str(ag.get("data_agendamento", ""))[:10] == hoje.isoformat()]
    elif st.session_state.agenda_filtro == "Amanhã":
        titulo_lista = f"Amanhã ({amanha.strftime('%d/%m/%Y')})"
        filtrados = [ag for ag in agendamentos if str(ag.get("data_agendamento", ""))[:10] == amanha.isoformat()]
    elif st.session_state.agenda_filtro == "Esta Semana":
        titulo_lista = f"Esta Semana ({inicio_semana.strftime('%d/%m')} a {fim_semana.strftime('%d/%m')})"
        filtrados = [
            ag
            for ag in agendamentos
            if inicio_semana.isoformat() <= str(ag.get("data_agendamento", ""))[:10] <= fim_semana.isoformat()
        ]
    else:
        dt_b = st.session_state.agenda_data_busca or hoje
        titulo_lista = f"Data selecionada ({dt_b.strftime('%d/%m/%Y')})"
        filtrados = [ag for ag in agendamentos if str(ag.get("data_agendamento", ""))[:10] == dt_b.isoformat()]

    st.markdown(f"#### Vistorias Agendadas — {titulo_lista} ({len(filtrados)})")

    if not filtrados:
        st.info("Nenhuma vistoria agendada para este período.")
        return

    for ag in filtrados:
        emp_nome = ag.get("empresa_nome", "")
        badge_cls = "cv-badge-red" if "AD " in emp_nome.upper() else "cv-badge-purple"
        msg_wa = (
            f"Olá {ag.get('cliente_nome', '')}, tudo bem? "
            f"Confirmando sua vistoria do veículo {ag.get('veiculo', '')} "
            f"(Placa {ag.get('placa', '')}) em {fmt_data_br(ag.get('data_agendamento'))} às {ag.get('hora_agendamento', '')}."
        )
        wa_url = link_whatsapp(ag.get("cliente_whatsapp", ""), msg_wa)
        wa_html = f'<a class="wa-btn" href="{wa_url}" target="_blank">💬 WhatsApp</a>' if wa_url else ""

        st.markdown(
            f"""
            <div class="cv-card">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <span style="color:var(--muted);font-size:0.85rem;font-weight:600;">
                        📅 {fmt_data_br(ag.get('data_agendamento'))} • ⏰ {ag.get('hora_agendamento', '')}
                    </span>
                    <span class="{badge_cls}">{emp_nome}</span>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
                    <div>
                        <div class="cv-card-title">
                            {ag.get('veiculo', '')} • Placa: {ag.get('placa', '')}
                        </div>
                        <div class="cv-card-sub">
                            👤 {ag.get('cliente_nome', '')} • 📞 {ag.get('cliente_whatsapp') or 'Não informado'}
                        </div>
                    </div>
                    <div>{wa_html}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        bc1, bc2 = st.columns([4, 1])
        with bc1:
            if st.button(
                "📋 Abrir Ordem de Serviço",
                key=f"iniciar_{ag['id']}",
                type="primary",
                use_container_width=True,
            ):
                emp_info = mapa_empresas.get(emp_nome, {})
                st.session_state.os_importada = {
                    "agendamento_id": ag["id"],
                    "empresa_nome": emp_nome,
                    "cliente_nome": ag.get("cliente_nome", ""),
                    "veiculo": ag.get("veiculo", ""),
                    "placa": ag.get("placa", ""),
                    "data_vistoria": ag.get("data_agendamento", hoje.isoformat()),
                    "valor_padrao": float(emp_info.get("valor_padrao") or 0.0),
                }
                st.session_state.form_os_ver += 1
                st.session_state.pagina = "Ordem de Serviço"
                st.rerun()
        with bc2:
            if st.button("🗑️", key=f"del_ag_{ag['id']}", help="Remover agendamento", use_container_width=True):
                supabase.table("agendamentos").delete().eq("id", ag["id"]).execute()
                st.session_state.aviso_sucesso = "Agendamento removido."
                st.rerun()


# =========================================================
# TELA 4: ORDEM DE SERVIÇO
# =========================================================
def tela_ordem_servico():
    st.markdown("### ✅ Ordem de Serviço")
    mostrar_aviso_pendente()

    empresas = carregar_empresas()
    nomes_empresas = [e["nome"] for e in empresas]
    mapa_empresas = {e["nome"]: e for e in empresas}
    hoje = hoje_br()
    ver = st.session_state.form_os_ver

    imp = st.session_state.get("os_importada")

    if imp:
        st.markdown(
            '<div class="cv-banner-import">📅 Dados carregados da Agenda</div>',
            unsafe_allow_html=True,
        )
        if st.button("Limpar dados importados (nova OS avulsa)", use_container_width=True):
            st.session_state.os_importada = None
            st.session_state.form_os_ver += 1
            st.rerun()

    with st.container(border=True):
        emp_padrao = imp["empresa_nome"] if imp else (nomes_empresas[0] if nomes_empresas else "")
        if nomes_empresas:
            idx_emp = nomes_empresas.index(emp_padrao) if emp_padrao in nomes_empresas else 0
            empresa_sel = st.selectbox("Empresa", nomes_empresas, index=idx_emp, key=f"os_emp_{ver}")
            valor_sugerido = float(mapa_empresas[empresa_sel].get("valor_padrao") or 0.0)
            if imp and empresa_sel == imp.get("empresa_nome") and imp.get("valor_padrao"):
                valor_sugerido = float(imp["valor_padrao"])
        else:
            empresa_sel = st.text_input("Empresa", value=emp_padrao, key=f"os_emp_txt_{ver}")
            valor_sugerido = float(imp["valor_padrao"]) if imp else 0.0

        cliente_val = st.text_input(
            "Cliente / Segurado (opcional)",
            value=imp.get("cliente_nome", "") if imp else "",
            key=f"os_cli_{ver}",
        )
        veiculo_val = st.text_input(
            "Veículo",
            value=imp.get("veiculo", "") if imp else "",
            key=f"os_veic_{ver}",
        )
        placa_val = st.text_input(
            "Placa",
            value=imp.get("placa", "") if imp else "",
            key=f"os_placa_{ver}",
        )

        try:
            data_ini = (
                datetime.strptime(str(imp["data_vistoria"])[:10], "%Y-%m-%d").date()
                if imp and imp.get("data_vistoria")
                else hoje
            )
        except ValueError:
            data_ini = hoje

        c1, c2 = st.columns(2)
        with c1:
            data_val = st.date_input("Data", value=data_ini, format="DD/MM/YYYY", key=f"os_data_{ver}")
        with c2:
            valor_val = st.number_input(
                "Valor do Serviço (R$)",
                min_value=0.0,
                value=valor_sugerido,
                step=1.0,
                format="%.2f",
                key=f"os_valor_{ver}_{empresa_sel}",
            )

        st.markdown("**Tipo de Vistoria**")
        tv1, tv2 = st.columns(2)
        with tv1:
            if st.button(
                "Nova",
                key=f"btn_tipo_nova_{ver}",
                type="primary" if st.session_state.tipo_vistoria_os == "Nova" else "secondary",
                use_container_width=True,
            ):
                st.session_state.tipo_vistoria_os = "Nova"
                st.rerun()
        with tv2:
            if st.button(
                "Renovação",
                key=f"btn_tipo_renov_{ver}",
                type="primary" if st.session_state.tipo_vistoria_os == "Renovação" else "secondary",
                use_container_width=True,
            ):
                st.session_state.tipo_vistoria_os = "Renovação"
                st.rerun()

        st.markdown("**Foto do Veículo**")
        modo_foto = st.radio(
            "Origem da foto",
            ["Galeria / Arquivo", "Câmera"],
            horizontal=True,
            label_visibility="collapsed",
            key=f"os_modo_foto_{ver}",
        )
        foto_arquivo = None
        if modo_foto == "Galeria / Arquivo":
            foto_arquivo = st.file_uploader(
                "Anexar foto do veículo",
                type=["jpg", "jpeg", "png", "webp"],
                label_visibility="collapsed",
                key=f"os_upload_{ver}",
            )
        else:
            foto_arquivo = st.camera_input("Capturar foto do veículo", key=f"os_cam_{ver}")

        if foto_arquivo is not None:
            p1, p2 = st.columns([1, 2])
            with p1:
                st.image(foto_arquivo, width=150)
            with p2:
                st.markdown(
                    '<span class="cv-badge-purple">✔ 1 foto anexada</span>',
                    unsafe_allow_html=True,
                )

    st.markdown('<span class="marker-red"></span>', unsafe_allow_html=True)
    concluir = st.button("✔ Concluir Ordem de Serviço", key=f"btn_concluir_os_{ver}", use_container_width=True)

    if concluir:
        if not empresa_sel.strip() or not veiculo_val.strip() or not placa_val.strip():
            st.warning("Preencha Empresa, Veículo e Placa antes de concluir.")
        else:
            foto_b64 = None
            if foto_arquivo is not None:
                try:
                    foto_b64 = comprimir_imagem_para_base64(foto_arquivo)
                except Exception as e:
                    st.error(f"Erro ao processar foto: {e}")
                    return

            payload = {
                "agendamento_id": imp["agendamento_id"] if imp else None,
                "empresa_id": None,
                "empresa_nome": empresa_sel.strip(),
                "cliente_nome": cliente_val.strip(),
                "veiculo": veiculo_val.strip(),
                "placa": placa_val.strip().upper(),
                "data_vistoria": data_val.isoformat(),
                "valor": float(valor_val),
                "tipo_vistoria": st.session_state.tipo_vistoria_os,
                "foto_base64": foto_b64,
                "status_pagamento": "Pendente",
                "data_recebimento": None,
            }
            try:
                supabase.table("vistorias").insert(payload).execute()
                if imp and imp.get("agendamento_id"):
                    supabase.table("agendamentos").update({"status": "Concluida"}).eq(
                        "id", imp["agendamento_id"]
                    ).execute()
                st.session_state.os_importada = None
                st.session_state.tipo_vistoria_os = "Nova"
                st.session_state.form_os_ver += 1
                st.session_state.aviso_sucesso = "Ordem de Serviço concluída e enviada para o Financeiro!"
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao concluir Ordem de Serviço: {e}")


# =========================================================
# TELA 5: FINANCEIRO & CALENDÁRIO
# =========================================================
def tela_financeiro():
    st.markdown("### 💰 Financeiro & Calendário")
    mostrar_aviso_pendente()

    nav1, nav2, nav3 = st.columns([1, 3.2, 1])
    with nav1:
        if st.button("◀", key="mes_ant", use_container_width=True):
            if st.session_state.fin_mes == 1:
                st.session_state.fin_mes = 12
                st.session_state.fin_ano -= 1
            else:
                st.session_state.fin_mes -= 1
            st.rerun()
    with nav2:
        titulo_mes = f"{MESES_PT[st.session_state.fin_mes]} {st.session_state.fin_ano}"
        st.markdown(f'<div class="cv-month-bar">📅 {titulo_mes}</div>', unsafe_allow_html=True)
    with nav3:
        if st.button("▶", key="mes_prox", use_container_width=True):
            if st.session_state.fin_mes == 12:
                st.session_state.fin_mes = 1
                st.session_state.fin_ano += 1
            else:
                st.session_state.fin_mes += 1
            st.rerun()

    vistorias = carregar_vistorias(st.session_state.fin_ano, st.session_state.fin_mes)
    empresas = carregar_empresas()
    dias_pgto = {e["nome"]: int(e.get("dia_pagamento") or 15) for e in empresas}

    pendentes = [v for v in vistorias if v.get("status_pagamento") != "Recebido"]
    recebidas = [v for v in vistorias if v.get("status_pagamento") == "Recebido"]

    total_pendente = sum(float(v.get("valor") or 0) for v in pendentes)
    total_recebido = sum(float(v.get("valor") or 0) for v in recebidas)

    st.markdown(
        f"""
        <div class="cv-hero-purple">
            <div class="cv-hero-label">💼 Total Líquido a Receber</div>
            <div class="cv-hero-value">{fmt_moeda(total_pendente)}</div>
            <div class="cv-hero-sub">
                {len(vistorias)} Vistorias Concluídas • {len(pendentes)} OS Pendentes
            </div>
            <div class="cv-pill-row">
                <span class="cv-pill-light">Pendente: {fmt_moeda(total_pendente)}</span>
                <span class="cv-pill-green">✓ Já Recebido: {fmt_moeda(total_recebido)}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if PDF_DISPONIVEL and vistorias:
        pdf_mes = gerar_pdf_lote(vistorias, titulo_mes, "Todas")
        st.download_button(
            "📄 Baixar Relatório Mensal em PDF (Lote)",
            data=pdf_mes,
            file_name=f"financeiro_{st.session_state.fin_ano}_{st.session_state.fin_mes:02d}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    st.markdown("#### 📆 A Receber por Empresa")
    grupos_pend = {}
    for v in pendentes:
        grupos_pend.setdefault(v["empresa_nome"], []).append(v)

    if not grupos_pend:
        st.info("Nenhum valor pendente de recebimento neste mês.")
    else:
        for emp_nome, lista_os in sorted(grupos_pend.items()):
            qtd = len(lista_os)
            soma = sum(float(x.get("valor") or 0) for x in lista_os)
            media = soma / qtd if qtd else 0
            dia_p = dias_pgto.get(emp_nome, 15)
            badge_cls = "cv-badge-purple" if dia_p == 15 else "cv-badge-red"

            st.markdown(
                f"""
                <div class="cv-card">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div class="cv-card-title">🏢 {emp_nome}</div>
                        <span class="{badge_cls}">Paga dia {dia_p:02d}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;">
                        <span class="cv-card-sub">
                            {qtd} vistoria(s) concluída(s) • {fmt_moeda(media)} por OS
                        </span>
                        <span style="font-weight:800;font-size:1.08rem;color:var(--text);">{fmt_moeda(soma)}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            col_baixa, col_pdf = st.columns([3.3, 1])
            with col_baixa:
                st.markdown('<span class="marker-green"></span>', unsafe_allow_html=True)
                if st.button(
                    "✓ Marcar como Recebido",
                    key=f"baixar_{emp_nome}_{st.session_state.fin_ano}_{st.session_state.fin_mes}",
                    use_container_width=True,
                ):
                    ids = [x["id"] for x in lista_os]
                    supabase.table("vistorias").update(
                        {
                            "status_pagamento": "Recebido",
                            "data_recebimento": hoje_br().isoformat(),
                        }
                    ).in_("id", ids).execute()
                    st.session_state.aviso_sucesso = f"Baixa registrada para {emp_nome}!"
                    st.rerun()
            with col_pdf:
                if PDF_DISPONIVEL:
                    pdf_emp = gerar_pdf_lote(lista_os, titulo_mes, emp_nome)
                    nome_arq = re.sub(r"\W+", "_", emp_nome)
                    st.download_button(
                        "📄 PDF",
                        data=pdf_emp,
                        file_name=f"cobranca_{nome_arq}_{st.session_state.fin_mes:02d}.pdf",
                        mime="application/pdf",
                        key=f"pdf_p_{emp_nome}",
                        use_container_width=True,
                    )

    st.markdown("#### ✅ Pagamentos Recebidos (Baixas)")
    grupos_rec = {}
    for v in recebidas:
        grupos_rec.setdefault(v["empresa_nome"], []).append(v)

    if not grupos_rec:
        st.caption("Nenhuma baixa registrada neste mês ainda.")
    else:
        for emp_nome, lista_os in sorted(grupos_rec.items()):
            qtd = len(lista_os)
            soma = sum(float(x.get("valor") or 0) for x in lista_os)
            media = soma / qtd if qtd else 0
            datas_rec = [x.get("data_recebimento") for x in lista_os if x.get("data_recebimento")]
            dt_label = fmt_data_curta(max(datas_rec)) if datas_rec else "-"

            st.markdown(
                f"""
                <div class="cv-card-green">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div class="cv-card-green-title">🏢 {emp_nome}</div>
                        <span class="cv-badge-green">✓ Recebido em {dt_label}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;">
                        <span class="cv-card-green-sub">
                            {qtd} vistoria(s) • {fmt_moeda(media)} por OS
                        </span>
                        <span class="cv-card-green-title">✓ {fmt_moeda(soma)}</span>
                    </div>
                    <div style="margin-top:8px;">
                        <span class="cv-badge-green">Baixa efetuada com sucesso</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                f"Desfazer baixa de {emp_nome}",
                key=f"estornar_{emp_nome}_{st.session_state.fin_ano}_{st.session_state.fin_mes}",
            ):
                ids = [x["id"] for x in lista_os]
                supabase.table("vistorias").update(
                    {"status_pagamento": "Pendente", "data_recebimento": None}
                ).in_("id", ids).execute()
                st.session_state.aviso_sucesso = f"Baixa de {emp_nome} desfeita."
                st.rerun()


# =========================================================
# TELA 6: RELATÓRIOS EM PDF
# =========================================================
def tela_pdf():
    st.markdown("### 📄 Relatórios em PDF")
    mostrar_aviso_pendente()

    if not PDF_DISPONIVEL:
        st.warning("Adicione `fpdf2` no seu arquivo `requirements.txt` para habilitar o download de PDFs.")

    todas = carregar_vistorias()
    if not todas:
        st.info("Nenhuma vistoria concluída registrada até o momento.")
        return

    empresas_unicas = ["Todas"] + sorted({v["empresa_nome"] for v in todas})
    f1, f2 = st.columns(2)
    with f1:
        f_emp = st.selectbox("Filtrar por Empresa", empresas_unicas)
    with f2:
        f_status = st.selectbox("Status Financeiro", ["Todos", "Pendente", "Recebido"])

    filtradas = [
        v
        for v in todas
        if (f_emp == "Todas" or v["empresa_nome"] == f_emp)
        and (f_status == "Todos" or v.get("status_pagamento") == f_status)
    ]

    if PDF_DISPONIVEL and filtradas:
        pdf_lote = gerar_pdf_lote(filtradas, "Relatório Filtrado", f_emp)
        st.download_button(
            f"📥 Baixar PDF em Lote ({len(filtradas)} OS)",
            data=pdf_lote,
            file_name="relatorio_vistorias_lote.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )

    st.markdown(f"**Registros encontrados: {len(filtradas)}**")

    for v in filtradas:
        st_pg = v.get("status_pagamento", "Pendente")
        badge = "cv-badge-green" if st_pg == "Recebido" else "cv-badge-purple"
        st.markdown(
            f"""
            <div class="cv-card">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span class="cv-card-title">
                        OS #{v['id']} • {v['veiculo']} ({v['placa']})
                    </span>
                    <span class="{badge}">{st_pg}</span>
                </div>
                <div class="cv-card-sub">
                    🏢 {v['empresa_nome']} • 📅 {fmt_data_br(v['data_vistoria'])} • {v.get('tipo_vistoria', 'Nova')} •
                    <strong style="color:var(--text);">{fmt_moeda(v['valor'])}</strong>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander(f"Ver foto / PDF / opções — OS #{v['id']}"):
            if v.get("cliente_nome"):
                st.write(f"**Cliente:** {v['cliente_nome']}")
            if v.get("foto_base64"):
                st.image(base64_para_bytes(v["foto_base64"]), width=280)
            else:
                st.caption("Sem foto anexada.")

            a1, a2 = st.columns([3, 1])
            with a1:
                if PDF_DISPONIVEL:
                    pdf_ind = gerar_pdf_individual(v)
                    st.download_button(
                        "📄 Baixar PDF Individual",
                        data=pdf_ind,
                        file_name=f"OS_{v['id']}_{v['placa']}.pdf",
                        mime="application/pdf",
                        key=f"pdf_ind_{v['id']}",
                        use_container_width=True,
                    )
            with a2:
                if st.button("🗑️ Excluir", key=f"del_os_{v['id']}", use_container_width=True):
                    supabase.table("vistorias").delete().eq("id", v["id"]).execute()
                    st.session_state.aviso_sucesso = f"OS #{v['id']} excluída."
                    st.rerun()


# =========================================================
# BARRA SUPERIOR E NAVEGAÇÃO PRINCIPAL
# =========================================================
def main():
    if not st.session_state.autenticado:
        tela_login()
        return

    # Barra superior sempre visível: Marca + Alternar Claro/Escuro + Sair
    top1, top2, top3 = st.columns([3.0, 1.2, 1.0])
    with top1:
        st.markdown(
            '<div class="brand-bar">🚗 Controle de Vistorias</div>',
            unsafe_allow_html=True,
        )
    with top2:
        botao_alternar_tema("app")
    with top3:
        if st.button("🚪 Sair", use_container_width=True):
            st.session_state.autenticado = False
            st.session_state.os_importada = None
            st.rerun()

    # Navegação principal com nomes completos
    abas = [
        ("Agenda", "📅 Agenda"),
        ("Ordem de Serviço", "✅ Ordem de Serviço"),
        ("Financeiro", "💰 Financeiro"),
        ("Empresas", "🤝 Empresas"),
        ("PDF", "📄 PDF"),
    ]
    cols_nav = st.columns([1.0, 1.85, 1.25, 1.15, 0.85])
    for col, (chave, rotulo) in zip(cols_nav, abas):
        with col:
            tipo = "primary" if st.session_state.pagina == chave else "secondary"
            if st.button(rotulo, key=f"nav_{chave}", type=tipo, use_container_width=True):
                st.session_state.pagina = chave
                st.rerun()

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    if st.session_state.pagina == "Empresas":
        tela_empresas()
    elif st.session_state.pagina == "Agenda":
        tela_agenda()
    elif st.session_state.pagina == "Ordem de Serviço":
        tela_ordem_servico()
    elif st.session_state.pagina == "Financeiro":
        tela_financeiro()
    elif st.session_state.pagina == "PDF":
        tela_pdf()


if __name__ == "__main__":
    main()

import base64
import html
import io
import json
import math
import os
import re
import tempfile
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import quote, urlencode

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

CATEGORIAS_EMPRESA = ["Vistoria", "Rastreamento"]
TIPOS_VISTORIA_OPCOES = ["Cautelar", "Sinistro", "Seguro", "Outra"]
TIPOS_RASTREAMENTO_OPCOES = ["Instalação", "Manutenção", "Retirada"]

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

DIAS_SEMANA_COMPLETO = [
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
]


def render_html(bloco_html: str):
    """Remove linhas em branco e recuos para o Markdown nunca quebrar o HTML."""
    limpo = "\n".join(linha.strip() for linha in bloco_html.splitlines() if linha.strip())
    st.markdown(limpo, unsafe_allow_html=True)


def esc(texto) -> str:
    return html.escape(str(texto or ""))


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
if "modalidade_os" not in st.session_state:
    st.session_state.modalidade_os = "Nova"
if "os_subaba" not in st.session_state:
    st.session_state.os_subaba = "OS do Dia"
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
if "fin_edit_ver" not in st.session_state:
    st.session_state.fin_edit_ver = 0
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
            "surface_soft": "#151822",
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
            "amber_bg": "#33260E",
            "amber_text": "#FDE68A",
            "sec_btn_bg": "#222634",
            "sec_btn_text": "#E5E7EB",
            "sec_btn_border": "#363C52",
            "shadow": "0 4px 14px rgba(0, 0, 0, 0.35)",
        }
    else:
        cores = {
            "bg": "#F4F5F7",
            "surface": "#FFFFFF",
            "surface_soft": "#F9FAFB",
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
            "amber_bg": "#FEF3C7",
            "amber_text": "#92400E",
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
            --surface-soft: {cores['surface_soft']};
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
            --amber-bg: {cores['amber_bg']};
            --amber-text: {cores['amber_text']};
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
            max-width: 920px !important;
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
        .cv-card-booked {{
            background: var(--surface);
            border: 1px solid var(--purple-soft-border);
            border-left: 5px solid var(--purple);
            border-radius: 14px;
            padding: 14px 16px;
            margin-bottom: 8px;
            box-shadow: var(--shadow);
        }}
        .cv-card-closest {{
            background: var(--surface);
            border: 2px solid var(--green);
            border-left: 6px solid var(--green);
            border-radius: 14px;
            padding: 14px 16px;
            margin-bottom: 8px;
            box-shadow: var(--shadow);
        }}
        .cv-slot-free {{
            background: var(--surface-soft);
            border: 1px dashed var(--border);
            border-radius: 10px;
            padding: 7px 14px;
            margin-bottom: 6px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: var(--muted);
            font-size: 0.86rem;
        }}
        .cv-slot-free-tag {{
            font-size: 0.76rem;
            font-weight: 600;
            opacity: 0.85;
        }}
        .cv-day-summary {{
            background: var(--purple-soft-bg);
            border: 1px solid var(--purple-soft-border);
            border-radius: 14px;
            padding: 12px 16px;
            margin: 10px 0 12px 0;
            color: var(--purple-soft-text);
        }}
        .cv-route-box {{
            background: var(--surface);
            border: 1px solid var(--green-card-border);
            border-left: 5px solid var(--green);
            border-radius: 14px;
            padding: 13px 16px;
            margin-bottom: 14px;
            box-shadow: var(--shadow);
        }}
        .cv-route-item {{
            padding: 6px 0;
            border-bottom: 1px dashed var(--border);
            font-size: 0.88rem;
            color: var(--text);
        }}
        .cv-route-item:last-child {{
            border-bottom: none;
            padding-bottom: 0;
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
        .cv-badge-amber {{
            background: var(--amber-bg);
            color: var(--amber-text);
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
            padding-left: 0.45rem !important;
            padding-right: 0.45rem !important;
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
            padding-left: 0.45rem !important;
            padding-right: 0.45rem !important;
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
            gap: 4px;
            background-color: #25D366;
            color: #FFFFFF !important;
            text-decoration: none !important;
            font-weight: 700;
            font-size: 0.8rem;
            padding: 5px 11px;
            border-radius: 999px;
            white-space: nowrap;
        }}
        .wa-btn:hover {{
            background-color: #1EBE5D;
            color: #FFFFFF !important;
        }}
        .maps-btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            background-color: var(--purple);
            color: #FFFFFF !important;
            text-decoration: none !important;
            font-weight: 700;
            font-size: 0.8rem;
            padding: 5px 11px;
            border-radius: 999px;
            white-space: nowrap;
        }}
        .maps-btn:hover {{
            background-color: var(--purple-hover);
            color: #FFFFFF !important;
        }}

        .brand-bar {{
            font-weight: 800;
            font-size: 1.2rem;
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


def fmt_km(km: float) -> str:
    return f"{km:.1f}".replace(".", ",") + " km"


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


def parse_data(data_str: str) -> date:
    try:
        return datetime.strptime(str(data_str)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return hoje_br()


def parse_hora(hora_str: str) -> time:
    try:
        partes = str(hora_str or "08:00").split(":")
        return time(int(partes[0]), int(partes[1]))
    except (ValueError, IndexError, TypeError):
        return time(8, 0)


def extrair_hora_int(hora_str: str) -> int:
    try:
        return int(str(hora_str or "08:00").split(":")[0])
    except (ValueError, IndexError, TypeError):
        return 8


def opcoes_por_categoria(categoria: str) -> list:
    if categoria == "Rastreamento":
        return TIPOS_RASTREAMENTO_OPCOES
    return TIPOS_VISTORIA_OPCOES


def parse_tipos_empresa(texto: str, categoria: str = "Vistoria") -> list:
    validas = opcoes_por_categoria(categoria)
    if not texto:
        return [validas[0]]
    partes = [p.strip() for p in str(texto).split(",") if p.strip() in validas]
    return partes if partes else [validas[0]]


def extrair_servico_os(texto: str, categoria: str = "Vistoria") -> str:
    validas = opcoes_por_categoria(categoria)
    t = str(texto or "")
    for op in validas:
        if op.lower() in t.lower():
            return op
    return validas[0]


def link_whatsapp(telefone: str, mensagem: str = "") -> str:
    digitos = re.sub(r"\D", "", str(telefone or ""))
    if not digitos:
        return ""
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    if mensagem:
        return f"https://wa.me/{digitos}?text={quote(mensagem)}"
    return f"https://wa.me/{digitos}"


def link_rota_maps(origem: str, destino: str) -> str:
    dest = str(destino or "").strip()
    orig = str(origem or "").strip()
    if not dest:
        return ""
    if orig:
        return f"https://www.google.com/maps/dir/?api=1&origin={quote(orig)}&destination={quote(dest)}"
    return f"https://www.google.com/maps/search/?api=1&query={quote(dest)}"


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
# GEOLOCALIZAÇÃO E CÁLCULO DE DISTÂNCIA (PONTO BASE -> CLIENTE)
# =========================================================
def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _buscar_nominatim(query: str):
    params = urlencode({"q": query, "format": "json", "limit": 1, "countrycodes": "br"})
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ControleDeVistoriasAD/1.0 (contato@adrastreamento.com.br)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
            if dados:
                return float(dados[0]["lat"]), float(dados[0]["lon"])
    except Exception:
        return None
    return None


@st.cache_data(ttl=86400, show_spinner=False)
def geocodificar_endereco(endereco: str):
    texto = str(endereco or "").strip()
    if len(texto) < 4:
        return None

    tentativas = [texto]
    if "brasil" not in texto.lower():
        tentativas.append(f"{texto}, Brasil")

    sem_num = re.sub(r"\b(?:n[º°]?\.?\s*)?\d+[A-Za-z]?\b", "", texto).strip(" ,-")
    if sem_num and sem_num != texto and len(sem_num) >= 4:
        tentativas.append(sem_num)
        if "brasil" not in sem_num.lower():
            tentativas.append(f"{sem_num}, Brasil")

    for t in tentativas:
        coord = _buscar_nominatim(t)
        if coord:
            return coord
    return None


@st.cache_data(ttl=86400, show_spinner=False)
def calcular_distancia_rota(origem_end: str, destino_end: str):
    """Retorna dict {'km': float, 'minutos': int|None, 'estimada': bool} ou None."""
    c_orig = geocodificar_endereco(origem_end)
    c_dest = geocodificar_endereco(destino_end)
    if not c_orig or not c_dest:
        return None

    lat1, lon1 = c_orig
    lat2, lon2 = c_dest

    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{lon1},{lat1};{lon2},{lat2}?overview=false"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "ControleDeVistoriasAD/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
            if dados.get("code") == "Ok" and dados.get("routes"):
                rota = dados["routes"][0]
                km = float(rota["distance"]) / 1000.0
                minutos = max(1, round(float(rota["duration"]) / 60.0))
                return {"km": km, "minutos": minutos, "estimada": False}
    except Exception:
        pass

    km_est = _haversine_km(lat1, lon1, lat2, lon2) * 1.25
    min_est = max(1, round((km_est / 32.0) * 60.0))
    return {"km": km_est, "minutos": min_est, "estimada": True}


# =========================================================
# CONSULTAS AO BANCO DE DADOS (APENAS TABELAS DE VISTORIAS)
# =========================================================
def carregar_perfil():
    try:
        res = supabase.table("vistorias_perfil").select("*").order("id").limit(1).execute()
        if res.data:
            return res.data[0]
        return {"id": None, "nome": "", "telefone": "", "ponto_base": ""}
    except Exception:
        return {"id": None, "nome": "", "telefone": "", "ponto_base": "", "_erro_tabela": True}


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


def iniciar_os_a_partir_agendamento(ag: dict, mapa_empresas: dict):
    emp_nome = ag.get("empresa_nome", "")
    emp_info = mapa_empresas.get(emp_nome, {})
    categoria = emp_info.get("categoria_servico") or "Vistoria"
    tipos_emp = parse_tipos_empresa(emp_info.get("tipo_vistoria"), categoria)
    tipo_ag = ag.get("tipo_servico") or tipos_emp[0]

    st.session_state.os_importada = {
        "agendamento_id": ag["id"],
        "empresa_nome": emp_nome,
        "cliente_nome": ag.get("cliente_nome", ""),
        "endereco": ag.get("endereco", ""),
        "veiculo": ag.get("veiculo", ""),
        "placa": ag.get("placa", ""),
        "data_vistoria": ag.get("data_agendamento", hoje_br().isoformat()),
        "valor_padrao": float(emp_info.get("valor_padrao") or 0.0),
        "tipo_padrao": tipo_ag,
        "categoria_servico": categoria,
        "sem_financeiro": bool(emp_info.get("sem_financeiro")),
    }
    st.session_state.form_os_ver += 1
    st.session_state.pagina = "Ordem de Serviço"
    st.rerun()


# =========================================================
# COMPONENTES REUTILIZÁVEIS (CARD AGENDAMENTO / EDITOR OS)
# =========================================================
def render_card_agendamento(
    ag: dict,
    mapa_empresas: dict,
    nomes_empresas: list,
    prefixo: str,
    ponto_base: str = "",
    dist_info: dict = None,
    eh_mais_proximo: bool = False,
    mostrar_data: bool = False,
):
    emp_nome = ag.get("empresa_nome", "")
    emp_info = mapa_empresas.get(emp_nome, {})
    categoria_emp = emp_info.get("categoria_servico") or "Vistoria"
    sem_fin = bool(emp_info.get("sem_financeiro"))
    badge_cls = "cv-badge-red" if (categoria_emp == "Rastreamento" or "AD " in emp_nome.upper()) else "cv-badge-purple"
    concluida = ag.get("status") == "Concluida"
    ver = st.session_state.form_ag_ver

    endereco_cli = (ag.get("endereco") or "").strip()
    tipo_serv_ag = (ag.get("tipo_servico") or "").strip()

    msg_wa = (
        f"Olá {ag.get('cliente_nome', '')}, tudo bem? "
        f"Confirmando seu atendimento ({tipo_serv_ag or categoria_emp}) do veículo {ag.get('veiculo', '')} "
        f"(Placa {ag.get('placa', '')}) em {fmt_data_br(ag.get('data_agendamento'))} às {ag.get('hora_agendamento', '')}."
    )
    wa_url = link_whatsapp(ag.get("cliente_whatsapp", ""), msg_wa)
    wa_html = f'<a class="wa-btn" href="{wa_url}" target="_blank">💬 WhatsApp</a>' if wa_url else ""

    maps_url = link_rota_maps(ponto_base, endereco_cli)
    maps_html = f'<a class="maps-btn" href="{maps_url}" target="_blank">🗺️ Rota</a>' if maps_url else ""

    status_badge = (
        '<span class="cv-badge-green">✅ Concluída</span>'
        if concluida
        else '<span class="cv-badge-purple">✔ Preenchido</span>'
    )
    serv_badge = f'&nbsp;<span class="cv-badge-amber">🔧 {esc(tipo_serv_ag)}</span>' if tipo_serv_ag else ""

    dist_badges = ""
    if dist_info:
        min_txt = f" (~{dist_info['minutos']} min)" if dist_info.get("minutos") else ""
        aprox = "aprox. " if dist_info.get("estimada") else ""
        dist_badges = f'<span class="cv-badge-purple">📍 {aprox}{fmt_km(dist_info["km"])} do ponto base{min_txt}</span>'
        if eh_mais_proximo:
            dist_badges = '<span class="cv-badge-green">⭐ Mais próximo</span>&nbsp;' + dist_badges

    topo_tempo = (
        f"📅 {fmt_data_br(ag.get('data_agendamento'))} • ⏰ {esc(ag.get('hora_agendamento', ''))}"
        if mostrar_data
        else f"⏰ {esc(ag.get('hora_agendamento', ''))}"
    )

    if concluida:
        card_cls = "cv-card-green"
    elif eh_mais_proximo:
        card_cls = "cv-card-closest"
    else:
        card_cls = "cv-card-booked"

    title_cls = "cv-card-green-title" if concluida else "cv-card-title"
    sub_cls = "cv-card-green-sub" if concluida else "cv-card-sub"
    end_html = f'<div class="{sub_cls}">📍 {esc(endereco_cli)}</div>' if endereco_cli else ""
    dist_row_html = f'<div style="margin-top:6px;">{dist_badges}</div>' if dist_badges else ""
    botoes_dir = ""
    if wa_html or maps_html:
        botoes_dir = (
            '<div style="display:flex;flex-direction:column;gap:6px;align-items:flex-end;">'
            f'{wa_html}{maps_html}'
            '</div>'
        )

    render_html(
        f"""
        <div class="{card_cls}">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:6px;">
                <span style="font-size:0.88rem;font-weight:700;">{topo_tempo} &nbsp;{status_badge}{serv_badge}</span>
                <span class="{badge_cls}">{esc(emp_nome)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;flex-wrap:wrap;">
                <div style="flex:1;min-width:210px;">
                    <div class="{title_cls}">{esc(ag.get('veiculo', ''))} • Placa: {esc(ag.get('placa', ''))}</div>
                    <div class="{sub_cls}">👤 {esc(ag.get('cliente_nome', ''))} • 📞 {esc(ag.get('cliente_whatsapp') or 'Não informado')}</div>
                    {end_html}
                    {dist_row_html}
                </div>
                {botoes_dir}
            </div>
        </div>
        """
    )

    if not concluida:
        if sem_fin:
            bc1, bc2, bc3 = st.columns([2.2, 2.2, 0.8])
            with bc1:
                render_html('<span class="marker-green"></span>')
                if st.button(
                    "✔ Concluir (Sem Cobrança)",
                    key=f"{prefixo}_conc_rap_{ag['id']}",
                    use_container_width=True,
                ):
                    try:
                        supabase.table("vistorias").insert(
                            {
                                "agendamento_id": ag["id"],
                                "empresa_id": None,
                                "empresa_nome": emp_nome,
                                "cliente_nome": ag.get("cliente_nome") or "",
                                "endereco": endereco_cli,
                                "veiculo": ag.get("veiculo") or "",
                                "placa": (ag.get("placa") or "").upper(),
                                "data_vistoria": ag.get("data_agendamento", hoje_br().isoformat()),
                                "valor": 0.0,
                                "tipo_vistoria": tipo_serv_ag or "Instalação",
                                "foto_base64": None,
                                "status_pagamento": "Sem Cobrança",
                                "data_recebimento": None,
                            }
                        ).execute()
                        supabase.table("agendamentos").update({"status": "Concluida"}).eq("id", ag["id"]).execute()
                        st.session_state.aviso_sucesso = (
                            f"Atendimento de {emp_nome} ({tipo_serv_ag or 'Rastreamento'}) concluído!"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao concluir: {e}")
            with bc2:
                if st.button(
                    "📋 Abrir OS (com foto)",
                    key=f"{prefixo}_iniciar_{ag['id']}",
                    type="primary",
                    use_container_width=True,
                ):
                    iniciar_os_a_partir_agendamento(ag, mapa_empresas)
            with bc3:
                if st.button("🗑️", key=f"{prefixo}_del_{ag['id']}", help="Remover", use_container_width=True):
                    supabase.table("agendamentos").delete().eq("id", ag["id"]).execute()
                    st.session_state.aviso_sucesso = "Agendamento removido."
                    st.rerun()
        else:
            bc1, bc2 = st.columns([4, 1])
            with bc1:
                if st.button(
                    "📋 Abrir Ordem de Serviço",
                    key=f"{prefixo}_iniciar_{ag['id']}",
                    type="primary",
                    use_container_width=True,
                ):
                    iniciar_os_a_partir_agendamento(ag, mapa_empresas)
            with bc2:
                if st.button("🗑️", key=f"{prefixo}_del_{ag['id']}", help="Remover", use_container_width=True):
                    supabase.table("agendamentos").delete().eq("id", ag["id"]).execute()
                    st.session_state.aviso_sucesso = "Agendamento removido."
                    st.rerun()

        with st.expander(f"✏️ Corrigir agendamento — {ag.get('hora_agendamento', '')} • {ag.get('veiculo', '')}"):
            opcoes_ag_emp = sorted({e for e in (nomes_empresas + [emp_nome]) if e})
            if opcoes_ag_emp:
                idx_ae = opcoes_ag_emp.index(emp_nome) if emp_nome in opcoes_ag_emp else 0
                ea_emp = st.selectbox(
                    "Empresa",
                    opcoes_ag_emp,
                    index=idx_ae,
                    key=f"{prefixo}_ea_emp_{ag['id']}_{ver}",
                )
            else:
                ea_emp = st.text_input("Empresa", value=emp_nome, key=f"{prefixo}_ea_emp_t_{ag['id']}_{ver}")

            ea_emp_info = mapa_empresas.get(ea_emp, {})
            ea_cat = ea_emp_info.get("categoria_servico") or "Vistoria"
            ea_opcoes_serv = opcoes_por_categoria(ea_cat)
            rotulo_serv = "Tipo de Serviço" if ea_cat == "Rastreamento" else "Tipo de Vistoria"
            idx_ts = ea_opcoes_serv.index(tipo_serv_ag) if tipo_serv_ag in ea_opcoes_serv else 0
            ea_serv = st.selectbox(
                rotulo_serv,
                ea_opcoes_serv,
                index=idx_ts,
                key=f"{prefixo}_ea_serv_{ag['id']}_{ver}_{ea_cat}",
            )

            ac1, ac2 = st.columns(2)
            with ac1:
                ea_cli = st.text_input("Cliente", value=ag.get("cliente_nome") or "", key=f"{prefixo}_ea_cli_{ag['id']}_{ver}")
            with ac2:
                ea_wa = st.text_input("WhatsApp do Cliente", value=ag.get("cliente_whatsapp") or "", key=f"{prefixo}_ea_wa_{ag['id']}_{ver}")

            ea_end = st.text_input("Endereço do Cliente", value=endereco_cli, key=f"{prefixo}_ea_end_{ag['id']}_{ver}")

            av1, av2 = st.columns([2, 1])
            with av1:
                ea_veic = st.text_input("Veículo", value=ag.get("veiculo") or "", key=f"{prefixo}_ea_veic_{ag['id']}_{ver}")
            with av2:
                ea_placa = st.text_input("Placa", value=ag.get("placa") or "", key=f"{prefixo}_ea_placa_{ag['id']}_{ver}")

            ad1, ad2 = st.columns(2)
            with ad1:
                ea_data = st.date_input(
                    "Data",
                    value=parse_data(ag.get("data_agendamento")),
                    format="DD/MM/YYYY",
                    key=f"{prefixo}_ea_data_{ag['id']}_{ver}",
                )
            with ad2:
                ea_hora = st.time_input(
                    "Horário",
                    value=parse_hora(ag.get("hora_agendamento")),
                    key=f"{prefixo}_ea_hora_{ag['id']}_{ver}",
                )

            if st.button("💾 Salvar Alterações", key=f"{prefixo}_ea_save_{ag['id']}_{ver}", type="primary", use_container_width=True):
                supabase.table("agendamentos").update(
                    {
                        "empresa_nome": ea_emp.strip(),
                        "tipo_servico": ea_serv,
                        "cliente_nome": ea_cli.strip(),
                        "cliente_whatsapp": ea_wa.strip(),
                        "endereco": ea_end.strip(),
                        "veiculo": ea_veic.strip(),
                        "placa": ea_placa.strip().upper(),
                        "data_agendamento": ea_data.isoformat(),
                        "hora_agendamento": ea_hora.strftime("%H:%M"),
                    }
                ).eq("id", ag["id"]).execute()
                st.session_state.form_ag_ver += 1
                st.session_state.aviso_sucesso = "Agendamento atualizado!"
                st.rerun()


def render_editor_os(vistoria: dict, mapa_empresas: dict, nomes_empresas: list, prefixo_key: str):
    ver_edit = st.session_state.fin_edit_ver
    emp_atual = vistoria.get("empresa_nome") or ""
    opcoes_emp = sorted({e for e in (nomes_empresas + [emp_atual]) if e})
    emp_info = mapa_empresas.get(emp_atual, {})
    cat_emp = emp_info.get("categoria_servico") or "Vistoria"
    opcoes_serv = TIPOS_RASTREAMENTO_OPCOES if cat_emp == "Rastreamento" else TIPOS_VISTORIA_OPCOES

    with st.form(f"edit_os_{prefixo_key}_{vistoria['id']}_{ver_edit}"):
        st.markdown(
            f"**OS #{vistoria['id']} — {vistoria.get('veiculo', '')} ({vistoria.get('placa', '')})**"
        )

        if opcoes_emp:
            idx_emp = opcoes_emp.index(emp_atual) if emp_atual in opcoes_emp else 0
            e_emp = st.selectbox("Empresa", opcoes_emp, index=idx_emp)
        else:
            e_emp = st.text_input("Empresa", value=emp_atual)

        c1, c2 = st.columns(2)
        with c1:
            e_cli = st.text_input("Cliente / Segurado", value=vistoria.get("cliente_nome") or "")
        with c2:
            e_veic = st.text_input("Veículo", value=vistoria.get("veiculo") or "")

        e_end = st.text_input("Endereço do Cliente", value=vistoria.get("endereco") or "")

        c3, c4 = st.columns(2)
        with c3:
            e_placa = st.text_input("Placa", value=vistoria.get("placa") or "")
        with c4:
            e_data = st.date_input(
                "Data",
                value=parse_data(vistoria.get("data_vistoria")),
                format="DD/MM/YYYY",
            )

        c5, c6, c7 = st.columns(3)
        with c5:
            e_valor = st.number_input(
                "Valor (R$)",
                min_value=0.0,
                value=float(vistoria.get("valor") or 0.0),
                step=1.0,
                format="%.2f",
            )
        with c6:
            todas_op_serv = opcoes_serv + [
                o for o in (TIPOS_VISTORIA_OPCOES + TIPOS_RASTREAMENTO_OPCOES) if o not in opcoes_serv
            ]
            serv_atual = extrair_servico_os(vistoria.get("tipo_vistoria"), cat_emp)
            idx_s_op = todas_op_serv.index(serv_atual) if serv_atual in todas_op_serv else 0
            e_serv = st.selectbox("Tipo de Serviço", todas_op_serv, index=idx_s_op)
        with c7:
            statuses = ["Pendente", "Recebido", "Sem Cobrança"]
            s_atual = vistoria.get("status_pagamento") or "Pendente"
            idx_st = statuses.index(s_atual) if s_atual in statuses else 0
            e_status = st.selectbox("Status", statuses, index=idx_st)

        b1, b2 = st.columns(2)
        with b1:
            salvar_ed = st.form_submit_button(
                "💾 Salvar Correção", type="primary", use_container_width=True
            )
        with b2:
            excluir_os = st.form_submit_button("🗑️ Excluir OS", use_container_width=True)

        if salvar_ed:
            if not e_emp.strip() or not e_veic.strip() or not e_placa.strip():
                st.warning("Preencha Empresa, Veículo e Placa.")
            else:
                nova_data_rec = vistoria.get("data_recebimento")
                if e_status == "Recebido" and not nova_data_rec:
                    nova_data_rec = hoje_br().isoformat()
                elif e_status != "Recebido":
                    nova_data_rec = None

                try:
                    supabase.table("vistorias").update(
                        {
                            "empresa_nome": e_emp.strip(),
                            "cliente_nome": e_cli.strip(),
                            "endereco": e_end.strip(),
                            "veiculo": e_veic.strip(),
                            "placa": e_placa.strip().upper(),
                            "data_vistoria": e_data.isoformat(),
                            "valor": 0.0 if e_status == "Sem Cobrança" else float(e_valor),
                            "tipo_vistoria": e_serv,
                            "status_pagamento": e_status,
                            "data_recebimento": nova_data_rec,
                        }
                    ).eq("id", vistoria["id"]).execute()
                    st.session_state.fin_edit_ver += 1
                    st.session_state.aviso_sucesso = f"OS #{vistoria['id']} atualizada com sucesso!"
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao atualizar OS: {e}")

        if excluir_os:
            try:
                supabase.table("vistorias").delete().eq("id", vistoria["id"]).execute()
                st.session_state.fin_edit_ver += 1
                st.session_state.aviso_sucesso = f"OS #{vistoria['id']} excluída com sucesso!"
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao excluir OS: {e}")


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
        ("Endereço", vistoria.get("endereco") or "-"),
        ("Veículo", vistoria.get("veiculo", "-")),
        ("Placa", vistoria.get("placa", "-")),
        ("Data", fmt_data_br(vistoria.get("data_vistoria"))),
        ("Tipo de Serviço", vistoria.get("tipo_vistoria", "Cautelar")),
        (
            "Valor do Serviço",
            "Sem Cobrança"
            if vistoria.get("status_pagamento") == "Sem Cobrança"
            else fmt_moeda(vistoria.get("valor", 0)),
        ),
        ("Status Financeiro", vistoria.get("status_pagamento", "Pendente")),
    ]
    if vistoria.get("data_recebimento"):
        campos.append(("Data do Recebimento", fmt_data_br(vistoria.get("data_recebimento"))))

    for rotulo, valor in campos:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(52, 8, limpar_latin1(f"{rotulo}:"), border=0)
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 8, limpar_latin1(str(valor)), border=0)

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

    cobraveis = [v for v in vistorias if v.get("status_pagamento") != "Sem Cobrança"]
    total_geral = sum(float(v.get("valor") or 0) for v in cobraveis)
    total_recebido = sum(
        float(v.get("valor") or 0) for v in cobraveis if v.get("status_pagamento") == "Recebido"
    )
    total_pendente = total_geral - total_recebido

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(
        0,
        7,
        limpar_latin1(
            f"Qtd. OS: {len(vistorias)}   |   Total Cobrável: {fmt_moeda(total_geral)}   |   "
            f"Recebido: {fmt_moeda(total_recebido)}   |   Pendente: {fmt_moeda(total_pendente)}"
        ),
        ln=True,
    )
    pdf.ln(4)

    pdf.set_fill_color(239, 230, 248)
    pdf.set_text_color(78, 26, 107)
    pdf.set_font("Helvetica", "B", 8.5)
    colunas = [
        ("Data", 20),
        ("Empresa", 38),
        ("Veículo", 39),
        ("Placa", 21),
        ("Serviço", 30),
        ("Status", 22),
        ("Valor", 20),
    ]
    for nome_col, largura in colunas:
        pdf.cell(largura, 8, limpar_latin1(nome_col), border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_text_color(31, 41, 55)
    pdf.set_font("Helvetica", "", 8)
    for v in vistorias:
        st_p = str(v.get("status_pagamento", "Pendente"))
        val_txt = "-" if st_p == "Sem Cobrança" else fmt_moeda(v.get("valor", 0))
        pdf.cell(20, 7, limpar_latin1(fmt_data_br(v.get("data_vistoria"))), border=1, align="C")
        pdf.cell(38, 7, limpar_latin1(str(v.get("empresa_nome", ""))[:20]), border=1)
        pdf.cell(39, 7, limpar_latin1(str(v.get("veiculo", ""))[:21]), border=1)
        pdf.cell(21, 7, limpar_latin1(str(v.get("placa", "")).upper()[:10]), border=1, align="C")
        pdf.cell(30, 7, limpar_latin1(str(v.get("tipo_vistoria", "Cautelar"))[:17]), border=1, align="C")
        pdf.cell(22, 7, limpar_latin1(st_p[:12]), border=1, align="C")
        pdf.cell(20, 7, limpar_latin1(val_txt), border=1, align="R")
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

    render_html(
        """
        <div class="login-box">
            <div class="login-icon">🚗</div>
            <h1 class="login-title">Controle de Vistorias</h1>
            <div class="login-sub-title">Acesso / Login</div>
            <div class="login-sub">Entre com as suas credenciais para continuar</div>
        </div>
        """
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

        render_html(
            "<p style='text-align:center;color:var(--muted);font-size:0.8rem;margin-top:16px;'>"
            "Vistorias Pro • AD Vistoria</p>"
        )


# =========================================================
# TELA PERFIL (NOME, TELEFONE E PONTO BASE)
# =========================================================
def tela_perfil():
    st.markdown("### 👤 Meu Perfil & Ponto Base")
    mostrar_aviso_pendente()

    perfil = carregar_perfil()
    if perfil.get("_erro_tabela"):
        st.warning("Rode o SQL do Passo 1 no Supabase para criar a tabela `vistorias_perfil`.")
        return

    with st.form("form_perfil_usuario"):
        st.markdown("**Dados do Vistoriador / Ponto de Partida**")
        p_nome = st.text_input("Seu Nome", value=perfil.get("nome") or "")
        p_tel = st.text_input("Seu Telefone / WhatsApp", value=perfil.get("telefone") or "")
        p_base = st.text_input(
            "Ponto Base (Endereço completo com rua, bairro e cidade)",
            value=perfil.get("ponto_base") or "",
        )
        salvar_p = st.form_submit_button("💾 Salvar Perfil", type="primary", use_container_width=True)

        if salvar_p:
            payload = {
                "nome": p_nome.strip(),
                "telefone": p_tel.strip(),
                "ponto_base": p_base.strip(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                if perfil.get("id"):
                    supabase.table("vistorias_perfil").update(payload).eq("id", perfil["id"]).execute()
                else:
                    supabase.table("vistorias_perfil").insert(payload).execute()
                st.session_state.aviso_sucesso = "Perfil e Ponto Base salvos com sucesso!"
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar perfil: {e}")

    base_atual = (perfil.get("ponto_base") or "").strip()
    if base_atual:
        coord = geocodificar_endereco(base_atual)
        if coord:
            render_html(
                f"""
                <div class="cv-card-green">
                    <div class="cv-card-green-title">✅ Ponto Base localizado no mapa</div>
                    <div class="cv-card-green-sub">
                        📍 {esc(base_atual)}<br>
                        A Agenda já está calculando a distância em km a partir deste endereço.
                    </div>
                </div>
                """
            )
        else:
            st.warning(
                "Não consegui localizar esse endereço exato no mapa para o cálculo de km. "
                "Tente incluir Rua, Bairro, Cidade e Estado (ex.: Rua ..., Bairro ..., Natal - RN)."
            )
    else:
        st.info("Cadastre seu Ponto Base acima para o sistema indicar qual atendimento do dia está mais perto de você.")


# =========================================================
# TELA 2: AGENDA DE VISTORIAS (COM DISTÂNCIA DO PONTO BASE)
# =========================================================
def tela_agenda():
    st.markdown("### 📅 Agenda de Vistorias")
    mostrar_aviso_pendente()

    perfil = carregar_perfil()
    ponto_base = (perfil.get("ponto_base") or "").strip()

    empresas = carregar_empresas()
    nomes_empresas = [e["nome"] for e in empresas]
    mapa_empresas = {e["nome"]: e for e in empresas}
    hoje = hoje_br()
    amanha = hoje + timedelta(days=1)
    ver = st.session_state.form_ag_ver

    with st.expander("➕ Novo Agendamento", expanded=False):
        if nomes_empresas:
            empresa_sel = st.selectbox("Empresa", nomes_empresas, key=f"ag_emp_{ver}")
            emp_obj = mapa_empresas.get(empresa_sel, {})
            cat_emp = emp_obj.get("categoria_servico") or "Vistoria"
            opcoes_serv = parse_tipos_empresa(emp_obj.get("tipo_vistoria"), cat_emp)
            if len(opcoes_serv) == 1:
                opcoes_serv = opcoes_por_categoria(cat_emp)
        else:
            empresa_sel = st.text_input("Empresa", key=f"ag_emp_txt_{ver}")
            cat_emp = "Vistoria"
            opcoes_serv = TIPOS_VISTORIA_OPCOES

        rotulo_serv = "Tipo de Serviço (Rastreamento)" if cat_emp == "Rastreamento" else "Tipo de Vistoria"
        tipo_serv_sel = st.selectbox(
            rotulo_serv,
            opcoes_serv,
            key=f"ag_serv_{ver}_{empresa_sel}_{cat_emp}",
        )

        c1, c2 = st.columns(2)
        with c1:
            cliente_nome = st.text_input("Cliente", key=f"ag_cli_{ver}")
        with c2:
            cliente_wa = st.text_input("WhatsApp do Cliente", key=f"ag_wa_{ver}")

        endereco_cli = st.text_input(
            "Endereço do Cliente (rua, bairro e cidade para cálculo de km)",
            key=f"ag_end_{ver}",
        )

        v1, v2 = st.columns([2, 1])
        with v1:
            veiculo = st.text_input("Veículo", key=f"ag_veic_{ver}")
        with v2:
            placa = st.text_input("Placa", key=f"ag_placa_{ver}")

        d1, d2 = st.columns(2)
        with d1:
            data_ag = st.date_input("Data", value=hoje, format="DD/MM/YYYY", key=f"ag_data_{ver}")
        with d2:
            hora_ag = st.time_input("Horário", value=time(8, 0), key=f"ag_hora_{ver}")

        if st.button("📅 Salvar na Agenda", key=f"btn_salvar_ag_{ver}", type="primary", use_container_width=True):
            if not empresa_sel or not cliente_nome.strip() or not veiculo.strip() or not placa.strip():
                st.warning("Preencha Empresa, Cliente, Veículo e Placa.")
            else:
                try:
                    supabase.table("agendamentos").insert(
                        {
                            "empresa_id": None,
                            "empresa_nome": empresa_sel.strip(),
                            "tipo_servico": tipo_serv_sel,
                            "cliente_nome": cliente_nome.strip(),
                            "cliente_whatsapp": cliente_wa.strip(),
                            "endereco": endereco_cli.strip(),
                            "veiculo": veiculo.strip(),
                            "placa": placa.strip().upper(),
                            "data_agendamento": data_ag.isoformat(),
                            "hora_agendamento": hora_ag.strftime("%H:%M"),
                            "status": "Agendada",
                        }
                    ).execute()
                    st.session_state.form_ag_ver += 1
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
            render_html("<div style='height:27px;'></div>")
            if st.button("🔍 Ver Data", key="btn_ver_data_cal", type="primary", use_container_width=True):
                st.session_state.agenda_filtro = "Data"
                st.session_state.agenda_data_busca = data_pesquisa
                st.rerun()

    todos_agendamentos = carregar_agendamentos(apenas_agendadas=False)

    if st.session_state.agenda_filtro == "Esta Semana":
        semana_ags = [
            ag
            for ag in todos_agendamentos
            if inicio_semana.isoformat() <= str(ag.get("data_agendamento", ""))[:10] <= fim_semana.isoformat()
        ]
        st.markdown(
            f"#### 📆 Agenda de Esta Semana ({inicio_semana.strftime('%d/%m')} a {fim_semana.strftime('%d/%m')}) — {len(semana_ags)} registro(s)"
        )
        if not semana_ags:
            st.info("Nenhum agendamento registrado para esta semana.")
            return

        por_dia = {}
        for ag in semana_ags:
            por_dia.setdefault(str(ag.get("data_agendamento", ""))[:10], []).append(ag)

        for dt_iso in sorted(por_dia.keys()):
            dt_obj = parse_data(dt_iso)
            lista_dia = por_dia[dt_iso]
            horarios_str = ", ".join(sorted(x.get("hora_agendamento", "") for x in lista_dia))
            h1, h2 = st.columns([3, 1.3])
            with h1:
                st.markdown(
                    f"**📅 {DIAS_SEMANA_COMPLETO[dt_obj.weekday()]}, {dt_obj.strftime('%d/%m/%Y')}** "
                    f"({len(lista_dia)} horário(s): {horarios_str})"
                )
            with h2:
                if st.button("Ver dia completo", key=f"ir_dia_{dt_iso}", use_container_width=True):
                    st.session_state.agenda_filtro = "Data"
                    st.session_state.agenda_data_busca = dt_obj
                    st.rerun()

            for ag in lista_dia:
                d_info = (
                    calcular_distancia_rota(ponto_base, ag.get("endereco"))
                    if (ponto_base and ag.get("endereco"))
                    else None
                )
                render_card_agendamento(
                    ag,
                    mapa_empresas,
                    nomes_empresas,
                    prefixo=f"sem_{dt_iso}",
                    ponto_base=ponto_base,
                    dist_info=d_info,
                    mostrar_data=False,
                )
        return

    if st.session_state.agenda_filtro == "Hoje":
        data_ref = hoje
    elif st.session_state.agenda_filtro == "Amanhã":
        data_ref = amanha
    else:
        data_ref = st.session_state.agenda_data_busca or hoje

    ags_do_dia = [
        ag for ag in todos_agendamentos if str(ag.get("data_agendamento", ""))[:10] == data_ref.isoformat()
    ]

    distancias_dia = {}
    if ponto_base and ags_do_dia:
        for ag in ags_do_dia:
            end_ag = (ag.get("endereco") or "").strip()
            if end_ag:
                info = calcular_distancia_rota(ponto_base, end_ag)
                if info:
                    distancias_dia[ag["id"]] = info

    pendentes_com_dist = [
        (ag, distancias_dia[ag["id"]])
        for ag in ags_do_dia
        if ag["id"] in distancias_dia and ag.get("status") != "Concluida"
    ]
    pendentes_com_dist.sort(key=lambda par: par[1]["km"])
    id_mais_proximo = pendentes_com_dist[0][0]["id"] if pendentes_com_dist else None

    horarios_preenchidos = sorted(x.get("hora_agendamento", "") for x in ags_do_dia)
    resumo_horarios = (
        f"Horários preenchidos: <strong>{esc(', '.join(horarios_preenchidos))}</strong>"
        if horarios_preenchidos
        else "Nenhum horário preenchido ainda — todos os horários estão livres."
    )

    render_html(
        f"""
        <div class="cv-day-summary">
            <div style="font-size:1.05rem;font-weight:800;">
                📅 {DIAS_SEMANA_COMPLETO[data_ref.weekday()]}, {data_ref.strftime('%d/%m/%Y')}
            </div>
            <div style="font-size:0.88rem;margin-top:4px;">
                {len(ags_do_dia)} agendamento(s) no dia • {resumo_horarios}
            </div>
        </div>
        """
    )

    if pendentes_com_dist:
        linhas_rota = []
        for idx, (ag_r, d_r) in enumerate(pendentes_com_dist, start=1):
            tag = '<span class="cv-badge-green">⭐ Mais próximo</span> ' if idx == 1 else f"<strong>{idx}º</strong> "
            min_txt = f" (~{d_r['minutos']} min)" if d_r.get("minutos") else ""
            linhas_rota.append(
                f'<div class="cv-route-item">'
                f'{tag}<strong>{fmt_km(d_r["km"])} do ponto base</strong>{min_txt} • '
                f'⏰ {esc(ag_r.get("hora_agendamento", ""))} • {esc(ag_r.get("veiculo", ""))} ({esc(ag_r.get("cliente_nome", ""))}) '
                f'<span style="color:var(--muted);">— {esc(ag_r.get("endereco", ""))}</span>'
                f'</div>'
            )
        render_html(
            f"""
            <div class="cv-route-box">
                <div style="font-weight:800;font-size:0.96rem;margin-bottom:6px;color:var(--text);">
                    🧭 Proximidade do Ponto Base ({esc(ponto_base)})
                </div>
                {''.join(linhas_rota)}
            </div>
            """
        )
    elif ags_do_dia and not ponto_base:
        st.info("💡 Cadastre seu **Ponto Base** em **👤 Perfil** (no topo) para ver a distância em km de cada cliente.")

    por_hora = {}
    for ag in ags_do_dia:
        h = extrair_hora_int(ag.get("hora_agendamento"))
        por_hora.setdefault(h, []).append(ag)

    faixa_horas = sorted(set(range(7, 20)) | set(por_hora.keys()))

    for h in faixa_horas:
        itens_hora = por_hora.get(h, [])
        if itens_hora:
            for ag in sorted(itens_hora, key=lambda x: x.get("hora_agendamento", "")):
                render_card_agendamento(
                    ag,
                    mapa_empresas,
                    nomes_empresas,
                    prefixo=f"dia_{data_ref.isoformat()}",
                    ponto_base=ponto_base,
                    dist_info=distancias_dia.get(ag["id"]),
                    eh_mais_proximo=(ag["id"] == id_mais_proximo),
                    mostrar_data=False,
                )
        else:
            render_html(
                f"""
                <div class="cv-slot-free">
                    <span>🕒 {h:02d}:00</span>
                    <span class="cv-slot-free-tag">Livre</span>
                </div>
                """
            )


# =========================================================
# TELA 3: ORDEM DE SERVIÇO
# =========================================================
def tela_ordem_servico():
    st.markdown("### ✅ Ordem de Serviço")
    mostrar_aviso_pendente()

    perfil = carregar_perfil()
    ponto_base = (perfil.get("ponto_base") or "").strip()

    empresas = carregar_empresas()
    nomes_empresas = [e["nome"] for e in empresas]
    mapa_empresas = {e["nome"]: e for e in empresas}
    hoje = hoje_br()
    ver = st.session_state.form_os_ver
    imp = st.session_state.get("os_importada")

    rotulo_exp = "📋 Concluir Ordem de Serviço (importada da Agenda)" if imp else "➕ Nova Ordem de Serviço"
    with st.expander(rotulo_exp, expanded=bool(imp)):
        if imp:
            render_html('<div class="cv-banner-import">📅 Dados carregados da Agenda</div>')
            if st.button("Limpar dados importados (nova OS avulsa)", use_container_width=True):
                st.session_state.os_importada = None
                st.session_state.form_os_ver += 1
                st.rerun()

        emp_padrao = imp["empresa_nome"] if imp else (nomes_empresas[0] if nomes_empresas else "")
        if nomes_empresas:
            idx_emp = nomes_empresas.index(emp_padrao) if emp_padrao in nomes_empresas else 0
            empresa_sel = st.selectbox("Empresa", nomes_empresas, index=idx_emp, key=f"os_emp_{ver}")
            emp_atual_obj = mapa_empresas[empresa_sel]
            categoria_emp = emp_atual_obj.get("categoria_servico") or "Vistoria"
            sem_financeiro = bool(emp_atual_obj.get("sem_financeiro"))
            valor_sugerido = float(emp_atual_obj.get("valor_padrao") or 0.0)
            opcoes_serv = opcoes_por_categoria(categoria_emp)
            tipo_sugerido = parse_tipos_empresa(emp_atual_obj.get("tipo_vistoria"), categoria_emp)[0]
            if imp and empresa_sel == imp.get("empresa_nome"):
                if imp.get("valor_padrao"):
                    valor_sugerido = float(imp["valor_padrao"])
                if imp.get("tipo_padrao") in opcoes_serv:
                    tipo_sugerido = imp["tipo_padrao"]
        else:
            empresa_sel = st.text_input("Empresa", value=emp_padrao, key=f"os_emp_txt_{ver}")
            categoria_emp = "Vistoria"
            sem_financeiro = False
            valor_sugerido = float(imp["valor_padrao"]) if imp else 0.0
            opcoes_serv = TIPOS_VISTORIA_OPCOES
            tipo_sugerido = imp.get("tipo_padrao", "Cautelar") if imp else "Cautelar"

        if sem_financeiro:
            st.info("📡 Empresa sem controle financeiro: esta OS será registrada apenas no Histórico/PDF (sem cobrança).")

        rotulo_serv = "Tipo de Serviço (Rastreamento)" if categoria_emp == "Rastreamento" else "Tipo de Vistoria"
        idx_tipo = opcoes_serv.index(tipo_sugerido) if tipo_sugerido in opcoes_serv else 0
        servico_escolhido = st.selectbox(
            rotulo_serv,
            opcoes_serv,
            index=idx_tipo,
            key=f"os_cat_{ver}_{empresa_sel}_{categoria_emp}",
        )

        cliente_val = st.text_input(
            "Cliente / Segurado (opcional)",
            value=imp.get("cliente_nome", "") if imp else "",
            key=f"os_cli_{ver}",
        )
        endereco_val = st.text_input(
            "Endereço do Cliente",
            value=imp.get("endereco", "") if imp else "",
            key=f"os_end_{ver}",
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

        data_ini = parse_data(imp["data_vistoria"]) if (imp and imp.get("data_vistoria")) else hoje

        if sem_financeiro:
            data_val = st.date_input("Data", value=data_ini, format="DD/MM/YYYY", key=f"os_data_{ver}")
            valor_val = 0.0
        else:
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

        if categoria_emp == "Vistoria":
            st.markdown("**Modalidade**")
            tv1, tv2 = st.columns(2)
            with tv1:
                if st.button(
                    "Nova",
                    key=f"btn_mod_nova_{ver}",
                    type="primary" if st.session_state.modalidade_os == "Nova" else "secondary",
                    use_container_width=True,
                ):
                    st.session_state.modalidade_os = "Nova"
                    st.rerun()
            with tv2:
                if st.button(
                    "Renovação",
                    key=f"btn_mod_renov_{ver}",
                    type="primary" if st.session_state.modalidade_os == "Renovação" else "secondary",
                    use_container_width=True,
                ):
                    st.session_state.modalidade_os = "Renovação"
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
                render_html('<span class="cv-badge-purple">✔ 1 foto anexada</span>')

        render_html('<span class="marker-red"></span>')
        concluir = st.button(
            "✔ Concluir Ordem de Serviço",
            key=f"btn_concluir_os_{ver}",
            use_container_width=True,
        )

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

                tipo_final = (
                    f"{servico_escolhido} ({st.session_state.modalidade_os})"
                    if categoria_emp == "Vistoria"
                    else servico_escolhido
                )
                status_final = "Sem Cobrança" if sem_financeiro else "Pendente"

                payload = {
                    "agendamento_id": imp["agendamento_id"] if imp else None,
                    "empresa_id": None,
                    "empresa_nome": empresa_sel.strip(),
                    "cliente_nome": cliente_val.strip(),
                    "endereco": endereco_val.strip(),
                    "veiculo": veiculo_val.strip(),
                    "placa": placa_val.strip().upper(),
                    "data_vistoria": data_val.isoformat(),
                    "valor": 0.0 if sem_financeiro else float(valor_val),
                    "tipo_vistoria": tipo_final,
                    "foto_base64": foto_b64,
                    "status_pagamento": status_final,
                    "data_recebimento": None,
                }
                try:
                    supabase.table("vistorias").insert(payload).execute()
                    if imp and imp.get("agendamento_id"):
                        supabase.table("agendamentos").update({"status": "Concluida"}).eq(
                            "id", imp["agendamento_id"]
                        ).execute()
                    st.session_state.os_importada = None
                    st.session_state.modalidade_os = "Nova"
                    st.session_state.form_os_ver += 1
                    st.session_state.aviso_sucesso = (
                        "Serviço concluído e salvo no Histórico (sem cobrança no Financeiro)!"
                        if sem_financeiro
                        else "Ordem de Serviço concluída e enviada para o Financeiro!"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao concluir Ordem de Serviço: {e}")

    render_html("<div style='height:6px;'></div>")
    s1, s2, s3 = st.columns(3)
    for col, nome_sub in [
        (s1, "OS do Dia"),
        (s2, "Próximas OS"),
        (s3, "Histórico de OS"),
    ]:
        with col:
            if st.button(
                nome_sub,
                key=f"sub_os_{nome_sub}",
                type="primary" if st.session_state.os_subaba == nome_sub else "secondary",
                use_container_width=True,
            ):
                st.session_state.os_subaba = nome_sub
                st.rerun()

    agendadas = carregar_agendamentos(apenas_agendadas=True)
    vistorias = carregar_vistorias()

    if st.session_state.os_subaba == "OS do Dia":
        ags_hoje = [a for a in agendadas if str(a.get("data_agendamento", ""))[:10] == hoje.isoformat()]
        concl_hoje = [v for v in vistorias if str(v.get("data_vistoria", ""))[:10] == hoje.isoformat()]

        st.markdown(f"#### 📌 Pendentes de Hoje ({hoje.strftime('%d/%m/%Y')}) — {len(ags_hoje)}")
        if not ags_hoje:
            st.info("Nenhuma Ordem de Serviço pendente na agenda de hoje.")
        else:
            for ag in ags_hoje:
                d_info = (
                    calcular_distancia_rota(ponto_base, ag.get("endereco"))
                    if (ponto_base and ag.get("endereco"))
                    else None
                )
                render_card_agendamento(
                    ag,
                    mapa_empresas,
                    nomes_empresas,
                    prefixo="os_hoje",
                    ponto_base=ponto_base,
                    dist_info=d_info,
                    mostrar_data=False,
                )

        st.markdown(f"#### ✅ Concluídas Hoje — {len(concl_hoje)}")
        if not concl_hoje:
            st.caption("Nenhuma Ordem de Serviço concluída hoje ainda.")
        else:
            for v in concl_hoje:
                _render_card_os_concluida(v, mapa_empresas, nomes_empresas, prefixo="os_dia_conc")

    elif st.session_state.os_subaba == "Próximas OS":
        proximas = [a for a in agendadas if str(a.get("data_agendamento", ""))[:10] > hoje.isoformat()]
        st.markdown(f"#### 📆 Próximas Ordens de Serviço ({len(proximas)})")
        if not proximas:
            st.info("Nenhuma Ordem de Serviço futura agendada.")
        else:
            for ag in proximas:
                d_info = (
                    calcular_distancia_rota(ponto_base, ag.get("endereco"))
                    if (ponto_base and ag.get("endereco"))
                    else None
                )
                render_card_agendamento(
                    ag,
                    mapa_empresas,
                    nomes_empresas,
                    prefixo="os_prox",
                    ponto_base=ponto_base,
                    dist_info=d_info,
                    mostrar_data=True,
                )

    else:
        st.markdown(f"#### 🗂️ Histórico de Ordens de Serviço ({len(vistorias)})")
        if not vistorias:
            st.info("Nenhuma Ordem de Serviço concluída ainda.")
        else:
            for v in vistorias:
                _render_card_os_concluida(v, mapa_empresas, nomes_empresas, prefixo="os_hist")


def _render_card_os_concluida(v: dict, mapa_empresas: dict, nomes_empresas: list, prefixo: str):
    st_pg = v.get("status_pagamento", "Pendente")
    if st_pg == "Recebido":
        badge = "cv-badge-green"
    elif st_pg == "Sem Cobrança":
        badge = "cv-badge-amber"
    else:
        badge = "cv-badge-purple"

    valor_str = "Sem cobrança" if st_pg == "Sem Cobrança" else fmt_moeda(v.get("valor", 0))
    end_txt = f"<div class='cv-card-sub'>📍 {esc(v['endereco'])}</div>" if v.get("endereco") else ""

    render_html(
        f"""
        <div class="cv-card">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <span class="cv-card-title">OS #{v['id']} • {esc(v['veiculo'])} ({esc(v['placa'])})</span>
                <span class="{badge}">{esc(st_pg)}</span>
            </div>
            <div class="cv-card-sub">
                🏢 {esc(v['empresa_nome'])} • 📅 {fmt_data_br(v['data_vistoria'])} • 🔧 {esc(v.get('tipo_vistoria', 'Cautelar'))} •
                <strong style="color:var(--text);">{valor_str}</strong>
            </div>
            {end_txt}
        </div>
        """
    )
    with st.expander(f"Ver foto / Corrigir / Excluir — OS #{v['id']}"):
        if v.get("cliente_nome"):
            st.write(f"**Cliente:** {v['cliente_nome']}")
        if v.get("foto_base64"):
            st.image(base64_para_bytes(v["foto_base64"]), width=260)
        render_editor_os(v, mapa_empresas, nomes_empresas, prefixo_key=prefixo)


# =========================================================
# TELA 4: EMPRESAS PARCEIRAS (VISTORIA OU RASTREAMENTO)
# =========================================================
def tela_empresas():
    st.markdown("### 🤝 Empresas Parceiras")
    mostrar_aviso_pendente()

    ver = st.session_state.form_emp_ver
    with st.expander("➕ Adicionar Nova Empresa", expanded=False):
        nome = st.text_input("Nome da Empresa", key=f"emp_nome_{ver}")
        categoria_sel = st.radio(
            "Serviço que a empresa presta",
            CATEGORIAS_EMPRESA,
            horizontal=True,
            key=f"emp_cat_{ver}",
        )

        if categoria_sel == "Rastreamento":
            tipos_sel = st.multiselect(
                "Tipo de Serviço",
                TIPOS_RASTREAMENTO_OPCOES,
                default=TIPOS_RASTREAMENTO_OPCOES,
                key=f"emp_tipos_ras_{ver}",
            )
            sem_fin = st.checkbox(
                "Sem controle financeiro (apenas agenda de horários, sem cobrança)",
                value=True,
                key=f"emp_semfin_ras_{ver}",
            )
        else:
            tipos_sel = st.multiselect(
                "Tipo de Vistoria",
                TIPOS_VISTORIA_OPCOES,
                default=["Cautelar"],
                key=f"emp_tipos_vis_{ver}",
            )
            sem_fin = st.checkbox(
                "Sem controle financeiro (apenas agenda)",
                value=False,
                key=f"emp_semfin_vis_{ver}",
            )

        responsavel = st.text_input("Nome do Responsável", key=f"emp_resp_{ver}")
        whatsapp = st.text_input("Celular (WhatsApp)", key=f"emp_wa_{ver}")

        if not sem_fin:
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
        else:
            dia_pagamento = 15
            valor_padrao = 0.0

        if st.button("+ Salvar Empresa", key=f"btn_salvar_emp_{ver}", type="primary", use_container_width=True):
            if not nome.strip():
                st.warning("Informe o nome da empresa.")
            else:
                op_default = opcoes_por_categoria(categoria_sel)[0]
                tipo_str = ", ".join(tipos_sel) if tipos_sel else op_default
                try:
                    supabase.table("vistorias_empresas").insert(
                        {
                            "nome": nome.strip(),
                            "categoria_servico": categoria_sel,
                            "tipo_vistoria": tipo_str,
                            "sem_financeiro": bool(sem_fin),
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
        cat_emp = emp.get("categoria_servico") or "Vistoria"
        sem_fin_emp = bool(emp.get("sem_financeiro"))
        tipos_label = emp.get("tipo_vistoria") or opcoes_por_categoria(cat_emp)[0]
        cat_badge = (
            '<span class="cv-badge-red">📡 Rastreamento</span>'
            if cat_emp == "Rastreamento"
            else '<span class="cv-badge-purple">🔍 Vistoria</span>'
        )
        fin_txt = (
            "Somente Agenda (Sem Cobrança)"
            if sem_fin_emp
            else f"Paga dia {int(emp.get('dia_pagamento') or 15):02d} • Padrão: {fmt_moeda(emp.get('valor_padrao', 0))}"
        )

        render_html(
            f"""
            <div class="cv-card">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;">
                    <div>
                        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                            <span class="cv-card-title">🏢 {esc(emp['nome'])}</span>
                            {cat_badge}
                            <span class="cv-badge-amber">{esc(tipos_label)}</span>
                        </div>
                        <div class="cv-card-sub">Resp.: {esc(emp.get('responsavel') or '-')} • {fin_txt}</div>
                    </div>
                    <div>{wa_html}</div>
                </div>
            </div>
            """
        )
        with st.expander(f"Detalhar / Editar / Excluir — {emp['nome']}"):
            e_nome = st.text_input("Nome da Empresa", value=emp["nome"], key=f"ee_nome_{emp['id']}_{ver}")
            idx_cat = CATEGORIAS_EMPRESA.index(cat_emp) if cat_emp in CATEGORIAS_EMPRESA else 0
            e_cat = st.radio(
                "Serviço que a empresa presta",
                CATEGORIAS_EMPRESA,
                index=idx_cat,
                horizontal=True,
                key=f"ee_cat_{emp['id']}_{ver}",
            )
            e_opcoes = opcoes_por_categoria(e_cat)
            e_rotulo = "Tipo de Serviço" if e_cat == "Rastreamento" else "Tipo de Vistoria"
            e_default_tipos = parse_tipos_empresa(emp.get("tipo_vistoria"), e_cat)
            e_tipos = st.multiselect(
                e_rotulo,
                e_opcoes,
                default=e_default_tipos,
                key=f"ee_tipos_{emp['id']}_{ver}_{e_cat}",
            )
            e_sem_fin = st.checkbox(
                "Sem controle financeiro (apenas agenda)",
                value=sem_fin_emp if e_cat == cat_emp else (e_cat == "Rastreamento"),
                key=f"ee_semfin_{emp['id']}_{ver}_{e_cat}",
            )
            e_resp = st.text_input("Nome do Responsável", value=emp.get("responsavel") or "", key=f"ee_resp_{emp['id']}_{ver}")
            e_wa = st.text_input("Celular (WhatsApp)", value=emp.get("whatsapp") or "", key=f"ee_wa_{emp['id']}_{ver}")

            if not e_sem_fin:
                ec1, ec2 = st.columns(2)
                with ec1:
                    e_dia = st.number_input(
                        "Dia do Pagamento",
                        1,
                        31,
                        int(emp.get("dia_pagamento") or 15),
                        key=f"ee_dia_{emp['id']}_{ver}",
                    )
                with ec2:
                    e_val = st.number_input(
                        "Valor Padrão (R$)",
                        min_value=0.0,
                        value=float(emp.get("valor_padrao") or 0.0),
                        step=1.0,
                        format="%.2f",
                        key=f"ee_val_{emp['id']}_{ver}",
                    )
            else:
                e_dia = 15
                e_val = 0.0

            b1, b2 = st.columns(2)
            with b1:
                if st.button("Salvar Alterações", key=f"ee_save_{emp['id']}_{ver}", type="primary", use_container_width=True):
                    tipo_str = ", ".join(e_tipos) if e_tipos else e_opcoes[0]
                    supabase.table("vistorias_empresas").update(
                        {
                            "nome": e_nome.strip(),
                            "categoria_servico": e_cat,
                            "tipo_vistoria": tipo_str,
                            "sem_financeiro": bool(e_sem_fin),
                            "responsavel": e_resp.strip(),
                            "whatsapp": e_wa.strip(),
                            "dia_pagamento": int(e_dia),
                            "valor_padrao": float(e_val),
                        }
                    ).eq("id", emp["id"]).execute()
                    st.session_state.form_emp_ver += 1
                    st.session_state.aviso_sucesso = f"Alterações de '{e_nome.strip()}' salvas!"
                    st.rerun()
            with b2:
                if st.button("Excluir Empresa", key=f"ee_del_{emp['id']}_{ver}", use_container_width=True):
                    supabase.table("vistorias_empresas").delete().eq("id", emp["id"]).execute()
                    st.session_state.form_emp_ver += 1
                    st.session_state.aviso_sucesso = f"Empresa '{emp['nome']}' removida."
                    st.rerun()


# =========================================================
# TELA 5: FINANCEIRO & CALENDÁRIO (IGNORA SEM COBRANÇA)
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
        render_html(f'<div class="cv-month-bar">📅 {titulo_mes}</div>')
    with nav3:
        if st.button("▶", key="mes_prox", use_container_width=True):
            if st.session_state.fin_mes == 12:
                st.session_state.fin_mes = 1
                st.session_state.fin_ano += 1
            else:
                st.session_state.fin_mes += 1
            st.rerun()

    todas_mes = carregar_vistorias(st.session_state.fin_ano, st.session_state.fin_mes)
    vistorias = [v for v in todas_mes if v.get("status_pagamento") != "Sem Cobrança"]

    empresas = carregar_empresas()
    nomes_empresas = [e["nome"] for e in empresas]
    mapa_empresas = {e["nome"]: e for e in empresas}
    dias_pgto = {e["nome"]: int(e.get("dia_pagamento") or 15) for e in empresas}

    pendentes = [v for v in vistorias if v.get("status_pagamento") != "Recebido"]
    recebidas = [v for v in vistorias if v.get("status_pagamento") == "Recebido"]

    total_pendente = sum(float(v.get("valor") or 0) for v in pendentes)
    total_recebido = sum(float(v.get("valor") or 0) for v in recebidas)

    render_html(
        f"""
        <div class="cv-hero-purple">
            <div class="cv-hero-label">💼 Total Líquido a Receber</div>
            <div class="cv-hero-value">{fmt_moeda(total_pendente)}</div>
            <div class="cv-hero-sub">{len(vistorias)} Vistorias Faturáveis • {len(pendentes)} OS Pendentes</div>
            <div class="cv-pill-row">
                <span class="cv-pill-light">Pendente: {fmt_moeda(total_pendente)}</span>
                <span class="cv-pill-green">✓ Já Recebido: {fmt_moeda(total_recebido)}</span>
            </div>
        </div>
        """
    )

    if PDF_DISPONIVEL and vistorias:
        pdf_mes = gerar_pdf_lote(vistorias, titulo_mes, "Todas (Financeiro)")
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

            render_html(
                f"""
                <div class="cv-card">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div class="cv-card-title">🏢 {esc(emp_nome)}</div>
                        <span class="{badge_cls}">Paga dia {dia_p:02d}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;">
                        <span class="cv-card-sub">{qtd} vistoria(s) concluída(s) • {fmt_moeda(media)} por OS</span>
                        <span style="font-weight:800;font-size:1.08rem;color:var(--text);">{fmt_moeda(soma)}</span>
                    </div>
                </div>
                """
            )

            col_baixa, col_pdf = st.columns([3.3, 1])
            with col_baixa:
                render_html('<span class="marker-green"></span>')
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

            with st.expander(f"✏️ Corrigir ou Excluir OS — {emp_nome} ({qtd})"):
                for os_item in lista_os:
                    render_editor_os(os_item, mapa_empresas, nomes_empresas, prefixo_key="fin_pend")

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

            render_html(
                f"""
                <div class="cv-card-green">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div class="cv-card-green-title">🏢 {esc(emp_nome)}</div>
                        <span class="cv-badge-green">✓ Recebido em {dt_label}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;">
                        <span class="cv-card-green-sub">{qtd} vistoria(s) • {fmt_moeda(media)} por OS</span>
                        <span class="cv-card-green-title">✓ {fmt_moeda(soma)}</span>
                    </div>
                    <div style="margin-top:8px;">
                        <span class="cv-badge-green">Baixa efetuada com sucesso</span>
                    </div>
                </div>
                """
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

            with st.expander(f"✏️ Corrigir ou Excluir OS recebidas — {emp_nome} ({qtd})"):
                for os_item in lista_os:
                    render_editor_os(os_item, mapa_empresas, nomes_empresas, prefixo_key="fin_rec")


# =========================================================
# TELA 6: RELATÓRIOS EM PDF
# =========================================================
def tela_pdf():
    st.markdown("### 📄 Relatórios em PDF")
    mostrar_aviso_pendente()

    if not PDF_DISPONIVEL:
        st.warning("Adicione `fpdf2` no seu arquivo `requirements.txt` para habilitar o download de PDFs.")

    todas = carregar_vistorias()
    empresas = carregar_empresas()
    nomes_empresas = [e["nome"] for e in empresas]
    mapa_empresas = {e["nome"]: e for e in empresas}

    if not todas:
        st.info("Nenhuma vistoria concluída registrada até o momento.")
        return

    empresas_unicas = ["Todas"] + sorted({v["empresa_nome"] for v in todas})
    f1, f2 = st.columns(2)
    with f1:
        f_emp = st.selectbox("Filtrar por Empresa", empresas_unicas)
    with f2:
        f_status = st.selectbox("Status Financeiro", ["Todos", "Pendente", "Recebido", "Sem Cobrança"])

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
        if st_pg == "Recebido":
            badge = "cv-badge-green"
        elif st_pg == "Sem Cobrança":
            badge = "cv-badge-amber"
        else:
            badge = "cv-badge-purple"

        val_str = "Sem cobrança" if st_pg == "Sem Cobrança" else fmt_moeda(v.get("valor", 0))
        end_txt = f"<div class='cv-card-sub'>📍 {esc(v['endereco'])}</div>" if v.get("endereco") else ""

        render_html(
            f"""
            <div class="cv-card">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span class="cv-card-title">OS #{v['id']} • {esc(v['veiculo'])} ({esc(v['placa'])})</span>
                    <span class="{badge}">{esc(st_pg)}</span>
                </div>
                <div class="cv-card-sub">
                    🏢 {esc(v['empresa_nome'])} • 📅 {fmt_data_br(v['data_vistoria'])} • 🔧 {esc(v.get('tipo_vistoria', 'Cautelar'))} •
                    <strong style="color:var(--text);">{val_str}</strong>
                </div>
                {end_txt}
            </div>
            """
        )
        with st.expander(f"Ver foto / PDF / Corrigir / Excluir — OS #{v['id']}"):
            if v.get("cliente_nome"):
                st.write(f"**Cliente:** {v['cliente_nome']}")
            if v.get("foto_base64"):
                st.image(base64_para_bytes(v["foto_base64"]), width=280)
            else:
                st.caption("Sem foto anexada.")

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

            st.markdown("---")
            render_editor_os(v, mapa_empresas, nomes_empresas, prefixo_key="pdf_tab")


# =========================================================
# BARRA SUPERIOR E NAVEGAÇÃO PRINCIPAL
# =========================================================
def main():
    if not st.session_state.autenticado:
        tela_login()
        return

    top1, top2, top3, top4 = st.columns([2.4, 1.0, 1.0, 0.9])
    with top1:
        render_html('<div class="brand-bar">🚗 Controle de Vistorias</div>')
    with top2:
        if st.button(
            "👤 Perfil",
            key="nav_perfil",
            type="primary" if st.session_state.pagina == "Perfil" else "secondary",
            use_container_width=True,
        ):
            st.session_state.pagina = "Perfil"
            st.rerun()
    with top3:
        botao_alternar_tema("app")
    with top4:
        if st.button("🚪 Sair", use_container_width=True):
            st.session_state.autenticado = False
            st.session_state.os_importada = None
            st.rerun()

    abas = [
        ("Agenda", "📅 Agenda"),
        ("Ordem de Serviço", "✅ Ordem de Serviço"),
        ("Empresas", "🤝 Empresas"),
        ("Financeiro", "💰 Financeiro"),
        ("PDF", "📄 PDF"),
    ]
    cols_nav = st.columns([1.0, 1.85, 1.15, 1.25, 0.85])
    for col, (chave, rotulo) in zip(cols_nav, abas):
        with col:
            tipo = "primary" if st.session_state.pagina == chave else "secondary"
            if st.button(rotulo, key=f"nav_{chave}", type=tipo, use_container_width=True):
                st.session_state.pagina = chave
                st.rerun()

    render_html("<div style='height:8px;'></div>")

    if st.session_state.pagina == "Perfil":
        tela_perfil()
    elif st.session_state.pagina == "Agenda":
        tela_agenda()
    elif st.session_state.pagina == "Ordem de Serviço":
        tela_ordem_servico()
    elif st.session_state.pagina == "Empresas":
        tela_empresas()
    elif st.session_state.pagina == "Financeiro":
        tela_financeiro()
    elif st.session_state.pagina == "PDF":
        tela_pdf()


if __name__ == "__main__":
    main()

import base64
import concurrent.futures
import hashlib
import hmac
import html
import io
import json
import math
import os
import re
import tempfile
import time as time_mod
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
SESSAO_TIMEOUT_SEGUNDOS = 3600  # 1 hora de inatividade

CATEGORIAS_EMPRESA = ["Vistoria", "Rastreamento"]
TIPOS_VISTORIA_OPCOES = ["Cautelar", "Sinistro", "Seguro", "Outra"]
TIPOS_RASTREAMENTO_OPCOES = ["Instalação", "Manutenção", "Retirada"]
HORARIOS_PADRAO = [f"{h:02d}:00" for h in range(7, 20)]

COLUNAS_VISTORIA_LEVE = (
    "id, agendamento_id, empresa_id, empresa_nome, cliente_nome, endereco, "
    "veiculo, placa, data_vistoria, valor, tipo_vistoria, status_pagamento, "
    "data_recebimento, created_at"
)

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
# CONTROLE DE SESSÃO PERSISTENTE (1 HORA DE INATIVIDADE)
# =========================================================
def _chave_assinatura() -> bytes:
    segredo_extra = str(st.secrets.get("SUPABASE_KEY", "ad-vistoria-key"))
    return f"{LOGIN_SENHA}:{segredo_extra}".encode("utf-8")


def _criar_token_sessao() -> str:
    exp = int(time_mod.time()) + SESSAO_TIMEOUT_SEGUNDOS
    msg = f"{LOGIN_USUARIO}|{exp}".encode("utf-8")
    sig = hmac.new(_chave_assinatura(), msg, hashlib.sha256).hexdigest()[:24]
    return f"{exp}.{sig}"


def _validar_token_sessao(token: str):
    if not token or "." not in str(token):
        return False, 0
    try:
        exp_str, sig = str(token).split(".", 1)
        exp = int(exp_str)
        if exp <= int(time_mod.time()):
            return False, exp
        msg = f"{LOGIN_USUARIO}|{exp}".encode("utf-8")
        esperada = hmac.new(_chave_assinatura(), msg, hashlib.sha256).hexdigest()[:24]
        return hmac.compare_digest(sig, esperada), exp
    except Exception:
        return False, 0


def _ler_token_url():
    try:
        val = st.query_params.get("sessao")
        if isinstance(val, list):
            return val[0] if val else None
        return val
    except Exception:
        return None


def _definir_token_url(token: str):
    try:
        st.query_params["sessao"] = token
    except Exception:
        pass


def _limpar_token_url():
    try:
        if "sessao" in st.query_params:
            del st.query_params["sessao"]
    except Exception:
        pass


def sincronizar_sessao():
    """Mantém o login ativo por até 1 hora de inatividade mesmo ao sair e voltar no celular."""
    agora = int(time_mod.time())
    token_url = _ler_token_url()

    if st.session_state.autenticado:
        ultimo = st.session_state.get("ultimo_acesso", agora)
        if agora - ultimo > SESSAO_TIMEOUT_SEGUNDOS:
            st.session_state.autenticado = False
            st.session_state.os_card_aberto_id = None
            st.session_state.aviso_expirado = True
            _limpar_token_url()
            return

        st.session_state.ultimo_acesso = agora
        if st.session_state.get("manter_conectado", True):
            valido, exp_atual = _validar_token_sessao(token_url)
            if (not valido) or (exp_atual - agora < SESSAO_TIMEOUT_SEGUNDOS - 300):
                _definir_token_url(_criar_token_sessao())
    else:
        if token_url:
            valido, exp_atual = _validar_token_sessao(token_url)
            if valido:
                st.session_state.autenticado = True
                st.session_state.manter_conectado = True
                st.session_state.ultimo_acesso = agora
                st.session_state.aviso_expirado = False
                if exp_atual - agora < SESSAO_TIMEOUT_SEGUNDOS - 300:
                    _definir_token_url(_criar_token_sessao())
            else:
                _limpar_token_url()
                st.session_state.aviso_expirado = True


# =========================================================
# ESTADO INICIAL DA SESSÃO
# =========================================================
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "manter_conectado" not in st.session_state:
    st.session_state.manter_conectado = True
if "ultimo_acesso" not in st.session_state:
    st.session_state.ultimo_acesso = int(time_mod.time())
if "aviso_expirado" not in st.session_state:
    st.session_state.aviso_expirado = False
if "tema" not in st.session_state:
    st.session_state.tema = "claro"
if "pagina" not in st.session_state:
    st.session_state.pagina = "Agenda"
if "mostrar_novo_ag" not in st.session_state:
    st.session_state.mostrar_novo_ag = False
if "os_card_aberto_id" not in st.session_state:
    st.session_state.os_card_aberto_id = None
if "modalidade_os_map" not in st.session_state:
    st.session_state.modalidade_os_map = {}
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
if "pending_cal_data" not in st.session_state:
    st.session_state.pending_cal_data = None
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
if "fotos_abertas" not in st.session_state:
    st.session_state.fotos_abertas = set()
if "pdfs_prontos" not in st.session_state:
    st.session_state.pdfs_prontos = {}


# =========================================================
# TEMA DINÂMICO (MODO CLARO E MODO ESCURO) + LAYOUT COMPACTO
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
            "late_card_bg": "#3B1219",
            "late_card_border": "#EF4444",
            "late_card_text": "#FEE2E2",
            "late_card_sub": "#FCA5A5",
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
            "nav_active_line": "#C084FC",
            "dot_bg": "#E9D5FF",
            "dot_border": "#E9D5FF",
            "shadow": "0 4px 14px rgba(0, 0, 0, 0.35)",
            "nav_shadow": "0 -4px 20px rgba(0, 0, 0, 0.45)",
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
            "late_card_bg": "#FEE2E2",
            "late_card_border": "#DC2626",
            "late_card_text": "#7F1D1D",
            "late_card_sub": "#991B1B",
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
            "nav_active_line": "#4E1A6B",
            "dot_bg": "#FFFFFF",
            "dot_border": "#4E1A6B",
            "shadow": "0 2px 10px rgba(17, 24, 39, 0.06)",
            "nav_shadow": "0 -4px 18px rgba(17, 24, 39, 0.10)",
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
            --late-card-bg: {cores['late_card_bg']};
            --late-card-border: {cores['late_card_border']};
            --late-card-text: {cores['late_card_text']};
            --late-card-sub: {cores['late_card_sub']};
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
            --nav-active-line: {cores['nav_active_line']};
            --dot-bg: {cores['dot_bg']};
            --dot-border: {cores['dot_border']};
            --shadow: {cores['shadow']};
            --nav-shadow: {cores['nav_shadow']};
        }}

        .stApp, [data-testid="stAppViewContainer"] {{
            background-color: var(--bg) !important;
            color: var(--text) !important;
        }}
        [data-testid="stHeader"] {{
            background-color: transparent !important;
            height: 2.6rem !important;
        }}
        .block-container {{
            max-width: 900px !important;
            padding-top: 3.4rem !important;
            padding-bottom: 6.5rem !important;
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
            border-radius: 16px !important;
            box-shadow: var(--shadow) !important;
        }}

        [data-baseweb="input"],
        [data-baseweb="base-input"],
        [data-baseweb="select"] > div,
        [data-testid="stFileUploader"] section,
        textarea {{
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
            margin-bottom: 8px;
            box-shadow: var(--shadow);
        }}
        [data-testid="stExpander"] summary p {{
            color: var(--text) !important;
            font-weight: 700;
        }}

        /* Expander recolhido de Distância do Ponto Base (borda verde à esquerda) */
        [data-testid="stExpander"]:has(.cv-route-inner-marker) {{
            border-left: 5px solid var(--green) !important;
            border-radius: 14px !important;
            margin-bottom: 10px !important;
        }}

        div[data-testid="stElementContainer"]:has(.marker-hidden),
        div.element-container:has(.marker-hidden) {{
            display: none !important;
        }}

        /* =====================================================
           TOPO FIXO EM LINHA ÚNICA (MARCA + BOLINHA + SAIR)
           ===================================================== */
        div[data-testid="stHorizontalBlock"]:has(.cv-top-bar-marker) {{
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: center !important;
            justify-content: space-between !important;
            gap: 8px !important;
            margin-bottom: 2px !important;
            padding-bottom: 6px !important;
            border-bottom: 1px solid var(--border) !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(.cv-top-bar-marker) > div[data-testid="stColumn"],
        div[data-testid="stHorizontalBlock"]:has(.cv-top-bar-marker) > div[data-testid="column"] {{
            min-width: 0 !important;
            width: auto !important;
            display: flex !important;
            align-items: center !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(.cv-top-bar-marker) > div[data-testid="stColumn"]:nth-child(1),
        div[data-testid="stHorizontalBlock"]:has(.cv-top-bar-marker) > div[data-testid="column"]:nth-child(1) {{
            flex: 1 1 auto !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(.cv-top-bar-marker) > div[data-testid="stColumn"]:nth-child(2),
        div[data-testid="stHorizontalBlock"]:has(.cv-top-bar-marker) > div[data-testid="column"]:nth-child(2) {{
            flex: 0 0 38px !important;
            justify-content: center !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(.cv-top-bar-marker) > div[data-testid="stColumn"]:nth-child(3),
        div[data-testid="stHorizontalBlock"]:has(.cv-top-bar-marker) > div[data-testid="column"]:nth-child(3) {{
            flex: 0 0 auto !important;
        }}

        div[data-testid="stHorizontalBlock"]:has(.cv-login-top-marker) {{
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: center !important;
            justify-content: flex-end !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(.cv-login-top-marker) > div[data-testid="stColumn"]:nth-child(1),
        div[data-testid="stHorizontalBlock"]:has(.cv-login-top-marker) > div[data-testid="column"]:nth-child(1) {{
            flex: 1 1 auto !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(.cv-login-top-marker) > div[data-testid="stColumn"]:nth-child(2),
        div[data-testid="stHorizontalBlock"]:has(.cv-login-top-marker) > div[data-testid="column"]:nth-child(2) {{
            flex: 0 0 38px !important;
        }}

        /* Botão BOLINHA Claro (vazia) / Escuro (preenchida) */
        div[data-testid="stElementContainer"]:has(.marker-theme-dot) + div[data-testid="stElementContainer"] button,
        div.element-container:has(.marker-theme-dot) + div.element-container button {{
            width: 28px !important;
            height: 28px !important;
            min-width: 28px !important;
            min-height: 28px !important;
            padding: 0 !important;
            margin: 0 auto !important;
            border-radius: 50% !important;
            background-color: var(--dot-bg) !important;
            border: 2.5px solid var(--dot-border) !important;
            box-shadow: var(--shadow) !important;
        }}
        div[data-testid="stElementContainer"]:has(.marker-theme-dot) + div[data-testid="stElementContainer"] button p,
        div.element-container:has(.marker-theme-dot) + div.element-container button p {{
            font-size: 1px !important;
            color: transparent !important;
            margin: 0 !important;
        }}

        /* =====================================================
           PÍLULAS DE FILTRO COMPACTAS EM 1 LINHA (MOBILE + PC)
           ===================================================== */
        div[data-testid="stHorizontalBlock"]:has(.cv-filter-row-marker) {{
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: center !important;
            gap: 6px !important;
            margin-bottom: 4px !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(.cv-filter-row-marker) > div[data-testid="stColumn"],
        div[data-testid="stHorizontalBlock"]:has(.cv-filter-row-marker) > div[data-testid="column"] {{
            flex: 1 1 0% !important;
            min-width: 0 !important;
            width: auto !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(.cv-filter-row-marker) button {{
            border-radius: 999px !important;
            padding: 4px 6px !important;
            min-height: 35px !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(.cv-filter-row-marker) button p {{
            font-size: 0.78rem !important;
        }}

        /* =====================================================
           LINHA COMPACTA: + NOVO AGENDAMENTO | CALENDÁRIO
           ===================================================== */
        div[data-testid="stHorizontalBlock"]:has(.cv-util-row-marker) {{
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: center !important;
            gap: 8px !important;
            margin-bottom: 4px !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(.cv-util-row-marker) > div[data-testid="stColumn"],
        div[data-testid="stHorizontalBlock"]:has(.cv-util-row-marker) > div[data-testid="column"] {{
            min-width: 0 !important;
            width: auto !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(.cv-util-row-marker) > div[data-testid="stColumn"]:nth-child(1),
        div[data-testid="stHorizontalBlock"]:has(.cv-util-row-marker) > div[data-testid="column"]:nth-child(1) {{
            flex: 1.2 1 0% !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(.cv-util-row-marker) > div[data-testid="stColumn"]:nth-child(2),
        div[data-testid="stHorizontalBlock"]:has(.cv-util-row-marker) > div[data-testid="column"]:nth-child(2) {{
            flex: 1 1 0% !important;
        }}

        /* Botão lilás suave (+ Novo Agendamento) */
        div[data-testid="stElementContainer"]:has(.marker-lavender) + div[data-testid="stElementContainer"] button,
        div.element-container:has(.marker-lavender) + div.element-container button {{
            background-color: var(--purple-soft-bg) !important;
            border: 1px solid var(--purple-soft-border) !important;
            color: var(--purple-soft-text) !important;
            border-radius: 11px !important;
            font-weight: 700 !important;
            min-height: 40px !important;
        }}
        div[data-testid="stElementContainer"]:has(.marker-lavender) + div[data-testid="stElementContainer"] button p,
        div.element-container:has(.marker-lavender) + div.element-container button p {{
            color: var(--purple-soft-text) !important;
        }}

        /* Faixa fina de resumo do dia (1 linha) */
        .cv-day-summary-slim {{
            background: var(--purple-soft-bg);
            border: 1px solid var(--purple-soft-border);
            border-radius: 12px;
            padding: 8px 14px;
            margin: 4px 0 8px 0;
            color: var(--purple-soft-text);
            font-size: 0.87rem;
            font-weight: 700;
        }}

        /* =====================================================
           BARRA DE NAVEGAÇÃO INFERIOR ESTILO APP (MOBILE + PC)
           ===================================================== */
        div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) {{
            position: fixed !important;
            bottom: 0 !important;
            left: 50% !important;
            transform: translateX(-50%) !important;
            width: 100% !important;
            max-width: 780px !important;
            z-index: 9999 !important;
            background-color: var(--surface) !important;
            border-top: 1px solid var(--border) !important;
            border-left: 1px solid var(--border) !important;
            border-right: 1px solid var(--border) !important;
            border-radius: 18px 18px 0 0 !important;
            box-shadow: var(--nav-shadow) !important;
            padding: 6px 6px calc(8px + env(safe-area-inset-bottom)) 6px !important;
            margin: 0 !important;
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            align-items: stretch !important;
            justify-content: space-between !important;
            gap: 2px !important;
        }}

        div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) > div[data-testid="stColumn"],
        div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) > div[data-testid="column"] {{
            flex: 1 1 0% !important;
            min-width: 0 !important;
            width: auto !important;
            padding: 0 !important;
        }}

        div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button {{
            border-radius: 12px !important;
            padding: 5px 2px !important;
            min-height: 52px !important;
            height: 100% !important;
            box-shadow: none !important;
        }}

        div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button[kind="secondary"],
        div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button[data-testid="stBaseButton-secondary"] {{
            background-color: transparent !important;
            border: none !important;
            border-bottom: 3px solid transparent !important;
            color: var(--muted) !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button[kind="secondary"] p,
        div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button[data-testid="stBaseButton-secondary"] p {{
            color: var(--muted) !important;
            font-size: 0.70rem !important;
            font-weight: 600 !important;
            line-height: 1.15 !important;
            white-space: normal !important;
            text-align: center !important;
            margin: 0 !important;
        }}

        div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button[kind="primary"],
        div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button[data-testid="stBaseButton-primary"] {{
            background-color: var(--purple-soft-bg) !important;
            border: none !important;
            border-bottom: 3px solid var(--nav-active-line) !important;
            color: var(--purple-soft-text) !important;
        }}
        div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button[kind="primary"] p,
        div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button[data-testid="stBaseButton-primary"] p {{
            color: var(--purple-soft-text) !important;
            font-size: 0.70rem !important;
            font-weight: 800 !important;
            line-height: 1.15 !important;
            white-space: normal !important;
            text-align: center !important;
            margin: 0 !important;
        }}

        div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button p::first-line {{
            font-size: 1.22rem !important;
            line-height: 1.32 !important;
        }}

        @media (max-width: 640px) {{
            .block-container {{
                padding-top: 2.9rem !important;
                padding-left: 0.75rem !important;
                padding-right: 0.75rem !important;
                padding-bottom: 6.5rem !important;
            }}
            .brand-bar {{
                font-size: 1.04rem !important;
            }}
            div[data-testid="stHorizontalBlock"]:has(.cv-filter-row-marker) {{
                gap: 4px !important;
            }}
            div[data-testid="stHorizontalBlock"]:has(.cv-filter-row-marker) button {{
                padding: 3px 3px !important;
                min-height: 33px !important;
            }}
            div[data-testid="stHorizontalBlock"]:has(.cv-filter-row-marker) button p {{
                font-size: 0.69rem !important;
            }}
            div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) {{
                max-width: 100% !important;
                border-left: none !important;
                border-right: none !important;
                border-radius: 16px 16px 0 0 !important;
                padding: 5px 3px calc(8px + env(safe-area-inset-bottom)) 3px !important;
            }}
            div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button {{
                min-height: 50px !important;
                padding: 4px 1px !important;
            }}
            div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button[kind="secondary"] p,
            div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button[data-testid="stBaseButton-secondary"] p,
            div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button[kind="primary"] p,
            div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button[data-testid="stBaseButton-primary"] p {{
                font-size: 0.58rem !important;
            }}
            div[data-testid="stHorizontalBlock"]:has(.cv-bottom-nav-marker) button p::first-line {{
                font-size: 1.12rem !important;
            }}
        }}

        /* =====================================================
           CARDS, BADGES E BOTÕES DO CONTEÚDO
           ===================================================== */
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
        .cv-card-late {{
            background: var(--late-card-bg);
            border: 2px solid var(--late-card-border);
            border-left: 6px solid var(--red);
            border-radius: 14px;
            padding: 14px 16px;
            margin-bottom: 8px;
            box-shadow: var(--shadow);
        }}
        .cv-card-late-title {{
            font-weight: 800;
            font-size: 1.02rem;
            color: var(--late-card-text);
        }}
        .cv-card-late-sub {{
            color: var(--late-card-sub);
            font-size: 0.86rem;
            margin-top: 3px;
            font-weight: 500;
        }}
        .cv-badge-danger {{
            background: var(--red);
            color: #FFFFFF;
            font-weight: 800;
            font-size: 0.77rem;
            padding: 3px 10px;
            border-radius: 999px;
            display: inline-block;
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
        .cv-slots-pills {{
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin-top: 6px;
        }}
        .cv-slot-pill-free {{
            background: var(--green-badge-bg);
            color: var(--green-badge-text);
            font-weight: 700;
            font-size: 0.76rem;
            padding: 2px 8px;
            border-radius: 8px;
            display: inline-block;
        }}
        .cv-route-item {{
            padding: 6px 0;
            border-bottom: 1px dashed var(--border);
            font-size: 0.86rem;
            color: var(--text);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 6px;
        }}
        .cv-route-item:last-child {{
            border-bottom: none;
            padding-bottom: 0;
        }}
        .cv-dist-pill {{
            background: var(--purple-soft-bg);
            color: var(--purple-soft-text);
            border: 1px solid var(--purple-soft-border);
            font-weight: 800;
            font-size: 0.8rem;
            padding: 4px 10px;
            border-radius: 10px;
            white-space: nowrap;
            display: inline-block;
        }}
        .cv-dist-pill-closest {{
            background: var(--green-badge-bg);
            color: var(--green-badge-text);
            border: 1px solid var(--green-card-border);
            font-weight: 800;
            font-size: 0.8rem;
            padding: 4px 10px;
            border-radius: 10px;
            white-space: nowrap;
            display: inline-block;
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
            padding: 9px 14px;
            font-weight: 700;
            font-size: 0.9rem;
            margin-bottom: 10px;
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

        /* Botão VERMELHO específico (Concluir OS / Marcar como Frustrada) */
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
            font-size: 0.78rem;
            padding: 5px 10px;
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
            font-size: 0.78rem;
            padding: 5px 10px;
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
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
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


@st.cache_resource
def get_geo_store() -> dict:
    """Cache compartilhado e thread-safe em memória do servidor para mapas e rotas."""
    return {"geo": {}, "rota": {}}


supabase = get_supabase()
GEO_STORE = get_geo_store()


def fmt_moeda(valor: float) -> str:
    try:
        v = float(valor or 0)
    except (TypeError, ValueError):
        v = 0.0
    texto = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def fmt_km(km: float) -> str:
    return f"{km:.1f}".replace(".", ",") + " km"


def fmt_tempo(minutos: int) -> str:
    m = max(1, int(minutos or 1))
    if m >= 60:
        h = m // 60
        r = m % 60
        return f"{h}h{r:02d}" if r else f"{h}h"
    return f"{m} min"


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


def normalizar_hora(hora_str: str) -> str:
    t = parse_hora(hora_str)
    return t.strftime("%H:%M")


def extrair_hora_int(hora_str: str) -> int:
    try:
        return int(str(hora_str or "08:00").split(":")[0])
    except (ValueError, IndexError, TypeError):
        return 8


def obter_horarios_status(todos_agendamentos: list, data_iso: str, ignorar_id=None):
    """Retorna (ocupados, disponiveis) para uma data específica, ignorando atendimentos Frustrados."""
    ocupados = sorted(
        {
            normalizar_hora(a.get("hora_agendamento"))
            for a in todos_agendamentos
            if str(a.get("data_agendamento", ""))[:10] == data_iso
            and a.get("status") != "Frustrada"
            and (ignorar_id is None or a.get("id") != ignorar_id)
        }
    )
    disponiveis = [h for h in HORARIOS_PADRAO if h not in ocupados]
    return ocupados, disponiveis


def agendamento_esta_atrasado(ag: dict) -> bool:
    if ag.get("status") != "Agendada":
        return False
    dt_d = parse_data(ag.get("data_agendamento"))
    dt_h = parse_hora(ag.get("hora_agendamento"))
    dt_agendada = datetime(dt_d.year, dt_d.month, dt_d.day, dt_h.hour, dt_h.minute, tzinfo=FUSO_BR)
    return agora_br() > dt_agendada


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
    """Abre a rota no Google Maps sempre saindo da localização atual (GPS) do celular."""
    dest = str(destino or "").strip()
    if not dest:
        return ""
    return f"https://www.google.com/maps/dir/?api=1&destination={quote(dest)}&travelmode=driving"


def comprimir_imagem_para_base64(arquivo_upload) -> str:
    img = Image.open(arquivo_upload)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.thumbnail((900, 900))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70, optimize=True)
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
# GEOLOCALIZAÇÃO RÁPIDA, PARALELA E COM CACHE PERSISTENTE
# =========================================================
def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _normalizar_endereco_br(texto: str) -> str:
    t = str(texto or "").strip()
    t = re.sub(r"\b[Rr]\.\s*", "Rua ", t)
    t = re.sub(r"\b[Aa][Vv]\.\s*", "Avenida ", t)
    t = re.sub(r"\b[Tt][Vv]\.\s*", "Travessa ", t)
    t = re.sub(r"\b[Pp][çc]\.\s*", "Praça ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _extrair_contexto_cidade(endereco_base: str) -> str:
    partes = [p.strip() for p in str(endereco_base or "").split(",") if p.strip()]
    if len(partes) >= 2:
        return ", ".join(partes[-2:])
    return ""


def _resolver_cep_viacep(texto: str) -> str:
    m = re.search(r"\b(\d{5})-?(\d{3})\b", str(texto or ""))
    if not m:
        return ""
    cep = m.group(1) + m.group(2)
    try:
        req = urllib.request.Request(
            f"https://viacep.com.br/ws/{cep}/json/",
            headers={"User-Agent": "ControleDeVistoriasAD/3.0"},
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            d = json.loads(resp.read().decode("utf-8"))
            if not d.get("erro"):
                partes = [d.get("logradouro"), d.get("bairro"), d.get("localidade"), d.get("uf")]
                return ", ".join(p for p in partes if p)
    except Exception:
        return ""
    return ""


def _buscar_photon(query: str, bias_coord=None):
    params = {"q": query, "limit": 1}
    if bias_coord:
        params["lat"] = f"{bias_coord[0]:.5f}"
        params["lon"] = f"{bias_coord[1]:.5f}"
    url = f"https://photon.komoot.io/api/?{urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "ControleDeVistoriasAD/3.0"})
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
            feats = dados.get("features") or []
            if feats:
                lon, lat = feats[0]["geometry"]["coordinates"]
                return float(lat), float(lon)
    except Exception:
        return None
    return None


def _buscar_nominatim(query: str):
    params = urlencode({"q": query, "format": "json", "limit": 1, "countrycodes": "br"})
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ControleDeVistoriasAD/3.0 (adrastreamentos@gmail.com)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
            if dados:
                return float(dados[0]["lat"]), float(dados[0]["lon"])
    except Exception:
        return None
    return None


def geocodificar_endereco(endereco: str, bias_coord=None, contexto_cidade: str = ""):
    texto = _normalizar_endereco_br(endereco)
    if len(texto) < 3:
        return None

    chave = f"{texto.lower()}|{contexto_cidade.lower()}"
    agora = time_mod.time()
    entrada = GEO_STORE["geo"].get(chave)
    if entrada is not None:
        valor, exp = entrada
        if agora < exp:
            return valor

    tentativas = []
    via_cep = _resolver_cep_viacep(texto)
    if via_cep:
        tentativas.append(via_cep)

    if contexto_cidade and contexto_cidade.lower() not in texto.lower():
        tentativas.append(f"{texto}, {contexto_cidade}")
    tentativas.append(texto)

    sem_num = re.sub(r"\b(?:n[º°]?\.?\s*)?\d+[A-Za-z]?\b", "", texto).strip(" ,-")
    if sem_num and sem_num != texto and len(sem_num) >= 4:
        if contexto_cidade and contexto_cidade.lower() not in sem_num.lower():
            tentativas.append(f"{sem_num}, {contexto_cidade}")
        else:
            tentativas.append(sem_num)

    for t in tentativas[:3]:
        coord = _buscar_photon(t, bias_coord=bias_coord)
        if coord:
            GEO_STORE["geo"][chave] = (coord, agora + 86400)
            return coord

    for t in tentativas[:2]:
        coord = _buscar_nominatim(t)
        if coord:
            GEO_STORE["geo"][chave] = (coord, agora + 86400)
            return coord

    GEO_STORE["geo"][chave] = (None, agora + 900)
    return None


def calcular_distancia_rota(origem_end: str, destino_end: str, c_orig_pre=None):
    orig = str(origem_end or "").strip()
    dest = str(destino_end or "").strip()
    if len(orig) < 3 or len(dest) < 3:
        return None

    chave_rota = f"{orig.lower()}=>{dest.lower()}"
    agora = time_mod.time()
    entrada = GEO_STORE["rota"].get(chave_rota)
    if entrada is not None:
        valor, exp = entrada
        if agora < exp:
            return valor

    c_orig = c_orig_pre if c_orig_pre else geocodificar_endereco(orig)
    if not c_orig:
        return None

    ctx_cidade = _extrair_contexto_cidade(orig)
    c_dest = geocodificar_endereco(dest, bias_coord=c_orig, contexto_cidade=ctx_cidade)
    if not c_dest:
        GEO_STORE["rota"][chave_rota] = (None, agora + 900)
        return None

    lat1, lon1 = c_orig
    lat2, lon2 = c_dest

    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{lon1},{lat1};{lon2},{lat2}?overview=false"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "ControleDeVistoriasAD/3.0"})
    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
            if dados.get("code") == "Ok" and dados.get("routes"):
                rota = dados["routes"][0]
                km = float(rota["distance"]) / 1000.0
                minutos = max(2, round(float(rota["duration"]) / 60.0))
                res = {"km": km, "minutos": minutos, "estimada": False}
                GEO_STORE["rota"][chave_rota] = (res, agora + 86400)
                return res
    except Exception:
        pass

    km_est = _haversine_km(lat1, lon1, lat2, lon2) * 1.25
    min_est = max(2, round((km_est / 30.0) * 60.0))
    res = {"km": km_est, "minutos": min_est, "estimada": True}
    GEO_STORE["rota"][chave_rota] = (res, agora + 86400)
    return res


def calcular_distancias_em_lote(ponto_base: str, lista_ags: list) -> dict:
    if not ponto_base or not lista_ags:
        return {}

    c_orig = geocodificar_endereco(ponto_base)
    if not c_orig:
        return {}

    enderecos_unicos = list(
        {(ag.get("endereco") or "").strip() for ag in lista_ags if (ag.get("endereco") or "").strip()}
    )
    if not enderecos_unicos:
        return {}

    por_endereco = {}
    if len(enderecos_unicos) == 1:
        end0 = enderecos_unicos[0]
        por_endereco[end0] = calcular_distancia_rota(ponto_base, end0, c_orig_pre=c_orig)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futuros = {
                ex.submit(calcular_distancia_rota, ponto_base, end, c_orig): end
                for end in enderecos_unicos
            }
            for fut in concurrent.futures.as_completed(futuros):
                end = futuros[fut]
                try:
                    por_endereco[end] = fut.result()
                except Exception:
                    por_endereco[end] = None

    resultado = {}
    for ag in lista_ags:
        end_ag = (ag.get("endereco") or "").strip()
        if end_ag and por_endereco.get(end_ag):
            resultado[ag["id"]] = por_endereco[end_ag]
    return resultado


# =========================================================
# CONSULTAS AO BANCO COM CACHE RÁPIDO (SEM FOTOS PESADAS)
# =========================================================
@st.cache_data(ttl=120, show_spinner=False)
def carregar_perfil():
    try:
        res = supabase.table("vistorias_perfil").select("*").order("id").limit(1).execute()
        if res.data:
            return res.data[0]
        return {"id": None, "nome": "", "telefone": "", "ponto_base": ""}
    except Exception:
        return {"id": None, "nome": "", "telefone": "", "ponto_base": "", "_erro_tabela": True}


@st.cache_data(ttl=120, show_spinner=False)
def carregar_empresas():
    try:
        res = supabase.table("vistorias_empresas").select("*").order("nome").execute()
        return res.data or []
    except Exception as e:
        st.error(f"Erro ao carregar empresas: {e}")
        return []


@st.cache_data(ttl=60, show_spinner=False)
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


@st.cache_data(ttl=60, show_spinner=False)
def carregar_vistorias(ano=None, mes=None):
    try:
        q = supabase.table("vistorias").select(COLUNAS_VISTORIA_LEVE)
        if ano and mes:
            inicio = date(ano, mes, 1)
            fim = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
            q = q.gte("data_vistoria", inicio.isoformat()).lt("data_vistoria", fim.isoformat())
        res = q.order("data_vistoria", desc=True).order("id", desc=True).execute()
        return res.data or []
    except Exception as e:
        st.error(f"Erro ao carregar vistorias: {e}")
        return []


@st.cache_data(ttl=600, show_spinner=False)
def carregar_foto_os(os_id: int):
    try:
        res = supabase.table("vistorias").select("foto_base64").eq("id", os_id).limit(1).execute()
        if res.data:
            return res.data[0].get("foto_base64")
    except Exception:
        return None
    return None


def limpar_cache_dados():
    carregar_perfil.clear()
    carregar_empresas.clear()
    carregar_agendamentos.clear()
    carregar_vistorias.clear()
    gerar_pdf_lote_cached.clear()


def verificar_conflito_horario(data_iso: str, hora_hhmm: str, ignorar_id=None):
    alvo = normalizar_hora(hora_hhmm)
    try:
        res = (
            supabase.table("agendamentos")
            .select("id, empresa_nome, cliente_nome, veiculo, placa, hora_agendamento, tipo_servico, status")
            .eq("data_agendamento", data_iso)
            .execute()
        )
        for item in res.data or []:
            if ignorar_id is not None and item.get("id") == ignorar_id:
                continue
            if item.get("status") == "Frustrada":
                continue
            if normalizar_hora(item.get("hora_agendamento")) == alvo:
                return item
    except Exception:
        return None
    return None


# =========================================================
# FORMULÁRIO DE ORDEM DE SERVIÇO (ABRE EMBAIXO DO CARD OU AVULSA)
# =========================================================
def render_formulario_os(
    mapa_empresas: dict,
    nomes_empresas: list,
    chave_prefixo: str,
    ag: dict = None,
):
    hoje = hoje_br()
    ver = st.session_state.form_os_ver
    mod_key = f"{chave_prefixo}_{ver}"
    if mod_key not in st.session_state.modalidade_os_map:
        st.session_state.modalidade_os_map[mod_key] = "Nova"

    imp = None
    if ag is not None:
        emp_nome_ag = ag.get("empresa_nome", "")
        emp_info_ag = mapa_empresas.get(emp_nome_ag, {})
        cat_ag = emp_info_ag.get("categoria_servico") or "Vistoria"
        tipos_ag = parse_tipos_empresa(emp_info_ag.get("tipo_vistoria"), cat_ag)
        imp = {
            "agendamento_id": ag["id"],
            "empresa_nome": emp_nome_ag,
            "cliente_nome": ag.get("cliente_nome", ""),
            "endereco": ag.get("endereco", ""),
            "veiculo": ag.get("veiculo", ""),
            "placa": ag.get("placa", ""),
            "data_vistoria": ag.get("data_agendamento", hoje.isoformat()),
            "valor_padrao": float(emp_info_ag.get("valor_padrao") or 0.0),
            "tipo_padrao": ag.get("tipo_servico") or tipos_ag[0],
        }

    with st.container(border=True):
        if imp:
            hc1, hc2 = st.columns([3.5, 1.0])
            with hc1:
                render_html('<div class="cv-banner-import">📋 Ordem de Serviço — Dados do Atendimento</div>')
            with hc2:
                if st.button("✖ Fechar", key=f"fechar_os_{chave_prefixo}_{ver}", use_container_width=True):
                    st.session_state.os_card_aberto_id = None
                    st.rerun()

        emp_padrao = imp["empresa_nome"] if imp else (nomes_empresas[0] if nomes_empresas else "")
        if nomes_empresas:
            idx_emp = nomes_empresas.index(emp_padrao) if emp_padrao in nomes_empresas else 0
            empresa_sel = st.selectbox("Empresa", nomes_empresas, index=idx_emp, key=f"os_emp_{chave_prefixo}_{ver}")
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
            empresa_sel = st.text_input("Empresa", value=emp_padrao, key=f"os_emp_txt_{chave_prefixo}_{ver}")
            categoria_emp = "Vistoria"
            sem_financeiro = False
            valor_sugerido = float(imp["valor_padrao"]) if imp else 0.0
            opcoes_serv = TIPOS_VISTORIA_OPCOES
            tipo_sugerido = imp.get("tipo_padrao", "Cautelar") if imp else "Cautelar"

        if sem_financeiro:
            st.info("📡 Empresa sem controle financeiro: esta OS será salva apenas no Histórico/PDF (sem cobrança).")

        rotulo_serv = "Tipo de Serviço (Rastreamento)" if categoria_emp == "Rastreamento" else "Tipo de Vistoria"
        idx_tipo = opcoes_serv.index(tipo_sugerido) if tipo_sugerido in opcoes_serv else 0
        servico_escolhido = st.selectbox(
            rotulo_serv,
            opcoes_serv,
            index=idx_tipo,
            key=f"os_cat_{chave_prefixo}_{ver}_{empresa_sel}_{categoria_emp}",
        )

        cliente_val = st.text_input(
            "Cliente / Segurado (opcional)",
            value=imp.get("cliente_nome", "") if imp else "",
            key=f"os_cli_{chave_prefixo}_{ver}",
        )
        endereco_val = st.text_input(
            "Endereço do Cliente",
            value=imp.get("endereco", "") if imp else "",
            key=f"os_end_{chave_prefixo}_{ver}",
        )

        v1, v2 = st.columns([2, 1])
        with v1:
            veiculo_val = st.text_input(
                "Veículo",
                value=imp.get("veiculo", "") if imp else "",
                key=f"os_veic_{chave_prefixo}_{ver}",
            )
        with v2:
            placa_val = st.text_input(
                "Placa",
                value=imp.get("placa", "") if imp else "",
                key=f"os_placa_{chave_prefixo}_{ver}",
            )

        data_ini = parse_data(imp["data_vistoria"]) if (imp and imp.get("data_vistoria")) else hoje

        if sem_financeiro:
            data_val = st.date_input("Data", value=data_ini, format="DD/MM/YYYY", key=f"os_data_{chave_prefixo}_{ver}")
            valor_val = 0.0
        else:
            c1, c2 = st.columns(2)
            with c1:
                data_val = st.date_input("Data", value=data_ini, format="DD/MM/YYYY", key=f"os_data_{chave_prefixo}_{ver}")
            with c2:
                valor_val = st.number_input(
                    "Valor do Serviço (R$)",
                    min_value=0.0,
                    value=valor_sugerido,
                    step=1.0,
                    format="%.2f",
                    key=f"os_valor_{chave_prefixo}_{ver}_{empresa_sel}",
                )

        if categoria_emp == "Vistoria":
            st.markdown("**Modalidade**")
            mod_atual = st.session_state.modalidade_os_map[mod_key]
            tv1, tv2 = st.columns(2)
            with tv1:
                if st.button(
                    "Nova",
                    key=f"btn_mod_nova_{chave_prefixo}_{ver}",
                    type="primary" if mod_atual == "Nova" else "secondary",
                    use_container_width=True,
                ):
                    st.session_state.modalidade_os_map[mod_key] = "Nova"
                    st.rerun()
            with tv2:
                if st.button(
                    "Renovação",
                    key=f"btn_mod_renov_{chave_prefixo}_{ver}",
                    type="primary" if mod_atual == "Renovação" else "secondary",
                    use_container_width=True,
                ):
                    st.session_state.modalidade_os_map[mod_key] = "Renovação"
                    st.rerun()

        st.markdown("**Foto do Veículo**")
        modo_foto = st.radio(
            "Origem da foto",
            ["Galeria / Arquivo", "Câmera"],
            horizontal=True,
            label_visibility="collapsed",
            key=f"os_modo_foto_{chave_prefixo}_{ver}",
        )
        foto_arquivo = None
        if modo_foto == "Galeria / Arquivo":
            foto_arquivo = st.file_uploader(
                "Anexar foto do veículo",
                type=["jpg", "jpeg", "png", "webp"],
                label_visibility="collapsed",
                key=f"os_upload_{chave_prefixo}_{ver}",
            )
        else:
            foto_arquivo = st.camera_input("Capturar foto do veículo", key=f"os_cam_{chave_prefixo}_{ver}")

        if foto_arquivo is not None:
            p1, p2 = st.columns([1, 2])
            with p1:
                st.image(foto_arquivo, width=150)
            with p2:
                render_html('<span class="cv-badge-purple">✔ 1 foto anexada</span>')

        render_html('<span class="marker-red marker-hidden"></span>')
        concluir = st.button(
            "✔ Concluir Ordem de Serviço",
            key=f"btn_concluir_os_{chave_prefixo}_{ver}",
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

                mod_escolhida = st.session_state.modalidade_os_map.get(mod_key, "Nova")
                tipo_final = (
                    f"{servico_escolhido} ({mod_escolhida})"
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
                    limpar_cache_dados()
                    st.session_state.os_card_aberto_id = None
                    st.session_state.form_os_ver += 1
                    st.session_state.aviso_sucesso = (
                        "Serviço concluído e salvo no Histórico (sem cobrança no Financeiro)!"
                        if sem_financeiro
                        else "Ordem de Serviço concluída e enviada para o Financeiro!"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao concluir Ordem de Serviço: {e}")


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

    status_ag = ag.get("status") or "Agendada"
    concluida = status_ag == "Concluida"
    frustrada = status_ag == "Frustrada"
    atrasada = agendamento_esta_atrasado(ag)
    alerta_vermelho = frustrada or atrasada
    ver = st.session_state.form_ag_ver

    endereco_cli = (ag.get("endereco") or "").strip()
    tipo_serv_ag = (ag.get("tipo_servico") or "").strip()
    obs_txt = (ag.get("observacao") or "").strip()
    card_uid = f"{prefixo}_{ag['id']}"
    os_aberta_neste_card = st.session_state.os_card_aberto_id == card_uid

    if alerta_vermelho:
        msg_wa = (
            f"Olá {ag.get('cliente_nome', '')}, tudo bem? "
            f"Sobre seu atendimento ({tipo_serv_ag or categoria_emp}) do veículo {ag.get('veiculo', '')} "
            f"(Placa {ag.get('placa', '')}), gostaria de combinar um novo horário/data com você."
        )
    else:
        msg_wa = (
            f"Olá {ag.get('cliente_nome', '')}, tudo bem? "
            f"Confirmando seu atendimento ({tipo_serv_ag or categoria_emp}) do veículo {ag.get('veiculo', '')} "
            f"(Placa {ag.get('placa', '')}) em {fmt_data_br(ag.get('data_agendamento'))} às {ag.get('hora_agendamento', '')}."
        )
    wa_url = link_whatsapp(ag.get("cliente_whatsapp", ""), msg_wa)
    wa_html = f'<a class="wa-btn" href="{wa_url}" target="_blank">💬 WhatsApp</a>' if wa_url else ""

    maps_url = link_rota_maps(ponto_base, endereco_cli)
    maps_html = f'<a class="maps-btn" href="{maps_url}" target="_blank">🗺️ Rota</a>' if maps_url else ""

    if concluida:
        status_badge = '<span class="cv-badge-green">✅ Concluída</span>'
    elif frustrada:
        status_badge = '<span class="cv-badge-danger">❌ Frustrada</span>'
    elif atrasada:
        status_badge = '<span class="cv-badge-danger">⚠️ Atrasada</span>'
    else:
        status_badge = '<span class="cv-badge-purple">✔ Preenchido</span>'

    serv_badge = f'&nbsp;<span class="cv-badge-amber">🔧 {esc(tipo_serv_ag)}</span>' if tipo_serv_ag else ""

    dist_lateral_html = ""
    if dist_info:
        aprox = "~" if dist_info.get("estimada") else ""
        pill_cls = "cv-dist-pill-closest" if eh_mais_proximo else "cv-dist-pill"
        star_txt = "⭐ Mais próximo • " if eh_mais_proximo else ""
        dist_lateral_html = (
            f'<span class="{pill_cls}">'
            f'{star_txt}📍 {aprox}{fmt_km(dist_info["km"])} • ⏱️ ~{fmt_tempo(dist_info["minutos"])}'
            f'</span>'
        )
    elif ponto_base and endereco_cli:
        dist_lateral_html = '<span class="cv-badge-amber">⚠️ Endereço não localizado no mapa</span>'

    topo_tempo = (
        f"📅 {fmt_data_br(ag.get('data_agendamento'))} • ⏰ {esc(ag.get('hora_agendamento', ''))}"
        if mostrar_data
        else f"⏰ {esc(ag.get('hora_agendamento', ''))}"
    )

    if concluida:
        card_cls = "cv-card-green"
        title_cls = "cv-card-green-title"
        sub_cls = "cv-card-green-sub"
    elif alerta_vermelho:
        card_cls = "cv-card-late"
        title_cls = "cv-card-late-title"
        sub_cls = "cv-card-late-sub"
    elif eh_mais_proximo:
        card_cls = "cv-card-closest"
        title_cls = "cv-card-title"
        sub_cls = "cv-card-sub"
    else:
        card_cls = "cv-card-booked"
        title_cls = "cv-card-title"
        sub_cls = "cv-card-sub"

    end_html = f'<div class="{sub_cls}">📍 {esc(endereco_cli)}</div>' if endereco_cli else ""
    obs_html = f'<div class="{sub_cls}">📝 <strong>Obs. / Motivo:</strong> {esc(obs_txt)}</div>' if obs_txt else ""

    acoes_links = ""
    if wa_html or maps_html:
        acoes_links = f'<div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;">{wa_html}{maps_html}</div>'

    coluna_direita = ""
    if dist_lateral_html or acoes_links:
        coluna_direita = (
            '<div style="display:flex;flex-direction:column;gap:6px;align-items:flex-end;">'
            f'{dist_lateral_html}{acoes_links}'
            '</div>'
        )

    render_html(
        f"""
        <div class="{card_cls}">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:6px;">
                <span style="font-size:0.88rem;font-weight:700;">{topo_tempo} &nbsp;{status_badge}{serv_badge}</span>
                <span class="{badge_cls}">{esc(emp_nome)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;">
                <div style="flex:1;min-width:210px;">
                    <div class="{title_cls}">{esc(ag.get('veiculo', ''))} • Placa: {esc(ag.get('placa', ''))}</div>
                    <div class="{sub_cls}">👤 {esc(ag.get('cliente_nome', ''))} • 📞 {esc(ag.get('cliente_whatsapp') or 'Não informado')}</div>
                    {end_html}
                    {obs_html}
                </div>
                {coluna_direita}
            </div>
        </div>
        """
    )

    if not concluida:
        if sem_fin:
            bc1, bc2, bc3 = st.columns([2.2, 2.2, 0.8])
            with bc1:
                render_html('<span class="marker-green marker-hidden"></span>')
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
                        limpar_cache_dados()
                        st.session_state.os_card_aberto_id = None
                        st.session_state.aviso_sucesso = (
                            f"Atendimento de {emp_nome} ({tipo_serv_ag or 'Rastreamento'}) concluído!"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao concluir: {e}")
            with bc2:
                lbl_os_btn = "▲ Fechar OS" if os_aberta_neste_card else "📋 Abrir OS (com foto)"
                if st.button(
                    lbl_os_btn,
                    key=f"{prefixo}_iniciar_{ag['id']}",
                    type="secondary" if os_aberta_neste_card else "primary",
                    use_container_width=True,
                ):
                    st.session_state.os_card_aberto_id = None if os_aberta_neste_card else card_uid
                    st.rerun()
            with bc3:
                if st.button("🗑️", key=f"{prefixo}_del_{ag['id']}", help="Remover", use_container_width=True):
                    supabase.table("agendamentos").delete().eq("id", ag["id"]).execute()
                    limpar_cache_dados()
                    if os_aberta_neste_card:
                        st.session_state.os_card_aberto_id = None
                    st.session_state.aviso_sucesso = "Agendamento removido."
                    st.rerun()
        else:
            bc1, bc2 = st.columns([4, 1])
            with bc1:
                lbl_os_btn = "▲ Fechar Ordem de Serviço" if os_aberta_neste_card else "📋 Abrir Ordem de Serviço"
                if st.button(
                    lbl_os_btn,
                    key=f"{prefixo}_iniciar_{ag['id']}",
                    type="secondary" if os_aberta_neste_card else "primary",
                    use_container_width=True,
                ):
                    st.session_state.os_card_aberto_id = None if os_aberta_neste_card else card_uid
                    st.rerun()
            with bc2:
                if st.button("🗑️", key=f"{prefixo}_del_{ag['id']}", help="Remover", use_container_width=True):
                    supabase.table("agendamentos").delete().eq("id", ag["id"]).execute()
                    limpar_cache_dados()
                    if os_aberta_neste_card:
                        st.session_state.os_card_aberto_id = None
                    st.session_state.aviso_sucesso = "Agendamento removido."
                    st.rerun()

        # Abre a Ordem de Serviço diretamente na PARTE DE BAIXO deste card
        if os_aberta_neste_card:
            render_formulario_os(mapa_empresas, nomes_empresas, chave_prefixo=f"inline_{card_uid}", ag=ag)

        rotulo_exp_ag = (
            f"🔄 Reagendar / Corrigir / Frustrada — {ag.get('hora_agendamento', '')} • {ag.get('veiculo', '')}"
            if alerta_vermelho
            else f"✏️ Corrigir / Reagendar / Frustrada — {ag.get('hora_agendamento', '')} • {ag.get('veiculo', '')}"
        )

        with st.expander(rotulo_exp_ag):
            tab_cor, tab_reag, tab_frust = st.tabs(["✏️ Corrigir", "🔄 Reagendar", "❌ Frustrada"])
            todos_ags_cache = carregar_agendamentos(apenas_agendadas=False)

            with tab_cor:
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
                    ea_cli = st.text_input(
                        "Cliente", value=ag.get("cliente_nome") or "", key=f"{prefixo}_ea_cli_{ag['id']}_{ver}"
                    )
                with ac2:
                    ea_wa = st.text_input(
                        "WhatsApp do Cliente",
                        value=ag.get("cliente_whatsapp") or "",
                        key=f"{prefixo}_ea_wa_{ag['id']}_{ver}",
                    )

                ea_end = st.text_input(
                    "Endereço do Cliente", value=endereco_cli, key=f"{prefixo}_ea_end_{ag['id']}_{ver}"
                )

                av1, av2 = st.columns([2, 1])
                with av1:
                    ea_veic = st.text_input(
                        "Veículo", value=ag.get("veiculo") or "", key=f"{prefixo}_ea_veic_{ag['id']}_{ver}"
                    )
                with av2:
                    ea_placa = st.text_input(
                        "Placa", value=ag.get("placa") or "", key=f"{prefixo}_ea_placa_{ag['id']}_{ver}"
                    )

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

                ea_obs = st.text_input(
                    "Observação / Motivo", value=obs_txt, key=f"{prefixo}_ea_obs_{ag['id']}_{ver}"
                )

                if st.button(
                    "💾 Salvar Alterações",
                    key=f"{prefixo}_ea_save_{ag['id']}_{ver}",
                    type="primary",
                    use_container_width=True,
                ):
                    hora_fmt = ea_hora.strftime("%H:%M")
                    conflito = verificar_conflito_horario(ea_data.isoformat(), hora_fmt, ignorar_id=ag["id"])
                    if conflito:
                        st.error(
                            f"⛔ Horário indisponível! Já existe um agendamento em {ea_data.strftime('%d/%m/%Y')} "
                            f"às {hora_fmt} ({conflito.get('empresa_nome', '')} — {conflito.get('veiculo', '')}). "
                            "Escolha outro horário."
                        )
                    else:
                        try:
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
                                    "hora_agendamento": hora_fmt,
                                    "observacao": ea_obs.strip(),
                                }
                            ).eq("id", ag["id"]).execute()
                            limpar_cache_dados()
                            st.session_state.form_ag_ver += 1
                            st.session_state.aviso_sucesso = "Agendamento atualizado!"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar alterações: {e}")

            with tab_reag:
                st.caption(
                    f"Agendamento atual: **{fmt_data_br(ag.get('data_agendamento'))} às {ag.get('hora_agendamento', '')}**"
                )
                data_padrao_reag = (
                    hoje_br() + timedelta(days=1)
                    if parse_data(ag.get("data_agendamento")) <= hoje_br()
                    else parse_data(ag.get("data_agendamento"))
                )
                rc1, rc2 = st.columns(2)
                with rc1:
                    nova_data_r = st.date_input(
                        "Nova Data",
                        value=data_padrao_reag,
                        format="DD/MM/YYYY",
                        key=f"{prefixo}_reag_data_{ag['id']}_{ver}",
                    )
                _, disp_reag = obter_horarios_status(
                    todos_ags_cache, nova_data_r.isoformat(), ignorar_id=ag["id"]
                )
                opcoes_hora_r = disp_reag + ["Outro horário..."]
                with rc2:
                    hora_r_sel = st.selectbox(
                        "Novo Horário Disponível",
                        opcoes_hora_r,
                        key=f"{prefixo}_reag_hsel_{ag['id']}_{ver}_{nova_data_r.isoformat()}",
                    )

                if hora_r_sel == "Outro horário...":
                    nova_hora_custom = st.time_input(
                        "Informe o novo horário",
                        value=parse_hora(ag.get("hora_agendamento")),
                        key=f"{prefixo}_reag_hcustom_{ag['id']}_{ver}_{nova_data_r.isoformat()}",
                    )
                    nova_hora_fmt = nova_hora_custom.strftime("%H:%M")
                else:
                    nova_hora_fmt = hora_r_sel

                motivo_reag = st.text_area(
                    "Motivo do Reagendamento (Observação)",
                    value="",
                    placeholder="Ex: Não deu tempo de chegar / Cliente pediu para remarcar / Imprevisto na rota",
                    height=80,
                    key=f"{prefixo}_reag_obs_{ag['id']}_{ver}",
                )

                if st.button(
                    "🔄 Confirmar Reagendamento",
                    key=f"{prefixo}_reag_btn_{ag['id']}_{ver}",
                    type="primary",
                    use_container_width=True,
                ):
                    conflito_r = verificar_conflito_horario(
                        nova_data_r.isoformat(), nova_hora_fmt, ignorar_id=ag["id"]
                    )
                    if conflito_r:
                        st.error(
                            f"⛔ Horário indisponível! Já existe um agendamento em {nova_data_r.strftime('%d/%m/%Y')} "
                            f"às {nova_hora_fmt} ({conflito_r.get('empresa_nome', '')} — {conflito_r.get('veiculo', '')}). "
                            "Escolha outro horário."
                        )
                    else:
                        data_ant = fmt_data_br(ag.get("data_agendamento"))
                        hora_ant = ag.get("hora_agendamento", "")
                        if motivo_reag.strip():
                            obs_final = f"Reagendado de {data_ant} {hora_ant}: {motivo_reag.strip()}"
                        else:
                            obs_final = f"Reagendado de {data_ant} {hora_ant}"
                        try:
                            supabase.table("agendamentos").update(
                                {
                                    "data_agendamento": nova_data_r.isoformat(),
                                    "hora_agendamento": nova_hora_fmt,
                                    "status": "Agendada",
                                    "observacao": obs_final,
                                }
                            ).eq("id", ag["id"]).execute()
                            limpar_cache_dados()
                            st.session_state.form_ag_ver += 1
                            st.session_state.aviso_sucesso = (
                                f"Atendimento reagendado para {nova_data_r.strftime('%d/%m/%Y')} às {nova_hora_fmt}!"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao reagendar: {e}")

            with tab_frust:
                st.caption(
                    "Use esta opção quando não foi possível realizar o serviço. "
                    "O atendimento fica marcado em vermelho com o motivo e o horário antigo é liberado."
                )
                motivo_frust = st.text_area(
                    "Motivo / Observação",
                    value=obs_txt,
                    placeholder="Ex: Não deu tempo de atender hoje / Cliente não estava no local / Aguardando reagendamento",
                    height=80,
                    key=f"{prefixo}_frust_obs_{ag['id']}_{ver}",
                )
                render_html('<span class="marker-red marker-hidden"></span>')
                if st.button(
                    "❌ Marcar como Frustrada",
                    key=f"{prefixo}_frust_btn_{ag['id']}_{ver}",
                    use_container_width=True,
                ):
                    obs_f = motivo_frust.strip() or "Atendimento frustrado — aguardando reagendamento"
                    try:
                        supabase.table("agendamentos").update(
                            {
                                "status": "Frustrada",
                                "observacao": obs_f,
                            }
                        ).eq("id", ag["id"]).execute()
                        limpar_cache_dados()
                        st.session_state.form_ag_ver += 1
                        st.session_state.aviso_sucesso = (
                            "Atendimento marcado como Frustrada. Você pode reagendá-lo quando combinar com o cliente."
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao marcar como frustrada: {e}")


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
                    limpar_cache_dados()
                    st.session_state.pdfs_prontos.pop(vistoria["id"], None)
                    st.session_state.fin_edit_ver += 1
                    st.session_state.aviso_sucesso = f"OS #{vistoria['id']} atualizada com sucesso!"
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao atualizar OS: {e}")

        if excluir_os:
            try:
                supabase.table("vistorias").delete().eq("id", vistoria["id"]).execute()
                limpar_cache_dados()
                st.session_state.pdfs_prontos.pop(vistoria["id"], None)
                st.session_state.fin_edit_ver += 1
                st.session_state.aviso_sucesso = f"OS #{vistoria['id']} excluída com sucesso!"
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao excluir OS: {e}")


# =========================================================
# GERADORES DE PDF (SOB DEMANDA E COM CACHE)
# =========================================================
def gerar_pdf_individual(vistoria: dict, foto_base64: str = None) -> bytes:
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

    if foto_base64:
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, limpar_latin1("Registro Fotográfico do Veículo"), ln=True)
        tmp_path = None
        try:
            img_bytes = base64_para_bytes(foto_base64)
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


@st.cache_data(ttl=300, show_spinner=False)
def gerar_pdf_lote_cached(vistorias_json: str, titulo_periodo: str, empresa_filtro: str = "Todas") -> bytes:
    vistorias = json.loads(vistorias_json)
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


def gerar_pdf_lote(vistorias: list, titulo_periodo: str, empresa_filtro: str = "Todas") -> bytes:
    payload = json.dumps(vistorias, sort_keys=True, default=str)
    return gerar_pdf_lote_cached(payload, titulo_periodo, empresa_filtro)


# =========================================================
# BOTÃO BOLINHA CLARO (VAZIA) / ESCURO (PREENCHIDA)
# =========================================================
def botao_alternar_tema(key_suffix: str = "topo"):
    eh_escuro = st.session_state.tema == "escuro"
    dica = (
        "Modo Escuro (toque para mudar para Claro)"
        if eh_escuro
        else "Modo Claro (toque para mudar para Escuro)"
    )
    render_html('<span class="marker-theme-dot marker-hidden"></span>')
    if st.button("\u00A0", key=f"toggle_tema_{key_suffix}", help=dica):
        st.session_state.tema = "claro" if eh_escuro else "escuro"
        st.rerun()


# =========================================================
# TELA 1: ACESSO / LOGIN
# =========================================================
def tela_login():
    t1, t2 = st.columns([5, 0.7])
    with t1:
        render_html('<span class="cv-login-top-marker marker-hidden"></span>')
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

    col_esq, col_centro, col_dir = st.columns([0.08, 0.84, 0.08])
    with col_centro:
        if st.session_state.get("aviso_expirado"):
            st.info("⏱️ Sua sessão expirou após 1 hora de inatividade. Entre novamente.")
            st.session_state.aviso_expirado = False

        with st.form("form_login"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            lembrar = st.checkbox("Manter conectado (1 hora de inatividade)", value=True)
            entrar = st.form_submit_button("Entrar →", type="primary", use_container_width=True)

            if entrar:
                if (
                    usuario.strip().lower() == LOGIN_USUARIO.lower()
                    and senha.strip() == LOGIN_SENHA
                ):
                    st.session_state.autenticado = True
                    st.session_state.manter_conectado = lembrar
                    st.session_state.ultimo_acesso = int(time_mod.time())
                    st.session_state.pagina = "Agenda"
                    if lembrar:
                        _definir_token_url(_criar_token_sessao())
                    else:
                        _limpar_token_url()
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
        st.warning("Tabela `vistorias_perfil` ainda não encontrada no Supabase.")
        return

    with st.form("form_perfil_usuario"):
        st.markdown("**Dados do Vistoriador / Ponto de Partida**")
        p_nome = st.text_input("Seu Nome", value=perfil.get("nome") or "")
        p_tel = st.text_input("Seu Telefone / WhatsApp", value=perfil.get("telefone") or "")
        p_base = st.text_input(
            "Ponto Base (Rua, Bairro, Cidade - UF ou CEP)",
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
                GEO_STORE["geo"].clear()
                GEO_STORE["rota"].clear()
                limpar_cache_dados()
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
                        As distâncias (km e tempo) na tela usam este endereço como referência. Ao clicar em <strong>🗺️ Rota</strong>, o Google Maps parte automaticamente de onde o seu celular estiver.
                    </div>
                </div>
                """
            )
        else:
            st.warning(
                "Não consegui localizar esse endereço exato no mapa. "
                "Tente colocar Rua, Bairro, Cidade - RN (ou o CEP)."
            )
    else:
        st.info("Cadastre seu Ponto Base acima para ver a distância em km e minutos de cada atendimento.")


# =========================================================
# TELA 2: AGENDA DE VISTORIAS (TOPO LIMPO E COMPACTO)
# =========================================================
def _ao_mudar_calendario_agenda():
    st.session_state.agenda_filtro = "Data"
    st.session_state.agenda_data_busca = st.session_state.cal_pesquisa_agenda


def tela_agenda():
    mostrar_aviso_pendente()

    hoje = hoje_br()
    amanha = hoje + timedelta(days=1)

    if st.session_state.get("pending_cal_data") is not None:
        st.session_state.cal_pesquisa_agenda = st.session_state.pending_cal_data
        st.session_state.pending_cal_data = None
    if "cal_pesquisa_agenda" not in st.session_state:
        st.session_state.cal_pesquisa_agenda = st.session_state.agenda_data_busca or hoje

    perfil = carregar_perfil()
    ponto_base = (perfil.get("ponto_base") or "").strip()

    empresas = carregar_empresas()
    nomes_empresas = [e["nome"] for e in empresas]
    mapa_empresas = {e["nome"]: e for e in empresas}
    todos_agendamentos = carregar_agendamentos(apenas_agendadas=False)

    atrasadas_ou_frustradas = [
        ag
        for ag in todos_agendamentos
        if ag.get("status") == "Frustrada" or agendamento_esta_atrasado(ag)
    ]

    inicio_semana = hoje - timedelta(days=hoje.weekday())
    fim_semana = inicio_semana + timedelta(days=6)
    ver = st.session_state.form_ag_ver

    # 1. Faixa compacta de filtros em 1 linha (Hoje | Amanhã | Semana | Atrasadas)
    qtd_alerta = len(atrasadas_ou_frustradas)
    rotulo_alerta = f"Atrasadas ({qtd_alerta})" if qtd_alerta else "Atrasadas"

    fc1, fc2, fc3, fc4 = st.columns(4)
    for idx, (col, chave_f, label_f) in enumerate(
        [
            (fc1, "Hoje", "Hoje"),
            (fc2, "Amanhã", "Amanhã"),
            (fc3, "Esta Semana", "Semana"),
            (fc4, "Atrasadas", rotulo_alerta),
        ]
    ):
        with col:
            if idx == 0:
                render_html('<span class="cv-filter-row-marker marker-hidden"></span>')
            ativo = st.session_state.agenda_filtro == chave_f
            if st.button(
                label_f,
                key=f"flt_{chave_f}",
                type="primary" if ativo else "secondary",
                use_container_width=True,
            ):
                st.session_state.agenda_filtro = chave_f
                st.session_state.agenda_data_busca = None
                if chave_f == "Hoje":
                    st.session_state.pending_cal_data = hoje
                elif chave_f == "Amanhã":
                    st.session_state.pending_cal_data = amanha
                st.rerun()

    # 2. Linha compacta: + Novo Agendamento | Calendário automático
    u1, u2 = st.columns([1.2, 1.0])
    with u1:
        render_html('<span class="cv-util-row-marker marker-hidden"></span>')
        if not st.session_state.mostrar_novo_ag:
            render_html('<span class="marker-lavender marker-hidden"></span>')
        rotulo_novo = "▲ Fechar Novo Agendamento" if st.session_state.mostrar_novo_ag else "+ Novo Agendamento"
        if st.button(
            rotulo_novo,
            key="btn_toggle_novo_ag",
            type="primary" if st.session_state.mostrar_novo_ag else "secondary",
            use_container_width=True,
        ):
            st.session_state.mostrar_novo_ag = not st.session_state.mostrar_novo_ag
            st.rerun()
    with u2:
        st.date_input(
            "Pesquisar data",
            format="DD/MM/YYYY",
            key="cal_pesquisa_agenda",
            on_change=_ao_mudar_calendario_agenda,
            label_visibility="collapsed",
        )

    # Formulário de Novo Agendamento (abre somente quando tocado)
    if st.session_state.mostrar_novo_ag:
        with st.container(border=True):
            st.markdown("**📅 Novo Agendamento**")
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
                "Endereço do Cliente (rua, bairro e cidade ou CEP para cálculo de km)",
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

            ocupados_data, disponiveis_data = obter_horarios_status(todos_agendamentos, data_ag.isoformat())
            opcoes_hora_ag = disponiveis_data + ["Outro horário..."]

            with d2:
                hora_sel_op = st.selectbox(
                    "Horário Disponível",
                    opcoes_hora_ag,
                    key=f"ag_hora_sel_{ver}_{data_ag.isoformat()}",
                )

            if hora_sel_op == "Outro horário...":
                hora_custom = st.time_input(
                    "Informe o horário",
                    value=time(8, 30),
                    key=f"ag_hora_custom_{ver}_{data_ag.isoformat()}",
                )
                hora_escolhida_fmt = hora_custom.strftime("%H:%M")
            else:
                hora_escolhida_fmt = hora_sel_op

            if disponiveis_data:
                st.caption(
                    f"🟢 {len(disponiveis_data)} horário(s) livre(s) em {data_ag.strftime('%d/%m/%Y')}: "
                    f"{', '.join(disponiveis_data)}"
                )
            else:
                st.warning(
                    f"Todos os horários padrão (07:00 às 19:00) estão preenchidos em {data_ag.strftime('%d/%m/%Y')}."
                )

            if hora_escolhida_fmt in ocupados_data:
                st.error(
                    f"⛔ O horário **{hora_escolhida_fmt}** em **{data_ag.strftime('%d/%m/%Y')}** já está preenchido!"
                )

            if st.button("📅 Salvar na Agenda", key=f"btn_salvar_ag_{ver}", type="primary", use_container_width=True):
                if not empresa_sel or not cliente_nome.strip() or not veiculo.strip() or not placa.strip():
                    st.warning("Preencha Empresa, Cliente, Veículo e Placa.")
                else:
                    conflito = verificar_conflito_horario(data_ag.isoformat(), hora_escolhida_fmt)
                    if conflito:
                        st.error(
                            f"⛔ Não é possível agendar! Já existe um atendimento em **{data_ag.strftime('%d/%m/%Y')}** "
                            f"às **{hora_escolhida_fmt}** ({conflito.get('empresa_nome', '')} — "
                            f"{conflito.get('veiculo', '')}). Escolha outro horário."
                        )
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
                                    "hora_agendamento": hora_escolhida_fmt,
                                    "status": "Agendada",
                                }
                            ).execute()
                            limpar_cache_dados()
                            st.session_state.form_ag_ver += 1
                            st.session_state.mostrar_novo_ag = False
                            st.session_state.pending_cal_data = data_ag
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
                                f"Agendamento salvo para {data_ag.strftime('%d/%m/%Y')} às {hora_escolhida_fmt}!"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar agendamento: {e}")

    # VISÃO ATRASADAS / FRUSTRADAS
    if st.session_state.agenda_filtro == "Atrasadas":
        render_html(
            f'<div class="cv-day-summary-slim">⚠️ Atrasadas / Frustradas • {len(atrasadas_ou_frustradas)} atendimento(s)</div>'
        )
        if not atrasadas_ou_frustradas:
            st.success("Nenhum atendimento atrasado ou frustrado no momento!")
            return

        dists_atraso = calcular_distancias_em_lote(ponto_base, atrasadas_ou_frustradas)
        for ag in atrasadas_ou_frustradas:
            render_card_agendamento(
                ag,
                mapa_empresas,
                nomes_empresas,
                prefixo="ag_atraso",
                ponto_base=ponto_base,
                dist_info=dists_atraso.get(ag["id"]),
                mostrar_data=True,
            )
        return

    # VISÃO SEMANAL
    if st.session_state.agenda_filtro == "Esta Semana":
        semana_ags = [
            ag
            for ag in todos_agendamentos
            if inicio_semana.isoformat() <= str(ag.get("data_agendamento", ""))[:10] <= fim_semana.isoformat()
        ]
        render_html(
            f'<div class="cv-day-summary-slim">📆 Semana ({inicio_semana.strftime("%d/%m")} a {fim_semana.strftime("%d/%m")}) • {len(semana_ags)} agendado(s)</div>'
        )
        if not semana_ags:
            st.info("Nenhum agendamento registrado para esta semana.")
            return

        dists_sem = calcular_distancias_em_lote(ponto_base, semana_ags)
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
                    f"({len(lista_dia)}: {horarios_str})"
                )
            with h2:
                if st.button("Ver dia", key=f"ir_dia_{dt_iso}", use_container_width=True):
                    st.session_state.agenda_filtro = "Data"
                    st.session_state.agenda_data_busca = dt_obj
                    st.session_state.pending_cal_data = dt_obj
                    st.rerun()

            pends_sem = [
                (a, dists_sem[a["id"]])
                for a in lista_dia
                if a["id"] in dists_sem and a.get("status") == "Agendada"
            ]
            pends_sem.sort(key=lambda x: x[1]["km"])
            id_prox_sem = pends_sem[0][0]["id"] if pends_sem else None

            for ag in lista_dia:
                render_card_agendamento(
                    ag,
                    mapa_empresas,
                    nomes_empresas,
                    prefixo=f"sem_{dt_iso}",
                    ponto_base=ponto_base,
                    dist_info=dists_sem.get(ag["id"]),
                    eh_mais_proximo=(ag["id"] == id_prox_sem),
                    mostrar_data=False,
                )
        return

    # VISÃO DIÁRIA COMPACTA (Hoje, Amanhã ou Data escolhida)
    if st.session_state.agenda_filtro == "Hoje":
        data_ref = hoje
    elif st.session_state.agenda_filtro == "Amanhã":
        data_ref = amanha
    else:
        data_ref = st.session_state.agenda_data_busca or hoje

    ags_do_dia = [
        ag for ag in todos_agendamentos if str(ag.get("data_agendamento", ""))[:10] == data_ref.isoformat()
    ]

    distancias_dia = calcular_distancias_em_lote(ponto_base, ags_do_dia)
    todos_com_dist = [(ag, distancias_dia[ag["id"]]) for ag in ags_do_dia if ag["id"] in distancias_dia]
    todos_com_dist.sort(key=lambda par: par[1]["km"])

    pendentes_com_dist = [(ag, d) for ag, d in todos_com_dist if ag.get("status") == "Agendada"]
    id_mais_proximo = pendentes_com_dist[0][0]["id"] if pendentes_com_dist else None
    dist_mais_proximo = pendentes_com_dist[0][1] if pendentes_com_dist else None

    horarios_preenchidos, horarios_disponiveis = obter_horarios_status(
        todos_agendamentos, data_ref.isoformat()
    )

    # 3. Resumo fino em 1 linha
    render_html(
        f"""
        <div class="cv-day-summary-slim">
            📅 {DIAS_SEMANA_COMPLETO[data_ref.weekday()]}, {data_ref.strftime('%d/%m')} •
            {len(ags_do_dia)} agendado(s) • {len(horarios_disponiveis)} livre(s)
        </div>
        """
    )

    # 4. Distância do Ponto Base + Horários Livres recolhidos em 1 barrinha compacta
    if dist_mais_proximo:
        aprox_m = "~" if dist_mais_proximo.get("estimada") else ""
        titulo_gaveta = (
            f"🧭 Distância do Ponto Base • Mais próximo: {aprox_m}{fmt_km(dist_mais_proximo['km'])} "
            f"(~{fmt_tempo(dist_mais_proximo['minutos'])})"
        )
    elif ponto_base and ags_do_dia:
        titulo_gaveta = "🧭 Distância do Ponto Base & Horários livres"
    else:
        titulo_gaveta = f"🕒 Ver horários livres ({len(horarios_disponiveis)})"

    with st.expander(titulo_gaveta, expanded=False):
        render_html('<span class="cv-route-inner-marker marker-hidden"></span>')

        if ponto_base and ags_do_dia and todos_com_dist:
            st.caption(f"Referência: {ponto_base}")
            linhas_rota = []
            for idx, (ag_r, d_r) in enumerate(todos_com_dist, start=1):
                eh_top = ag_r["id"] == id_mais_proximo
                tag = '<span class="cv-badge-green">⭐ Mais próximo</span> ' if eh_top else f"<strong>{idx}º</strong> "
                pill_cls = "cv-dist-pill-closest" if eh_top else "cv-dist-pill"
                aprox = "~" if d_r.get("estimada") else ""
                linhas_rota.append(
                    f'<div class="cv-route-item">'
                    f'<div>{tag}⏰ <strong>{esc(ag_r.get("hora_agendamento", ""))}</strong> • '
                    f'{esc(ag_r.get("veiculo", ""))} ({esc(ag_r.get("cliente_nome", ""))}) '
                    f'<span style="color:var(--muted);">— {esc(ag_r.get("endereco", ""))}</span></div>'
                    f'<span class="{pill_cls}">📍 {aprox}{fmt_km(d_r["km"])} • ⏱️ ~{fmt_tempo(d_r["minutos"])}</span>'
                    f'</div>'
                )

            sem_calc = [ag for ag in ags_do_dia if ag["id"] not in distancias_dia]
            for ag_s in sem_calc:
                motivo = (
                    "Endereço não informado"
                    if not (ag_s.get("endereco") or "").strip()
                    else "Endereço não localizado no mapa"
                )
                linhas_rota.append(
                    f'<div class="cv-route-item">'
                    f'<div>⏰ <strong>{esc(ag_s.get("hora_agendamento", ""))}</strong> • '
                    f'{esc(ag_s.get("veiculo", ""))} ({esc(ag_s.get("cliente_nome", ""))})</div>'
                    f'<span class="cv-badge-amber">⚠️ {motivo}</span>'
                    f'</div>'
                )
            render_html("".join(linhas_rota))
        elif ags_do_dia and not ponto_base:
            st.info("💡 Cadastre seu **Ponto Base** na aba **👤 Perfil** para calcular distâncias.")

        if horarios_preenchidos:
            st.caption(f"Preenchidos: {', '.join(horarios_preenchidos)}")
        if horarios_disponiveis:
            pills_livres = "".join(
                f'<span class="cv-slot-pill-free">{h}</span>' for h in horarios_disponiveis
            )
            render_html(
                f'<div style="font-size:0.82rem;font-weight:700;margin-top:6px;">🟢 Horários disponíveis ({len(horarios_disponiveis)}):</div>'
                f'<div class="cv-slots-pills">{pills_livres}</div>'
            )
        else:
            st.caption("🔴 Todos os horários padrão (07:00 às 19:00) preenchidos.")

    # 5. Cards da Agenda logo de cara
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
# TELA 3: ORDEM DE SERVIÇO (CARDS EM CIMA, DETALHES/NOVA EMBAIXO)
# =========================================================
def tela_ordem_servico():
    mostrar_aviso_pendente()

    perfil = carregar_perfil()
    ponto_base = (perfil.get("ponto_base") or "").strip()

    empresas = carregar_empresas()
    nomes_empresas = [e["nome"] for e in empresas]
    mapa_empresas = {e["nome"]: e for e in empresas}
    hoje = hoje_br()

    todos_ags = carregar_agendamentos(apenas_agendadas=False)
    agendadas = [a for a in todos_ags if a.get("status") == "Agendada"]
    atrasadas_frust = [
        a for a in todos_ags if a.get("status") == "Frustrada" or agendamento_esta_atrasado(a)
    ]

    qtd_af = len(atrasadas_frust)
    lbl_af = f"Atrasadas ({qtd_af})" if qtd_af else "Atrasadas"

    # Sub-abas compactas em 1 linha logo no topo
    s1, s2, s3, s4 = st.columns(4)
    for idx, (col, chave_sub, rotulo_sub) in enumerate(
        [
            (s1, "OS do Dia", "OS do Dia"),
            (s2, "Próximas OS", "Próximas"),
            (s3, "Atrasadas / Frustradas", lbl_af),
            (s4, "Histórico de OS", "Histórico"),
        ]
    ):
        with col:
            if idx == 0:
                render_html('<span class="cv-filter-row-marker marker-hidden"></span>')
            if st.button(
                rotulo_sub,
                key=f"sub_os_{chave_sub}",
                type="primary" if st.session_state.os_subaba == chave_sub else "secondary",
                use_container_width=True,
            ):
                st.session_state.os_subaba = chave_sub
                st.rerun()

    if st.session_state.os_subaba == "OS do Dia":
        vistorias = carregar_vistorias()
        ags_hoje = [
            a
            for a in todos_ags
            if str(a.get("data_agendamento", ""))[:10] == hoje.isoformat()
            and a.get("status") in ("Agendada", "Frustrada")
        ]
        concl_hoje = [v for v in vistorias if str(v.get("data_vistoria", ""))[:10] == hoje.isoformat()]

        render_html(
            f'<div class="cv-day-summary-slim">📌 OS de Hoje ({hoje.strftime("%d/%m")}) • {len(ags_hoje)} pendente(s) • {len(concl_hoje)} concluída(s)</div>'
        )

        if not ags_hoje:
            st.info("Nenhuma Ordem de Serviço pendente na agenda de hoje.")
        else:
            dists_hoje = calcular_distancias_em_lote(ponto_base, ags_hoje)
            ordenados_h = sorted(
                [(a["id"], dists_hoje[a["id"]]) for a in ags_hoje if a["id"] in dists_hoje and a.get("status") == "Agendada"],
                key=lambda x: x[1]["km"],
            )
            id_prox_h = ordenados_h[0][0] if ordenados_h else None

            for ag in ags_hoje:
                render_card_agendamento(
                    ag,
                    mapa_empresas,
                    nomes_empresas,
                    prefixo="os_hoje",
                    ponto_base=ponto_base,
                    dist_info=dists_hoje.get(ag["id"]),
                    eh_mais_proximo=(ag["id"] == id_prox_h),
                    mostrar_data=False,
                )

        if concl_hoje:
            st.markdown(f"#### ✅ Concluídas Hoje ({len(concl_hoje)})")
            for v in concl_hoje:
                _render_card_os_concluida(v, mapa_empresas, nomes_empresas, prefixo="os_dia_conc")

    elif st.session_state.os_subaba == "Próximas OS":
        proximas = [a for a in agendadas if str(a.get("data_agendamento", ""))[:10] > hoje.isoformat()]
        render_html(
            f'<div class="cv-day-summary-slim">📆 Próximas Ordens de Serviço • {len(proximas)} agendada(s)</div>'
        )
        if not proximas:
            st.info("Nenhuma Ordem de Serviço futura agendada.")
        else:
            dists_prox = calcular_distancias_em_lote(ponto_base, proximas)
            for ag in proximas:
                render_card_agendamento(
                    ag,
                    mapa_empresas,
                    nomes_empresas,
                    prefixo="os_prox",
                    ponto_base=ponto_base,
                    dist_info=dists_prox.get(ag["id"]),
                    mostrar_data=True,
                )

    elif st.session_state.os_subaba == "Atrasadas / Frustradas":
        render_html(
            f'<div class="cv-day-summary-slim">⚠️ Atrasadas ou Frustradas • {len(atrasadas_frust)} pendência(s)</div>'
        )
        if not atrasadas_frust:
            st.success("Nenhuma Ordem de Serviço atrasada ou frustrada!")
        else:
            dists_af = calcular_distancias_em_lote(ponto_base, atrasadas_frust)
            for ag in atrasadas_frust:
                render_card_agendamento(
                    ag,
                    mapa_empresas,
                    nomes_empresas,
                    prefixo="os_atraso",
                    ponto_base=ponto_base,
                    dist_info=dists_af.get(ag["id"]),
                    mostrar_data=True,
                )

    else:
        vistorias = carregar_vistorias()
        render_html(
            f'<div class="cv-day-summary-slim">🗂️ Histórico de Ordens de Serviço • {len(vistorias)} registro(s)</div>'
        )
        if not vistorias:
            st.info("Nenhuma Ordem de Serviço concluída ainda.")
        else:
            for v in vistorias:
                _render_card_os_concluida(v, mapa_empresas, nomes_empresas, prefixo="os_hist")

    # Formulário de Nova OS Avulsa na PARTE DE BAIXO
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    with st.expander("➕ Nova Ordem de Serviço (Avulsa)", expanded=False):
        render_formulario_os(mapa_empresas, nomes_empresas, chave_prefixo="avulsa", ag=None)


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

        chave_foto = f"{prefixo}_{v['id']}"
        if chave_foto in st.session_state.fotos_abertas:
            foto_b64 = carregar_foto_os(v["id"])
            if foto_b64:
                st.image(base64_para_bytes(foto_b64), width=260)
            else:
                st.caption("Sem foto anexada nesta OS.")
        else:
            if st.button("📷 Ver foto anexada", key=f"ver_foto_{chave_foto}"):
                st.session_state.fotos_abertas.add(chave_foto)
                st.rerun()

        render_editor_os(v, mapa_empresas, nomes_empresas, prefixo_key=prefixo)


# =========================================================
# TELA 4: EMPRESAS PARCEIRAS (LISTA EM CIMA, CADASTRO EMBAIXO)
# =========================================================
def tela_empresas():
    mostrar_aviso_pendente()

    ver = st.session_state.form_emp_ver
    empresas = carregar_empresas()

    render_html(
        f'<div class="cv-day-summary-slim">🤝 Empresas Parceiras • {len(empresas)} cadastrada(s)</div>'
    )

    if not empresas:
        st.info("Nenhuma empresa cadastrada ainda. Adicione a primeira na opção abaixo.")
    else:
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
                        limpar_cache_dados()
                        st.session_state.form_emp_ver += 1
                        st.session_state.aviso_sucesso = f"Alterações de '{e_nome.strip()}' salvas!"
                        st.rerun()
                with b2:
                    if st.button("Excluir Empresa", key=f"ee_del_{emp['id']}_{ver}", use_container_width=True):
                        supabase.table("vistorias_empresas").delete().eq("id", emp["id"]).execute()
                        limpar_cache_dados()
                        st.session_state.form_emp_ver += 1
                        st.session_state.aviso_sucesso = f"Empresa '{emp['nome']}' removida."
                        st.rerun()

    # Cadastro de Nova Empresa na PARTE DE BAIXO
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    with st.expander("➕ Adicionar Nova Empresa", expanded=not bool(empresas)):
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
                    limpar_cache_dados()
                    st.session_state.form_emp_ver += 1
                    st.session_state.aviso_sucesso = f"Empresa '{nome.strip()}' cadastrada com sucesso!"
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar empresa: {e}")


# =========================================================
# TELA 5: FINANCEIRO & CALENDÁRIO (IGNORA SEM COBRANÇA)
# =========================================================
def tela_financeiro():
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
                render_html('<span class="marker-green marker-hidden"></span>')
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
                    limpar_cache_dados()
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
                limpar_cache_dados()
                st.session_state.aviso_sucesso = f"Baixa de {emp_nome} desfeita."
                st.rerun()

            with st.expander(f"✏️ Corrigir ou Excluir OS recebidas — {emp_nome} ({qtd})"):
                for os_item in lista_os:
                    render_editor_os(os_item, mapa_empresas, nomes_empresas, prefixo_key="fin_rec")


# =========================================================
# TELA 6: RELATÓRIOS EM PDF (RÁPIDO, SOB DEMANDA)
# =========================================================
def tela_pdf():
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

    render_html(
        f'<div class="cv-day-summary-slim">📄 Relatórios em PDF • {len(filtradas)} registro(s)</div>'
    )

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

            p_col1, p_col2 = st.columns(2)
            chave_foto = f"pdf_{v['id']}"
            with p_col1:
                if chave_foto in st.session_state.fotos_abertas:
                    foto_b64 = carregar_foto_os(v["id"])
                    if foto_b64:
                        st.image(base64_para_bytes(foto_b64), width=260)
                    else:
                        st.caption("Sem foto anexada.")
                else:
                    if st.button("📷 Ver foto anexada", key=f"ver_foto_{chave_foto}", use_container_width=True):
                        st.session_state.fotos_abertas.add(chave_foto)
                        st.rerun()

            with p_col2:
                if PDF_DISPONIVEL:
                    if v["id"] in st.session_state.pdfs_prontos:
                        st.download_button(
                            "⬇️ Baixar PDF Individual",
                            data=st.session_state.pdfs_prontos[v["id"]],
                            file_name=f"OS_{v['id']}_{v['placa']}.pdf",
                            mime="application/pdf",
                            key=f"dl_pdf_ind_{v['id']}",
                            type="primary",
                            use_container_width=True,
                        )
                    else:
                        if st.button(
                            "📄 Gerar PDF Individual",
                            key=f"gen_pdf_ind_{v['id']}",
                            use_container_width=True,
                        ):
                            foto_b64 = carregar_foto_os(v["id"])
                            st.session_state.pdfs_prontos[v["id"]] = gerar_pdf_individual(v, foto_b64)
                            st.rerun()

            st.markdown("---")
            render_editor_os(v, mapa_empresas, nomes_empresas, prefixo_key="pdf_tab")


# =========================================================
# BARRA SUPERIOR (BOLINHA TEMA + SAIR) E BARRA INFERIOR FIXA
# =========================================================
def render_barra_inferior():
    abas = [
        ("Agenda", "📅  \nAgenda"),
        ("Ordem de Serviço", "✅  \nOrdem de Serviço"),
        ("Empresas", "🤝  \nEmpresas"),
        ("Financeiro", "💰  \nFinanceiro"),
        ("PDF", "📄  \nPDF"),
        ("Perfil", "👤  \nPerfil"),
    ]
    cols_nav = st.columns(len(abas))
    for idx, (col, (chave, rotulo)) in enumerate(zip(cols_nav, abas)):
        with col:
            if idx == 0:
                render_html('<span class="cv-bottom-nav-marker marker-hidden"></span>')
            tipo = "primary" if st.session_state.pagina == chave else "secondary"
            if st.button(rotulo, key=f"nav_{chave}", type=tipo, use_container_width=True):
                st.session_state.pagina = chave
                st.session_state.os_card_aberto_id = None
                st.rerun()


def main():
    sincronizar_sessao()

    if not st.session_state.autenticado:
        tela_login()
        return

    # Barra superior limpa: Marca | Bolinha Claro/Escuro | Sair
    top1, top2, top3 = st.columns([3.8, 0.55, 0.95])
    with top1:
        render_html('<div class="brand-bar cv-top-bar-marker">🚗 Controle de Vistorias</div>')
    with top2:
        botao_alternar_tema("app")
    with top3:
        if st.button("🚪 Sair", key="btn_sair_app", use_container_width=True):
            st.session_state.autenticado = False
            st.session_state.os_card_aberto_id = None
            _limpar_token_url()
            st.rerun()

    # Conteúdo da tela selecionada
    if st.session_state.pagina == "Agenda":
        tela_agenda()
    elif st.session_state.pagina == "Ordem de Serviço":
        tela_ordem_servico()
    elif st.session_state.pagina == "Empresas":
        tela_empresas()
    elif st.session_state.pagina == "Financeiro":
        tela_financeiro()
    elif st.session_state.pagina == "PDF":
        tela_pdf()
    elif st.session_state.pagina == "Perfil":
        tela_perfil()

    # Barra fixa inferior estilo aplicativo
    render_barra_inferior()


if __name__ == "__main__":
    main()

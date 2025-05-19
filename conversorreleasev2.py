import streamlit as st
import json
from pathlib import Path
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# =========================
# CONFIGURAÇÕES GERAIS
# =========================
ID_USUARIOS_DRIVE = "1Xy3R_XqKKbJI2h9dL6A1NV5kUbP7kh_K"
ID_EMBALAGENS_DRIVE = "1rMDq1rv-K-ON2CJ9pmv3QNlUPsqdCq47"
CAMINHO_USUARIOS_LOCAL = Path("usuarios.json")
CAMINHO_EMBALAGENS_LOCAL = Path("embalagens.json")
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# =========================
# CONEXÃO GOOGLE DRIVE
# =========================
def conectar_drive():
    service_account_info = st.secrets["gdrive"]
    creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def baixar_json(service, file_id, destino_local):
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(destino_local, 'wb') as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

def atualizar_json(service, file_id, local_path):
    media = MediaFileUpload(local_path, mimetype='application/json')
    service.files().update(fileId=file_id, media_body=media).execute()

# =========================
# FUNÇÕES AUXILIARES
# =========================
def carregar_usuarios():
    if CAMINHO_USUARIOS_LOCAL.exists():
        with open(CAMINHO_USUARIOS_LOCAL, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        st.error("Arquivo de usuários não encontrado localmente.")
        st.stop()

def carregar_embalagens():
    if CAMINHO_EMBALAGENS_LOCAL.exists():
        with open(CAMINHO_EMBALAGENS_LOCAL, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def salvar_embalagens(lista, service):
    with open(CAMINHO_EMBALAGENS_LOCAL, "w", encoding="utf-8") as f:
        json.dump(lista, f, indent=4, ensure_ascii=False)
    atualizar_json(service, ID_EMBALAGENS_DRIVE, CAMINHO_EMBALAGENS_LOCAL)

# =========================
# INÍCIO DO APP
# =========================
st.set_page_config(page_title="Conversor de Embalagens - Login", layout="wide")
service = conectar_drive()

# Baixar arquivos necessários
try:
    baixar_json(service, ID_USUARIOS_DRIVE, CAMINHO_USUARIOS_LOCAL)
    baixar_json(service, ID_EMBALAGENS_DRIVE, CAMINHO_EMBALAGENS_LOCAL)
except Exception as e:
    st.error(f"Erro ao sincronizar arquivos do Google Drive: {e}")
    st.stop()

usuarios = carregar_usuarios()

results = service.files().list(
    q=query,
    spaces='drive',
    fields="files(id, name)",
    supportsAllDrives=True,
    includeItemsFromAllDrives=True
).execute()

# =========================
# TELA DE LOGIN
# =========================
if "logado" not in st.session_state:
    st.session_state.logado = False

if not st.session_state.logado:
    st.title("🔒 Login - Conversor de Embalagens")
    usuario_input = st.text_input("Usuário")
    senha_input = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        if usuario_input in usuarios and usuarios[usuario_input] == senha_input:
            st.session_state.logado = True
            st.success(f"Bem-vindo, {usuario_input}!")
            st.experimental_rerun()
        else:
            st.error("Usuário ou senha inválidos.")
    st.stop()

# =========================
# MENU PRINCIPAL
# =========================
st.sidebar.image("https://i.imgur.com/YOwQy4V.png", width=200)  # Exemplo de logo hospedada
pagina = st.sidebar.selectbox("📂 Menu", ["Cadastro de Produto", "Conversão de Quantidades"])

dados = carregar_embalagens()

# =========================
# CADASTRO DE PRODUTO
# =========================
if pagina == "Cadastro de Produto":
    st.title("📦 Cadastro de Produto")

    with st.form("cadastro_produto"):
        produto = st.text_input("Nome do Produto")
        col1, col2, col3 = st.columns(3)
        with col1:
            cod_caixa = st.text_input("Código da Caixa")
            qtd_display_por_caixa = st.number_input("Displays por Caixa", min_value=1)
        with col2:
            cod_display = st.text_input("Código do Display")
            qtd_unid_por_display = st.number_input("Unidades por Display", min_value=1)
        with col3:
            cod_unitario = st.text_input("Código Unitário")

        if st.form_submit_button("Salvar Produto"):
            novo = {
                "produto": produto,
                "cod_caixa": cod_caixa.strip().upper(),
                "qtd_displays_caixa": qtd_display_por_caixa,
                "cod_display": cod_display.strip().upper(),
                "qtd_unidades_display": qtd_unid_por_display,
                "cod_unitario": cod_unitario.strip().upper()
            }
            dados.append(novo)
            salvar_embalagens(dados, service)
            st.success("Produto cadastrado com sucesso!")
            st.rerun()

    st.divider()
    st.subheader("📋 Produtos Cadastrados")
    if dados:
        df = pd.DataFrame(dados)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhum produto cadastrado.")

# =========================
# CONVERSÃO DE QUANTIDADES
# =========================
if pagina == "Conversão de Quantidades":
    st.title("🔁 Conversão de Quantidades")

    if not dados:
        st.warning("Nenhum produto cadastrado.")
        st.stop()

    codigos = []
    cod_to_produto = {}

    for item in dados:
        for cod in [item["cod_caixa"], item["cod_display"], item["cod_unitario"]]:
            codigos.append(cod)
            cod_to_produto[cod] = item

    codigo_origem = st.selectbox("Código de Origem", codigos)
    qtd_informada = st.number_input("Quantidade", min_value=1)

    if st.button("Converter"):
        produto = cod_to_produto.get(codigo_origem)
        if not produto:
            st.error("Código não encontrado.")
            st.stop()

        un_por_cx = produto["qtd_displays_caixa"] * produto["qtd_unidades_display"]
        un_por_dp = produto["qtd_unidades_display"]

        total_un = (
            qtd_informada * un_por_cx if codigo_origem == produto["cod_caixa"]
            else qtd_informada * un_por_dp if codigo_origem == produto["cod_display"]
            else qtd_informada
        )

        qtd_caixa = total_un // un_por_cx
        restante = total_un % un_por_cx

        qtd_display = restante // un_por_dp
        sobra_un = restante % un_por_dp

        st.success(f"🔹 Conversão de {qtd_informada}x ({codigo_origem}) → {produto['produto']}")
        st.markdown(f"- 📦 **Caixas** ({produto['cod_caixa']}): `{int(qtd_caixa)}`")
        st.markdown(f"- 📦 **Displays** ({produto['cod_display']}): `{int(qtd_display)}`")
        st.markdown(f"- 🧃 **Unidades** ({produto['cod_unitario']}): `{int(sobra_un)}`")

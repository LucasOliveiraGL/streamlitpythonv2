import streamlit as st
import json
from pathlib import Path
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

CAMINHO_JSON_LOCAL = Path("embalagens.json")
NOME_ARQUIVO_DRIVE = "embalagens.json"
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Conectar ao Google Drive usando secrets do Streamlit
def conectar_drive():
    service_account_info = st.secrets["gdrive"]
    creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

# Buscar ID do arquivo no Drive
def buscar_arquivo(service, nome_arquivo):
    query = f"name='{nome_arquivo}' and trashed = false"
    results = service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
    items = results.get('files', [])
    return items[0]['id'] if items else None

# Versão de debug que mostra todos os arquivos
def buscar_arquivo_debug(service, nome_arquivo):
    query = "trashed = false"
    results = service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
    st.write("📂 Arquivos disponíveis no Drive:", results.get("files", []))
    return buscar_arquivo(service, nome_arquivo)

# Baixar JSON do Drive
def baixar_json(service, file_id, destino_local):
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(destino_local, 'wb') as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

# Atualizar JSON no Drive
def atualizar_json(service, file_id, local_path):
    media = MediaFileUpload(local_path, mimetype='application/json')
    service.files().update(fileId=file_id, media_body=media).execute()

# ====== INÍCIO DO APP ======
st.set_page_config(page_title="Conversor de Embalagens", layout="wide")

service = conectar_drive()
file_id = buscar_arquivo_debug(service, NOME_ARQUIVO_DRIVE)  # apenas debug

if file_id:
    baixar_json(service, file_id, CAMINHO_JSON_LOCAL)
else:
    st.error("Arquivo embalagens.json não encontrado no Google Drive.")
    st.stop()

# ====== FUNÇÕES ======
def carregar_dados():
    if CAMINHO_JSON_LOCAL.exists():
        with open(CAMINHO_JSON_LOCAL, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def salvar_dados(lista):
    with open(CAMINHO_JSON_LOCAL, "w", encoding="utf-8") as f:
        json.dump(lista, f, indent=4, ensure_ascii=False)
    atualizar_json(service, file_id, CAMINHO_JSON_LOCAL)

# ====== INTERFACE ======
pagina = st.sidebar.selectbox("📂 Menu", ["Cadastro de Produto", "Conversão de Quantidades"])
dados = carregar_dados()

if pagina == "Cadastro de Produto":
    st.title("📦 Cadastro de Produto (Caixa > Display > Unidade)")

    with st.form("cadastro_produto"):
        st.subheader("➕ Cadastrar Novo Produto")
        produto = st.text_input("Nome do Produto")
        col1, col2, col3 = st.columns(3)
        with col1:
            cod_caixa = st.text_input("Código da Caixa")
            qtd_display_por_caixa = st.number_input("Displays por Caixa", min_value=1, step=1)
        with col2:
            cod_display = st.text_input("Código do Display")
            qtd_unid_por_display = st.number_input("Unidades por Display", min_value=1, step=1)
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
            salvar_dados(dados)
            st.success("Produto cadastrado com sucesso!")
            st.rerun()

    st.divider()
    st.subheader("📋 Produtos Cadastrados")
    if dados:
        df = pd.DataFrame(dados)
        editados = st.data_editor(df, use_container_width=True, num_rows="dynamic", key="editor")
        if st.button("💾 Salvar Alterações"):
            salvar_dados(editados.to_dict(orient="records"))
            st.success("Alterações salvas com sucesso!")
            st.rerun()

        selecionados = st.multiselect("Selecione produtos para excluir", df["produto"].tolist())
        if st.button("🗑️ Excluir Selecionados") and selecionados:
            df_filtrado = df[~df["produto"].isin(selecionados)]
            salvar_dados(df_filtrado.to_dict(orient="records"))
            st.success(f"Produtos excluídos: {', '.join(selecionados)}")
            st.rerun()
    else:
        st.info("Nenhum produto cadastrado.")

elif pagina == "Conversão de Quantidades":
    st.title("🔁 Conversão de Quantidades")

    if not dados:
        st.warning("Nenhum produto cadastrado.")
        st.stop()

    opcoes = []
    cod_to_produto = {}

    for item in dados:
        opcoes.extend([
            (item["cod_caixa"], item),
            (item["cod_display"], item),
            (item["cod_unitario"], item)
        ])
        cod_to_produto[item["cod_caixa"]] = item
        cod_to_produto[item["cod_display"]] = item
        cod_to_produto[item["cod_unitario"]] = item

    codigos = list(dict.fromkeys([c[0] for c in opcoes]))
    codigo_origem = st.selectbox("Código de Origem", codigos)
    qtd_informada = st.number_input("Quantidade", min_value=1, step=1)

    if st.button("Converter"):
        produto = cod_to_produto.get(codigo_origem)
        if not produto:
            st.error("Código não encontrado.")
            st.stop()

        cod_cx = produto["cod_caixa"]
        cod_dp = produto["cod_display"]
        cod_un = produto["cod_unitario"]
        qtd_dp_por_cx = produto["qtd_displays_caixa"]
        qtd_un_por_dp = produto["qtd_unidades_display"]

        un_por_cx = qtd_dp_por_cx * qtd_un_por_dp
        un_por_dp = qtd_un_por_dp

        if codigo_origem == cod_cx:
            total_un = qtd_informada * un_por_cx
        elif codigo_origem == cod_dp:
            total_un = qtd_informada * un_por_dp
        elif codigo_origem == cod_un:
            total_un = qtd_informada
        else:
            st.error("Código inválido.")
            st.stop()

        qtd_caixa = total_un // un_por_cx
        restante = total_un % un_por_cx

        qtd_display = restante // un_por_dp
        sobra_un = restante % un_por_dp

        st.success(f"🔹 Conversão de {qtd_informada}x ({codigo_origem}) → {produto['produto']}")
        st.markdown(f"- 📦 **Caixas** ({cod_cx}): `{int(qtd_caixa)}`")
        st.markdown(f"- 📦 **Displays** ({cod_dp}): `{int(qtd_display)}`")
        st.markdown(f"- 🧃 **Unidades** ({cod_un}): `{int(sobra_un)}`")

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

def conectar_drive():
    service_account_info = st.secrets["gdrive"]
    creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def buscar_arquivo(service, nome_arquivo):
    query = f"name='{nome_arquivo}' and trashed = false"
    results = service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
    items = results.get('files', [])
    return items[0]['id'] if items else None

def baixar_json(service, file_id, destino_local):
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(destino_local, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()

def atualizar_json(service, file_id, local_path):
    media = MediaFileUpload(local_path, mimetype='application/json')
    service.files().update(fileId=file_id, media_body=media).execute()

st.set_page_config(page_title="Conversor de Embalagens", layout="wide")

service = conectar_drive()
file_id = buscar_arquivo(service, NOME_ARQUIVO_DRIVE)

if file_id:
    baixar_json(service, file_id, CAMINHO_JSON_LOCAL)
else:
    st.warning("Arquivo embalagens.json não encontrado. Criando arquivo vazio...")
    with open(CAMINHO_JSON_LOCAL, "w", encoding="utf-8") as f:
        json.dump([], f)
    file_metadata = {"name": NOME_ARQUIVO_DRIVE}
    media = MediaFileUpload(CAMINHO_JSON_LOCAL, mimetype='application/json')
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    file_id = file.get("id")

def carregar_dados():
    if CAMINHO_JSON_LOCAL.exists():
        with open(CAMINHO_JSON_LOCAL, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def salvar_dados(lista):
    with open(CAMINHO_JSON_LOCAL, "w", encoding="utf-8") as f:
        json.dump(lista, f, indent=4, ensure_ascii=False)
    atualizar_json(service, file_id, CAMINHO_JSON_LOCAL)

pagina = st.sidebar.selectbox("📂 Menu", ["Cadastro de Produto", "Conversão de Quantidades"])
dados = carregar_dados()

if pagina == "Cadastro de Produto":
    st.title("📦 Cadastro de Produto (Display ↔ Caixa)")

    with st.form("cadastro_produto"):
        st.subheader("➕ Cadastrar Novo Produto")
        produto = st.text_input("Nome do Produto")
        col1, col2 = st.columns(2)
        with col1:
            cod_caixa = st.text_input("Código da Caixa")
        with col2:
            cod_display = st.text_input("Código do Display")
        qtd_display_por_caixa = st.number_input("Displays por Caixa", min_value=1, step=1)

        if st.form_submit_button("Salvar Produto"):
            novo = {
                "produto": produto,
                "cod_caixa": cod_caixa.strip().upper(),
                "qtd_displays_caixa": qtd_display_por_caixa,
                "cod_display": cod_display.strip().upper()
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
    st.title("🔁 Conversão entre Caixa e Display")

    if not dados:
        st.warning("Nenhum produto cadastrado.")
        st.stop()

    cod_to_produto = {}
    codigos = []

    for item in dados:
        codigos.extend([item["cod_caixa"], item["cod_display"]])
        cod_to_produto[item["cod_caixa"]] = item
        cod_to_produto[item["cod_display"]] = item

    codigo_origem = st.selectbox("Código de Origem", list(dict.fromkeys(codigos)))
    qtd_informada = st.number_input("Quantidade", min_value=1, step=1)

    if st.button("Converter"):
        produto = cod_to_produto.get(codigo_origem)
        if not produto:
            st.error("Código não encontrado.")
            st.stop()

        cod_cx = produto["cod_caixa"]
        cod_dp = produto["cod_display"]
        qtd_dp_por_cx = produto["qtd_displays_caixa"]

        if codigo_origem == cod_cx:
            qtd_caixas = qtd_informada
            qtd_displays = qtd_caixas * qtd_dp_por_cx
        elif codigo_origem == cod_dp:
            qtd_displays = qtd_informada
            qtd_caixas = qtd_displays // qtd_dp_por_cx
            sobra_dp = qtd_displays % qtd_dp_por_cx
        else:
            st.error("Código inválido.")
            st.stop()

        st.success(f"🔹 Conversão de {qtd_informada}x ({codigo_origem}) → {produto['produto']}")
        if codigo_origem == cod_cx:
            st.markdown(f"- 📦 **Caixas** ({cod_cx}): `{int(qtd_caixas)}`")
            st.markdown(f"- 📦 **Displays** ({cod_dp}): `{int(qtd_displays)}`")
        else:
            st.markdown(f"- 📦 **Displays** ({cod_dp}): `{int(qtd_displays)}`")
            st.markdown(f"- 📦 **Caixas** ({cod_cx}): `{int(qtd_caixas)}`")
            if sobra_dp:
                st.markdown(f"- ⚠️ **Displays avulsos**: `{int(sobra_dp)}`")

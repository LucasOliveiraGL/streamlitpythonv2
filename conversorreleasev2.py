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

# Conexão com o Google Drive
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
        _, done = downloader.next_chunk()

def atualizar_json(service, file_id, local_path):
    media = MediaFileUpload(local_path, mimetype='application/json')
    service.files().update(fileId=file_id, media_body=media).execute()

# Setup inicial
st.set_page_config(page_title="Conversor de Embalagens", layout="wide")
service = conectar_drive()
file_id = buscar_arquivo(service, NOME_ARQUIVO_DRIVE)

if file_id:
    baixar_json(service, file_id, CAMINHO_JSON_LOCAL)
else:
    st.warning("Arquivo embalagens.json não encontrado. Criando arquivo vazio...")
    with open(CAMINHO_JSON_LOCAL, "w", encoding="utf-8") as f:
        json.dump([], f)
    metadata = {"name": NOME_ARQUIVO_DRIVE}
    media = MediaFileUpload(CAMINHO_JSON_LOCAL, mimetype='application/json')
    file = service.files().create(body=metadata, media_body=media, fields='id').execute()
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

pagina = st.sidebar.radio("📂 Menu", ["📦 Cadastro de Produto", "🔁 Conversão de Quantidades", "📥 Importar Produtos (Planilha)"])
dados = carregar_dados()

# Cadastro manual
if pagina == "📦 Cadastro de Produto":
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

# Importação por planilha
elif pagina == "📥 Importar Produtos (Planilha)":
    st.title("📥 Importar Produtos em Massa (XLSX)")
    st.markdown("Envie uma planilha com os seguintes campos:")
    st.code("produto, cod_caixa, qtd_displays_caixa, cod_display")

    arquivo = st.file_uploader("Selecione o arquivo .xlsx", type=["xlsx", "xls"])
    substituir = st.checkbox("❗ Substituir todos os produtos existentes", value=False)

    if arquivo and st.button("📤 Importar"):
        try:
            df = pd.read_excel(arquivo, dtype=str)
            obrigatorios = ["produto", "cod_caixa", "qtd_displays_caixa", "cod_display"]
            if not all(col in df.columns for col in obrigatorios):
                st.error(f"A planilha deve conter as colunas: {', '.join(obrigatorios)}")
                st.stop()

            df["produto"] = df["produto"].astype(str).str.strip()
            df["cod_caixa"] = df["cod_caixa"].astype(str).str.upper()
            df["cod_display"] = df["cod_display"].astype(str).str.upper()
            df["qtd_displays_caixa"] = df["qtd_displays_caixa"].astype(int)

            lista_produtos = df.to_dict(orient="records")
            if substituir:
                dados.clear()
            dados.extend(lista_produtos)
            salvar_dados(dados)
            st.success(f"{len(lista_produtos)} produtos importados com sucesso!")
            st.rerun()

        except Exception as e:
            st.error(f"Erro ao importar: {e}")

# Conversão em massa
elif pagina == "🔁 Conversão de Quantidades":
    st.title("🔁 Conversão em Massa entre Caixa e Display")

    if not dados:
        st.warning("Nenhum produto cadastrado.")
        st.stop()

    cod_to_produto = {}
    for item in dados:
        cod_to_produto[item["cod_caixa"]] = item
        cod_to_produto[item["cod_display"]] = item

    st.markdown("### 📋 Entradas")
    col1, col2 = st.columns(2)
    with col1:
        codigos_texto = st.text_area("Códigos (um por linha)")
    with col2:
        quantidades_texto = st.text_area("Quantidades (mesma ordem)")

    if st.button("Converter em Massa"):
        codigos = codigos_texto.strip().splitlines()
        quantidades = quantidades_texto.strip().splitlines()

        if len(codigos) != len(quantidades):
            st.error("Número de códigos e quantidades deve ser igual.")
            st.stop()

        resultados = []
        for cod, qtd in zip(codigos, quantidades):
            cod = cod.strip().upper()
            try:
                qtd = int(qtd)
            except:
                st.error(f"Quantidade inválida para código {cod}")
                continue

            produto = cod_to_produto.get(cod)
            if not produto:
                resultados.append({
                    "Código": cod,
                    "Produto": "Não encontrado",
                    "Conversão": "❌"
                })
                continue

            cod_cx = produto["cod_caixa"]
            cod_dp = produto["cod_display"]
            qtd_dp_por_cx = produto["qtd_displays_caixa"]

            if cod == cod_dp:
                total_dp = qtd
                total_cx = total_dp // qtd_dp_por_cx
                sobra = total_dp % qtd_dp_por_cx
            elif cod == cod_cx:
                total_cx = qtd
                total_dp = total_cx * qtd_dp_por_cx
                sobra = 0
            else:
                resultados.append({
                    "Código": cod,
                    "Produto": produto["produto"],
                    "Conversão": "Código inválido"
                })
                continue

            resultados.append({
                "Código": cod,
                "Produto": produto["produto"],
                "Displays": total_dp,
                "Caixas": total_cx,
                "Sobra Displays": sobra
            })

        df_resultado = pd.DataFrame(resultados)
        st.success("Conversão realizada!")
        st.dataframe(df_resultado, use_container_width=True)

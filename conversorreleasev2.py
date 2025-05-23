import streamlit as st
import json
import requests
from pathlib import Path
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import random
from datetime import datetime

# === DEVE SER A PRIMEIRA CHAMADA DO STREAMLIT ===
st.set_page_config(page_title="Conversor de Embalagens", layout="wide")

# ===== CONFIGURAÇÕES =====
CAMINHO_JSON_LOCAL = Path("embalagens.json")
NOME_ARQUIVO_DRIVE = "embalagens.json"
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CNPJ_DESTINO = "19198834000262"

# ===== FUNÇÕES GOOGLE DRIVE =====
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

# ===== FUNÇÕES DE DADOS =====
def carregar_dados():
    if CAMINHO_JSON_LOCAL.exists():
        with open(CAMINHO_JSON_LOCAL, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def salvar_dados(lista):
    with open(CAMINHO_JSON_LOCAL, "w", encoding="utf-8") as f:
        json.dump(lista, f, indent=4, ensure_ascii=False)
    atualizar_json(service, file_id, CAMINHO_JSON_LOCAL)

def gerar_chave_nfe():
    return ''.join([str(random.randint(0, 9)) for _ in range(44)])

def gerar_numped():
    return ''.join([str(random.randint(0, 9)) for _ in range(6)])

def gerar_json_saida(codprod, qtde, lote):
    return {
        "CORPEM_ERP_DOC_SAI": {
            "CGCCLIWMS": CNPJ_DESTINO,
            "CGCEMINF": CNPJ_DESTINO,
            "OBSPED": "",
            "OBSROM": "",
            "NUMPEDCLI": gerar_numped(),
            "VLTOTPED": "1,00",
            "CGCDEST": "",
            "NOMEDEST": "",
            "ITENS": [{
                "NUMSEQ": "1",
                "CODPROD": codprod,
                "QTPROD": str(qtde),
                "VLUNIT": "1,00",
                "LOTFAB": lote
            }]
        }
    }

def gerar_json_entrada(itens):
    total_qtd = sum([float(i["QTPROD"]) for i in itens])
    itens_processados = []
    for i in itens:
        proporcional = (float(i["QTPROD"]) / total_qtd)
        valor_item = round(proporcional, 4)
        itens_processados.append({
            "NUMSEQ": i["NUMSEQ"],
            "CODPROD": i["CODPROD"],
            "QTPROD": i["QTPROD"],
            "VLTOTPROD": str(valor_item),
            "NUMSEQ_DEV": i["NUMSEQ"]
        })
    return {
        "CORPEM_ERP_DOC_ENT": {
            "CGCCLIWMS": CNPJ_DESTINO,
            "CGCREM": CNPJ_DESTINO,
            "OBSRESDP": "",
            "TPDESTNF": "",
            "NUMNF": "000000001",
            "SERIENF": "1",
            "DTEMINF": datetime.now().strftime("%d/%m/%Y"),
            "VLTOTALNF": "1.00",
            "NUMEPEDCLI": gerar_numped(),
            "CHAVENF": gerar_chave_nfe(),
            "ITENS": itens_processados
        }
    }

# ===== SETUP INICIAL =====
service = conectar_drive()
file_id = buscar_arquivo(service, NOME_ARQUIVO_DRIVE)

if file_id:
    baixar_json(service, file_id, CAMINHO_JSON_LOCAL)
else:
    with open(CAMINHO_JSON_LOCAL, "w", encoding="utf-8") as f:
        json.dump([], f)
    metadata = {"name": NOME_ARQUIVO_DRIVE}
    media = MediaFileUpload(CAMINHO_JSON_LOCAL, mimetype='application/json')
    file_id = service.files().create(body=metadata, media_body=media, fields='id').execute().get("id")

# ===== INTERFACE =====
pagina = st.sidebar.radio("📁 Menu", ["Cadastro de Produto", "Importar Produtos (Planilha)", "Executar Conversão com Estoque"])
dados = carregar_dados()

if pagina == "Cadastro de Produto":
    st.title("📦 Cadastro de Produto")

    with st.form("cadastro_produto"):
        produto = st.text_input("Nome do Produto")
        col1, col2 = st.columns(2)
        with col1:
            cod_caixa = st.text_input("Código da Caixa")
        with col2:
            cod_display = st.text_input("Código do Display")
        qtd_disp_cx = st.number_input("Displays por Caixa", min_value=1, step=1)

        if st.form_submit_button("Salvar"):
            dados.append({
                "produto": produto,
                "cod_caixa": cod_caixa.upper(),
                "cod_display": cod_display.upper(),
                "qtd_displays_caixa": int(qtd_disp_cx)
            })
            salvar_dados(dados)
            st.success("Produto salvo com sucesso!")
            st.rerun()

    # ✅ Esta parte deve ficar FORA do `with st.form(...)`
    if dados:
        st.markdown("### 📋 Produtos Cadastrados")
        df = pd.DataFrame(dados)
        df.columns = ["Nome", "Código da Caixa", "Código do Display", "Displays por Caixa"]
        st.dataframe(df, use_container_width=True)
    else:
        st.error("Nenhum produto cadastrado ainda.")
        

elif pagina == "Importar Produtos (Planilha)":
    st.title("📥 Importar Produtos via Planilha")
    arq = st.file_uploader("Selecione um .xlsx", type="xlsx")
    substituir = st.checkbox("❗ Substituir todos os produtos existentes", value=False)
    if arq and st.button("Importar"):
        df = pd.read_excel(arq, dtype=str)
        obrig = ["produto", "cod_caixa", "qtd_displays_caixa", "cod_display"]
        if not all(c in df.columns for c in obrig):
            st.error("Colunas obrigatórias ausentes.")
        else:
            df["qtd_displays_caixa"] = df["qtd_displays_caixa"].astype(int)
            novos = df.to_dict(orient="records")
            dados = novos if substituir else dados + novos
            salvar_dados(dados)
            st.success(f"{len(novos)} produtos importados!")


#ABA DE CONVERSÃO

There was an error committing your changes: File could not be edited
# 🔁 Bloco de envio separado para funcionar mesmo após reload
if "json_saida" in st.session_state and "json_entrada" in st.session_state:
    json_saida = st.session_state["json_saida"]
    json_entrada = st.session_state["json_entrada"]

    st.subheader("📦 Resumo - JSON de Saída")
    for item in json_saida["CORPEM_ERP_DOC_SAI"]["ITENS"]:
        st.markdown(f"- **Produto:** `{item['CODPROD']}` | **Qtd:** {item['QTPROD']} | **Lote:** `{item['LOTFAB']}`")

    st.subheader("📥 Resumo - JSON de Entrada")
    for item in json_entrada["CORPEM_ERP_DOC_ENT"]["ITENS"]:
        st.markdown(f"- **Produto:** `{item['CODPROD']}` | **Qtd:** {item['QTPROD']}")

    if st.button("📤 Enviar JSONs para CORPEM"):
        import json, io
        from googleapiclient.http import MediaIoBaseUpload

        url = "http://webcorpem.no-ip.info:800/scripts/mh.dll/wc"
        headers = {"Content-Type": "application/json"}
        r1 = requests.post(url, headers=headers, json=json_saida)
        r2 = requests.post(url, headers=headers, json=json_entrada)

        st.subheader("🔍 Resposta da API")
        st.code(f"Saída: {r1.status_code} - {r1.text}\nEntrada: {r2.status_code} - {r2.text}")

        if r1.ok and r2.ok:
            st.success("✅ JSONs enviados com sucesso!")

            json_final = {
                "saida": json_saida,
                "entrada": json_entrada,
                "resposta_saida": r1.text,
                "resposta_entrada": r2.text,
                "enviado_em": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            }

            service = conectar_drive()
            resultado = service.files().list(
                q="name='log_jsons' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="files(id)").execute()
            itens = resultado.get('files', [])
            if itens:
                pasta_id = itens[0]['id']
            else:
                meta = {'name': 'log_jsons', 'mimeType': 'application/vnd.google-apps.folder'}
                pasta_id = service.files().create(body=meta, fields='id').execute().get("id")

            nome_arquivo = f"log_json_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            buffer = io.BytesIO(json.dumps(json_final, indent=4, ensure_ascii=False).encode("utf-8"))
            media = MediaIoBaseUpload(buffer, mimetype='application/json')
            service.files().create(
                body={"name": nome_arquivo, "parents": [pasta_id]},
                media_body=media,
                fields="id"
            ).execute()

            st.success(f"📁 JSON salvo em log_jsons como `{nome_arquivo}`.")
        else:
            st.error("❌ Falha no envio dos JSONs.")

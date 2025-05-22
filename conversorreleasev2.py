import streamlit as st
import json
from pathlib import Path
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import random
from datetime import datetime

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

# ===== SETUP INICIAL =====
st.set_page_config(page_title="Conversor de Embalagens", layout="wide")
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

def gerar_json_saida(codprod, qtde, lote):
    return {
        "CORPEM_ERP_DOC_SAI": {
            "CGCCLIWMS": CNPJ_DESTINO,
            "CGCEMINF": CNPJ_DESTINO,
            "OBSPED": "",
            "OBSROM": "",
            "NUMPEDCLI": "CONVERSAO_DISPLAY_CAIXA",
            "VLTOTPED": "1,00",
            "CGCDEST": "",
            "NOMEDEST": "",
            "ITENS": [{
                "NUMSEQ": "1",
                "CODPROD": codprod,
                "QTPROD": str(qtde),
                "VLUNIT": "1,00",
                "LOTEFAB": lote
            }]
        }
    }

def gerar_json_entrada(itens):
    # Totalizar quantidades para proporção
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
            "DEV": "0",
            "NUMNF": "000000001",
            "SERIENF": "1",
            "DTEMINF": datetime.now().strftime("%d/%m/%Y"),
            "VLTOTALNF": "1.00",
            "NUMEPEDCLI": "ENTRADA_CONVERSAO",
            "CHAVENF": gerar_chave_nfe(),
            "ITENS": itens_processados
        }
    }

# ===== INTERFACE PRINCIPAL =====
pagina = st.sidebar.radio("📁 Menu", ["Cadastro de Produto", "Importar Produtos (Planilha)", "Conversão de Quantidades", "Executar Conversão com Estoque"])
dados = carregar_dados()

# ===== CADASTRO MANUAL =====
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

# ===== IMPORTAR PRODUTOS XLSX =====
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

# ===== CONVERSÃO MANUAL =====
elif pagina == "Executar Conversão com Estoque":
    st.title("🔁 Conversão por Lote com Estoque")
    relatorio = st.file_uploader("📄 Relatório de Estoque (.xlsx)", type="xlsx")
    planilha_conv = st.file_uploader("📋 Planilha com Conversões (.xlsx)", type="xlsx", help="Colunas: cod_display, lote_saida, quantidade")

    if not relatorio or not planilha_conv:
        st.stop()

    df_estoque = pd.read_excel(relatorio, dtype=str)
    df_estoque["Qt. Disp."] = df_estoque["Qt. Disp."].str.replace(",", ".").astype(float)

    df_conv = pd.read_excel(planilha_conv, dtype=str)
    df_conv["quantidade"] = df_conv["quantidade"].astype(int)

    jsons_saida = []
    jsons_entrada = []
    erros = []

    for idx, row in df_conv.iterrows():
        cod = row["cod_display"].strip().upper()
        lote = row["lote_saida"].strip()
        qtd = int(row["quantidade"])

        produto = next((p for p in dados if cod in [p["cod_caixa"], p["cod_display"]]), None)
        if not produto:
            erros.append(f"Linha {idx+2}: Código {cod} não encontrado.")
            continue

        if df_estoque.query(f"`Cód. Merc.` == '{cod}' and `Lote Fabr.` == '{lote}'").empty:
            erros.append(f"Linha {idx+2}: Lote {lote} para código {cod} não encontrado no estoque.")
            continue

        qtd_disp_cx = produto["qtd_displays_caixa"]
        if cod == produto["cod_display"]:
            cod_saida = cod
            cod_entrada = produto["cod_caixa"]
            total_entrada = qtd // qtd_disp_cx
        else:
            cod_saida = cod
            cod_entrada = produto["cod_display"]
            total_entrada = qtd * qtd_disp_cx

        jsons_saida.append(gerar_json_saida(cod_saida, qtd, lote))
        jsons_entrada.append({
            "NUMSEQ": str(len(jsons_entrada) + 1),
            "CODPROD": cod_entrada,
            "QTPROD": str(total_entrada)
        })

    if erros:
        st.warning("⚠️ Algumas linhas não foram processadas:")
        st.code("\n".join(erros))

    if st.button("Gerar JSONs em Massa") and jsons_saida and jsons_entrada:
        st.subheader("📦 JSONs de Saída")
        for i, js in enumerate(jsons_saida):
            st.code(json.dumps(js, indent=4), language="json")

        st.subheader("📥 JSON Único de Entrada")
        entrada_final = gerar_json_entrada(jsons_entrada)
        st.code(json.dumps(entrada_final, indent=4), language="json")

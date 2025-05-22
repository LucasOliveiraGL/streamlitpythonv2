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

# ===== CONFIG =====
CAMINHO_JSON_LOCAL = Path("embalagens.json")
NOME_ARQUIVO_DRIVE = "embalagens.json"
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CNPJ_DESTINO = "19198834000262"

# ===== GOOGLE DRIVE =====
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

# ===== LOCAIS =====
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

# ===== FUNÇÕES =====
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

def gerar_json_saida(codprod, qtde, vlunit, lote):
    return {
        "CORPEM_ERP_DOC_SAI": {
            "CGCCLIWMS": CNPJ_DESTINO,
            "CGCEMINF": CNPJ_DESTINO,
            "OBSPED": "",
            "OBSROM": "",
            "NUMPEDCLI": "CONVERSAO_DISPLAY_CAIXA",
            "VLTOTPED": str(round(float(qtde) * float(vlunit), 2)),
            "CGCDEST": "",
            "NOMEDEST": "",
            "ITENS": [{
                "NUMSEQ": "1",
                "CODPROD": codprod,
                "QTPROD": str(qtde),
                "VLUNIT": str(vlunit).replace(".", ","),
                "LOTEFAB": lote
            }]
        }
    }

def gerar_json_entrada(itens):
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
            "VLTOTALNF": str(sum([float(i["VLTOTPROD"]) for i in itens])),
            "NUMEPEDCLI": "ENTRADA_CONVERSAO",
            "CHAVENF": gerar_chave_nfe(),
            "ITENS": itens
        }
    }

# ===== INTERFACE =====
pagina = st.sidebar.radio("📁 Menu", ["Cadastro de Produto", "Conversão de Quantidades", "Importar Produtos (Planilha)", "Executar Conversão com Estoque"])
dados = carregar_dados()

# ===== PAG: CADASTRO MANUAL =====
if pagina == "Cadastro de Produto":
    st.title("📦 Cadastro de Produto (Display ↔ Caixa)")
    with st.form("cadastro_produto"):
        produto = st.text_input("Nome do Produto")
        col1, col2 = st.columns(2)
        with col1:
            cod_caixa = st.text_input("Código da Caixa")
        with col2:
            cod_display = st.text_input("Código do Display")
        qtd_display_por_caixa = st.number_input("Displays por Caixa", min_value=1, step=1)

        if st.form_submit_button("Salvar"):
            dados.append({
                "produto": produto,
                "cod_caixa": cod_caixa.upper(),
                "cod_display": cod_display.upper(),
                "qtd_displays_caixa": int(qtd_display_por_caixa)
            })
            salvar_dados(dados)
            st.success("Produto salvo!")
            st.rerun()

# ===== PAG: IMPORTAR PLANILHA =====
elif pagina == "Importar Produtos (Planilha)":
    st.title("📥 Importar Produtos (Excel)")
    arquivo = st.file_uploader("Selecione o arquivo .xlsx", type="xlsx")
    substituir = st.checkbox("❗ Substituir todos os produtos existentes", value=False)

    if arquivo and st.button("Importar"):
        df = pd.read_excel(arquivo, dtype=str)
        obrigatorios = ["produto", "cod_caixa", "qtd_displays_caixa", "cod_display"]
        if not all(col in df.columns for col in obrigatorios):
            st.error("Faltam colunas obrigatórias.")
        else:
            df["qtd_displays_caixa"] = df["qtd_displays_caixa"].astype(int)
            if substituir:
                dados = df.to_dict(orient="records")
            else:
                dados.extend(df.to_dict(orient="records"))
            salvar_dados(dados)
            st.success(f"{len(df)} produtos importados.")

# ===== PAG: CONVERSÃO MANUAL =====
elif pagina == "Conversão de Quantidades":
    st.title("🔁 Conversão de Display ↔ Caixa")
    cod_to_prod = {i["cod_caixa"]: i for i in dados}
    cod_to_prod.update({i["cod_display"]: i for i in dados})

    cod = st.text_input("Código (Display ou Caixa)").upper()
    qtd = st.number_input("Quantidade", step=1, min_value=1)

    if st.button("Converter"):
        prod = cod_to_prod.get(cod)
        if not prod:
            st.error("Código não cadastrado.")
            st.stop()

        qtd_disp_cx = prod["qtd_displays_caixa"]
        if cod == prod["cod_caixa"]:
            st.info(f"{qtd} Caixa(s) = {qtd * qtd_disp_cx} Displays")
        elif cod == prod["cod_display"]:
            cx = qtd // qtd_disp_cx
            sobra = qtd % qtd_disp_cx
            st.info(f"{qtd} Displays = {cx} Caixa(s) + {sobra} Display(s) avulsos")
        else:
            st.warning("Código não reconhecido.")

# ===== PAG: CONVERSÃO COM ESTOQUE =====
elif pagina == "Executar Conversão com Estoque":
    st.title("🚛 Conversão com Controle de Lotes")
    relatorio = st.file_uploader("Envie o relatório de estoque (.xlsx)", type="xlsx")
    if not relatorio:
        st.stop()

    df = pd.read_excel(relatorio, dtype=str)
    df["Qt. Disp."] = df["Qt. Disp."].str.replace(",", ".").astype(float)
    codigos_lote = df[["Cód. Merc.", "Lote Fabr.", "Qt. Disp."]]

    st.markdown("### Conversões")
    cod = st.text_input("Código de Origem (Display)").upper()
    lote = st.text_input("Lote que será utilizado")
    qtd = st.number_input("Quantidade para converter", step=1, min_value=1)

    produto = next((p for p in dados if cod in [p["cod_display"], p["cod_caixa"]]), None)
    if not produto:
        st.warning("Código não encontrado.")
        st.stop()

    lote_ok = codigos_lote.query(f"`Cód. Merc.` == '{cod}' and `Lote Fabr.` == '{lote}'")
    if lote_ok.empty:
        st.error("Lote indisponível ou código incorreto.")
        st.stop()

    if st.button("Gerar JSONs"):
        cod_saida = cod
        cods_entrada = [produto["cod_caixa"] if cod == produto["cod_display"] else produto["cod_display"]]
        qtd_disp_por_cx = produto["qtd_displays_caixa"]

        # Saída
        json_saida = gerar_json_saida(cod_saida, qtd, 1, lote)  # valor fictício 1

        # Entrada
        total_entrada = qtd // qtd_disp_por_cx if cod == produto["cod_display"] else qtd * qtd_disp_por_cx
        json_entrada = gerar_json_entrada([{
            "NUMSEQ": "1",
            "CODPROD": cods_entrada[0],
            "QTPROD": str(total_entrada),
            "VLTOTPROD": str(total_entrada * 1),
            "NUMSEQ_DEV": "1"
        }])

        st.success("JSONs Gerados")
        st.subheader("🔻 JSON de Saída")
        st.code(json.dumps(json_saida, indent=4), language="json")
        st.subheader("🔺 JSON de Entrada")
        st.code(json.dumps(json_entrada, indent=4), language="json")

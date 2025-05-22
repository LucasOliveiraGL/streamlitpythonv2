import streamlit as st
import json
import pandas as pd
from datetime import datetime
import random
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import io
from googleapiclient.http import MediaIoBaseDownload

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

# ===== FUNÇÕES JSON =====
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

# ===== INICIALIZAÇÃO =====
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

dados = carregar_dados()

# ===== PÁGINA DE CONVERSÃO COM ESTOQUE =====
st.title("🔁 Conversão por Lote com Estoque")

relatorio = st.file_uploader("📄 Relatório de Estoque (.xlsx)", type="xlsx")
if not relatorio:
    st.stop()

df_estoque = pd.read_excel(relatorio, dtype=str)
df_estoque["Qt. Disp."] = df_estoque["Qt. Disp."].str.replace(",", ".").astype(float)

st.markdown("### ✏️ Preencha abaixo as conversões")

dados_iniciais = pd.DataFrame([{
    "cod_caixa": "",
    "qtd_cx": 1,
    "lote": "",
    "descricao": "",
    "cod_display": "",
    "qtd_disp": 1
}])

edited = st.data_editor(
    dados_iniciais,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "cod_caixa": st.column_config.TextColumn(label="Código CX"),
        "qtd_cx": st.column_config.NumberColumn(label="Qtd Cx", min_value=1),
        "lote": st.column_config.TextColumn(label="Lote"),
        "descricao": st.column_config.TextColumn(label="Descrição", disabled=True),
        "cod_display": st.column_config.TextColumn(label="Código Display", disabled=True),
        "qtd_disp": st.column_config.NumberColumn(label="Qtd Dis", disabled=True)
    }
)

# Preenchimento automático
for idx in edited.index:
    cod_cx = edited.at[idx, "cod_caixa"].strip().upper()
    produto = next((p for p in dados if cod_cx == p["cod_caixa"]), None)
    if produto:
        edited.at[idx, "cod_display"] = produto["cod_display"]
        edited.at[idx, "descricao"] = produto["produto"]
        edited.at[idx, "qtd_disp"] = int(edited.at[idx, "qtd_cx"]) * int(produto["qtd_displays_caixa"])
    else:
        edited.at[idx, "cod_display"] = ""
        edited.at[idx, "descricao"] = ""
        edited.at[idx, "qtd_disp"] = ""

jsons_saida = []
itens_entrada = []
erros = []

if st.button("Gerar JSONs"):
    for idx, row in edited.iterrows():
        cod_display = row["cod_display"].strip().upper()
        cod_caixa = row["cod_caixa"].strip().upper()
        qtd_disp = int(row["qtd_disp"])
        qtd_cx = int(row["qtd_cx"])
        lote = row["lote"].strip()

        if not cod_display or not cod_caixa or not lote:
            erros.append(f"Linha {idx+1}: Campos obrigatórios ausentes.")
            continue

        if df_estoque.query(f"`Cód. Merc.` == '{cod_display}' and `Lote Fabr.` == '{lote}'").empty:
            erros.append(f"Linha {idx+1}: Lote {lote} não disponível para código {cod_display}.")
            continue

        jsons_saida.append({
            "NUMSEQ": str(len(jsons_saida) + 1),
            "CODPROD": cod_display,
            "QTPROD": str(qtd_disp),
            "VLUNIT": "1,00",
            "LOTEFAB": lote
        })

        itens_entrada.append({
            "NUMSEQ": str(len(itens_entrada) + 1),
            "CODPROD": cod_caixa,
            "QTPROD": str(qtd_cx)
        })

    if erros:
        st.warning("⚠️ Erros encontrados:")
        st.code("\\n".join(erros))

    if jsons_saida and itens_entrada:
        json_saida = {
            "CORPEM_ERP_DOC_SAI": {
                "CGCCLIWMS": CNPJ_DESTINO,
                "CGCEMINF": CNPJ_DESTINO,
                "OBSPED": "",
                "OBSROM": "",
                "NUMPEDCLI": "CONVERSAO_DISPLAY_CAIXA",
                "VLTOTPED": "1,00",
                "CGCDEST": "",
                "NOMEDEST": "",
                "ITENS": jsons_saida
            }
        }

        total_qtd = sum([float(i["QTPROD"]) for i in itens_entrada])
        itens_processados = []
        for i in itens_entrada:
            proporcional = (float(i["QTPROD"]) / total_qtd)
            valor_item = round(proporcional, 4)
            itens_processados.append({
                "NUMSEQ": i["NUMSEQ"],
                "CODPROD": i["CODPROD"],
                "QTPROD": i["QTPROD"],
                "VLTOTPROD": str(valor_item),
                "NUMSEQ_DEV": i["NUMSEQ"]
            })

        json_entrada = {
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

        st.subheader("📦 JSON de Saída")
        st.code(json.dumps(json_saida, indent=4), language="json")

        st.subheader("📥 JSON de Entrada (R$ 1,00 total)")
        st.code(json.dumps(json_entrada, indent=4), language="json")

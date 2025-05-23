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

elif pagina == "Executar Conversão com Estoque":
    st.title("🔁 Conversão por Lote com Estoque")
    relatorio = st.file_uploader("📄 Relatório de Estoque (.xlsx)", type="xlsx")

    if not relatorio:
        st.stop()

    df_estoque = pd.read_excel(relatorio, dtype=str)
    df_estoque.columns = df_estoque.columns.str.strip()
    df_estoque["Qt. Disp."] = df_estoque["Qt. Disp."].str.replace(",", ".").astype(float)

    # Colunas exatas do relatório
    col_merc = "Cod. Merc."
    col_lote = "Lote Fabr."

    if col_merc not in df_estoque.columns or col_lote not in df_estoque.columns:
        st.error("❌ Colunas 'Cod. Merc.' ou 'Lote Fabr.' não encontradas no relatório.")
        st.stop()

    st.markdown("### ✏️ Preencha abaixo as conversões")

    dados_iniciais = pd.DataFrame([{
        "cod_caixa": "",
        "qtd_cx": 1,
        "lote": ""
    }])

    edited = st.data_editor(
        dados_iniciais,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "cod_caixa": st.column_config.TextColumn(label="Código a ser convertido"),
            "qtd_cx": st.column_config.NumberColumn(label="Quant.", min_value=1),
            "lote": st.column_config.TextColumn(label="Lote escolhido")
        }
    )

    resultados_processados = []

    for idx in edited.index:
        raw_cod = edited.at[idx, "cod_caixa"]
        raw_qtd = edited.at[idx, "qtd_cx"]
        raw_lote = edited.at[idx, "lote"]

        if pd.isna(raw_cod):
            cod_cx = ""
        elif isinstance(raw_cod, str):
            cod_cx = raw_cod.strip().upper()
        elif isinstance(raw_cod, (int, float)):
            cod_cx = f"PA-{int(raw_cod)}"
        else:
            cod_cx = str(raw_cod).strip().upper()

        qtd_cx = int(raw_qtd) if pd.notna(raw_qtd) else 0
        lote = str(raw_lote).strip().upper() if pd.notna(raw_lote) else ""

        produto = next((p for p in dados if cod_cx == p["cod_caixa"]), None)
        cod_display = produto["cod_display"] if produto else ""
        descricao = produto["produto"] if produto else ""
        qtd_disp = qtd_cx * int(produto["qtd_displays_caixa"]) if produto else 0

        resultados_processados.append({
            "linha": idx + 1,
            "cod_caixa": cod_cx,
            "cod_display": cod_display,
            "qtd_cx": qtd_cx,
            "qtd_disp": qtd_disp,
            "lote": lote,
            "descricao": descricao
        })

    jsons_saida = []
    itens_entrada = []
    erros = []

    if st.button("Gerar JSONs"):
        df_estoque[col_merc] = df_estoque[col_merc].str.strip().str.upper()
        df_estoque[col_lote] = df_estoque[col_lote].str.strip().str.upper()

        for item in resultados_processados:
            cod_caixa = item["cod_caixa"]
            cod_display = item["cod_display"]
            lote = item["lote"]
            qtd_disp = item["qtd_disp"]
            qtd_cx = item["qtd_cx"]

            if not cod_display or not cod_caixa or not lote:
                erros.append(f"Linha {item['linha']}: Campos obrigatórios ausentes.")
                continue

            filtro = df_estoque[
                (df_estoque[col_merc] == cod_caixa) &
                (df_estoque[col_lote] == lote)
            ]

            if filtro.empty:
                erros.append(f"Linha {item['linha']}: Lote {lote} não disponível para código {cod_caixa}.")
                continue

            # JSON de ENTRADA → quantidade convertida (display)
            itens_entrada.append({
                "NUMSEQ": str(len(itens_entrada) + 1),
                "CODPROD": cod_display,
                "QTPROD": str(qtd_disp)
            })

            # JSON de SAÍDA → quantidade original (caixa)
            jsons_saida.append({
                "NUMSEQ": str(len(jsons_saida) + 1),
                "CODPROD": cod_caixa,
                "QTPROD": str(qtd_cx),
                "VLUNIT": "1,00",
                "LOTEFAB": lote
            })

        if erros:
            st.warning("⚠️ Erros encontrados:")
            st.code("\n".join(erros))

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

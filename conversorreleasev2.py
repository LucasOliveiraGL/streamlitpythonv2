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
        try:
            df = pd.read_excel(arq, dtype=str)
            obrig = ["produto", "cod_caixa", "qtd_displays_caixa", "cod_display"]
            if not all(c in df.columns for c in obrig):
                st.error("❌ Colunas obrigatórias ausentes. Verifique: produto, cod_caixa, qtd_displays_caixa, cod_display")
            else:
                df["qtd_displays_caixa"] = df["qtd_displays_caixa"].astype(int)
                novos = df[obrig].to_dict(orient="records")
                dados = novos if substituir else dados + novos
                salvar_dados(dados)
                st.success(f"✅ {len(novos)} produtos importados com sucesso!")
                st.rerun()
        except Exception as e:
            st.error(f"❌ Erro ao processar o arquivo: {e}")

    if dados:
        st.markdown("### 📋 Produtos Cadastrados")
        df_view = pd.DataFrame(dados)
        df_view.columns = ["Nome", "Código da Caixa", "Displays por Caixa", "Código do Display"]
        st.dataframe(df_view, use_container_width=True)
    else:
        st.info("ℹ️ Nenhum produto cadastrado ainda.")
        

elif pagina == "Executar Conversão com Estoque":
    st.title("🔁 Conversão por Lote com Estoque")
    relatorio = st.file_uploader("📄 Relatório de Estoque (.xlsx)", type="xlsx")

    if not relatorio:
        st.stop()

    df_estoque = pd.read_excel(relatorio, dtype=str)
    df_estoque.columns = df_estoque.columns.str.strip()
    df_estoque["Qt. Disp."] = df_estoque["Qt. Disp."].str.replace(",", ".").astype(float)

    col_merc = "Cód. Merc."
    col_lote = "Lote Fabr."
    numero_pedido = gerar_numped()

    if col_merc not in df_estoque.columns or col_lote not in df_estoque.columns:
        st.error("❌ Colunas 'Cód. Merc.' ou 'Lote Fabr.' não encontradas no relatório.")
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
        hide_index=False,
        column_order=["cod_caixa", "qtd_cx", "lote"],
        column_config={
            "cod_caixa": st.column_config.TextColumn(label="Código a ser convertido"),
            "qtd_cx": st.column_config.NumberColumn(label="Quant.", min_value=1),
            "lote": st.column_config.TextColumn(label="Lote escolhido")
        }
    )
    edited.index.name = "Linha"

    resultados_processados = []
    for idx in edited.index:
        cod_input = edited.at[idx, "cod_caixa"]
        qtd_input = edited.at[idx, "qtd_cx"]
        lote_input = edited.at[idx, "lote"]

        cod_caixa = str(cod_input).strip().upper() if pd.notna(cod_input) else ""
        qtd_cx = int(qtd_input) if pd.notna(qtd_input) else 0
        lote = str(lote_input).strip().upper() if pd.notna(lote_input) else ""

        produto = next((p for p in dados if cod_caixa == p["cod_caixa"]), None)
        cod_display = produto["cod_display"] if produto else ""
        descricao = produto["produto"] if produto else ""
        qtd_disp = qtd_cx * int(produto["qtd_displays_caixa"]) if produto else 0

        resultados_processados.append({
            "linha": idx + 1,
            "cod_caixa": cod_caixa,
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

            itens_entrada.append({
                "NUMSEQ": str(len(itens_entrada) + 1),
                "CODPROD": cod_display,
                "QTPROD": str(qtd_disp)
            })

            jsons_saida.append({
                "NUMSEQ": str(len(jsons_saida) + 1),
                "CODPROD": cod_caixa,
                "QTPROD": str(qtd_cx),
                "VLUNIT": "1,00",
                "LOTFAB": lote
            })

        if erros:
            st.warning("⚠️ Erros encontrados:")
            st.code("\n".join(erros))
        else:
            json_saida = {
                "CORPEM_ERP_DOC_SAI": {
                    "CGCCLIWMS": CNPJ_DESTINO,
                    "CGCEMINF": CNPJ_DESTINO,
                    "OBSPED": "",
                    "OBSROM": "",
                    "NUMPEDCLI": numero_pedido,
                    "VLTOTPED": "1,00",
                    "CGCDEST": "",
                    "NOMEDEST": "",
                    "ITENS": jsons_saida
                }
            }

            total_qtd = sum([float(i["QTPROD"]) for i in itens_entrada])
            itens_processados = []
            for i in itens_entrada:
                proporcional = float(i["QTPROD"]) / total_qtd
                valor_item = round(proporcional, 6)
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
                    "OBSRESDP": "CONVERSÃO/AJUSTE",
                    "TPDESTNF": "",
                    "DEV": "0",
                    "NUMNF": "000000001",
                    "SERIENF": "1",
                    "DTEMINF": datetime.now().strftime("%d/%m/%Y"),
                    "VLTOTALNF": "1.00",
                    "NUMEPEDCLI": numero_pedido,
                    "CHAVENF": gerar_chave_nfe(),
                    "ITENS": itens_processados
                }
            }

            st.session_state["json_saida"] = json_saida
            st.session_state["json_entrada"] = json_entrada

    # EXIBIR RESUMO + BOTÃO DE ENVIO
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
            url = "http://webcorpem.no-ip.info:800/scripts/mh.dll/wc"
            headers = {"Content-Type": "application/json"}
            r1 = requests.post(url, headers=headers, json=json_saida)
            r2 = requests.post(url, headers=headers, json=json_entrada)

            #st.subheader("🔍 Resposta da API")
            #st.code(f"Saída: {r1.status_code} - {r1.text}\nEntrada: {r2.status_code} - {r2.text}")

            if r1.ok and r2.ok:
                st.success("✅ JSONs enviados com sucesso!")

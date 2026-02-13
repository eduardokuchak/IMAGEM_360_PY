import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.features import DivIcon
import math
import requests
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="SIG - Rotas - ITTI", layout="wide", page_icon="🚛")

# Estilo CSS Profissional (Azul ITTI)
st.markdown("""
    <style>
    h1 { color: #1565C0; text-align: center; border-bottom: 2px solid #1565C0; }
    .stButton > button { background-color: #1565C0; color: white; font-weight: bold; border-radius: 8px; width: 100%; }
    .stButton > button:hover { background-color: #0D47A1; color: white; }
    div[data-testid="stFileUploader"] { border: 2px dashed #1565C0; padding: 10px; border-radius: 10px; }
    /* Destaque para a caixa de seleção */
    label[data-testid="stLabel"] { color: #1565C0; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# Inicialização de Variáveis
if 'pontos_raw' not in st.session_state: st.session_state.pontos_raw = None # Pontos originais do KML
if 'pontos_otimizados' not in st.session_state: st.session_state.pontos_otimizados = None # Pontos ordenados
if 'linhas_rota' not in st.session_state: st.session_state.linhas_rota = []
if 'centro_mapa' not in st.session_state: st.session_state.centro_mapa = [-25.42, -49.27]

# --- 2. FUNÇÕES DE OTIMIZAÇÃO (GOOGLE OR-TOOLS) ---

def create_data_model(pontos):
    """Cria a matriz de distâncias para o otimizador"""
    data = {}
    num_pontos = len(pontos)
    dist_matrix = {}
    for i in range(num_pontos):
        dist_matrix[i] = {}
        for j in range(num_pontos):
            if i == j:
                dist_matrix[i][j] = 0
            else:
                p1, p2 = pontos[i], pontos[j]
                # Distância Euclidiana multiplicada para inteiro
                d = math.sqrt((p1['lat'] - p2['lat'])**2 + (p1['lon'] - p2['lon'])**2)
                dist_matrix[i][j] = int(d * 100000) 
    
    data['distance_matrix'] = dist_matrix
    data['num_vehicles'] = 1
    data['depot'] = 0 # Otimizador sempre sai do índice 0 da lista fornecida
    return data

def resolver_tsp_ortools(pontos_entrada):
    """Resolve o problema do Caixeiro Viajante"""
    if len(pontos_entrada) <= 2: return pontos_entrada

    data = create_data_model(pontos_entrada)
    manager = pywrapcp.RoutingIndexManager(len(data['distance_matrix']), data['num_vehicles'], data['depot'])
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data['distance_matrix'][from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
    search_parameters.time_limit.seconds = 2 

    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        index = routing.Start(0)
        nova_ordem = []
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            nova_ordem.append(pontos_entrada[node_index])
            index = solution.Value(routing.NextVar(index))
        return nova_ordem
    else:
        return pontos_entrada

# --- 3. FUNÇÕES AUXILIARES ---

def get_rota_osrm(p1, p2):
    """Pega o traçado real da estrada (Linha Azul)"""
    url = f"http://router.project-osrm.org/route/v1/driving/{p1['lon']},{p1['lat']};{p2['lon']},{p2['lat']}?overview=full&geometries=geojson"
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        if r.status_code == 200:
            coords = r.json()['routes'][0]['geometry']['coordinates']
            return [[c[1], c[0]] for c in coords] 
    except:
        return [[p1['lat'], p1['lon']], [p2['lat'], p2['lon']]]

def gerar_link_google(pontos):
    if not pontos: return ""
    origem = f"{pontos[0]['lat']},{pontos[0]['lon']}"
    destino = f"{pontos[-1]['lat']},{pontos[-1]['lon']}"
    waypoints = "|".join([f"{p['lat']},{p['lon']}" for p in pontos[1:-1][:9]])
    return f"https://www.google.com/maps/dir/?api=1&origin={origem}&destination={destino}&waypoints={waypoints}&travelmode=driving"

# --- 4. FUNÇÕES DE PROCESSAMENTO (CALLBACKS) ---

def carregar_kml():
    """Lê o KML e salva os pontos brutos na memória (sem otimizar ainda)"""
    uploaded_file = st.session_state.file_uploader_key
    if uploaded_file is not None:
        try:
            gpd.io.file.f_engine = "fiona"
            df = gpd.read_file(uploaded_file, driver='KML')
            pontos = []
            for i, row in df.iterrows():
                nome = row.get('Name', f"Ponto {i+1}")
                if row.geometry.geom_type == 'Point':
                    if abs(row.geometry.y) > 0.1:
                        pontos.append({"nome": nome, "lat": row.geometry.y, "lon": row.geometry.x})
            
            if pontos:
                st.session_state.pontos_raw = pontos
                # Define padrão: Otimiza com o primeiro da lista como saída
                executar_otimizacao(pontos[0]['nome'])
        except Exception as e:
            st.error(f"Erro ao ler arquivo: {e}")

def executar_otimizacao(ponto_partida_nome=None):
    """Reordena a lista com base no ponto de partida escolhido e calcula rotas"""
    if not st.session_state.pontos_raw: return

    # 1. Prepara a lista: Coloca o ponto escolhido como o primeiro (Depot)
    lista_base = st.session_state.pontos_raw.copy()
    
    if ponto_partida_nome:
        # Acha o ponto e move para o topo
        start_node = next((p for p in lista_base if p['nome'] == ponto_partida_nome), lista_base[0])
        lista_base.remove(start_node)
        lista_base.insert(0, start_node)
    
    # 2. Roda a IA do Google (OR-Tools)
    rota_final = resolver_tsp_ortools(lista_base)
    
    # 3. Baixa as linhas das ruas (OSRM)
    linhas = []
    # Calculamos apenas se a lista foi atualizada para evitar chamadas excessivas
    # Mas como é local, rodamos direto
    for i in range(len(rota_final) - 1):
        caminho = get_rota_osrm(rota_final[i], rota_final[i+1])
        if caminho: linhas.append(caminho)

    # 4. Atualiza Estado Final
    st.session_state.pontos_otimizados = rota_final
    st.session_state.linhas_rota = linhas
    st.session_state.centro_mapa = [rota_final[0]['lat'], rota_final[0]['lon']]

# --- 5. INTERFACE DO USUÁRIO ---

st.title("SIG - Rotas - ITTI CARTO")

# Sidebar
st.sidebar.markdown("### 📂 Entrada de Dados")
st.sidebar.file_uploader(
    "Carregar KML:", 
    type=['kml'], 
    key='file_uploader_key', 
    on_change=carregar_kml # Ao carregar, já roda tudo com o primeiro ponto
)

# Se já carregou o KML, mostra a caixa de seleção
if st.session_state.pontos_raw:
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚙️ Configuração")
    
    # Lista de nomes para o selectbox
    opcoes = [p['nome'] for p in st.session_state.pontos_raw]
    
    # O selectbox dispara a otimização assim que muda (on_change)
    start_point = st.sidebar.selectbox(
        "🚩 Ponto de Partida:", 
        options=opcoes,
        index=0, # Padrão: primeiro da lista
        key='selectbox_start',
        on_change=lambda: executar_otimizacao(st.session_state.selectbox_start)
    )
    
    st.sidebar.success(f"✅ Rota calculada saindo de:\n**{start_point}**")

    # Links
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔗 Google Maps")
    pts = st.session_state.pontos_otimizados
    if pts:
        for i in range(0, len(pts)-1, 10):
            chunk = pts[i : i+11]
            link = gerar_link_google(chunk)
            if len(chunk) > 1:
                st.sidebar.markdown(f"🗺️ [**Rota {i+1} a {min(i+11, len(pts))}**]({link})")

    if st.sidebar.button("🗑️ Limpar Tudo"):
        st.session_state.clear()
        st.rerun()

# --- 6. RENDERIZAÇÃO DO MAPA ---
if st.session_state.centro_mapa:
    m = folium.Map(
        location=st.session_state.centro_mapa, 
        zoom_start=11, 
        tiles="CartoDB positron"
    )

    # Desenha Pontos Otimizados
    if st.session_state.pontos_otimizados:
        for i, p in enumerate(st.session_state.pontos_otimizados):
            cor_bg = '#1565C0' # Azul ITTI
            if i == 0: cor_bg = '#2E7D32' # Verde (Início)
            if i == len(st.session_state.pontos_otimizados)-1: cor_bg = '#C62828' # Vermelho (Fim)

            folium.map.Marker(
                [p['lat'], p['lon']],
                icon=DivIcon(
                    icon_size=(30,30), icon_anchor=(15,15),
                    html=f'''<div style="
                        background-color: {cor_bg}; color: white; border-radius: 50%; 
                        width: 30px; height: 30px; display: flex; justify-content: center; 
                        align-items: center; font-weight: bold; border: 2px solid white; 
                        box-shadow: 0 2px 5px rgba(0,0,0,0.3); font-family: sans-serif;">
                        {i+1}
                    </div>'''
                ),
                popup=f"<b>{i+1}. {p['nome']}</b>"
            ).add_to(m)

    # Desenha Linhas
    if st.session_state.linhas_rota:
        for linha in st.session_state.linhas_rota:
            folium.PolyLine(linha, color='#1565C0', weight=4, opacity=0.8).add_to(m)

    st_folium(m, width=1400, height=700)
else:
    st.info("👈 Faça upload de um KML para começar.")
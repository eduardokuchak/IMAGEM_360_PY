import streamlit as st
import osmnx as ox
import networkx as nx
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.features import DivIcon
import math

# 1. CONFIGURAÇÃO DA PÁGINA E ESTADOS
st.set_page_config(page_title="Roteirizador Logístico Profissional", layout="wide")

if 'pontos_geometria' not in st.session_state:
    st.session_state.pontos_geometria = None
if 'linhas_rota' not in st.session_state:
    st.session_state.linhas_rota = []
if 'centro_mapa' not in st.session_state:
    st.session_state.centro_mapa = [-25.42, -49.27]

# Dicionário de mapas global
tiles_map = {
    "OpenStreetMap": "openstreetmap",
    "Google Satélite": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
}

st.title("📍 Roteirização: Ordem por Eficiência Logística")

# 2. FUNÇÕES AUXILIARES
def calc_dist(p1, p2):
    """Cálculo simples de distância para ordenação vizinho mais próximo"""
    return math.sqrt((p1['lat'] - p2['lat'])**2 + (p1['lon'] - p2['lon'])**2)

def gerar_link_google_maps(pontos):
    """Gera link para Google Maps (Limite de 11 pontos por link do Google)"""
    if not pontos: return ""
    origem = f"{pontos[0]['lat']},{pontos[0]['lon']}"
    destino = f"{pontos[-1]['lat']},{pontos[-1]['lon']}"
    intermediarios = pontos[1:-1]
    waypoint_str = ""
    if intermediarios:
        coords_inter = [f"{p['lat']},{p['lon']}" for p in intermediarios[:9]]
        waypoint_str = "&waypoints=" + "|".join(coords_inter)
    return f"https://www.google.com/maps/dir/?api=1&origin={origem}&destination={destino}{waypoint_str}&travelmode=driving"

# 3. BARRA LATERAL - ENTRADA DE DADOS
st.sidebar.header("1. Entrada de Dados")
uploaded_file = st.sidebar.file_uploader("Fazer upload do arquivo KML", type=['kml'])
mapa_base = st.sidebar.selectbox("Plano de Fundo", list(tiles_map.keys()))

if uploaded_file is not None:
    try:
        gpd.io.file.f_engine = "fiona"
        df = gpd.read_file(uploaded_file, driver='KML')
        pontos = []
        for i, row in df.iterrows():
            nome_ponto = row.get('Name', f"Ponto {i+1}")
            pontos.append({"nome": nome_ponto, "lat": row.geometry.y, "lon": row.geometry.x})
        
        if st.session_state.pontos_geometria is None:
            st.session_state.pontos_geometria = pontos
            st.session_state.centro_mapa = [pontos[0]['lat'], pontos[0]['lon']]
    except Exception as e:
        st.error(f"Erro ao ler o arquivo KML: {e}")

# 4. CONFIGURAÇÃO DO TRAJETO E OTIMIZAÇÃO (TSP + BBOX)
if st.session_state.pontos_geometria:
    st.sidebar.header("2. Configuração do Trajeto")
    
    lista_nomes = [p['nome'] for p in st.session_state.pontos_geometria]
    ponto_saida_nome = st.sidebar.selectbox("Ponto de Saída:", lista_nomes)
    
    modo_transporte = st.sidebar.selectbox(
        "Modo de Transporte", 
        ["drive", "walk", "bike"], 
        format_func=lambda x: {"drive": "Carro/Caminhão", "walk": "Caminhada", "bike": "Bicicleta"}[x]
    )
    
    if st.sidebar.button("Calcular Rota Mais Eficiente"):
        with st.spinner('Baixando mapa da região e otimizando...'):
            # --- OTIMIZAÇÃO DA SEQUÊNCIA (Vizinho Mais Próximo) ---
            nao_visitados = st.session_state.pontos_geometria.copy()
            partida = next(p for p in nao_visitados if p['nome'] == ponto_saida_nome)
            nao_visitados.remove(partida)
            
            rota_ordenada = [partida]
            while nao_visitados:
                atual = rota_ordenada[-1]
                proximo = min(nao_visitados, key=lambda p: calc_dist(atual, p))
                rota_ordenada.append(proximo)
                nao_visitados.remove(proximo)
            
            # Atualiza pontos para a nova ordem logística (muda os números no mapa)
            st.session_state.pontos_geometria = rota_ordenada

            # --- DOWNLOAD DO MAPA PELA ÁREA TOTAL (BBOX) ---
            lats = [p['lat'] for p in rota_ordenada]
            lons = [p['lon'] for p in rota_ordenada]
            
            # Margem de segurança de ~500 metros (0.005 graus)
            try:
                G = ox.graph_from_bbox(
                    bbox=(max(lats) + 0.005, min(lats) - 0.005, max(lons) + 0.005, min(lons) - 0.005),
                    network_type=modo_transporte
                )
                G = ox.utils_graph.get_largest_component(G, strongly=True)
                
                novas_linhas = []
                for i in range(len(rota_ordenada) - 1):
                    n1 = ox.distance.nearest_nodes(G, rota_ordenada[i]['lon'], rota_ordenada[i]['lat'])
                    n2 = ox.distance.nearest_nodes(G, rota_ordenada[i+1]['lon'], rota_ordenada[i+1]['lat'])
                    try:
                        caminho_indices = nx.shortest_path(G, n1, n2, weight='length')
                        geometria_rua = [(G.nodes[node]['y'], G.nodes[node]['x']) for node in caminho_indices]
                        novas_linhas.append(geometria_rua)
                    except:
                        st.sidebar.warning(f"Sem conexão entre {i+1} e {i+2}")
                        continue
                
                st.session_state.linhas_rota = novas_linhas
                st.session_state.centro_mapa = [rota_ordenada[0]['lat'], rota_ordenada[0]['lon']]
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao baixar mapa da região: {e}")

# 5. EXPORTAÇÃO E LINKS
if st.session_state.linhas_rota:
    st.sidebar.header("3. Exportar Rota")
    total_pts = len(st.session_state.pontos_geometria)
    
    if total_pts <= 11:
        link = gerar_link_google_maps(st.session_state.pontos_geometria)
        st.sidebar.markdown(f'[↗️ Abrir Rota no Google Maps]({link})')
    else:
        # Divide em partes se exceder 11 pontos (limite do link do Google)
        st.sidebar.info(f"Rota com {total_pts} pontos. Links divididos:")
        for i in range(0, total_pts - 1, 10):
            sub_rota = st.session_state.pontos_geometria[i : i + 11]
            if len(sub_rota) > 1:
                link = gerar_link_google_maps(sub_rota)
                st.sidebar.markdown(f'[📍 Parte {(i//10)+1} (Pontos {i+1}-{min(i+11, total_pts)})]({link})')

# 6. RENDERIZAÇÃO DO MAPA
m = folium.Map(location=st.session_state.centro_mapa, zoom_start=14, 
               tiles=tiles_map[mapa_base], attr="Dados do Mapa")

if st.session_state.pontos_geometria:
    pts = st.session_state.pontos_geometria
    for i, p in enumerate(pts):
        cor = 'green' if i == 0 else ('red' if i == len(pts)-1 else 'blue')
        
        folium.Marker(
            [p['lat'], p['lon']], 
            popup=f"Ponto {i+1}: {p['nome']}",
            icon=folium.Icon(color=cor, icon='info-sign')
        ).add_to(m)
        
        # O Número agora segue estritamente a ordem eficiente calculada
        folium.map.Marker(
            [p['lat'], p['lon']],
            icon=DivIcon(
                icon_size=(150,36), icon_anchor=(7,20),
                html=f'''<div style="font-size: 11pt; color: white; background-color: black; 
                        border-radius: 50%; width: 24px; height: 24px; display: flex; 
                        justify-content: center; align-items: center; border: 2px solid white; 
                        font-weight: bold;">{i+1}</div>'''
            )
        ).add_to(m)

if st.session_state.linhas_rota:
    for trecho in st.session_state.linhas_rota:
        folium.PolyLine(trecho, color='red', weight=5, opacity=0.8).add_to(m)

st_folium(m, width=1200, height=600, key="mapa_final_corrigido")

if st.sidebar.button("Limpar Tudo"):
    st.session_state.pontos_geometria = None
    st.session_state.linhas_rota = []
    st.rerun()
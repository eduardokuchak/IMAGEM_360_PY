import http.server
import socketserver
import os
import webbrowser
import threading
import time

# --- CONFIGURAÇÃO DO SERVIDOR ---
PORT = 8000

# Garante que o diretório de trabalho seja a pasta onde este script está salvo.
# Isso é crucial para que, se você tiver arquivos locais (imagens), o servidor os encontre.
try:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
except:
    os.chdir(os.getcwd())

# --- CONTEÚDO DO FRONTEND (HTML/CSS/JS) ---
# Armazenamos o site inteiro dentro desta variável string para que o script seja
# um arquivo único (.py) fácil de transportar, sem precisar de uma pasta separada.
HTML_CONTENT = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Engenharia 360 - ITTI (Com Área m²)</title>
    
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.css"/>
    <script type="text/javascript" src="https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.js"></script>

    <style>
        /* Reset básico e tipografia */
        body, html { margin: 0; padding: 0; height: 100%; font-family: 'Segoe UI', sans-serif; background: #111; color: white; overflow: hidden; }
        
        /* CAMADA 1: O Visualizador 360 (Fica no fundo, z-index: 1) */
        #panorama { width: 100%; height: 100vh; position: absolute; top:0; left:0; z-index: 1; }
        
        /* CAMADA 2: O Canvas de Desenho (Fica transparente por cima, z-index: 2) 
           É aqui que desenhamos as linhas e polígonos verdes/azuis. */
        #drawing-layer { position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 2; pointer-events: none; }
        
        /* Cursor em formato de mira quando estiver medindo */
        #panorama.measuring { cursor: crosshair !important; }

        /* --- UI: BARRA SUPERIOR --- */
        #top-bar {
            position: absolute; top: 0; left: 0; width: 100%; height: 60px;
            background: rgba(0, 0, 0, 0.9); display: flex; align-items: center;
            padding: 0 20px; box-sizing: border-box; z-index: 100;
            border-bottom: 1px solid #444; justify-content: space-between;
        }

        .title { font-weight: bold; color: #3498db; font-size: 18px; margin-right: 20px; }
        .btn-container { display: flex; gap: 10px; align-items: center; }
        
        /* Estilos dos Botões */
        button {
            padding: 8px 15px; border: none; border-radius: 4px; 
            font-weight: bold; cursor: pointer; font-size: 13px; transition: 0.2s;
            color: white;
        }
        
        .btn-load { background: #444; border: 1px solid #666; }
        
        /* Botões de Modo (Régua, Área, Altura) */
        .btn-mode { background: #333; border: 1px solid #555; color: #aaa; }
        
        /* Classes ativas para mudar a cor do botão quando selecionado */
        .btn-mode.active-poly { background: #27ae60; color: white; border-color: #2ecc71; } /* Verde */
        .btn-mode.active-area { background: #3498db; color: white; border-color: #2980b9; } /* Azul */
        .btn-mode.active-vert { background: #8e44ad; color: white; border-color: #9b59b6; } /* Roxo */
        
        .btn-undo { background: #c0392b; opacity: 0.5; cursor: not-allowed; }
        .btn-undo.active { opacity: 1; cursor: pointer; }

        /* --- UI: PAINEL DE RESULTADOS (Canto inferior direito) --- */
        #result-panel {
            position: absolute; bottom: 30px; right: 30px;
            background: rgba(0,0,0,0.9); padding: 20px; border-radius: 8px;
            border-left: 4px solid #3498db; 
            text-align: right; z-index: 90;
            min-width: 250px;
        }
        .res-big { font-size: 32px; color: #3498db; font-weight: bold; }
        .res-small { font-size: 14px; color: #aaa; margin-top: 5px; }
        
        /* Hotspots: As bolinhas que aparecem onde clicamos */
        .custom-hotspot {
            background-color: #3498db; width: 12px; height: 12px;
            border-radius: 50%; border: 2px solid white; box-shadow: 0 0 4px black;
        }
        .hotspot-poly { background-color: #2ecc71 !important; }
        .hotspot-area { background-color: #3498db !important; }
        .hotspot-vert { background-color: #8e44ad !important; border-color: #fff !important; }
    </style>
</head>
<body>

    <div id="top-bar">
        <div><div class="title">ITTI | Distância 360°</div></div>
        <div class="btn-container">
            <button class="btn-load" onclick="document.getElementById('fileInput').click()">📂 ABRIR</button>
            
            <div style="width:1px; height:20px; background:#444; margin:0 5px;"></div>
            
            <button id="btn-poly" class="btn-mode" onclick="setMode('polyline')">📏 SOLO</button>
            <button id="btn-area" class="btn-mode" onclick="setMode('polygon')">📐 ÁREA</button> 
            <button id="btn-vert" class="btn-mode" onclick="setMode('vertical')">🏢 ALTURA</button>
            
            <button id="btn-undo" class="btn-undo" onclick="undoLastPoint()">↩</button>
        </div>
        <input type="file" id="fileInput" accept="image/*" style="display: none;">
    </div>

    <canvas id="drawing-layer"></canvas>

    <div id="result-panel">
        <div class="res-label" id="res-label">RESULTADO</div>
        <div id="main-result" class="res-big">0.00 m</div>
        <div style="height:1px; background:#444; margin: 10px 0;"></div>
        <div id="secondary-info" class="res-small">Pronto</div>
        <div id="flight-info" style="color:#27ae60; font-size:12px; margin-top:10px;">H Voo: 10.0m</div>
        <div style="color:#f39c12; font-size:11px; margin-top:2px;">Corr. Horizonte: -1.80°</div>
    </div>

    <div id="panorama"></div>

    <script>
        // --- CONSTANTES E VARIÁVEIS GLOBAIS ---
        const MAX_TEXTURE_SIZE = 4096; // Limite seguro de textura para WebGL (celulares/PCs fracos)
        let viewer = null;             // Instância do Pannellum
        let canvas, ctx;               // Referências para o Canvas de desenho
        
        // --- PARÂMETROS DE CALIBRAÇÃO ---
        let droneHeight = 10.0;        // Altura do drone (metros) - Fundamental para calcular distâncias
        let pitchOffset = -1.80;       // Correção do horizonte (se a câmera não estava perfeitamente reta)
        
        // --- ESTADO DA APLICAÇÃO ---
        let appMode = 'idle';          // Modos: 'idle' (nada), 'polyline' (dist), 'polygon' (área), 'vertical'
        let points = [];               // Lista de pontos clicados {pitch, yaw, x, y, id}
        let isScrolling = false;       // Controle para evitar clique enquanto dá zoom/scroll
        let scrollTimeout = null;
        
        // --- INICIALIZAÇÃO ---
        window.onload = function() {
            canvas = document.getElementById('drawing-layer');
            ctx = canvas.getContext('2d');
            
            // Ajusta o tamanho do canvas para tela cheia
            resizeCanvas();
            window.addEventListener('resize', resizeCanvas);
            
            // "Game Loop": Redesenha as linhas sobre a imagem 30 vezes por segundo (33ms)
            // Isso é necessário porque quando giramos a câmera 360, as linhas precisam acompanhar.
            setInterval(drawOverlay, 33);
        };

        function resizeCanvas() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        }

        // --- CARREGAMENTO DE ARQUIVO ---
        document.getElementById('fileInput').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (!file) return;
            
            // Tenta ler a altura do nome do arquivo (ex: "DJI_001 120m.jpg")
            detectHeightFromFileName(file.name);
            
            const img = new Image();
            const url = URL.createObjectURL(file);
            
            img.onload = function() {
                // Se a imagem for gigante (>4k), redimensiona para não travar o navegador
                if (img.width > MAX_TEXTURE_SIZE) resizeAndLoad(img);
                else loadViewer(url);
            };
            img.src = url;
        });

        // Função Inteligente: Procura "120m", "50.5m" no nome do arquivo
        function detectHeightFromFileName(filename) {
            const regex = /([0-9]+[.,]?[0-9]*)\s*[mM](?![a-zA-Z])/;
            const match = filename.match(regex);
            if (match) {
                const val = parseFloat(match[1].replace(',', '.'));
                if (val > 0) {
                    droneHeight = val;
                    document.getElementById('flight-info').innerText = `H Voo: ${droneHeight.toFixed(2)}m (Detectado)`;
                    document.getElementById('flight-info').style.color = '#3498db'; 
                    return;
                }
            }
            // Se não achar, usa padrão
            droneHeight = 10.0;
            document.getElementById('flight-info').innerText = "H Voo: 10.0m (Padrão)";
            document.getElementById('flight-info').style.color = '#e74c3c'; 
        }

        // Redimensiona imagem usando um Canvas temporário na memória
        function resizeAndLoad(img) {
            const canvasTmp = document.createElement('canvas');
            const scale = MAX_TEXTURE_SIZE / img.width;
            canvasTmp.width = MAX_TEXTURE_SIZE;
            canvasTmp.height = img.height * scale;
            const ctxTmp = canvasTmp.getContext('2d');
            ctxTmp.drawImage(img, 0, 0, canvasTmp.width, canvasTmp.height);
            canvasTmp.toBlob(b => loadViewer(URL.createObjectURL(b)), 'image/jpeg', 0.95);
        }

        // Inicia o Pannellum (Biblioteca 360)
        function loadViewer(url) {
            if (viewer) { try { viewer.destroy(); } catch(e){} }
            viewer = pannellum.viewer('panorama', {
                "type": "equirectangular", 
                "panorama": url,
                "autoLoad": true, 
                "compass": true,
                "pitch": -20, // Começa olhando levemente para baixo
                "mouseZoom": false // Desabilita zoom nativo para não conflitar com scroll customizado
            });
            
            // Adiciona evento de clique NA IMAGEM 360
            viewer.on('load', () => {
                document.getElementById('panorama').addEventListener('mousedown', onPanoramaClick);
            });
            setupScrollRotation();
        }

        // Permite girar a câmera usando a roda do mouse (Scroll) em vez de zoom
        function setupScrollRotation() {
            const panDiv = document.getElementById('panorama');
            panDiv.onwheel = null; 
            panDiv.addEventListener('wheel', function(e) {
                if (!viewer) return;
                e.preventDefault(); 
                isScrolling = true;
                
                // Debounce para saber quando parou de rolar
                if (scrollTimeout) clearTimeout(scrollTimeout);
                scrollTimeout = setTimeout(() => { isScrolling = false; }, 300);
                
                const sensitivity = 0.05; 
                let newYaw = viewer.getYaw() + (e.deltaY * sensitivity);
                viewer.setYaw(newYaw);
            }, { passive: false });
        }

        // --- RENDERIZAÇÃO (DRAW LOOP) ---
        // Esta função roda ~30x por segundo
        function drawOverlay() {
            // 1. Limpa o canvas (apaga o desenho anterior)
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            if (!viewer || points.length < 2) return;
            if (appMode !== 'polyline' && appMode !== 'vertical' && appMode !== 'polygon') return;

            ctx.beginPath();
            ctx.lineWidth = 3;
            
            // 2. Define cores baseado no modo
            if (appMode === 'polygon') {
                ctx.strokeStyle = '#3498db'; // Azul
                ctx.fillStyle = 'rgba(52, 152, 219, 0.3)'; 
            } else if (appMode === 'vertical') {
                ctx.strokeStyle = '#8e44ad'; // Roxo
            } else {
                ctx.strokeStyle = '#2ecc71'; // Verde
            }

            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';

            // 3. Converte coordenadas 3D (Pitch/Yaw) para 2D (X/Y da tela)
            for (let i = 0; i < points.length; i++) {
                // pitchYawToCoords é uma função do Pannellum que diz onde um ponto esférico está na tela agora
                const screenPos = viewer.pitchYawToCoords(points[i].pitch, points[i].yaw);
                
                // Hack: Se o ponto está "atrás" da câmera, o valor vem maluco. Ignoramos.
                if (screenPos.x < -1000 || screenPos.x > canvas.width + 1000) continue;

                if (i === 0) ctx.moveTo(screenPos.x, screenPos.y);
                else ctx.lineTo(screenPos.x, screenPos.y);
            }

            // 4. Se for Área, fecha o polígono e preenche
            if (appMode === 'polygon' && points.length > 2) {
                ctx.closePath();
                ctx.fill(); 
            }
            
            // 5. Desenha a borda
            ctx.stroke();
        }

        // --- EVENTOS DE INTERAÇÃO ---
        function onPanoramaClick(e) {
            if (e.button !== 0) return; // Só aceita botão esquerdo
            if (appMode === 'idle') return; // Se não escolheu ferramenta, não faz nada
            if (e.ctrlKey || e.shiftKey) return;
            if (isScrolling) return; // Não clica se estiver girando a câmera

            // Pega onde clicou na tela e converte para Pitch/Yaw (Latitude/Longitude da esfera)
            const coords = viewer.mouseEventToCoords(e);
            addPoint(coords[0], coords[1]);
        }

        function addPoint(pitch, yaw) {
            let projected = {x:0, y:0};
            
            // MÁGICA MATEMÁTICA:
            // Converte ângulos (Pitch/Yaw) + Altura do Drone em metros no chão (X/Y)
            if (appMode === 'vertical' && points.length === 1) {
                // O segundo ponto da medição vertical não é projetado no chão
                projected = {x:0, y:0}; 
            } else {
                projected = projectToPlane(pitch, yaw, droneHeight);
            }

            // Cria um ID único para o ponto
            const spotId = 'pt-' + Date.now();
            let cssClass = "custom-hotspot";
            
            // Define cor do hotspot (bolinha)
            if (appMode === 'vertical') cssClass += " hotspot-vert"; 
            else if (appMode === 'polygon') cssClass += " hotspot-area";
            else cssClass += " hotspot-poly"; 

            // Adiciona a "bolinha" visual no Pannellum
            viewer.addHotSpot({ "id": spotId, "pitch": pitch, "yaw": yaw, "cssClass": cssClass });
            
            // Salva o ponto na memória com suas coordenadas projetadas (metros)
            points.push({ pitch, yaw, x: projected.x, y: projected.y, id: spotId });

            // Executa os cálculos matemáticos dependendo do modo
            if (appMode === 'polyline') calculatePolyline();
            else if (appMode === 'polygon') calculatePolygonArea();
            else if (appMode === 'vertical' && points.length === 2) {
                calculateVertical();
                // Pequeno delay para UX
                setTimeout(() => {
                    if(confirm("Medição Concluída. Fazer outra?")) resetPointsOnly();
                    else setMode('idle');
                }, 500); 
            }
            updateUI();
        }

        // --- CÁLCULO DE ÁREA (Algoritmo "Shoelace") ---
        function calculatePolygonArea() {
            if (points.length < 3) {
                document.getElementById('main-result').innerText = "0.00 m²";
                document.getElementById('secondary-info').innerText = "Marque 3+ pontos...";
                return;
            }
            
            // Fórmula Shoelace para calcular área de polígono irregular simples
            let area = 0;
            const n = points.length;
            
            for (let i = 0; i < n; i++) {
                const j = (i + 1) % n; 
                area += points[i].x * points[j].y;
                area -= points[j].x * points[i].y;
            }
            
            area = Math.abs(area) / 2.0;
            
            document.getElementById('main-result').innerText = area.toFixed(2) + " m²";
            document.getElementById('secondary-info').innerText = "Área Total (Plana)";
        }

        // --- CORAÇÃO MATEMÁTICO: Projeção Esférica para Plana ---
        function projectToPlane(pitchDeg, yawDeg, height) {
            const toRad = d => d * Math.PI / 180;
            
            // Aplica correção do horizonte (pitchOffset)
            const correctedPitch = pitchDeg + pitchOffset; 
            const pitch = toRad(correctedPitch);
            const yaw = toRad(yawDeg);
            
            // Theta é o ângulo em relação ao Nadir (baixo)
            const theta = (Math.PI / 2) + pitch; 
            
            // Evita divisão por zero ou projeção infinita no horizonte
            if (theta >= Math.PI/2 - 0.01) {
                 return { x: 99999 * Math.sin(yaw), y: 99999 * Math.cos(yaw) };
            }
            
            // Trigonometria básica: Raio = Altura * tan(theta)
            const r = height * Math.tan(theta);
            
            // Converte polar para cartesiano (X, Y)
            return { x: r * Math.sin(yaw), y: r * Math.cos(yaw) };
        }

        // --- CÁLCULO DE DISTÂNCIA (Soma de segmentos) ---
        function calculatePolyline() {
            if (points.length < 2) {
                document.getElementById('main-result').innerText = "0.00 m";
                document.getElementById('secondary-info').innerText = "Comece a clicar...";
                return;
            }
            let accDist = 0;
            // Percorre os pontos somando a distância euclidiana entre eles
            for (let i = 0; i < points.length - 1; i++) {
                const dx = points[i+1].x - points[i].x;
                const dy = points[i+1].y - points[i].y;
                accDist += Math.sqrt(dx*dx + dy*dy);
            }
            document.getElementById('main-result').innerText = accDist.toFixed(2) + " m";
            document.getElementById('secondary-info').innerText = "Distância Total (Solo)";
        }

        // --- CÁLCULO DE ALTURA VERTICAL (Objeto em pé) ---
        function calculateVertical() {
            const base = points[0]; // Ponto no chão
            const top = points[1];  // Ponto no topo do objeto
            const toRad = d => d * Math.PI / 180;
            
            // 1. Calcula a distância horizontal do drone até a base do objeto
            const thetaBase = (Math.PI / 2) + toRad(base.pitch + pitchOffset);
            const distToWall = droneHeight * Math.tan(thetaBase);
            
            // 2. Usa essa distância para calcular a altura do ponto do topo
            const thetaTop = toRad(top.pitch + pitchOffset);
            
            // Fórmula: H_drone + (Distancia * tan(angulo_topo))
            const objectHeight = droneHeight + (distToWall * Math.tan(thetaTop));
            
            document.getElementById('main-result').innerText = Math.abs(objectHeight).toFixed(2) + " m";
            document.getElementById('secondary-info').innerText = "Altura Vertical Estimada";
        }

        // --- CONTROLE DE MODO (Troca de Ferramentas) ---
        function setMode(newMode) {
            appMode = newMode;
            resetPointsOnly(); // Limpa medição anterior ao trocar ferramenta
            
            // Adiciona cursor de mira
            document.getElementById('panorama').classList.remove('measuring');
            
            // Reseta estilo dos botões
            document.getElementById('btn-poly').className = "btn-mode";
            document.getElementById('btn-area').className = "btn-mode";
            document.getElementById('btn-vert').className = "btn-mode";
            
            // Ativa o botão selecionado e muda o texto da label
            if (newMode === 'polyline') {
                document.getElementById('panorama').classList.add('measuring');
                document.getElementById('btn-poly').className = "btn-mode active-poly";
                document.getElementById('res-label').innerText = "DISTÂNCIA DE SOLO";
            } 
            else if (newMode === 'polygon') {
                document.getElementById('panorama').classList.add('measuring');
                document.getElementById('btn-area').className = "btn-mode active-area";
                document.getElementById('res-label').innerText = "ÁREA (SOLO)";
            }
            else if (newMode === 'vertical') {
                document.getElementById('panorama').classList.add('measuring');
                document.getElementById('btn-vert').className = "btn-mode active-vert";
                document.getElementById('res-label').innerText = "ALTURA VERTICAL";
            }
        }

        // --- UNDO (Desfazer último ponto) ---
        function undoLastPoint() {
            if (points.length === 0) return;
            const last = points.pop(); // Remove do array
            viewer.removeHotSpot(last.id); // Remove do visualizador
            
            // Recalcula o resultado sem aquele ponto
            if (appMode === 'polyline') calculatePolyline();
            else if (appMode === 'polygon') calculatePolygonArea();
            
            updateUI();
        }

        // Limpa tudo (Reset)
        function resetPointsOnly() {
            points.forEach(p => viewer.removeHotSpot(p.id));
            points = [];
            ctx.clearRect(0, 0, canvas.width, canvas.height); 
            
            if (appMode === 'polygon') document.getElementById('main-result').innerText = "0.00 m²";
            else document.getElementById('main-result').innerText = "0.00 m";
            
            document.getElementById('secondary-info').innerText = "Aguardando pontos...";
            updateUI();
        }

        function updateUI() {
            // Ativa ou desativa o botão de Desfazer
            const btnUndo = document.getElementById('btn-undo');
            btnUndo.className = points.length > 0 ? "btn-undo active" : "btn-undo";
        }
    </script>
</body>
</html>"""

# --- INICIALIZAÇÃO DO SERVIDOR PYTHON ---

# Handler customizado: Intercepta qualquer requisição GET
# e serve o conteúdo da variável HTML_CONTENT em vez de procurar um arquivo index.html
class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
        else:
            # Se a requisição não for "/", tenta servir arquivos da pasta (ex: imagens locais)
            super().do_GET()

# Bloco Principal de Execução
if __name__ == "__main__":
    # Função para abrir o navegador automaticamente após 1 segundo
    def open_browser():
        time.sleep(1)
        webbrowser.open(f"http://localhost:{PORT}")
    
    # Inicia a thread do navegador
    threading.Thread(target=open_browser).start()
    
    # Inicia o servidor HTTP
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Servidor ITTI Azul rodando: http://localhost:{PORT}")
        try: 
            httpd.serve_forever() # Mantém o servidor rodando até fechar a janela
        except: 
            pass
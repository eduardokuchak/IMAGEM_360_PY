import http.server
import socketserver
import os
import webbrowser
import threading
import time

PORT = 8000

try:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
except:
    os.chdir(os.getcwd())

HTML_CONTENT = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Engenharia 360 - ITTI (Com Área m²)</title>
    
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.css"/>
    <script type="text/javascript" src="https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.js"></script>

    <style>
        body, html { margin: 0; padding: 0; height: 100%; font-family: 'Segoe UI', sans-serif; background: #111; color: white; overflow: hidden; }
        
        #panorama { width: 100%; height: 100vh; position: absolute; top:0; left:0; z-index: 1; }
        #drawing-layer { position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 2; pointer-events: none; }
        
        #panorama.measuring { cursor: crosshair !important; }

        #top-bar {
            position: absolute; top: 0; left: 0; width: 100%; height: 60px;
            background: rgba(0, 0, 0, 0.9); display: flex; align-items: center;
            padding: 0 20px; box-sizing: border-box; z-index: 100;
            border-bottom: 1px solid #444; justify-content: space-between;
        }

        .title { font-weight: bold; color: #3498db; font-size: 18px; margin-right: 20px; }
        .btn-container { display: flex; gap: 10px; align-items: center; }
        
        button {
            padding: 8px 15px; border: none; border-radius: 4px; 
            font-weight: bold; cursor: pointer; font-size: 13px; transition: 0.2s;
            color: white;
        }
        
        .btn-load { background: #444; border: 1px solid #666; }
        
        .btn-mode { background: #333; border: 1px solid #555; color: #aaa; }
        .btn-mode.active-poly { background: #27ae60; color: white; border-color: #2ecc71; }
        .btn-mode.active-area { background: #3498db; color: white; border-color: #2980b9; } /* Azul para Área */
        .btn-mode.active-vert { background: #8e44ad; color: white; border-color: #9b59b6; }
        
        .btn-undo { background: #c0392b; opacity: 0.5; cursor: not-allowed; }
        .btn-undo.active { opacity: 1; cursor: pointer; }

        #result-panel {
            position: absolute; bottom: 30px; right: 30px;
            background: rgba(0,0,0,0.9); padding: 20px; border-radius: 8px;
            border-left: 4px solid #3498db; 
            text-align: right; z-index: 90;
            min-width: 250px;
        }
        .res-big { font-size: 32px; color: #3498db; font-weight: bold; }
        .res-small { font-size: 14px; color: #aaa; margin-top: 5px; }
        
        .custom-hotspot {
            background-color: #3498db; width: 12px; height: 12px;
            border-radius: 50%; border: 2px solid white; box-shadow: 0 0 4px black;
        }
        /* Cores diferentes para cada modo nos hotspots */
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
            <button id="btn-area" class="btn-mode" onclick="setMode('polygon')">📐 ÁREA</button> <button id="btn-vert" class="btn-mode" onclick="setMode('vertical')">🏢 ALTURA</button>
            
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
        const MAX_TEXTURE_SIZE = 4096;
        let viewer = null;
        let canvas, ctx;
        
        // --- CONFIGURAÇÕES FIXAS ---
        let droneHeight = 10.0;
        let pitchOffset = -1.80; // CORREÇÃO FIXA
        
        let appMode = 'idle'; 
        let points = []; 
        let isScrolling = false;
        let scrollTimeout = null;
        
        window.onload = function() {
            canvas = document.getElementById('drawing-layer');
            ctx = canvas.getContext('2d');
            resizeCanvas();
            window.addEventListener('resize', resizeCanvas);
            setInterval(drawOverlay, 33);
        };

        function resizeCanvas() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        }

        document.getElementById('fileInput').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (!file) return;
            detectHeightFromFileName(file.name);
            const img = new Image();
            const url = URL.createObjectURL(file);
            img.onload = function() {
                if (img.width > MAX_TEXTURE_SIZE) resizeAndLoad(img);
                else loadViewer(url);
            };
            img.src = url;
        });

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
            droneHeight = 10.0;
            document.getElementById('flight-info').innerText = "H Voo: 10.0m (Padrão)";
            document.getElementById('flight-info').style.color = '#e74c3c'; 
        }

        function resizeAndLoad(img) {
            const canvasTmp = document.createElement('canvas');
            const scale = MAX_TEXTURE_SIZE / img.width;
            canvasTmp.width = MAX_TEXTURE_SIZE;
            canvasTmp.height = img.height * scale;
            const ctxTmp = canvasTmp.getContext('2d');
            ctxTmp.drawImage(img, 0, 0, canvasTmp.width, canvasTmp.height);
            canvasTmp.toBlob(b => loadViewer(URL.createObjectURL(b)), 'image/jpeg', 0.95);
        }

        function loadViewer(url) {
            if (viewer) { try { viewer.destroy(); } catch(e){} }
            viewer = pannellum.viewer('panorama', {
                "type": "equirectangular", "panorama": url,
                "autoLoad": true, "compass": true,
                "pitch": -20, 
                "mouseZoom": false 
            });
            viewer.on('load', () => {
                document.getElementById('panorama').addEventListener('mousedown', onPanoramaClick);
            });
            setupScrollRotation();
        }

        function setupScrollRotation() {
            const panDiv = document.getElementById('panorama');
            panDiv.onwheel = null; 
            panDiv.addEventListener('wheel', function(e) {
                if (!viewer) return;
                e.preventDefault(); 
                isScrolling = true;
                if (scrollTimeout) clearTimeout(scrollTimeout);
                scrollTimeout = setTimeout(() => { isScrolling = false; }, 300);
                const sensitivity = 0.05; 
                let newYaw = viewer.getYaw() + (e.deltaY * sensitivity);
                viewer.setYaw(newYaw);
            }, { passive: false });
        }

        function drawOverlay() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            if (!viewer || points.length < 2) return;
            // Desenha apenas nos modos permitidos
            if (appMode !== 'polyline' && appMode !== 'vertical' && appMode !== 'polygon') return;

            ctx.beginPath();
            ctx.lineWidth = 3;
            
            // Define cores baseadas no modo
            if (appMode === 'polygon') {
                ctx.strokeStyle = '#3498db'; // Azul
                ctx.fillStyle = 'rgba(52, 152, 219, 0.3)'; // Preenchimento azul transparente
            } else if (appMode === 'vertical') {
                ctx.strokeStyle = '#8e44ad'; // Roxo
            } else {
                ctx.strokeStyle = '#2ecc71'; // Verde
            }

            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';

            for (let i = 0; i < points.length; i++) {
                const screenPos = viewer.pitchYawToCoords(points[i].pitch, points[i].yaw);
                
                // Evita desenhar pontos que estão "atrás" da câmera (coordenadas malucas)
                if (screenPos.x < -1000 || screenPos.x > canvas.width + 1000) continue;

                if (i === 0) ctx.moveTo(screenPos.x, screenPos.y);
                else ctx.lineTo(screenPos.x, screenPos.y);
            }

            // Se for polígono e tiver mais de 2 pontos, fecha o desenho
            if (appMode === 'polygon' && points.length > 2) {
                ctx.closePath();
                ctx.fill(); // Preenche a área
            }
            
            ctx.stroke();
        }

        function onPanoramaClick(e) {
            if (e.button !== 0) return; 
            if (appMode === 'idle') return;
            if (e.ctrlKey || e.shiftKey) return;
            if (isScrolling) return;

            const coords = viewer.mouseEventToCoords(e);
            addPoint(coords[0], coords[1]);
        }

        function addPoint(pitch, yaw) {
            let projected = {x:0, y:0};
            
            // Se for vertical e for o segundo ponto, não projeta no chão normal
            if (appMode === 'vertical' && points.length === 1) {
                projected = {x:0, y:0}; // Placeholder, calculado depois
            } else {
                projected = projectToPlane(pitch, yaw, droneHeight);
            }

            const spotId = 'pt-' + Date.now();
            let cssClass = "custom-hotspot";
            
            // Define estilo do ponto
            if (appMode === 'vertical') cssClass += " hotspot-vert"; 
            else if (appMode === 'polygon') cssClass += " hotspot-area";
            else cssClass += " hotspot-poly"; 

            viewer.addHotSpot({ "id": spotId, "pitch": pitch, "yaw": yaw, "cssClass": cssClass });
            points.push({ pitch, yaw, x: projected.x, y: projected.y, id: spotId });

            // Cálculos
            if (appMode === 'polyline') calculatePolyline();
            else if (appMode === 'polygon') calculatePolygonArea();
            else if (appMode === 'vertical' && points.length === 2) {
                calculateVertical();
                setTimeout(() => {
                    if(confirm("Medição Concluída. Fazer outra?")) resetPointsOnly();
                    else setMode('idle');
                }, 500); 
            }
            updateUI();
        }

        // --- CÁLCULO DE ÁREA (Fórmula de Shoelace) ---
        function calculatePolygonArea() {
            if (points.length < 3) {
                document.getElementById('main-result').innerText = "0.00 m²";
                document.getElementById('secondary-info').innerText = "Marque 3+ pontos...";
                return;
            }
            
            let area = 0;
            const n = points.length;
            
            for (let i = 0; i < n; i++) {
                const j = (i + 1) % n; // Próximo índice (faz a volta no último)
                area += points[i].x * points[j].y;
                area -= points[j].x * points[i].y;
            }
            
            area = Math.abs(area) / 2.0;
            
            document.getElementById('main-result').innerText = area.toFixed(2) + " m²";
            document.getElementById('secondary-info').innerText = "Área Total (Plana)";
        }

        function projectToPlane(pitchDeg, yawDeg, height) {
            const toRad = d => d * Math.PI / 180;
            const correctedPitch = pitchDeg + pitchOffset; 
            const pitch = toRad(correctedPitch);
            const yaw = toRad(yawDeg);
            const theta = (Math.PI / 2) + pitch; 
            
            if (theta >= Math.PI/2 - 0.01) {
                 return { x: 99999 * Math.sin(yaw), y: 99999 * Math.cos(yaw) };
            }
            const r = height * Math.tan(theta);
            return { x: r * Math.sin(yaw), y: r * Math.cos(yaw) };
        }

        function calculatePolyline() {
            if (points.length < 2) {
                document.getElementById('main-result').innerText = "0.00 m";
                document.getElementById('secondary-info').innerText = "Comece a clicar...";
                return;
            }
            let accDist = 0;
            for (let i = 0; i < points.length - 1; i++) {
                const dx = points[i+1].x - points[i].x;
                const dy = points[i+1].y - points[i].y;
                accDist += Math.sqrt(dx*dx + dy*dy);
            }
            document.getElementById('main-result').innerText = accDist.toFixed(2) + " m";
            document.getElementById('secondary-info').innerText = "Distância Total (Solo)";
        }

        function calculateVertical() {
            const base = points[0];
            const top = points[1];
            const toRad = d => d * Math.PI / 180;
            
            const thetaBase = (Math.PI / 2) + toRad(base.pitch + pitchOffset);
            const distToWall = droneHeight * Math.tan(thetaBase);
            const thetaTop = toRad(top.pitch + pitchOffset);
            const objectHeight = droneHeight + (distToWall * Math.tan(thetaTop));
            
            document.getElementById('main-result').innerText = Math.abs(objectHeight).toFixed(2) + " m";
            document.getElementById('secondary-info').innerText = "Altura Vertical Estimada";
        }

        function setMode(newMode) {
            appMode = newMode;
            resetPointsOnly();
            document.getElementById('panorama').classList.remove('measuring');
            
            // Reseta botões
            document.getElementById('btn-poly').className = "btn-mode";
            document.getElementById('btn-area').className = "btn-mode";
            document.getElementById('btn-vert').className = "btn-mode";
            
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

        function undoLastPoint() {
            if (points.length === 0) return;
            const last = points.pop();
            viewer.removeHotSpot(last.id);
            
            if (appMode === 'polyline') calculatePolyline();
            else if (appMode === 'polygon') calculatePolygonArea();
            
            updateUI();
        }

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
            const btnUndo = document.getElementById('btn-undo');
            btnUndo.className = points.length > 0 ? "btn-undo active" : "btn-undo";
        }
    </script>
</body>
</html>"""

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
        else: super().do_GET()

if __name__ == "__main__":
    def open_browser():
        time.sleep(1)
        webbrowser.open(f"http://localhost:{PORT}")
    
    threading.Thread(target=open_browser).start()
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Servidor ITTI Azul rodando: http://localhost:{PORT}")
        try: httpd.serve_forever()
        except: pass
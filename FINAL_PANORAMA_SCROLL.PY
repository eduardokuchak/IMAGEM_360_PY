import http.server
import socketserver
import os

PORT = 8000
try:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
except:
    os.chdir(os.getcwd())

HTML_CONTENT = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Engenharia 360 - ITTI (Azul)</title>
    
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.css"/>
    <script type="text/javascript" src="https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.js"></script>

    <style>
        body, html { margin: 0; padding: 0; height: 100%; font-family: 'Segoe UI', sans-serif; background: #111; color: white; overflow: hidden; }
        
        #panorama { width: 100%; height: 100vh; position: absolute; top:0; left:0; z-index: 1; }
        
        #drawing-layer { 
            position: absolute; top: 0; left: 0; width: 100%; height: 100%; 
            z-index: 2; pointer-events: none; 
        }

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
        .btn-calib { background: #2980b9; } 
        
        .btn-mode { background: #333; border: 1px solid #555; color: #aaa; }
        .btn-mode.active-poly { background: #27ae60; color: white; border-color: #2ecc71; }
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
        .res-label { font-size: 11px; color: #777; text-transform: uppercase; letter-spacing: 1px; }
        
        #calibration-modal {
            display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.8); z-index: 200;
            justify-content: center; align-items: center;
        }
        .modal-box {
            background: #222; padding: 25px; border-radius: 8px; 
            border: 1px solid #3498db;
            text-align: center; width: 300px;
        }
        #calib-input {
            width: 100%; padding: 12px; margin: 15px 0; font-size: 18px;
            background: #111; border: 1px solid #444; color: white; text-align: center;
        }
        .btn-confirm { background: #27ae60; color: white; width: 100%; padding: 12px;}

        .custom-hotspot {
            background-color: #3498db; width: 12px; height: 12px;
            border-radius: 50%; border: 2px solid white; box-shadow: 0 0 4px black;
        }
        .hotspot-last { background-color: #e74c3c !important; width: 14px; height: 14px; }
        .hotspot-vert { background-color: #8e44ad !important; border-color: #fff !important; }
    </style>
</head>
<body>

    <div id="top-bar">
        <div>
            <div class="title">ITTI | Distância 360°</div>
        </div>
        <div class="btn-container">
            <button class="btn-load" onclick="document.getElementById('fileInput').click()">📂 ABRIR</button>
            <button class="btn-calib" onclick="startCalibration()">⚙️ CALIBRAR</button>
            <div style="width:1px; height:20px; background:#444; margin:0 5px;"></div>
            <button id="btn-poly" class="btn-mode" onclick="setMode('polyline')">📏 MEDIR SOLO</button>
            <button id="btn-vert" class="btn-mode" onclick="setMode('vertical')">🏢 MEDIR ALTURA</button>
            <button id="btn-undo" class="btn-undo" onclick="undoLastPoint()">↩ DESFAZER</button>
        </div>
        <input type="file" id="fileInput" accept="image/*" style="display: none;">
    </div>

    <canvas id="drawing-layer"></canvas>

    <div id="result-panel">
        <div id="res-label" class="res-label">RESULTADO</div>
        <div id="main-result" class="res-big">0.00 m</div>
        <div style="height:1px; background:#444; margin: 10px 0;"></div>
        <div id="secondary-info" class="res-small">Selecione um modo</div>
        <div id="flight-info" style="color:#27ae60; font-size:12px; margin-top:10px;">H Voo: Padrão (10m)</div>
    </div>

    <div id="calibration-modal">
        <div class="modal-box">
            <h3 style="margin:0; color:white">CALIBRAÇÃO</h3>
            <p style="color:#aaa; font-size:13px;">Clique em 2 pontos no CHÃO e digite a distância real:</p>
            <input type="number" id="calib-input" placeholder="Metros (ex: 10.0)" step="0.1">
            <button class="btn-confirm" onclick="confirmCalibration()">CONFIRMAR</button>
        </div>
    </div>

    <div id="panorama"></div>

    <script>
        const MAX_TEXTURE_SIZE = 4096;
        let viewer = null;
        let canvas, ctx;
        
        let droneHeight = 10.0;
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
            const img = new Image();
            const url = URL.createObjectURL(file);
            img.onload = function() {
                if (img.width > MAX_TEXTURE_SIZE) resizeAndLoad(img);
                else loadViewer(url);
            };
            img.src = url;
        });

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
                "pitch": -45,
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
                
                scrollTimeout = setTimeout(() => {
                    isScrolling = false;
                }, 300);

                const sensitivity = 0.05; 
                let currentYaw = viewer.getYaw();
                let newYaw = currentYaw + (e.deltaY * sensitivity);
                viewer.setYaw(newYaw);
            }, { passive: false });
        }

        function drawOverlay() {
            if (!viewer || points.length < 2) {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                return;
            }
            if (appMode !== 'polyline' && appMode !== 'calibrating') {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                return;
            }

            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.beginPath();
            ctx.lineWidth = 3;
            ctx.strokeStyle = (appMode === 'calibrating') ? '#3498db' : '#2ecc71';
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';

            for (let i = 0; i < points.length; i++) {
                const screenPos = viewer.pitchYawToCoords(points[i].pitch, points[i].yaw);
                if (i === 0) ctx.moveTo(screenPos.x, screenPos.y);
                else ctx.lineTo(screenPos.x, screenPos.y);
            }
            ctx.stroke();
        }

        function onPanoramaClick(e) {
            // --- CORREÇÃO PRINCIPAL: BLOQUEIA BOTÃO DO MEIO OU DIREITO ---
            // event.button === 0 é o botão esquerdo. Se for diferente, ignora.
            if (e.button !== 0) return;

            if (appMode === 'idle') return;
            if (e.ctrlKey || e.shiftKey) return;
            if (isScrolling) return;

            const coords = viewer.mouseEventToCoords(e);
            const pitch = coords[0];
            const yaw = coords[1];

            if (appMode === 'vertical') {
                if (points.length === 0 && pitch > -1) {
                    alert("Para medir altura, o PRIMEIRO ponto deve ser a BASE no chão.");
                    return;
                }
            } else {
                if (pitch > -1) {
                    alert("Clique apenas no chão.");
                    return;
                }
            }
            addPoint(pitch, yaw);
        }

        function addPoint(pitch, yaw) {
            let projected = {x:0, y:0};
            
            if (appMode === 'vertical' && points.length === 1) {
                projected = {x:0, y:0}; 
            } else {
                projected = projectToPlane(pitch, yaw, droneHeight);
            }

            const spotId = 'pt-' + Date.now();
            let cssClass = "custom-hotspot";
            if (appMode === 'vertical') cssClass += " hotspot-vert"; 
            else cssClass += " hotspot-last"; 

            if (appMode === 'polyline' && points.length > 0) {
                 const prevId = points[points.length-1].id;
                 viewer.removeHotSpot(prevId);
                 viewer.addHotSpot({ 
                     "id": prevId, "pitch": points[points.length-1].pitch, "yaw": points[points.length-1].yaw, 
                     "cssClass": "custom-hotspot" 
                 });
            }

            viewer.addHotSpot({ "id": spotId, "pitch": pitch, "yaw": yaw, "cssClass": cssClass });
            points.push({ pitch, yaw, x: projected.x, y: projected.y, id: spotId });

            if (appMode === 'calibrating' && points.length === 2) {
                document.getElementById('calibration-modal').style.display = 'flex';
                document.getElementById('calib-input').focus();
            }
            else if (appMode === 'polyline') {
                calculatePolyline();
            }
            else if (appMode === 'vertical' && points.length === 2) {
                calculateVertical();
                setTimeout(() => {
                    if(confirm("Medição Concluída. Fazer outra?")) resetPointsOnly();
                    else setMode('idle');
                }, 500); 
            }
            updateUI();
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
            
            const thetaBase = (Math.PI / 2) + toRad(base.pitch);
            const distToWall = droneHeight * Math.tan(thetaBase);
            
            const objectHeight = droneHeight + (distToWall * Math.tan(toRad(top.pitch)));
            
            document.getElementById('main-result').innerText = Math.abs(objectHeight).toFixed(2) + " m";
            document.getElementById('secondary-info').innerText = "Altura Vertical Estimada";
        }

        function projectToPlane(pitchDeg, yawDeg, height) {
            const toRad = d => d * Math.PI / 180;
            const pitch = toRad(pitchDeg);
            const yaw = toRad(yawDeg);
            const theta = (Math.PI / 2) + pitch; 
            const r = height * Math.tan(theta);
            return { x: r * Math.sin(yaw), y: r * Math.cos(yaw) };
        }

        function startCalibration() {
            setMode('calibrating');
            alert("Clique em 2 pontos no chão com distância conhecida.");
        }

        function confirmCalibration() {
            const val = parseFloat(document.getElementById('calib-input').value.replace(',', '.'));
            if (!val || val <= 0) return alert("Inválido");
            
            const p1 = points[0]; const p2 = points[1];
            const proj1 = projectToPlane(p1.pitch, p1.yaw, 1.0);
            const proj2 = projectToPlane(p2.pitch, p2.yaw, 1.0);
            const distUnit = Math.sqrt(Math.pow(proj2.x-proj1.x, 2) + Math.pow(proj2.y-proj1.y, 2));
            
            droneHeight = val / distUnit;
            
            document.getElementById('flight-info').innerText = `H Voo: ${droneHeight.toFixed(2)} m`;
            document.getElementById('calibration-modal').style.display = 'none';
            alert("Calibrado!");
            
            resetPointsOnly();
            setMode('idle');
        }

        function setMode(newMode) {
            appMode = newMode;
            resetPointsOnly();
            
            document.getElementById('panorama').classList.remove('measuring');
            document.getElementById('btn-poly').className = "btn-mode";
            document.getElementById('btn-vert').className = "btn-mode";
            
            if (newMode === 'polyline') {
                document.getElementById('panorama').classList.add('measuring');
                document.getElementById('btn-poly').className = "btn-mode active-poly";
                document.getElementById('res-label').innerText = "DISTÂNCIA DE SOLO";
            } 
            else if (newMode === 'vertical') {
                document.getElementById('panorama').classList.add('measuring');
                document.getElementById('btn-vert').className = "btn-mode active-vert";
                document.getElementById('res-label').innerText = "ALTURA VERTICAL";
            }
            else if (newMode === 'calibrating') {
                document.getElementById('panorama').classList.add('measuring');
            }
        }

        function undoLastPoint() {
            if (points.length === 0) return;
            const last = points.pop();
            viewer.removeHotSpot(last.id);
            if (appMode === 'polyline') calculatePolyline();
            updateUI();
        }

        function resetPointsOnly() {
            points.forEach(p => viewer.removeHotSpot(p.id));
            points = [];
            ctx.clearRect(0, 0, canvas.width, canvas.height); 
            document.getElementById('main-result').innerText = "0.00 m";
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
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Servidor ITTI Azul rodando: http://localhost:{PORT}")
        try: httpd.serve_forever()
        except: pass
import http.server
import socketserver
import os
import webbrowser
import threading
import time

PORT = 8000

# Garante que o servidor rode na pasta do script
try:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
except:
    os.chdir(os.getcwd())

HTML_CONTENT = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ITTI 360 - Ajuste Fino</title>
    
    <script type="importmap">
        {
            "imports": {
                "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
                "three/addons/": "https://unpkg.com/three@0.160.0/examples/jsm/"
            }
        }
    </script>

    <style>
        body, html { margin: 0; padding: 0; height: 100%; font-family: 'Segoe UI', sans-serif; background: #111; color: white; overflow: hidden; }
        
        #container { width: 100%; height: 100vh; display: block; touch-action: none; outline: none; }
        
        #top-bar {
            position: absolute; top: 0; left: 0; width: 100%; height: 60px;
            background: rgba(0, 0, 0, 0.85); display: flex; align-items: center;
            padding: 0 20px; box-sizing: border-box; z-index: 100;
            border-bottom: 1px solid #444; justify-content: space-between;
        }

        .title { font-weight: bold; color: #3498db; font-size: 18px; }
        .btn-container { display: flex; gap: 10px; }
        
        button {
            padding: 8px 15px; border: none; border-radius: 4px; 
            font-weight: bold; cursor: pointer; font-size: 13px; transition: 0.2s; color: white;
        }
        
        .btn-load { background: #444; border: 1px solid #666; }
        .btn-load:hover { background: #555; }
        .btn-mode { background: #333; border: 1px solid #555; color: #aaa; }
        .btn-mode.active { background: #27ae60; color: white; border-color: #2ecc71; }
        .btn-undo { background: #c0392b; opacity: 0.5; cursor: not-allowed; }
        .btn-undo.active { opacity: 1; cursor: pointer; }

        /* --- NOVO: PAINEL DE CONTROLE DE AJUSTES --- */
        #adjust-panel {
            position: absolute; top: 70px; left: 10px;
            background: rgba(0, 0, 0, 0.8); padding: 15px;
            border-radius: 8px; border: 1px solid #444;
            z-index: 100; width: 200px;
        }
        .control-group { margin-bottom: 10px; }
        .control-group label { display: block; font-size: 12px; color: #ccc; margin-bottom: 5px; }
        .control-group input { width: 100%; cursor: pointer; }
        .val-display { float: right; color: #ffff00; font-weight: bold; }

        #result-panel {
            position: absolute; bottom: 30px; right: 30px;
            background: rgba(0,0,0,0.8); padding: 20px; border-radius: 8px;
            border-left: 4px solid #3498db; text-align: right; z-index: 90;
            min-width: 250px; pointer-events: none;
        }
        .res-big { font-size: 32px; color: #3498db; font-weight: bold; }
        
        #debug-info {
            position: absolute; bottom: 10px; left: 10px; color: lime; 
            font-family: monospace; font-size: 12px; pointer-events: none;
            background: rgba(0,0,0,0.5); padding: 5px; border-radius: 4px;
        }
    </style>
</head>
<body>

    <div id="top-bar">
        <div class="title">ITTI | Ajuste Fino</div>
        <div class="btn-container">
            <input type="file" id="fileInputImg" accept="image/*" style="display: none;">
            <input type="file" id="fileInputModel" accept=".glb,.gltf" style="display: none;">

            <button class="btn-load" onclick="document.getElementById('fileInputImg').click()">1. FOTO 360</button>
            <button class="btn-load" onclick="document.getElementById('fileInputModel').click()">2. MODELO GLB</button>
            
            <div style="width:1px; height:20px; background:#444; margin:0 5px;"></div>
            
            <button id="btn-dist" class="btn-mode" onclick="setMode('distance')">📏 DISTÂNCIA</button>
            <button id="btn-area" class="btn-mode" onclick="setMode('area')">📐 ÁREA</button>
            <button id="btn-undo" class="btn-undo" onclick="undoLastPoint()">↩</button>
        </div>
    </div>

    <div id="adjust-panel">
        <div class="control-group">
            <label>🔄 Rotação (Lados) <span id="lbl-rot" class="val-display">0°</span></label>
            <input type="range" id="slider-rot" min="0" max="360" step="1" value="0">
        </div>
        <div class="control-group">
            <label>👻 Opacidade <span id="lbl-op" class="val-display">50%</span></label>
            <input type="range" id="slider-op" min="0" max="1" step="0.05" value="0.5">
        </div>
    </div>

    <div id="result-panel">
        <div style="font-size:12px; color:#aaa; margin-bottom:5px;">RESULTADO</div>
        <div id="main-result" class="res-big">0.00</div>
        <div id="sub-result" style="font-size:14px; color:#ddd; margin-top:5px;">Pronto</div>
    </div>

    <div id="debug-info">Carregue a Foto e o Modelo...</div>
    <div id="container"></div>

    <script type="module">
        import * as THREE from 'three';
        import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
        import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

        // --- VARIÁVEIS GLOBAIS ---
        let scene, camera, renderer, controls;
        let sphereMesh, modelMesh = null;
        let raycaster, mouse;
        
        let droneHeight = 124.0;
        let groundPlane;

        let appMode = 'idle';
        let points = []; 
        let markers = []; 
        let lineRef = null; 

        window.onerror = function(message, source, lineno, colno, error) {
            alert("Erro no Script: " + message);
        };

        init();

        function init() {
            const container = document.getElementById('container');
            container.innerHTML = ""; 

            // 1. Cena
            scene = new THREE.Scene();

            // 2. Câmera
            camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 2000);
            camera.position.set(0, 0, 1); 

            // 3. Renderizador
            renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: true });
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            container.appendChild(renderer.domElement);

            // 4. Controles
            controls = new OrbitControls(camera, renderer.domElement);
            controls.target.set(0, 0, 0); 
            controls.enableZoom = false;  
            controls.enablePan = false;   
            controls.rotateSpeed = -0.5;  
            controls.enableDamping = true; 
            controls.dampingFactor = 0.1;

            // 5. Luz
            const ambientLight = new THREE.AmbientLight(0xffffff, 3);
            scene.add(ambientLight);
            
            raycaster = new THREE.Raycaster();
            mouse = new THREE.Vector2();
            groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), droneHeight);

            // 6. Listeners (Sliders)
            document.getElementById('slider-rot').addEventListener('input', updateModelSettings);
            document.getElementById('slider-op').addEventListener('input', updateModelSettings);

            // 7. Eventos Janela
            window.addEventListener('resize', onWindowResize);
            document.addEventListener('pointerdown', onPointerDown);
            
            document.getElementById('debug-info').innerText = "Sistema pronto.";
            animate();
        }

        // --- FUNÇÃO PARA ATUALIZAR ROTAÇÃO E OPACIDADE ---
        function updateModelSettings() {
            if (!modelMesh) return;

            // Pega valores
            const rotVal = document.getElementById('slider-rot').value;
            const opVal = document.getElementById('slider-op').value;

            // Atualiza Texto
            document.getElementById('lbl-rot').innerText = rotVal + "°";
            document.getElementById('lbl-op').innerText = Math.round(opVal * 100) + "%";

            // Aplica Rotação (Eixo Y - Lados)
            modelMesh.rotation.y = THREE.MathUtils.degToRad(rotVal);

            // Aplica Opacidade em todos os pedaços do modelo
            modelMesh.traverse((child) => {
                if (child.isMesh && child.material) {
                    child.material.opacity = parseFloat(opVal);
                    // Se opacidade for > 0, visivel. Se 0, invisivel.
                    child.material.visible = parseFloat(opVal) > 0.01; 
                }
            });
        }

        // --- CARREGAMENTO ---

        document.getElementById('fileInputImg').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if(!file) return;
            
            detectHeightFromFileName(file.name);

            const url = URL.createObjectURL(file);
            const loader = new THREE.TextureLoader();
            
            document.getElementById('debug-info').innerText = "Carregando imagem...";

            loader.load(url, function(texture) {
                texture.colorSpace = THREE.SRGBColorSpace;
                
                if(sphereMesh) scene.remove(sphereMesh);

                const geometry = new THREE.SphereGeometry(500, 60, 40);
                geometry.scale(-1, 1, 1); 
                const material = new THREE.MeshBasicMaterial({ map: texture });
                
                sphereMesh = new THREE.Mesh(geometry, material);
                scene.add(sphereMesh);
                
                document.getElementById('debug-info').innerText = "Imagem carregada.";
            }, undefined, function (err) {
                alert("Erro ao carregar imagem.");
            });
        });

        // CARREGAMENTO DO MODELO
        document.getElementById('fileInputModel').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if(!file) return;
            const url = URL.createObjectURL(file);

            const loader = new GLTFLoader();
            document.getElementById('debug-info').innerText = "Carregando GLB...";
            
            loader.load(url, function(gltf) {
                if(modelMesh) scene.remove(modelMesh);
                
                modelMesh = gltf.scene;
                
                // Configuração inicial do material (Vermelho)
                modelMesh.traverse((child) => {
                    if (child.isMesh) {
                        child.material = new THREE.MeshBasicMaterial({
                            color: 0xff0000, 
                            transparent: true,
                            opacity: 0.5, // Começa com 50%
                            side: THREE.DoubleSide,
                            depthWrite: true 
                        });
                    }
                });

                scene.add(modelMesh);
                
                // Aplica os valores que já estão nos sliders
                updateModelSettings();

                document.getElementById('debug-info').innerText = "Modelo Carregado. Use o painel para ajustar.";
            }, undefined, function(e) {
                console.error(e);
                alert("Erro ao ler GLB.");
            });
        });

        // --- CLIQUE E RAYCAST ---

        function onPointerDown(event) {
            if(appMode === 'idle') return;
            // Evita clicar se estiver mexendo nos sliders
            if(event.target.tagName === 'INPUT') return; 
            if(event.target.tagName === 'BUTTON') return;

            mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
            mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

            raycaster.setFromCamera(mouse, camera);

            let hitPoint = null;
            let hitType = "";

            // 1. Prioridade: Modelo GLB (Só se estiver visível)
            if (modelMesh && modelMesh.visible) {
                const intersects = raycaster.intersectObject(modelMesh, true);
                if (intersects.length > 0) {
                    hitPoint = intersects[0].point;
                    hitType = "MODELO 3D";
                }
            }

            // 2. Fallback: Matemática
            if (!hitPoint) {
                const target = new THREE.Vector3();
                groundPlane.constant = droneHeight; 
                const hit = raycaster.ray.intersectPlane(groundPlane, target);
                if (hit && hit.distanceTo(camera.position) < 2000) {
                    hitPoint = hit;
                    hitType = "MATEMÁTICO";
                }
            }

            if (hitPoint) addMeasurementPoint(hitPoint, hitType);
        }

        function addMeasurementPoint(point, type) {
            points.push(point);

            const geometry = new THREE.SphereGeometry(0.5, 16, 16);
            const material = new THREE.MeshBasicMaterial({ color: 0xffff00, depthTest: false });
            const marker = new THREE.Mesh(geometry, material);
            marker.position.copy(point);
            marker.renderOrder = 999;
            scene.add(marker);
            markers.push(marker);

            document.getElementById('debug-info').innerText = `Ponto: ${type}`;
            updateCalculations();
            updateLines();
            updateUIState();
        }

        function updateCalculations() {
            const resultEl = document.getElementById('main-result');
            const subEl = document.getElementById('sub-result');

            if (points.length < 2) {
                resultEl.innerText = "0.00";
                return;
            }

            if (appMode === 'distance') {
                let dist = 0;
                for(let i=0; i<points.length-1; i++) {
                    dist += points[i].distanceTo(points[i+1]);
                }
                resultEl.innerText = dist.toFixed(2) + " m";
                subEl.innerText = "Distância Total";
            } 
            else if (appMode === 'area' && points.length >= 3) {
                let area = 0;
                for (let i = 0; i < points.length; i++) {
                    let j = (i + 1) % points.length;
                    area += points[i].x * points[j].z;
                    area -= points[j].x * points[i].z;
                }
                area = Math.abs(area) / 2.0;
                resultEl.innerText = area.toFixed(2) + " m²";
                subEl.innerText = "Área (Solo)";
            }
        }

        function updateLines() {
            if(lineRef) scene.remove(lineRef);
            if(points.length < 2) return;

            const material = new THREE.LineBasicMaterial({ color: 0x00ff00, linewidth: 2, depthTest: false });
            let drawPoints = [...points];
            if (appMode === 'area' && points.length > 2) drawPoints.push(points[0]);

            const geometry = new THREE.BufferGeometry().setFromPoints(drawPoints);
            lineRef = new THREE.Line(geometry, material);
            lineRef.renderOrder = 998;
            scene.add(lineRef);
        }

        function detectHeightFromFileName(name) {
            const regex = /([0-9]+)\s*m/; 
            const match = name.match(regex);
            if (match) {
                droneHeight = parseFloat(match[1]);
                groundPlane.constant = droneHeight;
            }
        }

        window.setMode = function(mode) {
            appMode = mode;
            points = [];
            markers.forEach(m => scene.remove(m));
            markers = [];
            if(lineRef) scene.remove(lineRef);
            
            document.getElementById('btn-dist').className = mode === 'distance' ? 'btn-mode active' : 'btn-mode';
            document.getElementById('btn-area').className = mode === 'area' ? 'btn-mode active' : 'btn-mode';
            document.getElementById('main-result').innerText = "0.00";
            document.getElementById('sub-result').innerText = mode.toUpperCase();
        }

        window.undoLastPoint = function() {
            if(points.length === 0) return;
            points.pop();
            const lastMarker = markers.pop();
            scene.remove(lastMarker);
            updateCalculations();
            updateLines();
            updateUIState();
        }

        function updateUIState() {
            document.getElementById('btn-undo').className = points.length > 0 ? "btn-undo active" : "btn-undo";
        }

        function onWindowResize() {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }

        function animate() {
            requestAnimationFrame(animate);
            if(controls) controls.update(); 
            if(renderer && scene && camera) renderer.render(scene, camera);
        }
    </script>
</body>
</html>
"""

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
        else:
            super().do_GET()

if __name__ == "__main__":
    def open_browser():
        time.sleep(1)
        webbrowser.open(f"http://localhost:{PORT}")
    
    threading.Thread(target=open_browser).start()
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Servidor com Slider rodando: http://localhost:{PORT}")
        try: httpd.serve_forever()
        except: pass
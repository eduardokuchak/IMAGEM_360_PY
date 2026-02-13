import http.server
import socketserver
import os
import webbrowser
import threading
import time
import cgi
import tempfile
import zipfile
import sys
import shutil
import traceback
import json

# --- CONFIGURAÇÃO ---
try:
    import geopandas as gpd
    import pandas as pd
    import fiona
    from fiona.drvsupport import supported_drivers
    
    # Habilita drivers extras
    supported_drivers['KML'] = 'rw'
    supported_drivers['LIBKML'] = 'rw'
    supported_drivers['DXF'] = 'rw'
    supported_drivers['GPKG'] = 'rw'
    supported_drivers['GeoJSON'] = 'rw'
    
    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False
    print("❌ AVISO: Instale geopandas e fiona.")

PORT = 8000
CHUNK_SIZE = 1024 * 1024 * 1 # 1MB

try:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
except:
    os.chdir(os.getcwd())

# --- FRONT-END ---
HTML_CONTENT = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>GeoConversor - ITTI</title>
    <style>
        body { margin: 0; padding: 0; font-family: 'Segoe UI', sans-serif; background: #121212; color: #eee; display: flex; justify-content: center; align-items: center; height: 100vh; }
        .container { background: #1e1e1e; width: 750px; padding: 40px; border-radius: 12px; box-shadow: 0 0 60px rgba(0, 0, 0, 0.5); text-align: center; border: 1px solid #333; }
        
        /* COR AZUL ITTI */
        h1 { color: #2979ff; margin: 0 0 10px 0; font-size: 32px; letter-spacing: 2px; text-transform: uppercase; }
        p { color: #888; font-size: 14px; margin-bottom: 30px; }
        
        .drop-zone { border: 2px dashed #444; border-radius: 10px; padding: 40px; background: #181818; cursor: pointer; transition: 0.2s; position: relative; }
        .drop-zone:hover { border-color: #2979ff; background: #222; }
        
        .btn-group { display: flex; gap: 15px; justify-content: center; margin-top: 25px; }
        .btn-select { background: #2c2c2c; border: 1px solid #444; padding: 12px 25px; border-radius: 6px; cursor: pointer; font-size: 14px; color: #fff; transition: 0.2s; }
        .btn-select:hover { background: #3c3c3c; border-color: #2979ff; }
        
        #fileList { margin-top: 20px; text-align: left; font-size: 13px; color: #2979ff; max-height: 150px; overflow-y: auto; background: #000; padding: 10px; border: 1px solid #333; display: none; }
        
        .options-panel { background: #252525; padding: 20px; border-radius: 8px; margin-top: 25px; border: 1px solid #333; text-align: left; }
        
        /* Checkboxes Bonitos - Azul */
        .chk-container { display: block; position: relative; padding-left: 35px; margin-bottom: 12px; cursor: pointer; font-size: 15px; user-select: none; }
        .chk-container input { position: absolute; opacity: 0; cursor: pointer; height: 0; width: 0; }
        .checkmark { position: absolute; top: 0; left: 0; height: 20px; width: 20px; background-color: #444; border-radius: 4px; }
        .chk-container:hover input ~ .checkmark { background-color: #555; }
        .chk-container input:checked ~ .checkmark { background-color: #2979ff; }
        .checkmark:after { content: ""; position: absolute; display: none; }
        .chk-container input:checked ~ .checkmark:after { display: block; }
        .chk-container .checkmark:after { left: 7px; top: 3px; width: 5px; height: 10px; border: solid #fff; border-width: 0 3px 3px 0; transform: rotate(45deg); }

        select { width: 100%; padding: 15px; background: #2c2c2c; border: 1px solid #555; color: #fff; border-radius: 6px; outline: none; font-size: 16px; margin-top: 10px;}
        
        #progressContainer { width: 100%; background-color: #333; border-radius: 6px; margin-top: 25px; display: none; overflow: hidden; }
        #progressBar { width: 0%; height: 25px; background-color: #2979ff; text-align: center; line-height: 25px; color: white; font-weight: bold; font-size: 12px; transition: width 0.1s; }
        
        button.convert { width: 100%; padding: 20px; margin-top: 20px; background: #2979ff; border: none; color: #fff; font-weight: 900; border-radius: 6px; cursor: pointer; font-size: 18px; text-transform: uppercase; letter-spacing: 1px; }
        button.convert:hover { background: #2264d1; }
        button.convert:disabled { background: #333; color: #555; cursor: not-allowed; }
        
        #status { margin-top: 20px; font-weight: bold; min-height: 20px; white-space: pre-wrap; text-align: left; background: #000; padding: 10px; border-radius: 6px; display: none; font-family: monospace; font-size: 12px; border: 1px solid #333; }
        .error { color: #ff5555; } .success { color: #00e676; }
    </style>
</head>
<body>
    <div class="container">
        <h1>GeoConversor - ITTI</h1>
        <p>Conversor Universal de Dados Geográficos</p>
        
        <input type="file" id="fileInput" style="display: none;" multiple>
        <input type="file" id="folderInput" style="display: none;" webkitdirectory directory multiple>
        
        <div id="dropZone" class="drop-zone">
            <div style="font-size: 50px; margin-bottom: 10px;">🌐</div>
            <div id="dropText">Arraste SHP, KML, DXF, GeoJSON...</div>
            <div class="btn-group">
                <button class="btn-select" onclick="document.getElementById('fileInput').click()">Arquivos</button>
                <button class="btn-select" onclick="document.getElementById('folderInput').click()">Pastas</button>
            </div>
            <div id="fileList"></div>
        </div>
        
        <div class="options-panel">
            <label class="chk-container">Manter Organização de Pastas (Espelho)
                <input type="checkbox" id="chkMirror" checked>
                <span class="checkmark"></span>
            </label>
            
            <label class="chk-container">Gerar Lista de Rótulos (TXT para DXF)
                <input type="checkbox" id="chkLabels">
                <span class="checkmark"></span>
            </label>
            
            <hr style="border-color: #444; margin: 15px 0;">
            <div style="font-size: 14px; color: #ccc; margin-bottom: 5px;">Formato de Saída:</div>
            <select id="formatSelect">
                <option value="shp">Shapefile (.shp)</option>
                <option value="dxf">AutoCAD (.dxf)</option>
                <option value="kml">Google Earth (.kml)</option>
                <option value="geojson">GeoJSON (.json)</option>
                <option value="xlsx">Excel (.xlsx)</option>
                <option value="csv">CSV (.csv)</option>
            </select>
        </div>
        
        <div id="progressContainer">
            <div id="progressBar">0%</div>
        </div>
        
        <button id="btnConvert" class="convert" onclick="startProcess()">Converter</button>
        <div id="status"></div>
    </div>

    <script>
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const folderInput = document.getElementById('folderInput');
        const fileListDisplay = document.getElementById('fileList');
        const statusDiv = document.getElementById('status');
        const progressBar = document.getElementById('progressBar');
        const progressContainer = document.getElementById('progressContainer');
        const btn = document.getElementById('btnConvert');
        
        let selectedFiles = [];
        const sessionID = Date.now().toString(); 

        dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
        dropZone.addEventListener('dragleave', (e) => { dropZone.classList.remove('dragover'); });
        dropZone.addEventListener('drop', (e) => { e.preventDefault(); dropZone.classList.remove('dragover'); handleFiles(e.dataTransfer.files); });
        fileInput.addEventListener('change', () => handleFiles(fileInput.files));
        folderInput.addEventListener('change', () => handleFiles(folderInput.files));

        function handleFiles(files) {
            if (!files.length) return;
            selectedFiles = Array.from(files);
            fileListDisplay.style.display = 'block';
            fileListDisplay.innerHTML = `<strong>${files.length} arquivos na fila.</strong>`;
        }

        async function startProcess() {
            if (selectedFiles.length === 0) {
                statusDiv.style.display = 'block';
                statusDiv.innerHTML = "<span class='error'>⚠️ Selecione arquivos!</span>";
                return;
            }

            btn.disabled = true;
            progressContainer.style.display = 'block';
            progressBar.style.width = '0%';
            progressBar.innerText = '0%';
            statusDiv.style.display = 'block';
            statusDiv.innerHTML = "Enviando...";

            const CHUNK_SIZE = 1024 * 1024; 
            let totalSize = selectedFiles.reduce((acc, f) => acc + f.size, 0);
            let uploadedSize = 0;

            for (const file of selectedFiles) {
                const path = file.webkitRelativePath || file.name;
                let offset = 0;

                while (offset < file.size) {
                    const chunk = file.slice(offset, offset + CHUNK_SIZE);
                    const formData = new FormData();
                    formData.append('action', 'upload_chunk');
                    formData.append('session_id', sessionID);
                    formData.append('rel_path', path);
                    formData.append('chunk', chunk);
                    
                    try {
                        const resp = await fetch('/', { method: 'POST', body: formData });
                        if (!resp.ok) throw new Error("Erro no upload");
                    } catch (err) {
                        statusDiv.innerHTML = "<span class='error'>❌ Falha de conexão.</span>";
                        btn.disabled = false;
                        return;
                    }

                    offset += CHUNK_SIZE;
                    uploadedSize += chunk.size;
                    const percent = Math.min(100, Math.round((uploadedSize / totalSize) * 100));
                    progressBar.style.width = percent + '%';
                    progressBar.innerText = percent + '%';
                }
            }

            statusDiv.innerHTML = "Convertendo...";
            progressBar.style.backgroundColor = "#2979ff"; 

            const format = document.getElementById('formatSelect').value;
            const mirror = document.getElementById('chkMirror').checked;
            const labels = document.getElementById('chkLabels').checked;

            const finishForm = new FormData();
            finishForm.append('action', 'convert');
            finishForm.append('session_id', sessionID);
            finishForm.append('target_format', format);
            finishForm.append('mirror_mode', mirror);
            finishForm.append('export_labels', labels);

            try {
                const response = await fetch('/', { method: 'POST', body: finishForm });
                
                if (response.ok) {
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = "Resultado_ITTI.zip";
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    statusDiv.innerHTML = "<span class='success'>✅ Sucesso! Download iniciado.</span>";
                } else {
                    const errText = await response.text();
                    statusDiv.innerHTML = `<span class='error'>❌ RELATÓRIO:</span>\n${errText}`;
                }
            } catch (err) {
                statusDiv.innerHTML = `<span class='error'>❌ Erro fatal: ${err.message}</span>`;
            }

            btn.disabled = false;
        }
    </script>
</body>
</html>
"""

# --- BACK-END ---
class GeoHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML_CONTENT.encode('utf-8'))

    def send_utf8_error(self, code, message):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode('utf-8'))

    def do_POST(self):
        if not HAS_GEOPANDAS:
            self.send_utf8_error(500, "Geopandas não instalado.")
            return
            
        try:
            form = cgi.FieldStorage(
                fp=self.rfile, 
                headers=self.headers, 
                environ={'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': self.headers['Content-Type']}
            )
            
            action = form.getvalue('action')
            session_id = form.getvalue('session_id')
            session_dir = os.path.join(tempfile.gettempdir(), "geo_itti_" + session_id)
            input_root = os.path.join(session_dir, "INPUT")
            
            # 1. UPLOAD
            if action == 'upload_chunk':
                os.makedirs(input_root, exist_ok=True)
                rel_path = form.getvalue('rel_path')
                chunk_data = form['chunk'].file.read()
                
                # Segurança simples de path
                safe_path = rel_path.lstrip("/").lstrip("\\")
                full_path = os.path.join(input_root, safe_path)
                
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'ab') as f:
                    f.write(chunk_data)
                self.send_response(200); self.end_headers(); self.wfile.write(b"OK"); return

            # 2. CONVERSÃO
            elif action == 'convert':
                target_format = form.getvalue('target_format')
                mirror_mode = form.getvalue('mirror_mode') == 'true'
                export_labels = form.getvalue('export_labels') == 'true'
                
                output_root = os.path.join(session_dir, "OUTPUT")
                os.makedirs(output_root, exist_ok=True)

                print(f"--> Processando ITTI. Mirror: {mirror_mode}, Labels: {export_labels}")
                
                files_processed = 0
                error_log = []
                
                # Formatos Suportados
                SUPPORTED_EXTS = ('.shp', '.kml', '.kmz', '.geojson', '.json', '.gpkg', '.tab', '.dxf')

                for root, dirs, files in os.walk(input_root):
                    for f in files:
                        f_lower = f.lower()
                        input_path = os.path.join(root, f)
                        base_name = os.path.splitext(f)[0]

                        # Se não suportado, pula
                        if not f_lower.endswith(SUPPORTED_EXTS): continue
                        
                        # Lógica de Espelhamento vs Flat
                        if mirror_mode:
                            rel_dir = os.path.relpath(root, input_root)
                            target_dir = os.path.join(output_root, rel_dir)
                        else:
                            target_dir = output_root # Tudo na raiz
                        
                        os.makedirs(target_dir, exist_ok=True)

                        # Tratamento KMZ
                        if f_lower.endswith('.kmz'):
                            try:
                                with tempfile.TemporaryDirectory() as kmz_tmp:
                                    with zipfile.ZipFile(input_path, 'r') as z:
                                        kml_files = [x for x in z.namelist() if x.lower().endswith('.kml')]
                                        if kml_files:
                                            z.extract(kml_files[0], kmz_tmp)
                                            kml_p = os.path.join(kmz_tmp, kml_files[0])
                                            self.converter_core(kml_p, None, target_format, target_dir, base_name, export_labels)
                                            files_processed += 1
                            except Exception as e: error_log.append(f"Erro KMZ {f}: {e}")
                        
                        # Tratamento Padrão
                        else:
                            try:
                                # Resolve conflito de nome se estiver no modo Flat
                                final_name = base_name
                                if not mirror_mode:
                                    counter = 1
                                    while os.path.exists(os.path.join(target_dir, final_name + "." + target_format)):
                                        final_name = f"{base_name}_{counter}"
                                        counter += 1
                                
                                self.converter_core(input_path, None, target_format, target_dir, final_name, export_labels)
                                files_processed += 1
                            except Exception as e:
                                error_log.append(f"Erro Arquivo {f}: {e}")

                if files_processed == 0:
                    report = "Nenhum arquivo convertido.\n"
                    if error_log: report += "\nERROS:\n" + "\n".join(error_log)
                    self.send_utf8_error(400, report)
                    return

                # Zipar
                zip_path = os.path.join(session_dir, "Resultado.zip")
                with zipfile.ZipFile(zip_path, 'w') as zf:
                    for root, dirs, files in os.walk(output_root):
                        for file in files:
                            full = os.path.join(root, file)
                            rel = os.path.relpath(full, output_root)
                            zf.write(full, rel)
                    if error_log:
                        zf.writestr("ERROS.txt", "\n".join(error_log))

                with open(zip_path, 'rb') as f:
                    self.send_response(200)
                    self.send_header("Content-type", "application/zip")
                    self.send_header("Content-Disposition", f'attachment; filename="Resultado_ITTI.zip"')
                    self.end_headers()
                    self.wfile.write(f.read())
                
                try: shutil.rmtree(session_dir, ignore_errors=True)
                except: pass

        except Exception as e:
            self.send_utf8_error(500, f"Erro Fatal: {str(e)}\n{traceback.format_exc()}")

    def converter_core(self, src, layer, fmt, dst, name, do_labels):
        # 1. Leitura
        try:
            if layer: gdf = gpd.read_file(src, layer=layer)
            else:
                try: gdf = gpd.read_file(src)
                except: 
                    try: gdf = gpd.read_file(src, driver='KML')
                    except: gdf = gpd.read_file(src, driver='DXF')
        except: raise Exception("Formato ilegível")

        # 2. Limpeza
        if hasattr(gdf.geometry, 'make_valid'): gdf['geometry'] = gdf.geometry.make_valid()
        
        LIMITE = 1e10
        if not gdf.empty and gdf.geometry.notnull().any():
            b = gdf.bounds
            mask = ((b['minx'] > -LIMITE) & (b['miny'] > -LIMITE) & (b['maxx'] < LIMITE) & (b['maxy'] < LIMITE))
            gdf = gdf[mask & b['minx'].notna()]
        
        if len(gdf) == 0: return

        # 3. Saída
        out_path = os.path.join(dst, name)

        # SE O USUÁRIO QUER RÓTULOS (DXF LABELS)
        if do_labels and fmt == 'dxf':
            try:
                # Tenta achar uma coluna de nome
                cols = [c for c in gdf.columns if c.lower() in ['name', 'nome', 'label', 'texto', 'id', 'codigo']]
                label_col = cols[0] if cols else (gdf.columns[0] if len(gdf.columns) > 0 and gdf.columns[0] != 'geometry' else None)
                
                if label_col:
                    centroids = gdf.geometry.centroid
                    txt_path = out_path + "_ROTULOS.txt"
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write("X,Y,TEXTO\n")
                        for geom, val in zip(centroids, gdf[label_col]):
                            if geom and not geom.is_empty:
                                f.write(f"{geom.x},{geom.y},{val}\n")
            except: pass

        # Projeção para KML/GeoJSON
        if fmt in ['kml', 'geojson']:
            if gdf.crs and gdf.crs.to_string() != "EPSG:4326":
                try: gdf = gdf.to_crs("EPSG:4326")
                except: pass

        # Exportação Principal
        if fmt == 'shp':
            gdf.columns = [c[:10] for c in gdf.columns]
            gdf = gdf.loc[:,~gdf.columns.duplicated()]
            for c in gdf.columns:
                if gdf[c].dtype == 'datetime64[ns]': gdf[c] = gdf[c].astype(str)
            gdf.to_file(out_path + ".shp")
        elif fmt == 'dxf':
            gdf[['geometry']].to_file(out_path + ".dxf", driver='DXF')
        elif fmt == 'kml':
            gdf.to_file(out_path + ".kml", driver='KML')
        elif fmt == 'geojson':
            gdf.to_file(out_path + ".geojson", driver='GeoJSON')
        elif fmt == 'gpkg':
            gdf.to_file(out_path + ".gpkg", driver='GPKG', layer=name)
        elif fmt == 'xlsx':
            df = pd.DataFrame(gdf.drop(columns='geometry', errors='ignore'))
            df.to_excel(out_path + ".xlsx", index=False)
        elif fmt == 'csv':
            df = pd.DataFrame(gdf.drop(columns='geometry', errors='ignore'))
            df.to_csv(out_path + ".csv", sep=';', encoding='utf-8-sig', index=False)

if __name__ == "__main__":
    def open_browser(): time.sleep(1); webbrowser.open(f"http://localhost:{PORT}")
    if HAS_GEOPANDAS:
        threading.Thread(target=open_browser).start()
        print(f"✅ GEO ITTI RODANDO! Acesse: http://localhost:{PORT}")
        with socketserver.ThreadingTCPServer(("", PORT), GeoHandler) as httpd:
            try: httpd.serve_forever()
            except KeyboardInterrupt: pass
    else: print("Instale Geopandas!")
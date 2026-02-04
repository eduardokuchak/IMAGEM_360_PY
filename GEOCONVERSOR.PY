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

# --- VERIFICAÇÃO DE BIBLIOTECAS ---
try:
    import geopandas as gpd
    import pandas as pd
    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False
    print("❌ ERRO: Geopandas não encontrado.")

PORT = 8000

try:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
except:
    os.chdir(os.getcwd())

# --- FRONT-END ---
HTML_CONTENT = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>GeoConversor V6 - Batch</title>
    <style>
        body { margin: 0; padding: 0; font-family: 'Segoe UI', sans-serif; background: #121212; color: #e0e0e0; display: flex; justify-content: center; align-items: center; height: 100vh; }
        .container { background: #1e1e1e; width: 500px; padding: 40px; border-radius: 16px; box-shadow: 0 15px 40px rgba(0,0,0,0.6); text-align: center; border: 1px solid #333; }
        h1 { color: #9b59b6; margin: 0 0 10px 0; font-size: 26px; letter-spacing: 1px; }
        p { color: #888; font-size: 14px; margin-bottom: 20px; }
        
        .drop-zone { border: 2px dashed #444; border-radius: 12px; padding: 30px 20px; background: #181818; cursor: pointer; transition: 0.3s; position: relative; }
        .drop-zone:hover, .drop-zone.dragover { border-color: #9b59b6; background: #222; }
        .drop-zone span { font-size: 40px; display: block; margin-bottom: 10px; opacity: 0.8; }
        .file-list { margin-top: 10px; font-size: 13px; color: #2ecc71; text-align: left; max-height: 80px; overflow-y: auto; }
        
        select { width: 100%; padding: 12px; margin-top: 20px; background: #252525; border: 1px solid #444; color: white; border-radius: 8px; font-size: 14px; outline: none; cursor: pointer; }
        
        /* CHECKBOX ESTILIZADO */
        .checkbox-wrapper { margin-top: 20px; display: flex; align-items: center; justify-content: flex-start; background: #252525; padding: 10px; border-radius: 8px; border: 1px solid #444; }
        .checkbox-wrapper input { width: 20px; height: 20px; cursor: pointer; accent-color: #9b59b6; margin-right: 10px; }
        .checkbox-wrapper label { cursor: pointer; font-size: 14px; color: #ddd; user-select: none; }

        button { width: 100%; padding: 16px; margin-top: 20px; background: #9b59b6; border: none; color: white; font-weight: bold; border-radius: 8px; cursor: pointer; font-size: 16px; transition: 0.2s; box-shadow: 0 4px 15px rgba(155, 89, 182, 0.3); }
        button:hover { background: #8e44ad; transform: translateY(-2px); }
        button:disabled { background: #444; cursor: not-allowed; }
        
        .status { margin-top: 20px; font-size: 14px; min-height: 20px; font-weight: 500; }
        .error { color: #e74c3c; } .success { color: #2ecc71; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ GeoConversor V6</h1>
        <p>Conversão em Lote ou Unificada</p>
        
        <input type="file" id="fileInput" style="display: none;" multiple>
        <div class="drop-zone" id="dropZone" onclick="document.getElementById('fileInput').click()">
            <span>📂</span>
            <div id="dropText">Arraste seus arquivos aqui</div>
            <div id="fileList" class="file-list"></div>
        </div>
        
        <select id="formatSelect">
            <option value="csv">Excel (Separado por Colunas)</option>
            <option value="dxf">DXF (AutoCAD) - Apenas Desenho</option>
            <option value="kml">KML (Google Earth)</option>
            <option value="geojson">GeoJSON</option>
            <option value="shp">Shapefile (ZIP)</option>
        </select>

        <div class="checkbox-wrapper">
            <input type="checkbox" id="batchMode">
            <label for="batchMode">Processar em Lote (Manter arquivos separados)</label>
        </div>
        
        <button id="btnConvert" onclick="uploadAndConvert()">Converter</button>
        <div id="status" class="status"></div>
    </div>

    <script>
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const fileListDisplay = document.getElementById('fileList');
        let selectedFiles = [];

        dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
        dropZone.addEventListener('drop', (e) => { e.preventDefault(); dropZone.classList.remove('dragover'); handleFiles(e.dataTransfer.files); });
        fileInput.addEventListener('change', (e) => handleFiles(fileInput.files));

        function handleFiles(files) {
            selectedFiles = files; fileListDisplay.innerHTML = "";
            if (files.length > 0) {
                document.getElementById('dropText').style.display = 'none';
                for (let i = 0; i < files.length; i++) {
                    const div = document.createElement("div"); div.className = "file-item"; div.innerText = "📄 " + files[i].name; fileListDisplay.appendChild(div);
                }
            }
        }

        async function uploadAndConvert() {
            if (selectedFiles.length === 0) { setStatus("⚠️ Selecione arquivos!", "error"); return; }
            const btn = document.getElementById('btnConvert');
            const format = document.getElementById('formatSelect').value;
            const isBatch = document.getElementById('batchMode').checked;
            
            btn.innerHTML = '⏳ Processando...'; btn.disabled = true; setStatus("");

            const formData = new FormData();
            for (let i = 0; i < selectedFiles.length; i++) formData.append("files", selectedFiles[i]);
            formData.append("target_format", format);
            formData.append("batch_mode", isBatch); // Envia o estado do checkbox

            try {
                const response = await fetch("/", { method: "POST", body: formData });
                if (response.ok) {
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a'); a.href = url;
                    
                    // Se for Batch, sempre baixa ZIP. Se não, depende do formato.
                    let ext = (format === 'shp' || isBatch) ? 'zip' : format;
                    let prefix = isBatch ? 'Lote_Convertido' : 'Resultado_Unico';
                    
                    a.download = `${prefix}.${ext}`;
                    document.body.appendChild(a); a.click(); a.remove();
                    setStatus("✅ Arquivo pronto!", "success");
                } else {
                    const errText = await response.text(); setStatus("Erro: " + errText, "error");
                }
            } catch (error) { setStatus("Erro de conexão.", "error"); }
            btn.innerHTML = 'Converter'; btn.disabled = false;
        }
        function setStatus(msg, type) { const el = document.getElementById('status'); el.innerText = msg; el.className = "status " + type; }
    </script>
</body>
</html>
"""

# --- BACK-END ---
class GeoHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
        else: super().do_GET()

    def do_POST(self):
        if not HAS_GEOPANDAS: self.send_error(500, "Falta Geopandas"); return
        
        try:
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': self.headers['Content-Type']})
            
            with tempfile.TemporaryDirectory() as tmp_dir:
                # 1. RECEBER DADOS
                if 'files' not in form: raise Exception("Sem arquivos")
                uploaded_files = form['files']
                if not isinstance(uploaded_files, list): uploaded_files = [uploaded_files]
                
                target_format = form.getvalue('target_format')
                batch_mode = form.getvalue('batch_mode') == 'true' # Verifica checkbox
                
                # Lista para guardar os caminhos dos arquivos de entrada válidos
                input_maps = []

                # Salvar arquivos no disco temporário
                for file_item in uploaded_files:
                    if file_item.filename:
                        fname = os.path.basename(file_item.filename)
                        save_path = os.path.join(tmp_dir, fname)
                        with open(save_path, 'wb') as f: f.write(file_item.file.read())
                        
                        # Detecta arquivos processáveis
                        if fname.lower().endswith(('.shp', '.kml', '.geojson', '.json', '.gpkg')):
                            input_maps.append(save_path)
                        elif fname.lower().endswith('.zip'):
                            # Se for zip, extrai e procura dentro
                            extract_path = os.path.join(tmp_dir, "ext_" + fname)
                            os.makedirs(extract_path, exist_ok=True)
                            with zipfile.ZipFile(save_path, 'r') as z:
                                z.extractall(extract_path)
                                for root, dirs, files in os.walk(extract_path):
                                    for zf in files:
                                        if zf.lower().endswith('.shp'):
                                            input_maps.append(os.path.join(root, zf))

                if not input_maps: raise Exception("Nenhum mapa válido encontrado nos uploads.")

                # 2. PROCESSAMENTO (BATCH vs UNIFICADO)
                
                final_download_path = ""
                mime = "application/octet-stream"

                # FUNÇÃO AUXILIAR DE CONVERSÃO
                def convert_gdf(gdf, fmt, path_out):
                    if fmt == 'csv':
                        df = pd.DataFrame(gdf.drop(columns='geometry', errors='ignore'))
                        df.to_csv(path_out + ".csv", sep=';', encoding='utf-8-sig', index=False)
                        return path_out + ".csv"
                    elif fmt == 'dxf':
                        gdf[['geometry']].to_file(path_out + ".dxf", driver='DXF')
                        return path_out + ".dxf"
                    elif fmt == 'kml':
                        if gdf.crs != "EPSG:4326": gdf = gdf.to_crs("EPSG:4326")
                        gdf.to_file(path_out + ".kml", driver='KML')
                        return path_out + ".kml"
                    elif fmt == 'geojson':
                        if gdf.crs != "EPSG:4326": gdf = gdf.to_crs("EPSG:4326")
                        gdf.to_file(path_out + ".geojson", driver='GeoJSON')
                        return path_out + ".geojson"
                    elif fmt == 'shp':
                        os.makedirs(path_out, exist_ok=True)
                        gdf.columns = [c[:10] for c in gdf.columns] # Fix colunas
                        gdf = gdf.loc[:,~gdf.columns.duplicated()]
                        for col in gdf.columns:
                            if gdf[col].dtype == 'datetime64[ns]': gdf[col] = gdf[col].astype(str)
                        gdf.to_file(os.path.join(path_out, os.path.basename(path_out) + ".shp"))
                        # Zipar o shapefile resultante
                        sh_zip = path_out + ".zip"
                        with zipfile.ZipFile(sh_zip, 'w') as zf:
                            for root, dirs, files in os.walk(path_out):
                                for f in files: zf.write(os.path.join(root, f), f)
                        return sh_zip

                if batch_mode:
                    # --- MODO LOTE (VARIOS ARQUIVOS) ---
                    output_folder = os.path.join(tmp_dir, "batch_output")
                    os.makedirs(output_folder, exist_ok=True)
                    
                    for map_file in input_maps:
                        try:
                            gdf = gpd.read_file(map_file)
                            name_no_ext = os.path.splitext(os.path.basename(map_file))[0]
                            out_base = os.path.join(output_folder, name_no_ext)
                            
                            # Converte e salva na pasta de saida
                            convert_gdf(gdf, target_format, out_base)
                        except Exception as e:
                            print(f"Erro ao converter {map_file}: {e}")

                    # Zipar a pasta inteira de resultados
                    final_download_path = os.path.join(tmp_dir, "Lote_Completo.zip")
                    with zipfile.ZipFile(final_download_path, 'w') as zf:
                        for root, dirs, files in os.walk(output_folder):
                            for file in files:
                                # Evita estrutura de pastas profunda no zip
                                arcname = os.path.basename(file)
                                zf.write(os.path.join(root, file), arcname)
                    mime = "application/zip"

                else:
                    # --- MODO UNIFICADO (MERGE) ---
                    # Lê todos e junta em um só
                    gdfs = []
                    for map_file in input_maps:
                        try:
                            gdfs.append(gpd.read_file(map_file))
                        except: pass
                    
                    if not gdfs: raise Exception("Falha ao ler arquivos.")
                    
                    # Concatena (Junta as tabelas)
                    full_gdf = pd.concat(gdfs, ignore_index=True)
                    
                    out_base = os.path.join(tmp_dir, "resultado_unificado")
                    res_file = convert_gdf(full_gdf, target_format, out_base)
                    
                    final_download_path = res_file
                    
                    # Definir mime types
                    if target_format == 'csv': mime = "text/csv"
                    elif target_format == 'dxf': mime = "application/dxf"
                    elif target_format == 'kml': mime = "application/vnd.google-earth.kml+xml"
                    elif target_format == 'geojson': mime = "application/json"
                    elif target_format == 'shp': mime = "application/zip"

                # 3. ENVIAR RESPOSTA
                with open(final_download_path, 'rb') as f:
                    self.send_response(200)
                    self.send_header("Content-type", mime)
                    self.send_header("Content-Disposition", f'attachment; filename="{os.path.basename(final_download_path)}"')
                    self.end_headers()
                    self.wfile.write(f.read())

        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Erro no servidor: {str(e)}".encode('utf-8'))

if __name__ == "__main__":
    def open_browser(): time.sleep(1); webbrowser.open(f"http://localhost:{PORT}")
    if HAS_GEOPANDAS:
        threading.Thread(target=open_browser).start()
        print(f"✅ GEO V6 (BATCH) RODANDO! Acesse: http://localhost:{PORT}")
        with socketserver.TCPServer(("", PORT), GeoHandler) as httpd:
            try: httpd.serve_forever()
            except KeyboardInterrupt: pass
    else: print("Instale Geopandas!")
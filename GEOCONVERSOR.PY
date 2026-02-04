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
    import fiona
    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False
    print("❌ AVISO: Bibliotecas Geopandas/Fiona não encontradas. O backend falhará.")

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
    <title>GeoConversor V11 - Final</title>
    <style>
        body { margin: 0; padding: 0; font-family: 'Segoe UI', sans-serif; background: #0a0a0a; color: #fff; display: flex; justify-content: center; align-items: center; height: 100vh; }
        .container { background: #111; width: 680px; padding: 40px; border-radius: 12px; box-shadow: 0 0 50px rgba(0,255,100,0.1); text-align: center; border: 1px solid #333; }
        h1 { color: #00ff88; margin: 0 0 10px 0; font-size: 32px; letter-spacing: 1px; }
        p { color: #888; font-size: 14px; margin-bottom: 30px; }
        
        .drop-zone { border: 2px dashed #444; border-radius: 10px; padding: 40px; background: #0f0f0f; cursor: pointer; transition: 0.2s; }
        .drop-zone:hover { border-color: #00ff88; background: #1a1a1a; }
        .drop-zone.dragover { border-color: #fff; background: #222; }
        
        .btn-group { display: flex; gap: 15px; justify-content: center; margin-top: 25px; }
        .btn-select { background: #222; border: 1px solid #444; padding: 12px 25px; border-radius: 6px; cursor: pointer; font-size: 14px; color: #fff; transition: 0.2s; }
        .btn-select:hover { background: #333; border-color: #00ff88; }
        
        #fileList { margin-top: 20px; text-align: left; font-size: 13px; color: #00ff88; max-height: 150px; overflow-y: auto; background: #000; padding: 10px; border: 1px solid #333; display: none; }
        
        select { width: 100%; padding: 15px; margin-top: 25px; background: #222; border: 1px solid #444; color: #fff; border-radius: 6px; outline: none; }
        
        button.convert { width: 100%; padding: 20px; margin-top: 25px; background: #00ff88; border: none; color: #000; font-weight: bold; border-radius: 6px; cursor: pointer; font-size: 18px; text-transform: uppercase; }
        button.convert:hover { background: #00cc6a; }
        button.convert:disabled { background: #333; color: #555; cursor: not-allowed; }
        
        #status { margin-top: 20px; font-weight: bold; min-height: 20px; }
        .error { color: #ff5555; } .success { color: #00ff88; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 GeoConversor V11</h1>
        <p>Suporte Total: MDB, SHP e Pastas (Sem Erros de JS)</p>
        
        <input type="file" id="fileInput" style="display: none;" multiple>
        <input type="file" id="folderInput" style="display: none;" webkitdirectory directory multiple>
        
        <div id="dropZone" class="drop-zone">
            <div style="font-size: 50px; margin-bottom: 10px;">📂</div>
            <div id="dropText">Arraste Arquivos ou Pastas aqui</div>
            
            <div class="btn-group">
                <button class="btn-select" onclick="document.getElementById('fileInput').click()">Selecionar Arquivos</button>
                <button class="btn-select" onclick="document.getElementById('folderInput').click()">Selecionar Pasta</button>
            </div>
            
            <div id="fileList"></div>
        </div>
        
        <select id="formatSelect">
            <option value="shp">Shapefile (ZIP)</option>
            <option value="dxf">DXF (AutoCAD) - Limpo</option>
            <option value="xlsx">Excel .XLSX</option>
            <option value="kml">KML (Google Earth)</option>
            <option value="geojson">GeoJSON</option>
            <option value="gpkg">GeoPackage</option>
            <option value="csv">CSV (Excel)</option>
        </select>
        
        <button id="btnConvert" class="convert" onclick="uploadAndConvert()">Iniciar Conversão</button>
        <div id="status"></div>
    </div>

    <script>
        // Elementos
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const folderInput = document.getElementById('folderInput');
        const fileListDisplay = document.getElementById('fileList');
        const statusDiv = document.getElementById('status');
        let selectedFiles = [];

        // Drag & Drop Simplificado e Robusto
        dropZone.addEventListener('dragover', function(e) {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', function(e) {
            dropZone.classList.remove('dragover');
        });

        dropZone.addEventListener('drop', function(e) {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            handleFiles(e.dataTransfer.files);
        });

        // Inputs normais
        fileInput.addEventListener('change', function() { handleFiles(fileInput.files); });
        folderInput.addEventListener('change', function() { handleFiles(folderInput.files); });

        function handleFiles(files) {
            if (!files || files.length === 0) return;
            selectedFiles = files;
            
            fileListDisplay.style.display = 'block';
            fileListDisplay.innerHTML = `<strong>${files.length} itens prontos para envio.</strong><br>`;
            
            const limit = Math.min(files.length, 10);
            for (let i = 0; i < limit; i++) {
                // webkitRelativePath é usado para pastas, name para arquivos soltos
                let name = files[i].webkitRelativePath || files[i].name;
                fileListDisplay.innerHTML += `<div>📄 ${name}</div>`;
            }
            if (files.length > 10) {
                fileListDisplay.innerHTML += `<div>... e mais ${files.length - 10} arquivos.</div>`;
            }
        }

        async function uploadAndConvert() {
            if (selectedFiles.length === 0) {
                statusDiv.innerHTML = "<span class='error'>⚠️ Selecione arquivos primeiro!</span>";
                return;
            }

            const btn = document.getElementById('btnConvert');
            const format = document.getElementById('formatSelect').value;
            
            btn.innerHTML = '⏳ Enviando e Convertendo...';
            btn.disabled = true;
            statusDiv.innerHTML = "";

            const formData = new FormData();
            
            // Adiciona arquivos ao FormData
            for (let i = 0; i < selectedFiles.length; i++) {
                const file = selectedFiles[i];
                const path = file.webkitRelativePath || file.name;
                formData.append("files", file, path);
            }
            formData.append("target_format", format);

            try {
                const response = await fetch("/", {
                    method: "POST",
                    body: formData
                });

                if (response.ok) {
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = "Resultado_GeoConversor.zip";
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    statusDiv.innerHTML = "<span class='success'>✅ Sucesso! Download iniciado.</span>";
                } else {
                    const errorText = await response.text();
                    // Detecta erro 413 (Arquivo muito grande)
                    if (response.status === 413 || errorText.includes("Too Large")) {
                        statusDiv.innerHTML = "<span class='error'>❌ Erro: Arquivos muito grandes para este servidor/proxy. Tente enviar menos arquivos por vez.</span>";
                    } else {
                        statusDiv.innerHTML = `<span class='error'>❌ Erro no servidor: ${errorText}</span>`;
                    }
                }
            } catch (error) {
                statusDiv.innerHTML = `<span class='error'>❌ Erro de conexão: ${error.message}</span>`;
            }

            btn.innerHTML = 'Iniciar Conversão';
            btn.disabled = false;
        }
        
        console.log("GeoConversor V11 JS Carregado com Sucesso!");
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
        else:
            super().do_GET()

    def do_POST(self):
        if not HAS_GEOPANDAS:
            self.send_error(500, "Geopandas nao instalado no servidor.")
            return

        try:
            # Tenta processar o upload
            # Se for muito grande e houver um proxy (Nginx), isso nem será executado, cairá no erro 413 antes.
            form = cgi.FieldStorage(
                fp=self.rfile, 
                headers=self.headers, 
                environ={'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': self.headers['Content-Type']}
            )
            
            with tempfile.TemporaryDirectory() as tmp_dir:
                if 'files' not in form: raise Exception("Nenhum arquivo recebido pelo servidor.")
                
                uploaded_files = form['files']
                if not isinstance(uploaded_files, list): uploaded_files = [uploaded_files]
                
                target_format = form.getvalue('target_format')
                
                input_root = os.path.join(tmp_dir, "INPUT")
                output_root = os.path.join(tmp_dir, "OUTPUT")
                os.makedirs(input_root, exist_ok=True)
                os.makedirs(output_root, exist_ok=True)

                print(f"--> Recebendo {len(uploaded_files)} arquivos...")

                # 1. Salvar arquivos mantendo estrutura de pastas
                for file_item in uploaded_files:
                    if file_item.filename:
                        # Limpa barras iniciais para evitar erro de path absoluto
                        safe_name = file_item.filename.lstrip("/").lstrip("\\")
                        save_path = os.path.join(input_root, safe_name)
                        
                        os.makedirs(os.path.dirname(save_path), exist_ok=True)
                        with open(save_path, 'wb') as f:
                            f.write(file_item.file.read())

                files_processed = 0

                # 2. Varrer e Converter
                for root, dirs, files in os.walk(input_root):
                    for f in files:
                        f_lower = f.lower()
                        input_path = os.path.join(root, f)
                        
                        # Calcula onde salvar no OUTPUT (Espelhamento)
                        rel_path = os.path.relpath(root, input_root)
                        target_dir = os.path.join(output_root, rel_path)
                        os.makedirs(target_dir, exist_ok=True)
                        
                        base_name = os.path.splitext(f)[0]

                        if f_lower.endswith('.shp'):
                            try:
                                self.convert_layer(input_path, None, target_format, target_dir, base_name)
                                files_processed += 1
                            except Exception as e: print(f"Erro SHP {f}: {e}")
                        
                        elif f_lower.endswith('.mdb'):
                            try:
                                # Cria pasta para o MDB
                                mdb_out_dir = os.path.join(target_dir, base_name)
                                os.makedirs(mdb_out_dir, exist_ok=True)
                                
                                layers = fiona.listlayers(input_path)
                                for lyr in layers:
                                    try:
                                        self.convert_layer(input_path, lyr, target_format, mdb_out_dir, lyr)
                                    except: pass
                                files_processed += 1
                            except Exception as e: print(f"Erro MDB {f}: {e}")

                if files_processed == 0:
                    raise Exception("Nenhum arquivo válido (.shp ou .mdb) foi processado.")

                # 3. Zipar Resultado
                zip_path = os.path.join(tmp_dir, "Download.zip")
                with zipfile.ZipFile(zip_path, 'w') as zf:
                    for root, dirs, files in os.walk(output_root):
                        for file in files:
                            full_path = os.path.join(root, file)
                            rel_name = os.path.relpath(full_path, output_root)
                            zf.write(full_path, rel_name)

                # 4. Enviar
                with open(zip_path, 'rb') as f:
                    self.send_response(200)
                    self.send_header("Content-type", "application/zip")
                    self.send_header("Content-Disposition", f'attachment; filename="Geo_Convertido_V11.zip"')
                    self.end_headers()
                    self.wfile.write(f.read())

        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Erro Interno: {str(e)}".encode('utf-8'))

    def convert_layer(self, src_path, layer, fmt, dst_folder, out_name):
        # Leitura
        if layer: gdf = gpd.read_file(src_path, layer=layer)
        else: gdf = gpd.read_file(src_path)

        # Limpeza e Filtro Anti-Limbo (10 Bilhões)
        if hasattr(gdf.geometry, 'make_valid'): gdf['geometry'] = gdf.geometry.make_valid()
        # Explode opcional (pode pesar muito em MDBs grandes, descomente se necessário)
        # try: gdf = gdf.explode(index_parts=True).reset_index(drop=True)
        # except: pass
        
        # Filtro de Coordenadas
        LIMITE = 1e10
        b = gdf.bounds
        mask = ((b['minx'] > -LIMITE) & (b['miny'] > -LIMITE) & (b['maxx'] < LIMITE) & (b['maxy'] < LIMITE))
        mask = mask & b['minx'].notna()
        gdf = gdf[mask]

        if len(gdf) == 0: return

        out_path = os.path.join(dst_folder, out_name)

        if fmt == 'dxf':
            gdf[['geometry']].to_file(out_path + ".dxf", driver='DXF')
        elif fmt == 'shp':
            # Fix colunas < 10 chars e datas
            gdf.columns = [c[:10] for c in gdf.columns]
            gdf = gdf.loc[:,~gdf.columns.duplicated()]
            for col in gdf.columns:
                if gdf[col].dtype == 'datetime64[ns]': gdf[col] = gdf[col].astype(str)
            gdf.to_file(out_path + ".shp")
        elif fmt == 'xlsx':
            try:
                df = pd.DataFrame(gdf.drop(columns='geometry', errors='ignore'))
                for col in df.select_dtypes(include=['datetime64[ns, UTC]', 'datetime64[ns]']).columns:
                    df[col] = df[col].astype(str)
                df.to_excel(out_path + ".xlsx", index=False)
            except: pass
        elif fmt == 'csv':
            df = pd.DataFrame(gdf.drop(columns='geometry', errors='ignore'))
            df.to_csv(out_path + ".csv", sep=';', encoding='utf-8-sig', index=False)
        elif fmt == 'kml':
            if gdf.crs != "EPSG:4326": gdf = gdf.to_crs("EPSG:4326")
            gdf.to_file(out_path + ".kml", driver='KML')
        elif fmt == 'geojson':
            if gdf.crs != "EPSG:4326": gdf = gdf.to_crs("EPSG:4326")
            gdf.to_file(out_path + ".geojson", driver='GeoJSON')
        elif fmt == 'gpkg':
            gdf.to_file(out_path + ".gpkg", driver='GPKG', layer=out_name)

if __name__ == "__main__":
    def open_browser(): time.sleep(1); webbrowser.open(f"http://localhost:{PORT}")
    if HAS_GEOPANDAS:
        threading.Thread(target=open_browser).start()
        print(f"✅ GEO V11 RODANDO! Acesse: http://localhost:{PORT}")
        # Usa ThreadingTCPServer para não travar em múltiplos requests
        with socketserver.ThreadingTCPServer(("", PORT), GeoHandler) as httpd:
            try: httpd.serve_forever()
            except KeyboardInterrupt: pass
    else: print("Instale Geopandas!")
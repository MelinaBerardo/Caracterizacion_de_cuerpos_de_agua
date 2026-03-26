# aquaraster.py — Aplicación Flask principal

from flask import Flask, render_template, url_for, request, redirect, flash, session, jsonify, send_from_directory, make_response
from datetime import datetime
from werkzeug.utils import secure_filename
import uuid
import shutil

# --- Importar funciones de procesamiento
from core.carga import  convertir_a_tiff
from core.recorte import needs_cropping, aplicar_recorte, MAX_DIMENSION
from core.utils import create_preview_image, get_band_paths_from_session

# --- Bibliotecas base
import os
import pandas as pd

# --- Auth y DB
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from bdate import db, User
from forms import LoginForm, RegisterForm
from werkzeug.security import generate_password_hash, check_password_hash

# --- Reporte y descarga
import json
from weasyprint import HTML


app = Flask(__name__)
app.config.from_mapping(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'dev'),
    UPLOAD_FOLDER=os.path.join(os.getcwd(), 'uploads'),
    ALLOWED_EXTENSIONS={'.tif', '.tiff', '.jp2'},
    # --- Configuración Base de Datos ---
    SQLALCHEMY_DATABASE_URI='sqlite:///db.sqlite3',
    SQLALCHEMY_TRACK_MODIFICATIONS=False
)

# Inicializar DB y Login Manager
db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'login' # A dónde redirigir si no está logueado
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Crear tablas DB si no existen
with app.app_context():
    db.create_all()


# Crear carpeta de subida si no existe
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def allowed_file(filename):
    _, ext = os.path.splitext(filename)
    return ext.lower() in app.config['ALLOWED_EXTENSIONS']

def get_session_folder():
    """Crea y retorna carpeta única por sesión"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    session_folder = os.path.join(app.config['UPLOAD_FOLDER'], session['session_id'])
    os.makedirs(session_folder, exist_ok=True)
    return session_folder


def today(date):
    """Filtro de plantilla para formatear fechas."""
    return date.strftime('%d-%m-%Y')

app.add_template_filter(today, 'today')


# RUTAS DE AUTENTICACIÓN (LOGIN / REGISTER)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        flash('Ya tienes una sesión iniciada.', 'info')
        return redirect(url_for('index'))
        
    form = RegisterForm()
    
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data, method='scrypt')
        new_user = User(username=form.username.data, password=hashed_password)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('¡Cuenta creada exitosamente! Ahora puedes ingresar.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Error al crear usuario: {e}', 'error')
            
    return render_template('auth/register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    form = LoginForm()
    
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        
        if user and check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            flash(f'Bienvenido de nuevo, {user.username}', 'success')
            
            # Redirigir a la página que intentaba acceder o al inicio
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('upload'))
        else:
            flash('Usuario o contraseña incorrectos', 'error')
            
    return render_template('auth/login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado sesión correctamente.', 'info')
    return redirect(url_for('index'))

# endpoint pagina de inicio
@app.route('/')
def index():
    date = datetime.now()
    return render_template('index.html', date=date)

# endpoint de carga
@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    session_folder = session.get('session_folder')
    session_id = str(uuid.uuid4()) 
    session['upload_id'] = session_id

    if not session_folder:
        session_folder = get_session_folder()
        session['session_folder'] = session_folder

    
    
    band_names = {
        "band_blue": "band_blue",
        "band_green": "band_green",
        "band_red": "band_red",
        "band_nir": "band_nir",
        "band_swir": "band_swir"
    }
    
    if request.method == 'POST':
        errores = []
        bandas_cargadas = {}


        #  PROCESAR BANDAS
        for campo, nombre_estandar in band_names.items():
            file = request.files.get(campo)

            if file and file.filename != "":
                if allowed_file(file.filename):
                    
                    filename = secure_filename(f"{nombre_estandar}_{file.filename}")
                    filepath = os.path.join(session_folder, filename)
                    file.save(filepath)

                    #  Convertir si no es GeoTIFF
                    ruta_final = convertir_a_tiff(filepath)
                    if ruta_final is None:
                        errores.append(f"❌ No se pudo convertir {nombre_estandar.upper()} a GeoTIFF.")
                        os.remove(filepath)
                        continue
                    
                    bandas_cargadas[nombre_estandar] = {
                        "filename": os.path.basename(ruta_final),
                        "size": os.path.getsize(ruta_final)
                    }
                else:
                    errores.append(f"❌ Formato no válido para {nombre_estandar.upper()}")

        session["bandas_cargadas"] = bandas_cargadas


        if errores:
            for e in errores:
                flash(e, "error")
            return redirect(url_for("upload"))

        # Verificar que están las 5 bandas
        if len(bandas_cargadas) != 5:
            faltan = set(band_names.values()) - set(bandas_cargadas.keys())
            faltan_str = ", ".join(faltan)
            flash(f"Faltan bandas: {faltan_str}", "error")
            return redirect(url_for("upload"))


        # Verificar si necesitan recorte
        band_paths_only = {
            nombre: os.path.join(session_folder, data["filename"])
            for nombre, data in bandas_cargadas.items()
        }

        should_crop, width, height = needs_cropping(band_paths_only)

        if should_crop:
            flash(f"Las bandas ({width}x{height}) exceden {MAX_DIMENSION}px. Recorta para continuar.", "warning")
            return redirect(url_for("crop_interface"))

        # procesar
        flash("Bandas cargadas y validadas correctamente.", "success")
        return redirect(url_for("process"))

    # GET
    bandas_info = session.get("bandas_cargadas", {})
    hay_bandas_cargadas = (len(bandas_info) == 5) 
    
    return render_template("upload.html", 
                           bandas_info=bandas_info, 
                           hay_bandas_cargadas=hay_bandas_cargadas)

# endpoint de recorte
@app.route('/crop', methods=['GET', 'POST'])
@login_required
def crop_interface():
    try:
        bandas_cargadas = session.get('bandas_cargadas', {})
        
        # Validacion de Seguridad
        if len(bandas_cargadas) != 5:
            flash("Debes subir las 5 bandas antes de acceder al recorte.", 'error')
            return redirect(url_for('upload'))

        session_folder = get_session_folder()
        band_paths_only = get_band_paths_from_session(session_folder)
        if not band_paths_only:
             flash("Error de sesión al reconstruir rutas.", 'error')
             return redirect(url_for('upload'))
        
        # Llamada a 'needs_cropping' (UNA SOLA VEZ)
        should_crop, width, height = needs_cropping(band_paths_only)
        
        # Flag para permitir recorte opcional incluso si no excede el límite
        force_crop = request.args.get('force') in ('1', 'true', 'True', 'yes', 'on')

        #  MANEJO DE MÉTODO GET
        if request.method == 'GET':
            
            # Si NO necesita recorte, redirigir
            if not should_crop and not force_crop:
                flash("Las imágenes ya cumplen con el límite de tamaño. (Puedes recortar opcionalmente desde el botón de recorte).", 'success')
                return redirect(url_for('process')) 
            
            # Si SÍ necesita recorte, generar preview   
            ref_path = band_paths_only[list(band_paths_only.keys())[0]]  
            preview_url, scale_factor = create_preview_image(ref_path, session_folder)

            if preview_url is None:
                 raise Exception("La URL de previsualización es nula.")
            
            return render_template('crop.html', 
                                   original_width=width, 
                                   original_height=height, 
                                   max_dim=MAX_DIMENSION,
                                   preview_url=preview_url,
                                   scale_factor=scale_factor,
                                   recorte_obligatorio=should_crop)
                                   

        # MANEJO DE MÉTODO POST 
        elif request.method == 'POST':
            data = request.get_json()
            
            if not data:
                return jsonify({'success': False, 'error': 'No se recibieron datos de recorte (JSON).'}), 400
            
            x_start = int(data.get('x1'))
            y_start = int(data.get('y1'))
            x_end = int(data.get('x2'))
            y_end = int(data.get('y2'))
            
            cropped_paths = aplicar_recorte(band_paths_only, x_start, y_start, x_end, y_end, session_folder)
            
            # Actualizar la sesión 
            for nombre, path in cropped_paths.items():
                 bandas_cargadas[nombre]['filename'] = os.path.basename(path) 
                 bandas_cargadas[nombre]['size'] = os.path.getsize(path)
            
            session['bandas_cargadas'] = bandas_cargadas
            session['recorte_aplicado'] = True

            return jsonify({ 
                'success': True, 
                'message': 'Recorte aplicado con éxito.', 
                'redirect': url_for('process') 
            })

    
    except Exception as e:
        app.logger.error(f"Error fatal en la interfaz de recorte: {e}", exc_info=True)
        flash(f"❌ Error crítico en el recorte: {e}", 'error')
        return redirect(url_for('upload'))

# endpoint archivos temporales
@app.route('/static_file/<path:filename>')
def static_file(filename):
    """
    Sirve archivos estáticos/temporales desde la carpeta UPLOAD_FOLDER (uploads/<session_id>/<filename>)
    """
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# endpoint para limpiar bandas de la sesion actual
@app.route('/clear_bands')
def clear_bands():
    # Recuperar ID de la carpeta actual desde la sesión
    folder_id = session.get('upload_id')
    
    if folder_id:
        # Construir la ruta completa a la carpeta de esa sesión
        folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder_id)
        
        # si la carpeta existe en el disco borrar
        if os.path.exists(folder_path):
            try:
                shutil.rmtree(folder_path)
                app.logger.info(f"Limpieza: carpeta {folder_id} eliminada del disco.")
            except OSError as e:
                app.logger.error(f"Error al borrar la carpeta {folder_id}: {e}")
        else:
            app.logger.info(f"Limpieza: carpeta {folder_id} no existía en disco.")

    # Limpiar las variables de sesión 
    session.pop('bandas_cargadas', None)
    session.pop('config_procesamiento', None)
    session.pop('resultados_filename', None)
    session.pop('uploaded_files', None)
    session.pop('upload_id', None) 

    flash("Se ha limpiado la carga y eliminado los archivos temporales.", "info")
    return redirect(url_for('upload')) # Redirige de vuelta a la carga

# endpoint pagina de procesamiento
@app.route('/process', methods=['GET', 'POST'])
@login_required
def process():
    # Validar que las bandas existan en la sesión
    if 'bandas_cargadas' not in session or len(session.get('bandas_cargadas', {})) != 5:
        flash('⚠️ Primero debes cargar las 5 bandas', 'warning')
        return redirect(url_for('upload'))
    
    if request.method == 'POST':
        try:
            # Leer los campos de los sliders
            config = {
                'metodo_deteccion': request.form.get('metodo_deteccion', 'mndwi'),
                'min_size_initial': int(request.form.get('min_size_initial', 5)),
                'closing_width': int(request.form.get('closing_width', 5)),
                'closing_height': int(request.form.get('closing_height', 5)),
                'closing_iterations': int(request.form.get('closing_iterations', 3)),
                'min_size_final': int(request.form.get('min_size_final', 5))
            }
            
            session['config_procesamiento'] = config
            flash('🔄 Procesamiento iniciado...', 'info')
            return redirect(url_for('execute_processing'))
        
        except ValueError as e:
            flash(f'❌ Error en parámetros: {str(e)}', 'error')
            return redirect(url_for('process'))
        except Exception as e:
            flash(f'❌ Error inesperado: {str(e)}', 'error')
            return redirect(url_for('process'))
    
    # --- LÓGICA GET ---
    # Cargar la configuración guardada (o valores por defecto)
    config_guardada = session.get('config_procesamiento', {
        'metodo_deteccion': 'completo',
        'min_size_initial': 5,
        'closing_width': 5,
        'closing_height': 5,
        'closing_iterations': 3,
        'min_size_final': 5
    })
    
    return render_template(
        'process.html',
        config=config_guardada 
    )

# endpoint previsualizacionde la limpieza configurada
@app.route('/preview_cleaning', methods=['POST'])
@login_required
def preview_cleaning():
    bandas_cargadas = session.get('bandas_cargadas')
    if not bandas_cargadas or len(bandas_cargadas) < 5:
        return jsonify({'error': 'No hay bandas cargadas o faltan para previsualizar.'}), 400

    try:
        data = request.get_json()
        min_size_initial= int(data.get('min_size_initial', 5))
        closing_width = int(data.get('closing_width', 5))
        closing_height = int(data.get('closing_height', 5))
        closing_iterations = int(data.get('closing_iterations', 3))
        min_size_final= int(data.get('min_size_final', 5))
        metodo_deteccion = data.get('metodo_deteccion', 'mndwi')

        # diccionario de las rutas de las bandas cargadas
        session_folder = get_session_folder()
        bandas_paths = get_band_paths_from_session(session_folder)
        if not bandas_paths:
             return jsonify({'error': 'Error de sesión al reconstruir rutas.'}), 400
        
        from core.limpieza import previsualizar_limpieza
        
        preview_images = previsualizar_limpieza(
            bandas_paths,
            metodo_deteccion,
            min_size_initial,
            closing_width,
            closing_height,
            closing_iterations,
            min_size_final
        )
        
        return jsonify(preview_images)

    except Exception as e:
        app.logger.error(f"Error en previsualización de limpieza: {e}")
        return jsonify({'error': f'Error en previsualización: {str(e)}'}), 500

# endpoint analisis (ejecuta el proceso configurado en template)
@app.route('/execute_processing')
@login_required
def execute_processing():
    """Ejecuta el procesamiento y genera resultados"""
    
    if 'bandas_cargadas' not in session or 'config_procesamiento' not in session:
        flash('⚠️ Configuración incompleta o bandas no encontradas', 'warning')
        return redirect(url_for('process'))
    
    try:
        from core.procesamiento import procesar_bandas
        
        config = session['config_procesamiento']
        session_folder = get_session_folder() 

        bandas_paths = get_band_paths_from_session(session_folder)
        if not bandas_paths:
            flash('❌ Error al reconstruir las rutas de las bandas', 'error')
            return redirect(url_for('process'))

        resultados_filename = procesar_bandas(bandas_paths, config, session_folder)

        resultados_path = os.path.join(session_folder, resultados_filename)
        with open(resultados_path, 'r') as f:
            resultados_data = json.load(f)
        
        metodo_clave = resultados_data.get('metodo', 'mndwi')
        num_regiones = resultados_data.get(metodo_clave, {}).get('num_regiones', 0)

        session['resultados_filename'] = resultados_filename
        session['resultados_num_regiones'] = num_regiones

        flash('✅ Procesamiento completado exitosamente', 'success')
        return redirect(url_for('results'))
        
    except Exception as e:
        app.logger.error(f"Error fatal en execute_processing: {e}", exc_info=True)
        flash(f'❌ Error crítico en procesamiento: {str(e)}', 'error')
        return redirect(url_for('process'))

# endpoint pagina de resultados
@app.route('/results')
@login_required
def results():
    # Validar que las bandas existan en la sesión
    if 'bandas_cargadas' not in session or len(session['bandas_cargadas']) != 5:
        flash(' Primero debes cargar las bandas y procesarlas', 'warning')
        return redirect(url_for('upload'))

    # Verificar si el nombre del archivo de resultados existe en la sesión
    if 'resultados_filename' not in session:
        return render_template('results.html', resultados=None) 
    

    try:
        # carpeta de sesión y nombre del archivo
        session_folder = get_session_folder()
        resultados_filename = session['resultados_filename']
        resultados_path = os.path.join(session_folder, resultados_filename)
        
        # Cargar los resultados del archivo JSON
        with open(resultados_path, 'r') as f:
            resultados = json.load(f)
            
        # Pasar el diccionario cargado a la plantilla
        return render_template('results.html', resultados=resultados)
        
    except Exception as e:
        # En caso de que el archivo se haya borrado, esté corrupto, o haya fallado la lectura
        flash(f'❌ Error al cargar resultados desde el archivo: {str(e)}', 'error')
        return render_template('results.html', resultados=None)

# endpoint pagina para exportar 
@app.route('/export')
def export():
    return render_template('export.html')

# endpoint descarga de reporte
@app.route('/download_report/<format>')
@login_required
def download_report(format):
    if 'resultados_filename' not in session:
        flash('No hay reporte para descargar. Inicia un procesamiento primero.', 'error')
        return redirect(url_for('export'))
        
    session_folder = get_session_folder()
    json_filename = session['resultados_filename']
    json_path = os.path.join(session_folder, json_filename)
    
    if not os.path.exists(json_path):
        flash('Error: No se encontró el archivo de resultados.', 'error')
        return redirect(url_for('export'))
        
    try:
        # Cargar el JSON 
        with open(json_path, 'r') as f:
            resultados = json.load(f)
        
        metodo_clave = resultados.get('metodo', 'mndwi')
        analisis_data = resultados.get(metodo_clave, {}).get('analisis', [])
        
        # - Lógica por Formato ---
        
        if format == 'json':
            # Descargar el JSON original
            return send_from_directory(session_folder, json_filename, as_attachment=True)
            
        elif format == 'csv':
            # Convertir a CSV usando Pandas
            if not analisis_data:
                flash('El reporte JSON no contenía datos de análisis para el CSV.', 'warning')
                return redirect(url_for('export'))
                
            df = pd.json_normalize(analisis_data) 
            csv_filename = os.path.splitext(json_filename)[0] + '.csv'
            csv_path = os.path.join(session_folder, csv_filename)
            df.to_csv(csv_path, index=False)
            
            # Descargar el CSV
            return send_from_directory(session_folder, csv_filename, as_attachment=True)
            
        elif format == 'pdf':
            # Renderizar la plantilla HTML como string
            html_out = render_template('results.html', resultados=resultados)
            # Conversión a PDF usando WeasyPrint
            pdf_file = HTML(string=html_out).write_pdf()
            response = make_response(pdf_file)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = 'attachment; filename=AquaRaster_Reporte.pdf'
            return response
            
        else:
            flash('Formato de descarga no válido.', 'error')
            return redirect(url_for('export'))
            
    except Exception as e:
        flash(f'Error al generar el archivo de descarga: {e}', 'error')
        return redirect(url_for('export'))

if __name__ == '__main__':
    app.run(debug=True)
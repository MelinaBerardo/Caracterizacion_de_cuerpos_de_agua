# AquaRaster

**Trabajo de Prácticas Profesionales - Ingeniería en Telecomunicaciones** 

**Autora:** Melina Aylén Berardo  

**Tutores:** Primo, Damián Héctor y Tosco, Sebastián

**Institución:** Universidad Nacional de Río Cuarto (UNRC) - Facultad de Ingeniería  

**Lugar de desarrollo:** GIDAT - Grupo de Investigación y Desarrollo Aplicado a las Telecomunicaciones

**Año:** 2026  

---

Aplicación web para la detección y caracterización de cuerpos de agua a partir de imágenes satelitales multibanda. Permite cargar bandas espectrales (Blue, Green, Red, NIR, SWIR) en formato tiff o jp2, aplicar índices de agua, limpiar morfológicamente las regiones detectadas y exportar los resultados a PDF.

---

## Índice

* [Instalación](#instalación)
* [Tecnologías](#tecnologías)
* [Uso](#uso)
* [Licencia](#licencia)

---

## Instalación

**Requisitos previos:** tener instalado [Docker](https://docs.docker.com/get-docker/) y [Docker Compose](https://docs.docker.com/compose/install/).

1. Clonar el repositorio:

```bash
git clone https://github.com/MelinaBerardo/Caracterizacion_de_cuerpos_de_agua.git
cd Caracterizacion_de_cuerpos_de_agua
```

2. Crear el archivo de variables de entorno:

```bash
cp .env.example .env
```

3. Editar `.env` y reemplazar `SECRET_KEY` con una clave segura generada así:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

4. Construir y levantar el contenedor:

```bash
docker compose up -d --build
```

5. Abrir en el navegador: `http://localhost:8000`

> Los datos de usuarios y archivos procesados se persisten localmente en `db.sqlite3` y `uploads/` mediante volúmenes Docker. No se pierden al reiniciar el contenedor.

Para detener:

```bash
docker compose down
```

---

## Tecnologías

- [Flask](https://flask.palletsprojects.com/) — framework web
- [Rasterio](https://rasterio.readthedocs.io/) / [GDAL](https://gdal.org/) — lectura de rasters geoespaciales
- [scikit-image](https://scikit-image.org/) — morfología y detección de regiones
- [pyproj](https://pyproj4.github.io/pyproj/) — transformación de sistemas de coordenadas
- [WeasyPrint](https://weasyprint.org/) — generación de reportes PDF
- [Gunicorn](https://gunicorn.org/) — servidor WSGI para producción
- [SQLite](https://www.sqlite.org/) + [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/) — base de datos de usuarios
- [Docker](https://www.docker.com/) — contenedorización y despliegue

---
## Estructura del Proyecto

```
AQUARASTER_APP
│
├── aquaraster.py              # Aplicación Flask principal: rutas y configuración
├── bdate.py                   # Modelos de base de datos (SQLAlchemy) y tabla de usuarios
├── forms.py                   # Formularios de login y registro (Flask-WTF)
├── requirements.txt           # Dependencias Python del proyecto
│
├── README.md                  # Documentación y guía de despliegue
├── Dockerfile                 # Imagen Docker de la aplicación
├── docker-compose.yml         # Orquestación: puertos, volúmenes y variables de entorno
├── .dockerignore              # Archivos excluidos al construir la imagen Docker
├── .env.example               # Plantilla de variables de entorno 
├── .gitignore                 # Archivos excluidos del repositorio Git
├── LICENSE                    # Licencia MIT
│
├── core                       # Módulos de procesamiento satelital
│   ├── __init__.py            # Marca core/ como paquete Python
│   ├── carga.py               # Conversión de formatos raster (GDAL)
│   ├── caracterizacion.py     # Profundidad, turbidez y morfología de regiones
│   ├── georeferenciacion.py   # Transformación de coordenadas
│   ├── indices.py             # Índices espectrales: MNDWI, USI, filtro de techos
│   ├── limpieza.py            # Limpieza morfológica y detección de regiones
│   ├── procesamiento.py       # Pipeline principal de procesamiento
│   ├── recorte.py             # Recorte espacial de bandas raster
│   └── utils.py               # Utilidades: normalización e imágenes base64
│
├── templates                  # Plantillas HTML (Jinja2)
│   ├── base.html              # Layout base: navegación, flash messages, footer
│   ├── crop.html              # Interfaz de recorte interactivo
│   ├── export.html            # Descarga de resultados en CSV y PDF
│   ├── index.html             # Página de inicio
│   ├── process.html           # Configuración de parámetros de procesamiento
│   ├── results.html           # Visualización de resultados por región
│   ├── upload.html            # Carga de las 5 bandas espectrales
│   └── auth
│       ├── login.html         # Formulario de inicio de sesión
│       └── register.html      # Formulario de registro de usuario
│
├── static                     # Archivos estáticos servidos por Flask
│   ├── css
│   │   └── style.css          # Estilos globales de la aplicación
│   └── js
│       ├── crop.js            # Lógica de selección y envío del recorte
│       ├── process.js         # Previsualización dinámica de limpieza (jQuery + AJAX)
│       └── upload.js          # Validación y drag & drop de bandas
│
├── instance
│   └── db.sqlite3             # Base de datos de usuarios ← excluida de Git
│
├── uploads                    # Archivos subidos por usuarios ← excluidos de Git
│   └── .gitkeep               # Marcador para que Git registre la carpeta vacía
│
└── examples                   # Imágenes satelitales de ejemplo ← excluidas de Git
    ├── frontera  
    ├── piedras_moras_enero2024   
    ├── RioCuarto_Landsat    
    ├── RioCuarto_Sentinel   
    └── villa_dalcar_enero2017
```

## Uso

Una vez levantada la aplicación, el flujo es:

1. **Registrarse** e iniciar sesión.
2. **Cargar las 5 bandas** espectrales en formato `.tif`, `.tiff` o `.jp2`: Blue, Green, Red, NIR, SWIR.
3. **Recortar** el área de interés si las imágenes superan 3000×3000 píxeles (obligatorio) o para analizar solo una zona (opcional).
4. **Configurar** los parámetros de detección y limpieza morfológica.
5. **Previsualizar** el resultado antes de procesar.
6. **Ejecutar** el procesamiento completo.
7. **Explorar** los resultados por región detectada: área, perímetro, turbidez, profundidad estimada, morfología y coordenadas geográficas.
8. **Exportar** en CSV o PDF.

### Datos de Ejemplo (Imágenes Satelitales)

Se han preparado distintos conjuntos de bandas espectrales (por ejemplo: Río Cuarto, Piedras Moras, Villa Dalcar). Debido al gran volumen de datos (archivos `.tif` pesados), estos no se incluyen en el repositorio de GitHub.
**Para utilizarlos:**
1. Descargar los datos de ejemplo desde el siguiente enlace: `[https://drive.google.com/file/d/1qko-K2TYgbW8JXLM5IjldD1F-rWngMFg/view?usp=sharing]`
2. Extraer los archivos en su computadora local.
3. En la aplicación web, ir a la sección de "Carga de bandas" y seleccionar las 5 bandas correspondientes a la escena que desee probar.

### Métodos de detección disponibles

| Método | Descripción |
|---|---|
| `mndwi` | Índice MNDWI (Green − SWIR). Detección rápida. Para entornos no urbanos |
| `completo` | MNDWI + USI (elimina sombras urbanas) + filtro de techos brillantes. |
---

## Licencia

MIT

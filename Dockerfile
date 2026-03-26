# Dockerfile

# 1. Imagen Base
FROM python:3.12-slim

# 4. Directorio de Trabajo
WORKDIR /app

# 2. Configuración de Entorno
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal
ENV FLASK_APP=aquaraster.py
ENV PYTHONUNBUFFERED=1

# 3. Instalar dependencias del sistema 
# - libgdal-dev: lectura de rasters .tif, .jp2 y otros formatos geoespaciales
# - libpango-1.0-0, libpangoft2-1.0-0, libpangocairo-1.0-0: renderizado de texto para WeasyPrint
# - libcairo2, libgdk-pixbuf2.0-0, libffi-dev: gráficos y exportación PDF con WeasyPrint
# - libxml2, libxslt1.1: parseo de HTML/CSS necesario para WeasyPrint
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    build-essential \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && apt-get clean && rm -rf /var/lib/apt/lists/*


# 5. Instalar Dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copiar el Código de la Aplicación
COPY . . 

# 7. Exponer Puerto: Documenta el puerto que usará el servidor Gunicorn
EXPOSE 8000

# 8. Comando de Inicio 
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "aquaraster:app"] 

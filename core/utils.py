# FUNCIONES VISUALIZACION Y PROCESAMIENTO
#----------------------------------------
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import rasterio
from flask import url_for, session
from scipy.ndimage import gaussian_filter
import base64
from io import BytesIO
from skimage.measure import find_contours

from PIL import Image

def cargar_arrays_desde_paths(bandas_paths):
    """
    Carga los arrays de las bandas desde los archivos.
    
    Args:
        bandas_paths (dict): Diccionario con rutas de bandas
    
    Returns:
        tuple: (band_arrays, band_transforms, band_crs)
    """
    band_arrays = {}
    band_transforms = {}
    band_crs = {}
    
    for nombre, path in bandas_paths.items():
        with rasterio.open(path) as src:
            band_arrays[nombre] = src.read(1).astype(float)
            band_transforms[nombre] = src.transform
            band_crs[nombre] = src.crs
    
    return band_arrays, band_transforms, band_crs

def normalize(array):
    """Normalizacion de (0-1)"""
    if array.max() != array.min():
        return (array - array.min()) / (array.max() - array.min())
    else:
        return np.zeros_like(array)

def filtro_gaussiano(imagen, sigma=3):
    """Aplica un filtro gaussiano a la imagen."""
    return gaussian_filter(imagen, sigma=sigma)

def create_preview_image(band_path, session_folder):
    """Genera una imagen de previsualización reducida de la banda."""
    try:
        with rasterio.open(band_path) as src:
            MAX_PREVIEW_DIM = 1000

            scale = MAX_PREVIEW_DIM / max(src.width, src.height)

            if scale < 1:
                new_h = int(src.height * scale)
                new_w = int(src.width * scale)
                array = src.read(1, out_shape=(new_h, new_w)).astype(np.float32)
                scale_factor = src.width / new_w
            else:
                array = src.read(1).astype(np.float32)
                scale_factor = 1.0

            array[array == 0] = np.nan

            p2, p98 = np.nanpercentile(array, (2, 98))
            array_norm = np.clip(array, p2, p98)
            denom = (p98 - p2)
            if denom == 0: denom = 1
            array_norm = (array_norm - p2) / denom

            plt.ioff()
            h, w = array_norm.shape
            fig, ax = plt.subplots(figsize=(w/100, h/100), dpi=100)

            ax.imshow(array_norm, cmap='gray')
            ax.axis('off')
            plt.subplots_adjust(left=0, right=1, top=1, bottom=0)

            preview_filename = f"preview_{os.path.basename(band_path)}.png"
            preview_filepath = os.path.join(session_folder, preview_filename)

            plt.savefig(preview_filepath, bbox_inches='tight', pad_inches=0)
            plt.close(fig)
            plt.ion()

            preview_url = url_for('static_file', filename=f"{session['session_id']}/{preview_filename}")

            return preview_url, scale_factor

    except Exception as e:
        print(f"Error en create_preview_image: {e}")
        return None, None

def generar_imagen_base64(array, cmap='gray'):
    """Convierte un array numpy a imagen base64 para visualización web"""
    if array is None:
        return ""

    if array.dtype == bool:
        array_norm = array.astype(np.uint8) * 255
    else:
        array_norm = (normalize(array) * 255).astype(np.uint8)

    img = Image.fromarray(array_norm)

    if cmap != 'gray' and array.dtype != bool:
        img = img.convert('L')

    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

def generar_imagen_base64_mask_completa(band_arrays, mask_limpia, cmap='Blues'):
    """Genera la máscara completa de agua superpuesta en falso color (NIR-SWIR-Blue) como Base64."""
    rgb = np.dstack((
        normalize(band_arrays['band_nir']),
        normalize(band_arrays['band_swir']),
        normalize(band_arrays['band_blue'])
    ))

    plt.ioff()
    fig, ax = plt.subplots(figsize=(8, 12))

    ax.imshow(rgb)
    ax.imshow(mask_limpia, cmap=cmap, alpha=0.3)
    ax.set_title("Mascara de agua")
    ax.axis("off")
    plt.tight_layout()

    buffered = BytesIO()
    plt.savefig(buffered, format="PNG")
    plt.close(fig)
    plt.ion()

    return base64.b64encode(buffered.getvalue()).decode()

def generar_imagen_base64_zoom(band_arrays, mask_region, region_props, region_id, cmap='Blues'):
    """Genera la imagen de la región recortada con la máscara superpuesta como Base64"""
    minr, minc, maxr, maxc = region_props.bbox
    alto = maxr - minr
    ancho = maxc - minc
    margen_pixeles = int(max(alto, ancho) * 4.0)

    r_min = max(0, minr - margen_pixeles)
    r_max = min(band_arrays['band_red'].shape[0], maxr + margen_pixeles)
    c_min = max(0, minc - margen_pixeles)
    c_max = min(band_arrays['band_red'].shape[1], maxc + margen_pixeles)

    nir_zoom = band_arrays['band_nir'][r_min:r_max, c_min:c_max].astype(float)
    swir_zoom = band_arrays['band_swir'][r_min:r_max, c_min:c_max].astype(float)
    blue_zoom = band_arrays['band_blue'][r_min:r_max, c_min:c_max].astype(float)

    rgb_zoom = np.dstack((normalize(nir_zoom), normalize(swir_zoom), normalize(blue_zoom)))
    mask_recortada = mask_region[r_min:r_max, c_min:c_max]

    plt.ioff()
    fig, ax = plt.subplots(figsize=(6, 6))

    ax.imshow(rgb_zoom)
    ax.imshow(mask_recortada, cmap=cmap, alpha=0.5)
    ax.set_title(f"Región {region_id}")
    ax.axis("off")
    plt.tight_layout()

    buffered = BytesIO()
    plt.savefig(buffered, format="PNG")
    plt.close(fig)
    plt.ion()

    return base64.b64encode(buffered.getvalue()).decode()

def generar_imagen_base64_con_ids(mask_limpia, props, metodo_deteccion):
    """Genera la máscara limpia con los IDs de las regiones como Base64"""
    plt.ioff()
    fig, ax = plt.subplots(figsize=(8, 8))

    ax.imshow(mask_limpia, cmap='Blues')

    for i, prop in enumerate(props, 1):
        y, x = prop.centroid
        ax.text(x, y, str(i), color="#C4672D", fontsize=16,
                ha='center', va='center', weight="bold")

    ax.set_title(f"Cuerpos de Agua Detectados ({len(props)} regiones) - {metodo_deteccion.upper()}")
    ax.axis("off")
    plt.tight_layout()

    buffered = BytesIO()
    plt.savefig(buffered, format="PNG")
    plt.close(fig)
    plt.ion()

    return base64.b64encode(buffered.getvalue()).decode()

def generar_imagen_rgb_con_bordes(band_arrays, mask_limpia, metodo_deteccion):
    """Genera una imagen True-Color (RGB) con los bordes de la máscara de agua superpuestos"""
    try:
        r = normalize(band_arrays['band_red'])
        g = normalize(band_arrays['band_green'])
        b = normalize(band_arrays['band_blue'])
    except KeyError as e:
        print(f"Error: Faltan bandas RGB para generar imagen de bordes. {e}")
        return ""

    p2, p98 = np.percentile(np.dstack((r, g, b)), (2, 98))
    rgb_image = np.clip((np.dstack((r, g, b)) - p2) / (p98 - p2), 0, 1)

    contours = find_contours(mask_limpia.astype(int), 0.5)

    plt.ioff()
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.imshow(rgb_image)
    ax.set_title(f'Bordes Detectados ({metodo_deteccion.upper()})')

    for contour in contours:
        ax.plot(contour[:, 1], contour[:, 0], linewidth=1.5, color='cyan')

    ax.axis('off')
    plt.tight_layout()

    buffered = BytesIO()
    plt.savefig(buffered, format="PNG")
    plt.close(fig)
    plt.ion()

    return base64.b64encode(buffered.getvalue()).decode()

def generar_imagen_contexto_global(band_arrays, mask_limpia_total, mask_region_especifica, region_props_especifica, region_id):
    """Genera falso color global resaltando el borde e ID de la región específica"""
    rgb = np.dstack((
        normalize(band_arrays['band_nir']),
        normalize(band_arrays['band_swir']),
        normalize(band_arrays['band_blue'])
    ))

    plt.ioff()
    fig, ax = plt.subplots(figsize=(10, 10))

    ax.imshow(rgb)
    ax.imshow(mask_limpia_total, cmap='Blues', alpha=0.3)

    contours = find_contours(mask_region_especifica.astype(int), 0.5)

    for contour in contours:
        ax.plot(contour[:, 1], contour[:, 0], linewidth=2.0, color='cyan')

    y, x = region_props_especifica.centroid
    ax.text(x, y, str(region_id), color="#C4672D", fontsize=16,
            ha='center', va='center', weight="bold",
            bbox=dict(boxstyle="circle,pad=0.2", fc="white", ec="none", alpha=0.6))

    ax.set_title(f"Contexto Global - Resaltando Región {region_id}")
    ax.axis("off")
    plt.tight_layout()

    buffered = BytesIO()
    plt.savefig(buffered, format="PNG")
    plt.close(fig)
    plt.ion()

    return base64.b64encode(buffered.getvalue()).decode()

def get_band_paths_from_session(session_folder):
    """Reconstruye el diccionario de paths usando los filenames de la sesión"""
    bandas_info = session.get('bandas_cargadas', {})
    if not bandas_info or len(bandas_info) < 5:
        return None

    band_paths_only = {}
    for nombre, data in bandas_info.items():
        band_paths_only[nombre] = os.path.join(session_folder, data['filename'])
    return band_paths_only

def generar_grafico_firma_espectral(reflectancias):
    """Genera un gráfico de firma espectral y lo retorna como base64"""
    bandas_orden = ['azul', 'verde', 'rojo', 'nir', 'swir']
    valores = [reflectancias[b] for b in bandas_orden]
    etiquetas = ['Azul', 'Verde', 'Rojo', 'NIR', 'SWIR']
    colores = ['blue', 'green', 'red', 'darkred', 'brown']

    plt.ioff()
    fig, ax = plt.subplots(figsize=(5, 3))

    ax.plot(etiquetas, valores, marker='o', linestyle='-', color='black', alpha=0.6, linewidth=1)
    ax.scatter(etiquetas, valores, c=colores, s=50, zorder=5)

    ax.set_title("Firma Espectral Media", fontsize=10)
    ax.set_ylabel("Reflectancia", fontsize=8)
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.tick_params(axis='both', which='major', labelsize=8)

    plt.tight_layout()

    buffered = BytesIO()
    plt.savefig(buffered, format="PNG", dpi=100)
    plt.close(fig)
    plt.ion()

    return base64.b64encode(buffered.getvalue()).decode()

def generar_imagen_base64_profundidad(profundidad_mapa, mask_region):
    """
    Genera una imagen coloreada del mapa de profundidad estimada por píxel.
    Solo muestra los píxeles dentro de la región de agua.
    """
    mapa_visual = np.full_like(profundidad_mapa, np.nan)
    mapa_visual[mask_region] = profundidad_mapa[mask_region]

    plt.ioff()
    fig, ax = plt.subplots(figsize=(6, 6))

    im = ax.imshow(mapa_visual, cmap='Blues_r', interpolation='nearest')
    plt.colorbar(im, ax=ax, label='Profundidad estimada (m)', shrink=0.7)
    ax.set_title("Mapa de Profundidad Estimada")
    ax.axis("off")
    plt.tight_layout()

    buffered = BytesIO()
    plt.savefig(buffered, format="PNG", dpi=100)
    plt.close(fig)
    plt.ion()

    return base64.b64encode(buffered.getvalue()).decode()
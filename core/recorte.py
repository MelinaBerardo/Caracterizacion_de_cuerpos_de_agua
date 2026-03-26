# core/recorte.py - Verificación y aplicación de recorte espacial de bandas raster

import os
import rasterio
from rasterio.windows import from_bounds

# Dimensión máxima permitida por eje (en píxeles) para el procesamiento
MAX_DIMENSION = 3000


def needs_cropping(band_paths_dict):
    """
    Verifica si alguna banda supera el límite de tamaño definido por MAX_DIMENSION.
    Usa la primera banda del dict como referencia (se asume que todas tienen el mismo tamaño).

    Args:
        band_paths_dict (dict): Rutas de las bandas espectrales.

    Returns:
        tuple: (necesita_recorte bool, width int, height int)
    """
    if not band_paths_dict:
        return False, 0, 0

    ruta_ref = list(band_paths_dict.values())[0]
    try:
        with rasterio.open(ruta_ref) as src_ref:
            width, height = src_ref.width, src_ref.height
            return (width > MAX_DIMENSION or height > MAX_DIMENSION), width, height
    except Exception:
        # Si no se puede leer, se recorta por precaución para evitar errores posteriores
        return True, 0, 0


def aplicar_recorte(band_paths_dict, x_start, y_start, x_end, y_end, session_folder):
    """
    Recorta todas las bandas usando coordenadas de píxeles seleccionadas por el usuario.

    Las coordenadas de píxel se convierten a coordenadas geográficas antes de calcular
    la ventana de recorte, lo que garantiza consistencia entre bandas con distintos CRS.

    Args:
        band_paths_dict (dict): Rutas de las bandas espectrales.
        x_start, y_start (int): Esquina superior izquierda del recorte (en píxeles).
        x_end, y_end (int): Esquina inferior derecha del recorte (en píxeles).
        session_folder (str): Carpeta donde se guardan los archivos recortados.

    Returns:
        dict: Rutas de las bandas recortadas, con las mismas claves que band_paths_dict.
    """
    ruta_ref = list(band_paths_dict.values())[0]
    bandas_recortadas = {}

    with rasterio.open(ruta_ref) as src_ref:
        # Convertir coordenadas de píxel a coordenadas geográficas del CRS de la banda
        x_min_geo, y_max_geo = src_ref.xy(y_start, x_start)
        x_max_geo, y_min_geo = src_ref.xy(y_end, x_end)

        window = from_bounds(
            min(x_min_geo, x_max_geo),
            min(y_min_geo, y_max_geo),
            max(x_min_geo, x_max_geo),
            max(y_min_geo, y_max_geo),
            src_ref.transform
        )
        out_transform = src_ref.window_transform(window)

    for nombre_estandar, ruta in band_paths_dict.items():
        with rasterio.open(ruta) as src:
            # Se lee con el dtype original del archivo para no alterar los valores de DN
            banda_recorte = src.read(1, window=window)

            out_meta = src.meta.copy()
            out_meta.update({
                "height": int(window.height),
                "width": int(window.width),
                "transform": out_transform,
                "dtype": banda_recorte.dtype
            })

            # El sufijo _recorte previo se elimina para evitar nombres como banda_recorte_recorte
            base_name = os.path.splitext(os.path.basename(ruta))[0].replace("_recorte", "")
            salida_path = os.path.join(session_folder, f"{base_name}_recorte.tif")

            with rasterio.open(salida_path, "w", **out_meta) as dest:
                dest.write(banda_recorte, 1)

            bandas_recortadas[nombre_estandar] = salida_path

    return bandas_recortadas
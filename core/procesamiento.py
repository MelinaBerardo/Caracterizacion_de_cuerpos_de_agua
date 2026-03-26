# core/procesamiento.py - Lógica principal de procesamiento

import numpy as np
import rasterio
import json
import os
from rasterio.transform import xy
from pyproj import Geod
from core.indices import calcular_mndwi, calcular_usi, generar_mask_techos
from core.limpieza import limpiar_y_detectar_regiones
from core.caracterizacion import (
    analizar_esqueleto,
    calcular_profundidad,
    calcular_ndti_medio_region,
    clasificar_turbidez
)
from core.georeferenciacion import transformador_a_wgs84, obtener_centroide_wgs84
from core.utils import (
    cargar_arrays_desde_paths,
    normalize,
    generar_imagen_base64,
    generar_imagen_base64_zoom,
    generar_imagen_base64_mask_completa,
    generar_imagen_base64_con_ids,
    generar_imagen_rgb_con_bordes,
    generar_imagen_contexto_global,
    generar_grafico_firma_espectral
)

def _calcular_geometria_pixel_robusta(path_raster):
    """
    Calcula el área real del píxel (m²) manejando correctamente sistemas
    geográficos (grados) y proyectados (metros).
    """
    with rasterio.open(path_raster) as src:
        transform = src.transform

        if src.crs.is_geographic:
            # En sistemas geográficos la resolución está en grados, no en metros.
            # Se usan geodésicas sobre el elipsoide WGS84 muestreando desde el centro
            # de la imagen para minimizar la distorsión por latitud.
            try:
                geod = Geod(ellps="WGS84")
                row, col = src.height // 2, src.width // 2

                lon0, lat0 = xy(transform, row, col, offset="center")
                lon_x, lat_x = xy(transform, row, col+1, offset="center")
                lon_y, lat_y = xy(transform, row+1, col, offset="center")

                _, _, dist_x = geod.inv(lon0, lat0, lon_x, lat_x)
                _, _, dist_y = geod.inv(lon0, lat0, lon_y, lat_y)

                res_x_m, res_y_m = abs(dist_x), abs(dist_y)
            except Exception:
                res_x_m, res_y_m = src.res
        else:
            # En sistemas proyectados (UTM, etc.) la resolución ya está en metros
            res_x_m, res_y_m = src.res

        area_m2 = res_x_m * res_y_m
        return area_m2, res_x_m, res_y_m

def procesar_bandas(bandas_paths, config, session_folder):
    """
    Orquesta el pipeline completo: detección de agua, limpieza morfológica,
    análisis de regiones y serialización de resultados a JSON.

    Args:
        bandas_paths (dict): Rutas absolutas de cada banda espectral.
        config (dict): Parámetros de procesamiento elegidos por el usuario.
        session_folder (str): Carpeta de sesión donde se guarda el JSON de salida.

    Returns:
        str: Nombre del archivo JSON con los resultados.
    """
    band_arrays, band_transforms, band_crs = cargar_arrays_desde_paths(bandas_paths)
    pix_area_m2, pix_size_x_m, pix_size_y_m = _calcular_geometria_pixel_robusta(bandas_paths['band_blue'])

    metodo = config.get('metodo_deteccion', 'completo')

    # PASO 1: DETECCIÓN DE AGUA
    # MNDWI siempre se calcula; USI y filtro de techos solo en métodos 'completo' y 'comparar'
    mndwi, mask_mndwi = calcular_mndwi(band_arrays['band_green'], band_arrays['band_swir'])
    mask_sin_techos = None

    resultados = {
        'metodo': metodo,
        'geodatos': {
            'pix_size_x_m': pix_size_x_m,
            'pix_size_y_m': pix_size_y_m,
            'pix_area_m2': pix_area_m2
        },
        'indices': {
            'mndwi': {
                'array': mndwi,
                'mask': mask_mndwi,
                'imagen': generar_imagen_base64(mask_mndwi)
            }
        },
        'comparacion': {}
    }

    if metodo in ['completo', 'comparar']:
        # USI refina la máscara MNDWI eliminando sombras urbanas;
        # el filtro de techos quita brillos especulares de superficies artificiales
        usi, mask_sin_sombras = calcular_usi(
            band_arrays['band_red'],
            band_arrays['band_green'],
            band_arrays['band_blue'],
            band_arrays['band_nir'],
            mask_mndwi,
            mndwi
        )
        mask_techos, mask_sin_techos = generar_mask_techos(
            band_arrays['band_blue'], band_arrays['band_swir'], mask_sin_sombras
        )

        resultados['indices']['usi'] = {
            'array': usi,
            'mask': mask_sin_sombras,
            'imagen': generar_imagen_base64(mask_sin_sombras)
        }
        resultados['indices']['sin_techos'] = {
            'mask': mask_sin_techos,
            'imagen': generar_imagen_base64(mask_sin_techos)
        }

    # PASO 2: LIMPIEZA MORFOLÓGICA Y DETECCIÓN DE REGIONES
    min_size_initial  = config.get('min_size_initial', 5)
    min_size_final    = config.get('min_size_final', 5)
    closing_width     = config.get('closing_width', 5)
    closing_height    = config.get('closing_height', 5)
    closing_iterations = config.get('closing_iterations', 3)

    # A. Procesamiento sobre máscara MNDWI (siempre se ejecuta)
    imagen_mask_cruda_mndwi = generar_imagen_base64(mask_mndwi)

    mask_limpia_mndwi, labels_mndwi, props_mndwi = limpiar_y_detectar_regiones(
        mask_mndwi,
        min_size_initial=min_size_initial,
        min_size_final=min_size_final,
        closing_params=(closing_width, closing_height),
        iterations=closing_iterations,
        mostrar=False
    )

    resultados['mndwi'] = {
        'pixeles_de_agua': np.sum(mask_limpia_mndwi),
        'imagen': generar_imagen_base64(mask_limpia_mndwi),
        'num_regiones': len(props_mndwi),
        'labels': labels_mndwi,
        'props': props_mndwi,
        'imagen_con_ids': generar_imagen_base64_con_ids(mask_limpia_mndwi, props_mndwi, metodo),
        'imagen_rgb_con_bordes': generar_imagen_rgb_con_bordes(band_arrays, mask_limpia_mndwi, metodo),
        'imagen_mask_completa': generar_imagen_base64_mask_completa(band_arrays, mask_limpia_mndwi),
        'imagen_mask_cruda': imagen_mask_cruda_mndwi,
        'imagen_mask_limpia': generar_imagen_base64(mask_limpia_mndwi)
    }

    # B. Procesamiento sobre máscara completa (MNDWI + USI + sin techos)
    if metodo in ['completo', 'comparar']:
        imagen_mask_cruda_completo = generar_imagen_base64(mask_sin_techos)

        mask_limpia_completo, labels_completo, props_completo = limpiar_y_detectar_regiones(
            mask_sin_techos,
            min_size_initial=min_size_initial,
            min_size_final=min_size_final,
            closing_params=(closing_width, closing_height),
            iterations=closing_iterations,
            mostrar=False
        )

        resultados['completo'] = {
            'pixeles_de_agua': np.sum(mask_limpia_completo),
            'imagen': generar_imagen_base64(mask_limpia_completo),
            'num_regiones': len(props_completo),
            'labels': labels_completo,
            'props': props_completo,
            'imagen_con_ids': generar_imagen_base64_con_ids(mask_limpia_completo, props_completo, metodo),
            'imagen_rgb_con_bordes': generar_imagen_rgb_con_bordes(band_arrays, mask_limpia_completo, metodo),
            'imagen_mask_completa': generar_imagen_base64_mask_completa(band_arrays, mask_limpia_completo),
            'imagen_mask_cruda': imagen_mask_cruda_completo,
            'imagen_mask_limpia': generar_imagen_base64(mask_limpia_completo)
        }

    # PASO 3: ANÁLISIS DE REGIONES
    resultados_mndwi = analizar_regiones_web(
        mask_limpia_mndwi, labels_mndwi, props_mndwi,
        band_arrays, band_transforms, band_crs,
        pix_size_x_m, pix_area_m2, ref_band='band_blue'
    )
    resultados['mndwi']['analisis'] = resultados_mndwi
    # labels y props no son serializables a JSON; se eliminan tras el análisis
    del resultados['mndwi']['labels']
    del resultados['mndwi']['props']

    if metodo in ['completo', 'comparar']:
        resultados_completo = analizar_regiones_web(
            mask_limpia_completo, labels_completo, props_completo,
            band_arrays, band_transforms, band_crs,
            pix_size_x_m, pix_area_m2, ref_band='band_blue'
        )
        resultados['completo']['analisis'] = resultados_completo
        del resultados['completo']['labels']
        del resultados['completo']['props']

    # PASO 4: COMPARACIÓN (solo en modo 'comparar')
    if metodo == 'comparar':
        resultados['comparacion'] = {
            'regiones_mndwi': len(props_mndwi),
            'pixeles_de_agua_mndwi': np.sum(mask_limpia_mndwi),
            'pixeles_de_agua_completo': np.sum(mask_limpia_completo),
            'regiones_completo': len(props_completo),
            'diferencia': len(props_completo) - len(props_mndwi)
        }
        # Los arrays numpy no son serializables; se eliminan del índice
        del resultados['indices']['mndwi']['array']
        del resultados['indices']['mndwi']['mask']

    # PASO 5: SERIALIZACIÓN Y GUARDADO
    resultados_serializables = serializar_resultados(resultados)

    if session_folder is None:
        raise ValueError("La carpeta de sesión es requerida para guardar resultados.")

    resultados_filename = f"resultados_analisis_{config['metodo_deteccion']}.json"
    resultados_path = os.path.join(session_folder, resultados_filename)

    try:
        with open(resultados_path, 'w') as f:
            json.dump(resultados_serializables, f)
    except Exception as e:
        raise RuntimeError(f"Fallo al guardar resultados en archivo JSON: {e}")

    return resultados_filename


def analizar_regiones_web(mask_limpia, labels, props, band_arrays, band_transforms, band_crs,
                         pix_size_x_m, pix_area_m2, ref_band='band_red'):
    """
    Calcula métricas geométricas, espectrales, morfológicas y geoespaciales
    para cada región detectada. Retorna una lista de dicts serializables a JSON.
    """
    # La banda de referencia define el CRS y la transformación afín usados en georeferenciación
    transform_aff = band_transforms[ref_band]
    crs_raster = band_crs[ref_band]
    transformer = transformador_a_wgs84(crs_raster)

    resultados = []

    for i, region_props in enumerate(props, 1):
        mask_region = (labels == region_props.label)

        # Métricas geométricas
        area_m2 = region_props.area * pix_area_m2
        perimetro_m = region_props.perimeter * pix_size_x_m
        area_km2 = area_m2 / 1e6
        perimetro_km = perimetro_m / 1000
        # Circularidad: 1 = círculo perfecto, 0 = forma muy irregular o lineal
        circularidad = (4 * np.pi * area_m2) / (perimetro_m ** 2) if perimetro_m > 0 else 0

        # Reflectancias medias (valores crudos de DN)
        refl = {
            'azul': float(band_arrays['band_blue'][mask_region].mean()),
            'verde': float(band_arrays['band_green'][mask_region].mean()),
            'rojo': float(band_arrays['band_red'][mask_region].mean()),
            'nir': float(band_arrays['band_nir'][mask_region].mean()),
            'swir': float(band_arrays['band_swir'][mask_region].mean())
        }

        # Reflectancias normalizadas (0–1), usadas para el gráfico de firma espectral
        refl_norm = {
            'azul': float(normalize(band_arrays['band_blue'][mask_region]).mean()),
            'verde': float(normalize(band_arrays['band_green'][mask_region]).mean()),
            'rojo': float(normalize(band_arrays['band_red'][mask_region]).mean()),
            'nir': float(normalize(band_arrays['band_nir'][mask_region]).mean()),
            'swir': float(normalize(band_arrays['band_swir'][mask_region]).mean())
        }

        grafico_espectral_b64 = generar_grafico_firma_espectral(refl)

        # Turbidez estimada via NDTI (Normalized Difference Turbidity Index)
        ndti_mean, ndti_vals = calcular_ndti_medio_region(band_arrays, mask_region)
        sd_estimada, clasificacion_turbidez = clasificar_turbidez(ndti_mean)

        # Profundidad estimada a partir de la reflectancia azul (modelo empírico)
        mapa_profu, profundidad_media, profundidad_max = calcular_profundidad(band_arrays, mask_region)

        # Morfología vía esqueletización: clasifica entre Río, Lago, Laguna o Embalse
        res_esqueleto = analizar_esqueleto(
            mask_region, pix_size=pix_size_x_m, area_m2=area_m2, perimetro_m=perimetro_m
        )

        lat, lon = obtener_centroide_wgs84(region_props, transform_aff, transformer)

        # Imagen de zoom centrada en la región (falso color NIR-SWIR-Blue)
        imagen_region_base64 = generar_imagen_base64_zoom(band_arrays, mask_region, region_props, i)

        # Imagen global con todas las regiones, resaltando la actual
        imagen_contexto_base64 = generar_imagen_contexto_global(
            band_arrays, mask_limpia, mask_region, region_props, i
        )

        resultado = {
            'id': i,
            'area_km2': float(area_km2),
            'perimetro_km': float(perimetro_km),
            'circularidad': float(circularidad),
            'reflectancias': refl,
            'reflectancias_normalizadas': refl_norm,
            'ndti_mean': ndti_mean,
            'sd_estimada': sd_estimada,
            'clasificacion_turbidez': clasificacion_turbidez,
            'profundidad_mean': float(profundidad_media) if np.isfinite(profundidad_media) else None,
            'profundidad_max': float(profundidad_max) if np.isfinite(profundidad_max) else None,
            'morfologia': {
                'longitud_m': float(res_esqueleto['longitud_m']),
                'ancho_promedio_m': float(res_esqueleto['ancho_promedio_m']),
                'extremos': int(res_esqueleto['extremos']),
                'cruces': int(res_esqueleto['cruces']),
                'clasificacion': res_esqueleto['clasificacion']
            },
            'lat': float(lat),
            'lon': float(lon),
            'grafico_espectral': grafico_espectral_b64,
            'imagen_base64': imagen_region_base64,
            'imagen_contexto_base64': imagen_contexto_base64,
            'google_maps': f"https://www.google.com/maps/@{lat},{lon},18z"
        }

        resultados.append(resultado)

    return resultados


def serializar_resultados(resultados):
    """
    Convierte recursivamente el dict de resultados a tipos nativos de Python
    para que sea serializable a JSON. Los numpy arrays se descartan (None)
    ya que solo se guardan las imágenes pre-renderizadas en base64.
    """
    def convertir_valor(obj):
        if isinstance(obj, np.ndarray):
            return None
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: convertir_valor(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convertir_valor(item) for item in obj]
        else:
            return obj

    return convertir_valor(resultados)
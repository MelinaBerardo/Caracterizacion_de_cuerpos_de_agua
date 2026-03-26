# core/caracterizacion.py - Análisis y caracterización de regiones de agua

import numpy as np
from skimage.morphology import skeletonize
from scipy.ndimage import convolve
from core.utils import normalize


def analizar_esqueleto(mask_region, pix_size=10, area_m2=10, perimetro_m=0):
    """
    Analiza la morfología de una región mediante esqueletización y la clasifica
    en Embalse, Río/Arroyo, Lago o Laguna según métricas geométricas.

    Args:
        mask_region (np.ndarray bool): Máscara binaria de la región.
        pix_size (float): Tamaño del píxel en metros.
        area_m2 (float): Área de la región en m².
        perimetro_m (float): Perímetro de la región en metros.

    Returns:
        dict: Métricas morfológicas y clasificación del cuerpo de agua.
    """
    skeleton = skeletonize(mask_region)

    # Kernel 8-vecinos para contar conexiones en cada píxel del esqueleto
    kernel = np.array([[1,1,1], [1,0,1], [1,1,1]])
    neighbors = convolve(skeleton.astype(int), kernel, mode="constant")
    coords = np.column_stack(np.where(skeleton))

    # Extremos: píxeles con un solo vecino (puntas del esqueleto)
    # Cruces: píxeles con 3 o más vecinos (bifurcaciones)
    extremos = [(y, x) for y, x in coords if neighbors[y, x] == 1]
    cruces   = [(y, x) for y, x in coords if neighbors[y, x] >= 3]

    # Longitud total del esqueleto ponderada por la distancia diagonal entre píxeles
    dy, dx = np.mgrid[-1:2, -1:2]
    distancias = np.sqrt(dx**2 + dy**2)
    mascara_vecinos = (kernel == 1)
    length_pix = np.sum(
        convolve(skeleton.astype(int), mascara_vecinos, mode='constant')
        * skeleton * np.mean(distancias[mascara_vecinos])
    ) / 2
    length_m = length_pix * pix_size

    # Ancho promedio estimado como Area / Longitud
    ancho_promedio_m = area_m2 / length_m if length_m > 0 else 0

    # Índice de elongación: >5 indica forma alargada (río/arroyo)
    indice_elongacion = length_m / ancho_promedio_m if ancho_promedio_m > 0 else 0

    # Circularidad: 1 = círculo perfecto, valores bajos = forma irregular o lineal
    circularidad = (4 * np.pi * area_m2) / (perimetro_m ** 2) if perimetro_m > 0 else 0

    # Clasificación por prioridad de criterios
    if area_m2 > 1_000_000 and circularidad < 0.2:
        # Grande e irregular: típico de embalses artificiales
        clasificacion = "EMBALSE (Cuerpo artificial/irregular)"
    elif indice_elongacion > 5.0:
        # Forma muy alargada respecto al ancho
        clasificacion = "RÍO / ARROYO"
    else:
        # Forma compacta: distinguir por tamaño (10 hectáreas como umbral)
        clasificacion = "LAGO" if area_m2 > 100_000 else "LAGUNA"

    return {
        "longitud_m": length_m,
        "ancho_promedio_m": ancho_promedio_m,
        "pixeles_esqueleto": len(coords),
        "extremos": len(extremos),
        "cruces": len(cruces),
        "clasificacion": clasificacion,
        "skeleton": skeleton,
        "indice_elongacion": indice_elongacion,
        "circularidad": circularidad
    }


def clasificar_por_color(band_arrays, mask_region):
    """
    Clasifica un cuerpo de agua según su firma espectral normalizada
    en bandas Blue, NIR y SWIR.

    Args:
        band_arrays (dict): Bandas espectrales.
        mask_region (np.ndarray bool): Máscara de la región.

    Returns:
        str: Clasificación visual del cuerpo de agua.
    """
    blue_norm = normalize(band_arrays['band_blue'][mask_region].astype(float))
    nir_norm  = normalize(band_arrays['band_nir'][mask_region].astype(float))
    swir_norm = normalize(band_arrays['band_swir'][mask_region].astype(float))

    blue_mean = np.nanmean(blue_norm)
    nir_mean  = np.nanmean(nir_norm)
    swir_mean = np.nanmean(swir_norm)

    # Clasificación heurística basada en umbrales empíricos por banda
    if nir_mean < 0.1 and swir_mean < 0.1 and blue_mean < 0.1:
        return "Agua profunda y limpia"
    elif blue_mean > 0.4 and swir_mean >= 0.25 and nir_mean < 0.25:
        return "Agua poco profunda o con sedimentos (Cian)"
    elif swir_mean > 0.35 and swir_mean < 0.6 and nir_mean < 0.2 and blue_mean < 0.45:
        return "Agua turbia con alta carga de limo/tierra (Marrón)"
    elif nir_mean > 0.45 and swir_mean >= 0.25 and swir_mean < 0.45 and blue_mean < 0.25:
        return "Vegetación saludable"
    elif nir_mean >= 0.25 and nir_mean < 0.45 and swir_mean > 0.45:
        return "Vegetación estresada o seca"
    elif swir_mean >= 0.25 and swir_mean < 0.45 and blue_mean >= 0.25 and blue_mean < 0.45 and nir_mean < 0.25:
        return "Suelos húmedos"
    elif swir_mean > 0.45 and blue_mean < 0.25 and nir_mean < 0.25:
        return "Suelos secos o sin cobertura"
    else:
        return "Sin clasificación clara"


def calcular_profundidad(band_arrays, mask_region):
    """
    Estima la profundidad de un cuerpo de agua a partir de la reflectancia
    de la banda azul, usando modelos empíricos logarítmicos.

    Retorna un mapa por píxel, la profundidad media y la profundidad máxima.

    Args:
        band_arrays (dict): Bandas espectrales.
        mask_region (np.ndarray bool): Máscara con True donde hay agua.

    Returns:
        tuple: (mapa de profundidad por píxel, profundidad_media, profundidad_max)
    """
    blue = band_arrays['band_blue'].astype(float)
    blue_norm = normalize(blue)

    # Evitar ceros en el logaritmo
    blue_norm = np.clip(blue_norm, 1e-6, 1)

    # Modelo empírico píxel a píxel: D = 0.544 - 1.841 * ln(R_blue)
    profundidad = 0.544 - 1.841 * np.log(blue_norm)

    profundidad_mapa = np.full_like(profundidad, np.nan)
    profundidad_mapa[mask_region] = profundidad[mask_region]

    # Profundidad media estimada sobre el valor promedio de reflectancia azul
    blue_mean = np.nanmean(normalize(band_arrays['band_blue'][mask_region].astype(float)))
    profundidad_media = 0.6381 - 2.9948 * np.log(blue_mean)

    # Profundidad máxima estimada a partir del píxel de menor reflectancia
    # (menor reflectancia = mayor profundidad)
    EPSILON = 1e-6
    blue_min = np.nanmin(band_arrays['band_blue'][mask_region].astype(float))
    blue_min = max(blue_min, EPSILON)
    profundidad_max = (-1 / 0.0453) * np.log(blue_min / 939.89)

    return profundidad_mapa, profundidad_media, profundidad_max


def calcular_ndti(rojo, verde):
    """
    Calcula el Índice de Turbidez de Diferencia Normalizada (NDTI).

    Valores más negativos indican agua más limpia; cercanos a cero, más turbia.

    Args:
        rojo, verde (np.ndarray o float): Reflectancias de las bandas roja y verde.

    Returns:
        np.ndarray: Valores NDTI (NaN donde la suma es cero).
    """
    rojo  = np.asarray(rojo,  dtype=np.float64)
    verde = np.asarray(verde, dtype=np.float64)
    suma  = rojo + verde
    return np.where(suma != 0, (rojo - verde) / suma, np.nan)


def calcular_ndti_medio_region(band_arrays, mask_region):
    """
    Calcula el NDTI medio sobre una región enmascarada.

    Args:
        band_arrays (dict): Bandas espectrales.
        mask_region (np.ndarray bool): Máscara de la región.

    Returns:
        tuple: (ndti_mean float, ndti_vals np.ndarray con valores finitos)
    """
    R = band_arrays['band_red'][mask_region]
    G = band_arrays['band_green'][mask_region]

    ndti_vals = calcular_ndti(R, G)
    ndti_vals = ndti_vals[np.isfinite(ndti_vals)]
    ndti_mean = np.nanmean(ndti_vals) if len(ndti_vals) > 0 else np.nan

    return ndti_mean, ndti_vals


def clasificar_turbidez(ndti_mean):
    """
    Estima la profundidad de disco de Secchi (SD) a partir del NDTI
    y clasifica el estado trófico del cuerpo de agua.

    La fórmula sigmoidal de SD está calibrada empíricamente.

    Args:
        ndti_mean (float): Valor medio de NDTI de la región.

    Returns:
        tuple: (sd_estimada en metros, clasificacion trófica como str)
    """
    if np.isfinite(ndti_mean) and ndti_mean != 0:
        # Modelo sigmoidal: mayor |NDTI| → mayor transparencia → mayor SD
        sd_estimada = 5.0978 / (1 + np.exp(-36.4276 * (np.abs(ndti_mean) - 0.0767)))
    else:
        sd_estimada = np.nan

    if not np.isfinite(sd_estimada):
        clasificacion = "sin datos"
    elif sd_estimada > 5:
        clasificacion = "Oligotrófico"
    elif 2 <= sd_estimada <= 5:
        clasificacion = "Mesotrófico"
    elif 1 <= sd_estimada < 2:
        clasificacion = "Eutrófico"
    elif sd_estimada < 1:
        clasificacion = "Hipereutrófico"
    else:
        clasificacion = "sin datos"

    return sd_estimada, clasificacion
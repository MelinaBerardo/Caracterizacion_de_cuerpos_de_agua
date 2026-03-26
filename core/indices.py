# core/indices.py - Cálculo de índices espectrales y máscaras de agua
# OBTENER MASCARAS DE AGUA - MNDWI, USI, UWI, TECHOS, COLOR
# -------------------------------------------
# Bibliotecas base
import numpy as np
from skimage.filters import threshold_otsu
from core.utils import normalize

def calcular_mndwi(green, swir, eps=1e-9):
    """
    Calcula el Índice de Agua de Diferencia Normalizada Modificado (MNDWI).
    Valores >= 0 se clasifican como agua.

    Args:
        green, swir (np.ndarray): Bandas verde e infrarrojo de onda corta.
        eps (float): Pequeño valor para evitar división por cero.

    Returns:
        tuple: (array MNDWI continuo, máscara booleana de agua)
    """
    mndwi = (green - swir) / ((green + swir) + eps)
    mask_mndwi = mndwi >= 0
    return mndwi, mask_mndwi

def calcular_usi(red, green, blue, nir, agua_mask, agua_indice, eps=1e-9):
    """
    Calcula el Índice Urbano de Sombras (USI) para refinar la máscara MNDWI,
    eliminando píxeles de sombras urbanas que confunden con agua.

    El USI se aplica solo sobre los píxeles candidatos de agua_mask;
    el resto se deja como NaN. Luego se umbraliza con Otsu.

    Args:
        red, green, blue, nir (np.ndarray): Bandas espectrales.
        agua_mask (np.ndarray bool): Máscara inicial de agua (ej. MNDWI >= 0).
        agua_indice (np.ndarray): Array continuo del índice de agua.
        eps (float): Evita división por cero.

    Returns:
        tuple: (array USI, máscara booleana agua sin sombras)
    """
    usi = np.full(red.shape, np.nan, dtype=np.float32)

    usi_formula = (0.25 * (green / (red + eps))
                   - 0.57 * (nir / (green + eps))
                   - 0.83 * (blue / (green + eps))
                   + 1.0)

    # Solo se calcula el USI donde la máscara MNDWI detectó agua
    usi[agua_mask] = usi_formula[agua_mask]

    usi_validos = usi[~np.isnan(usi)]
    if usi_validos.size == 0:
        print("⚠️ No hay píxeles candidatos detectados por el índice.")
        return usi, np.zeros_like(usi, dtype=bool)

    # Umbral de Otsu: separa agua real de sombras dentro de los candidatos
    t2 = threshold_otsu(usi_validos)
    mask_usi = usi > t2
    mask_sin_sombras = np.logical_and(agua_mask, mask_usi)

    return usi, mask_sin_sombras

def generar_mask_techos(blue, swir, mascara_agua, percentil_blue=90, percentil_swir=90, margen=0.05):
    """
    Detecta techos brillantes (alta reflectancia en Blue y SWIR) y los excluye
    de la máscara de agua para evitar falsos positivos.

    Los umbrales se calculan automáticamente por percentil sobre píxeles válidos,
    con un margen adicional para reducir falsas detecciones.

    Args:
        blue, swir (np.ndarray): Bandas sin normalizar.
        mascara_agua (np.ndarray bool): Máscara de agua previa (MNDWI + USI).
        percentil_blue, percentil_swir (float): Percentil superior para el umbral de brillo.
        margen (float): Margen adicional sobre el umbral calculado.

    Returns:
        tuple: (mask_techos booleana, mask_sin_techos booleana)
    """
    swir_norm = normalize(swir)
    blue_norm = normalize(blue)

    validos = ~np.isnan(blue_norm) & ~np.isnan(swir_norm)

    if np.sum(validos) == 0:
        print("⚠️ No hay píxeles válidos para calcular umbrales, usando valores por defecto.")
        umbral_blue = 0.2
        umbral_swir = 0.3
    else:
        umbral_blue = min(1.0, np.percentile(blue_norm[validos], percentil_blue) + margen)
        umbral_swir = min(1.0, np.percentile(swir_norm[validos], percentil_swir) + margen)

    # Píxeles con reflectancia muy alta en ambas bandas = probable techo o superficie artificial
    mask_techos = (blue_norm > umbral_blue) & (swir_norm > umbral_swir)
    mask_sin_techos = np.logical_and(mascara_agua, ~mask_techos)

    return mask_techos, mask_sin_techos
    

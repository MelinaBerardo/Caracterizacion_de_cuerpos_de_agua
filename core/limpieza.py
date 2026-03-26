# core/limpieza.py - Limpieza morfológica y detección de regiones de agua

import matplotlib.pyplot as plt
from skimage.morphology import remove_small_objects, binary_closing, disk, ellipse, binary_dilation, binary_erosion
from skimage import measure
from core.utils import cargar_arrays_desde_paths, generar_imagen_base64
from core.indices import calcular_mndwi, calcular_usi, generar_mask_techos

def limpiar_y_detectar_regiones(
    mask,
    min_size_initial=5,
    closing_shape="ellipse",
    iterations=2,
    closing_params=(20, 5),
    min_size_final=20,
    mostrar=True,
    cmap="gray"
):
    """
    Aplica un pipeline morfológico para limpiar la máscara de agua y detectar
    regiones individuales (cuerpos de agua).

    El pipeline es: eliminar ruido inicial → dilatar → erosionar → cierre morfológico
    → eliminar objetos pequeños finales → etiquetar regiones.

    La dilatación+erosión previa conecta píxeles próximos antes del cierre mayor,
    reduciendo la fragmentación en regiones angostas.

    Args:
        mask (np.ndarray): Máscara binaria de agua (True = agua).
        min_size_initial (int): Tamaño mínimo de objetos a eliminar antes del cierre.
        closing_shape (str): Forma del elemento estructurante ('ellipse' o 'disk').
        iterations (int): Número de iteraciones de dilatación y erosión.
        closing_params (tuple): (ancho, alto) para ellipse, o (radio,) para disk.
        min_size_final (int): Tamaño mínimo de objetos a eliminar después del cierre.
        mostrar (bool): Si True, muestra el resultado con matplotlib (solo notebooks).
        cmap (str): Colormap para la visualización.

    Returns:
        tuple: (mask_limpia, labels, props)
    """
    mask_work = mask.astype(bool).copy()

    # Eliminar ruido inicial: objetos menores a min_size_initial píxeles
    if min_size_initial > 0:
        mask_work = remove_small_objects(mask_work, min_size=min_size_initial)

    # Dilatación + erosión con disco pequeño: conecta píxeles próximos
    # sin agrandar significativamente las regiones
    footprint_small = disk(1)
    for _ in range(iterations):
        mask_work = binary_dilation(mask_work, footprint=footprint_small)
    for _ in range(iterations):
        mask_work = binary_erosion(mask_work, footprint=footprint_small)

    # Cierre morfológico: rellena huecos internos y suaviza contornos
    if closing_shape == "ellipse":
        footprint_closure = ellipse(*closing_params)
    else:
        footprint_closure = disk(closing_params[0])

    mask_close = binary_closing(mask_work, footprint=footprint_closure)

    # Eliminar objetos pequeños residuales tras el cierre
    if min_size_final > 0:
        mask_final = remove_small_objects(mask_close, min_size=min_size_final)
    else:
        mask_final = mask_close

    # Etiquetar regiones conexas con conectividad 8-vecinos
    labels = measure.label(mask_final, connectivity=2)
    props = measure.regionprops(labels)

    if mostrar:
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.imshow(mask_final, cmap=cmap)
        for i, prop in enumerate(props, 1):
            y, x = prop.centroid
            ax.text(x, y, str(i), color="blue", fontsize=14, weight="bold")
            ax.plot(prop.coords[:, 1], prop.coords[:, 0], '.', markersize=1)
        ax.set_title(f"Cuerpos de agua detectados ({len(props)} regiones)")
        ax.axis("off")
        plt.show()

    return mask_close, labels, props


def previsualizar_limpieza(bandas_paths, metodo_deteccion, min_size_initial, closing_width, closing_height, closing_iterations, min_size_final):
    """
    Genera un par de imágenes base64 mostrando la máscara de agua antes y después
    de aplicar la limpieza morfológica. Usado en el paso de configuración del flujo web.

    Args:
        bandas_paths (dict): Rutas de las bandas espectrales.
        metodo_deteccion (str): 'mndwi' o 'completo'.
        min_size_initial (int): Mínimo de píxeles antes del cierre.
        closing_width (int): Ancho del footprint de cierre.
        closing_height (int): Alto del footprint de cierre.
        closing_iterations (int): Iteraciones de dilatación/erosión.
        min_size_final (int): Mínimo de píxeles después del cierre.

    Returns:
        dict: {'imagen_antes': str base64, 'imagen_despues': str base64}
    """
    band_arrays, _, _ = cargar_arrays_desde_paths(bandas_paths)
    mndwi, mask_mndwi = calcular_mndwi(band_arrays['band_green'], band_arrays['band_swir'])

    if metodo_deteccion == 'mndwi':
        mask_inicial = mask_mndwi
    elif metodo_deteccion == 'completo':
        _, mask_sin_sombras = calcular_usi(
            band_arrays['band_red'], band_arrays['band_green'], band_arrays['band_blue'],
            band_arrays['band_nir'], mask_mndwi, mndwi)
        _, mask_techos = generar_mask_techos(band_arrays['band_blue'], band_arrays['band_swir'], mask_sin_sombras)
        mask_inicial = mask_techos
    else:
        raise ValueError("Método de detección no válido para previsualización.")
    
    imagen_antes = generar_imagen_base64(mask_inicial)

    mask_despues, _, _ = limpiar_y_detectar_regiones(
        mask_inicial,
        min_size_initial=min_size_initial,
        min_size_final=min_size_final,
        closing_params=(closing_width, closing_height),
        iterations=closing_iterations,
        mostrar=False
    )

    imagen_despues = generar_imagen_base64(mask_despues)

    return {
        'imagen_antes': imagen_antes,
        'imagen_despues': imagen_despues
    }
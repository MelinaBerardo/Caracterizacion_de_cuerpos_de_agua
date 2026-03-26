# core/georeferenciacion.py - Transformación de coordenadas a WGS84

from rasterio.transform import xy
from pyproj import Transformer


def transformador_a_wgs84(band_crs):
    """
    Crea un transformador de coordenadas desde el CRS de la banda a WGS84 (EPSG:4326).

    always_xy=True garantiza que la salida siempre sea (longitud, latitud),
    independientemente de cómo el CRS defina el orden de los ejes.

    Args:
        band_crs: CRS de la banda (objeto rasterio.crs.CRS o string EPSG).

    Returns:
        pyproj.Transformer: Transformador listo para usar con .transform().
    """
    return Transformer.from_crs(band_crs, "EPSG:4326", always_xy=True)


def obtener_centroide_wgs84(region_props, transform_aff, transformer):
    """
    Convierte el centroide de una región (en píxeles) a coordenadas WGS84.

    Args:
        region_props: Propiedades de la región (skimage.measure.regionprops).
        transform_aff: Transformación afín del raster (rasterio.transform.Affine).
        transformer: Transformador pyproj creado con transformador_a_wgs84().

    Returns:
        tuple: (lat, lon) en grados decimales WGS84.
    """
    r_centroide, c_centroide = region_props.centroid
    x_center, y_center = xy(transform_aff, r_centroide, c_centroide)
    lon, lat = transformer.transform(x_center, y_center)
    return lat, lon
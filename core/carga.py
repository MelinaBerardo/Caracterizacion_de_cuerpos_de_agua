# core/carga.py - Carga, conversión y diagnóstico de archivos raster

import os
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import xy
from pyproj import Geod
from osgeo import gdal
#from IPython.display import display


def convertir_a_tiff(input_file, output_file=None):
    """
    Convierte un raster (JP2, HDR/IMG, etc.) a GeoTIFF usando GDAL.
    Si el archivo ya es GeoTIFF, lo retorna sin cambios.

    Args:
        input_file (str): Ruta del archivo de entrada.
        output_file (str): Ruta de salida opcional. Si es None, se genera automáticamente.

    Returns:
        str: Ruta del archivo GeoTIFF resultante, o None si falla.
    """
    if output_file is None:
        base = os.path.splitext(input_file)[0]
        output_file = base + ".tif"

    if input_file.lower().endswith(('.tif', '.tiff')):
        print(f"Ya es GeoTIFF: {input_file}")
        return input_file

    dataset = gdal.Open(input_file, gdal.GA_ReadOnly)
    if not dataset:
        print(f"❌ No se pudo abrir: {input_file}")
        return None

    gdal.Translate(output_file, dataset, format="GTiff", creationOptions=['COMPRESS=LZW'])
    dataset = None  # Cierra el dataset y libera recursos
    print(f"Convertido: {input_file} → {output_file}")
    return output_file


def mostrar_info_geodatos(tif_path, mostrar_tabla=True):
    """
    Muestra y retorna información geoespacial y estadísticas de un GeoTIFF.
    Diseñada para uso en notebooks/entornos con IPython (usa display()).

    Para sistemas geográficos (grados), la resolución se convierte a metros
    usando geodésicas sobre el elipsoide WGS84.

    Args:
        tif_path (str): Ruta al archivo GeoTIFF.
        mostrar_tabla (bool): Si True, imprime la información por consola.

    Returns:
        tuple: (DataFrame con estadísticas, (res_x_m, res_y_m), area_pixel_m2)
    """
    if not os.path.exists(tif_path):
        print(f"❌ Archivo no encontrado: {tif_path}")
        return None, None, None

    with rasterio.open(tif_path) as src:
        general_info = {
            "Archivo": os.path.basename(src.name),
            "CRS": src.crs,
            "Es Geográfico": src.crs.is_geographic,
            "Resolución declarada": src.res,
        }

        if src.crs.is_geographic:
            # La resolución en grados varía según la latitud; se mide geodésicamente
            # en el centro de la imagen para minimizar la distorsión
            try:
                geod = Geod(ellps="WGS84")
                row, col = src.height // 2, src.width // 2

                lon0, lat0 = xy(src.transform, row, col, offset="center")
                lon_x, lat_x = xy(src.transform, row, col+1, offset="center")
                lon_y, lat_y = xy(src.transform, row+1, col, offset="center")

                _, _, dist_x = geod.inv(lon0, lat0, lon_x, lat_x)
                _, _, dist_y = geod.inv(lon0, lat0, lon_y, lat_y)

                res_x_m, res_y_m = abs(dist_x), abs(dist_y)
            except Exception:
                res_x_m, res_y_m = src.res
        else:
            res_x_m, res_y_m = src.res

        area_pixel_m2 = abs(res_x_m * res_y_m)

        data = []
        if mostrar_tabla:
            for i in range(1, src.count + 1):
                try:
                    # Submuestreo al 10% para evitar saturar memoria en imágenes grandes
                    banda = src.read(i, out_shape=(1, int(src.height/10), int(src.width/10))).astype(float)
                    data.append({
                        "Banda": i,
                        "Min": np.nanmin(banda),
                        "Max": np.nanmax(banda),
                        "Media": round(np.nanmean(banda), 4)
                    })
                except Exception:
                    pass

        df_info = pd.DataFrame(data)

        if mostrar_tabla:
            print("\nInformación general:")
            for k, v in general_info.items():
                print(f"   {k}: {v}")
            print(f"\nResolución real (m): {res_x_m:.2f} × {res_y_m:.2f}")
            print(f"Área por píxel (m²): {area_pixel_m2:.2f}\n")
            if not df_info.empty:
                print("Estadísticas por banda:")
                #display(df_info.style.background_gradient(cmap="YlGnBu"))

        return df_info, (res_x_m, res_y_m), area_pixel_m2
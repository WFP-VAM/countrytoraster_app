def geojson_country_NE(country):
    '''
    From a country name or code, it gets a geojson object of the country boundary from Natural Earth API
    '''
    import requests
    r = requests.get("https://d2ad6b4ur7yvpq.cloudfront.net/naturalearth-3.3.0/ne_50m_admin_0_countries.geojson")
    country_id=-1

    data = r.json()
    for i in range(0,len(data["features"])):
        for j in data["features"][i]["properties"]:
            if data["features"][i]["properties"][j]==country:
                country_id=i
                break
        else:
            continue
        break

    geojson={
      "type": "Feature",
      "properties": {},
      "geometry": {}
    }

    if country_id==-1:
        print("No Boundaries available for this request")
    else:
        geojson["geometry"]=data["features"][country_id]["geometry"]
        return geojson


def geojson_country_OSM(country_ISO):
    '''
    From a country ISO code, it gets a geojson object of the country boundary from Open Street Map (wambachers) API
    '''
    import requests
    from zipfile import ZipFile
    import io
    import json
    params = (
    ('cliVersion', '1.0'),
    ('cliKey', 'f7249a6c-5e0c-4834-823c-eef0167aebac'),
    ('exportFormat', 'json'),
    ('exportLayout', 'levels'),
    ('exportAreas', 'land'),
    ('union', 'false'),
    ('selected', country_ISO))

    r = requests.get('https://wambachers-osm.website/boundaries/exportBoundaries', params=params)

    if r.status_code == requests.codes.ok:
        zipfile = ZipFile(io.BytesIO(r.content))
        zip_names = zipfile.namelist()

        data = zipfile.open(zip_names[0]).read()
        data = json.loads(data.decode("utf-8"))

        geojson={
          "type": "Feature",
          "properties": {},
          "geometry": {}
        }
        geojson["geometry"]=data["features"][0]["geometry"]

        return geojson
    else:
        print("No Boundaries available for this request")

def reproject_geojson_gdal(geojson,dst_crs,src_crs=4326):
    '''
    Reprojects a geojson in a new coordinate reference system (crs) with GDAL library.
    If not specified, the input geojson crs is ESPG:4326  (WGS84 used for GPS coordinates in latitude/longitude)

    dst_crs and src_crs are the code of the projection in the ESPG system. Ex: 3857 for pseudo-Mercator.
    '''
    from osgeo import ogr, osr
    import json
    source = osr.SpatialReference()
    source.ImportFromEPSG(src_crs)
    target = osr.SpatialReference()
    target.ImportFromEPSG(dst_crs)
    transform = osr.CoordinateTransformation(source, target)
    polygon = ogr.CreateGeometryFromJson("""{}""".format(geojson["geometry"]))
    polygon.Transform(transform)
    geojson_reproj={
      "type": "Feature",
      "properties": {},
      "geometry": {}
    }
    geojson_reproj["geometry"]=json.loads(polygon.ExportToJson())
    return geojson_reproj

def reproject_geojson_gpd(geojson,dst_crs,src_crs=4326):
    '''
    Reprojects a geojson in a new coordinate reference system (crs) with GeoPandas library.
    If not specified, the input geojson crs is ESPG:4326, the WGS84 used for GPS coordinates in latitude/longitude.

    dst_crs and src_crs are the code of the projection in the ESPG system. Ex: 3857 for pseudo-Mercator.
    '''
    import geopandas as gpd
    from shapely.geometry import shape
    import json
    goodshape=shape(geojson["geometry"])
    gdf = gpd.GeoSeries(goodshape,crs={'init': 'epsg:{}'.format(src_crs)})
    gdf = gdf.to_crs({'init': 'epsg:{}'.format(dst_crs)})
    geojson_reproj={
      "type": "Feature",
      "properties": {},
      "geometry": {}
    }
    geojson_reproj["geometry"]=json.loads(gdf.to_json())["features"][0]["geometry"]
    return geojson_reproj

def rasterize_geojson(geojson,resolution,dst_raster,src_crs):
    '''
    Rasterize a geojson vector to a raster tiff file using rasterio library.
    It is mandatory to specify the coordinate reference system (crs) of the input geojson as
    the corresponding code in the ESPG system (ex:3857)

    resolution is the pixel size of the output raster in the unit system of crs. Usually
    metres for projected coordinates (ex: 3857) and degrees for non-projected crs (ex: 4326)

    Returns both the raster path and the numpy ndarray of the raster.
    '''
    from rasterio.features import bounds as calculate_bounds
    from math import ceil
    from affine import Affine
    from rasterio.features import rasterize
    from rasterio.io import MemoryFile
    import rasterio
    bounds = calculate_bounds(geojson)
    res = (resolution,resolution)
    geometries = ((geojson["geometry"], 1), )
    params = {
    'count': 1,
    'crs':'EPSG:{}'.format(src_crs),
    'width': max(int(ceil((bounds[2] - bounds[0]) / float(res[0]))), 1),
    'height': max(int(ceil((bounds[3] - bounds[1]) /float(res[1]))), 1),
    'driver': 'GTiff',
    'transform': Affine(res[0], 0, bounds[0], 0, -res[1], bounds[3]),
    'nodata': 0,
    'dtype': 'uint8'
    }

    output = rasterize(
                geometries,
                out_shape=(params['height'], params['width']),
                transform=params['transform'])

    with rasterio.open(dst_raster,'w',**params) as dst:
            dst.write(output, indexes=1)
    return dst_raster, output

def reproject_raster(src_raster,dst_raster,dst_crs):
    '''
    Reprojects a raster tiff file from a given coordinate reference system (crs) to a new crs using rasterio library.
    '''
    import numpy as np
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    dst_crs = 'EPSG:{}'.format(dst_crs)
    with rasterio.open(src_raster) as src:
        transform, width, height = calculate_default_transform(src.crs, dst_crs, src.width, src.height, *src.bounds)
        kwargs = src.meta.copy()
        kwargs.update({
            'crs': dst_crs,
            'transform': transform,
            'width': width,
            'height': height
        })

        with rasterio.open(dst_raster, 'w', **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.nearest)
        return dst_raster

from flask import Flask, flash, redirect, render_template, request, session, abort, send_file, make_response
import rasterio
import requests
from shapely.geometry import shape, mapping
from rasterio.features import bounds as calculate_bounds
from math import ceil
from rasterio.features import rasterize
from affine import Affine
import json
from osgeo import ogr, osr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import io
from PIL import Image
from rasterio.io import MemoryFile
from zipfile import ZipFile


app = Flask(__name__)


def output_showcase(img):
   # generate image with result
   fig = plt.figure(figsize=(5, 5), dpi=150)
   ax = fig.add_subplot(111)
   ax.imshow(img, cmap='Greys')
   output = io.BytesIO()
   plt.axis('off')
   plt.savefig(output, dpi=fig.dpi)
   output.seek(0)

   return send_file(output, mimetype='image/png', cache_timeout=-1)


@app.route("/")
def home():
    return render_template("index.html")



@app.route("/convert",methods=["POST"])
def countrytoraster():
    country=request.form["country"]
    resolution=float(request.form["gsize"])
    projection=int(request.form["projection"])
    api=int(request.form["api_field"])

    print(request.form)

    name="{}_{}_{}_{}".format(country, resolution, projection, api)

    #template geojson in the correct format
    geojson_template_polygon={
      "type": "Feature",
      "properties": {},
      "geometry": {}
    }

    #Get a geojson from the openstreetmap api
    #url="http://nominatim.openstreetmap.org/search?country={}&polygon_geojson=1&format=json".format(country)
    geojson=geojson_template_polygon

    if api==1:
        ##1st API: Natural Earth
        r = requests.get("https://d2ad6b4ur7yvpq.cloudfront.net/naturalearth-3.3.0/ne_50m_admin_0_countries.geojson")
        data = r.json()
        for i in range(0,len(data["features"])):
            for j in data["features"][i]["properties"]:
                if data["features"][i]["properties"][j]==country:
                    country_id=i
                    break
            else:
                continue
            break
        geojson["geometry"]["coordinates"]=data["features"][country_id]["geometry"]["coordinates"]
        geojson["geometry"]["type"]=data["features"][country_id]["geometry"]["type"]


    elif api==2:
        ## 2nd API: Open Street Map
        params = (
        ('cliVersion', '1.0'),
        ('cliKey', 'f7249a6c-5e0c-4834-823c-eef0167aebac'),
        ('exportFormat', 'json'),
        ('exportLayout', 'levels'),
        ('exportAreas', 'land'),
        ('union', 'false'),
        ('selected', country))

        r = requests.get('https://wambachers-osm.website/boundaries/exportBoundaries', params=params)

        zipfile = ZipFile(io.BytesIO(r.content))
        zip_names = zipfile.namelist()

        data = zipfile.open(zip_names[0]).read()
        data = json.loads(data.decode("utf-8"))

        geojson["geometry"]["coordinates"]=data["features"][0]["geometry"]["coordinates"]
        geojson["geometry"]["type"]=data["features"][0]["geometry"]["type"]


    #Reproject the original geojson with GDAL osr and ogr
    source = osr.SpatialReference()
    source.ImportFromEPSG(4326)
    target = osr.SpatialReference()
    target.ImportFromEPSG(projection)
    transform = osr.CoordinateTransformation(source, target)
    polygon = ogr.CreateGeometryFromJson("""{}""".format(geojson["geometry"]))
    polygon.Transform(transform)
    geojson_reproj=json.loads(polygon.ExportToJson())

    #Rasterize the polygon with rasterio
    bounds = calculate_bounds(geojson_reproj)
    res = (resolution,resolution)
    geometries = ((geojson_reproj, 1), )
    params = {
    'count': 1,
    'crs':'EPSG:{}'.format(projection),
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

    with MemoryFile() as memfile:
        with memfile.open(**params) as dst:
                dst.write(output, indexes=1)
        with open('/tmp/file.tif', 'wb') as g:
            memfile.seek(0)
            g.write(memfile.read())
            if request.form["action"] == "download":
                return send_file('/tmp/file.tif',
                                 mimetype='image/tiff',
                                 as_attachment=True,
                                 attachment_filename=name+".tif")
            elif request.form["action"] == "preview":
                return output_showcase(output)


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

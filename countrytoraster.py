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


app = Flask(__name__)


def output_showcase(img):
   # generate image with result
   fig = plt.figure(figsize=(5, 5), dpi=300)
   ax = fig.add_subplot(111)
   ax.imshow(img, cmap='Greys')
   #plt.imshow(img, cmap='Greys')

   output = io.BytesIO()
   plt.savefig(output, dpi=fig.dpi)
   output.seek(0)

   return send_file(output, mimetype='image/png')


@app.route("/")
def home():
    return render_template("index.html")



@app.route("/convert",methods=["POST"])
def countrytoraster():
    country=request.form["country"]
    resolution=int(request.form["gsize"])
    projection=int(request.form["projection"])

    #template geojson in the correct format
    geojson_template_polygon={
      "type": "Feature",
      "properties": {},
      "geometry": {}
    }

    #Get a geojson from the openstreetmap api
    url="http://nominatim.openstreetmap.org/search?country={}&polygon_geojson=1&format=json".format(country)
    r = requests.get(url)
    data = r.json()[0]['geojson']
    geojson=geojson_template_polygon
    geojson["geometry"]["coordinates"]=data["coordinates"]
    geojson["geometry"]["type"]=data["type"]

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
    bounds = geojson.get('bbox', calculate_bounds(geojson_reproj))
    res = (resolution,resolution)
    width = max(int(ceil((bounds[2] - bounds[0]) / float(res[0]))), 1)
    height = max(int(ceil((bounds[3] - bounds[1]) /float(res[1]))), 1)
    geometries = ((geojson_reproj, 1), )
    trans=Affine(res[0], 0, bounds[0], 0, -res[1],bounds[3])
    output = rasterize(geometries,
                   transform=trans,
                   out_shape=(height, width))

    with MemoryFile() as memfile:
        with memfile.open(
            driver='GTiff',
            dtype=rasterio.uint8,
            count=1,
            width=width,
            height=height,
            nodata=0) as dst:
                dst.write(output, indexes=1)
        with open('/tmp/test.tif', 'wb') as g:
            memfile.seek(0)
            g.write(memfile.read())
            if request.form["action"] == "download":
                return send_file('/tmp/test.tif',
                                 mimetype='image/tiff',
                                 as_attachment=True,
                                 attachment_filename="{}_{}_{}.tif".format(country, resolution, projection))
            elif request.form["action"] == "preview":
                return output_showcase(output)


if __name__ == "__main__":
    app.run()

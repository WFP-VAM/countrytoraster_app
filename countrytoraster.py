from GIS_utils import geojson_country_NE, geojson_country_OSM, \
    reproject_geojson_gpd, rasterize_geojson
from flask import Flask, request, send_file, render_template
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import io


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


@app.route("/convert", methods=["POST"])
def countrytoraster():
    country = request.form["country"]
    resolution = float(request.form["gsize"])
    projection = int(request.form["projection"])
    api = int(request.form["api_field"])
    name = "{}_{}_{}_{}".format(country, resolution, projection, api)

    if api == 1:
        geojson = geojson_country_NE(country)
    elif api == 2:
        geojson = geojson_country_OSM(country)

    if geojson is None:
        return "No Boundaries available for this request"

    if projection != 4326:
        geojson_reproj = reproject_geojson_gpd(geojson, src_crs=4326, dst_crs=projection)

    raster_path, output = rasterize_geojson(geojson_reproj, resolution, dst_raster="/tmp/raster.tif", src_crs=projection)

    if request.form["action"] == "download":
        return send_file(raster_path,
                         mimetype='image/tiff',
                         as_attachment=True,
                         attachment_filename=name + ".tif")
    elif request.form["action"] == "preview":
        return output_showcase(output)


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

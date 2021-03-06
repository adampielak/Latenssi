# encoding: utf-8

from lib import web, rrd
from lib import config
import tempfile
import os
import time
import json

from bottle import abort, request, response, redirect, static_file

import logging

logger = logging.getLogger("pages")

indexpage = web.WebPage("index", "Index")


def probe_sorter(probe_tuple):
    """
    Split probe name to tuples containing target address in reverse order and probe type.

    Eg. "Ping latenssi.link" results ('link', 'latenssi', 'ping')

    This makes probes to appear in logical order.
    """
    return tuple(reversed(probe_tuple[1].probe.target.split('.'))) + (probe_tuple[1].probe._name,)


def full_path(x):
    return "%s%s" % (config.relative_path.rstrip("/"), x)


if config.relative_path.lstrip("/") != "":
    @web.webapp.get("/")
    @web.webapp.get("")
    def callback():
        return redirect(full_path("/"))


def index(interval):
    if interval not in config.intervals.keys():
        abort(404, "Invalid interval")

    pages = []
    all_probes = web.ProbeCache.get_all().items()
    # List probes in sorted order
    for probename, probe in sorted(all_probes, key=probe_sorter):
        pages.append({
            "title": probe.title,
            "name": probe.name,
            "img": probe.get_index_graph(interval),
            "link": probe.get_path(interval)
        })


    return web.webgenerator.output("index.html", {'pages': pages, 'intervals': indexpage.generate_intervals()})


@web.webapp.route(full_path('/static/<path:path>'))
def callback(path):
    root = os.path.join(os.path.dirname(__file__), '../../www/static')
    return static_file(path, root=root)


def probepage(probe, interval):
    if interval not in config.intervals.keys():
        abort(404, "Invalid interval")
    p = web.ProbeCache.get(probe)
    if not p:
        abort(404, "Not such probe")

    return web.webgenerator.output("host.html", {'host': {'name': p.title, 'probes': p.get_graph_urls(interval)},
                                                 'intervals': p.generate_intervals(),
                                                 'index': indexpage.get_path(interval)})


@web.webapp.get(full_path(""))
@web.webapp.get(full_path("/"))
def callback():
    return index(config.default_interval)

@web.webapp.get(full_path( "/<interval>"))
def callback(interval):
    return index(interval)

@web.webapp.get(full_path("/probes/<probe>/"))
@web.webapp.get(full_path("/probes/<probe>"))
def callback(probe):
    interval = config.default_interval
    return probepage(probe, interval)

@web.webapp.get(full_path("/probes/<probe>/<interval>"))
@web.webapp.get(full_path("/probes/<probe>/<interval>/"))
def callback(probe, interval):
    return probepage(probe, interval)

@web.webapp.get(full_path('/graph/<graph>/'))
def callback(graph):
    if not rrd.RRD.exists(graph):
        return abort(404, "No such graph")
    response.set_header('Content-Type', 'image/png')
    params = dict(request.GET)

    start = None
    end = None
    if 'start' in params:
        try:
            start = int(params['start'])
        except ValueError:
            abort(400, "Invalid start time")
            return
    else:
        start = time.time() - 3600 * 24
    if 'end' in params:
        try:
            end = int(params['end'])
        except ValueError:
            abort(400, "Invalid end time")
            return
    else:
        end = time.time()
    if 'interval' in params:
        interval = params['interval']
        if interval not in config.intervals.keys():
            abort(400, "Invalid interval")
            return
        else:
            start = time.time() - config.intervals[interval]
    width = None
    height = None
    if 'width' in params:
        try:
            width = int(params['width'])
        except ValueError:
            abort(400, "Invalid width")
            return
    if 'height' in params:
        try:
            height = int(params['height'])
        except ValueError:
            abort(400, "Invalid height")
            return
    (tf, path) = tempfile.mkstemp()
    retval = None
    try:
        rrd.RRD.graph(graph, path, start=start, end=end, width=width, height=height)
        f = os.fdopen(tf, 'rb')
        retval = f.read()
        f.close()
    except Exception as e:
        logging.exception("Got unknown error")
    return retval

@web.webapp.get(full_path('/rrd/<graph>/'))
def callback(graph):
    if not rrd.RRD.exists(graph):
        return abort(404, "No such graph")
    params = dict(request.GET)
    start = None
    end = None
    if 'start' in params:
        try:
            start = int(params['start'])
        except ValueError:
            abort(400, "Invalid start time")
            return
    else:
        start = int(time.time() - 86400)
    if 'end' in params:
        try:
            end = int(params['end'])
        except ValueError:
            abort(400, "Invalid end time")
            return
    else:
        end = int(time.time())
    interval = config.default_interval
    if 'interval' in params:
        interval = params['interval']
        if interval not in config.intervals.keys():
            abort(400, "Invalid interval")
            return
        else:
            start = int(end - config.intervals[interval])
    interval = config.intervals[interval]
    nulls = True
    if 'nulls' in params:
       if params['nulls'] == "false" or params['nulls'] == "0":
           nulls = False

    g = rrd.RRD.get_graph(graph)

    response.set_header('Content-Type', 'application/json')

    resolution = 5
    if interval > 5000:
        resolution = int(resolution * (interval / 5000))

    mins = g.fetch(cf="MIN", start=int(start), end=int(end), nulls=nulls, resolution=resolution)
    avgs = g.fetch(cf="AVERAGE", start=int(start), end=int(end), nulls=nulls, resolution=resolution)
    maxes = g.fetch(cf="MAX", start=int(start), end=int(end), nulls=nulls, resolution=resolution)

    #keys = [x for x in mins[0].keys() if x != "time"]

    #times = {}
    #def add_time(t):
    #    times[t] = {k: {"min": None, "avg": None, "max": None} for k in keys}
    #for i in mins:
    #    if mins["time"] not in times:
    #        add_time(mins["time"])
    #    times[mins["time"]]["min"] = mins["ping"]

    d = {"min": mins,
         "avg": avgs,
         "max": maxes}

    return json.dumps(d)

def check_api_key(f, *args, **kwargs):
    def callback():
        if request.headers.get('X-Auth') in config.api_keys:
            return f(*args, **kwargs)
        return abort(401, "Unauthenticated")
    return callback

@web.webapp.get(full_path('/api/v1/probes'))
@web.webapp.get(full_path('/api/v1/probes/'))
@check_api_key
def callback():
    return config.probes

@web.webapp.get(full_path('/api/v1/hosts'))
@web.webapp.get(full_path('/api/v1/hosts/'))
@check_api_key
def callback():
    return config.hosts


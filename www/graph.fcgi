#!/usr/bin/env python2.7
# encoding: utf-8

from cgi import escape
import sys, os
from flup.server.fcgi import WSGIServer
from urlparse import urlparse, parse_qs
import time
import tempfile

LATENSSI="/opt/latenssi"

sys.path.insert(0, LATENSSI)

# Enable virtualenv if needed
activate_this = os.path.join(LATENSSI, 'env/bin/activate_this.py')
execfile(activate_this, dict(__file__=activate_this))

from lib import config, latenssi, probes
from lib.rrd import RRD

def app(environ, start_response):
    def error(msg):
        start_response('400 Bad Request', [('Content-Type', 'text/plain')])
        return str(msg)

    params = parse_qs(environ['QUERY_STRING'])
    graph = None
    name = None
    interval = None
    if 'graph' in params:
        graph = params['graph'][0]
        if graph not in probes.probes_dict:
            yield error("Invalid probe")
            return
        else:
            name = probes.probes_dict[graph].name
    else:
        error("graph missing")
        return

    start = None
    end = None
    if 'start' in params:
        try:
            start = int(params['start'][0])
        except ValueError:
            yield error("Invalid start time")
            return
    else:
        start = time.time() - 3600 * 24
    if 'end' in params:
        try:
            end = int(params['end'][0])
        except ValueError:
            yield error("Invalid end time")
            return
    else:
        end = time.time()
    if 'interval' in params:
        interval = params['interval'][0]
        if interval not in config.intervals.keys():
            yield error("Invalid interval")
            return
        else:
            start = time.time() - config.intervals[interval]
    width = None
    height = None
    if 'width' in params:
        try:
            width = int(params['width'][0])
        except ValueError:
            yield error("Invalid width")
            return
    if 'height' in params:
        try:
            height = int(params['height'][0])
        except ValueError:
            yield error("Invalid height")
            return
    start_response('200 OK', [('Content-Type', 'image/png')])
    (tf, path) = tempfile.mkstemp()
    try:
        RRD.graph(name, path, start=start, end=end, width=width, height=height)
        f = os.fdopen(tf, 'rb')
        yield f.read()
        f.close()
    except Exception as e:
        yield "Got unknown error %s" % e
        pass
    os.remove(path)

WSGIServer(app).run()

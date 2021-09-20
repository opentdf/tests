# from https://github.com/rodrobin/flask-server-timing
# duplicated kas_core/tdf3_kas_core/server_timing eas/src/server_timing
import datetime
import logging
from contextlib import contextmanager
from functools import partial, wraps

import flask
import statsd
from flask import request

from .NullStatsClient import NullStatsClient


class Timing:
    stats_client = NullStatsClient()
    debug = False
    log = logging.getLogger(__name__)

    def __init__(self, app, host, port, service):
        Timing.log = app.logger
        try:
            Timing.stats_client = statsd.StatsClient(host, port, service)
        except OSError:
            Timing.log.info("StatsClient not found [%s,%s]", host, port, exc_info=True)
        if app.debug:
            Timing.debug = True
            Timing.log.debug(
                "Setting up after-request handler to add server timing header"
            )
            app.after_request(Timing._add_header)

    @staticmethod
    def start(key):
        if not flask.has_request_context():
            Timing.log.debug("No request context available - start timing ignored")
            return

        if not hasattr(request, "context"):
            request.context = {}

        request.context[key.replace(" ", "-")] = {"start": datetime.datetime.now()}

    @staticmethod
    def stop(key):
        if not flask.has_request_context() or not hasattr(request, "context"):
            Timing.log.debug("No request context available - stop timing ignored")
            return

        _key = key.replace(" ", "-")
        if _key not in request.context:
            Timing.log.warning("Key [%s] not found in request context", key)
            return

        stop_time = datetime.datetime.now()
        start_time = None
        if request.context.get(_key, {}) is dict:
            start_time = request.context.get(_key, {}).get("start")
        if request.context.get(_key, {}) is float:
            start_time = request.context.get(_key, {})
        if start_time:
            request.context[_key] = (stop_time - start_time).total_seconds() * 1000
        else:
            Timing.log.warning(f"No start time found for key '{key}'")

    @staticmethod
    @contextmanager
    def time(key):
        Timing.start(key)
        yield key
        Timing.stop(key)

    @staticmethod
    def timer(f=None, name=None):
        if f is None:
            return partial(Timing.timer, name=name)

        if not Timing.debug:
            Timing.log.debug(
                "Mode is not set to 'debug' - not wrapping function for timing"
            )
            return f

        @wraps(f)
        def wrapper(*args, **kwds):
            with Timing.time(name or f.__name__):
                return f(*args, **kwds)

        return wrapper

    @staticmethod
    def _add_header(response):
        Timing.stats_client.incr("requests")
        Timing.stats_client.incr(f"request.status.{str(response.status_code)}")
        Timing.stats_client.incr(f"request.path.{flask.request.full_path}")
        if flask.has_request_context() and hasattr(flask.request, "context"):
            timing_list = []
            for key, val in flask.request.context.items():
                if isinstance(val, dict):
                    stop_time = datetime.datetime.now()
                    start_time = val.get("start")
                    val = (stop_time - start_time).total_seconds() * 1000
                timing_list.append(f"{key};dur={val}")
                Timing.stats_client.timing(f"request.segment.{key}", val)
            response.headers.set("Server-Timing", ", ".join(timing_list))
        return response

from statsd.client.base import StatsClientBase


class NullStatsClient(StatsClientBase):
    def __init__(
        self, host="localhost", port=8125, prefix=None, timeout=None, ipv6=False
    ):
        """Create a new client."""
        self._host = host
        self._port = port
        self._ipv6 = ipv6
        self._timeout = timeout
        self._prefix = prefix
        self._sock = None

    def pipeline(self):
        pass

    def _send(self, data):
        pass

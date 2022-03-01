import struct
from typing import Dict, Optional
from enum import Enum


class ResourceDirectory(object):
    def __init__(self, directory: Dict[int, str]):
        self._directory = directory
        self._memoized_reverse_lookup = None

    def resolve(self, id: int) -> str:
        return self._directory[id]

    def _build_reverse_lookup(self):
        self._memoized_reverse_lookup = dict()
        for dir_id, url in self._directory.items():
            self._memoized_reverse_lookup[url] = dir_id

    def match(self, url: str):
        if self._memoized_reverse_lookup is None:
            self._build_reverse_lookup()
        return self._recursive_match(url, "")

    def _recursive_match(self, url: str, remaining: str):
        dir_id = self._memoized_reverse_lookup.get(url)
        if dir_id is not None:
            return (dir_id, remaining)
        else:
            split_url = url.rsplit("/", 1)
            if split_url[0] in ["http:/", "https:/"]:
                return (None, "/".join(split_url))
            return self._recursive_match(split_url[0], "/" + split_url[1] + remaining)


class ResourceProtocol(Enum):
    Http = 0
    Https = 1
    Directory = 255


class Protocol(object):
    def resolve(self, data: bytes) -> str:
        pass


class ProtocolHTTP(object):
    prefix = "http"

    def resolve(self, data: bytes) -> str:
        data = data.encode("utf-8")
        return "%s://%s" % (self.prefix, data)


class ProtocolHTTPS(ProtocolHTTP):
    prefix = "https"


class ProtocolDirectory(Protocol):
    def resolve(self, data: bytes, directory: ResourceDirectory) -> str:
        id = struct.unpack("!B", data[0:1])[0]
        return "%s%s" % (directory.resolve(id), data[1:].decode("utf-8"))


PROTOCOLS = {
    ResourceProtocol.Http: ProtocolHTTP(),
    ResourceProtocol.Https: ProtocolHTTPS(),
    ResourceProtocol.Directory: ProtocolDirectory(),
}


class ResourceLocator(object):
    @classmethod
    def parse(cls, data: bytes) -> ("ResourceLocator", bytes):
        locator_header = data[0:2]
        locator_mode, locator_data_length = struct.unpack("!BB", locator_header)
        locator_data = data[2 : 2 + locator_data_length]
        resource_locator = cls(ResourceProtocol(locator_mode), locator_data)
        return (resource_locator, data[2 + locator_data_length :])

    def __init__(self, mode: ResourceProtocol, data: bytes):
        self._mode = mode
        self._data = data

    @property
    def data(self):
        return self._data

    @property
    def mode(self):
        return self._mode

    def resolve(self, directory: Optional[ResourceDirectory] = None):
        if self.mode == ResourceProtocol.Directory:
            return PROTOCOLS[self._mode].resolve(self.data, directory)
        return PROTOCOLS[self._mode].resolve(self.data)

    def serialize(self) -> bytes:
        locator_header = struct.pack("!BB", self._mode.value, len(self._data))
        return b"%s%s" % (locator_header, self._data)


def create_resource_locator(
    url: str, directory: Optional[ResourceDirectory] = None
) -> ResourceLocator:
    if directory:
        dir_id, remaining = directory.match(url)
        if dir_id is not None:
            return ResourceLocator(
                ResourceProtocol.Directory, bytes([dir_id]) + remaining.encode("utf-8")
            )
    if url.startswith("http://"):
        return ResourceLocator(ResourceProtocol.Http, url[7:].encode("utf-8"))
    elif url.startswith("https://"):
        return ResourceLocator(ResourceProtocol.Https, url[8:].encode("utf-8"))
    else:
        raise ValueError("Unsupported URI")

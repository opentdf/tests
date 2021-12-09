import math

from fastapi import Query, Request, Response


class Pagination:
    _default_offset: int = 1
    _default_limit: int = 100
    _max_limit: int = 1000

    def __init__(
        self,
        request: Request,
        response: Response,
        offset: int = Query(_default_offset, ge=1),
        limit: int = Query(_default_limit, ge=1, le=_max_limit),
    ):
        self.offset = offset
        self.limit = limit
        self.request = request
        self.response = response

    def skip(self) -> int:
        return (self.offset - 1) * self.limit

    def first_page(self) -> int:
        return self._default_offset

    def last_page(self, count: int) -> int:
        return math.ceil(count / self.limit)

    def next_url(self, count: int):
        if self.offset == self.last_page(count):
            return None
        return self.request.url.include_query_params(offset=self.offset + 1)

    def prev_url(self):
        if self.offset == self.first_page():
            return None
        return self.request.url.include_query_params(offset=self.offset - 1)

    def first_url(self):
        return self.request.url.include_query_params(offset=self.first_page())

    def last_url(self, count: int):
        return self.request.url.include_query_params(offset=self.last_page(count))

    def paginate(self, item_list: list):
        count = len(item_list)

        link_headers = []

        self_url = self.request.url
        link_headers.append('<{url}>; rel="{rel}"'.format(url=self_url, rel="self"))

        first_url = self.first_url()
        link_headers.append('<{url}>; rel="{rel}"'.format(url=first_url, rel="first"))

        last_url = self.last_url(count)
        link_headers.append('<{url}>; rel="{rel}"'.format(url=last_url, rel="last"))

        next_url = self.next_url(count)
        if next_url is not None:
            link_headers.append('<{url}>; rel="{rel}"'.format(url=next_url, rel="next"))

        prev_url = self.prev_url()
        if prev_url is not None:
            link_headers.append('<{url}>; rel="{rel}"'.format(url=prev_url, rel="prev"))

        self.response.headers["x-total-count"] = str(count)
        self.response.headers["link"] = ",".join(link_headers)

        return item_list[self.skip() : self.skip() + self.limit]

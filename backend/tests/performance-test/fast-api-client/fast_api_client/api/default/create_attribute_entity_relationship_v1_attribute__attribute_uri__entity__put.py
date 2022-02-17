from typing import Any, Dict, List, Optional, Union

import httpx

from ...client import Client
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    client: Client,
    attribute_uri: str,
    json_body: List[str],
) -> Dict[str, Any]:
    url = "{}/v1/attribute/{attributeURI}/entity/".format(
        client.base_url, attributeURI=attribute_uri
    )

    headers: Dict[str, Any] = client.get_headers()
    cookies: Dict[str, Any] = client.get_cookies()

    json_json_body = json_body

    return {
        "url": url,
        "headers": headers,
        "cookies": cookies,
        "timeout": client.get_timeout(),
        "json": json_json_body,
    }


def _parse_response(
    *, response: httpx.Response
) -> Optional[Union[None, HTTPValidationError]]:
    if response.status_code == 200:
        response_200 = None

        return response_200
    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422
    return None


def _build_response(
    *, response: httpx.Response
) -> Response[Union[None, HTTPValidationError]]:
    return Response(
        status_code=response.status_code,
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(response=response),
    )


def sync_detailed(
    *,
    client: Client,
    attribute_uri: str,
    json_body: List[str],
) -> Response[Union[None, HTTPValidationError]]:
    kwargs = _get_kwargs(
        client=client,
        attribute_uri=attribute_uri,
        json_body=json_body,
    )

    response = httpx.put(
        **kwargs,
    )

    return _build_response(response=response)


def sync(
    *,
    client: Client,
    attribute_uri: str,
    json_body: List[str],
) -> Optional[Union[None, HTTPValidationError]]:
    """ """

    return sync_detailed(
        client=client,
        attribute_uri=attribute_uri,
        json_body=json_body,
    ).parsed


async def asyncio_detailed(
    *,
    client: Client,
    attribute_uri: str,
    json_body: List[str],
) -> Response[Union[None, HTTPValidationError]]:
    kwargs = _get_kwargs(
        client=client,
        attribute_uri=attribute_uri,
        json_body=json_body,
    )

    async with httpx.AsyncClient() as _client:
        response = await _client.put(**kwargs)

    return _build_response(response=response)


async def asyncio(
    *,
    client: Client,
    attribute_uri: str,
    json_body: List[str],
) -> Optional[Union[None, HTTPValidationError]]:
    """ """

    return (
        await asyncio_detailed(
            client=client,
            attribute_uri=attribute_uri,
            json_body=json_body,
        )
    ).parsed

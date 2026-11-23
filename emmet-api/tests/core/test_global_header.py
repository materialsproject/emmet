import pytest
from fastapi import HTTPException
from starlette.requests import Request

from emmet.api.core.global_header import GlobalHeaderProcessor
from emmet.api.routes.materials.materials.query_operators import LicenseQuery

BY_C = {"criteria": {"builder_meta.license": "BY-C"}}
BY_NC = {"criteria": {"builder_meta.license": "BY-NC"}}
ALL = {"criteria": {"builder_meta.license": {"$in": ["BY-C", "BY-NC"]}}}


def configure(headers: dict, query_string: str = ""):
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
            "query_string": query_string.encode(),
        }
    )
    return GlobalHeaderProcessor().configure_query_on_request(request, LicenseQuery())


@pytest.mark.parametrize(
    "headers,query_string,expected",
    [
        # no groups: license param is ignored
        ({}, "license=All", BY_C),
        # no license param: default depends on NC authorization
        ({"x-consumer-groups": "foo"}, "", BY_C),
        ({"x-consumer-groups": " admin "}, "", ALL),
        # license param passes through when permitted
        ({"x-consumer-groups": "x,TERMS:ACCEPT-NC"}, "license=BY-NC", BY_NC),
        ({"x-consumer-groups": "admin"}, "license=BY-C", BY_C),
        ({"x-consumer-groups": "foo"}, "license=BY-C", BY_C),
        # empty license param falls back to default
        ({"x-consumer-groups": "admin"}, "license=", ALL),
        # falls back to x-authenticated-groups
        ({"x-authenticated-groups": "admin"}, "", ALL),
    ],
)
def test_configure_query(headers, query_string, expected):
    assert configure(headers, query_string) == expected


@pytest.mark.parametrize(
    "headers,query_string",
    [
        ({"x-consumer-groups": "foo"}, "license=All"),
        ({"x-consumer-groups": "foo"}, "license=BY-NC"),
        # x-consumer-groups takes precedence over x-authenticated-groups
        (
            {"x-consumer-groups": "foo", "x-authenticated-groups": "admin"},
            "license=All",
        ),
    ],
)
def test_configure_query_forbidden(headers, query_string):
    with pytest.raises(HTTPException) as exc:
        configure(headers, query_string)
    assert exc.value.status_code == 403

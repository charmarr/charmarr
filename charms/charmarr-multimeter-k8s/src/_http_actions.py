# Copyright 2025 The Charmarr Project
# See LICENSE file for licensing details.

"""HTTP request action handlers for integration testing."""

import json
from typing import Any

import httpx
import ops
from tenacity import retry, stop_after_attempt, wait_exponential


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _make_request(
    method: str,
    url: str,
    headers: dict[str, str],
    cookies: dict[str, str],
    auth: httpx.BasicAuth | None,
    body: str | None,
    content_type: str,
    timeout: int,
) -> httpx.Response:
    """Make HTTP request with retry logic."""
    kwargs: dict[str, Any] = {
        "headers": headers,
        "cookies": cookies,
    }
    if auth is not None:
        kwargs["auth"] = auth

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        if method == "GET":
            return client.get(url, **kwargs)
        elif method == "POST":
            if content_type == "application/json":
                if "content-type" not in {k.lower() for k in headers}:
                    headers["Content-Type"] = "application/json"
                kwargs["content"] = body
            else:
                data = None
                if body:
                    try:
                        data = json.loads(body)
                    except json.JSONDecodeError:
                        data = dict(pair.split("=", 1) for pair in body.split("&") if "=" in pair)
                kwargs["data"] = data
            return client.post(url, **kwargs)
        elif method == "PUT":
            kwargs["content"] = body
            return client.put(url, **kwargs)
        elif method == "DELETE":
            return client.delete(url, **kwargs)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")


def handle_http_request(event: ops.ActionEvent) -> None:
    """Make HTTP request from within the cluster.

    Supports GET/POST with optional basic auth, cookies, and custom headers.
    Returns status code, response body, and any cookies set by the server.
    Retries up to 3 times with exponential backoff on failure.
    """
    url = event.params["url"]
    method = event.params.get("method", "GET").upper()
    body = event.params.get("body")
    content_type = event.params.get("content-type", "application/x-www-form-urlencoded")
    headers_json = event.params.get("headers")
    basic_auth = event.params.get("basic-auth")
    cookies_json = event.params.get("cookies")
    timeout = event.params.get("timeout", 10)

    headers: dict[str, str] = {}
    if headers_json:
        try:
            headers = json.loads(headers_json)
        except json.JSONDecodeError as e:
            event.fail(f"Invalid headers JSON: {e}")
            return

    cookies: dict[str, str] = {}
    if cookies_json:
        try:
            cookies = json.loads(cookies_json)
        except json.JSONDecodeError as e:
            event.fail(f"Invalid cookies JSON: {e}")
            return

    auth = None
    if basic_auth and ":" in basic_auth:
        username, password = basic_auth.split(":", 1)
        auth = httpx.BasicAuth(username, password)

    try:
        response = _make_request(
            method=method,
            url=url,
            headers=headers,
            cookies=cookies,
            auth=auth,
            body=body,
            content_type=content_type,
            timeout=timeout,
        )

        response_cookies = dict(response.cookies)
        response_body = response.text
        if len(response_body) > 10000:
            response_body = response_body[:10000] + "... (truncated)"

        event.set_results(
            {
                "status-code": str(response.status_code),
                "body": response_body,
                "cookies": json.dumps(response_cookies) if response_cookies else "",
            }
        )

    except httpx.TimeoutException:
        event.fail(f"Request timed out after {timeout}s (3 attempts)")
    except httpx.RequestError as e:
        event.fail(f"Request failed after 3 attempts: {e}")
    except ValueError as e:
        event.fail(str(e))
    except Exception as e:
        event.fail(f"Unexpected error: {e}")

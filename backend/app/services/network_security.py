"""SSRF guardrails for user-configured HTTP and database destinations."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

from app.core.config import settings


class UnsafeDestinationError(ValueError):
    pass


def _validate_ip(address: str) -> None:
    ip = ipaddress.ip_address(address)
    if not settings.ALLOW_PRIVATE_CONNECTORS and (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        or ip.is_reserved or ip.is_unspecified
    ):
        raise UnsafeDestinationError("Private, local, reserved and metadata destinations are blocked")


def validate_outbound_host(host: str, port: int) -> None:
    hostname = str(host or "").strip().rstrip(".")
    if not hostname or hostname.lower() == "localhost":
        raise UnsafeDestinationError("A public destination hostname is required")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(hostname, int(port), type=socket.SOCK_STREAM)
        }
    except (OSError, ValueError) as exc:
        raise UnsafeDestinationError("Destination hostname could not be resolved") from exc
    if not addresses:
        raise UnsafeDestinationError("Destination hostname did not resolve")
    for address in addresses:
        _validate_ip(address)


def validate_outbound_url(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    allowed_schemes = {"https"}
    if settings.ALLOW_INSECURE_HTTP_CONNECTORS:
        allowed_schemes.add("http")
    if parsed.scheme.lower() not in allowed_schemes:
        raise UnsafeDestinationError("Only HTTPS API destinations are allowed")
    if parsed.username or parsed.password:
        raise UnsafeDestinationError("Credentials in URLs are not allowed; use encrypted headers")
    if not parsed.hostname:
        raise UnsafeDestinationError("API destination hostname is required")
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    validate_outbound_host(parsed.hostname, port)
    return parsed.geturl()


def validated_redirect_url(current_url: str, location: str) -> str:
    target = urljoin(current_url, location)
    return validate_outbound_url(target)

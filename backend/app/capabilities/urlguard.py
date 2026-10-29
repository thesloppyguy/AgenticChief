"""Outbound URL checks for admin-supplied connection addresses.

Not a full SSRF defence (DNS can change between check and use), but it stops the obvious mistakes:
non-HTTP schemes, embedded credentials, and cloud-metadata / link-local targets. Private and loopback addresses are allowed
on purpose: internal HR systems usually live there.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from .types import ConfigError


def check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ConfigError("URL must be http(s) with a host")
    if parts.username or parts.password:
        raise ConfigError("credentials must not be embedded in the URL")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80),
                                   type=socket.SOCK_STREAM)
    except OSError as e:
        raise ConfigError("host does not resolve") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        ip = getattr(ip, "ipv4_mapped", None) or ip  # ::ffff:169.254.169.254 is the same address
        if ip.is_loopback:  # note: Python also calls ::1 "reserved", so loopback is allowed before that check
            continue
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified:
            raise ConfigError("that address range is not allowed (link-local, multicast or unspecified)")

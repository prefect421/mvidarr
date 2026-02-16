"""
URL Validator for SSRF Protection
Blocks requests to private/loopback IP ranges and internal services.
"""

import ipaddress
import socket
from typing import List, Optional
from urllib.parse import urlparse

from src.utils.logger import get_logger

logger = get_logger("mvidarr.url_validator")

# Private/reserved IP ranges that should be blocked
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("10.0.0.0/8"),  # Private Class A
    ipaddress.ip_network("172.16.0.0/12"),  # Private Class B
    ipaddress.ip_network("192.168.0.0/16"),  # Private Class C
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("0.0.0.0/8"),  # Current network
    ipaddress.ip_network("100.64.0.0/10"),  # Shared address space
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]

# Ports commonly used by internal services
_BLOCKED_PORTS = {6379, 3306, 5432, 27017, 11211, 9200, 2379}


def is_url_safe(
    url: str,
    allow_local_network: bool = False,
    allowed_hosts: Optional[List[str]] = None,
) -> bool:
    """
    Check if a URL is safe to fetch (not pointing to internal/private resources).

    Args:
        url: URL to validate
        allow_local_network: If True, allow 192.168.x.x addresses (for self-hosted setups)
        allowed_hosts: Optional list of explicitly allowed hostnames/IPs

    Returns:
        True if the URL is safe to fetch
    """
    try:
        parsed = urlparse(url)

        # Only allow http and https
        if parsed.scheme not in ("http", "https"):
            logger.warning(f"SSRF blocked: non-HTTP scheme '{parsed.scheme}' in {url}")
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # Check blocked ports
        if port in _BLOCKED_PORTS:
            logger.warning(f"SSRF blocked: internal service port {port} in {url}")
            return False

        # Check against allowed hosts
        if allowed_hosts and hostname in allowed_hosts:
            return True

        # Resolve hostname to IP
        try:
            addr_infos = socket.getaddrinfo(hostname, port)
        except socket.gaierror:
            logger.warning(f"SSRF blocked: DNS resolution failed for {hostname}")
            return False

        for family, type_, proto, canonname, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            for network in _BLOCKED_NETWORKS:
                if allow_local_network and network == ipaddress.ip_network(
                    "192.168.0.0/16"
                ):
                    continue
                if ip in network:
                    logger.warning(
                        f"SSRF blocked: {hostname} resolves to private IP {ip_str}"
                    )
                    return False

        return True

    except Exception as e:
        logger.error(f"URL validation error for {url}: {e}")
        return False


def validate_url_or_raise(
    url: str,
    allow_local_network: bool = False,
    allowed_hosts: Optional[List[str]] = None,
) -> None:
    """
    Validate URL and raise ValueError if unsafe.

    Args:
        url: URL to validate
        allow_local_network: If True, allow local network addresses
        allowed_hosts: Optional list of explicitly allowed hostnames
    """
    if not is_url_safe(url, allow_local_network, allowed_hosts):
        raise ValueError(f"URL blocked by SSRF protection: {url}")

"""Защита от SSRF: в облачной версии пользовательские HTTP-запросы не должны ходить во внутреннюю сеть."""
import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from ..config import settings


def _is_forbidden(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast
        or addr.is_reserved or addr.is_unspecified
    )


async def _resolve(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError(f"Не удалось определить адрес {host}")
    return [i[4][0] for i in infos]


async def assert_public_url(url: str) -> None:
    """Бросает ValueError, если URL ведёт во внутреннюю сеть. В локальной версии не проверяет."""
    if not settings.is_cloud:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Недопустимый URL")
    host = parsed.hostname
    try:
        ipaddress.ip_address(host)
        ips = [host]
    except ValueError:
        ips = await _resolve(host, parsed.port or 443)
    for ip in ips:
        if _is_forbidden(ip):
            raise ValueError("Запросы во внутреннюю сеть запрещены в облачной версии")

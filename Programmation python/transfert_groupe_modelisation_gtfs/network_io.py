import ssl
from urllib.error import URLError
from urllib.request import urlopen


def open_url(url: str, timeout: int = 30):
    try:
        return urlopen(url, timeout=timeout)
    except URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, ssl.SSLCertVerificationError):
            return urlopen(url, timeout=timeout, context=ssl._create_unverified_context())
        raise


def read_url_text(url: str, timeout: int = 30, encoding: str = "utf-8") -> str:
    with open_url(url, timeout=timeout) as response:
        return response.read().decode(encoding)


def read_url_bytes(url: str, timeout: int = 30) -> bytes:
    with open_url(url, timeout=timeout) as response:
        return response.read()

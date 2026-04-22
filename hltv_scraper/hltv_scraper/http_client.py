"""Compatibility shim for Scrapy package imports.

The canonical fallback transport implementation lives in the submodule root
`http_client.py`. Scrapy loads spiders from inside `hltv_scraper/`, so this
module re-exports the root helper under a package-local import path without
duplicating the implementation.
"""

from importlib import import_module
from pathlib import Path
import sys

_ROOT_DIR = Path(__file__).resolve().parents[2]
_ROOT_DIR_STR = str(_ROOT_DIR)
_inserted_path = False

if _ROOT_DIR_STR not in sys.path:
    sys.path.insert(0, _ROOT_DIR_STR)
    _inserted_path = True

try:
    _root_http_client = import_module("http_client")
finally:
    if _inserted_path:
        sys.path.remove(_ROOT_DIR_STR)


HLTV_IMPERSONATION_CHAIN = _root_http_client.HLTV_IMPERSONATION_CHAIN
LIQUIPEDIA_IMPERSONATION_CHAIN = _root_http_client.LIQUIPEDIA_IMPERSONATION_CHAIN
FALLBACK_RETRY_STATUSES = _root_http_client.FALLBACK_RETRY_STATUSES
CHALLENGE_BODY_MARKERS = _root_http_client.CHALLENGE_BODY_MARKERS
build_impersonation_chain = _root_http_client.build_impersonation_chain
detect_cloudflare_challenge = _root_http_client.detect_cloudflare_challenge
is_retryable_response = _root_http_client.is_retryable_response
get_with_impersonation_fallback = _root_http_client.get_with_impersonation_fallback

__all__ = [
    "HLTV_IMPERSONATION_CHAIN",
    "LIQUIPEDIA_IMPERSONATION_CHAIN",
    "FALLBACK_RETRY_STATUSES",
    "CHALLENGE_BODY_MARKERS",
    "build_impersonation_chain",
    "detect_cloudflare_challenge",
    "is_retryable_response",
    "get_with_impersonation_fallback",
]

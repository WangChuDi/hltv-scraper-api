import subprocess
import sys
from pathlib import Path

import http_client as root_http_client
from hltv_scraper.hltv_scraper import http_client as package_http_client


def test_match_spider_imports_from_scrapy_workdir():
    repo_root = Path(__file__).resolve().parents[1]
    scrapy_root = repo_root / "hltv_scraper"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib; importlib.import_module('hltv_scraper.spiders.hltv_match')",
        ],
        cwd=scrapy_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_package_http_client_reexports_root_helper_objects():
    assert (
        package_http_client.get_with_impersonation_fallback
        is root_http_client.get_with_impersonation_fallback
    )
    assert (
        package_http_client.build_impersonation_chain
        is root_http_client.build_impersonation_chain
    )
    assert (
        package_http_client.HLTV_IMPERSONATION_CHAIN
        == root_http_client.HLTV_IMPERSONATION_CHAIN
    )

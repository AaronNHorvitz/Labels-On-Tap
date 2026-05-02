"""Public COLA Registry search helpers.

These helpers use the public registry's own search + save-to-file flow through a
single HTTP session so daily search results can be exported reproducibly.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import urljoin

import httpx

from cola_etl.http import make_client


PUBLIC_COLA_BASE_URL = "https://ttbonline.gov/colasonline/"
SEARCH_PAGE_URL = urljoin(PUBLIC_COLA_BASE_URL, "publicSearchColasBasic.do")
SEARCH_POST_URL = urljoin(
    PUBLIC_COLA_BASE_URL,
    "publicSearchColasBasicProcess.do?action=search",
)
SEARCH_EXPORT_URL = urljoin(
    PUBLIC_COLA_BASE_URL,
    "publicSaveSearchResultsToFile.do?path=/publicSearchColasBasicProcess",
)


def ttb_date(value: date) -> str:
    """Format a date for the public registry search form."""

    return value.strftime("%m/%d/%Y")


def search_form_payload(search_date: date) -> dict[str, str]:
    """Build the daily public search payload."""

    formatted = ttb_date(search_date)
    return {
        "searchCriteria.dateCompletedFrom": formatted,
        "searchCriteria.dateCompletedTo": formatted,
        "searchCriteria.productOrFancifulName": "",
        "searchCriteria.productNameSearchType": "B",
        "searchCriteria.classTypeFrom": "",
        "searchCriteria.classTypeTo": "",
        "searchCriteria.originCode": "",
    }


def fetch_search_results_csv(
    search_date: date,
    *,
    timeout: float = 30.0,
    verify: bool = True,
) -> tuple[bytes, httpx.Response, httpx.Response]:
    """Run a one-day public registry search and export the CSV result."""

    with make_client(timeout=timeout, verify=verify) as client:
        client.get(SEARCH_PAGE_URL)
        search_response = client.post(
            SEARCH_POST_URL,
            data=search_form_payload(search_date),
        )
        search_response.raise_for_status()
        export_response = client.get(SEARCH_EXPORT_URL)
        export_response.raise_for_status()
        return export_response.content, search_response, export_response

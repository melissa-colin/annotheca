"""Tests for the PDF lookup of annotheca.sources, with the web faked."""

import httpx

from annotheca import bibtex
from annotheca import sources

_PDF = b'%PDF-1.7 fake'
_ENTRY = bibtex.Entry('article', 'doe2024', {
    'title': 'Deep Things', 'doi': '10.1000/deep'})


def _client(pages: dict[str, httpx.Response]) -> httpx.Client:
    """A client answering `pages` by URL without query, 404 elsewhere."""
    def handle(request: httpx.Request) -> httpx.Response:
        url = str(request.url.copy_with(query=None))
        return pages.get(url, httpx.Response(404))
    return httpx.Client(transport=httpx.MockTransport(handle))


def _semantic_scholar(open_access_url: str) -> httpx.Response:
    return httpx.Response(200, json={
        'externalIds': {}, 'openAccessPdf': {'url': open_access_url}})


def test_pdf_announced_by_a_landing_page_is_followed():
    client = _client({
        'https://api.semanticscholar.org/graph/v1/paper/DOI:10.1000/deep':
            _semantic_scholar('https://repo.org/item/1'),
        'https://repo.org/item/1': httpx.Response(200, html=(
            '<meta content="/files/deep.pdf?x=1&amp;y=2"'
            ' name="citation_pdf_url">')),
        'https://repo.org/files/deep.pdf': httpx.Response(200, content=_PDF),
    })
    assert sources.find_pdf(_ENTRY, client) == _PDF


def test_openalex_copies_are_tried_after_semantic_scholar():
    client = _client({
        'https://api.semanticscholar.org/graph/v1/paper/DOI:10.1000/deep':
            _semantic_scholar('https://orcid.org/0000'),
        'https://orcid.org/0000': httpx.Response(200, html='<p>Profile</p>'),
        'https://api.openalex.org/works/doi:10.1000/deep': httpx.Response(
            200, json={'locations': [
                {'is_oa': False, 'pdf_url': 'https://paywall.org/deep.pdf'},
                {'is_oa': True, 'pdf_url': None,
                 'landing_page_url': 'https://repo.org/item/1'},
                {'is_oa': True, 'pdf_url': 'https://uni.edu/deep.pdf'},
            ]}),
        'https://uni.edu/deep.pdf': httpx.Response(200, content=_PDF),
    })
    assert sources.find_pdf(_ENTRY, client) == _PDF


def test_no_pdf_anywhere():
    assert sources.find_pdf(_ENTRY, _client({})) is None

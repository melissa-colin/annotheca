"""Remote scholarly sources: resolves pasted references and finds PDFs.

Uses doi.org content negotiation, arXiv, Crossref, Semantic Scholar and
OpenAlex. None of them needs an API key.
"""

import html
import re
import time
from collections.abc import Iterator
from urllib import parse

import httpx

from annotheca import __version__
from annotheca import bibtex

_USER_AGENT = (
    f'Annotheca/{__version__} (+https://github.com/melissa-colin/annotheca)')
_SEMANTIC_SCHOLAR = 'https://api.semanticscholar.org/graph/v1/paper'
_OPENALEX = 'https://api.openalex.org/works'
# Repository and publisher landing pages announce their PDF in this tag.
_PDF_META_RE = re.compile(
    r'<meta\b[^>]*\bname=["\']citation_pdf_url["\'][^>]*>', re.IGNORECASE)
_CONTENT_RE = re.compile(r'\bcontent=["\']([^"\']+)', re.IGNORECASE)
# Semantic Scholar rate-limits anonymous clients; busy answers are retried.
_RATE_LIMIT_RETRIES = 3
_RATE_LIMIT_DELAY_S = 1.5


class ResolveError(Exception):
    """Pasted text could not be turned into references.

    The message is a short error code: 'unresolvable' or 'unreachable'.
    """


def make_client() -> httpx.Client:
    """Returns an HTTP client configured for the scholarly APIs."""
    return httpx.Client(
        timeout=20, follow_redirects=True,
        headers={'User-Agent': _USER_AGENT})


def resolve(text: str, client: httpx.Client) -> list[bibtex.Entry]:
    """Turns pasted text into BibTeX entries.

    Accepts BibTeX (one or more entries), DOIs, arXiv identifiers or URLs,
    one per line, and free-form formatted citations (APA, IEEE, ...).

    Raises:
        ResolveError: Nothing usable was found, or a source was unreachable.
    """
    text = text.strip()
    if text.startswith('@'):
        entries = bibtex.parse(text)
    else:
        lines = [line for line in text.splitlines() if line.strip()]
        if not all(map(_has_identifier, lines)):
            lines = [text]
        try:
            entries = [_resolve_one(line, client) for line in lines]
        except httpx.HTTPError as error:
            raise ResolveError('unreachable') from error
    if not entries:
        raise ResolveError('unresolvable')
    return entries


def find_pdf(entry: bibtex.Entry, client: httpx.Client) -> bytes | None:
    """Downloads an open-access PDF of the entry, or returns None."""
    tried = set()
    for url in _pdf_candidates(entry, client):
        if url not in tried:
            tried.add(url)
            if pdf := _download_pdf(url, client):
                return pdf
    return None


def _download_pdf(url: str, client: httpx.Client,
                  follow_landing_page: bool = True) -> bytes | None:
    """Downloads `url` if it is a PDF, or the PDF its landing page points to."""
    try:
        response = client.get(url)
    except httpx.HTTPError:
        return None
    if not response.is_success:
        return None
    if response.content.startswith(b'%PDF'):
        return response.content
    if follow_landing_page and (tag := _PDF_META_RE.search(response.text)):
        if content := _CONTENT_RE.search(tag.group()):
            pdf_url = parse.urljoin(
                str(response.url), html.unescape(content.group(1)))
            return _download_pdf(pdf_url, client, follow_landing_page=False)
    return None


def _has_identifier(text: str) -> bool:
    return bool(bibtex.find_doi(text) or bibtex.find_arxiv_id(text))


def _resolve_one(text: str, client: httpx.Client) -> bibtex.Entry:
    if doi := bibtex.find_doi(text):
        source = _bibtex_from_doi(doi, client)
    elif arxiv_id := bibtex.find_arxiv_id(text):
        source = _get(client, f'https://arxiv.org/bibtex/{arxiv_id}').text
    else:
        source = _bibtex_from_doi(_search_crossref(text, client), client)
    entries = bibtex.parse(source)
    if not entries:
        raise ResolveError('unresolvable')
    entry = entries[0]
    entry.citekey = bibtex.make_citekey(entry.fields)
    return entry


def _bibtex_from_doi(doi: str, client: httpx.Client) -> str:
    return _get(client, f'https://doi.org/{doi}',
                headers={'Accept': 'application/x-bibtex; charset=utf-8'}).text


def _search_crossref(citation: str, client: httpx.Client) -> str:
    response = _get(client, 'https://api.crossref.org/works',
                    params={'query.bibliographic': citation, 'rows': 1})
    items = response.json()['message']['items']
    if not items:
        raise ResolveError('unresolvable')
    return items[0]['DOI']


def _get(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    response = client.get(url, **kwargs)
    if response.status_code == 404:
        raise ResolveError('unresolvable')
    response.raise_for_status()
    return response


def _pdf_candidates(entry: bibtex.Entry, client: httpx.Client) -> Iterator[str]:
    """Yields likely PDF URLs, cheapest first; lookups happen lazily."""
    if entry.arxiv_id:
        yield f'https://arxiv.org/pdf/{entry.arxiv_id}'
    paper = _semantic_scholar(entry, client)
    if arxiv_id := paper.get('externalIds', {}).get('ArXiv'):
        yield f'https://arxiv.org/pdf/{arxiv_id}'
    if url := (paper.get('openAccessPdf') or {}).get('url'):
        yield url
    if entry.doi:
        yield from _openalex_urls(entry.doi, client)


def _openalex_urls(doi: str, client: httpx.Client) -> Iterator[str]:
    """Yields the PDFs, then the landing pages, of OpenAlex's open copies."""
    try:
        response = client.get(f'{_OPENALEX}/doi:{doi}')
    except httpx.HTTPError:
        return
    if not response.is_success:
        return
    locations = [location for location in response.json()['locations']
                 if location.get('is_oa')]
    for key in ('pdf_url', 'landing_page_url'):
        yield from (location[key] for location in locations
                    if location.get(key))


def _semantic_scholar(entry: bibtex.Entry, client: httpx.Client) -> dict:
    params = {'fields': 'externalIds,openAccessPdf'}
    title = bibtex.plain(entry.fields.get('title', ''))
    if entry.doi:
        url = f'{_SEMANTIC_SCHOLAR}/DOI:{entry.doi}'
    elif title:
        url = f'{_SEMANTIC_SCHOLAR}/search/match'
        params['query'] = title
    else:
        return {}
    for attempt in range(1, _RATE_LIMIT_RETRIES + 1):
        try:
            response = client.get(url, params=params)
        except httpx.HTTPError:
            return {}
        if response.status_code != 429:
            break
        time.sleep(_RATE_LIMIT_DELAY_S * attempt)
    if not response.is_success:
        return {}
    data = response.json()
    return data['data'][0] if data.get('data') else data

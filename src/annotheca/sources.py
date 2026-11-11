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
_URL_RE = re.compile(r'^https?://\S+$')
# Publisher and repository pages describe their paper with
# <meta name="citation_..."> tags (the Highwire Press convention).
_META_TAG_RE = re.compile(r'<meta\b[^>]*>', re.IGNORECASE)
_META_NAME_RE = re.compile(r'\bname=["\'](citation_\w+)', re.IGNORECASE)
_META_CONTENT_RE = re.compile(r'\bcontent=["\']([^"\']*)', re.IGNORECASE)
# A free-text search result is accepted only if the pasted citation contains
# at least this share of the words of the title found.
_TITLE_MATCH_SHARE = 0.8
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

    Accepts BibTeX (one or more entries); DOIs, arXiv identifiers or links to
    paper pages, one per line; and free-form formatted citations (APA, IEEE,
    ...). A citation is never matched to a paper whose title it lacks.

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
    pdf_urls = _citation_meta(response.text).get('citation_pdf_url')
    if follow_landing_page and pdf_urls:
        pdf_url = parse.urljoin(str(response.url), pdf_urls[0])
        return _download_pdf(pdf_url, client, follow_landing_page=False)
    return None


def _has_identifier(text: str) -> bool:
    return bool(bibtex.find_doi(text) or bibtex.find_arxiv_id(text)
                or _URL_RE.match(text.strip()))


def _resolve_one(text: str, client: httpx.Client) -> bibtex.Entry:
    if doi := bibtex.find_doi(text):
        source = _bibtex_from_doi(doi, client)
    elif arxiv_id := bibtex.find_arxiv_id(text):
        source = _get(client, f'https://arxiv.org/bibtex/{arxiv_id}').text
    elif _URL_RE.match(text.strip()):
        return _from_paper_page(text.strip(), client)
    else:
        source = _bibtex_from_doi(_search_crossref(text, client), client)
    entries = bibtex.parse(source)
    if not entries:
        raise ResolveError('unresolvable')
    entry = entries[0]
    # Some registrars leave HTML entities such as &amp; in their BibTeX.
    entry.fields = {name: _latex_escape(html.unescape(value))
                    for name, value in entry.fields.items()}
    entry.citekey = bibtex.make_citekey(entry.fields)
    return entry


def _from_paper_page(url: str, client: httpx.Client) -> bibtex.Entry:
    """Builds an entry from the citation tags of a paper's web page."""
    response = _get(client, url)
    meta = _citation_meta(response.text)
    if doi := bibtex.find_doi(' '.join(meta.get('citation_doi', []))):
        return _resolve_one(doi, client)
    if not meta.get('citation_title'):
        raise ResolveError('unresolvable')
    date = ' '.join(meta.get('citation_publication_date', [])
                    + meta.get('citation_date', []))
    fields = {
        'title': meta['citation_title'][0],
        'author': ' and '.join(meta.get('citation_author', [])),
        'year': next(iter(re.findall(r'\d{4}', date)), ''),
        'url': str(response.url),
    }
    if journal := meta.get('citation_journal_title'):
        entry_type, fields['journal'] = 'article', journal[0]
    elif conference := meta.get('citation_conference_title'):
        entry_type, fields['booktitle'] = 'inproceedings', conference[0]
    else:
        entry_type = 'misc'
    fields = {name: _latex_escape(value)
              for name, value in fields.items() if value}
    return bibtex.Entry(entry_type, bibtex.make_citekey(fields), fields)


def _citation_meta(page: str) -> dict[str, list[str]]:
    """The values of the citation_* meta tags of a web page, by name."""
    meta = {}
    for tag in _META_TAG_RE.findall(page):
        name = _META_NAME_RE.search(tag)
        content = _META_CONTENT_RE.search(tag)
        if name and content and content.group(1).strip():
            meta.setdefault(name.group(1).lower(), []).append(
                html.unescape(content.group(1)).strip())
    return meta


def _latex_escape(value: str) -> str:
    """Escapes the characters LaTeX reads as commands, except in URLs."""
    if value.startswith('http'):
        return value
    return re.sub(r'(?<!\\)([&%#])', r'\\\1', value)


def _bibtex_from_doi(doi: str, client: httpx.Client) -> str:
    return _get(client, f'https://doi.org/{doi}',
                headers={'Accept': 'application/x-bibtex; charset=utf-8'}).text


def _search_crossref(citation: str, client: httpx.Client) -> str:
    response = _get(client, 'https://api.crossref.org/works',
                    params={'query.bibliographic': citation, 'rows': 1})
    items = response.json()['message']['items']
    if not items or not _cites_title(citation, items[0].get('title', [''])[0]):
        raise ResolveError('unresolvable')
    return items[0]['DOI']


def _cites_title(citation: str, title: str) -> bool:
    """Whether `citation` contains most of the words of `title`."""
    def words(text):
        return set(re.findall(r'[a-z0-9]{3,}', text.lower()))
    title_words = words(title)
    found = title_words & words(citation)
    return bool(title_words) and (
        len(found) >= _TITLE_MATCH_SHARE * len(title_words))


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
    if url := entry.fields.get('url'):
        yield url
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

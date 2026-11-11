"""Tests for annotheca.sources, with the web faked."""

import httpx
import pytest

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


_EPRINT_PAGE = """<html><head>
<meta name="citation_title" content="Signatures &amp; Credentials">
<meta name="citation_author" content="Olivier Sanders">
<meta content="Ada Lovelace" name="citation_author">
<meta name="citation_journal_title" content="Cryptology ePrint Archive">
<meta name="citation_publication_date" content="2019/10/15">
</head></html>"""


def test_paper_pages_are_read_from_their_citation_tags():
    client = _client({
        'https://eprint.iacr.org/2019/1201': httpx.Response(
            200, html=_EPRINT_PAGE),
        'https://eprint.iacr.org/2004/077': httpx.Response(
            200, html=_EPRINT_PAGE.replace('2019/10/15', '2004')),
    })
    first, second = sources.resolve(
        'https://eprint.iacr.org/2019/1201\nhttps://eprint.iacr.org/2004/077',
        client)
    assert first == bibtex.Entry('article', 'sanders2019signatures', {
        'title': 'Signatures \\& Credentials',
        'author': 'Olivier Sanders and Ada Lovelace',
        'year': '2019',
        'url': 'https://eprint.iacr.org/2019/1201',
        'journal': 'Cryptology ePrint Archive'})
    assert second.fields['year'] == '2004'


def test_paper_pages_with_a_doi_use_it():
    client = _client({
        'https://publisher.org/paper': httpx.Response(200, html=(
            '<meta name="citation_doi" content="10.1000/deep">')),
        'https://doi.org/10.1000/deep': httpx.Response(200, text=(
            '@inproceedings{X, title={Deep Things}, author={Doe, Jane},'
            ' year={2024}, booktitle={Data Mining &amp; Discovery}}')),
    })
    (entry,) = sources.resolve('https://publisher.org/paper', client)
    assert entry.citekey == 'doe2024deep'
    assert entry.fields['booktitle'] == 'Data Mining \\& Discovery'


@pytest.mark.parametrize('text, pages', [
    ('https://www.example.org', {'https://www.example.org': httpx.Response(
        200, html='<title>Not a paper</title>')}),
    ('Les Misérables, Victor Hugo, 1862', {
        'https://api.crossref.org/works': httpx.Response(200, json={
            'message': {'items': [{'DOI': '10.1000/x',
                                   'title': ['An unrelated thesis']}]}})}),
])
def test_references_that_cannot_be_matched_are_refused(text, pages):
    with pytest.raises(sources.ResolveError, match='unresolvable'):
        sources.resolve(text, _client(pages))

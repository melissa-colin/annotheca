"""Tests for annotheca.mcp_server, through an in-process MCP client."""

import asyncio

import httpx
import mcp
from mcp import types

from annotheca import library as library_lib
from annotheca import mcp_server

_DOI_BIBTEX = """@article{Doe_2024, title={Deep {T}hings},
  author={Doe, Jane and Roe, Richard}, year={2024}, doi={10.1000/deep},
  journal={Journal of Things}}"""
_PDF = b'%PDF-1.7 fake'


def _fake_sources(request: httpx.Request) -> httpx.Response:
    if request.url.host == 'doi.org':
        return httpx.Response(200, text=_DOI_BIBTEX)
    if request.url.host == 'api.semanticscholar.org':
        return httpx.Response(200, json={
            'openAccessPdf': {'url': 'https://example.org/deep.pdf'}})
    if request.url.path == '/deep.pdf':
        return httpx.Response(200, content=_PDF)
    return httpx.Response(404)


def _session(tmp_path, calls):
    """Runs `calls(client)` against a server on a fresh library."""
    library = library_lib.Library(tmp_path)
    library.create_project('Thesis')
    sources = httpx.Client(transport=httpx.MockTransport(_fake_sources))
    server = mcp_server.create_server(library, sources)

    async def run():
        async with mcp.Client(server, client_info=types.Implementation(
                name='claude-code', version='1')) as client:
            return await calls(client)
    return library, asyncio.run(run())


async def _call(client, tool, **arguments):
    """Returns whether the call failed, and its result or error message."""
    result = await client.call_tool(tool, arguments)
    content = result.structured_content
    if content is None:
        return result.is_error, result.content[0].text
    # Results that are not objects are wrapped as {'result': ...}.
    return result.is_error, content.get('result', content)


def test_references_are_filed_with_verified_metadata_and_provenance(tmp_path):
    async def calls(client):
        added = await _call(client, 'add_references', project='Thesis',
                            references='https://doi.org/10.1000/deep',
                            note='Baseline for chapter 3.')
        again = await _call(client, 'add_references', project='Thesis',
                            references='10.1000/deep')
        return added, again, await _call(client, 'list_papers',
                                         project='Thesis')
    library, (added, again, listed) = _session(tmp_path, calls)
    assert added == (False, [{
        'citekey': 'doe2024deep', 'title': 'Deep Things',
        'authors': ['Doe, Jane', 'Roe, Richard'], 'year': '2024',
        'venue': 'Journal of Things', 'link': 'https://doi.org/10.1000/deep',
        'doi': '10.1000/deep',
        'pdf_available': True, 'already_in_folder': False}])
    assert again[1][0]['already_in_folder']
    [paper] = listed[1]['SoA']
    assert paper['added_by'] == 'claude-code'
    assert paper['notes'] == '[claude-code] Baseline for chapter 3.'


def test_notes_and_annotations_can_be_read_back(tmp_path):
    async def calls(client):
        await _call(client, 'create_folder', project='Thesis',
                    folder='Method')
        await _call(client, 'add_references', project='Thesis',
                    folder='Method', references='10.1000/deep')
        await _call(client, 'add_note', project='Thesis',
                    citekey='doe2024deep', text='Uses LCP contacts.')
        return await _call(client, 'read_paper', project='Thesis',
                           citekey='doe2024deep')
    library, (is_error, paper) = _session(tmp_path, calls)
    assert not is_error
    assert paper['bibtex'].startswith('@article{doe2024deep,')
    assert paper['pdf_path'].endswith('.pdf')
    assert paper['folders'] == {'Method': {
        'notes': '[claude-code] Uses LCP contacts.', 'added_by': 'claude-code',
        'highlights': [], 'sticky_notes': []}}


def test_mistakes_get_helpful_errors(tmp_path):
    async def calls(client):
        return [
            await _call(client, 'add_references', project='Thesys',
                        references='10.1000/deep'),
            await _call(client, 'add_references', project='Thesis',
                        folder='Methods', references='10.1000/deep'),
            await _call(client, 'add_references', project='Thesis',
                        references='no idea'),
            await _call(client, 'create_project', name='Thesis'),
        ]
    _, results = _session(tmp_path, calls)
    assert all(is_error for is_error, _ in results)
    messages = [message for _, message in results]
    assert 'Projects: Thesis' in messages[0]
    assert 'Folders: SoA' in messages[1]
    assert 'No paper could be identified' in messages[2]
    assert 'already named' in messages[3]

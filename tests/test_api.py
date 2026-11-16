"""Tests for annotheca.api, with the scholarly sources faked."""

from urllib import parse

import httpx
import pytest
from fastapi import testclient

from annotheca import api
from annotheca import library

_DOI_BIBTEX = """@article{Doe_2024, title={Deep Things},
  author={Doe, Jane}, year={2024}, doi={10.1000/deep}, journal={J}}"""
_PDF = b'%PDF-1.7 fake'


def _fake_sources(request: httpx.Request) -> httpx.Response:
    if request.url.host == 'doi.org':
        return httpx.Response(200, text=_DOI_BIBTEX)
    if request.url.host == 'api.crossref.org':
        return httpx.Response(200, json={'message': {'items': [
            {'DOI': '10.1000/deep', 'title': ['Deep Things']}]}})
    if request.url.host == 'api.semanticscholar.org':
        return httpx.Response(200, json={
            'openAccessPdf': {'url': 'https://example.org/deep.pdf'}})
    if request.url.path == '/deep.pdf':
        return httpx.Response(200, content=_PDF)
    return httpx.Response(404)


@pytest.fixture
def client(tmp_path):
    sources = httpx.Client(transport=httpx.MockTransport(_fake_sources))
    app = api.create_app(library.Library(tmp_path), sources)
    return testclient.TestClient(app)


@pytest.fixture
def folder_id(client):
    project = client.post('/api/projects', json={'name': 'Thesis'}).json()
    return client.get(f'/api/projects/{project["id"]}').json()['folders'][0][
        'id']


def test_formatted_citation_is_resolved_then_deduplicated(client, folder_id):
    citation = 'Doe, J. (2024). Deep things. J.'
    first = client.post(f'/api/folders/{folder_id}/papers',
                        json={'text': citation}).json()
    again = client.post(f'/api/folders/{folder_id}/papers',
                        json={'text': 'https://doi.org/10.1000/deep'}).json()
    assert first['added'] == 1
    assert again == {**first, 'added': 0, 'already_there': 1}


def test_pdf_is_fetched_and_served(client, folder_id):
    response = client.post(f'/api/folders/{folder_id}/papers',
                           json={'text': '10.1000/deep'})
    paper_id = response.json()['paper_ids'][0]
    assert client.post(f'/api/papers/{paper_id}/pdf/fetch').json() == {
        'found': True}
    assert client.get(f'/api/papers/{paper_id}/pdf').content == _PDF


def test_errors_carry_codes(client, folder_id):
    response = client.post('/api/projects', json={'name': 'Thesis'})
    assert (response.status_code, response.json()) == (
        409, {'detail': 'name_taken'})
    response = client.post(f'/api/folders/{folder_id}/papers',
                           json={'text': ' '})
    assert response.json() == {'detail': 'unresolvable'}
    assert client.delete('/api/folders/999').status_code == 404


def test_export_downloads_bibtex(client, folder_id):
    client.post(f'/api/folders/{folder_id}/papers',
                json={'text': '10.1000/deep'})
    project_id = client.get('/api/projects').json()[0]['id']
    response = client.get(f'/api/projects/{project_id}/bibtex')
    assert response.text.startswith('@article{doe2024deep,')
    assert 'Thesis.bib' in response.headers['content-disposition']


def test_annotations_can_be_edited(client, folder_id):
    client.post(f'/api/folders/{folder_id}/papers',
                json={'text': '10.1000/deep'})
    project_id = client.get('/api/projects').json()[0]['id']
    folders = client.get(f'/api/projects/{project_id}').json()['folders']
    placement_id = folders[0]['placements'][0]['id']
    annotations = f'/api/placements/{placement_id}/annotations'
    note = client.post(annotations, json={
        'kind': 'note', 'page': 1, 'color': '#ffd54f', 'geometry': [0, 0]})
    response = client.patch(f'/api/annotations/{note.json()["id"]}',
                            json={'geometry': [0.5, 0.5], 'body': 'Moved'})
    assert response.json() == {
        **note.json(), 'geometry': [0.5, 0.5], 'body': 'Moved'}


def test_projects_are_shared_as_bundles(client, folder_id):
    client.post(f'/api/folders/{folder_id}/papers',
                json={'text': '10.1000/deep'})
    response = client.get('/api/projects/1/bundle')
    assert "Thesis.annotheca" in response.headers['content-disposition']
    imported = client.post('/api/projects/import', content=response.content)
    assert imported.json() == {'id': 2, 'name': 'Thesis (2)'}
    response = client.post('/api/projects/import', content=b'junk')
    assert response.json() == {'detail': 'not_bundle'}


def test_journal_and_todos_over_http(client, folder_id):
    del folder_id  # The project exists.
    entry = client.post('/api/projects/1/journal',
                        json={'body': '# Progress'}).json()
    image = client.post(f'/api/journal/{entry["id"]}/images',
                        content=b'\x89PNG fake').json()
    assert client.get(f'/api/journal-images/{image["id"]}').content == (
        b'\x89PNG fake')
    file = client.post(f'/api/journal/{entry["id"]}/files',
                       params={'name': 'données.csv'},
                       content=b'a,b\n').json()
    response = client.get(f'/api/journal-files/{file["id"]}')
    assert response.content == b'a,b\n'
    assert "données.csv" in parse.unquote(
        response.headers['content-disposition'])
    response = client.post(f'/api/journal/{entry["id"]}/images',
                           content=b'not an image')
    assert response.json() == {'detail': 'not_image'}
    todo = client.post('/api/projects/1/todos', json={'text': ' Plot '}).json()
    assert todo['text'] == 'Plot'
    assert client.patch(f'/api/todos/{todo["id"]}',
                        json={'done': True}).json()['done_at']
    assert client.post('/api/projects/1/todos',
                       json={'text': '  '}).status_code == 422


def test_paper_orchestra_materials_download_as_a_zip(client, folder_id):
    del folder_id  # The project exists.
    response = client.get('/api/projects/1/paper-orchestra')
    assert response.headers['content-type'] == 'application/zip'
    assert 'PaperOrchestra.zip' in response.headers['content-disposition']


def test_deleted_projects_and_papers_go_to_the_trash(client, folder_id):
    client.post(f'/api/folders/{folder_id}/papers',
                json={'text': '10.1000/deep'})
    placement = client.get('/api/projects/1').json()['folders'][0][
        'placements'][0]
    client.delete(f'/api/placements/{placement["id"]}')
    assert client.get('/api/projects/1').json()['folders'][0][
        'placements'] == []
    [trashed] = client.get('/api/trash').json()['papers']
    assert (trashed['title'], trashed['project']) == ('Deep Things', 'Thesis')
    client.post(f'/api/trash/placement/{placement["id"]}/restore')
    assert client.get('/api/projects/1').json()['folders'][0]['placements']

    client.delete('/api/projects/1')
    assert client.get('/api/projects').json() == []
    assert client.get('/api/projects/1').status_code == 404
    assert client.post('/api/projects', json={'name': 'Thesis'}).json() == {
        'detail': 'name_in_trash'}
    client.delete('/api/trash/project/1')
    assert client.get('/api/trash').json() == {'projects': [], 'papers': []}
    assert client.post('/api/projects',
                       json={'name': 'Thesis'}).status_code == 201

"""Tests for annotheca.bundle."""

import io
import json
import zipfile

import pytest

from annotheca import bibtex
from annotheca import bundle
from annotheca import library as library_lib

_PDF = b'%PDF-1.4 shared'
_PNG_IMAGE = b'\x89PNG shared'
_HIGHLIGHT = {'kind': 'highlight', 'page': 2, 'color': '#90caf9',
              'geometry': [[0.1, 0.2, 0.3, 0.02]], 'quote': 'Key result'}


def _entry(citekey, title):
    return bibtex.Entry('article', citekey, {'title': title, 'year': '2024'})


@pytest.fixture
def shared(tmp_path):
    """A project with a paper filed in two folders, annotated differently."""
    library = library_lib.Library(tmp_path / 'alice')
    project_id = library.create_project('Thesis')['id']
    soa_id = library.get_project(project_id)['folders'][0]['id']
    method_id = library.create_folder(project_id, 'Method')['id']
    paper_id = library.add_paper(_entry('doe2024', 'One'))
    library.save_pdf(paper_id, _PDF)
    library.add_paper(_entry('roe2023', 'Two'))
    soa = library.file_paper(soa_id, paper_id)
    library.file_paper(method_id, paper_id)
    library.add_reading_note(soa, 'Read first.')
    library.create_annotation(soa, _HIGHLIGHT)
    library.rename('folder', soa_id, 'Background')
    entry = library.add_journal_entry(project_id, 'Kick-off', 'claude-code')
    library.add_journal_image(entry['id'], _PNG_IMAGE)
    library.add_journal_file(entry['id'], 'train.py', io.BytesIO(b'print(1)'))
    library.add_journal_entry(project_id, 'Second step')
    library.add_todo(project_id, 'Write intro')
    return bundle.export_project(library, project_id)


def _placements(library, project_id):
    return {folder['name']: [
        (p['citekey'], p['note_count'], p['has_pdf'],
         library.list_annotations(p['id']))
        for p in folder['placements']]
        for folder in library.get_project(project_id)['folders']}


def test_round_trip_keeps_folders_notes_annotations_and_pdfs(tmp_path, shared):
    name, data = shared
    assert name == 'Thesis'
    library = library_lib.Library(tmp_path / 'bob')
    project = bundle.import_project(library, data)
    [highlight] = library.list_annotations(1)
    assert _placements(library, project['id']) == {
        'Background': [('doe2024', 1, True, [highlight])],
        'Method': [('doe2024', 0, True, [])],
    }
    assert {k: highlight[k] for k in _HIGHLIGHT} == _HIGHLIGHT
    assert library.export_bibtex(project['id'])[1].count('@article') == 1


def test_import_keeps_existing_projects_and_papers(tmp_path, shared):
    library = library_lib.Library(tmp_path / 'bob')
    library.create_project('Thesis')
    own_paper = library.add_paper(_entry('mine', 'One'))
    project = bundle.import_project(library, shared[1])
    assert project['name'] == 'Thesis (2)'
    folder = library.get_project(project['id'])['folders'][0]
    assert folder['placements'][0]['paper_id'] == own_paper


@pytest.mark.parametrize('manifest', [
    None,
    {'format': 'other'},
    {'format': 'annotheca', 'version': 1, 'name': 'X', 'papers': [],
     'folders': [{'name': 'SoA', 'placements': [{'citekey': 'missing'}]}]},
])
def test_invalid_bundles_are_rejected_untouched(tmp_path, manifest):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        if manifest is not None:
            archive.writestr('project.json', json.dumps(manifest))
    library = library_lib.Library(tmp_path)
    for data in (buffer.getvalue(), b'not a zip'):
        with pytest.raises(bundle.InvalidBundleError):
            bundle.import_project(library, data)
    assert library.list_projects() == []


def test_notes_of_older_bundles_become_reading_notes(tmp_path):
    manifest = {
        'format': 'annotheca', 'version': 1, 'name': 'Old',
        'papers': [{'citekey': 'doe2024', 'entry_type': 'article',
                    'fields': {'title': 'One'}}],
        'folders': [{'name': 'SoA', 'placements': [
            {'citekey': 'doe2024', 'notes': 'Read first.'}]}]}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('project.json', json.dumps(manifest))
    library = library_lib.Library(tmp_path)
    project_id = bundle.import_project(library, buffer.getvalue())['id']
    [note] = library.list_journal(project_id)
    assert (note['body'], note['category']) == ('Read first.', 'reading')


def test_round_trip_keeps_the_journal_and_todos(tmp_path, shared):
    library = library_lib.Library(tmp_path / 'bob')
    project_id = bundle.import_project(library, shared[1])['id']
    second, first, note = library.list_journal(project_id)
    assert (first['body'], first['author'], second['body']) == (
        'Kick-off', 'claude-code', 'Second step')
    assert (note['body'], note['paper']['citekey']) == (
        'Read first.', 'doe2024')
    folders = library.get_project(project_id)['folders']
    assert note['paper']['folder_id'] == folders[0]['id']
    assert first['created_at'] <= second['created_at']
    image_path = library.image_path(first['images'][0]['id'])
    assert image_path.read_bytes() == _PNG_IMAGE
    [file] = first['files']
    path, name = library.journal_file(file['id'])
    assert (path.read_bytes(), name) == (b'print(1)', 'train.py')
    assert [t['text'] for t in library.list_todos(project_id)] == [
        'Write intro']

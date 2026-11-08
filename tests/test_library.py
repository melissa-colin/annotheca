"""Tests for annotheca.library."""

import pytest

from annotheca import bibtex
from annotheca import library as library_lib

_PDF = b'%PDF-1.4 minimal'


def _entry(citekey, title, doi=None):
    fields = {'title': title, 'author': 'Doe, Jane', 'year': '2024'}
    if doi:
        fields['doi'] = doi
    return bibtex.Entry('article', citekey, fields)


@pytest.fixture
def library(tmp_path):
    return library_lib.Library(tmp_path)


@pytest.fixture
def project(library):
    project = library.create_project('Thesis')
    folder_id = library.create_folder(project['id'], 'Method')['id']
    soa_id = library.get_project(project['id'])['folders'][0]['id']
    return project['id'], soa_id, folder_id


def test_new_project_has_default_folder(library):
    project = library.create_project('Thesis')
    folders = library.get_project(project['id'])['folders']
    assert [f['name'] for f in folders] == [library_lib.DEFAULT_FOLDER]


def test_duplicate_names_conflict(library, project):
    project_id, _, _ = project
    with pytest.raises(library_lib.ConflictError):
        library.create_project('Thesis')
    with pytest.raises(library_lib.ConflictError):
        library.create_folder(project_id, 'Method')


def test_same_paper_is_stored_once(library):
    first = library.add_paper(_entry('a', 'Title', doi='10.1000/x'))
    by_doi = library.add_paper(_entry('b', 'Other title', doi='10.1000/X'))
    by_title = library.add_paper(_entry('c', 'TITLE!'))
    assert first == by_doi == by_title


def test_citekeys_stay_unique(library):
    first = library.add_paper(_entry('doe2024', 'One'))
    second = library.add_paper(_entry('doe2024', 'Two'))
    assert library.get_paper(first).citekey == 'doe2024'
    assert library.get_paper(second).citekey == 'doe2024a'


def test_export_lists_each_paper_once(library, project):
    project_id, soa_id, method_id = project
    paper_id = library.add_paper(_entry('doe2024', 'One'))
    assert library.file_papers(soa_id, [paper_id]) == 1
    assert library.file_papers(method_id, [paper_id]) == 1
    assert library.file_papers(method_id, [paper_id]) == 0
    name, content = library.export_bibtex(project_id)
    assert name == 'Thesis'
    assert content.count('@article{doe2024,') == 1


def test_annotations_belong_to_one_placement(library, project):
    project_id, soa_id, method_id = project
    paper_id = library.add_paper(_entry('doe2024', 'One'))
    library.file_papers(soa_id, [paper_id])
    library.file_papers(method_id, [paper_id])
    soa, method = (f['placements'][0]
                   for f in library.get_project(project_id)['folders'])
    note = library.create_annotation(soa['id'], {
        'kind': 'note', 'page': 1, 'color': '#ffd54f',
        'geometry': [0.1, 0.2], 'body': 'hi'})
    assert library.list_annotations(soa['id']) == [note]
    assert library.list_annotations(method['id']) == []

    changed = library.update_annotation(note['id'], {'body': 'edited'})
    assert changed['body'] == 'edited'
    assert changed['geometry'] == [0.1, 0.2]


def test_paper_is_forgotten_when_filed_nowhere(library, project):
    project_id, soa_id, _ = project
    paper_id = library.add_paper(_entry('doe2024', 'One'))
    library.file_papers(soa_id, [paper_id])
    library.save_pdf(paper_id, _PDF)
    placement = library.get_project(project_id)['folders'][0]['placements'][0]
    assert placement['has_pdf']

    library.remove_placement(placement['id'])
    assert not library.pdf_path(paper_id).exists()
    with pytest.raises(library_lib.NotFoundError):
        library.get_paper(paper_id)


def test_rejects_non_pdf(library):
    paper_id = library.add_paper(_entry('doe2024', 'One'))
    with pytest.raises(library_lib.InvalidPdfError):
        library.save_pdf(paper_id, b'<html>')

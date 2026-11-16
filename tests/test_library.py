"""Tests for annotheca.library."""

import io
import sqlite3

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


def test_reading_notes_belong_to_one_placement(library, project):
    project_id, soa_id, method_id = project
    paper_id = library.add_paper(_entry('doe2024', 'One'))
    soa = library.file_paper(soa_id, paper_id)
    assert library.file_paper(soa_id, paper_id) == soa
    library.file_paper(method_id, paper_id)
    library.add_reading_note(soa, 'Related to chapter 2.')
    library.add_reading_note(soa, 'Also chapter 3.', author='claude-code')
    counts = [f['placements'][0]['note_count']
              for f in library.get_project(project_id)['folders']]
    assert counts == [2, 0]
    notes = library.list_journal(project_id, soa)
    assert [n['body'] for n in notes] == [
        'Also chapter 3.', 'Related to chapter 2.']
    assert notes[0]['category'] == 'reading'
    assert notes[0]['paper'] == {
        'placement_id': soa, 'folder_id': soa_id, 'citekey': 'doe2024',
        'title': 'One', 'trashed': False}
    with pytest.raises(library_lib.NotFoundError):
        library.add_journal_entry(
            library.create_project('Other')['id'], 'x', placement_id=soa)


def test_comments_on_annotations_go_to_the_journal(library, project):
    project_id, soa_id, _ = project
    soa = library.file_paper(
        soa_id, library.add_paper(_entry('doe2024', 'One')))
    highlight = library.create_annotation(soa, {
        'kind': 'highlight', 'page': 3, 'color': '#fff59d',
        'geometry': [], 'quote': 'Key result'})
    note = library.create_annotation(soa, {
        'kind': 'note', 'page': 5, 'color': '#fff59d', 'geometry': [0, 0],
        'body': 'Check this proof.'})
    assert len(library.list_journal(project_id)) == 1
    library.update_annotation(highlight['id'], {'body': 'Holds for LCP.'})
    library.update_annotation(highlight['id'], {'body': 'Holds for LCPs.'})
    library.update_annotation(note['id'], {'body': 'Checked.'})
    assert [e['body'] for e in library.list_journal(project_id)] == [
        '> Key result\n\nHolds for LCP.\n\n*p. 3*',
        'Check this proof.\n\n*p. 5*']


def test_libraries_from_older_versions_are_migrated(tmp_path):
    with sqlite3.connect(tmp_path / 'library.db') as db:
        for number, sql in enumerate(library_lib._MIGRATIONS[:7], 1):
            db.executescript(sql)
            db.execute(f'PRAGMA user_version = {number}')
        db.executescript("""
            INSERT INTO projects (name) VALUES ('Old');
            INSERT INTO folders (project_id, name) VALUES (1, 'SoA');
            INSERT INTO papers (citekey, entry_type, fields)
                VALUES ('doe2024', 'article', '{"title": "One"}');
            INSERT INTO placements (folder_id, paper_id, notes)
                VALUES (1, 1, 'Kept.' || char(10, 10) || 'Same note.'
                        || char(10, 10) || '[claude-code] Signed.');
            INSERT INTO todos (project_id, text, created_at)
                VALUES (1, 'Plot', '2026-01-01');
        """)
    library = library_lib.Library(tmp_path)
    notes = library.list_journal(1, placement_id=1)
    assert [(n['author'], n['body'], n['category']) for n in notes] == [
        ('claude-code', 'Signed.', 'reading'),
        ('', 'Kept.\n\nSame note.', 'reading')]
    [todo] = library.list_todos(1)
    assert (todo['due_date'], todo['priority']) == (None, '')


_PNG = b'\x89PNG\r\n\x1a\n fake image'


def test_journal_entries_are_dated_signed_and_newest_first(library):
    project_id = library.create_project('Thesis')['id']
    first = library.add_journal_entry(project_id, 'Read the SoA.')
    second = library.add_journal_entry(
        project_id, 'Tried a baseline.', author='claude-code',
        created_at='2099-01-01T00:00:00+00:00')
    assert [e['id'] for e in library.list_journal(project_id)] == [
        second['id'], first['id']]
    assert first['created_at'] and first['author'] == ''
    assert first['category'] == ''
    edited = library.update_journal_entry(
        first['id'], 'Read the SoA again.', 'reading')
    assert edited['updated_at'] and edited['created_at'] == first['created_at']
    assert edited['category'] == 'reading'
    assert library.list_projects()[0]['last_entry'] == second['created_at']


def test_projects_add_their_own_journal_categories(library):
    project_id = library.create_project('Thesis')['id']
    with pytest.raises(library_lib.UnknownCategoryError):
        library.add_journal_entry(project_id, 'Met Yilin', category='meeting')
    assert library.add_category(project_id, 'meeting') == ['meeting']
    with pytest.raises(library_lib.ConflictError):
        library.add_category(project_id, 'meeting')
    with pytest.raises(library_lib.ConflictError):
        library.add_category(project_id, 'Idea')
    entry = library.add_journal_entry(
        project_id, 'Met Yilin', category='meeting')
    assert library.get_project(project_id)['categories'] == ['meeting']
    other = library.create_project('Other')['id']
    with pytest.raises(library_lib.UnknownCategoryError):
        library.update_journal_entry(
            library.add_journal_entry(other, 'x')['id'], 'x', 'meeting')
    library.delete_category(project_id, 'meeting')
    assert library.list_journal(project_id)[0]['category'] == ''
    assert library.list_journal(project_id)[0]['id'] == entry['id']


def test_journal_images_are_checked_stored_and_removed(library, tmp_path):
    project_id = library.create_project('Thesis')['id']
    entry = library.add_journal_entry(project_id, 'Figure')
    with pytest.raises(library_lib.InvalidImageError):
        library.add_journal_image(entry['id'], b'<svg/>')
    image = library.add_journal_image(entry['id'], _PNG)
    path = library.image_path(image['id'])
    assert path.read_bytes() == _PNG
    assert library.list_journal(project_id)[0]['images'] == [image]
    library.delete('project', project_id)
    assert not path.exists()


def test_journal_files_keep_their_name_and_content(library):
    project_id = library.create_project('Thesis')['id']
    entry = library.add_journal_entry(project_id, 'Dataset v2')
    file = library.add_journal_file(
        entry['id'], 'C:\\data\\train.csv', io.BytesIO(b'x,y\n1,2\n'))
    assert file == {'id': file['id'], 'name': 'train.csv', 'size': 8}
    path, name = library.journal_file(file['id'])
    assert (path.read_bytes(), name) == (b'x,y\n1,2\n', 'train.csv')
    assert library.list_journal(project_id)[0]['files'] == [file]
    library.delete_journal_entry(entry['id'])
    assert not path.exists()


def test_trash_keeps_items_until_restored_or_emptied(library):
    project_id = library.create_project('Thesis')['id']
    soa_id = library.get_project(project_id)['folders'][0]['id']
    paper_id = library.add_paper(bibtex.Entry(
        'article', 'doe2024', {'title': 'Deep', 'year': '2024'}))
    placement_id = library.file_paper(soa_id, paper_id)
    library.add_reading_note(placement_id, 'Key.')
    library.trash('placement', placement_id)
    assert library.get_project(project_id)['folders'][0]['placements'] == []
    assert library.export_bibtex(project_id)[1] == ''
    assert library.list_projects()[0]['paper_count'] == 0
    assert library.file_paper(soa_id, paper_id) == placement_id
    assert library.get_project(project_id)['folders'][0]['placements'][0][
        'note_count'] == 1

    library.trash('project', project_id)
    assert library.list_projects() == []
    with pytest.raises(library_lib.NotFoundError):
        library.get_project(project_id)
    with pytest.raises(library_lib.NameInTrashError):
        library.create_project('Thesis')
    assert [p['name'] for p in library.list_trash()['projects']] == ['Thesis']
    library.restore('project', project_id)
    assert library.get_project(project_id)['name'] == 'Thesis'

    library.trash('placement', placement_id)
    library.empty_trash()
    assert library.list_trash() == {'projects': [], 'papers': []}
    with pytest.raises(library_lib.NotFoundError):
        library.get_paper(paper_id)


def test_trash_is_emptied_after_its_delay(tmp_path):
    library = library_lib.Library(tmp_path)
    project_id = library.create_project('Old')['id']
    library.trash('project', project_id)
    with sqlite3.connect(tmp_path / 'library.db') as db:
        db.execute('UPDATE projects SET deleted_at = ?',
                   ('2000-01-01T00:00:00+00:00',))
    library_lib.Library(tmp_path)
    assert library.list_trash()['projects'] == []


def test_todos_open_first_and_dated_when_done(library):
    project_id = library.create_project('Thesis')['id']
    first = library.add_todo(project_id, 'Write intro')
    second = library.add_todo(project_id, 'Run baseline', author='claude-code')
    done = library.update_todo(first['id'], done=True)
    assert done['done_at']
    assert [t['id'] for t in library.list_todos(project_id)] == [
        second['id'], first['id']]
    assert library.get_project(project_id)['open_todos'] == 1
    assert library.update_todo(first['id'], done=False)['done_at'] is None
    library.delete_todo(second['id'])
    assert [t['text'] for t in library.list_todos(project_id)] == [
        'Write intro']

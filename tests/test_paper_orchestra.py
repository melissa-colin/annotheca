"""Tests for annotheca.paper_orchestra."""

import io
import json
import zipfile

from annotheca import bibtex
from annotheca import library as library_lib
from annotheca import paper_orchestra


def test_export_gives_paper_orchestra_its_raw_materials(tmp_path):
    library = library_lib.Library(tmp_path)
    project_id = library.create_project('Thesis')['id']
    soa_id = library.get_project(project_id)['folders'][0]['id']
    library.create_folder(project_id, 'Empty')
    paper_id = library.add_paper(bibtex.Entry('article', 'doe2024', {
        'title': 'Contact', 'author': 'Doe, Jane and Roe, Rick',
        'year': '2024'}))
    library.set_notes(library.file_paper(soa_id, paper_id), 'Key baseline.')
    first = library.add_journal_entry(
        project_id, '## Ran the **ablation**', 'claude-code')
    library.add_journal_image(first['id'], b'\x89PNG plot')
    library.add_journal_image(first['id'], b'GIF89a animation')
    library.add_journal_entry(project_id, 'Wrote the method')

    name, data = paper_orchestra.export_project(library, project_id)

    assert name == 'Thesis'
    archive = zipfile.ZipFile(io.BytesIO(data))
    read = lambda path: archive.read(f'raw_materials/{path}').decode()
    idea = read('idea_sparse.md')
    assert '## Problem Statement' in idea
    assert ('### SoA\n\n- **Contact** (Doe, Jane; Roe, Rick, 2024) [doe2024]\n'
            '  Key baseline.') in idea
    assert '### Empty' not in idea
    log = read('experimental_log.md')
    assert log.index('Ran the') < log.index('Wrote the method')
    assert '(claude-code)' in log
    image_name = f'journal_{first["id"]}.png'
    assert f'Figure: `figures/{image_name}`' in log
    assert json.loads(read('figures/info.json')) == [{
        'name': image_name,
        'caption': f'From the journal entry of {first["created_at"][:10]}:'
                   ' Ran the ablation'}]
    assert archive.read(
        f'raw_materials/figures/{image_name}') == b'\x89PNG plot'
    assert not [n for n in archive.namelist() if n.endswith('.gif')]
    assert '@article{doe2024' in read('references.bib')
    assert 'github.com/google-research/paper-orchestra' in read('README.md')

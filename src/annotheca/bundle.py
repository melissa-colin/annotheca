"""Project bundles: a whole project in one file, to share it.

A bundle is a zip archive holding `project.json`, which describes the
folders, papers, notes, annotations, journal and to-dos, the PDFs as
`pdfs/<citekey>.pdf`, the journal images as `images/<name>` and the files
attached to the journal as `files/<id>/<name>`. Bundles from before the
journal existed remain valid.
"""

import io
import itertools
import json
import posixpath
import zipfile
from typing import Any, Literal

import pydantic

from annotheca import bibtex
from annotheca import library as library_lib
from annotheca import models

_MANIFEST = 'project.json'


class InvalidBundleError(ValueError):
    """The file is not an Annotheca project bundle."""


class _Paper(pydantic.BaseModel):
    citekey: str
    entry_type: str
    fields: dict[str, str]


class _Placement(pydantic.BaseModel):
    citekey: str
    # Reading notes, in bundles made before the journal kept them.
    notes: str = ''
    added_by: str = ''
    annotations: list[models.Annotation] = []


class _Folder(pydantic.BaseModel):
    name: models.Name
    placements: list[_Placement]


class _PaperLink(pydantic.BaseModel):
    """The paper, as filed in a folder, that a journal entry is about."""
    folder: str
    citekey: str


class _JournalEntry(pydantic.BaseModel):
    body: str
    category: models.JournalCategory = ''
    author: str = ''
    created_at: str
    images: list[str] = []
    files: list[str] = []
    paper: _PaperLink | None = None


class _Todo(pydantic.BaseModel):
    text: models.TodoText
    author: str = ''
    created_at: str
    done_at: str | None = None
    due_date: str | None = None
    priority: models.Priority = ''


class _Manifest(pydantic.BaseModel):
    format: Literal['annotheca']
    version: Literal[1]
    name: models.Name
    papers: list[_Paper]
    folders: list[_Folder] = pydantic.Field(min_length=1)
    categories: list[models.JournalCategory] = []
    journal: list[_JournalEntry] = []
    todos: list[_Todo] = []

    @pydantic.model_validator(mode='after')
    def _check_references(self) -> '_Manifest':
        """Rejects bundles that could only be imported halfway."""
        citekeys = {paper.citekey for paper in self.papers}
        names = [folder.name for folder in self.folders]
        filed = {(folder.name, placement.citekey) for folder in self.folders
                 for placement in folder.placements}
        categories = {'', *library_lib.BUILTIN_CATEGORIES, *self.categories}
        if len(set(names)) < len(names) or any(
                citekey not in citekeys for _, citekey in filed) or any(
                    (entry.paper.folder, entry.paper.citekey) not in filed
                    for entry in self.journal if entry.paper) or any(
                        entry.category not in categories
                        for entry in self.journal):
            raise ValueError('Inconsistent bundle.')
        return self


def export_project(library: library_lib.Library,
                   project_id: int) -> tuple[str, bytes]:
    """Returns the name of a project and its bundle."""
    project = library.get_project(project_id)
    papers = {}
    folders = []
    for folder in project['folders']:
        placements = []
        for placement in folder['placements']:
            paper_id = placement['paper_id']
            if paper_id not in papers:
                entry = library.get_paper(paper_id)
                papers[paper_id] = _Paper(
                    citekey=entry.citekey, entry_type=entry.entry_type,
                    fields=entry.fields)
            placements.append(_Placement(
                citekey=papers[paper_id].citekey,
                added_by=placement['added_by'],
                annotations=library.list_annotations(placement['id'])))
        folders.append(_Folder(name=folder['name'], placements=placements))
    folder_names = {folder['id']: folder['name']
                    for folder in project['folders']}
    attachments = {}
    journal = []
    for entry in library.list_journal(project_id):
        images = []
        for image in entry['images']:
            name = f'images/{image["id"]}{image["extension"]}'
            attachments[name] = library.image_path(image['id'])
            images.append(name)
        files = []
        for file in entry['files']:
            name = f'files/{file["id"]}/{file["name"]}'
            attachments[name] = library.journal_file(file['id'])[0]
            files.append(name)
        paper = entry['paper'] and _PaperLink(
            folder=folder_names[entry['paper']['folder_id']],
            citekey=entry['paper']['citekey'])
        journal.append(_JournalEntry(**entry | {
            'images': images, 'files': files, 'paper': paper}))
    manifest = _Manifest(
        format='annotheca', version=1, name=project['name'],
        papers=list(papers.values()), folders=folders,
        categories=project['categories'], journal=journal,
        todos=library.list_todos(project_id))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr(_MANIFEST, manifest.model_dump_json(indent=1),
                         compress_type=zipfile.ZIP_DEFLATED)
        for paper_id, paper in papers.items():
            if (path := library.pdf_path(paper_id)).exists():
                archive.write(path, _pdf_name(paper.citekey))
        for name, path in attachments.items():
            archive.write(path, name, compress_type=zipfile.ZIP_DEFLATED)
    return project['name'], buffer.getvalue()


def import_project(library: library_lib.Library,
                   data: bytes) -> dict[str, Any]:
    """Creates a project from a bundle and returns its id and name.

    Papers already in the library are reused, keeping their PDF. The project
    name gets a number appended if it is already taken.

    Raises:
        InvalidBundleError: `data` is not a valid bundle.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        manifest = _Manifest.model_validate(
            json.loads(archive.read(_MANIFEST)))
        images = {name: archive.read(name) for entry in manifest.journal
                  for name in entry.images}
        for name in (name for entry in manifest.journal
                     for name in entry.files):
            archive.getinfo(name)
    except (zipfile.BadZipFile, KeyError, ValueError) as error:
        raise InvalidBundleError from error
    if not all(map(library_lib.image_extension, images.values())):
        raise InvalidBundleError

    paper_ids = {}
    for paper in manifest.papers:
        paper_id = library.add_paper(
            bibtex.Entry(paper.entry_type, paper.citekey, paper.fields))
        paper_ids[paper.citekey] = paper_id
        pdf_name = _pdf_name(paper.citekey)
        if (pdf_name in archive.namelist()
                and not library.pdf_path(paper_id).exists()):
            library.save_pdf(paper_id, archive.read(pdf_name))

    project = _create_project(library, manifest.name)
    default_folder = library.get_project(project['id'])['folders'][0]
    placement_ids = {}
    for index, folder in enumerate(manifest.folders):
        if index == 0:
            folder_id = default_folder['id']
            library.rename('folder', folder_id, folder.name)
        else:
            folder_id = library.create_folder(project['id'], folder.name)['id']
        for placement in folder.placements:
            placement_id = library.file_paper(
                folder_id, paper_ids[placement.citekey], placement.added_by)
            placement_ids[folder.name, placement.citekey] = placement_id
            if placement.notes:
                library.add_reading_note(placement_id, placement.notes)
            for annotation in placement.annotations:
                library.create_annotation(
                    placement_id, annotation.model_dump(), log_comment=False)
    for category in manifest.categories:
        library.add_category(project['id'], category)
    for entry in reversed(manifest.journal):
        entry_id = library.add_journal_entry(
            project['id'], entry.body, entry.author, entry.created_at,
            entry.category, entry.paper and placement_ids[
                entry.paper.folder, entry.paper.citekey])['id']
        for name in entry.images:
            library.add_journal_image(entry_id, images[name])
        for name in entry.files:
            with archive.open(name) as source:
                library.add_journal_file(
                    entry_id, posixpath.basename(name), source)
    for todo in manifest.todos:
        library.add_todo(project['id'], todo.text, todo.author,
                         todo.created_at, todo.done_at, todo.due_date,
                         todo.priority)
    return project


def _create_project(library: library_lib.Library,
                    name: str) -> dict[str, Any]:
    """Creates a project named `name`, or `name (2)`, `name (3)`..."""
    for number in itertools.count(1):
        try:
            return library.create_project(
                name if number == 1 else f'{name} ({number})')
        except library_lib.ConflictError:
            continue


def _pdf_name(citekey: str) -> str:
    return f'pdfs/{citekey}.pdf'

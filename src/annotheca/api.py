"""HTTP API and static web interface."""

import datetime
import mimetypes
import pathlib
import tempfile
from typing import Annotated, Any, Literal
from urllib import parse

import fastapi
import httpx
import pydantic
from fastapi import responses
from fastapi import staticfiles

from annotheca import bundle
from annotheca import library as library_lib
from annotheca import models
from annotheca import paper_orchestra
from annotheca import sources

_STATIC_DIR = pathlib.Path(__file__).parent / 'static'
# Uploads larger than this go to a temporary file rather than memory.
_SPOOL_SIZE = 8 * 1024 * 1024

# Exception types mapped to an HTTP status and the error code the
# interface translates for the user.
_ERRORS = {
    library_lib.NotFoundError: (404, 'not_found'),
    library_lib.NameInTrashError: (409, 'name_in_trash'),
    library_lib.ConflictError: (409, 'name_taken'),
    library_lib.InvalidPdfError: (422, 'not_pdf'),
    library_lib.InvalidImageError: (422, 'not_image'),
    library_lib.UnknownCategoryError: (422, 'unknown_category'),
    bundle.InvalidBundleError: (422, 'not_bundle'),
}


TrashedKind = Literal['project', 'placement']


class NameBody(pydantic.BaseModel):
    name: models.Name


class AddPapersBody(pydantic.BaseModel):
    """Either pasted references or an already known paper to file."""
    text: str | None = None
    paper_id: int | None = None


class AnnotationChanges(pydantic.BaseModel):
    color: models.Color | None = None
    geometry: list[Any] | None = None
    body: str | None = None


class JournalBody(pydantic.BaseModel):
    body: str
    category: models.JournalCategory = ''
    placement_id: int | None = None


class CategoryBody(pydantic.BaseModel):
    name: Annotated[models.JournalCategory, pydantic.Field(min_length=1)]


class TodoBody(pydantic.BaseModel):
    text: models.TodoText
    due_date: datetime.date | None = None
    priority: models.Priority = ''


class TodoChanges(pydantic.BaseModel):
    """Only the fields sent are changed; a null due_date removes it."""
    text: models.TodoText = None
    done: bool = None
    due_date: datetime.date | None = None
    priority: models.Priority = None


def create_app(library: library_lib.Library,
               client: httpx.Client | None = None) -> fastapi.FastAPI:
    """Builds the web application.

    Args:
        library: Where everything is stored.
        client: HTTP client for the scholarly sources; a default one is
            created when omitted.
    """
    client = client or sources.make_client()
    app = fastapi.FastAPI(title='Annotheca', docs_url=None, redoc_url=None)
    api = fastapi.APIRouter(prefix='/api')

    for error_type, (status, code) in _ERRORS.items():
        app.add_exception_handler(error_type, _error_handler(status, code))

    @app.exception_handler(sources.ResolveError)
    def _resolve_error(request, error):
        del request  # Unused.
        return responses.JSONResponse({'detail': str(error)}, status_code=422)

    @api.get('/projects')
    def list_projects():
        return library.list_projects()

    @api.post('/projects', status_code=201)
    def create_project(body: NameBody):
        return library.create_project(body.name)

    @api.get('/projects/{project_id}')
    def get_project(project_id: int):
        return library.get_project(project_id)

    @api.get('/projects/{project_id}/bibtex')
    def export_bibtex(project_id: int):
        name, content = library.export_bibtex(project_id)
        return _download(content, f'{name}.bib', 'application/x-bibtex')

    @api.get('/projects/{project_id}/bundle')
    def export_bundle(project_id: int):
        """The project with its notes, annotations and PDFs, to share."""
        name, content = bundle.export_project(library, project_id)
        return _download(content, f'{name}.annotheca', 'application/zip')

    @api.get('/projects/{project_id}/paper-orchestra')
    def export_paper_orchestra(project_id: int):
        """The project as raw materials for PaperOrchestra to draft a paper."""
        name, content = paper_orchestra.export_project(library, project_id)
        return _download(content, f'{name} - PaperOrchestra.zip',
                         'application/zip')

    @api.post('/projects/import', status_code=201)
    async def import_bundle(request: fastapi.Request):
        return bundle.import_project(library, await request.body())

    @api.post('/projects/{project_id}/folders', status_code=201)
    def create_folder(project_id: int, body: NameBody):
        return library.create_folder(project_id, body.name)

    @api.patch('/projects/{project_id}', status_code=204)
    def rename_project(project_id: int, body: NameBody):
        library.rename('project', project_id, body.name)

    @api.delete('/projects/{project_id}', status_code=204)
    def delete_project(project_id: int):
        """Moves the project to the trash."""
        library.trash('project', project_id)

    @api.patch('/folders/{folder_id}', status_code=204)
    def rename_folder(folder_id: int, body: NameBody):
        library.rename('folder', folder_id, body.name)

    @api.delete('/folders/{folder_id}', status_code=204)
    def delete_folder(folder_id: int):
        library.delete('folder', folder_id)

    @api.post('/folders/{folder_id}/papers')
    def add_papers(folder_id: int, body: AddPapersBody):
        """Files pasted references, or a known paper, in a folder."""
        if body.paper_id is not None:
            paper_ids = [body.paper_id]
        elif body.text and body.text.strip():
            entries = sources.resolve(body.text, client)
            paper_ids = list(dict.fromkeys(map(library.add_paper, entries)))
        else:
            raise sources.ResolveError('unresolvable')
        added = library.file_papers(folder_id, paper_ids)
        return {'paper_ids': paper_ids, 'added': added,
                'already_there': len(paper_ids) - added}

    @api.delete('/placements/{placement_id}', status_code=204)
    def remove_placement(placement_id: int):
        """Moves the paper, as filed in this folder, to the trash."""
        library.trash('placement', placement_id)

    @api.get('/trash')
    def list_trash():
        return library.list_trash()

    @api.delete('/trash', status_code=204)
    def empty_trash():
        library.empty_trash()

    @api.post('/trash/{kind}/{item_id}/restore', status_code=204)
    def restore(kind: TrashedKind, item_id: int):
        library.restore(kind, item_id)

    @api.delete('/trash/{kind}/{item_id}', status_code=204)
    def delete_for_good(kind: TrashedKind, item_id: int):
        if kind == 'project':
            library.delete('project', item_id)
        else:
            library.remove_placement(item_id)

    @api.get('/papers/{paper_id}/pdf')
    def get_pdf(paper_id: int):
        path = library.pdf_path(paper_id)
        if not path.exists():
            raise library_lib.NotFoundError
        return responses.FileResponse(path, media_type='application/pdf')

    @api.put('/papers/{paper_id}/pdf', status_code=204)
    async def upload_pdf(paper_id: int, request: fastapi.Request):
        library.save_pdf(paper_id, await request.body())

    @api.post('/papers/{paper_id}/pdf/fetch')
    def fetch_pdf(paper_id: int):
        """Looks for an open-access PDF; reports whether one was found."""
        pdf = sources.find_pdf(library.get_paper(paper_id), client)
        if pdf:
            library.save_pdf(paper_id, pdf)
        return {'found': pdf is not None}

    @api.get('/placements/{placement_id}/annotations')
    def list_annotations(placement_id: int):
        return library.list_annotations(placement_id)

    @api.post('/placements/{placement_id}/annotations', status_code=201)
    def create_annotation(placement_id: int, body: models.Annotation):
        return library.create_annotation(placement_id, body.model_dump())

    @api.patch('/annotations/{annotation_id}')
    def update_annotation(annotation_id: int, body: AnnotationChanges):
        return library.update_annotation(
            annotation_id, body.model_dump(exclude_none=True))

    @api.delete('/annotations/{annotation_id}', status_code=204)
    def delete_annotation(annotation_id: int):
        library.delete_annotation(annotation_id)

    @api.post('/projects/{project_id}/categories', status_code=201)
    def add_category(project_id: int, body: CategoryBody):
        return library.add_category(project_id, body.name)

    @api.delete('/projects/{project_id}/categories/{name}', status_code=204)
    def delete_category(project_id: int, name: str):
        library.delete_category(project_id, name)

    @api.get('/projects/{project_id}/journal')
    def list_journal(project_id: int, placement_id: int | None = None):
        return library.list_journal(project_id, placement_id)

    @api.post('/projects/{project_id}/journal', status_code=201)
    def add_journal_entry(project_id: int, body: JournalBody):
        return library.add_journal_entry(
            project_id, body.body, category=body.category,
            placement_id=body.placement_id)

    @api.patch('/journal/{entry_id}')
    def update_journal_entry(entry_id: int, body: JournalBody):
        return library.update_journal_entry(
            entry_id, body.body, body.category)

    @api.delete('/journal/{entry_id}', status_code=204)
    def delete_journal_entry(entry_id: int):
        library.delete_journal_entry(entry_id)

    @api.post('/journal/{entry_id}/images', status_code=201)
    async def add_journal_image(entry_id: int, request: fastapi.Request):
        return library.add_journal_image(entry_id, await request.body())

    @api.post('/journal/{entry_id}/files', status_code=201)
    async def add_journal_file(entry_id: int, name: str,
                               request: fastapi.Request):
        """Attaches the request body, which may be large, as a file."""
        with tempfile.SpooledTemporaryFile(_SPOOL_SIZE) as upload:
            async for chunk in request.stream():
                upload.write(chunk)
            upload.seek(0)
            return library.add_journal_file(entry_id, name, upload)

    @api.get('/journal-files/{file_id}')
    def get_journal_file(file_id: int):
        path, name = library.journal_file(file_id)
        return responses.FileResponse(path, filename=name)

    @api.delete('/journal-files/{file_id}', status_code=204)
    def delete_journal_file(file_id: int):
        library.delete_journal_file(file_id)

    @api.get('/journal-images/{image_id}')
    def get_journal_image(image_id: int):
        return responses.FileResponse(library.image_path(image_id))

    @api.delete('/journal-images/{image_id}', status_code=204)
    def delete_journal_image(image_id: int):
        library.delete_journal_image(image_id)

    @api.get('/projects/{project_id}/todos')
    def list_todos(project_id: int):
        return library.list_todos(project_id)

    @api.post('/projects/{project_id}/todos', status_code=201)
    def add_todo(project_id: int, body: TodoBody):
        return library.add_todo(**body.model_dump(mode='json'),
                                project_id=project_id)

    @api.patch('/todos/{todo_id}')
    def update_todo(todo_id: int, body: TodoChanges):
        return library.update_todo(
            todo_id, **body.model_dump(mode='json', exclude_unset=True))

    @api.delete('/todos/{todo_id}', status_code=204)
    def delete_todo(todo_id: int):
        library.delete_todo(todo_id)

    app.include_router(api)
    mimetypes.add_type('text/javascript', '.mjs')
    app.mount('/', staticfiles.StaticFiles(directory=_STATIC_DIR, html=True))
    return app


def _download(content: str | bytes, filename: str,
              media_type: str) -> responses.Response:
    disposition = f"attachment; filename*=UTF-8''{parse.quote(filename)}"
    return responses.Response(content, media_type=media_type,
                              headers={'Content-Disposition': disposition})


def _error_handler(status: int, code: str):
    def handle(request: fastapi.Request, error: Exception):
        del request, error  # Unused.
        return responses.JSONResponse({'detail': code}, status_code=status)
    return handle

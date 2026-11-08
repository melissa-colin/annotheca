"""HTTP API and static web interface."""

import mimetypes
import pathlib
from typing import Annotated, Any, Literal
from urllib import parse

import fastapi
import httpx
import pydantic
from fastapi import responses
from fastapi import staticfiles

from annotheca import library as library_lib
from annotheca import sources

_STATIC_DIR = pathlib.Path(__file__).parent / 'static'

# Exception types mapped to an HTTP status and the error code the
# interface translates for the user.
_ERRORS = {
    library_lib.NotFoundError: (404, 'not_found'),
    library_lib.ConflictError: (409, 'name_taken'),
    library_lib.InvalidPdfError: (422, 'not_pdf'),
}

Name = Annotated[str, pydantic.StringConstraints(
    strip_whitespace=True, min_length=1, max_length=80)]
Color = Annotated[str, pydantic.StringConstraints(pattern=r'^#[0-9a-fA-F]{6}$')]


class NameBody(pydantic.BaseModel):
    name: Name


class AddPapersBody(pydantic.BaseModel):
    """Either pasted references or an already known paper to file."""
    text: str | None = None
    paper_id: int | None = None


class AnnotationBody(pydantic.BaseModel):
    """A highlight or a note; coordinates are fractions of the page size.

    A highlight's geometry is a list of [x, y, width, height] rectangles;
    a note's is its [x, y] top-left corner.
    """
    kind: Literal['highlight', 'note']
    page: int = pydantic.Field(ge=1)
    color: Color
    geometry: list[Any]
    quote: str = ''
    body: str = ''


class AnnotationChanges(pydantic.BaseModel):
    color: Color | None = None
    geometry: list[Any] | None = None
    body: str | None = None


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
        filename = parse.quote(f'{name}.bib')
        disposition = f"attachment; filename*=UTF-8''{filename}"
        return responses.Response(
            content, media_type='application/x-bibtex',
            headers={'Content-Disposition': disposition})

    @api.post('/projects/{project_id}/folders', status_code=201)
    def create_folder(project_id: int, body: NameBody):
        return library.create_folder(project_id, body.name)

    @api.patch('/projects/{project_id}', status_code=204)
    def rename_project(project_id: int, body: NameBody):
        library.rename('project', project_id, body.name)

    @api.delete('/projects/{project_id}', status_code=204)
    def delete_project(project_id: int):
        library.delete('project', project_id)

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
        library.remove_placement(placement_id)

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
    def create_annotation(placement_id: int, body: AnnotationBody):
        return library.create_annotation(placement_id, body.model_dump())

    @api.patch('/annotations/{annotation_id}')
    def update_annotation(annotation_id: int, body: AnnotationChanges):
        return library.update_annotation(
            annotation_id, body.model_dump(exclude_none=True))

    @api.delete('/annotations/{annotation_id}', status_code=204)
    def delete_annotation(annotation_id: int):
        library.delete_annotation(annotation_id)

    app.include_router(api)
    mimetypes.add_type('text/javascript', '.mjs')
    app.mount('/', staticfiles.StaticFiles(directory=_STATIC_DIR, html=True))
    return app


def _error_handler(status: int, code: str):
    def handle(request: fastapi.Request, error: Exception):
        del request, error  # Unused.
        return responses.JSONResponse({'detail': code}, status_code=status)
    return handle

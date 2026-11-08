"""Annotheca's tools for AI assistants, served over the Model Context Protocol.

An assistant that finds papers files them here rather than writing references
itself: titles, authors and venues then come from doi.org, arXiv and Crossref,
not from its memory, and the user can see what each assistant added.
"""

from typing import Any

import httpx
from mcp.server.mcpserver import Context
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from annotheca import bibtex
from annotheca import library as library_lib
from annotheca import sources

_INSTRUCTIONS = """\
Annotheca is the user's reference manager. Each research project has folders
for its stages; every project has a 'SoA' (state of the art) folder.

- Whenever you find, recommend or rely on papers for the user, file them with
  add_references rather than writing references yourself. Annotheca resolves
  DOIs, arXiv IDs, BibTeX or formatted citations into verified metadata: quote
  the citation keys, titles and authors it returns, never your own recollection.
- Call list_projects when you do not know the project or folder names.
- Say in `note` why each paper matters; it is added to the paper's notes.
- Before summarising a paper the user has read, look at their notes and
  highlights with read_paper; its pdf_path lets you read the full text.
- get_bibtex returns the project's .bib file, to cite with LaTeX."""

_RESOLVE_ERRORS = {
    'unresolvable': 'No paper could be identified. Give a DOI, an arXiv ID, '
                    'a BibTeX entry or a complete formatted citation.',
    'unreachable': 'The online sources could not be reached; retry later.',
}
_DEFAULT_AGENT = 'AI assistant'


def create_server(library: library_lib.Library,
                  client: httpx.Client | None = None) -> MCPServer:
    """Builds the MCP server.

    Args:
        library: Where everything is stored.
        client: HTTP client for the scholarly sources; a default one is
            created when omitted.
    """
    client = client or sources.make_client()
    server = MCPServer('annotheca', instructions=_INSTRUCTIONS,
                       log_level='WARNING')

    @server.tool()
    def list_projects() -> list[dict[str, Any]]:
        """Lists the projects, with the number of papers in each folder."""
        return [{
            'project': project['name'],
            'folders': {folder['name']: len(folder['placements'])
                        for folder in _folders(library, project['id'])},
        } for project in library.list_projects()]

    @server.tool()
    def create_project(name: str) -> str:
        """Creates a project, which starts with an empty 'SoA' folder."""
        try:
            library.create_project(name)
        except library_lib.ConflictError as error:
            raise ToolError(f'A project is already named {name!r}.') from error
        return f'Created the project {name!r}.'

    @server.tool()
    def create_folder(project: str, folder: str) -> str:
        """Adds a folder, i.e. a stage such as 'Method', to a project."""
        try:
            library.create_folder(_project(library, project)['id'], folder)
        except library_lib.ConflictError as error:
            raise ToolError(
                f'{project!r} already has a folder {folder!r}.') from error
        return f'Created the folder {folder!r} in {project!r}.'

    @server.tool()
    def add_references(
            project: str, references: str, ctx: Context,
            folder: str = library_lib.DEFAULT_FOLDER,
            note: str = '') -> list[dict[str, Any]]:
        """Files papers in a project folder, with verified metadata and PDFs.

        Args:
            project: Project name, as listed by list_projects.
            references: DOIs, arXiv IDs or paper URLs (one per line), BibTeX
                entries, or a single formatted citation.
            folder: Folder of the project; 'SoA' by default.
            note: Why these papers matter here; added to their notes.

        Returns:
            For each paper: its citation key, title, authors, year and venue
            as resolved from the sources, its DOI, whether its PDF is
            available, and whether it was already in the folder.
        """
        folder_id = _folder(library, project, folder)['id']
        try:
            entries = sources.resolve(references, client)
        except sources.ResolveError as error:
            raise ToolError(_RESOLVE_ERRORS[str(error)]) from error
        agent = _agent(ctx)
        papers = []
        for entry in entries:
            paper_id = library.add_paper(entry)
            added = library.file_papers(folder_id, [paper_id], agent)
            if note:
                placement_id = library.file_paper(folder_id, paper_id)
                library.append_notes(placement_id, f'[{agent}] {note}')
            if not library.pdf_path(paper_id).exists():
                if pdf := sources.find_pdf(library.get_paper(paper_id), client):
                    library.save_pdf(paper_id, pdf)
            entry = library.get_paper(paper_id)
            papers.append({
                **entry.summary(),
                'doi': entry.doi,
                'pdf_available': library.pdf_path(paper_id).exists(),
                'already_in_folder': not added,
            })
        return papers

    @server.tool()
    def list_papers(project: str,
                    folder: str | None = None) -> dict[str, list[dict]]:
        """Lists the papers of a project, by folder, with the user's notes.

        Args:
            project: Project name.
            folder: Only list this folder.
        """
        folders = ([_folder(library, project, folder)] if folder
                   else _folders(library, _project(library, project)['id']))
        return {f['name']: [{
            key: placement[key] for key in (
                'citekey', 'title', 'authors', 'year', 'venue', 'notes',
                'added_by', 'annotation_count')
        } for placement in f['placements']] for f in folders}

    @server.tool()
    def read_paper(project: str, citekey: str) -> dict[str, Any]:
        """Returns what the user knows about a paper of the project.

        That is its BibTeX, the path of its PDF (null if missing) and, for
        each folder where it is filed, the general notes, the highlighted
        passages and the sticky notes.
        """
        placements = _placements(library, project, citekey)
        paper_id = placements[0][1]['paper_id']
        pdf_path = library.pdf_path(paper_id)
        folders = {}
        for folder_name, placement in placements:
            annotations = library.list_annotations(placement['id'])
            folders[folder_name] = {
                'notes': placement['notes'],
                'added_by': placement['added_by'],
                'highlights': [
                    {'page': a['page'], 'quote': a['quote']}
                    for a in annotations if a['kind'] == 'highlight'],
                'sticky_notes': [
                    {'page': a['page'], 'text': a['body']}
                    for a in annotations if a['kind'] == 'note'],
            }
        return {
            'bibtex': bibtex.format_entry(library.get_paper(paper_id)),
            'pdf_path': str(pdf_path) if pdf_path.exists() else None,
            'folders': folders,
        }

    @server.tool()
    def add_note(project: str, citekey: str, text: str, ctx: Context,
                 folder: str | None = None) -> str:
        """Appends a signed paragraph to a paper's notes in one folder.

        Args:
            project: Project name.
            citekey: Citation key of the paper.
            text: The note.
            folder: Required when the paper is filed in several folders.
        """
        placements = _placements(library, project, citekey)
        if folder:
            placements = [p for p in placements if p[0] == folder]
            if not placements:
                raise ToolError(f'{citekey} is not in the folder {folder!r}.')
        elif len(placements) > 1:
            names = ', '.join(name for name, _ in placements)
            raise ToolError(f'{citekey} is in several folders ({names}); '
                            'say which one.')
        folder_name, placement = placements[0]
        library.append_notes(placement['id'], f'[{_agent(ctx)}] {text}')
        return f'Added the note to {citekey} in {folder_name!r}.'

    @server.tool()
    def get_bibtex(project: str) -> str:
        """Returns the .bib file of a project, each paper appearing once."""
        return library.export_bibtex(_project(library, project)['id'])[1]

    return server


def _agent(ctx: Context) -> str:
    """The name the assistant's application gave when connecting."""
    params = ctx.session.client_params
    return params.client_info.name if params else _DEFAULT_AGENT


def _project(library: library_lib.Library, name: str) -> dict[str, Any]:
    projects = library.list_projects()
    for project in projects:
        if project['name'] == name:
            return project
    raise ToolError(f'No project is named {name!r}. Projects: '
                    f'{", ".join(p["name"] for p in projects) or "none"}.')


def _folders(library: library_lib.Library,
             project_id: int) -> list[dict[str, Any]]:
    return library.get_project(project_id)['folders']


def _folder(library: library_lib.Library, project: str,
            name: str) -> dict[str, Any]:
    folders = _folders(library, _project(library, project)['id'])
    for folder in folders:
        if folder['name'] == name:
            return folder
    raise ToolError(f'{project!r} has no folder {name!r}. Folders: '
                    f'{", ".join(f["name"] for f in folders)}.')


def _placements(library: library_lib.Library, project: str,
                citekey: str) -> list[tuple[str, dict[str, Any]]]:
    """The (folder name, placement) pairs of a paper in a project."""
    placements = [
        (folder['name'], placement)
        for folder in _folders(library, _project(library, project)['id'])
        for placement in folder['placements']
        if placement['citekey'] == citekey]
    if not placements:
        raise ToolError(f'{project!r} has no paper {citekey!r}; '
                        'see list_papers.')
    return placements

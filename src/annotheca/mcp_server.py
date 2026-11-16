"""Annotheca's tools for AI assistants, served over the Model Context Protocol.

An assistant that finds papers files them here rather than writing references
itself: titles, authors and venues then come from doi.org, arXiv and Crossref,
not from its memory, and the user can see what each assistant added.
"""

import datetime
import pathlib
from typing import Any

import httpx
from mcp.server.mcpserver import Context
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from annotheca import bibtex
from annotheca import library as library_lib
from annotheca import models
from annotheca import sources

_INSTRUCTIONS = """\
Annotheca is the user's research notebook and reference manager. Each research
project has folders of papers for its stages (every project has a 'SoA', state
of the art, folder), a dated journal of its progress and a to-do list.

- Whenever you find, recommend or rely on papers for the user, file them with
  add_references rather than writing references yourself. Annotheca resolves
  DOIs, arXiv IDs, BibTeX or formatted citations into verified metadata: quote
  the citation keys, titles and authors it returns, never your own recollection.
- Call list_projects when you do not know the project or folder names.
- Say in `note` why each paper matters; it becomes a reading note on the
  paper. Reading notes, added with add_note too, are journal entries linked
  to the paper: a paper can have any number of them.
- Before summarising a paper the user has read, look at their reading notes
  and highlights with read_paper; its pdf_path lets you read the full text.
- get_bibtex returns the project's .bib file, to cite with LaTeX.
- Record what you did, decided or found for the project with
  add_journal_entry: entries are dated and signed, which versions the work.
  Write Markdown; a ```tikz code block (a tikzpicture, \\usetikzlibrary lines
  allowed; positioning, arrows.meta, calc, fit and shapes.geometric are
  always loaded) is drawn as a diagram, and image_paths attaches local images
  such as plots; file_paths attaches files of any kind (scripts, datasets) as
  they are now, which versions them with the entry. Give each entry a
  category so that the user can sort the journal: idea, experiment, result,
  problem, decision, reading, or one of the project's own, listed by
  list_projects and added with add_journal_category. Read the history with
  read_journal before resuming a project; it gives the local path of each
  attached file.
- Keep the project's to-do list current with list_todos, add_todo (with a
  deadline and a priority when they are known) and complete_todo."""

_RESOLVE_ERRORS = {
    'unresolvable': 'No paper could be identified with certainty. Give a '
                    'DOI, an arXiv ID, a link to the paper page, a BibTeX '
                    'entry or a complete formatted citation.',
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
        """Lists the projects, with the number of papers in each folder
        and the categories of their journal."""
        return [{
            'project': project['name'],
            'folders': {folder['name']: len(folder['placements'])
                        for folder in _folders(library, project['id'])},
            'journal_categories': _categories(library, project['id']),
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
            references: DOIs, arXiv IDs or links to paper pages (one per
                line), BibTeX entries, or a single formatted citation.
            folder: Folder of the project; 'SoA' by default.
            note: Why these papers matter here; added as a reading note on
                each.

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
                library.add_reading_note(
                    library.file_paper(folder_id, paper_id), note, agent)
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
        """Lists the papers of a project, by folder.

        Args:
            project: Project name.
            folder: Only list this folder.
        """
        folders = ([_folder(library, project, folder)] if folder
                   else _folders(library, _project(library, project)['id']))
        return {f['name']: [{
            key: placement[key] for key in (
                'citekey', 'title', 'authors', 'year', 'venue',
                'added_by', 'note_count', 'annotation_count')
        } for placement in f['placements']] for f in folders}

    @server.tool()
    def read_paper(project: str, citekey: str) -> dict[str, Any]:
        """Returns what the user knows about a paper of the project.

        That is its BibTeX, the path of its PDF (null if missing) and, for
        each folder where it is filed, the reading notes, the highlighted
        passages and the sticky notes.
        """
        project_id = _project(library, project)['id']
        placements = _placements(library, project, citekey)
        paper_id = placements[0][1]['paper_id']
        pdf_path = library.pdf_path(paper_id)
        folders = {}
        for folder_name, placement in placements:
            annotations = library.list_annotations(placement['id'])
            notes = library.list_journal(project_id, placement['id'])
            folders[folder_name] = {
                'notes': [{
                    'date': note['created_at'],
                    'author': note['author'] or 'user', 'text': note['body'],
                } for note in notes],
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
        """Adds a dated, signed reading note on a paper, shown in the
        journal with a link to the paper.

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
        library.add_reading_note(placement['id'], text, _agent(ctx))
        return f'Added the note to {citekey} in {folder_name!r}.'

    @server.tool()
    def get_bibtex(project: str) -> str:
        """Returns the .bib file of a project, each paper appearing once."""
        return library.export_bibtex(_project(library, project)['id'])[1]

    @server.tool()
    def add_journal_entry(project: str, text: str, ctx: Context,
                          category: str = '',
                          image_paths: list[str] | None = None,
                          file_paths: list[str] | None = None) -> str:
        """Adds a dated, signed entry to the project's journal.

        Args:
            project: Project name.
            text: The entry, in Markdown. A ```tikz code block holding a
                tikzpicture is drawn as a diagram.
            category: What the entry is: an 'idea', an 'experiment' run, a
                'result', a 'problem' met, a 'decision', a 'reading' note, or
                one of the project's own categories (see list_projects); ''
                when none fits.
            image_paths: Local PNG, JPEG, GIF or WebP files, shown in the
                entry.
            file_paths: Local files of any kind (a script, a dataset, a
                config) to attach as they are now, so that this version can
                be found again with the entry.
        """
        project_id = _project(library, project)['id']
        categories = _categories(library, project_id)
        if category and category not in categories:
            raise ToolError(f'Unknown category {category!r}; use one of '
                            f'{", ".join(categories)}, or add it first.')
        images = [pathlib.Path(path).expanduser() for path in image_paths or []]
        files = [pathlib.Path(path).expanduser() for path in file_paths or []]
        for path in images + files:
            if not path.is_file():
                raise ToolError(f'No file at {path}.')
        entry = library.add_journal_entry(
            project_id, text, _agent(ctx), category=category)
        try:
            for path in images:
                library.add_journal_image(entry['id'], path.read_bytes())
        except library_lib.InvalidImageError as error:
            library.delete_journal_entry(entry['id'])
            raise ToolError(
                f'{path} is not a PNG, JPEG, GIF or WebP image.') from error
        for path in files:
            with path.open('rb') as source:
                library.add_journal_file(entry['id'], path.name, source)
        return f'Added the entry of {entry["created_at"]} to {project!r}.'

    @server.tool()
    def add_journal_category(project: str, name: str) -> list[str]:
        """Adds a journal category of the project's own, such as 'meeting';
        returns all the categories of the project."""
        project_id = _project(library, project)['id']
        try:
            library.add_category(project_id, name.strip())
        except library_lib.ConflictError as error:
            raise ToolError(f'{project!r} already has {name!r}.') from error
        return _categories(library, project_id)

    @server.tool()
    def read_journal(
            project: str, limit: int = 20,
            category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Returns the latest journal entries of a project, newest first,
        optionally only those of one category."""
        entries = [
            entry for entry in library.list_journal(
                _project(library, project)['id'])
            if category is None or entry['category'] == category]
        return [{
            'date': entry['created_at'], 'category': entry['category'],
            'paper': entry['paper'] and entry['paper']['citekey'],
            'author': entry['author'] or 'user', 'text': entry['body'],
            'images': len(entry['images']),
            'files': {file['name']: str(library.journal_file(file['id'])[0])
                      for file in entry['files']},
        } for entry in entries[:limit]]

    @server.tool()
    def list_todos(project: str,
                   include_done: bool = False) -> list[dict[str, Any]]:
        """Lists the to-dos of a project, open ones first."""
        todos = library.list_todos(_project(library, project)['id'])
        return [todo for todo in todos if include_done or not todo['done_at']]

    @server.tool()
    def add_todo(project: str, text: str, ctx: Context,
                 due_date: datetime.date | None = None,
                 priority: models.Priority = '') -> dict[str, Any]:
        """Adds a task to the project's to-do list.

        Args:
            project: Project name.
            text: The task.
            due_date: Its deadline, if any.
            priority: 'high', 'medium' or 'low'; '' for none.
        """
        return library.add_todo(
            _project(library, project)['id'], text, _agent(ctx),
            due_date=due_date and due_date.isoformat(), priority=priority)

    @server.tool()
    def complete_todo(project: str, todo_id: int) -> dict[str, Any]:
        """Marks a to-do of the project as done, dated now."""
        project_id = _project(library, project)['id']
        if not any(todo['id'] == todo_id
                   for todo in library.list_todos(project_id)):
            raise ToolError(f'{project!r} has no to-do {todo_id}.')
        return library.update_todo(todo_id, done=True)

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


def _categories(library: library_lib.Library, project_id: int) -> list[str]:
    """The journal categories a project can use."""
    return [*library_lib.BUILTIN_CATEGORIES,
            *library.get_project(project_id)['categories']]


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

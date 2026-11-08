"""Persistent storage of projects, folders, papers and annotations.

A paper is stored once, with its BibTeX and PDF, whatever the number of
folders it is filed in. Each filing (a "placement") carries its own
highlights and notes, so the same paper can be annotated differently in
two folders.
"""

import contextlib
import json
import pathlib
import sqlite3
import string
from collections.abc import Iterator
from typing import Any

from annotheca import bibtex

DEFAULT_FOLDER = 'SoA'

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    UNIQUE (project_id, name)
);
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY,
    citekey TEXT NOT NULL UNIQUE,
    entry_type TEXT NOT NULL,
    fields TEXT NOT NULL,
    doi TEXT UNIQUE,
    arxiv_id TEXT UNIQUE,
    title_key TEXT
);
CREATE INDEX IF NOT EXISTS papers_title_key ON papers (title_key);
CREATE TABLE IF NOT EXISTS placements (
    id INTEGER PRIMARY KEY,
    folder_id INTEGER NOT NULL REFERENCES folders (id) ON DELETE CASCADE,
    paper_id INTEGER NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
    UNIQUE (folder_id, paper_id)
);
CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY,
    placement_id INTEGER NOT NULL
        REFERENCES placements (id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('highlight', 'note')),
    page INTEGER NOT NULL,
    color TEXT NOT NULL,
    geometry TEXT NOT NULL,
    quote TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT ''
);
"""

# Each statement upgrades the database by one version, starting from the
# empty database (PRAGMA user_version = 0).
_MIGRATIONS = (
    _SCHEMA,
    "ALTER TABLE placements ADD COLUMN notes TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE placements ADD COLUMN added_by TEXT NOT NULL DEFAULT ''",
)

_ANNOTATION_COLUMNS = (
    'id', 'kind', 'page', 'color', 'geometry', 'quote', 'body')


class NotFoundError(LookupError):
    """The requested project, folder, paper or annotation does not exist."""


class ConflictError(ValueError):
    """A sibling project or folder already has that name."""


class InvalidPdfError(ValueError):
    """The uploaded bytes are not a PDF."""


class Library:
    """A library stored as a SQLite database plus a directory of PDFs."""

    def __init__(self, root: pathlib.Path) -> None:
        """Opens the library in `root`, creating it if needed."""
        self._pdf_dir = root / 'pdfs'
        self._pdf_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = root / 'library.db'
        with self._connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            for number, sql in enumerate(_MIGRATIONS[version:], version + 1):
                db.executescript(sql)
                db.execute(f'PRAGMA user_version = {number}')

    # Projects and folders.

    def list_projects(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                'SELECT id, name FROM projects ORDER BY name COLLATE NOCASE')
            return [dict(row) for row in rows]

    def create_project(self, name: str) -> dict[str, Any]:
        """Creates a project holding the default folder."""
        with self._connect() as db:
            project_id = _write(
                db, 'INSERT INTO projects (name) VALUES (?)', name)
            _write(db, 'INSERT INTO folders (project_id, name) VALUES (?, ?)',
                   project_id, DEFAULT_FOLDER)
        return {'id': project_id, 'name': name}

    def get_project(self, project_id: int) -> dict[str, Any]:
        """Returns a project with its folders and the papers filed in them."""
        with self._connect() as db:
            project = _fetch_one(
                db, 'SELECT id, name FROM projects WHERE id = ?', project_id)
            rows = db.execute("""
                SELECT f.id AS folder_id, f.name AS folder_name,
                       pl.id AS placement_id, pl.notes, pl.added_by,
                       p.id AS paper_id,
                       p.citekey, p.entry_type, p.fields,
                       (SELECT COUNT(*) FROM annotations a
                        WHERE a.placement_id = pl.id) AS annotation_count
                FROM folders f
                LEFT JOIN placements pl ON pl.folder_id = f.id
                LEFT JOIN papers p ON p.id = pl.paper_id
                WHERE f.project_id = ?
                ORDER BY f.id, pl.id DESC""", (project_id,)).fetchall()
        folders = {}
        for row in rows:
            folder = folders.setdefault(row['folder_id'], {
                'id': row['folder_id'], 'name': row['folder_name'],
                'placements': []})
            if row['placement_id'] is not None:
                folder['placements'].append(self._placement_summary(row))
        return {**dict(project), 'folders': list(folders.values())}

    def create_folder(self, project_id: int, name: str) -> dict[str, Any]:
        with self._connect() as db:
            _fetch_one(db, 'SELECT id FROM projects WHERE id = ?', project_id)
            folder_id = _write(
                db, 'INSERT INTO folders (project_id, name) VALUES (?, ?)',
                project_id, name)
        return {'id': folder_id, 'name': name, 'placements': []}

    def rename(self, kind: str, item_id: int, name: str) -> None:
        """Renames a project or a folder.

        Args:
            kind: Either 'project' or 'folder'.
            item_id: Identifier of the project or folder.
            name: The new name.
        """
        table = _container_table(kind)
        with self._connect() as db:
            _fetch_one(db, f'SELECT id FROM {table} WHERE id = ?', item_id)
            _write(db, f'UPDATE {table} SET name = ? WHERE id = ?',
                   name, item_id)

    def delete(self, kind: str, item_id: int) -> None:
        """Deletes a project or a folder with everything filed in it."""
        table = _container_table(kind)
        with self._connect() as db:
            _execute_one(db, f'DELETE FROM {table} WHERE id = ?', item_id)
            self._prune_orphans(db)

    def export_bibtex(self, project_id: int) -> tuple[str, str]:
        """Returns the project name and the BibTeX of all its papers.

        A paper filed in several folders appears only once.
        """
        with self._connect() as db:
            project = _fetch_one(
                db, 'SELECT name FROM projects WHERE id = ?', project_id)
            rows = db.execute("""
                SELECT DISTINCT p.citekey, p.entry_type, p.fields
                FROM papers p
                JOIN placements pl ON pl.paper_id = p.id
                JOIN folders f ON f.id = pl.folder_id
                WHERE f.project_id = ?
                ORDER BY p.citekey""", (project_id,)).fetchall()
        entries = [bibtex.format_entry(_entry(row)) for row in rows]
        return project['name'], '\n\n'.join(entries) + '\n' if entries else ''

    # Papers and placements.

    def add_paper(self, entry: bibtex.Entry) -> int:
        """Stores a paper, or finds it if already known, and returns its id.

        A paper is known when its DOI, arXiv identifier or title matches.
        """
        with self._connect() as db:
            known = db.execute(
                'SELECT id FROM papers'
                ' WHERE doi = ? OR arxiv_id = ? OR title_key = ?',
                (entry.doi, entry.arxiv_id, entry.title_key)).fetchone()
            if known:
                return known['id']
            return _write(
                db, 'INSERT INTO papers (citekey, entry_type, fields, doi,'
                ' arxiv_id, title_key) VALUES (?, ?, ?, ?, ?, ?)',
                _unique_citekey(db, entry.citekey), entry.entry_type,
                json.dumps(entry.fields), entry.doi, entry.arxiv_id,
                entry.title_key)

    def get_paper(self, paper_id: int) -> bibtex.Entry:
        with self._connect() as db:
            return _entry(_fetch_one(
                db, 'SELECT citekey, entry_type, fields FROM papers'
                ' WHERE id = ?', paper_id))

    def file_papers(self, folder_id: int, paper_ids: list[int],
                    added_by: str = '') -> int:
        """Files papers in a folder and returns how many were not already.

        Args:
            folder_id: The folder to file the papers in.
            paper_ids: The papers to file.
            added_by: Name of the AI assistant filing them, if any.
        """
        with self._connect() as db:
            _fetch_one(db, 'SELECT id FROM folders WHERE id = ?', folder_id)
            before = db.total_changes
            db.executemany(
                'INSERT OR IGNORE INTO placements (folder_id, paper_id,'
                ' added_by) VALUES (?, ?, ?)',
                [(folder_id, pid, added_by) for pid in paper_ids])
            return db.total_changes - before

    def file_paper(self, folder_id: int, paper_id: int,
                   added_by: str = '') -> int:
        """Files a paper in a folder if needed; returns the placement id."""
        self.file_papers(folder_id, [paper_id], added_by)
        with self._connect() as db:
            placement = _fetch_one(
                db, 'SELECT id FROM placements'
                ' WHERE folder_id = ? AND paper_id = ?', folder_id, paper_id)
            return placement['id']

    def append_notes(self, placement_id: int, text: str) -> None:
        """Adds a paragraph to the general notes taken on a paper."""
        with self._connect() as db:
            _execute_one(
                db, "UPDATE placements SET notes = CASE notes WHEN '' THEN ?"
                " ELSE notes || char(10) || char(10) || ? END WHERE id = ?",
                text, text, placement_id)

    def set_notes(self, placement_id: int, notes: str) -> None:
        """Replaces the general notes taken on a paper in one folder."""
        with self._connect() as db:
            _execute_one(db, 'UPDATE placements SET notes = ? WHERE id = ?',
                         notes, placement_id)

    def remove_placement(self, placement_id: int) -> None:
        """Takes a paper out of a folder, forgetting it if filed nowhere."""
        with self._connect() as db:
            _execute_one(
                db, 'DELETE FROM placements WHERE id = ?', placement_id)
            self._prune_orphans(db)

    def pdf_path(self, paper_id: int) -> pathlib.Path:
        """Where the paper's PDF is stored; the file may not exist."""
        return self._pdf_dir / f'{paper_id}.pdf'

    def save_pdf(self, paper_id: int, data: bytes) -> None:
        if not data.startswith(b'%PDF'):
            raise InvalidPdfError
        with self._connect() as db:
            _fetch_one(db, 'SELECT id FROM papers WHERE id = ?', paper_id)
        self.pdf_path(paper_id).write_bytes(data)

    # Annotations.

    def list_annotations(self, placement_id: int) -> list[dict[str, Any]]:
        with self._connect() as db:
            _fetch_one(
                db, 'SELECT id FROM placements WHERE id = ?', placement_id)
            rows = db.execute(
                f'SELECT {", ".join(_ANNOTATION_COLUMNS)} FROM annotations'
                ' WHERE placement_id = ? ORDER BY page, id', (placement_id,))
            return [_annotation(row) for row in rows]

    def create_annotation(
            self, placement_id: int, annotation: dict[str, Any]) -> dict:
        """Adds a highlight or a note to a placement.

        Args:
            placement_id: The placement being annotated.
            annotation: Values for 'kind', 'page', 'color', 'geometry' and
                optionally 'quote' and 'body'.
        """
        values = {**annotation, 'geometry': json.dumps(annotation['geometry'])}
        with self._connect() as db:
            _fetch_one(
                db, 'SELECT id FROM placements WHERE id = ?', placement_id)
            columns = ', '.join(values)
            placeholders = ', '.join('?' * len(values))
            annotation_id = _write(
                db, f'INSERT INTO annotations (placement_id, {columns})'
                f' VALUES (?, {placeholders})', placement_id, *values.values())
            return self._get_annotation(db, annotation_id)

    def update_annotation(
            self, annotation_id: int, changes: dict[str, Any]) -> dict:
        """Changes the color, geometry or body of an annotation."""
        if 'geometry' in changes:
            changes = {**changes, 'geometry': json.dumps(changes['geometry'])}
        assignments = ', '.join(f'{name} = ?' for name in changes)
        with self._connect() as db:
            _fetch_one(
                db, 'SELECT id FROM annotations WHERE id = ?', annotation_id)
            if changes:
                db.execute(
                    f'UPDATE annotations SET {assignments} WHERE id = ?',
                    (*changes.values(), annotation_id))
            return self._get_annotation(db, annotation_id)

    def delete_annotation(self, annotation_id: int) -> None:
        with self._connect() as db:
            _execute_one(
                db, 'DELETE FROM annotations WHERE id = ?', annotation_id)

    # Helpers.

    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yields a connection whose changes are committed on success."""
        db = sqlite3.connect(self._db_path)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def _prune_orphans(self, db: sqlite3.Connection) -> None:
        orphans = db.execute(
            'DELETE FROM papers WHERE id NOT IN'
            ' (SELECT paper_id FROM placements) RETURNING id').fetchall()
        for row in orphans:
            self.pdf_path(row['id']).unlink(missing_ok=True)

    def _placement_summary(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            **_entry(row).summary(),
            'id': row['placement_id'],
            'paper_id': row['paper_id'],
            'has_pdf': self.pdf_path(row['paper_id']).exists(),
            'annotation_count': row['annotation_count'],
            'notes': row['notes'],
            'added_by': row['added_by'],
        }

    def _get_annotation(
            self, db: sqlite3.Connection, annotation_id: int) -> dict:
        return _annotation(_fetch_one(
            db, f'SELECT {", ".join(_ANNOTATION_COLUMNS)} FROM annotations'
            ' WHERE id = ?', annotation_id))


def _container_table(kind: str) -> str:
    tables = {'project': 'projects', 'folder': 'folders'}
    if kind not in tables:
        raise ValueError(f'Unknown container kind: {kind!r}')
    return tables[kind]


def _write(db: sqlite3.Connection, sql: str, *params: Any) -> int:
    """Runs a write statement, turning uniqueness errors into conflicts."""
    try:
        return db.execute(sql, params).lastrowid
    except sqlite3.IntegrityError as error:
        raise ConflictError(str(error)) from error


def _fetch_one(db: sqlite3.Connection, sql: str, *params: Any) -> sqlite3.Row:
    row = db.execute(sql, params).fetchone()
    if row is None:
        raise NotFoundError
    return row


def _execute_one(db: sqlite3.Connection, sql: str, *params: Any) -> None:
    if db.execute(sql, params).rowcount == 0:
        raise NotFoundError


def _unique_citekey(db: sqlite3.Connection, citekey: str) -> str:
    """Appends a, b, c... to `citekey` until no paper uses it."""
    for suffix in ('', *string.ascii_lowercase):
        candidate = citekey + suffix
        if not db.execute('SELECT 1 FROM papers WHERE citekey = ?',
                          (candidate,)).fetchone():
            return candidate
    raise ConflictError(citekey)


def _entry(row: sqlite3.Row) -> bibtex.Entry:
    return bibtex.Entry(
        row['entry_type'], row['citekey'], json.loads(row['fields']))


def _annotation(row: sqlite3.Row) -> dict[str, Any]:
    return {**dict(row), 'geometry': json.loads(row['geometry'])}

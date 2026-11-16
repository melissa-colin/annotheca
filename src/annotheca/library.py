"""Persistent storage of projects, folders, papers and annotations.

A paper is stored once, with its BibTeX and PDF, whatever the number of
folders it is filed in. Each filing (a "placement") carries its own
highlights, sticky notes and reading notes, so the same paper can be
annotated differently in two folders. Reading notes are journal entries
linked to the placement, so that they also tell the story of the project.

Deleted projects and placements first go to the trash, from which they can
be restored with everything they hold, until they are deleted for good,
at the latest after TRASH_DAYS.
"""

import contextlib
import datetime
import json
import pathlib
import shutil
import sqlite3
import string
from collections.abc import Iterator
from typing import Any, BinaryIO

from annotheca import bibtex

DEFAULT_FOLDER = 'SoA'
TRASH_DAYS = 30

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
    """
    CREATE TABLE journal_entries (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
        body TEXT NOT NULL,
        author TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT
    );
    CREATE TABLE journal_images (
        id INTEGER PRIMARY KEY,
        entry_id INTEGER NOT NULL
            REFERENCES journal_entries (id) ON DELETE CASCADE,
        extension TEXT NOT NULL
    );
    CREATE TABLE todos (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
        text TEXT NOT NULL,
        author TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        done_at TEXT
    );
    """,
    "ALTER TABLE journal_entries ADD COLUMN category TEXT NOT NULL DEFAULT ''",
    """
    CREATE TABLE journal_files (
        id INTEGER PRIMARY KEY,
        entry_id INTEGER NOT NULL
            REFERENCES journal_entries (id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        size INTEGER NOT NULL DEFAULT 0
    );
    """,
    """
    ALTER TABLE projects ADD COLUMN deleted_at TEXT;
    ALTER TABLE placements ADD COLUMN deleted_at TEXT;
    """,
    """
    ALTER TABLE journal_entries ADD COLUMN placement_id INTEGER
        REFERENCES placements (id) ON DELETE SET NULL;
    -- Notes become reading notes, one per paragraph signed '[assistant] '.
    WITH RECURSIVE parts (placement_id, project_id, part, rest, n) AS (
        SELECT pl.id, f.project_id, NULL, pl.notes, 0
        FROM placements pl JOIN folders f ON f.id = pl.folder_id
        WHERE pl.notes != ''
        UNION ALL
        SELECT placement_id, project_id,
               iif(instr(rest, char(10, 10, 91)),
                   substr(rest, 1, instr(rest, char(10, 10, 91)) - 1), rest),
               iif(instr(rest, char(10, 10, 91)),
                   substr(rest, instr(rest, char(10, 10, 91)) + 2), ''),
               n + 1
        FROM parts WHERE rest != ''
    ),
    signed (placement_id, project_id, part, n, is_signed) AS (
        SELECT placement_id, project_id, part, n,
               part GLOB '[[]*] *' AND instr(part, '] ') <= 40
        FROM parts WHERE part IS NOT NULL
    )
    INSERT INTO journal_entries
        (project_id, body, category, author, created_at, placement_id)
    SELECT project_id,
           iif(is_signed, substr(part, instr(part, '] ') + 2), part),
           'reading',
           iif(is_signed, substr(part, 2, instr(part, '] ') - 2), ''),
           strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'), placement_id
    FROM signed ORDER BY placement_id, n;
    ALTER TABLE placements DROP COLUMN notes;
    ALTER TABLE todos ADD COLUMN due_date TEXT;
    ALTER TABLE todos ADD COLUMN priority TEXT NOT NULL DEFAULT '';
    """,
)

# Accepted journal images: leading bytes, then the extension they are saved
# with. A WebP file starts with RIFF....WEBP.
_IMAGE_SIGNATURES = (
    (b'\x89PNG', '.png'),
    (b'\xff\xd8\xff', '.jpg'),
    (b'GIF8', '.gif'),
    (b'RIFF', '.webp'),
)

_TODO_COLUMNS = (
    'id, text, author, created_at, done_at, due_date, priority')

_ANNOTATION_COLUMNS = (
    'id', 'kind', 'page', 'color', 'geometry', 'quote', 'body')


class NotFoundError(LookupError):
    """The requested project, folder, paper or annotation does not exist."""


class ConflictError(ValueError):
    """A sibling project or folder already has that name."""


class NameInTrashError(ConflictError):
    """A project in the trash has that name."""


class InvalidPdfError(ValueError):
    """The uploaded bytes are not a PDF."""


class InvalidImageError(ValueError):
    """The uploaded bytes are not a PNG, JPEG, GIF or WebP image."""


class Library:
    """A library stored as a SQLite database plus a directory of PDFs."""

    def __init__(self, root: pathlib.Path) -> None:
        """Opens the library in `root`, creating it if needed."""
        self._pdf_dir = root / 'pdfs'
        self._pdf_dir.mkdir(parents=True, exist_ok=True)
        self._image_dir = root / 'images'
        self._image_dir.mkdir(exist_ok=True)
        self._file_dir = root / 'files'
        self._file_dir.mkdir(exist_ok=True)
        self._db_path = root / 'library.db'
        with self._connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            for number, sql in enumerate(_MIGRATIONS[version:], version + 1):
                db.executescript(sql)
                db.execute(f'PRAGMA user_version = {number}')
        self._empty_trash(f'-{TRASH_DAYS} days')

    # Projects and folders.

    def list_projects(self) -> list[dict[str, Any]]:
        """Returns the projects with their size and latest activity."""
        with self._connect() as db:
            rows = db.execute("""
                SELECT p.id, p.name,
                       (SELECT COUNT(DISTINCT pl.paper_id) FROM folders f
                        JOIN placements pl ON pl.folder_id = f.id
                        WHERE f.project_id = p.id
                        AND pl.deleted_at IS NULL) AS paper_count,
                       (SELECT COUNT(*) FROM todos t WHERE t.project_id = p.id
                        AND t.done_at IS NULL) AS open_todos,
                       (SELECT MAX(created_at) FROM journal_entries j
                        WHERE j.project_id = p.id) AS last_entry
                FROM projects p WHERE p.deleted_at IS NULL
                ORDER BY p.name COLLATE NOCASE""")
            return [dict(row) for row in rows]

    def create_project(self, name: str) -> dict[str, Any]:
        """Creates a project holding the default folder."""
        with self._connect() as db:
            project_id = _write_project_name(
                db, 'INSERT INTO projects (name) VALUES (?)', name)
            _write(db, 'INSERT INTO folders (project_id, name) VALUES (?, ?)',
                   project_id, DEFAULT_FOLDER)
        return {'id': project_id, 'name': name}

    def get_project(self, project_id: int) -> dict[str, Any]:
        """Returns a project with its folders and the papers filed in them."""
        with self._connect() as db:
            project = _fetch_one(db, """
                SELECT id, name,
                       (SELECT COUNT(*) FROM todos
                        WHERE project_id = projects.id
                        AND done_at IS NULL) AS open_todos,
                       (SELECT COUNT(*) FROM journal_entries
                        WHERE project_id = projects.id) AS journal_entries
                FROM projects WHERE id = ? AND deleted_at IS NULL""",
                project_id)
            rows = db.execute("""
                SELECT f.id AS folder_id, f.name AS folder_name,
                       pl.id AS placement_id, pl.added_by,
                       p.id AS paper_id,
                       p.citekey, p.entry_type, p.fields,
                       (SELECT COUNT(*) FROM annotations a
                        WHERE a.placement_id = pl.id) AS annotation_count,
                       (SELECT COUNT(*) FROM journal_entries j
                        WHERE j.placement_id = pl.id) AS note_count
                FROM folders f
                LEFT JOIN placements pl
                    ON pl.folder_id = f.id AND pl.deleted_at IS NULL
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
            write = _write_project_name if kind == 'project' else _write
            write(db, f'UPDATE {table} SET name = ? WHERE id = ?',
                  name, item_id)

    def delete(self, kind: str, item_id: int) -> None:
        """Deletes a project or a folder with everything filed in it, for
        good."""
        table = _container_table(kind)
        with self._connect() as db:
            _execute_one(db, f'DELETE FROM {table} WHERE id = ?', item_id)
            self._prune_orphans(db)
        self._prune_attachments()

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
                WHERE f.project_id = ? AND pl.deleted_at IS NULL
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
            # Filing a paper again takes it out of the trash, with its
            # highlights.
            db.executemany(
                'UPDATE placements SET deleted_at = NULL WHERE folder_id = ?'
                ' AND paper_id = ? AND deleted_at IS NOT NULL',
                [(folder_id, pid) for pid in paper_ids])
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

    def remove_placement(self, placement_id: int) -> None:
        """Takes a paper out of a folder for good, forgetting the paper if
        it is filed nowhere else."""
        with self._connect() as db:
            _execute_one(
                db, 'DELETE FROM placements WHERE id = ?', placement_id)
            self._prune_orphans(db)

    # Trash.

    def trash(self, kind: str, item_id: int) -> None:
        """Moves a project, or a paper out of a folder, to the trash.

        Args:
            kind: Either 'project' or 'placement'.
            item_id: Identifier of the project or placement.
        """
        with self._connect() as db:
            _execute_one(db, f'UPDATE {_trashable_table(kind)}'
                         ' SET deleted_at = ? WHERE id = ?', _now(), item_id)

    def restore(self, kind: str, item_id: int) -> None:
        """Takes a project or a placement out of the trash."""
        with self._connect() as db:
            _execute_one(db, f'UPDATE {_trashable_table(kind)}'
                         ' SET deleted_at = NULL WHERE id = ?', item_id)

    def list_trash(self) -> dict[str, list[dict[str, Any]]]:
        """Returns the projects, and the papers taken out of a folder of a
        project that is not itself in the trash, most recent first."""
        with self._connect() as db:
            projects = [dict(row) for row in db.execute("""
                SELECT p.id, p.name, p.deleted_at,
                       (SELECT COUNT(DISTINCT pl.paper_id) FROM folders f
                        JOIN placements pl ON pl.folder_id = f.id
                        WHERE f.project_id = p.id
                        AND pl.deleted_at IS NULL) AS paper_count
                FROM projects p WHERE p.deleted_at IS NOT NULL
                ORDER BY p.deleted_at DESC""")]
            rows = db.execute("""
                SELECT pl.id, pl.deleted_at, p.citekey, p.entry_type,
                       p.fields, f.name AS folder, pr.name AS project
                FROM placements pl
                JOIN papers p ON p.id = pl.paper_id
                JOIN folders f ON f.id = pl.folder_id
                JOIN projects pr ON pr.id = f.project_id
                WHERE pl.deleted_at IS NOT NULL AND pr.deleted_at IS NULL
                ORDER BY pl.deleted_at DESC""").fetchall()
        papers = [{
            **_entry(row).summary(), 'id': row['id'], 'folder': row['folder'],
            'project': row['project'], 'deleted_at': row['deleted_at'],
        } for row in rows]
        return {'projects': projects, 'papers': papers}

    def empty_trash(self) -> None:
        """Deletes everything in the trash for good."""
        self._empty_trash('0 days')

    def _empty_trash(self, age: str) -> None:
        """Deletes for good what went to the trash before `age`, such as
        '-30 days', ago."""
        with self._connect() as db:
            limit = db.execute(
                "SELECT strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now', ?)",
                (age,)).fetchone()[0]
            for table in ('projects', 'placements'):
                db.execute(f'DELETE FROM {table} WHERE deleted_at <= ?',
                           (limit,))
            self._prune_orphans(db)
        self._prune_attachments()

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

    def create_annotation(self, placement_id: int, annotation: dict[str, Any],
                          log_comment: bool = True) -> dict:
        """Adds a highlight or a note to a placement.

        Args:
            placement_id: The placement being annotated.
            annotation: Values for 'kind', 'page', 'color', 'geometry' and
                optionally 'quote' and 'body'.
            log_comment: Whether a comment in 'body' is also added to the
                journal, as update_annotation does.
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
            created = self._get_annotation(db, annotation_id)
        if log_comment and created['body'].strip():
            self._log_comment(placement_id, created)
        return created

    def update_annotation(
            self, annotation_id: int, changes: dict[str, Any]) -> dict:
        """Changes the color, geometry or body of an annotation.

        The first comment written on an annotation is also added to the
        journal, as a reading note on the paper.
        """
        if 'geometry' in changes:
            changes = {**changes, 'geometry': json.dumps(changes['geometry'])}
        assignments = ', '.join(f'{name} = ?' for name in changes)
        with self._connect() as db:
            before = _fetch_one(
                db, 'SELECT placement_id, body FROM annotations WHERE id = ?',
                annotation_id)
            if changes:
                db.execute(
                    f'UPDATE annotations SET {assignments} WHERE id = ?',
                    (*changes.values(), annotation_id))
            updated = self._get_annotation(db, annotation_id)
        if not before['body'].strip() and updated['body'].strip():
            self._log_comment(before['placement_id'], updated)
        return updated

    def delete_annotation(self, annotation_id: int) -> None:
        with self._connect() as db:
            _execute_one(
                db, 'DELETE FROM annotations WHERE id = ?', annotation_id)

    # Journal: dated notes on the progress of a project.

    def list_journal(self, project_id: int,
                     placement_id: int | None = None) -> list[dict[str, Any]]:
        """Returns the journal entries of a project, newest first.

        Args:
            project_id: The project.
            placement_id: If given, only the reading notes on this paper, as
                filed in one folder.

        Returns:
            The entries; `paper` describes the paper an entry is about, if
            any: its placement and folder, citation key, title, and whether
            it is in the trash.
        """
        with self._connect() as db:
            _fetch_one(db, 'SELECT id FROM projects WHERE id = ?', project_id)
            rows = db.execute("""
                SELECT e.id, e.body, e.category, e.author, e.created_at,
                       e.updated_at, e.placement_id, pl.folder_id,
                       pl.deleted_at, p.citekey, p.entry_type, p.fields
                FROM journal_entries e
                LEFT JOIN placements pl ON pl.id = e.placement_id
                LEFT JOIN papers p ON p.id = pl.paper_id
                WHERE e.project_id = ? AND (? IS NULL OR e.placement_id = ?)
                ORDER BY e.created_at DESC, e.id DESC""",
                (project_id, placement_id, placement_id)).fetchall()
            entries = [_journal_entry(row) for row in rows]
            images = {}
            for row in db.execute(
                    'SELECT i.id, i.entry_id, i.extension FROM journal_images i'
                    ' JOIN journal_entries e ON e.id = i.entry_id'
                    ' WHERE e.project_id = ? ORDER BY i.id', (project_id,)):
                images.setdefault(row['entry_id'], []).append(
                    {'id': row['id'], 'extension': row['extension']})
            files = {}
            for row in db.execute(
                    'SELECT f.id, f.entry_id, f.name, f.size'
                    ' FROM journal_files f'
                    ' JOIN journal_entries e ON e.id = f.entry_id'
                    ' WHERE e.project_id = ? ORDER BY f.id', (project_id,)):
                files.setdefault(row['entry_id'], []).append(
                    {'id': row['id'], 'name': row['name'], 'size': row['size']})
        return [{**entry, 'images': images.get(entry['id'], []),
                 'files': files.get(entry['id'], [])} for entry in entries]

    def add_journal_entry(self, project_id: int, body: str, author: str = '',
                          created_at: str | None = None, category: str = '',
                          placement_id: int | None = None) -> dict[str, Any]:
        """Adds an entry, dated now unless `created_at` is given.

        Args:
            project_id: The project the entry is about.
            body: The text of the entry.
            author: Name of the AI assistant writing it, if any.
            created_at: ISO 8601 date, when restoring an older entry.
            category: Kind of entry, such as 'idea' or 'result', or ''.
            placement_id: The paper, as filed in a folder of the project,
                that the entry is a reading note on, if any.
        """
        with self._connect() as db:
            _fetch_one(db, 'SELECT id FROM projects WHERE id = ?', project_id)
            if placement_id is not None:
                _fetch_one(db, 'SELECT pl.id FROM placements pl'
                           ' JOIN folders f ON f.id = pl.folder_id'
                           ' WHERE pl.id = ? AND f.project_id = ?',
                           placement_id, project_id)
            entry_id = _write(
                db, 'INSERT INTO journal_entries (project_id, body, category,'
                ' author, created_at, placement_id) VALUES (?, ?, ?, ?, ?, ?)',
                project_id, body, category, author, created_at or _now(),
                placement_id)
        return self._journal_entry(entry_id)

    def add_reading_note(self, placement_id: int, body: str,
                         author: str = '') -> dict[str, Any]:
        """Adds a reading note on a paper to the journal of its project."""
        with self._connect() as db:
            project_id = _fetch_one(
                db, 'SELECT f.project_id FROM placements pl'
                ' JOIN folders f ON f.id = pl.folder_id WHERE pl.id = ?',
                placement_id)['project_id']
        return self.add_journal_entry(project_id, body, author,
                                      category='reading',
                                      placement_id=placement_id)

    def update_journal_entry(self, entry_id: int, body: str,
                             category: str) -> dict[str, Any]:
        """Replaces the text and category of an entry; its date stays, and
        it is marked as edited."""
        with self._connect() as db:
            _execute_one(db, 'UPDATE journal_entries SET body = ?,'
                         ' category = ?, updated_at = ? WHERE id = ?',
                         body, category, _now(), entry_id)
        return self._journal_entry(entry_id)

    def delete_journal_entry(self, entry_id: int) -> None:
        with self._connect() as db:
            _execute_one(
                db, 'DELETE FROM journal_entries WHERE id = ?', entry_id)
        self._prune_attachments()

    def add_journal_image(self, entry_id: int, data: bytes) -> dict[str, Any]:
        """Attaches an image to a journal entry.

        Raises:
            InvalidImageError: `data` is not a supported image.
        """
        extension = image_extension(data)
        if not extension:
            raise InvalidImageError
        with self._connect() as db:
            _fetch_one(
                db, 'SELECT id FROM journal_entries WHERE id = ?', entry_id)
            image_id = _write(
                db, 'INSERT INTO journal_images (entry_id, extension)'
                ' VALUES (?, ?)', entry_id, extension)
        self._image_dir.joinpath(f'{image_id}{extension}').write_bytes(data)
        return {'id': image_id, 'extension': extension}

    def image_path(self, image_id: int) -> pathlib.Path:
        """Where a journal image is stored."""
        with self._connect() as db:
            image = _fetch_one(
                db, 'SELECT extension FROM journal_images WHERE id = ?',
                image_id)
        return self._image_dir / f'{image_id}{image["extension"]}'

    def delete_journal_image(self, image_id: int) -> None:
        with self._connect() as db:
            _execute_one(
                db, 'DELETE FROM journal_images WHERE id = ?', image_id)
        self._prune_attachments()

    def add_journal_file(self, entry_id: int, name: str,
                         source: BinaryIO) -> dict[str, Any]:
        """Attaches a file of any kind, such as a dataset or a script, to a
        journal entry. It is kept as it is now: a later version goes in a
        later entry.

        Args:
            entry_id: The journal entry.
            name: The file name, without directories.
            source: The content, read to its end.
        """
        name = pathlib.PurePosixPath(name.replace('\\', '/')).name.strip()
        with self._connect() as db:
            _fetch_one(
                db, 'SELECT id FROM journal_entries WHERE id = ?', entry_id)
            file_id = _write(
                db, 'INSERT INTO journal_files (entry_id, name) VALUES (?, ?)',
                entry_id, name[:255] or 'file')
        path = self._file_dir / str(file_id)
        with path.open('wb') as target:
            shutil.copyfileobj(source, target)
        with self._connect() as db:
            _write(db, 'UPDATE journal_files SET size = ? WHERE id = ?',
                   path.stat().st_size, file_id)
            return dict(_fetch_one(
                db, 'SELECT id, name, size FROM journal_files WHERE id = ?',
                file_id))

    def journal_file(self, file_id: int) -> tuple[pathlib.Path, str]:
        """Where an attached file is stored, and its name."""
        with self._connect() as db:
            file = _fetch_one(
                db, 'SELECT name FROM journal_files WHERE id = ?', file_id)
        return self._file_dir / str(file_id), file['name']

    def delete_journal_file(self, file_id: int) -> None:
        with self._connect() as db:
            _execute_one(db, 'DELETE FROM journal_files WHERE id = ?', file_id)
        self._prune_attachments()

    # To-do list.

    def list_todos(self, project_id: int) -> list[dict[str, Any]]:
        """Returns the to-dos of a project: open ones first, by priority,
        then by deadline, then oldest first; done ones last."""
        with self._connect() as db:
            _fetch_one(db, 'SELECT id FROM projects WHERE id = ?', project_id)
            return [dict(row) for row in db.execute(f"""
                SELECT {_TODO_COLUMNS} FROM todos WHERE project_id = ?
                ORDER BY done_at IS NOT NULL, done_at DESC,
                         CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1
                                       WHEN 'low' THEN 2 ELSE 3 END,
                         due_date IS NULL, due_date, id""", (project_id,))]

    def add_todo(self, project_id: int, text: str, author: str = '',
                 created_at: str | None = None, done_at: str | None = None,
                 due_date: str | None = None,
                 priority: str = '') -> dict[str, Any]:
        """Adds a to-do, dated now unless restoring an older one.

        Args:
            project_id: The project.
            text: What is to be done.
            author: Name of the AI assistant adding it, if any.
            created_at: ISO 8601 date, when restoring an older to-do.
            done_at: When it was done, when restoring a done to-do.
            due_date: Its deadline, as YYYY-MM-DD, if any.
            priority: 'high', 'medium', 'low', or '' for none.
        """
        with self._connect() as db:
            _fetch_one(db, 'SELECT id FROM projects WHERE id = ?', project_id)
            todo_id = _write(
                db, 'INSERT INTO todos (project_id, text, author, created_at,'
                ' done_at, due_date, priority) VALUES (?, ?, ?, ?, ?, ?, ?)',
                project_id, text, author, created_at or _now(), done_at,
                due_date, priority)
        return self._todo(todo_id)

    def update_todo(self, todo_id: int, **changes: Any) -> dict[str, Any]:
        """Changes a to-do.

        Args:
            todo_id: The to-do.
            **changes: Its new `text`, `due_date` (None removes it) or
                `priority` (see add_todo), or `done`: True marks it done
                now, False open again.
        """
        if 'done' in changes:
            changes['done_at'] = _now() if changes.pop('done') else None
        if not set(changes) <= {'text', 'due_date', 'priority', 'done_at'}:
            raise ValueError(f'Unknown to-do fields: {set(changes)}')
        with self._connect() as db:
            _fetch_one(db, 'SELECT id FROM todos WHERE id = ?', todo_id)
            for name, value in changes.items():
                db.execute(f'UPDATE todos SET {name} = ? WHERE id = ?',
                           (value, todo_id))
        return self._todo(todo_id)

    def delete_todo(self, todo_id: int) -> None:
        with self._connect() as db:
            _execute_one(db, 'DELETE FROM todos WHERE id = ?', todo_id)

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

    def _prune_attachments(self) -> None:
        """Deletes the images and files whose journal entry is gone."""
        with self._connect() as db:
            kept = {self._image_dir / f'{row["id"]}{row["extension"]}'
                    for row in db.execute(
                        'SELECT id, extension FROM journal_images')}
            kept |= {self._file_dir / str(row['id'])
                     for row in db.execute('SELECT id FROM journal_files')}
        for path in [*self._image_dir.iterdir(), *self._file_dir.iterdir()]:
            if path not in kept:
                path.unlink()

    def _journal_entry(self, entry_id: int) -> dict[str, Any]:
        with self._connect() as db:
            project_id = _fetch_one(
                db, 'SELECT project_id FROM journal_entries WHERE id = ?',
                entry_id)['project_id']
        return next(entry for entry in self.list_journal(project_id)
                    if entry['id'] == entry_id)

    def _todo(self, todo_id: int) -> dict[str, Any]:
        with self._connect() as db:
            return dict(_fetch_one(
                db, f'SELECT {_TODO_COLUMNS} FROM todos WHERE id = ?', todo_id))

    def _log_comment(self, placement_id: int, annotation: dict) -> None:
        """Adds the comment written on a highlight or sticky note to the
        journal, with the highlighted passage and the page."""
        quote = annotation['quote'].strip()
        lines = [f'> {quote}', ''] if quote else []
        lines += [annotation['body'].strip(), '', f'*p. {annotation["page"]}*']
        self.add_reading_note(placement_id, '\n'.join(lines))

    def _placement_summary(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            **_entry(row).summary(),
            'id': row['placement_id'],
            'paper_id': row['paper_id'],
            'has_pdf': self.pdf_path(row['paper_id']).exists(),
            'annotation_count': row['annotation_count'],
            'note_count': row['note_count'],
            'added_by': row['added_by'],
        }

    def _get_annotation(
            self, db: sqlite3.Connection, annotation_id: int) -> dict:
        return _annotation(_fetch_one(
            db, f'SELECT {", ".join(_ANNOTATION_COLUMNS)} FROM annotations'
            ' WHERE id = ?', annotation_id))


def image_extension(data: bytes) -> str | None:
    """The extension of a PNG, JPEG, GIF or WebP image, or None."""
    extension = next((ext for signature, ext in _IMAGE_SIGNATURES
                      if data.startswith(signature)), None)
    if extension == '.webp' and data[8:12] != b'WEBP':
        return None
    return extension


def _journal_entry(row: sqlite3.Row) -> dict[str, Any]:
    entry = {name: row[name] for name in (
        'id', 'body', 'category', 'author', 'created_at', 'updated_at')}
    entry['paper'] = None if row['placement_id'] is None else {
        'placement_id': row['placement_id'], 'folder_id': row['folder_id'],
        'citekey': row['citekey'], 'title': _entry(row).summary()['title'],
        'trashed': row['deleted_at'] is not None,
    }
    return entry


def _now() -> str:
    """The current UTC time in ISO 8601, to the second."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec='seconds')


def _container_table(kind: str) -> str:
    tables = {'project': 'projects', 'folder': 'folders'}
    if kind not in tables:
        raise ValueError(f'Unknown container kind: {kind!r}')
    return tables[kind]


def _trashable_table(kind: str) -> str:
    tables = {'project': 'projects', 'placement': 'placements'}
    if kind not in tables:
        raise ValueError(f'Unknown kind of trashed item: {kind!r}')
    return tables[kind]


def _write_project_name(db: sqlite3.Connection, sql: str,
                        *params: Any) -> int:
    """Writes the name of a project, telling apart a conflict with a
    project in the trash."""
    try:
        return _write(db, sql, *params)
    except ConflictError:
        if db.execute('SELECT 1 FROM projects WHERE name = ?'
                      ' AND deleted_at IS NOT NULL', params[:1]).fetchone():
            raise NameInTrashError from None
        raise


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

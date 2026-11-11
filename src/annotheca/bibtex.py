"""BibTeX entries: parsing, formatting, citation keys and identifiers."""

import dataclasses
import re
import unicodedata
from typing import Any

_DOI_RE = re.compile(r'\b(10\.\d{4,9}/[^\s"<>{}]+)', re.IGNORECASE)
_ARXIV_NEW_RE = re.compile(r'\b(\d{4}\.\d{4,5})(?:v\d+)?\b')
_ARXIV_OLD_RE = re.compile(
    r'arxiv(?:\.org/(?:abs|pdf)/|:)\s*([a-z-]+(?:\.[a-z]{2})?/\d{7})',
    re.IGNORECASE)
_ARXIV_DOI_PREFIX = '10.48550/arxiv.'
_ENTRY_RE = re.compile(r'@\s*([a-zA-Z]+)\s*\{')
_FIELD_NAME_RE = re.compile(r'\s*([^\s=,{}]+)\s*=\s*')
_BARE_VALUE_RE = re.compile(r'[^\s,#}]*')
_CONCATENATION_RE = re.compile(r'\s*#\s*')
_SEPARATOR_RE = re.compile(r'\s*,')
_IGNORED_TYPES = frozenset(('comment', 'preamble', 'string'))
_LATEX_ACCENT_RE = re.compile(
    r'\\([`\'^"~]|c(?=[\s{]))\s*\{?([a-zA-Z])\}?')
_COMBINING_ACCENTS = {
    '`': '\u0300', "'": '\u0301', '^': '\u0302', '~': '\u0303',
    '"': '\u0308', 'c': '\u0327'}

# Fields printed first, in this order; the others follow alphabetically.
_FIELD_ORDER = ('author', 'title', 'journal', 'booktitle', 'year')
# Fields naming where a paper was published, by preference.
_VENUE_FIELDS = (
    'journal', 'booktitle', 'publisher', 'howpublished', 'archiveprefix')
_TITLE_STOPWORDS = frozenset(
    ('a', 'an', 'the', 'on', 'of', 'for', 'in', 'to', 'and', 'with'))


@dataclasses.dataclass
class Entry:
    """A single BibTeX entry.

    Attributes:
        entry_type: Lowercase entry type, e.g. 'article'.
        citekey: The citation key.
        fields: Field values keyed by lowercase field name.
    """
    entry_type: str
    citekey: str
    fields: dict[str, str]

    @property
    def doi(self) -> str | None:
        """The normalized DOI, if the entry has one."""
        return find_doi(self.fields.get('doi', ''))

    @property
    def arxiv_id(self) -> str | None:
        """The arXiv identifier, from the DOI, eprint, URL or journal."""
        doi = self.doi
        if doi and doi.startswith(_ARXIV_DOI_PREFIX):
            return doi.removeprefix(_ARXIV_DOI_PREFIX)
        sources = ('eprint', 'url', 'journal', 'note')
        return find_arxiv_id(
            ' '.join(self.fields.get(name, '') for name in sources))

    def summary(self) -> dict[str, Any]:
        """The citation key, title, authors, year and venue, as plain text,
        and a link to the paper's page ('' if unknown)."""
        venue = next((self.fields[name] for name in _VENUE_FIELDS
                      if name in self.fields), '')
        return {
            'citekey': self.citekey,
            'title': plain(self.fields.get('title', self.citekey)),
            'authors': split_authors(self.fields.get('author', '')),
            'year': self.fields.get('year', ''),
            'venue': plain(venue),
            'link': self.link,
        }

    @property
    def link(self) -> str:
        """The paper's page: its URL, else its DOI or arXiv page, else ''."""
        if url := self.fields.get('url', '').strip():
            return url
        if self.doi:
            return f'https://doi.org/{self.doi}'
        if self.arxiv_id:
            return f'https://arxiv.org/abs/{self.arxiv_id}'
        return ''

    @property
    def title_key(self) -> str | None:
        """The title as lowercase alphanumerics, used to spot duplicates."""
        title = plain(self.fields.get('title', '')).lower()
        return re.sub(r'[^a-z0-9]', '', title) or None


def find_doi(text: str) -> str | None:
    """Returns the first DOI found in `text`, lowercased, or None."""
    match = _DOI_RE.search(text)
    return match.group(1).rstrip('.,;)]').lower() if match else None


def find_arxiv_id(text: str) -> str | None:
    """Returns the first arXiv identifier found in `text`, or None."""
    match = _ARXIV_NEW_RE.search(text) or _ARXIV_OLD_RE.search(text)
    return match.group(1) if match else None


def parse(text: str) -> list[Entry]:
    """Parses every entry of a BibTeX string.

    Macros are kept verbatim rather than expanded, e.g. `month = jun` gives
    'jun'. Entries without a citation key are skipped.
    """
    entries = []
    position = 0
    while match := _ENTRY_RE.search(text, position):
        end = _closing(text, match.end(), '}')
        citekey, comma, body = text[match.end():end].partition(',')
        entry_type = match.group(1).lower()
        if comma and citekey.strip() and entry_type not in _IGNORED_TYPES:
            entries.append(Entry(entry_type, citekey.strip(), _fields(body)))
        position = end + 1
    return entries


def format_entry(entry: Entry) -> str:
    """Formats an entry as BibTeX source."""
    rank = {name: i for i, name in enumerate(_FIELD_ORDER)}
    names = sorted(entry.fields, key=lambda n: (rank.get(n, len(rank)), n))
    lines = [f'@{entry.entry_type}{{{entry.citekey},']
    lines += [f'  {name} = {{{entry.fields[name]}}},' for name in names]
    lines.append('}')
    return '\n'.join(lines)


def make_citekey(fields: dict[str, str]) -> str:
    """Builds a Google Scholar style key such as 'vaswani2017attention'."""
    authors = split_authors(fields.get('author', ''))
    last_name = ''
    if authors:
        first = authors[0]
        last_name = first.split(',')[0] if ',' in first else first.split()[-1]
    title_words = re.findall(
        r'[a-z0-9]+', _ascii(plain(fields.get('title', ''))))
    word = next((w for w in title_words if w not in _TITLE_STOPWORDS), '')
    key = _ascii(last_name) + fields.get('year', '').strip() + word
    return re.sub(r'[^a-z0-9]', '', key) or 'ref'


def split_authors(author_field: str) -> list[str]:
    """Splits a BibTeX author field into plain author names."""
    names = re.split(r'\s+and\s+', plain(author_field))
    return [name.strip() for name in names if name.strip()]


def plain(text: str) -> str:
    """Strips the LaTeX braces, accents and escapes common in fields."""
    text = _LATEX_ACCENT_RE.sub(
        lambda m: m.group(2) + _COMBINING_ACCENTS[m.group(1)], text)
    text = unicodedata.normalize('NFC', re.sub(r'\\([&%$#_])', r'\1', text))
    return ' '.join(text.replace('{', '').replace('}', '').split())


def _fields(text: str) -> dict[str, str]:
    """Parses the `name = value` pairs of an entry body."""
    fields = {}
    position = 0
    while match := _FIELD_NAME_RE.match(text, position):
        parts = []
        position = match.end()
        while True:
            if text.startswith(('{', '"'), position):
                end = _closing(text, position + 1, '}' if text[position] == '{'
                               else '"')
                parts.append(text[position + 1:end])
                position = end + 1
            else:
                bare = _BARE_VALUE_RE.match(text, position)
                parts.append(bare.group())
                position = bare.end()
            concatenation = _CONCATENATION_RE.match(text, position)
            if not concatenation:
                break
            position = concatenation.end()
        fields[match.group(1).lower()] = ' '.join(''.join(parts).split())
        if separator := _SEPARATOR_RE.match(text, position):
            position = separator.end()
    return fields


def _closing(text: str, start: int, closer: str) -> int:
    """Index of the first `closer` outside braces from `start`, or the end."""
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == closer and depth == 0:
            return index
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
    return len(text)


def _ascii(text: str) -> str:
    decomposed = unicodedata.normalize('NFKD', text)
    return decomposed.encode('ascii', 'ignore').decode().lower()

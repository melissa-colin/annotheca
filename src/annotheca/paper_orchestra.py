"""Raw materials for PaperOrchestra, which drafts a paper from them.

PaperOrchestra (https://github.com/google-research/paper-orchestra) turns an
idea, an experimental log and figures into a LaTeX manuscript. The export
gives it a project as a zipped `raw_materials` directory:

- `idea_sparse.md`: the headings of the idea, for the user to fill in, the
  journal entries filed as ideas, then the papers of the project, folder by
  folder, with the user's notes;
- `experimental_log.md`: the journal, oldest entry first;
- `figures/`: the journal images in a format it accepts, with their captions
  in `info.json`;
- `references.bib`: the BibTeX of the project;
- `README.md`: how to run PaperOrchestra on the directory.
"""

import datetime
import io
import json
import re
import zipfile

from annotheca import library as library_lib

_ROOT = 'raw_materials'
_REPOSITORY = 'https://github.com/google-research/paper-orchestra'
# Image formats PaperOrchestra includes in the LaTeX manuscript.
_FIGURE_EXTENSIONS = ('.png', '.jpg')
_CAPTION_LENGTH = 200
_LISTED_AUTHORS = 3
_MARKUP_RE = re.compile(r'[#*_`>]+')

_IDEA_HEADER = """\
# {name}

<!-- Describe the idea of the paper under the headings below before running
PaperOrchestra; an AI assistant can draft them from the journal. -->

## Problem Statement


## Core Hypothesis


## Proposed Methodology

{ideas}
## Key References

Papers collected in Annotheca, with the author's notes. Their BibTeX is in
references.bib.
"""

_README = """\
# Raw materials for PaperOrchestra

Exported from Annotheca on {date}, for the project "{name}".

PaperOrchestra drafts a LaTeX paper from an idea, an experimental log and
figures, with a team of AI agents: outline, literature review, section
writing, refinement and plots.

1. Describe the idea of the paper in `idea_sparse.md`.
2. Install PaperOrchestra and set up its API keys (an LLM provider and
   Semantic Scholar): {repository}
3. From the PaperOrchestra directory, run:

       python paper_writing_cli.py \\
         --raw_materials_dir /path/to/raw_materials \\
         --latex_template_dir templates/cvpr2025 \\
         --output_dir /path/to/output

`experimental_log.md` is the project journal and `figures/` holds its
images. PaperOrchestra searches the literature itself and writes its own
bibliography: check the papers it cites by pasting them into Annotheca.
`references.bib` keeps the papers you collected.
"""


def export_project(library: library_lib.Library,
                   project_id: int) -> tuple[str, bytes]:
    """Returns the name of a project and its raw materials, zipped."""
    project = library.get_project(project_id)
    _, bib = library.export_bibtex(project_id)
    journal = list(reversed(library.list_journal(project_id)))
    figures = []
    log = ['# Experimental log', '']
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for entry in journal:
            log += [f'## {_heading(entry)}', '', entry['body'], '']
            if entry['files']:
                names = ', '.join(
                    f'`{file["name"]}`' for file in entry['files'])
                log += [f'Attached files (in Annotheca): {names}', '']
            for image in entry['images']:
                if image['extension'] not in _FIGURE_EXTENSIONS:
                    continue
                name = f'journal_{image["id"]}{image["extension"]}'
                archive.write(library.image_path(image['id']),
                              f'{_ROOT}/figures/{name}')
                figures.append({'name': name, 'caption': _caption(entry)})
                log += [f'Figure: `figures/{name}`', '']
        files = {
            'idea_sparse.md': _idea(project, journal),
            'experimental_log.md': '\n'.join(log),
            'figures/info.json': json.dumps(figures, indent=2),
            'references.bib': bib,
            'README.md': _README.format(
                date=datetime.date.today().isoformat(), name=project['name'],
                repository=_REPOSITORY),
        }
        for name, content in files.items():
            archive.writestr(f'{_ROOT}/{name}', content)
    return project['name'], buffer.getvalue()


def _heading(entry: dict) -> str:
    """The date of a journal entry, with its category and author if any."""
    heading = entry['created_at'][:16].replace('T', ' ')
    if entry['category']:
        heading += f' · {entry["category"].capitalize()}'
    if entry['author']:
        heading += f' ({entry["author"]})'
    return heading


def _idea(project: dict, journal: list[dict]) -> str:
    ideas = ''.join(
        f'\n### {_heading(entry)}\n\n{entry["body"].strip()}\n'
        for entry in journal if entry['category'] == 'idea')
    if ideas:
        ideas = f'\n## Ideas From the Journal\n{ideas}\n'
    lines = [_IDEA_HEADER.format(name=project['name'], ideas=ideas)]
    for folder in project['folders']:
        if not folder['placements']:
            continue
        lines += [f'### {folder["name"]}', '']
        for placement in folder['placements']:
            authors = placement['authors']
            if len(authors) > _LISTED_AUTHORS:
                authors = [authors[0], 'et al.']
            about = ', '.join(filter(None, [
                '; '.join(authors), placement['year']]))
            lines.append(f'- **{placement["title"]}** ({about})'
                         f' [{placement["citekey"]}]')
            lines += [f'  {line}'.rstrip()
                      for line in placement['notes'].strip().splitlines()]
        lines.append('')
    return '\n'.join(lines)


def _caption(entry: dict) -> str:
    """Describes an image by the start of the journal entry it belongs to."""
    text = ' '.join(_MARKUP_RE.sub('', entry['body']).split())
    if len(text) > _CAPTION_LENGTH:
        text = text[:_CAPTION_LENGTH].rsplit(' ', 1)[0] + '...'
    date = entry['created_at'][:10]
    return f'From the journal entry of {date}: {text}' if text else date

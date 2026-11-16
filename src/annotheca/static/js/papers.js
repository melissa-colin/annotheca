/**
 * @fileoverview Folder view: the papers filed in one folder of a project.
 */

import {api} from './api.js';
import {t} from './i18n.js';
import {readingNotes} from './notes.js';
import {ask, chooseFiles, h, icon, report, toast} from './ui.js';
import {TRASH_DAYS} from './trash.js';
import {PaperViewer} from './viewer.js';

/** The folder shown, set by renderFolder. */
const view = {
  /** @type {?Object} The project, with its folders and placements. */
  project: null,
  /** @type {?Object} */
  folder: null,
  /** @type {function(): !Promise} */
  reload: async () => {},
};
const state = {
  filter: '',
  /** @type {!Set<number>} Papers whose PDF is being looked for. */
  searching: new Set(),
  /** @type {!Set<number>} Placements whose reading notes are unfolded. */
  openNotes: new Set(),
};

/**
 * Shows the papers of a folder.
 * @param {!HTMLElement} main
 * @param {!Object} project The project, with its folders and placements.
 * @param {!Object} folder One of its folders.
 * @param {function(): !Promise} reload Reloads the project and this view.
 */
export function renderFolder(main, project, folder, reload) {
  Object.assign(view, {project, folder, reload});
  const filter = h('input.input.filter', {
    type: 'search', placeholder: t('filter'), value: state.filter,
    oninput: () => {
      state.filter = filter.value;
      renderPapers();
    },
  });
  main.replaceChildren(
      h('header.view-header', {}, h('h1', {}, folder.name)),
      renderPasteBox(),
      h('div.list-toolbar', {}, h('span.muted', {id: 'paper-count'}), filter),
      h('div.paper-list', {id: 'papers'}));
  renderPapers();
}

/**
 * Applies a change to every placement of a paper in the project.
 * @param {number} paperId
 * @param {function(!Object)} change
 */
function updatePaper(paperId, change) {
  for (const folder of view.project.folders) {
    folder.placements.filter((p) => p.paper_id === paperId).forEach(change);
  }
}

/**
 * Files pasted references in the folder, then looks for their PDFs.
 * @param {!HTMLTextAreaElement} textarea
 * @param {!HTMLButtonElement} button
 */
async function addReferences(textarea, button) {
  const text = textarea.value.trim();
  if (!text) return;
  button.disabled = true;
  try {
    const result = await api.addPapers(view.folder.id, {text});
    const {added, already_there: alreadyThere} = result;
    toast([
      added && t('paste.added', {n: added}),
      alreadyThere && t('paste.alreadyThere', {n: alreadyThere}),
    ].filter(Boolean).join(' '));
    await view.reload();
    await findPdfs(result.paper_ids);
  } catch (error) {
    button.disabled = false;
    report(error);
  }
}

/**
 * Looks online, one after the other, for the PDFs that are still missing.
 * @param {!Array<number>} paperIds
 */
async function findPdfs(paperIds) {
  const placements = view.folder.placements;
  const missing = paperIds.filter((id) =>
    placements.some((p) => p.paper_id === id && !p.has_pdf));
  missing.forEach((id) => state.searching.add(id));
  renderPapers();
  for (const paperId of missing) {
    try {
      const {found} = await api.fetchPdf(paperId);
      updatePaper(paperId, (p) => p.has_pdf = found);
      if (!found) {
        const {title} = placements.find((p) => p.paper_id === paperId);
        toast(t('pdf.notFound', {title}));
      }
    } catch (error) {
      report(error);
    }
    state.searching.delete(paperId);
    renderPapers();
  }
}

/**
 * Uploads a PDF for a paper.
 * @param {!Object} placement
 * @param {!File} file
 */
async function uploadPdf(placement, file) {
  try {
    await api.uploadPdf(placement.paper_id, file);
    updatePaper(placement.paper_id, (p) => p.has_pdf = true);
    renderPapers();
  } catch (error) {
    report(error);
  }
}

/** @param {!Object} placement */
function choosePdf(placement) {
  chooseFiles('application/pdf', ([file]) => uploadPdf(placement, file));
}

/** @param {!Object} placement Unfolds or folds its reading notes. */
function toggleNotes(placement) {
  if (!state.openNotes.delete(placement.id)) {
    state.openNotes.add(placement.id);
  }
  renderPapers();
  document.querySelector(`[data-placement="${placement.id}"] .notes`)?.focus();
}

/**
 * Opens a paper of the folder shown: its reader if it has a PDF, else its
 * card, scrolled to and highlighted.
 * @param {number} placementId
 */
export function openPaper(placementId) {
  const placement = view.folder.placements.find((p) => p.id === placementId);
  if (!placement) return;
  if (placement.has_pdf) {
    read(placement);
    return;
  }
  state.openNotes.add(placement.id);
  renderPapers();
  const card = document.querySelector(`[data-placement="${placementId}"]`);
  card.scrollIntoView({block: 'center'});
  card.classList.add('flash');
}

/**
 * Files a paper in another folder of the project.
 * @param {!Object} placement
 * @param {number} folderId
 */
async function fileIn(placement, folderId) {
  try {
    await api.addPapers(folderId, {paper_id: placement.paper_id});
    const folder = view.project.folders.find((f) => f.id === folderId);
    toast(t('paper.fileInDone', {folder: folder.name}));
    await view.reload();
  } catch (error) {
    report(error);
  }
}

/** @param {!Object} placement */
async function removePlacement(placement) {
  const confirmed = await ask({
    title: t('paper.remove'),
    message: t('paper.removeConfirm', {
      title: placement.title, folder: view.folder.name, days: TRASH_DAYS,
    }),
    action: t('trash.move'),
    danger: true,
  });
  if (!confirmed) return;
  try {
    await api.removePlacement(placement.id);
    toast(t('trash.moved', {name: placement.title}));
    await view.reload();
  } catch (error) {
    report(error);
  }
}

/** @param {!Object} placement */
async function copyCite(placement) {
  const cite = `\\cite{${placement.citekey}}`;
  await navigator.clipboard.writeText(cite);
  toast(t('paper.copied', {cite}));
}

/** @param {!Object} placement */
function read(placement) {
  const viewer = new PaperViewer(document.getElementById('viewer'), {
    placement,
    projectId: view.project.id,
    subtitle: `${view.project.name} · ${view.folder.name}`,
    onClose: () => {
      // Back to the folder when the reader was opened by a link.
      history.replaceState(
          null, '', `#/p/${view.project.id}/f/${view.folder.id}`);
      return view.reload();
    },
  });
  viewer.open().catch((error) => {
    viewer.close();
    report(error);
  });
}

function renderPasteBox() {
  const button = h('button.button.primary', {
    onclick: () => addReferences(textarea, button),
  }, icon('plus'), t('paste.add'));
  const textarea = h('textarea.paste', {
    rows: 3,
    placeholder: t('paste.placeholder'),
    onkeydown: (event) => {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
        addReferences(textarea, button);
      }
    },
  });
  return h('div.paste-box', {}, textarea,
      h('div.paste-actions', {},
          h('kbd', {}, t('paste.hint')), button));
}

function renderPapers() {
  const list = document.getElementById('papers');
  if (!list) return;
  const placements = view.folder.placements;
  const query = state.filter.trim().toLowerCase();
  const shown = placements.filter((p) => !query ||
      [p.title, p.citekey, p.venue, p.year, p.added_by, ...p.authors]
          .join(' ').toLowerCase().includes(query));
  document.getElementById('paper-count').textContent =
      t('papers', {n: shown.length});
  list.replaceChildren(...shown.map(paperCard));
  if (!placements.length) {
    list.append(h('p.empty-hint', {}, t('folder.empty')));
  }
}

/**
 * @param {!Array<string>} authors Names as 'Last, First' or 'First Last'.
 * @return {string} A short author line such as 'Vaswani et al.'.
 */
function shortAuthors(authors) {
  const lastNames = authors.map((name) =>
    name.includes(',') ? name.split(',')[0] : name.split(' ').at(-1));
  if (lastNames.length > 2) return `${lastNames[0]} et al.`;
  return lastNames.join(' & ');
}

/**
 * @param {!Object} placement
 * @return {!HTMLElement}
 */
function paperCard(placement) {
  const otherFolders = view.project.folders.filter((f) =>
    f.id !== view.folder.id &&
    f.placements.some((p) => p.paper_id === placement.paper_id));
  const targets = view.project.folders.filter((f) =>
    f.id !== view.folder.id && !otherFolders.includes(f));
  const open = () => placement.has_pdf ? read(placement) : choosePdf(placement);

  const card = h('article.paper', {
    dataset: {placement: placement.id},
    ondragover: (event) => {
      event.preventDefault();
      card.classList.add('dropping');
    },
    ondragleave: () => card.classList.remove('dropping'),
    ondrop: (event) => {
      event.preventDefault();
      card.classList.remove('dropping');
      const file = event.dataTransfer.files[0];
      if (file) uploadPdf(placement, file);
    },
  },
  h(`button.paper-thumb${placement.has_pdf ? '.has-pdf' : ''}`, {
    title: placement.has_pdf ? t('paper.open') : t('pdf.attach'),
    onclick: open,
  }, icon('file'), h('span', {}, placement.has_pdf ? 'PDF' : t('pdf.drop'))),
  h('div.paper-body', {},
      h('h3.paper-title', {onclick: open}, placement.title),
      h('p.paper-meta', {}, [shortAuthors(placement.authors), placement.year,
        placement.venue].filter(Boolean).join(' · ')),
      h('div.paper-tags', {},
          h('button.chip.mono', {
            title: t('paper.copy'), onclick: () => copyCite(placement),
          }, placement.citekey),
          h(`button.chip${placement.note_count ? '.accent' : ''}`, {
            title: t('notes.title'), onclick: () => toggleNotes(placement),
          }, icon('note'), t('notes'), placement.note_count > 0 &&
              h('span.category-count', {}, String(placement.note_count))),
          placement.annotation_count > 0 && h('span.chip.accent', {
            title: t('paper.annotations'),
          }, icon('highlighter'), String(placement.annotation_count)),
          placement.added_by && h('span.chip.agent', {
            title: t('paper.addedBy', {agent: placement.added_by}),
          }, icon('bot'), placement.added_by),
          otherFolders.length > 0 && h('span.chip.subtle', {}, t(
              'paper.alsoIn',
              {folders: otherFolders.map((f) => f.name).join(', ')})))),
  h('div.paper-actions', {}, paperActions(placement, open, targets)),
  state.openNotes.has(placement.id) &&
      h('div.paper-notes', {}, readingNotes(
          view.project.id, placement, () => renderPapers())));
  return card;
}

/**
 * @param {!Object} placement
 * @param {function()} open Opens the reader, or asks for the PDF.
 * @param {!Array<!Object>} targets Folders the paper can still be filed in.
 * @return {!Array<!HTMLElement>}
 */
function paperActions(placement, open, targets) {
  const actions = [];
  if (state.searching.has(placement.paper_id)) {
    actions.push(h('span.searching', {}, h('span.spinner'),
        t('pdf.searching')));
  } else if (placement.has_pdf) {
    actions.push(h('button.button.primary.small', {onclick: open},
        t('paper.open')));
  } else {
    actions.push(
        h('button.button.small', {
          onclick: () => findPdfs([placement.paper_id]),
        }, icon('search'), t('pdf.find')),
        placement.link && h('a.button.small', {
          href: placement.link, target: '_blank', rel: 'noopener',
          title: t('pdf.pageHint'),
        }, icon('external'), t('pdf.page')),
        h('button.button.small', {onclick: open},
            icon('upload'), t('pdf.attach')));
  }
  if (targets.length) {
    const select = h('select.select', {
      onchange: () => fileIn(placement, Number(select.value)),
    }, h('option', {value: '', disabled: true, selected: true},
        t('paper.fileIn')),
    targets.map((f) => h('option', {value: f.id}, f.name)));
    actions.push(select);
  }
  actions.push(h('button.icon-button.danger', {
    title: t('paper.remove'), onclick: () => removePlacement(placement),
  }, icon('trash')));
  return actions;
}

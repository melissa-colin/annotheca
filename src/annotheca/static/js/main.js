/**
 * @fileoverview Library view: projects, folders and the papers filed in them.
 */

import {api} from './api.js';
import {LANGUAGES, getLanguage, setLanguage, t, translatePage} from './i18n.js';
import {load, save} from './storage.js';
import {ask, h, icon, notesEditor, report, toast} from './ui.js';
import {PaperViewer} from './viewer.js';

const state = {
  /** @type {!Array<{id: number, name: string}>} */
  projects: [],
  /** @type {?Object} The open project, with its folders and placements. */
  project: null,
  /** @type {?number} */
  folderId: null,
  filter: '',
  /** @type {!Set<number>} Papers whose PDF is being looked for. */
  searching: new Set(),
  /** @type {!Set<number>} Placements whose notes are unfolded. */
  openNotes: new Set(),
};

/** @return {?Object} The selected folder of the open project. */
function currentFolder() {
  return state.project?.folders.find((f) => f.id === state.folderId) ?? null;
}

/**
 * Applies a change to every placement of a paper in the open project.
 * @param {number} paperId
 * @param {function(!Object)} change
 */
function updatePaper(paperId, change) {
  for (const folder of state.project.folders) {
    folder.placements.filter((p) => p.paper_id === paperId).forEach(change);
  }
}

// Loading.

/**
 * Reloads the project list and opens a project.
 * @param {?number} projectId Project to open; defaults to the first one.
 */
async function loadProjects(projectId) {
  state.projects = await api.listProjects();
  const project = state.projects.find((p) => p.id === projectId) ??
      state.projects[0];
  if (project) {
    await openProject(project.id);
  } else {
    state.project = null;
    render();
  }
}

/**
 * Loads a project and shows it, keeping the selected folder if possible.
 * @param {number} projectId
 */
async function openProject(projectId) {
  state.project = await api.getProject(projectId);
  const folders = state.project.folders;
  const remembered = load('folder');
  state.folderId = [state.folderId, remembered]
      .find((id) => folders.some((f) => f.id === id)) ?? folders[0].id;
  save('project', projectId);
  save('folder', state.folderId);
  render();
}

async function refresh() {
  await openProject(state.project.id);
}

// Actions.

async function createProject() {
  const name = await ask(
      {title: t('project.new'), value: '', action: t('create')});
  if (!name) return;
  try {
    const project = await api.createProject(name);
    state.folderId = null;
    await loadProjects(project.id);
  } catch (error) {
    report(error);
  }
}

/**
 * Renames a project or a folder.
 * @param {string} kind 'project' or 'folder'.
 * @param {{id: number, name: string}} item
 */
async function rename(kind, item) {
  const name = await ask(
      {title: t(`${kind}.rename`), value: item.name, action: t('save')});
  if (!name || name === item.name) return;
  try {
    await api.rename(kind, item.id, name);
    await loadProjects(state.project.id);
  } catch (error) {
    report(error);
  }
}

/**
 * Deletes a project or a folder after confirmation.
 * @param {string} kind 'project' or 'folder'.
 * @param {{id: number, name: string}} item
 */
async function remove(kind, item) {
  const confirmed = await ask({
    title: t(`${kind}.delete`),
    message: t(`${kind}.deleteConfirm`, {name: item.name}),
    action: t('delete'),
    danger: true,
  });
  if (!confirmed) return;
  try {
    await api.remove(kind, item.id);
    await loadProjects(kind === 'folder' ? state.project.id : null);
  } catch (error) {
    report(error);
  }
}

async function createFolder() {
  const name = await ask(
      {title: t('folder.new'), value: '', action: t('create')});
  if (!name) return;
  try {
    state.folderId = (await api.createFolder(state.project.id, name)).id;
    await refresh();
  } catch (error) {
    report(error);
  }
}

/**
 * Files pasted references in the current folder, then looks for their PDFs.
 * @param {!HTMLTextAreaElement} textarea
 * @param {!HTMLButtonElement} button
 */
async function addReferences(textarea, button) {
  const text = textarea.value.trim();
  if (!text) return;
  button.disabled = true;
  try {
    const result = await api.addPapers(state.folderId, {text});
    const {added, already_there: alreadyThere} = result;
    toast([
      added && t('paste.added', {n: added}),
      alreadyThere && t('paste.alreadyThere', {n: alreadyThere}),
    ].filter(Boolean).join(' '));
    await refresh();
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
  const placements = currentFolder().placements;
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

/**
 * Asks the user for a file.
 * @param {string} accept Accepted types, as for <input type="file">.
 * @param {function(!File)} use Called with the chosen file.
 */
function chooseFile(accept, use) {
  const input = h('input', {type: 'file', accept});
  input.addEventListener('change', () => use(input.files[0]));
  input.click();
}

/** @param {!Object} placement */
function choosePdf(placement) {
  chooseFile('application/pdf', (file) => uploadPdf(placement, file));
}

function importProject() {
  chooseFile('.annotheca', async (file) => {
    try {
      const project = await api.importBundle(file);
      toast(t('import.done', {name: project.name}));
      state.folderId = null;
      await loadProjects(project.id);
    } catch (error) {
      report(error);
    }
  });
}

/** @param {!Object} placement Unfolds or folds its general notes. */
function toggleNotes(placement) {
  if (!state.openNotes.delete(placement.id)) {
    state.openNotes.add(placement.id);
  }
  renderPapers();
  document.querySelector(`[data-placement="${placement.id}"] .notes`)?.focus();
}

/**
 * Files a paper in another folder of the project.
 * @param {!Object} placement
 * @param {number} folderId
 */
async function fileIn(placement, folderId) {
  try {
    await api.addPapers(folderId, {paper_id: placement.paper_id});
    const folder = state.project.folders.find((f) => f.id === folderId);
    toast(t('paper.fileInDone', {folder: folder.name}));
    await refresh();
  } catch (error) {
    report(error);
  }
}

/** @param {!Object} placement */
async function removePlacement(placement) {
  const confirmed = await ask({
    title: t('paper.remove'),
    message: t('paper.removeConfirm',
        {title: placement.title, folder: currentFolder().name}),
    action: t('remove'),
    danger: true,
  });
  if (!confirmed) return;
  try {
    await api.removePlacement(placement.id);
    await refresh();
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
    subtitle: `${state.project.name} · ${currentFolder().name}`,
    onClose: refresh,
  });
  viewer.open().catch((error) => {
    viewer.close();
    report(error);
  });
}

// Rendering.

function render() {
  renderProjectList();
  renderMain();
}

function renderProjectList() {
  const items = state.projects.map((project) => h(`div.project-item${
    project.id === state.project?.id ? '.active' : ''}`, {},
  h('button.project-name', {onclick: () => openProject(project.id)},
      icon('book'), h('span', {}, project.name)),
  h('button.icon-button.reveal', {
    title: t('project.rename'), onclick: () => rename('project', project),
  }, icon('pencil')),
  h('button.icon-button.reveal', {
    title: t('project.delete'), onclick: () => remove('project', project),
  }, icon('trash'))));
  document.getElementById('project-list').replaceChildren(...items);
}

function renderMain() {
  const main = document.getElementById('main');
  if (!state.project) {
    main.replaceChildren(h('div.empty-state', {},
        icon('book'),
        h('h2', {}, t('project.none')),
        h('p', {}, t('project.noneHint')),
        h('button.button.primary', {onclick: createProject},
            icon('plus'), t('project.new'))));
    return;
  }
  const filter = h('input.input.filter', {
    type: 'search', placeholder: t('filter'), value: state.filter,
    oninput: () => {
      state.filter = filter.value;
      renderPapers();
    },
  });
  main.replaceChildren(
      h('header.project-header', {},
          h('h1', {}, state.project.name),
          h('div.header-actions', {},
              h('a.button', {
                href: api.bundleUrl(state.project.id), download: '',
                title: t('share.hint'),
              }, icon('share'), t('share')),
              h('a.button', {
                href: api.exportUrl(state.project.id), download: '',
                title: t('export.hint'),
              }, icon('download'), t('export')))),
      renderTabs(),
      renderPasteBox(),
      h('div.list-toolbar', {}, h('span.muted', {id: 'paper-count'}), filter),
      h('div.paper-list', {id: 'papers'}));
  renderPapers();
}

function renderTabs() {
  const tabs = state.project.folders.map((folder) => {
    const active = folder.id === state.folderId;
    return h(`div.tab${active ? '.active' : ''}`, {},
        h('button.tab-name', {
          onclick: () => {
            state.folderId = folder.id;
            save('folder', folder.id);
            renderMain();
          },
          ondblclick: () => rename('folder', folder),
        }, folder.name, h('span.count', {}, String(folder.placements.length))),
        active && h('button.icon-button.small', {
          title: t('folder.rename'), onclick: () => rename('folder', folder),
        }, icon('pencil')),
        active && state.project.folders.length > 1 &&
            h('button.icon-button.small', {
              title: t('folder.delete'),
              onclick: () => remove('folder', folder),
            }, icon('trash')));
  });
  return h('nav.tabs', {},
      tabs,
      h('button.tab-add', {onclick: createFolder},
          icon('folderPlus'), t('folder.new')));
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
  const placements = currentFolder().placements;
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
  const otherFolders = state.project.folders.filter((f) =>
    f.id !== state.folderId &&
    f.placements.some((p) => p.paper_id === placement.paper_id));
  const targets = state.project.folders.filter((f) =>
    f.id !== state.folderId && !otherFolders.includes(f));
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
          h(`button.chip${placement.notes ? '.accent' : ''}`, {
            title: t('notes.title'), onclick: () => toggleNotes(placement),
          }, icon('note'), t('notes')),
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
      h('div.paper-notes', {}, notesEditor(placement)));
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

function renderLanguageSwitch() {
  const buttons = LANGUAGES.map((code) => h(
      `button${code === getLanguage() ? '.active' : ''}`, {
    onclick: () => {
      setLanguage(code);
      renderLanguageSwitch();
      render();
    },
  }, code.toUpperCase()));
  document.getElementById('language-switch').replaceChildren(...buttons);
}

/**
 * Reloads the open project, e.g. after an AI assistant changed it, unless
 * the user is typing or reading.
 */
function refreshIfIdle() {
  const editing = document.activeElement.matches('input, textarea') ||
      document.querySelector('.paste')?.value;
  if (state.project && !editing && document.getElementById('viewer').hidden) {
    refresh().catch(report);
  }
}

async function init() {
  translatePage();
  renderLanguageSwitch();
  const newProject = document.getElementById('new-project');
  newProject.append(icon('plus'));
  newProject.addEventListener('click', createProject);
  const importButton = document.getElementById('import-project');
  importButton.append(icon('upload'));
  importButton.addEventListener('click', importProject);
  window.addEventListener('focus', refreshIfIdle);
  try {
    await loadProjects(load('project'));
  } catch (error) {
    report(error);
  }
}

init();

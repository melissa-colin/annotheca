/**
 * @fileoverview Project journal: dated entries in Markdown, with TikZ
 * diagrams and images, written by the user or by AI assistants.
 */

import {api} from './api.js';
import {formatDate, getLanguage, t} from './i18n.js';
import {renderMarkdown} from './markdown.js';
import {pdfPreview} from './pdf-preview.js';
import {ask, chooseFiles, h, icon, report, setChildren} from './ui.js';

/** Kinds of entries, to sort the journal; '' is an uncategorised entry. */
const CATEGORIES = [
  'idea', 'experiment', 'result', 'problem', 'decision', 'reading'];

const SIZE_UNITS = ['byte', 'kilobyte', 'megabyte', 'gigabyte'];

/** @type {string} The category shown, or '' to show every entry. */
let shownCategory = '';

/**
 * Shows the journal of a project.
 * @param {!HTMLElement} main
 * @param {!Object} project
 * @param {function(): !Promise} reload Reloads the project and this view.
 */
export async function renderJournal(main, project, reload) {
  const allEntries = await api.listJournal(project.id);
  const used = CATEGORIES.filter((category) =>
    allEntries.some((entry) => entry.category === category));
  if (!used.includes(shownCategory)) shownCategory = '';
  const entries = allEntries.filter((entry) =>
    !shownCategory || entry.category === shownCategory);
  const days = new Map();
  for (const entry of entries) {
    const day = formatDate(entry.created_at, {dateStyle: 'full'});
    days.set(day, [...days.get(day) ?? [], entry]);
  }
  setChildren(main,
      h('header.view-header', {},
          h('h1', {}, t('journal')),
          h('p.muted', {}, t('journal.subtitle'))),
      composer(project, reload),
      used.length > 0 && categoryFilter(allEntries, used,
          () => renderJournal(main, project, reload).catch(report)),
      entries.length ? null : h('p.empty-hint', {}, t('journal.empty')),
      [...days].map(([day, dayEntries]) => h('section.journal-day', {},
          h('h2', {}, day),
          dayEntries.map((entry) => entryElement(project, entry, reload)))));
}

/**
 * @param {!Array<!Object>} entries Every entry of the journal.
 * @param {!Array<string>} used The categories some entry has.
 * @param {function()} rerender Shows the journal again, filtered.
 * @return {!HTMLElement} Buttons to show only the entries of a category.
 */
function categoryFilter(entries, used, rerender) {
  const option = (category, label, count) => h(
      `button.chip.category${category ? `.cat-${category}` : ''}` +
      `${category === shownCategory ? '.active' : ''}`, {
        onclick: () => {
          shownCategory = category;
          rerender();
        },
      }, label, h('span.category-count', {}, String(count)));
  return h('div.category-filter', {},
      option('', t('journal.all'), entries.length),
      used.map((category) => option(category, t(`category.${category}`),
          entries.filter((entry) => entry.category === category).length)));
}

/**
 * @param {string} selected The category chosen, or ''.
 * @param {function(string)} choose Called with the new category, or ''.
 * @return {!HTMLElement} Buttons to choose the category of an entry.
 */
function categoryPicker(selected, choose) {
  const picker = h('div.category-picker', {});
  const render = () => picker.replaceChildren(...CATEGORIES.map((category) =>
    h(`button.chip.category.cat-${category}` +
        `${category === selected ? '.active' : ''}`, {
      type: 'button',
      onclick: () => {
        selected = category === selected ? '' : category;
        choose(selected);
        render();
      },
    }, t(`category.${category}`))));
  render();
  return picker;
}

/**
 * @param {!Object} project
 * @param {function(): !Promise} reload
 * @return {!HTMLElement} The form to write a new entry, with images.
 */
function composer(project, reload) {
  let category = '';
  /** @type {?number} The paper the entry is a reading note on. */
  let placementId = null;
  const images = [];
  const attachments = [];
  const previews = h('div.pending-images');
  const pendingFiles = h('div.entry-files');
  const remove = (list, index) => h('button.icon-button.small', {
    title: t('journal.removeFile'),
    onclick: () => {
      list.splice(index, 1);
      addFiles([]);
    },
  }, icon('x'));
  // Images are shown in the entry; other files are attached for download.
  const addFiles = (files) => {
    for (const file of files) {
      (file.type.startsWith('image/') ? images : attachments).push(file);
    }
    previews.replaceChildren(...images.map((file, index) =>
      h('figure.pending-image', {},
          h('img', {src: URL.createObjectURL(file), alt: file.name}),
          remove(images, index))));
    pendingFiles.replaceChildren(...attachments.map((file, index) =>
      h('span.file-chip', {}, icon('file'), file.name,
          h('span.muted', {}, formatSize(file.size)),
          remove(attachments, index))));
  };
  const submit = async () => {
    if (!textarea.value.trim() && !images.length && !attachments.length) {
      return;
    }
    button.disabled = true;
    try {
      // A note on a paper is a reading note unless said otherwise.
      const entry = await api.addJournalEntry(project.id, textarea.value,
          category || (placementId ? 'reading' : ''), placementId);
      for (const image of images) {
        await api.addJournalImage(entry.id, image);
      }
      for (const file of attachments) {
        await api.addJournalFile(entry.id, file);
      }
      await reload();
    } catch (error) {
      button.disabled = false;
      report(error);
    }
  };
  const textarea = h('textarea.paste.journal-input', {
    rows: 4,
    placeholder: t('journal.placeholder'),
    onkeydown: (event) => {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) submit();
    },
    onpaste: (event) => addFiles([...event.clipboardData.files]),
  });
  const button = h('button.button.primary', {onclick: submit},
      icon('plus'), t('journal.add'));
  return h('div.paste-box.composer', {
    ondragover: (event) => event.preventDefault(),
    ondrop: (event) => {
      event.preventDefault();
      addFiles([...event.dataTransfer.files]);
    },
  }, textarea, previews, pendingFiles,
  paperPicker(project, (chosen) => placementId = chosen),
  h('div.paste-actions', {},
      categoryPicker(category, (chosen) => category = chosen),
      h('button.button.small.ghost', {
        onclick: () => chooseFiles('', addFiles, true),
      }, icon('paperclip'), t('journal.attach')),
      h('kbd', {}, t('paste.hint')), button));
}

/**
 * @param {!Object} project The project, with its folders and placements.
 * @param {function(?number)} choose Called with the placement chosen, or
 *     null for none.
 * @return {!HTMLElement} A menu to link the entry to a paper of the project,
 *     or to a new one, added to a folder first.
 */
function paperPicker(project, choose) {
  const NEW = 'new';
  const select = h('select.select.paper-select', {
    onchange: () => {
      newPaper.hidden = select.value !== NEW;
      choose(Number(select.value) || null);
      if (select.value === NEW) reference.focus();
    },
  });
  const fill = (selected = '') => {
    setChildren(select,
        h('option', {value: ''}, t('journal.noPaper')),
        project.folders.filter((folder) => folder.placements.length).map(
            (folder) => h('optgroup', {label: folder.name},
                folder.placements.map((placement) => h('option',
                    {value: placement.id}, placement.title)))),
        h('option', {value: NEW}, t('journal.newPaper')));
    select.value = selected;
  };
  const reference = h('input.input', {
    placeholder: t('journal.newPaperPlaceholder'),
    onkeydown: (event) => {
      if (event.key === 'Enter') addPaper();
    },
  });
  const folderSelect = h('select.select', {},
      project.folders.map((folder) =>
        h('option', {value: folder.id}, folder.name)));
  const addPaper = async () => {
    if (!reference.value.trim()) return;
    try {
      const folderId = Number(folderSelect.value);
      const {paper_ids: [paperId]} =
          await api.addPapers(folderId, {text: reference.value});
      project.folders = (await api.getProject(project.id)).folders;
      const placement = project.folders.find((f) => f.id === folderId)
          .placements.find((p) => p.paper_id === paperId);
      api.fetchPdf(paperId).catch(() => {});
      reference.value = '';
      newPaper.hidden = true;
      fill(String(placement.id));
      choose(placement.id);
    } catch (error) {
      report(error);
    }
  };
  const newPaper = h('div.new-paper', {hidden: true}, reference, folderSelect,
      h('button.button.small', {onclick: addPaper},
          icon('plus'), t('paste.add')));
  fill();
  return h('div.composer-paper', {},
      h('label.composer-paper-label', {}, icon('file'), select), newPaper);
}

/**
 * @param {!Object} project
 * @param {?Object} paper The paper an entry is about, as listed with it.
 * @return {?HTMLElement} A link that opens the paper.
 */
function paperLink(project, paper) {
  if (!paper) return null;
  if (paper.trashed) {
    return h('span.chip.subtle.paper-link', {}, icon('file'), paper.title,
        h('span.muted', {}, t('journal.paperInTrash')));
  }
  return h('a.chip.paper-link', {
    href: `#/p/${project.id}/f/${paper.folder_id}/r/${paper.placement_id}`,
    title: t('journal.openPaper'),
  }, icon('file'), paper.title);
}

/**
 * @param {!Object} project
 * @param {!Object} entry
 * @param {function(): !Promise} reload
 * @return {!HTMLElement}
 */
function entryElement(project, entry, reload) {
  const body = h('div.markdown', {}, renderMarkdown(entry.body));
  const edit = () => {
    let category = entry.category;
    const textarea = h('textarea.paste.journal-input', {
      value: entry.body, rows: Math.max(4, entry.body.split('\n').length),
    });
    body.replaceChildren(textarea, h('div.edit-actions', {},
        categoryPicker(category, (chosen) => category = chosen),
        h('button.button.small.ghost', {
          onclick: () => body.replaceChildren(renderMarkdown(entry.body)),
        }, t('cancel')),
        h('button.button.small.primary', {
          onclick: () => api.updateJournalEntry(
              entry.id, textarea.value, category).then(reload, report),
        }, t('save'))));
    textarea.focus();
  };
  const remove = async () => {
    const confirmed = await ask({
      title: t('journal.delete'), message: t('journal.deleteConfirm'),
      action: t('delete'), danger: true,
    });
    if (confirmed) api.deleteJournalEntry(entry.id).then(reload, report);
  };
  return h('article.entry', {},
      h('header.entry-header', {},
          h('time', {dateTime: entry.created_at},
              formatDate(entry.created_at, {timeStyle: 'short'})),
          entry.category && h(`span.chip.category.cat-${entry.category}`, {},
              t(`category.${entry.category}`)),
          entry.author && h('span.chip.agent', {}, icon('bot'), entry.author),
          entry.updated_at && h('span.muted.small', {}, t('journal.edited',
              {date: formatDate(entry.updated_at,
                  {dateStyle: 'medium', timeStyle: 'short'})})),
          h('span.entry-actions', {},
              h('button.icon-button.small', {
                title: t('journal.edit'), onclick: edit,
              }, icon('pencil')),
              h('button.icon-button.small.danger', {
                title: t('journal.delete'), onclick: remove,
              }, icon('trash')))),
      paperLink(project, entry.paper),
      body,
      entry.images.length > 0 && h('div.entry-images', {},
          entry.images.map((image) => imageElement(image, reload))),
      entry.files.filter(isPdf).map((file) =>
        pdfPreview(api.journalFileUrl(file.id), file.name)),
      entry.files.length > 0 && h('div.entry-files', {},
          entry.files.map((file) => fileElement(file, reload))));
}

/**
 * @param {{name: string}} file
 * @return {boolean} Whether the file is a PDF, which the entry previews.
 */
function isPdf(file) {
  return file.name.toLowerCase().endsWith('.pdf');
}

/**
 * @param {{id: number, name: string, size: number}} file
 * @param {function(): !Promise} reload
 * @return {!HTMLElement} A link that downloads the attached file.
 */
function fileElement(file, reload) {
  return h('span.file-chip', {},
      h('a', {
        href: api.journalFileUrl(file.id), download: file.name,
        title: t('journal.download'),
      }, icon('file'), file.name),
      h('span.muted', {}, formatSize(file.size)),
      h('button.icon-button.small.danger', {
        title: t('journal.removeFile'),
        onclick: () => api.deleteJournalFile(file.id).then(reload, report),
      }, icon('x')));
}

/**
 * @param {number} bytes
 * @return {string} The size in the largest unit below it, such as '2.4 MB'.
 */
function formatSize(bytes) {
  const exponent = Math.min(
      SIZE_UNITS.length - 1, Math.floor(Math.log(bytes || 1) / Math.log(1024)));
  return new Intl.NumberFormat(getLanguage(), {
    style: 'unit', unit: SIZE_UNITS[exponent], unitDisplay: 'narrow',
    maximumFractionDigits: 1,
  }).format(bytes / 1024 ** exponent);
}

/**
 * @param {{id: number}} image
 * @param {function(): !Promise} reload
 * @return {!HTMLElement} A thumbnail that opens full size when clicked.
 */
function imageElement(image, reload) {
  const url = api.journalImageUrl(image.id);
  return h('figure.entry-image', {},
      h('img', {src: url, alt: '', loading: 'lazy', onclick: () => {
        const viewer = h('dialog.lightbox', {
          onclick: () => viewer.close(),
          onclose: () => viewer.remove(),
        }, h('img', {src: url, alt: ''}));
        document.body.append(viewer);
        viewer.showModal();
      }}),
      h('button.icon-button.small.danger', {
        title: t('journal.removeImage'),
        onclick: () => api.deleteJournalImage(image.id).then(reload, report),
      }, icon('x')));
}

/**
 * @fileoverview Project journal: dated entries in Markdown, with TikZ
 * diagrams and images, written by the user or by AI assistants.
 */

import {api} from './api.js';
import {formatDate, getLanguage, t} from './i18n.js';
import {renderMarkdown} from './markdown.js';
import {pdfPreview} from './pdf-preview.js';
import {ask, chooseFiles, h, icon, report, setChildren} from './ui.js';

/** Categories of every project, translated; each project adds its own. */
const BUILTIN_CATEGORIES = [
  'idea', 'experiment', 'result', 'problem', 'decision', 'reading'];
/** Colours of the categories a project adds, picked from their name. */
const CUSTOM_COLORS = [
  '#7a5bd6', '#b5562b', '#4f7d3a', '#2d6f8f', '#9c3d8f', '#8a6d3b'];

const SIZE_UNITS = ['byte', 'kilobyte', 'megabyte', 'gigabyte'];

/** @type {!Set<string>} The categories shown; none means every entry. */
const shownCategories = new Set();

/**
 * Shows the journal of a project.
 * @param {!HTMLElement} main
 * @param {!Object} project
 * @param {function(): !Promise} reload Reloads the project and this view.
 */
export async function renderJournal(main, project, reload) {
  const allEntries = await api.listJournal(project.id);
  const used = categories(project).filter((category) =>
    allEntries.some((entry) => entry.category === category));
  for (const category of shownCategories) {
    if (!used.includes(category)) shownCategories.delete(category);
  }
  const entries = allEntries.filter((entry) =>
    !shownCategories.size || shownCategories.has(entry.category));
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
 * @param {!Object} project
 * @return {!Array<string>} The categories its entries can have.
 */
function categories(project) {
  return [...BUILTIN_CATEGORIES, ...project.categories];
}

/**
 * Creates a chip, or a button, showing a category in its colour.
 * @param {string} tag The element, such as 'span.chip' or 'button.chip'.
 * @param {string} category
 * @param {!Object=} props
 * @param {...*} children Shown after the name of the category.
 * @return {!HTMLElement}
 */
function categoryChip(tag, category, props = {}, ...children) {
  if (BUILTIN_CATEGORIES.includes(category)) {
    return h(`${tag}.category.cat-${category}`, props,
        t(`category.${category}`), children);
  }
  const hash = [...category].reduce(
      (sum, char) => (sum * 31 + char.codePointAt(0)) % 1000003, 0);
  const chip = h(`${tag}.category`, props, category, children);
  chip.style.setProperty(
      '--category', CUSTOM_COLORS[hash % CUSTOM_COLORS.length]);
  return chip;
}

/**
 * @param {!Array<!Object>} entries Every entry of the journal.
 * @param {!Array<string>} used The categories some entry has.
 * @param {function()} rerender Shows the journal again, filtered.
 * @return {!HTMLElement} Buttons to show only the entries of some
 *     categories, one or several.
 */
function categoryFilter(entries, used, rerender) {
  const count = (n) => h('span.category-count', {}, String(n));
  return h('div.category-filter', {},
      h(`button.chip.category${shownCategories.size ? '' : '.active'}`, {
        onclick: () => {
          shownCategories.clear();
          rerender();
        },
      }, t('journal.all'), count(entries.length)),
      used.map((category) => categoryChip(
          `button.chip${shownCategories.has(category) ? '.active' : ''}`,
          category, {
            title: t('journal.filterHint'),
            onclick: () => {
              if (!shownCategories.delete(category)) {
                shownCategories.add(category);
              }
              rerender();
            },
          }, count(entries.filter((e) => e.category === category).length))));
}

/**
 * @param {!Object} project Its `categories` are kept up to date.
 * @param {string} selected The category chosen, or ''.
 * @param {function(string)} choose Called with the new category, or ''.
 * @param {function(): !Promise} reload Reloads the journal, after a category
 *     of the project's own is deleted.
 * @return {!HTMLElement} Buttons to choose the category of an entry, to add
 *     one to the project, or to delete one it added.
 */
function categoryPicker(project, selected, choose, reload) {
  const picker = h('div.category-picker', {});
  const select = (category) => {
    selected = category === selected ? '' : category;
    choose(selected);
    render();
  };
  const create = async () => {
    const name = await ask({
      title: t('category.new'), value: '', action: t('create'),
    });
    if (!name) return;
    try {
      project.categories = await api.addCategory(project.id, name);
      select(name);
    } catch (error) {
      report(error);
    }
  };
  const remove = async (category) => {
    const confirmed = await ask({
      title: t('category.delete'),
      message: t('category.deleteConfirm', {name: category}),
      action: t('delete'), danger: true,
    });
    if (confirmed) {
      api.deleteCategory(project.id, category).then(reload, report);
    }
  };
  const render = () => setChildren(picker,
      categories(project).map((category) => categoryChip(
          `button.chip${category === selected ? '.active' : ''}`, category,
          {type: 'button', onclick: () => select(category)},
          !BUILTIN_CATEGORIES.includes(category) &&
              h('span.category-delete', {
                title: t('category.delete'),
                onclick: (event) => {
                  event.stopPropagation();
                  remove(category);
                },
              }, icon('x')))),
      h('button.chip.category.category-new', {
        type: 'button', title: t('category.new'), onclick: create,
      }, icon('plus')));
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
      categoryPicker(
          project, category, (chosen) => category = chosen, reload),
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
        categoryPicker(project, category, (chosen) => category = chosen,
            reload),
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
          entry.category && categoryChip('span.chip', entry.category),
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

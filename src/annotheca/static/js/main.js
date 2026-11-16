/**
 * @fileoverview Application shell: the project picker, the sidebar of the open
 * project and the routing between its views.
 *
 * Routes live in the URL hash so that the browser's back button works:
 *   #/                      the project picker
 *   #/p/<id>/f/<folder id>  the papers of a folder
 *   #/p/<id>/journal        the project journal
 *   #/p/<id>/todo           the project to-do list
 */

import {api} from './api.js';
import {
  LANGUAGES, formatDate, getLanguage, setLanguage, t, translatePage,
} from './i18n.js';
import {renderJournal} from './journal.js';
import {renderFolder} from './papers.js';
import {renderTodos} from './todos.js';
import {ask, chooseFiles, h, icon, report, setChildren, toast} from './ui.js';

const ROUTE_RE = /^#\/p\/(\d+)(?:\/f\/(\d+)|\/(journal|todo))?$/;

/** @type {?Object} The open project, with its folders and placements. */
let project = null;

/**
 * Shows the view the URL hash names, reloading the project it belongs to.
 */
async function route() {
  const match = location.hash.match(ROUTE_RE);
  const main = document.getElementById('main');
  if (!match) {
    project = null;
    renderSidebar();
    await renderPicker(main);
    return;
  }
  try {
    project = await api.getProject(Number(match[1]));
  } catch (error) {
    report(error);
    location.hash = '#/';
    return;
  }
  const folder = project.folders.find((f) => f.id === Number(match[2]));
  if (!folder && !match[3]) {
    location.replace(`#/p/${project.id}/f/${project.folders[0].id}`);
    return;
  }
  renderSidebar();
  if (folder) {
    renderFolder(main, project, folder, route);
  } else if (match[3] === 'journal') {
    await renderJournal(main, project, route);
  } else {
    await renderTodos(main, project, route);
  }
}

// Project picker.

/** @param {!HTMLElement} main */
async function renderPicker(main) {
  const projects = await api.listProjects();
  const actions = h('div.header-actions', {},
      h('button.button', {onclick: importProject},
          icon('upload'), t('import')),
      h('button.button.primary', {onclick: createProject},
          icon('plus'), t('project.new')));
  if (!projects.length) {
    main.replaceChildren(h('div.empty-state', {},
        icon('book'),
        h('h2', {}, t('project.none')),
        h('p', {}, t('project.noneHint')),
        actions));
    return;
  }
  main.replaceChildren(
      h('header.view-header.with-actions', {},
          h('div', {},
              h('h1', {}, t('projects.title')),
              h('p.muted', {}, t('projects.subtitle'))),
          actions),
      h('div.project-grid', {}, projects.map((item) =>
        h('a.project-card', {href: `#/p/${item.id}`},
            icon('book'),
            h('strong', {}, item.name),
            h('span.muted', {}, [
              t('papers', {n: item.paper_count}),
              item.open_todos && t('project.openTodos', {n: item.open_todos}),
            ].filter(Boolean).join(' · ')),
            h('span.muted.small', {}, item.last_entry ?
                t('project.lastEntry', {date: formatDate(item.last_entry)}) :
                t('project.noEntry'))))));
}

async function createProject() {
  const name = await ask(
      {title: t('project.new'), value: '', action: t('create')});
  if (!name) return;
  try {
    location.hash = `#/p/${(await api.createProject(name)).id}`;
  } catch (error) {
    report(error);
  }
}

function importProject() {
  chooseFiles('.annotheca', async ([file]) => {
    try {
      const imported = await api.importBundle(file);
      toast(t('import.done', {name: imported.name}));
      location.hash = `#/p/${imported.id}`;
    } catch (error) {
      report(error);
    }
  });
}

// Project sidebar.

function renderSidebar() {
  const nav = document.getElementById('sidebar-nav');
  if (!project) {
    nav.replaceChildren();
    return;
  }
  const base = `#/p/${project.id}`;
  setChildren(nav,
      h('a.back-link', {href: '#/'}, icon('arrowLeft'), t('nav.allProjects')),
      h('div.sidebar-project', {},
          h('strong', {}, project.name),
          h('button.icon-button.small', {
            title: t('project.rename'),
            onclick: () => rename('project', project),
          }, icon('pencil')),
          h('button.icon-button.small.danger', {
            title: t('project.delete'),
            onclick: () => remove('project', project),
          }, icon('trash'))),
      h('div.sidebar-actions', {},
          h('a.button.small', {
            href: api.bundleUrl(project.id), download: '',
            title: t('share.hint'),
          }, icon('share'), t('share')),
          h('a.button.small', {
            href: api.exportUrl(project.id), download: '',
            title: t('export.hint'),
          }, icon('download'), t('export')),
          h('button.button.small', {
            title: t('orchestra.hint'), onclick: exportPaperOrchestra,
          }, icon('file'), t('orchestra'))),
      h('div.sidebar-heading', {}, t('nav.project')),
      navItem(`${base}/journal`, 'journal', t('journal'),
          project.journal_entries),
      navItem(`${base}/todo`, 'check', t('todo'), project.open_todos),
      h('div.sidebar-heading', {}, t('nav.papers')),
      project.folders.map((folder) => navItem(
          `${base}/f/${folder.id}`, 'folder', folder.name,
          folder.placements.length,
          h('button.icon-button.small.reveal', {
            title: t('folder.rename'), onclick: () => rename('folder', folder),
          }, icon('pencil')),
          project.folders.length > 1 && h('button.icon-button.small.reveal', {
            title: t('folder.delete'), onclick: () => remove('folder', folder),
          }, icon('trash')))),
      h('button.nav-add', {onclick: createFolder},
          icon('folderPlus'), t('folder.new')));
}

/** Explains PaperOrchestra, then downloads the project's materials for it. */
async function exportPaperOrchestra() {
  const repository = 'https://github.com/google-research/paper-orchestra';
  const confirmed = await ask({
    title: t('orchestra'),
    message: [t('orchestra.about'), h('a', {
      href: repository, target: '_blank', rel: 'noopener',
    }, 'github.com/google-research/paper-orchestra'), '.'],
    action: t('orchestra.download'),
  });
  if (confirmed) location.assign(api.paperOrchestraUrl(project.id));
}

/**
 * @param {string} href Route of the item.
 * @param {string} iconName
 * @param {string} label
 * @param {number} count
 * @param {...*} actions Buttons shown when hovering the item.
 * @return {!HTMLElement}
 */
function navItem(href, iconName, label, count, ...actions) {
  const active = location.hash === href;
  return h(`div.nav-item${active ? '.active' : ''}`, {},
      h('a.nav-link', {href}, icon(iconName), h('span', {}, label),
          h('span.count', {}, String(count))),
      actions);
}

async function createFolder() {
  const name = await ask(
      {title: t('folder.new'), value: '', action: t('create')});
  if (!name) return;
  try {
    const folder = await api.createFolder(project.id, name);
    location.hash = `#/p/${project.id}/f/${folder.id}`;
  } catch (error) {
    report(error);
  }
}

/**
 * Renames the project or one of its folders.
 * @param {string} kind 'project' or 'folder'.
 * @param {{id: number, name: string}} item
 */
async function rename(kind, item) {
  const name = await ask(
      {title: t(`${kind}.rename`), value: item.name, action: t('save')});
  if (!name || name === item.name) return;
  try {
    await api.rename(kind, item.id, name);
    await route();
  } catch (error) {
    report(error);
  }
}

/**
 * Deletes the project or one of its folders after confirmation.
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
    if (kind === 'project') {
      location.hash = '#/';
    } else if (location.hash.endsWith(`/f/${item.id}`)) {
      location.hash = `#/p/${project.id}`;
    } else {
      await route();
    }
  } catch (error) {
    report(error);
  }
}

// Start-up.

function renderLanguageSwitch() {
  const buttons = LANGUAGES.map((code) => h(
      `button${code === getLanguage() ? '.active' : ''}`, {
    onclick: () => {
      setLanguage(code);
      renderLanguageSwitch();
      route().catch(report);
    },
  }, code.toUpperCase()));
  document.getElementById('language-switch').replaceChildren(...buttons);
}

/**
 * Reloads the view, e.g. after an AI assistant changed the project, unless
 * the user is typing or reading.
 */
function refreshIfIdle() {
  const typing = document.activeElement.matches('input, textarea') ||
      [...document.querySelectorAll('textarea')].some((area) => area.value);
  if (!typing && document.getElementById('viewer').hidden) {
    route().catch(report);
  }
}

translatePage();
renderLanguageSwitch();
window.addEventListener('hashchange', () => route().catch(report));
window.addEventListener('focus', refreshIfIdle);
route().catch(report);

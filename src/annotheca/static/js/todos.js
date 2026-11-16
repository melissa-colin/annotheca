/**
 * @fileoverview Project to-do list: what is left to do, with an optional
 * priority and deadline, and what got done.
 */

import {api} from './api.js';
import {formatDate, t} from './i18n.js';
import {h, icon, report, setChildren} from './ui.js';

const PRIORITIES = ['', 'high', 'medium', 'low'];
/** Deadlines this close are marked as near. */
const SOON_DAYS = 3;

/**
 * Shows the to-do list of a project.
 * @param {!HTMLElement} main
 * @param {!Object} project
 * @param {function(): !Promise} reload Reloads the project and this view.
 */
export async function renderTodos(main, project, reload) {
  const todos = await api.listTodos(project.id);
  const open = todos.filter((todo) => !todo.done_at);
  const done = todos.filter((todo) => todo.done_at);
  const add = () => {
    if (!input.value.trim()) return;
    api.addTodo(project.id, {
      text: input.value, due_date: due.value || null,
      priority: priority.value,
    }).then(reload, report);
  };
  const input = h('input.input.todo-input', {
    placeholder: t('todo.placeholder'),
    onkeydown: (event) => {
      if (event.key === 'Enter') add();
    },
  });
  const priority = prioritySelect('', () => {});
  const due = dueInput(null, () => {});
  setChildren(main,
      h('header.view-header', {},
          h('h1', {}, t('todo')),
          h('p.muted', {}, t('todo.subtitle'))),
      h('div.todo-composer', {}, input, priority, due,
          h('button.button.primary', {onclick: add},
              icon('plus'), t('todo.add'))),
      h('ul.todo-list', {}, open.map((todo) => todoItem(todo, reload))),
      !todos.length && h('p.empty-hint', {}, t('todo.empty')),
      done.length > 0 && h('details.todo-done', {},
          h('summary', {}, t('todo.done', {n: done.length})),
          h('ul.todo-list', {}, done.map((todo) => todoItem(todo, reload)))));
  input.focus();
}

/**
 * @param {string} priority 'high', 'medium', 'low' or ''.
 * @param {function(string)} change Called with the priority chosen.
 * @return {!HTMLSelectElement}
 */
function prioritySelect(priority, change) {
  const select = h(`select.select.priority.priority-${priority || 'none'}`, {
    title: t('todo.priority'),
    onchange: () => {
      select.className = `select priority priority-${select.value || 'none'}`;
      change(select.value);
    },
  }, PRIORITIES.map((value) => h('option', {value},
      t(value ? `priority.${value}` : 'todo.noPriority'))));
  select.value = priority;
  return select;
}

/**
 * @param {?string} date The deadline, as YYYY-MM-DD, or null.
 * @param {function(?string)} change Called with the date chosen, or null.
 * @return {!HTMLInputElement} A date field, marked when the deadline is
 *     past or near.
 */
function dueInput(date, change) {
  const now = new Date();
  const today = new Date(now - now.getTimezoneOffset() * 60000)
      .toISOString().slice(0, 10);
  const soon = new Date(Date.parse(today) + SOON_DAYS * 86400000)
      .toISOString().slice(0, 10);
  const state = !date ? '' : date < today ? '.overdue' :
      date <= soon ? '.soon' : '';
  return h(`input.input.todo-due${date ? '.has-date' : ''}${state}`, {
    type: 'date', value: date ?? '', title: t('todo.due'),
    onchange: (event) => change(event.target.value || null),
  });
}

/**
 * @param {!Object} todo
 * @param {function(): !Promise} reload
 * @return {!HTMLElement}
 */
function todoItem(todo, reload) {
  const update = (changes) =>
    api.updateTodo(todo.id, changes).then(reload, report);
  const text = h('span.todo-text', {
    title: t('todo.editHint'),
    ondblclick: () => {
      const input = h('input.input', {
        value: todo.text,
        onkeydown: (event) => {
          if (event.key === 'Enter') update({text: input.value});
          if (event.key === 'Escape') input.replaceWith(text);
        },
        onblur: () => input.replaceWith(text),
      });
      text.replaceWith(input);
      input.select();
    },
  }, todo.text);
  return h(`li.todo${todo.done_at ? '.is-done' : ''}`, {},
      h('input', {
        type: 'checkbox', checked: Boolean(todo.done_at),
        ariaLabel: todo.text,
        onchange: () => update({done: !todo.done_at}),
      }),
      text,
      todo.author && h('span.chip.agent', {}, icon('bot'), todo.author),
      todo.done_at ?
          h('span.muted.small', {},
              t('todo.doneOn', {date: formatDate(todo.done_at)})) :
          [prioritySelect(todo.priority,
              (priority) => update({priority})),
          dueInput(todo.due_date, (date) => update({due_date: date}))],
      h('button.icon-button.small.danger', {
        title: t('todo.delete'),
        onclick: () => api.deleteTodo(todo.id).then(reload, report),
      }, icon('trash')));
}

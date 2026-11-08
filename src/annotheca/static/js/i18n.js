/**
 * @fileoverview English and French interface strings.
 */

import {load, save} from './storage.js';

const MESSAGES = {
  en: {
    'app.tagline': 'Research bibliographies',
    'projects': 'Projects',
    'project.new': 'New project',
    'project.rename': 'Rename project',
    'project.delete': 'Delete project',
    'project.deleteConfirm':
        'Delete “{name}” with all its folders, notes and highlights?',
    'project.none': 'No project yet',
    'project.noneHint':
        'Create a project to start collecting references. Each one gets a ' +
        '“SoA” (state of the art) folder.',
    'folder.new': 'New folder',
    'folder.rename': 'Rename folder',
    'folder.delete': 'Delete folder',
    'folder.deleteConfirm':
        'Delete the folder “{name}”? Its papers stay in the other folders, ' +
        'but the notes and highlights made here are lost.',
    'folder.empty': 'This folder is empty. Paste a reference above.',
    'name': 'Name',
    'cancel': 'Cancel',
    'create': 'Create',
    'save': 'Save',
    'delete': 'Delete',
    'remove': 'Remove',
    'export': 'Export BibTeX',
    'export.hint': 'One .bib file with every paper of the project, once.',
    'share': 'Share',
    'share.hint':
        'Download the project with its notes, highlights and PDFs as one ' +
        'file to send. It opens with “Import” in Annotheca.',
    'import': 'Import a shared project',
    'import.done': 'Imported “{name}”.',
    'notes': 'Notes',
    'notes.title': 'General notes on this paper, for this folder',
    'notes.placeholder':
        'General notes on this paper: what it brings, how you use it here…',
    'paste.placeholder':
        'Paste BibTeX, DOIs, arXiv IDs or a formatted citation (APA, IEEE…)',
    'paste.add': 'Add',
    'paste.hint': 'Ctrl+Enter',
    'paste.added': 'Added {n} reference(s).',
    'paste.alreadyThere': '{n} already in this folder.',
    'filter': 'Filter…',
    'papers': '{n} paper(s)',
    'pdf.searching': 'Looking for the PDF…',
    'pdf.notFound': 'No open-access PDF found for “{title}”. Attach it.',
    'pdf.attach': 'Attach PDF',
    'pdf.find': 'Find PDF',
    'pdf.drop': 'Drop the PDF',
    'paper.open': 'Read',
    'paper.fileIn': 'Add to folder…',
    'paper.fileInDone': 'Added to “{folder}”.',
    'paper.remove': 'Remove from this folder',
    'paper.removeConfirm':
        'Remove “{title}” from “{folder}”? The notes and highlights made ' +
        'in this folder are lost.',
    'paper.alsoIn': 'Also in {folders}',
    'paper.copy': 'Copy \\cite command',
    'paper.copied': 'Copied {cite}',
    'paper.annotations': 'Notes and highlights in this folder',
    'viewer.back': 'Back',
    'viewer.highlight': 'Highlight',
    'viewer.note': 'Sticky note',
    'viewer.zoomIn': 'Zoom in',
    'viewer.zoomOut': 'Zoom out',
    'viewer.annotations': 'Notes & highlights',
    'viewer.empty':
        'Select text to highlight it, or pick the sticky note tool and ' +
        'click on the page.',
    'viewer.notePlaceholder': 'Write a note…',
    'viewer.page': 'p. {n}',
    'error.not_found': 'This item no longer exists.',
    'error.name_taken': 'This name is already used.',
    'error.not_pdf': 'This file is not a PDF.',
    'error.not_bundle': 'This file is not a shared Annotheca project.',
    'error.unresolvable': 'Could not recognise this reference.',
    'error.unreachable':
        'Could not reach the online sources. Are you offline?',
    'error.generic': 'Something went wrong.',
  },
  fr: {
    'app.tagline': 'Bibliographies de recherche',
    'projects': 'Projets',
    'project.new': 'Nouveau projet',
    'project.rename': 'Renommer le projet',
    'project.delete': 'Supprimer le projet',
    'project.deleteConfirm':
        'Supprimer « {name} » avec tous ses dossiers, notes et surlignages ?',
    'project.none': 'Aucun projet',
    'project.noneHint':
        'Créez un projet pour rassembler vos références. Chacun démarre ' +
        'avec un dossier « SoA » (état de l’art).',
    'folder.new': 'Nouveau dossier',
    'folder.rename': 'Renommer le dossier',
    'folder.delete': 'Supprimer le dossier',
    'folder.deleteConfirm':
        'Supprimer le dossier « {name} » ? Ses papiers restent dans les ' +
        'autres dossiers, mais les notes et surlignages faits ici sont perdus.',
    'folder.empty': 'Ce dossier est vide. Collez une référence ci-dessus.',
    'name': 'Nom',
    'cancel': 'Annuler',
    'create': 'Créer',
    'save': 'Enregistrer',
    'delete': 'Supprimer',
    'remove': 'Retirer',
    'export': 'Exporter le BibTeX',
    'export.hint': 'Un fichier .bib avec chaque papier du projet, une fois.',
    'share': 'Partager',
    'share.hint':
        'Télécharger le projet avec ses notes, surlignages et PDF en un seul ' +
        'fichier à envoyer. Il s’ouvre avec « Importer » dans Annotheca.',
    'import': 'Importer un projet partagé',
    'import.done': '« {name} » importé.',
    'notes': 'Notes',
    'notes.title': 'Notes générales sur ce papier, pour ce dossier',
    'notes.placeholder':
        'Notes générales sur ce papier : ce qu’il apporte, comment vous ' +
        'l’utilisez ici…',
    'paste.placeholder':
        'Collez du BibTeX, des DOI, des identifiants arXiv ou une citation ' +
        'formatée (APA, IEEE…)',
    'paste.add': 'Ajouter',
    'paste.hint': 'Ctrl+Entrée',
    'paste.added': '{n} référence(s) ajoutée(s).',
    'paste.alreadyThere': '{n} déjà dans ce dossier.',
    'filter': 'Filtrer…',
    'papers': '{n} papier(s)',
    'pdf.searching': 'Recherche du PDF…',
    'pdf.notFound': 'Aucun PDF en libre accès pour « {title} ». Joignez-le.',
    'pdf.attach': 'Joindre le PDF',
    'pdf.find': 'Chercher le PDF',
    'pdf.drop': 'Déposez le PDF',
    'paper.open': 'Lire',
    'paper.fileIn': 'Ajouter au dossier…',
    'paper.fileInDone': 'Ajouté à « {folder} ».',
    'paper.remove': 'Retirer de ce dossier',
    'paper.removeConfirm':
        'Retirer « {title} » de « {folder} » ? Les notes et surlignages ' +
        'faits dans ce dossier sont perdus.',
    'paper.alsoIn': 'Aussi dans {folders}',
    'paper.copy': 'Copier la commande \\cite',
    'paper.copied': '{cite} copié',
    'paper.annotations': 'Notes et surlignages dans ce dossier',
    'viewer.back': 'Retour',
    'viewer.highlight': 'Surligner',
    'viewer.note': 'Post-it',
    'viewer.zoomIn': 'Zoom avant',
    'viewer.zoomOut': 'Zoom arrière',
    'viewer.annotations': 'Notes et surlignages',
    'viewer.empty':
        'Sélectionnez du texte pour le surligner, ou prenez l’outil post-it ' +
        'et cliquez sur la page.',
    'viewer.notePlaceholder': 'Écrire une note…',
    'viewer.page': 'p. {n}',
    'error.not_found': 'Cet élément n’existe plus.',
    'error.name_taken': 'Ce nom est déjà utilisé.',
    'error.not_pdf': 'Ce fichier n’est pas un PDF.',
    'error.not_bundle': 'Ce fichier n’est pas un projet Annotheca partagé.',
    'error.unresolvable': 'Impossible de reconnaître cette référence.',
    'error.unreachable':
        'Les sources en ligne sont injoignables. Êtes-vous hors ligne ?',
    'error.generic': 'Une erreur est survenue.',
  },
};

export const LANGUAGES = Object.keys(MESSAGES);

let language = load('language') ??
    (navigator.language.startsWith('fr') ? 'fr' : 'en');

/** @return {string} The current interface language. */
export function getLanguage() {
  return language;
}

/**
 * Switches the interface language and remembers the choice.
 * @param {string} code One of LANGUAGES.
 */
export function setLanguage(code) {
  language = code;
  save('language', code);
  translatePage();
}

/**
 * @param {string} key
 * @return {boolean} Whether a message exists for the key.
 */
export function hasMessage(key) {
  return key in MESSAGES.en;
}

/**
 * Returns a translated message.
 * @param {string} key Message key.
 * @param {!Object<string, (string|number)>=} params Values for {placeholders}.
 * @return {string}
 */
export function t(key, params = {}) {
  const message = MESSAGES[language][key] ?? MESSAGES.en[key] ?? key;
  return message.replace(/\{(\w+)\}/g, (match, name) => params[name] ?? match);
}

/** Translates the static markup tagged with data-i18n attributes. */
export function translatePage() {
  document.documentElement.lang = language;
  for (const el of document.querySelectorAll('[data-i18n]')) {
    el.textContent = t(el.dataset.i18n);
  }
  for (const el of document.querySelectorAll('[data-i18n-title]')) {
    el.title = t(el.dataset.i18nTitle);
    el.setAttribute('aria-label', el.title);
  }
}

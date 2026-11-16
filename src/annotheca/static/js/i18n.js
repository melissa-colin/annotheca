/**
 * @fileoverview English and French interface strings.
 */

import {load, save} from './storage.js';

const MESSAGES = {
  en: {
    'app.tagline': 'Research bibliographies',
    'projects.title': 'Your projects',
    'projects.subtitle': 'Choose a project to open it.',
    'project.openTodos': '{n} to-do(s)',
    'project.lastEntry': 'Last journal entry {date}',
    'project.noEntry': 'No journal entry yet',
    'nav.allProjects': 'All projects',
    'nav.papers': 'Papers',
    'nav.project': 'Project',
    'journal': 'Journal',
    'journal.subtitle':
        'Dated notes on the progress of the project: what was done, decided ' +
        'or found. AI assistants can write here too.',
    'journal.placeholder':
        'What did you do, decide or find? Markdown works, and a ```tikz ' +
        'block becomes a diagram. Paste or drop images and files.',
    'journal.add': 'Add to journal',
    'trash': 'Trash',
    'trash.subtitle': 'Deleted projects and papers stay here {days} days, ' +
        'then are deleted for good.',
    'trash.empty': 'The trash is empty.',
    'trash.projects': 'Projects',
    'trash.papers': 'Papers',
    'trash.move': 'Move to trash',
    'trash.moved': '“{name}” is in the trash.',
    'trash.restore': 'Restore',
    'trash.restored': '“{name}” is back.',
    'trash.deletedOn': 'deleted {date}',
    'trash.deleteForGood': 'Delete for good',
    'trash.deleteForGoodConfirm':
        'Delete “{name}” for good? This cannot be undone.',
    'trash.emptyAll': 'Empty the trash',
    'trash.emptyConfirm':
        'Delete everything in the trash for good? This cannot be undone.',
    'journal.all': 'All',
    'journal.noPaper': 'About no paper in particular',
    'journal.newPaper': 'A new paper…',
    'journal.newPaperPlaceholder': 'DOI, arXiv ID, link or citation',
    'journal.openPaper': 'Open the paper',
    'journal.paperInTrash': 'in the trash',
    'category.idea': 'Idea',
    'category.experiment': 'Experiment',
    'category.result': 'Result',
    'category.problem': 'Problem',
    'category.decision': 'Decision',
    'category.reading': 'Reading',
    'journal.attach': 'Attach',
    'journal.removeImage': 'Remove image',
    'journal.removeFile': 'Remove file',
    'journal.openLarger': 'Open larger',
    'journal.previousPage': 'Previous page',
    'journal.nextPage': 'Next page',
    'journal.page': 'Page {n} of {total}',
    'journal.download': 'Download',
    'journal.empty': 'No entry yet.',
    'journal.edit': 'Edit',
    'journal.edited': 'edited {date}',
    'journal.delete': 'Delete entry',
    'journal.tikzError':
        'This diagram could not be drawn: check its TikZ code below, or the ' +
        'connection (diagrams are compiled with TikZJax, loaded online).',
    'journal.deleteConfirm': 'Delete this entry and its images?',
    'todo': 'To-do',
    'todo.subtitle': 'What you plan to do next. AI assistants can add to it.',
    'todo.placeholder': 'Add a task',
    'todo.empty': 'Nothing to do yet.',
    'todo.editHint': 'Double-click to edit',
    'todo.done': 'Done ({n})',
    'todo.doneOn': 'done {date}',
    'todo.delete': 'Delete task',
    'todo.add': 'Add',
    'todo.due': 'Deadline',
    'todo.priority': 'Priority',
    'todo.noPriority': 'No priority',
    'priority.high': 'High',
    'priority.medium': 'Medium',
    'priority.low': 'Low',
    'project.new': 'New project',
    'project.rename': 'Rename project',
    'project.delete': 'Delete project',
    'project.deleteConfirm':
        'Move “{name}” to the trash? You can restore it with its folders, ' +
        'notes and highlights for {days} days.',
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
    'close': 'Close',
    'create': 'Create',
    'save': 'Save',
    'delete': 'Delete',
    'export': 'Export BibTeX',
    'export.hint': 'One .bib file with every paper of the project, once.',
    'orchestra': 'PaperOrchestra',
    'orchestra.hint': 'Raw materials to draft a paper with PaperOrchestra.',
    'orchestra.about':
        'PaperOrchestra, by Google Research, drafts a LaTeX paper from an ' +
        'idea, an experimental log and figures, with a team of AI agents. ' +
        'This download gives it your journal as the log, its images as ' +
        'figures, and your papers with your notes. Describe the idea in ' +
        'idea_sparse.md, then run PaperOrchestra as the README of the ' +
        'archive explains. It runs on your own API keys (an LLM and ' +
        'Semantic Scholar). Install it from ',
    'orchestra.download': 'Download the materials',
    'share': 'Share',
    'share.hint':
        'Download the project with its notes, highlights and PDFs as one ' +
        'file to send. It opens with “Import” in Annotheca.',
    'import': 'Import a shared project',
    'import.done': 'Imported “{name}”.',
    'notes': 'Notes',
    'notes.title': 'Reading notes on this paper, for this folder',
    'notes.placeholder':
        'A note on this paper: what it brings, how you use it here… ' +
        'It is dated and added to the journal.',
    'notes.add': 'Add note',
    'notes.empty': 'No note yet.',
    'paste.placeholder':
        'Paste BibTeX, DOIs, arXiv IDs, links to paper pages or a formatted ' +
        'citation (APA, IEEE…)',
    'paste.add': 'Add',
    'paste.hint': 'Ctrl+Enter',
    'paste.added': 'Added {n} reference(s).',
    'paste.alreadyThere': '{n} already in this folder.',
    'filter': 'Filter…',
    'papers': '{n} paper(s)',
    'pdf.searching': 'Looking for the PDF…',
    'pdf.notFound':
        'Could not download the PDF of “{title}”. Open the paper page, ' +
        'download it there, then drop it on the paper.',
    'pdf.page': 'Paper page',
    'pdf.pageHint':
        'Open the paper page in your browser to download the PDF, then drop ' +
        'it on the paper',
    'pdf.attach': 'Attach PDF',
    'pdf.find': 'Find PDF',
    'pdf.drop': 'Drop the PDF',
    'paper.open': 'Read',
    'paper.fileIn': 'Add to folder…',
    'paper.fileInDone': 'Added to “{folder}”.',
    'paper.remove': 'Remove from this folder',
    'paper.removeConfirm':
        'Move “{title}” out of “{folder}” to the trash? You can restore it ' +
        'with the notes and highlights made in this folder for {days} days.',
    'paper.alsoIn': 'Also in {folders}',
    'paper.copy': 'Copy \\cite command',
    'paper.copied': 'Copied {cite}',
    'paper.annotations': 'Notes and highlights in this folder',
    'paper.addedBy': 'Added by {agent}, with metadata from verified sources',
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
    'error.name_in_trash': 'A project in the trash has this name: restore ' +
        'it, or delete it for good, first.',
    'error.not_pdf': 'This file is not a PDF.',
    'error.not_image': 'Only PNG, JPEG, GIF and WebP images can be added.',
    'error.not_bundle': 'This file is not a shared Annotheca project.',
    'error.unresolvable':
        'Could not identify this reference with certainty. Try its DOI or ' +
        'the link to its page.',
    'error.unreachable':
        'Could not reach the online sources. Are you offline?',
    'error.generic': 'Something went wrong.',
  },
  fr: {
    'app.tagline': 'Bibliographies de recherche',
    'projects.title': 'Vos projets',
    'projects.subtitle': 'Choisissez un projet pour l’ouvrir.',
    'project.openTodos': '{n} tâche(s) à faire',
    'project.lastEntry': 'Dernière entrée du journal le {date}',
    'project.noEntry': 'Pas encore d’entrée dans le journal',
    'nav.allProjects': 'Tous les projets',
    'nav.papers': 'Articles',
    'nav.project': 'Projet',
    'journal': 'Journal',
    'journal.subtitle':
        'Notes datées sur l’avancée du projet : ce qui a été fait, décidé ou ' +
        'trouvé. Les assistants IA peuvent aussi y écrire.',
    'journal.placeholder':
        'Qu’avez-vous fait, décidé ou trouvé ? Le Markdown fonctionne, et un ' +
        'bloc ```tikz devient un schéma. Collez ou déposez images et fichiers.',
    'journal.add': 'Ajouter au journal',
    'trash': 'Corbeille',
    'trash.subtitle': 'Les projets et papiers supprimés restent ici ' +
        '{days} jours, puis sont supprimés définitivement.',
    'trash.empty': 'La corbeille est vide.',
    'trash.projects': 'Projets',
    'trash.papers': 'Papiers',
    'trash.move': 'Mettre à la corbeille',
    'trash.moved': '« {name} » est dans la corbeille.',
    'trash.restore': 'Restaurer',
    'trash.restored': '« {name} » est de retour.',
    'trash.deletedOn': 'supprimé le {date}',
    'trash.deleteForGood': 'Supprimer définitivement',
    'trash.deleteForGoodConfirm':
        'Supprimer « {name} » définitivement ? C’est irréversible.',
    'trash.emptyAll': 'Vider la corbeille',
    'trash.emptyConfirm':
        'Tout supprimer définitivement ? C’est irréversible.',
    'journal.all': 'Tout',
    'journal.noPaper': 'Sur aucun papier en particulier',
    'journal.newPaper': 'Un nouveau papier…',
    'journal.newPaperPlaceholder': 'DOI, identifiant arXiv, lien ou citation',
    'journal.openPaper': 'Ouvrir le papier',
    'journal.paperInTrash': 'dans la corbeille',
    'category.idea': 'Idée',
    'category.experiment': 'Expérience',
    'category.result': 'Résultat',
    'category.problem': 'Problème',
    'category.decision': 'Décision',
    'category.reading': 'Lecture',
    'journal.attach': 'Joindre',
    'journal.removeImage': 'Retirer l’image',
    'journal.removeFile': 'Retirer le fichier',
    'journal.openLarger': 'Ouvrir en grand',
    'journal.previousPage': 'Page précédente',
    'journal.nextPage': 'Page suivante',
    'journal.page': 'Page {n} sur {total}',
    'journal.download': 'Télécharger',
    'journal.empty': 'Pas encore d’entrée.',
    'journal.edit': 'Modifier',
    'journal.edited': 'modifié le {date}',
    'journal.delete': 'Supprimer l’entrée',
    'journal.tikzError':
        'Ce schéma n’a pas pu être dessiné : vérifiez son code TikZ ' +
        'ci-dessous, ou la connexion (les schémas sont compilés par TikZJax, ' +
        'chargé en ligne).',
    'journal.deleteConfirm': 'Supprimer cette entrée et ses images ?',
    'todo': 'À faire',
    'todo.subtitle':
        'Ce que vous prévoyez de faire ensuite. Les assistants IA peuvent ' +
        'aussi y ajouter des tâches.',
    'todo.placeholder': 'Ajoutez une tâche',
    'todo.empty': 'Rien à faire pour l’instant.',
    'todo.editHint': 'Double-cliquez pour modifier',
    'todo.done': 'Fait ({n})',
    'todo.doneOn': 'fait le {date}',
    'todo.delete': 'Supprimer la tâche',
    'todo.add': 'Ajouter',
    'todo.due': 'Échéance',
    'todo.priority': 'Priorité',
    'todo.noPriority': 'Sans priorité',
    'priority.high': 'Haute',
    'priority.medium': 'Moyenne',
    'priority.low': 'Basse',
    'project.new': 'Nouveau projet',
    'project.rename': 'Renommer le projet',
    'project.delete': 'Supprimer le projet',
    'project.deleteConfirm':
        'Mettre « {name} » à la corbeille ? Vous pourrez le restaurer avec ' +
        'ses dossiers, notes et surlignages pendant {days} jours.',
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
    'close': 'Fermer',
    'create': 'Créer',
    'save': 'Enregistrer',
    'delete': 'Supprimer',
    'export': 'Exporter le BibTeX',
    'export.hint': 'Un fichier .bib avec chaque papier du projet, une fois.',
    'orchestra': 'PaperOrchestra',
    'orchestra.hint':
        'Les matériaux pour rédiger un article avec PaperOrchestra.',
    'orchestra.about':
        'PaperOrchestra, de Google Research, rédige un article LaTeX à ' +
        'partir d\'une idée, d\'un journal d\'expériences et de figures, ' +
        'avec une équipe d\'agents IA. Ce téléchargement lui donne votre ' +
        'journal, ses images comme figures, et vos papiers avec vos notes. ' +
        'Décrivez l\'idée dans idea_sparse.md, puis lancez PaperOrchestra ' +
        'comme l\'explique le README de l\'archive. Il fonctionne avec vos ' +
        'propres clés d\'API (un LLM et Semantic Scholar). Installez-le ' +
        'depuis ',
    'orchestra.download': 'Télécharger les matériaux',
    'share': 'Partager',
    'share.hint':
        'Télécharger le projet avec ses notes, surlignages et PDF en un seul ' +
        'fichier à envoyer. Il s’ouvre avec « Importer » dans Annotheca.',
    'import': 'Importer un projet partagé',
    'import.done': '« {name} » importé.',
    'notes': 'Notes',
    'notes.title': 'Notes de lecture sur ce papier, pour ce dossier',
    'notes.placeholder':
        'Une note sur ce papier : ce qu’il apporte, comment vous ' +
        'l’utilisez ici… Elle est datée et ajoutée au journal.',
    'notes.add': 'Ajouter la note',
    'notes.empty': 'Pas encore de note.',
    'paste.placeholder':
        'Collez du BibTeX, des DOI, des identifiants arXiv, des liens ' +
        'd’articles ou une citation formatée (APA, IEEE…)',
    'paste.add': 'Ajouter',
    'paste.hint': 'Ctrl+Entrée',
    'paste.added': '{n} référence(s) ajoutée(s).',
    'paste.alreadyThere': '{n} déjà dans ce dossier.',
    'filter': 'Filtrer…',
    'papers': '{n} papier(s)',
    'pdf.searching': 'Recherche du PDF…',
    'pdf.notFound':
        'Impossible de télécharger le PDF de « {title} ». Ouvrez la page de ' +
        'l’article, téléchargez-le, puis déposez-le sur la fiche.',
    'pdf.page': 'Page de l’article',
    'pdf.pageHint':
        'Ouvrir la page de l’article dans le navigateur pour télécharger le ' +
        'PDF, puis le déposer sur la fiche',
    'pdf.attach': 'Joindre le PDF',
    'pdf.find': 'Chercher le PDF',
    'pdf.drop': 'Déposez le PDF',
    'paper.open': 'Lire',
    'paper.fileIn': 'Ajouter au dossier…',
    'paper.fileInDone': 'Ajouté à « {folder} ».',
    'paper.remove': 'Retirer de ce dossier',
    'paper.removeConfirm':
        'Retirer « {title} » de « {folder} » et le mettre à la corbeille ? ' +
        'Vous pourrez le restaurer avec les notes et surlignages faits dans ' +
        'ce dossier pendant {days} jours.',
    'paper.alsoIn': 'Aussi dans {folders}',
    'paper.copy': 'Copier la commande \\cite',
    'paper.copied': '{cite} copié',
    'paper.annotations': 'Notes et surlignages dans ce dossier',
    'paper.addedBy':
        'Ajouté par {agent}, métadonnées issues de sources vérifiées',
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
    'error.name_in_trash': 'Un projet de la corbeille porte ce nom : ' +
        'restaurez-le, ou supprimez-le définitivement, d’abord.',
    'error.not_pdf': 'Ce fichier n’est pas un PDF.',
    'error.not_image':
        'Seules les images PNG, JPEG, GIF et WebP peuvent être ajoutées.',
    'error.not_bundle': 'Ce fichier n’est pas un projet Annotheca partagé.',
    'error.unresolvable':
        'Impossible d’identifier cette référence avec certitude. Essayez son ' +
        'DOI ou le lien de sa page.',
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

/**
 * Formats an ISO 8601 date in the interface language.
 * @param {string} iso
 * @param {!Object=} options Intl.DateTimeFormat options.
 * @return {string}
 */
export function formatDate(iso, options = {dateStyle: 'medium'}) {
  return new Intl.DateTimeFormat(language, options).format(new Date(iso));
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

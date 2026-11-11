"""Tests for annotheca.bibtex."""

from annotheca import bibtex

_SOURCE = r"""
@inproceedings{vaswani2017attention,
  title = {Attention Is All You Need},
  author = {Vaswani, Ashish and Shazeer, Noam},
  booktitle = {Advances in Neural Information Processing Systems},
  year = {2017},
  eprint = {1706.03762},
}
@article{dupont2021,
  title = {{\'E}tude des {R}eseaux \& Graphes},
  author = {J{\'e}r{\^o}me Dupont},
  year = {2021},
  doi = {https://doi.org/10.1000/ABC.123},
}
"""


def test_parse_reads_every_entry():
    first, second = bibtex.parse(_SOURCE)
    assert first.entry_type == 'inproceedings'
    assert first.citekey == 'vaswani2017attention'
    assert first.fields['year'] == '2017'
    assert bibtex.make_citekey(second.fields) == 'dupont2021etude'


def test_parse_handles_quotes_macros_and_concatenation():
    (entry,) = bibtex.parse(
        '@comment{ignored} @Article{ key ,\n TITLE = "A {"}B " # {C},'
        '\n month = jun, year = 2020 }')
    assert entry.citekey == 'key'
    assert entry.fields == {'title': 'A {"}B C', 'month': 'jun',
                            'year': '2020'}


def test_identifiers():
    first, second = bibtex.parse(_SOURCE)
    assert first.arxiv_id == '1706.03762'
    assert first.doi is None
    assert second.doi == '10.1000/abc.123'
    assert first.title_key == 'attentionisallyouneed'


def test_arxiv_id_from_arxiv_doi():
    entry = bibtex.Entry('misc', 'k', {'doi': '10.48550/arXiv.2106.09685'})
    assert entry.arxiv_id == '2106.09685'


def test_find_identifiers_in_free_text():
    assert bibtex.find_doi('see https://doi.org/10.1145/3292500.3330701.') == (
        '10.1145/3292500.3330701')
    assert bibtex.find_arxiv_id('arXiv:2106.09685v2') == '2106.09685'
    assert bibtex.find_arxiv_id('arxiv.org/abs/hep-th/9901001') == (
        'hep-th/9901001')
    assert bibtex.find_arxiv_id('Proc. CVPR, pp. 770-778, 2016.') is None


def test_format_round_trips():
    entry = bibtex.parse(_SOURCE)[0]
    formatted = bibtex.format_entry(entry)
    assert formatted.splitlines()[:3] == [
        '@inproceedings{vaswani2017attention,',
        '  author = {Vaswani, Ashish and Shazeer, Noam},',
        '  title = {Attention Is All You Need},',
    ]
    assert bibtex.parse(formatted) == [entry]


def test_split_authors_and_plain():
    assert bibtex.split_authors('Doe, J. and {Smith}, A.') == [
        'Doe, J.', 'Smith, A.']
    assert bibtex.plain('{GANs} \\& {Diffusion}') == 'GANs & Diffusion'
    assert bibtex.plain("J{\\'e}r{\\^o}me Gar\\c{c}on") == 'Jérôme Garçon'
    assert bibtex.plain('Scheme Using $\\rm{SPHINCS}^+$') == (
        'Scheme Using SPHINCS+')
    assert bibtex.plain('\\emph{Deep} nets in $O(n^2)$, for 5\\$') == (
        'Deep nets in O(n^2), for 5$')


def test_link_prefers_the_page_url_then_doi_then_arxiv():
    first, second = bibtex.parse(_SOURCE)
    assert first.link == 'https://arxiv.org/abs/1706.03762'
    assert second.link == 'https://doi.org/10.1000/abc.123'
    page = bibtex.Entry('misc', 'k', {'url': 'https://eprint.iacr.org/1'})
    assert page.link == 'https://eprint.iacr.org/1'
    assert bibtex.Entry('misc', 'k', {}).link == ''

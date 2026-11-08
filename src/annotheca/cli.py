"""Command line entry point: starts the server and opens the browser."""

import argparse
import os
import pathlib
import socket
import threading
import webbrowser

import uvicorn

from annotheca import __version__
from annotheca import api
from annotheca import library


def main(argv: list[str] | None = None) -> None:
    """Runs Annotheca until interrupted."""
    parser = argparse.ArgumentParser(
        prog='annotheca',
        description='Manage the bibliography of your research projects.')
    parser.add_argument('--port', type=int, default=8737,
                        help='local port to serve on (default: %(default)s)')
    parser.add_argument('--data-dir', type=pathlib.Path,
                        default=_default_data_dir(),
                        help='where the library is stored'
                        ' (default: %(default)s)')
    parser.add_argument('--no-browser', action='store_true',
                        help='do not open the interface in a browser')
    parser.add_argument('--version', action='version', version=__version__)
    args = parser.parse_args(argv)

    url = f'http://127.0.0.1:{args.port}'
    if _port_in_use(args.port):
        print(f'Port {args.port} is busy: opening the running instance.'
              ' Use --port if another program holds it.')
        if not args.no_browser:
            webbrowser.open(url)
        return
    app = api.create_app(library.Library(args.data_dir))
    print(f'Annotheca is running at {url} (library: {args.data_dir}).'
          ' Press Ctrl+C to stop.')
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')


def _default_data_dir() -> pathlib.Path:
    """$ANNOTHECA_HOME, else the XDG data directory."""
    if home := os.environ.get('ANNOTHECA_HOME'):
        return pathlib.Path(home)
    xdg = os.environ.get('XDG_DATA_HOME')
    return pathlib.Path(xdg or pathlib.Path.home() / '.local' / 'share',
                        'annotheca')


def _port_in_use(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(('127.0.0.1', port)) == 0

"""Command line entry point.

`annotheca` opens the interface; `annotheca mcp` serves the tools for AI
assistants; `annotheca connect` makes those tools available to Claude.
"""

import argparse
import json
import os
import pathlib
import platform
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser

import uvicorn

from annotheca import __version__
from annotheca import api
from annotheca import library
from annotheca import mcp_server


def main(argv: list[str] | None = None) -> None:
    """Runs the requested command."""
    parser = argparse.ArgumentParser(
        prog='annotheca',
        description='Manage the bibliography of your research projects.')
    parser.add_argument('--data-dir', type=pathlib.Path,
                        help='where the library is stored (default: '
                        f'{_default_data_dir()})')
    parser.add_argument('--port', type=int, default=8737,
                        help='local port of the interface (default: '
                        '%(default)s)')
    parser.add_argument('--no-browser', action='store_true',
                        help='do not open the interface in a browser')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', metavar='COMMAND')
    commands.add_parser(
        'mcp', help='serve the tools for AI assistants over MCP (stdio)')
    commands.add_parser(
        'connect', help='make the tools available to Claude Code and Claude '
        'Desktop, and show how to add them to other assistants')
    args = parser.parse_args(argv)

    data_dir = args.data_dir or _default_data_dir()
    if args.command == 'mcp':
        mcp_server.create_server(library.Library(data_dir)).run()
    elif args.command == 'connect':
        _connect(args.data_dir)
    else:
        _serve(data_dir, args.port, open_browser=not args.no_browser)


def _serve(data_dir: pathlib.Path, port: int, open_browser: bool) -> None:
    url = f'http://127.0.0.1:{port}'
    if _port_in_use(port):
        print(f'Port {port} is busy: opening the running instance.'
              ' Use --port if another program holds it.')
        if open_browser:
            webbrowser.open(url)
        return
    app = api.create_app(library.Library(data_dir))
    print(f'Annotheca is running at {url} (library: {data_dir}).'
          ' Press Ctrl+C to stop.')
    if open_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')


def _connect(data_dir: pathlib.Path | None) -> None:
    """Registers `annotheca mcp` with the Claude applications found."""
    data_args = ['--data-dir', str(data_dir.resolve())] if data_dir else []
    command = [sys.executable, '-m', 'annotheca', *data_args, 'mcp']
    server = {'command': command[0], 'args': command[1:]}

    if claude := shutil.which('claude'):
        subprocess.run([claude, 'mcp', 'remove', '--scope', 'user',
                        'annotheca'], capture_output=True, check=False)
        subprocess.run([claude, 'mcp', 'add', '--scope', 'user', 'annotheca',
                        '--', *command], capture_output=True, check=True)
        print('Connected to Claude Code (all projects).')

    config_path = _claude_desktop_config()
    if config_path.parent.is_dir():
        config = (json.loads(config_path.read_text())
                  if config_path.exists() else {})
        config.setdefault('mcpServers', {})['annotheca'] = server
        config_path.write_text(json.dumps(config, indent=2) + '\n')
        print('Connected to Claude Desktop; restart it to load the tools.')

    print('\nFor other assistants (Cursor, Codex, Gemini CLI...), add this '
          'MCP server to their configuration:\n'
          + json.dumps({'mcpServers': {'annotheca': server}}, indent=2))


def _claude_desktop_config() -> pathlib.Path:
    if platform.system() == 'Darwin':
        root = pathlib.Path.home() / 'Library' / 'Application Support'
    elif platform.system() == 'Windows':
        root = pathlib.Path(os.environ['APPDATA'])
    else:
        root = pathlib.Path(os.environ.get('XDG_CONFIG_HOME')
                            or pathlib.Path.home() / '.config')
    return root / 'Claude' / 'claude_desktop_config.json'


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

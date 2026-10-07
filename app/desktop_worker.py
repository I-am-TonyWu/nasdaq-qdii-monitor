"""Bundled desktop/scheduled entry point; choose writable data before imports."""
import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Nasdaq QDII desktop worker')
    parser.add_argument('--home', required=True)
    parser.add_argument('command', choices=['serve', 'collect', 'funds', 'retry', 'freeze', 'report', 'backup', 'status', 'weekly'])
    parser.add_argument('--port', type=int)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    home = Path(args.home).expanduser().resolve()
    home.mkdir(parents=True, exist_ok=True)
    os.environ['NASDAQ_QDII_HOME'] = str(home)
    sys.argv = ['nasdaq-qdii', args.command]
    if args.port is not None:
        if not 1024 <= args.port <= 65535:
            parser.error('port must be between 1024 and 65535')
        sys.argv += ['--port', str(args.port)]
    if args.force:
        sys.argv.append('--force')
    from .cli import main as cli_main
    cli_main()


if __name__ == '__main__':
    main()

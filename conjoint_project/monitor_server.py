"""Run oTree with separately authenticated recruitment-monitor routes."""

import argparse
from importlib.metadata import version
import os


SUPPORTED_OTREE_VERSION = '6.0.15'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('addrport', nargs='?', help='Optional address:port or port')
    args = parser.parse_args(argv)

    if version('otree') != SUPPORTED_OTREE_VERSION:
        raise RuntimeError(
            'The monitoring launcher requires the tested oTree version '
            f'{SUPPORTED_OTREE_VERSION}.'
        )

    # Match the normal production CLI before importing oTree's runtime modules.
    os.environ['USE_TIMEOUT_WORKER'] = '1'
    from otree.main import setup

    setup()

    from otree.asgi import app
    from otree.cli.prodserver1of2 import Command
    from monitor_routes import MONITOR_ROUTE_NAMES, build_monitor_routes

    # Retain the original app, transaction middleware, authentication, and
    # lifespan. The production command also retains oTree's timeout subprocess.
    other_routes = [
        route for route in app.router.routes
        if getattr(route, 'name', None) not in MONITOR_ROUTE_NAMES
    ]
    app.router.routes[:] = build_monitor_routes() + other_routes
    Command().handle(addrport=args.addrport)


if __name__ == '__main__':
    main()

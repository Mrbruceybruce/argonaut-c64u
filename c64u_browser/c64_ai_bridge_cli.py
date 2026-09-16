# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Run the paired C64 listener from a private configuration file."""
import argparse

from .c64_ai_bridge_config import load_bridge_config
from .c64_ai_chat import C64ChatGateway
from .c64_ai_service import paired_c64_server


def main(argv=None):
    parser = argparse.ArgumentParser(description='Argonaut paired C64 AI bridge')
    parser.add_argument('--config', required=True)
    args = parser.parse_args(argv)
    config = load_bridge_config(args.config)
    server = paired_c64_server(
        C64ChatGateway(config.model), config.token, config.host,
        config.allowed_clients, config.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

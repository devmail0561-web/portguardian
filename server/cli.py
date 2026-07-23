"""CLI pour lancer le serveur PortGuardian."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="portguardian-server",
        description="PortGuardian Server — dashboard web centralisé",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Adresse d'écoute (défaut: 0.0.0.0)")
    parser.add_argument("-p", "--port", type=int, default=8600, help="Port (défaut: 8600)")
    parser.add_argument("--api-key", metavar="KEY", help="Clé API requise pour les agents")
    parser.add_argument("--debug", action="store_true", help="Mode debug Flask")

    args = parser.parse_args()

    from server.app import create_app
    application = create_app(api_key=args.api_key)

    print(f"PortGuardian Server démarré sur http://{args.host}:{args.port}")
    print(f"API key: {'configurée' if args.api_key else 'désactivée (accès libre)'}")
    print(f"Endpoint agents: POST http://{args.host}:{args.port}/api/report")

    application.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()

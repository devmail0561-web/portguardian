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
    parser.add_argument("--host", default="127.0.0.1", help="Adresse d'écoute (défaut: 127.0.0.1)")
    parser.add_argument("-p", "--port", type=int, default=8600, help="Port (défaut: 8600)")
    parser.add_argument("--api-key", metavar="KEY", help="Clé API requise pour les agents")
    parser.add_argument("--password", metavar="PASS", help="Mot de passe pour l'interface web (sauvegardé hashé)")
    parser.add_argument("--no-auth", action="store_true", help="Désactiver l'authentification (localhost uniquement)")
    parser.add_argument("--secret-key", metavar="KEY", help="Clé secrète pour les sessions (auto-générée si absente)")
    parser.add_argument("--allow-remote", action="store_true", help="Écouter sur 0.0.0.0 (exposé au réseau)")
    parser.add_argument("--debug", action="store_true", help="Mode debug Flask")

    args = parser.parse_args()

    host = args.host

    if args.allow_remote:
        host = "0.0.0.0"
        if args.debug:
            print("ERREUR: --debug est interdit avec --allow-remote (debugger Werkzeug accessible depuis le réseau).")
            sys.exit(1)
        if args.no_auth:
            print("ERREUR: --no-auth est interdit avec --allow-remote (risque de sécurité).")
            sys.exit(1)
        print("⚠  ATTENTION: Serveur exposé au réseau (--allow-remote)")
        print("   Assurez-vous que --api-key est définie et que le réseau est de confiance.")
        if not args.api_key:
            print("   ⚠  Pas d'API key configurée — les agents pourront reporter sans authentification!")

    if args.no_auth:
        if host not in ("127.0.0.1", "localhost", "::1"):
            print("ERREUR: --no-auth est autorisé uniquement en écoute locale (127.0.0.1).")
            sys.exit(1)
    else:
        from server.auth import load_password_hash
        if not args.password and not load_password_hash():
            print("ERREUR: Aucun mot de passe configuré.")
            print()
            print("Options:")
            print("  --password <mdp>   Définir un mot de passe (sauvegardé hashé)")
            print("  --no-auth          Désactiver l'auth (localhost uniquement, usage éducatif)")
            print()
            print("Exemple:")
            print("  ./portguardian server --no-auth")
            print("  ./portguardian server --password secret123")
            sys.exit(1)

    from server.app import create_app
    application = create_app(
        api_key=args.api_key,
        password=args.password,
        secret_key=args.secret_key,
        no_auth=args.no_auth,
    )

    print(f"PortGuardian Server démarré sur http://{host}:{args.port}")
    if args.no_auth:
        print(f"Auth: désactivée (mode local/éducatif)")
    else:
        print(f"Auth web: protégé par mot de passe")
    print(f"API key agents: {'configurée' if args.api_key else 'désactivée (accès libre)'}")
    print(f"Endpoint agents: POST http://{host}:{args.port}/api/report")
    print(f"Dashboard: http://{host}:{args.port}/")

    application.run(host=host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()

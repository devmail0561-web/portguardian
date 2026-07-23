"""CLI pour le daemon PortGuardian."""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from daemon.agent import Agent
from daemon.config import DaemonConfig


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_run(args: argparse.Namespace) -> None:
    """Lance l'agent en mode daemon."""
    config = DaemonConfig.load(Path(args.config) if args.config else None)

    if args.interval:
        config.interval = args.interval
    if args.server:
        config.server_url = args.server
    if args.api_key:
        config.api_key = args.api_key
    if args.webhook:
        config.webhook_url = args.webhook
    if args.slack:
        config.slack_webhook_url = args.slack
    if args.hostname:
        config.hostname = args.hostname

    setup_logging(args.verbose)
    agent = Agent(config)

    def handle_stop(signum, frame):
        agent.stop()

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    asyncio.run(agent.run())


def cmd_once(args: argparse.Namespace) -> None:
    """Exécute un seul cycle de collecte."""
    config = DaemonConfig.load(Path(args.config) if args.config else None)

    if args.server:
        config.server_url = args.server
    if args.api_key:
        config.api_key = args.api_key

    setup_logging(args.verbose)
    agent = Agent(config)
    snapshot = asyncio.run(agent.run_once())

    if args.json:
        import json
        print(json.dumps(snapshot, indent=2, ensure_ascii=False))
    else:
        print(f"Host: {snapshot['hostname']}")
        print(f"Connexions: {snapshot['connections_total']}")
        print(f"Ports en écoute: {snapshot['listening_total']}")
        if snapshot.get("events"):
            print(f"Événements: {len(snapshot['events'])}")
            for e in snapshot["events"]:
                print(f"  [{e['severity']}] {e['message']}")


def cmd_init_config(args: argparse.Namespace) -> None:
    """Génère un fichier de configuration par défaut."""
    config = DaemonConfig()
    path = Path(args.output) if args.output else None
    config.save(path)
    target = path or Path("~/.config/portguardian/daemon.json").expanduser()
    print(f"Configuration créée: {target}")
    print("Éditez ce fichier pour configurer les notifications et le serveur central.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="portguardian-daemon",
        description="PortGuardian Agent — surveillance autonome des ports réseau",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Mode verbeux")
    parser.add_argument("-c", "--config", metavar="FILE", help="Fichier de configuration")

    sub = parser.add_subparsers(dest="command")

    # run
    p_run = sub.add_parser("run", help="Lancer l'agent en continu")
    p_run.add_argument("-i", "--interval", type=int, help="Intervalle en secondes")
    p_run.add_argument("--server", metavar="URL", help="URL du serveur central")
    p_run.add_argument("--api-key", metavar="KEY", help="Clé API du serveur")
    p_run.add_argument("--webhook", metavar="URL", help="URL de webhook pour notifications")
    p_run.add_argument("--slack", metavar="URL", help="URL du webhook Slack")
    p_run.add_argument("--hostname", help="Nom d'hôte personnalisé")

    # once
    p_once = sub.add_parser("once", help="Exécuter un seul cycle de collecte")
    p_once.add_argument("--json", action="store_true", help="Sortie JSON")
    p_once.add_argument("--server", metavar="URL", help="URL du serveur central")
    p_once.add_argument("--api-key", metavar="KEY", help="Clé API du serveur")

    # init
    p_init = sub.add_parser("init", help="Générer la configuration par défaut")
    p_init.add_argument("-o", "--output", metavar="FILE", help="Chemin du fichier de sortie")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "once":
        cmd_once(args)
    elif args.command == "init":
        cmd_init_config(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

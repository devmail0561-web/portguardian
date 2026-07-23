#!/usr/bin/env python3
"""Point d'entrée de PortGuardian."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import LOG_DIR, EXPORT_DIR, SCREENSHOTS_DIR


def ensure_directories() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def _run_cli(args) -> int:
    """Mode non-interactif (--once, --list-listen, etc.)."""
    from core.ports import get_all_connections, get_listening_ports
    from core.exporter import export_connections

    if args.list_listen:
        conns = get_listening_ports()
        for c in conns:
            print(f"{c.protocol:<6} {c.local_addr}:{c.local_port}  {c.process_name} (PID {c.pid})")
        return 0

    conns = get_all_connections()

    if args.output or args.format:
        fmt = args.format or "json"
        if args.output:
            # Export vers le fichier spécifié
            import json, csv
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            from core.exporter import _connection_to_dict
            data = [_connection_to_dict(c) for c in conns]
            if fmt == "json":
                output.write_text(
                    __import__("json").dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            elif fmt == "csv":
                import csv as _csv
                from core.exporter import EXPORT_FIELDS
                with open(output, "w", newline="", encoding="utf-8") as f:
                    w = _csv.DictWriter(f, fieldnames=EXPORT_FIELDS)
                    w.writeheader()
                    w.writerows(data)
            else:
                lines = [
                    f"{c.protocol:<6} {c.local_addr}:{c.local_port}  "
                    f"{c.remote_addr or '*'}  {c.status}  {c.process_name} (PID {c.pid})"
                    for c in conns
                ]
                output.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"Exporté: {output} ({len(conns)} entrées)")
        else:
            # Sortie sur stdout
            import json as _json
            from core.exporter import _connection_to_dict
            data = [_connection_to_dict(c) for c in conns]
            if fmt == "json":
                print(_json.dumps(data, indent=2, ensure_ascii=False))
            elif fmt == "csv":
                import csv as _csv, io
                from core.exporter import EXPORT_FIELDS
                buf = io.StringIO()
                w = _csv.DictWriter(buf, fieldnames=EXPORT_FIELDS)
                w.writeheader()
                w.writerows(data)
                print(buf.getvalue(), end="")
            else:
                for c in conns:
                    print(
                        f"{c.protocol:<6} {c.local_addr}:{c.local_port}  "
                        f"{c.remote_addr or '*'}  {c.status}  {c.process_name} (PID {c.pid})"
                    )
        return 0

    # --once sans format : affichage texte simple sur stdout
    for c in conns:
        print(
            f"{c.protocol:<6} {c.local_addr}:{c.local_port:<6} "
            f"{c.status:<12} {c.process_name} (PID {c.pid})"
        )
    return 0


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="PortGuardian — surveillance des ports réseau",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples:\n"
            "  portguardian                        # TUI interactif\n"
            "  portguardian --once                 # liste toutes les connexions\n"
            "  portguardian --list-listen          # ports en écoute uniquement\n"
            "  portguardian --once --format json   # sortie JSON sur stdout\n"
            "  portguardian --once --format csv --output /tmp/ports.csv\n"
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Mode non-interactif : affiche les connexions et quitte",
    )
    parser.add_argument(
        "--list-listen",
        action="store_true",
        help="Affiche uniquement les ports en écoute (implique --once)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv", "txt"],
        default=None,
        help="Format de sortie pour --once (défaut: txt sur stdout)",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        default=None,
        help="Fichier de sortie (sinon stdout)",
    )

    args = parser.parse_args()

    ensure_directories()

    if args.once or args.list_listen or args.format or args.output:
        sys.exit(_run_cli(args))

    from app import PortGuardianApp
    PortGuardianApp().run()


if __name__ == "__main__":
    main()

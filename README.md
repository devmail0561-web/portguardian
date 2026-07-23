# PortGuardian

**Surveillance des ports reseau, processus et services systemd en temps reel.**

PortGuardian est une application TUI (Terminal User Interface) de type htop, specialisee dans le monitoring des ports reseau, la gestion des processus et le controle des services systemd sous Linux (Ubuntu 24.04+). Construite avec Python 3.12+, Textual et psutil.

---

## Captures d'ecran

### Vue principale — tableau des connexions

![Vue principale](screenshots/screenshot_main.svg)

### Statistiques globales (`t`)

![Statistiques globales](screenshots/screenshot_stats.svg)

### Alertes et regles de securite (`A`)

![Alertes](screenshots/screenshot_alerts.svg)

### Historique des evenements reseau (`h`)

![Historique](screenshots/screenshot_history.svg)

---

## Installation

### Prerequis

- **Python 3.12** ou superieur
- **Linux** (Ubuntu 24.04+ recommande)
- **systemd** (pour la gestion des services)

### Avec venv (recommande)

```bash
git clone <url-du-depot>
cd port_listen_script
python3 -m venv venv
venv/bin/pip install -r portguardian/requirements.txt
```

### Avec uv

```bash
git clone <url-du-depot>
cd port_listen_script
uv venv venv
uv pip install -r portguardian/requirements.txt
```

### Dependances

| Paquet   | Version minimale | Role                          |
|----------|-----------------|-------------------------------|
| textual  | 0.75.0          | Interface TUI                 |
| rich     | 13.7.0          | Formatage et rendu terminal   |
| psutil   | 5.9.0           | Introspection systeme         |

---

## Utilisation

### Mode TUI interactif (recommande)

Avec les privileges root, PortGuardian peut afficher tous les processus, PIDs, chemins d'executables et gerer les services systemd :

```bash
cd portguardian/
./run.sh
```

Le script `run.sh` localise automatiquement le venv adjacent (`../venv/`) et lance l'application avec `sudo`.

### Mode non-interactif (CLI)

```bash
# Lister toutes les connexions (texte)
python3 main.py --once

# Lister uniquement les ports en ecoute
python3 main.py --list-listen

# Exporter en JSON sur stdout
python3 main.py --once --format json

# Exporter en CSV vers un fichier
python3 main.py --once --format csv --output /tmp/ports.csv

# Exporter en JSON vers un fichier
python3 main.py --once --format json --output /var/log/ports.json
```

---

## Raccourcis clavier

### Navigation principale

| Touche   | Action                                           |
|----------|--------------------------------------------------|
| `q`      | Quitter l'application                            |
| `r`      | Rafraichir manuellement les donnees              |
| `/`      | Rechercher (port, PID, nom, user, protocole)     |
| `s`      | Trier les connexions par colonne (asc/desc)      |
| `e`      | Exporter les donnees (CSV / JSON / TXT)          |
| `Escape` | Effacer le filtre actif / fermer le panneau      |
| `Ctrl+P` | Sauvegarder un screenshot SVG dans `screenshots/` |

### Securite et alertes

| Touche | Action                                              |
|--------|-----------------------------------------------------|
| `A`    | Afficher les alertes actives et gerer les regles    |
| `B`    | Capturer la baseline / afficher les deviations      |
| `b`    | Bloquer / debloquer des ports (firewall)            |

### Surveillance et statistiques

| Touche | Action                                              |
|--------|-----------------------------------------------------|
| `h`    | Historique des evenements reseau (ouvertures, etc.) |
| `t`    | Vue statistiques : top CPU/RAM, bande passante      |
| `f`    | Filtres de recherche sauvegardes                    |

### Gestion des processus

| Touche | Action                                              |
|--------|-----------------------------------------------------|
| `k`    | Envoyer SIGTERM au processus selectionne            |
| `K`    | Envoyer SIGKILL au processus selectionne            |
| `p`    | Suspendre le processus selectionne (SIGSTOP)        |
| `c`    | Reprendre le processus suspendu (SIGCONT)           |
| `S`    | Ouvrir le menu de gestion du service systemd        |

---

## Fonctionnalites

### Surveillance reseau en temps reel

- Rafraichissement automatique configurable (par defaut : 2 secondes)
- Support complet **IPv4** et **IPv6**
- Protocoles : **TCP**, **UDP**, **sockets Unix** (optionnel)
- Tous les etats de connexion : LISTEN, ESTABLISHED, TIME_WAIT, CLOSE_WAIT, SYN_SENT, etc.
- Colonne **Distant** avec resolution DNS inverse asynchrone (cache TTL 5 min)
- Colonne **Trend** : sparkline ASCII `▁▂▃▄▅▆▇█` de l'historique CPU par processus

### Securite et alertes

**Regles d'alerte configurables** (`A`)
- Creation de regles avec conditions : port exact/range, protocole, processus (exact ou `*substring`), utilisateur, exclusions (`process_not`, `user_not`)
- Severites : `critical`, `warning`, `info`
- Persistees dans `~/.config/portguardian/rules.json`
- Regles par defaut : SSH ecoute par un processus non-sshd, port < 1024 par un non-root
- Notification automatique lors d'alertes critiques

**Baseline snapshot** (`B`)
- Premier appui : sauvegarde l'etat actuel dans `~/.local/share/portguardian/baseline.json`
- Appuis suivants : affiche le nombre de connexions nouvelles / disparues
- Les entrees absentes de la baseline sont surlignees en vert dans la table

**Gestion du firewall** (`b`)
- Detection automatique du backend : **ufw** > **firewalld** > **nftables** > **iptables**
- Blocage/deblocage de ports (simple, liste, plage : `80`, `80,443`, `8000-8100`)
- Protocoles : TCP, UDP, ou les deux
- Direction : entrant, sortant, ou les deux
- Persistance automatique des regles iptables (`iptables-save`)

### Historique des evenements (`h`)

- Liste scrollable de tous les changements detectes par le watcher
- Affichage : timestamp, type d'evenement, protocole, port, processus
- Historique circulaire (500 entrees maximum)
- Bouton "Vider" pour reinitialiser

### Statistiques globales (`t`)

- Top 5 processus par CPU% avec barre de progression ASCII
- Top 5 processus par RAM% avec barre de progression ASCII
- Top processus par nombre de connexions
- Bande passante en temps reel par interface reseau (↑ envoye / ↓ recu)

### Gestion des processus

- Affichage des details complets : PID, PPID, utilisateur, groupe, CPU%, RAM, threads, uptime, ligne de commande
- Envoi de signaux avec confirmation : SIGTERM, SIGKILL, SIGSTOP, SIGCONT
- Visualisation des fichiers ouverts et des variables d'environnement

### Integration systemd

- Detection automatique du service associe a un processus
- Actions disponibles : start, stop, restart, reload, status
- Consultation des logs dans un ecran dedie scrollable (via journalctl)

### Recherche et tri

- Recherche insensible a la casse sur tous les champs (port, PID, nom, user, protocole, adresse, etat)
- **Filtres nommes et persistes** (`f`) dans `~/.config/portguardian/filters.json`
- Tri par toutes les colonnes avec choix ascendant / descendant

### Screenshots (`Ctrl+P`)

- Sauvegarde un screenshot SVG de l'ecran courant dans le repertoire `screenshots/`
- Nommage automatique horodate : `PortGuardian_YYYY-MM-DD_HH-MM.svg`
- Fonctionne correctement meme en mode `sudo` (contrairement au comportement par defaut de Textual qui ecrit dans `~/Telechargements` inaccessible en root)
- Les SVG sont separes des exports de donnees (CSV/JSON/TXT)
- Le fichier SVG peut etre ouvert dans un navigateur ou converti en PNG avec `rsvg-convert` ou Inkscape

### Export des donnees (`e`)

- Formats supportes : **CSV**, **JSON**, **TXT** (texte tabule)
- Champs exportes : protocol, local_addr, local_port, remote_addr, remote_port, status, pid, process_name, username, **cpu_percent**, **memory_percent**, **service**, **uptime**
- Fichiers horodates dans le repertoire `exports/`
- Egalement disponible en mode CLI avec `--format` et `--output`

---

## Architecture

```
portguardian/
├── run.sh                      # Script de lancement (trouve le venv, lance avec sudo)
├── main.py                     # Point d'entree — TUI interactif ou CLI (argparse)
├── app.py                      # Application Textual principale (bindings, workers)
├── config.py                   # Configuration centralisee (intervalles, chemins XDG)
├── pyproject.toml              # Metadonnees et dependances
├── requirements.txt            # Dependances pip
├── core/                       # Logique metier
│   ├── ports.py                # Collecte des connexions reseau (TCP/UDP/IPv4/IPv6/Unix)
│   ├── process.py              # Informations detaillees sur les processus psutil
│   ├── services.py             # Detection et gestion des services systemd
│   ├── search.py               # Moteur de recherche et tri des connexions
│   ├── exporter.py             # Export horodate (CSV, JSON, TXT) avec metriques
│   ├── watcher.py              # Surveillance des changements reseau (deque cap 500)
│   ├── firewall.py             # Backend firewall multi-plateforme (ufw/firewalld/nft/iptables)
│   ├── alerts.py               # Moteur de regles d'alerte configurables
│   ├── baseline.py             # Snapshot baseline et detection de deviations
│   ├── dns_cache.py            # Resolution DNS inverse asynchrone avec cache TTL
│   ├── bandwidth.py            # Suivi de la bande passante par interface
│   ├── sparkline.py            # Historique circulaire et rendu sparkline ASCII
│   ├── filters.py              # Filtres de recherche nommes et persistes
│   ├── permissions.py          # Verification des privileges root
│   └── logs.py                 # Configuration du logging applicatif
├── ui/                         # Composants de l'interface utilisateur
│   ├── dashboard.py            # Layout principal du tableau de bord
│   ├── tables.py               # Tableau interactif (sparkline, DNS, baseline highlight)
│   ├── details.py              # Panneau de details d'un processus
│   ├── dialogs.py              # Dialogues modaux (recherche, tri+sens, export, service, firewall, logs)
│   ├── history_screen.py       # Ecran historique des evenements reseau
│   ├── stats_screen.py         # Ecran statistiques globales et bande passante
│   ├── alerts_screen.py        # Ecran alertes actives et gestion des regles
│   ├── header.py               # En-tete systeme (CPU, RAM, connexions, LISTEN)
│   └── footer.py               # Pied de page avec tous les raccourcis
├── utils/                      # Utilitaires
│   ├── formatter.py            # Formatage des valeurs pour l'affichage
│   ├── helpers.py              # format_bytes, format_duration, etc.
│   ├── colors.py               # Palette de couleurs par etat/protocole
│   └── icons.py                # Icones et symboles unicode
├── tests/                      # Tests unitaires (289 tests)
│   ├── test_alerts.py          # AlertRule matching, AlertEngine evaluation
│   ├── test_baseline.py        # save/load baseline, get_deviations
│   ├── test_bandwidth.py       # BandwidthMonitor rate calculation
│   ├── test_cli.py             # Mode CLI (--once, --list-listen, --format, --output)
│   ├── test_dns_cache.py       # Cache DNS, TTL, resolution async
│   ├── test_export.py          # Export CSV/JSON/TXT avec les nouveaux champs
│   ├── test_filters.py         # FilterStore CRUD et persistance
│   ├── test_firewall.py        # parse_port_spec
│   ├── test_ports.py           # get_all_connections, protocols, deduplication
│   ├── test_process.py         # ProcessDetail, get_process_detail
│   ├── test_search.py          # filter_connections
│   ├── test_sort.py            # sort_connections par toutes les colonnes
│   ├── test_sparkline.py       # MetricHistory, HistoryStore, sparkline rendering
│   └── test_watcher.py         # NetworkWatcher event detection, history cap
├── exports/                    # Fichiers exportes (CSV/JSON/TXT horodates)
├── screenshots/                # Screenshots SVG (Ctrl+P)
└── logs/                       # Logs applicatifs (application.log)
```

### Fichiers de configuration utilisateur (XDG)

| Fichier                                              | Contenu                        |
|------------------------------------------------------|--------------------------------|
| `~/.config/portguardian/rules.json`                  | Regles d'alerte                |
| `~/.config/portguardian/filters.json`                | Filtres de recherche nommes    |
| `~/.local/share/portguardian/baseline.json`          | Snapshot baseline              |

---

## Tests

```bash
cd portguardian/
../venv/bin/python3 -m pytest tests/ -v
```

289 tests couvrant : collecte reseau, recherche/tri, export, firewall, alertes, baseline, sparklines, filtres, watcher, DNS cache, bande passante, mode CLI.

---

## FAQ

### Pourquoi certains processus affichent un PID vide ?

Sans privileges root, le systeme ne permet pas d'acceder aux informations de processus appartenant a d'autres utilisateurs. Lancez avec `sudo` pour un acces complet.

### Quel backend firewall est utilise ?

PortGuardian detecte automatiquement dans l'ordre : ufw, firewalld, nftables, iptables. Le backend actif est journalise au demarrage.

### Le screenshot ne fonctionne pas / "Failed to save screenshot" ?

L'app tourne en `sudo` (root), mais Textual par defaut essaie d'ecrire dans `~/Telechargements` qui appartient a l'utilisateur normal. PortGuardian contourne ce probleme avec `Ctrl+P` qui sauvegarde directement dans `exports/` (repertoire du projet, accessible en root). Evitez d'utiliser le raccourci `Ctrl+S` de Textual.

### Comment creer une regle d'alerte ?

Appuyez sur `A` pour ouvrir la vue alertes, puis sur `n` (ou le bouton "+ Regle") pour ouvrir le formulaire de creation. Les regles sont sauvegardees automatiquement dans `~/.config/portguardian/rules.json`.

### Comment utiliser la baseline ?

Appuyez sur `B` une premiere fois pour capturer l'etat actuel. Ensuite, toute connexion absente de la baseline sera surlignee en vert dans la table. Un nouvel appui sur `B` affiche le nombre de deviations detectees.

### Quels systemes d'exploitation sont supportes ?

PortGuardian est concu pour **Linux** avec systemd. Il est teste sur Ubuntu 24.04+. La gestion des services systemd n'est pas disponible sur macOS ou Windows.

### Le rafraichissement est-il configurable ?

Oui, modifiez les constantes dans `config.py` :

```python
REFRESH_INTERVAL: float = 2.0   # Intervalle de rafraichissement de l'interface (secondes)
WATCHER_INTERVAL: float = 1.0   # Intervalle de surveillance des changements reseau
```

### Comment ajouter PortGuardian au PATH ?

```bash
# Alias dans ~/.bashrc ou ~/.zshrc
alias portguardian='/chemin/vers/portguardian/run.sh'

# Lien symbolique
sudo ln -s /chemin/vers/portguardian/run.sh /usr/local/bin/portguardian
```

---

## Licence

Ce projet est distribue sous licence **MIT**.

```
MIT License

Copyright (c) 2024 PortGuardian Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

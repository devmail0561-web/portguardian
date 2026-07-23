"""Filtres de recherche nommés et persistés."""

import json
from dataclasses import dataclass

from config import FILTERS_FILE
from core.logs import logger


@dataclass
class SavedFilter:
    name: str
    query: str

    def to_dict(self) -> dict:
        return {"name": self.name, "query": self.query}


class FilterStore:
    """Gère les filtres nommés persistés dans FILTERS_FILE."""

    def __init__(self) -> None:
        self._filters: list[SavedFilter] = []
        self._load()

    def _load(self) -> None:
        if not FILTERS_FILE.exists():
            return
        try:
            data = json.loads(FILTERS_FILE.read_text(encoding="utf-8"))
            self._filters = [SavedFilter(**f) for f in data]
            logger.debug("FilterStore: %d filtre(s) chargé(s)", len(self._filters))
        except Exception:
            logger.exception("Erreur lors du chargement des filtres")

    def _save(self) -> None:
        FILTERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        FILTERS_FILE.write_text(
            json.dumps([f.to_dict() for f in self._filters], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @property
    def filters(self) -> list[SavedFilter]:
        return list(self._filters)

    def add(self, name: str, query: str) -> None:
        self._filters = [f for f in self._filters if f.name != name]
        self._filters.append(SavedFilter(name=name, query=query))
        self._save()

    def remove(self, name: str) -> bool:
        before = len(self._filters)
        self._filters = [f for f in self._filters if f.name != name]
        if len(self._filters) < before:
            self._save()
            return True
        return False

    def get(self, name: str) -> SavedFilter | None:
        return next((f for f in self._filters if f.name == name), None)

    def get_by_index(self, idx: int) -> SavedFilter | None:
        if 0 <= idx < len(self._filters):
            return self._filters[idx]
        return None

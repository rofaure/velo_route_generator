"""
Favoris : enregistrement et rechargement de tracés.

Principe « recette » : on ne stocke PAS la géométrie (lourde), mais les
ingrédients qui permettent de la recalculer à l'identique via BRouter —
points de passage, profil et surcharges de paramètres. Résultat : ~1 Ko par
favori au lieu de plusieurs centaines, et un rechargement en une requête.

Stockage : app/data/favorites.json (monté en volume pour survivre aux rebuilds).
"""

import json
import os
import uuid
from datetime import datetime

_DATA = os.path.join(os.path.dirname(__file__), "data")
_PATH = os.path.join(_DATA, "favorites.json")


def _read():
    if not os.path.exists(_PATH):
        return []
    try:
        with open(_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def _write(items):
    os.makedirs(_DATA, exist_ok=True)
    tmp = _PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _PATH)          # écriture atomique


def list_favorites():
    """Favoris, du plus récent au plus ancien."""
    return sorted(_read(), key=lambda d: d.get("created", ""), reverse=True)


def save_favorite(name, route, profile, profile_params, start, start_name,
                  waypoints=None, wp_names=None, terrain=None, pct_paved=None):
    """Enregistre un tracé. Renvoie l'identifiant créé."""
    items = _read()
    fav = {
        "id": uuid.uuid4().hex[:8],
        "name": (name or "Sans titre").strip()[:80],
        "created": datetime.now().isoformat(timespec="seconds"),
        "start": list(start),
        "start_name": start_name,
        "waypoints": [list(w) for w in (waypoints or [])],
        "wp_names": list(wp_names or []),
        "profile": profile,
        "profile_params": dict(profile_params or {}),
        # la « recette » : la liste de points réellement routée
        "route_waypoints": [list(w) for w in route["waypoints"]],
        "bearing": route.get("bearing"),
        # métadonnées d'affichage (évitent de recalculer pour la liste)
        "length_km": round(route["length_km"], 1),
        "ascend_m": round(route["ascend_m"]),
        "shape": route.get("shape", "Boucle"),
        "terrain": terrain,
        "pct_paved": round(pct_paved, 1) if pct_paved is not None else None,
    }
    items.append(fav)
    _write(items)
    return fav["id"]


def delete_favorite(fav_id):
    items = [d for d in _read() if d.get("id") != fav_id]
    _write(items)


def get_favorite(fav_id):
    for d in _read():
        if d.get("id") == fav_id:
            return d
    return None


def label(fav):
    """Libellé court pour une liste déroulante."""
    date = (fav.get("created") or "")[:10]
    bits = [fav.get("name", "Sans titre"),
            f"{fav.get('length_km', 0):.0f} km",
            f"{fav.get('ascend_m', 0):.0f} m D+"]
    if fav.get("terrain"):
        bits.append(fav["terrain"])
    return " · ".join(bits) + f"  ({date})"

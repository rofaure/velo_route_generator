"""
Jointure LOCALE avec le jeu de référence (cols + villages) construit une fois
par build_reference.py. Aucune requête réseau ici.
"""

import json
import os

from geo_utils import haversine

_DATA = os.path.join(os.path.dirname(__file__), "data")


def _load(name):
    path = os.path.join(_DATA, name)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            return []
    return []


_COLS = _load("cols.json")
_PLACES = _load("places.json")


def has_reference():
    """True si le jeu de référence a été construit (fichiers présents)."""
    return bool(_COLS) or bool(_PLACES)


def nearest_col(lat, lon, max_m=1200.0):
    """Col de référence le plus proche d'un point, ou None."""
    best, best_d = None, max_m
    for c in _COLS:
        d = haversine(lon, lat, c["lon"], c["lat"])
        if d < best_d:
            best, best_d = c, d
    return best


def nearest_place(lat, lon, max_m=5000.0):
    """Localite (village/ville) la plus proche d'un point, ou None."""
    best, best_d = None, max_m
    for p in _PLACES:
        d = haversine(lon, lat, p["lon"], p["lat"])
        if d < best_d:
            best, best_d = p, d
    return best


def summit_name(lat, lon, summit_ele=None, ele_tol=120.0):
    """Nom d'un sommet : col si proche (<=1.5 km) ET a la bonne altitude
    (l'ele officielle du col doit etre a +/- ele_tol de l'altitude du tracE au
    sommet, sinon c'est un faux positif) ; sinon village proche (<=5 km).

    Renvoie {'name', 'ele', 'kind': 'col'|'village'} ou None.
    """
    col = nearest_col(lat, lon, max_m=1500.0)
    if col:
        ce = col.get("ele")
        if summit_ele is None or ce is None or abs(ce - summit_ele) <= ele_tol:
            return {"name": col["name"], "ele": ce, "kind": "col"}
    p = nearest_place(lat, lon, max_m=5000.0)
    if p:
        return {"name": p["name"], "ele": None, "kind": "village"}
    return None


def villages_along_route(coords, max_m=600.0, target_samples=60):
    """Villages proches du tracé, ordonnés le long du parcours, dédupliqués."""
    if not _PLACES or not coords:
        return []
    step = max(1, len(coords) // target_samples)
    seen, result = set(), []
    for i in range(0, len(coords), step):
        lon, lat = coords[i][0], coords[i][1]
        best, best_d = None, max_m
        for p in _PLACES:
            d = haversine(lon, lat, p["lon"], p["lat"])
            if d < best_d:
                best, best_d = p, d
        if best and best["name"] not in seen:
            seen.add(best["name"])
            result.append(best["name"])
    return result

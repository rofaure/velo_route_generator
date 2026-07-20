"""
Resolution d'un lieu saisi par l'utilisateur en (lon, lat).

Accepte soit des coordonnees "lat, lon", soit une adresse libre geocodee via
Nominatim (OpenStreetMap). Le geocodage est CONTRAINT a la France + Suisse et
biaise autour du bassin lemanique, pour que "gland", "nyon", etc. tombent au
bon endroit et pas dans une autre region.
"""

import re

import requests

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")

# Boite de biais : Leman / Haute-Savoie / Pays de Gex / Chablais (lon,lat coins)
_VIEWBOX = "5.5,46.9,7.6,45.5"
_COUNTRIES = "fr,ch"


def geocode_place(text):
    """Renvoie {'lon','lat','name'} pour une adresse ou 'lat, lon'. None si echec."""
    if not text or not text.strip():
        return None

    m = _COORD_RE.match(text)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return {"lon": lon, "lat": lat, "name": f"{lat:.4f}, {lon:.4f}"}
        return None

    try:
        r = requests.get(
            _NOMINATIM,
            params={
                "q": text,
                "format": "json",
                "limit": 1,
                "countrycodes": _COUNTRIES,
                "viewbox": _VIEWBOX,
                "bounded": 0,
            },
            headers={"User-Agent": "velo-route-generator/1.0 (perso)"},
            timeout=15,
        )
        data = r.json()
        if data:
            return {
                "lon": float(data[0]["lon"]),
                "lat": float(data[0]["lat"]),
                "name": data[0].get("display_name", text).split(",")[0],
            }
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return None
    return None


def parse_location(text):
    """Version compacte : renvoie (lon, lat) ou None."""
    g = geocode_place(text)
    return (g["lon"], g["lat"]) if g else None

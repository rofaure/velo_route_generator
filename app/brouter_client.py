"""
Client HTTP minimal pour le serveur BRouter local.

Le serveur standalone n'expose PAS de mode round-trip : il fait uniquement
du point-a-point sur une liste de waypoints. La logique de boucle est donc
dans loop_generator.py ; ici on ne fait qu'appeler /brouter et parser.

Parametres HTTP supportes par le serveur (verifie dans ServerHandler.java) :
  lonlats, nogos, profile, alternativeidx, format, trackname, heading, ...
"""

import requests

import config


class BRouterError(RuntimeError):
    """Erreur de routage renvoyee par BRouter (point non mappe, pas de trace...)."""


def _build_url(lonlats, profile, fmt, heading=None, alternativeidx=0):
    # lonlats : liste de (lon, lat) -> "lon,lat|lon,lat|..."
    pts = "|".join(f"{lon:.6f},{lat:.6f}" for lon, lat in lonlats)
    params = {
        "lonlats": pts,
        "profile": profile,
        "alternativeidx": alternativeidx,
        "format": fmt,
    }
    if heading is not None:
        params["heading"] = int(heading) % 360
    return params


def route(lonlats, profile=None, fmt="gpx", heading=None, alternativeidx=0):
    """Appelle BRouter et renvoie le corps texte (gpx / geojson / csv).

    Leve BRouterError si BRouter renvoie une erreur (il repond souvent en
    HTTP 200 avec un corps texte commencant par une explication).
    """
    profile = profile or config.PROFILE
    params = _build_url(lonlats, profile, fmt, heading, alternativeidx)
    url = f"{config.BROUTER_URL}/brouter"
    try:
        r = requests.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
    except requests.RequestException as e:
        raise BRouterError(f"BRouter injoignable sur {config.BROUTER_URL} : {e}") from e

    body = r.text
    # BRouter signale ses erreurs de routage dans le corps, pas via le code HTTP.
    lowered = body[:200].lower()
    if fmt == "gpx" and "<gpx" not in body:
        raise BRouterError(body.strip()[:300] or "reponse GPX vide")
    if fmt == "geojson" and '"features"' not in body:
        raise BRouterError(body.strip()[:300] or "reponse GeoJSON vide")
    if any(k in lowered for k in ("not mapped", "no track", "cannot find", "error")):
        raise BRouterError(body.strip()[:300])
    return body


# Colonnes du format CSV (cf. MESSAGES_HEADER dans OsmTrack.java)
_CSV_COLS = [
    "Longitude", "Latitude", "Elevation", "Distance", "CostPerKm",
    "ElevCost", "TurnCost", "NodeCost", "InitialCost", "WayTags",
    "NodeTags", "Time", "Energy",
]


def parse_csv(body):
    """Transforme la sortie CSV de BRouter en liste de segments.

    Chaque segment = un dict avec au moins lon, lat, dist_m (metres), waytags.
    BRouter agrege les points consecutifs de meme way : 1 ligne = 1 troncon.
    """
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if not lines:
        return []
    # 1re ligne = en-tete
    rows = []
    for ln in lines[1:]:
        parts = ln.split("\t")
        if len(parts) < 10:
            continue
        rec = dict(zip(_CSV_COLS, parts))
        # BRouter donne lon/lat en microdegres (entiers) dans le CSV.
        try:
            lon = int(rec["Longitude"]) / 1_000_000
            lat = int(rec["Latitude"]) / 1_000_000
        except ValueError:
            # certaines versions sortent deja en degres
            lon = float(rec["Longitude"])
            lat = float(rec["Latitude"])
        rows.append({
            "lon": lon,
            "lat": lat,
            "dist_m": float(rec["Distance"] or 0),
            "waytags": rec.get("WayTags", "") or "",
        })
    return rows


def total_length_km(csv_rows):
    return sum(r["dist_m"] for r in csv_rows) / 1000.0

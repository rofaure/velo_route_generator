"""
Generation de boucles (round-trip) par-dessus le point-a-point de BRouter.

Principe (le meme que l'interface web de BRouter sous le capot) :
  1. On place quelques waypoints "via" autour du depart, sur un cercle,
     repartis a 120 degres, oriente par un azimut de depart (seed).
  2. On route  depart -> via1 -> via2 -> via3 -> depart  avec le profil route.
  3. La distance routee reelle depasse le triangle theorique -> on ajuste
     le rayon du cercle et on recommence quelques fois jusqu'a approcher
     la distance cible.
  4. En variant l'azimut seed, on obtient N boucles differentes.
"""

import math

import config
from brouter_client import route, parse_csv, total_length_km, BRouterError

_R_EARTH = 6_371_000.0  # metres


def forward(lon, lat, dist_m, bearing_deg):
    """Point destination a `dist_m` metres et `bearing_deg` depuis (lon, lat)."""
    br = math.radians(bearing_deg)
    lat1, lon1 = math.radians(lat), math.radians(lon)
    dr = dist_m / _R_EARTH
    lat2 = math.asin(
        math.sin(lat1) * math.cos(dr)
        + math.cos(lat1) * math.sin(dr) * math.cos(br)
    )
    lon2 = lon1 + math.atan2(
        math.sin(br) * math.sin(dr) * math.cos(lat1),
        math.cos(dr) - math.sin(lat1) * math.sin(lat2),
    )
    return (math.degrees(lon2), math.degrees(lat2))


def _waypoints(start, radius_m, seed_bearing):
    """Depart + 3 via sur un cercle (triangle), boucle fermee sur le depart."""
    lon0, lat0 = start
    vias = [
        forward(lon0, lat0, radius_m, seed_bearing + 120 * i)
        for i in range(3)
    ]
    return [start] + vias + [start]


def generate_loop(start, target_km, seed_bearing):
    """Genere une boucle proche de target_km pour un azimut donne.

    Renvoie un dict {bearing, length_km, waypoints, csv_rows} ou None si echec.
    """
    target_m = target_km * 1000.0
    # Estimation initiale du rayon : perimetre triangle ~ 5.2*r, on vise la cible.
    radius = target_m / 5.2
    best = None

    for _ in range(config.MAX_ITERATIONS):
        wpts = _waypoints(start, radius, seed_bearing)
        try:
            csv_rows = parse_csv(
                route(wpts, fmt="csv", heading=seed_bearing)
            )
        except BRouterError:
            # direction bouchee (eau, cul-de-sac...) : on abandonne cet azimut
            return None
        if not csv_rows:
            return None

        length_km = total_length_km(csv_rows)
        cand = {
            "bearing": seed_bearing,
            "length_km": length_km,
            "waypoints": wpts,
            "csv_rows": csv_rows,
        }
        # on garde la meilleure approximation rencontree
        if best is None or abs(length_km - target_km) < abs(best["length_km"] - target_km):
            best = cand

        err = (length_km - target_km) / target_km
        if abs(err) <= config.TOLERANCE:
            return cand
        # ajustement proportionnel du rayon (borne pour rester stable)
        ratio = target_km / max(length_km, 1e-6)
        ratio = min(max(ratio, 0.5), 1.8)
        radius *= ratio

    return best  # meilleure approximation meme si hors tolerance


def generate_candidates(start, target_km, n_candidates):
    """Genere n boucles en balayant les azimuts autour de la rose des vents."""
    loops = []
    for i in range(n_candidates):
        seed = (360.0 / n_candidates) * i
        loop = generate_loop(start, target_km, seed)
        if loop is not None:
            loops.append(loop)
    return loops

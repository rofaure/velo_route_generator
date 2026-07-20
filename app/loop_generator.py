"""
Generation de boucles (round-trip) par-dessus le point-a-point de BRouter.

On place n_via points sur un cercle complet autour du DEPART, on route
depart -> via1 -> ... -> viaN -> depart, puis on ajuste le rayon jusqu'a
approcher la distance cible. En variant l'azimut du cercle, on obtient
plusieurs boucles concentriques variees autour du depart.

Choisir sa zone de sortie = choisir son point de depart (cf. config.START_POINTS).

Rejets automatiques : vol d'oiseau (max_gap_m), aller-retour (overlap_ratio),
distance hors cible (MAX_DIST_ERROR). On garde le candidat le plus proche de
la cible.
"""

import math

import config
from brouter_client import route_geojson, BRouterError
from geo_utils import max_gap_m, overlap_ratio, bearing, haversine

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


def _waypoints(start, radius_m, seed_bearing, n_via):
    """Depart + n_via via sur un cercle complet, boucle fermee."""
    lon0, lat0 = start
    angles = [seed_bearing + (360.0 / n_via) * i for i in range(n_via)]
    vias = [forward(lon0, lat0, radius_m, a) for a in angles]
    return [start] + vias + [start]


def _perimeter_factor(n_via):
    return n_via * 2 * math.sin(math.pi / n_via)


def generate_loop(start, target_km, seed_bearing, profile=None):
    """Genere la boucle valide la plus proche de target_km. Renvoie un dict ou None."""
    n_via = config.WAYPOINTS_PER_LOOP
    target_m = target_km * 1000.0
    radius = target_m / _perimeter_factor(n_via)
    best = None

    for _ in range(config.MAX_ITERATIONS):
        wpts = _waypoints(start, radius, seed_bearing, n_via)
        try:
            r = route_geojson(wpts, profile=profile, heading=seed_bearing)
        except BRouterError:
            return None
        coords = r["coords"]
        if not coords:
            return None
        length_km = r["length_m"] / 1000.0

        if max_gap_m(coords) > config.BEELINE_GAP_M:   # vol d'oiseau
            radius *= 0.8
            continue

        err = abs(length_km - target_km) / target_km
        ov = overlap_ratio(coords)

        if ov <= config.OVERLAP_MAX and err <= config.MAX_DIST_ERROR:
            cand = {
                "bearing": seed_bearing,
                "length_km": length_km,
                "ascend_m": r["ascend_m"],
                "total_time_s": r["total_time_s"],
                "overlap": ov,
                "waypoints": wpts,
                "coords": coords,
                "csv_rows": r["segments"],
            }
            if best is None or err < best["_err"]:
                cand["_err"] = err
                best = cand
            if err <= 0.05:
                best.pop("_err", None)
                return best

        ratio = min(max(target_km / max(length_km, 1e-6), 0.5), 1.8)
        radius *= ratio

    if best is not None:
        best.pop("_err", None)
    return best


def generate_candidates(start, target_km, n_candidates, profile=None):
    """Teste n_candidates azimuts autour du depart et renvoie les boucles retenues."""
    loops = []
    for i in range(n_candidates):
        seed = (360.0 / n_candidates) * i
        lp = generate_loop(start, target_km, seed, profile=profile)
        if lp is not None:
            lp["shape"] = "Boucle"
            loops.append(lp)
    return loops


def _route_dict(r, waypoints, seed_bearing, shape):
    return {
        "bearing": seed_bearing,
        "length_km": r["length_m"] / 1000.0,
        "ascend_m": r["ascend_m"],
        "total_time_s": r["total_time_s"],
        "overlap": None,
        "shape": shape,
        "waypoints": waypoints,
        "coords": r["coords"],
        "csv_rows": r["segments"],
    }


def generate_out_and_back(start, target_km, n_candidates, profile=None, dest=None):
    """Genere des aller-retours (le filtre anti-recouvrement ne s'applique pas).

    dest fixe : un seul aller-retour start -> dest -> start.
    dest None : demi-tour automatique dans n directions, ajuste a la distance.
    """
    results = []

    if dest is not None:
        wpts = [start, dest, start]
        try:
            r = route_geojson(wpts, profile=profile)
        except BRouterError:
            return results
        if r["coords"] and max_gap_m(r["coords"]) <= config.BEELINE_GAP_M:
            results.append(_route_dict(r, wpts, None, "Aller-retour"))
        return results

    for i in range(n_candidates):
        seed = (360.0 / n_candidates) * i
        leg = target_km * 1000.0 / 2.0  # aller ~ la moitie de la cible
        for _ in range(config.MAX_ITERATIONS):
            turn = forward(start[0], start[1], leg, seed)
            wpts = [start, turn, start]
            try:
                r = route_geojson(wpts, profile=profile, heading=seed)
            except BRouterError:
                break
            if not r["coords"]:
                break
            if max_gap_m(r["coords"]) > config.BEELINE_GAP_M:
                leg *= 0.8
                continue
            length_km = r["length_m"] / 1000.0
            err = abs(length_km - target_km) / target_km
            if err <= config.MAX_DIST_ERROR:
                results.append(_route_dict(r, wpts, seed, "Aller-retour"))
                break
            leg *= min(max(target_km / max(length_km, 1e-6), 0.5), 1.8)
    return results


def generate_all(start, target_km, n_candidates, profile=None, dest=None):
    """Melange boucles rondes et aller-retours pour maximiser le choix."""
    loops = generate_candidates(start, target_km, n_candidates, profile=profile)
    n_oab = max(2, n_candidates // 3)
    oab = generate_out_and_back(start, target_km, n_oab, profile=profile, dest=dest)
    return loops + oab


def _shape_of(coords):
    """Etiquette Boucle / Aller-retour selon le taux de recouvrement."""
    return "Aller-retour" if overlap_ratio(coords) > config.OVERLAP_MAX else "Boucle"


def generate_via_waypoints(start, waypoints, target_km, n_candidates, profile=None):
    """Genere des traces passant OBLIGATOIREMENT par tous les points de passage.

    La distance cible n'est qu'une reference : on ajoute du detour pour s'en
    approcher, mais les points de passage priment. On ne rejette pas sur la
    distance ; on trie du plus proche de la cible au plus eloigne.
    """
    routes = []
    seen = set()

    def _add(wpts, r):
        if not r["coords"] or max_gap_m(r["coords"]) > config.BEELINE_GAP_M:
            return
        key = round(r["length_m"] / 500.0)  # dedup grossier (~500 m)
        if key in seen:
            return
        seen.add(key)
        routes.append(_route_dict(r, wpts, None, _shape_of(r["coords"])))

    # 1) circuit direct (+ ordre inverse si plusieurs points) + alternatives BRouter
    seqs = [waypoints]
    if len(waypoints) > 1:
        seqs.append(list(reversed(waypoints)))
    for seq in seqs:
        base = [start] + seq + [start]
        for alt in range(2):
            try:
                r = route_geojson(base, profile=profile, alternativeidx=alt)
            except BRouterError:
                continue
            _add(base, r)

    # 2) variantes avec detour (offset perpendiculaire) pour varier + allonger
    axis = bearing(start[0], start[1], waypoints[0][0], waypoints[0][1])
    leg = haversine(start[0], start[1], waypoints[0][0], waypoints[0][1])
    for i in range(n_candidates):
        side = 1 if i % 2 == 0 else -1
        mag = 0.3 + 0.25 * (i // 2)
        mid = forward(start[0], start[1], leg * 0.5, axis)
        det = forward(mid[0], mid[1], leg * mag, axis + 90 * side)
        wpts = [start, det] + waypoints + [start]
        try:
            r = route_geojson(wpts, profile=profile, heading=axis)
        except BRouterError:
            continue
        _add(wpts, r)

    routes.sort(key=lambda d: abs(d["length_km"] - target_km))
    return routes

"""
Utilitaires geometriques, sans dependance a Streamlit ni au reseau.
Partages entre loop_generator (detection vol d'oiseau) et streamlit_app (carte).
"""

import math

from surface_audit import classify_segment

_R_EARTH = 6_371_000.0  # metres


def haversine(lon1, lat1, lon2, lat2):
    """Distance en metres entre deux points (lon/lat en degres)."""
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dl / 2) ** 2)
    return 2 * _R_EARTH * math.asin(math.sqrt(a))


def bearing(lon1, lat1, lon2, lat2):
    """Azimut (deg, 0=Nord) du point 1 vers le point 2."""
    dl = math.radians(lon2 - lon1)
    la1, la2 = math.radians(lat1), math.radians(lat2)
    y = math.sin(dl) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360


def max_gap_m(coords):
    """Plus grand ecart (m) entre deux points consecutifs d'un trace dense."""
    mx = 0.0
    for i in range(1, len(coords)):
        d = haversine(coords[i - 1][0], coords[i - 1][1], coords[i][0], coords[i][1])
        if d > mx:
            mx = d
    return mx


def overlap_ratio(coords, cell_m=60.0, min_index_gap=20):
    """Fraction du trace qui repasse sur lui-meme (aller-retour).

    On discretise le trace en cellules d'environ `cell_m` metres. Un point est
    compte comme "repasse" si sa cellule est aussi visitee par une portion
    ELOIGNEE du trace (ecart d'index > min_index_gap). Une vraie boucle ronde
    ne repasse quasiment jamais -> ratio bas. Un aller-retour repasse partout
    -> ratio eleve.
    """
    if len(coords) < 2:
        return 0.0
    dlat = cell_m / 111_320.0
    lat0 = coords[0][1]
    dlon = cell_m / (111_320.0 * max(math.cos(math.radians(lat0)), 0.1))

    cells = {}
    keys = []
    for i, c in enumerate(coords):
        k = (int(c[0] / dlon), int(c[1] / dlat))
        keys.append(k)
        cells.setdefault(k, []).append(i)

    revisited = 0
    for i, k in enumerate(keys):
        if any(abs(j - i) > min_index_gap for j in cells[k]):
            revisited += 1
    return revisited / len(coords)


def direction_arrows(coords, n=10):
    """Positions régulières le long du tracé, avec le cap local.

    Renvoie [(lat, lon, cap_deg), ...] : sert à dessiner des flèches indiquant
    le sens de circulation sur la carte.
    """
    if not coords or len(coords) < 2 or n < 1:
        return []
    cum = [0.0]
    for i in range(1, len(coords)):
        cum.append(cum[-1] + haversine(coords[i - 1][0], coords[i - 1][1],
                                       coords[i][0], coords[i][1]))
    total = cum[-1]
    if total <= 0:
        return []

    out, j = [], 1
    for k in range(1, n + 1):
        cible = total * k / (n + 1)
        while j < len(cum) - 1 and cum[j] < cible:
            j += 1
        lon1, lat1 = coords[j - 1][0], coords[j - 1][1]
        lon2, lat2 = coords[j][0], coords[j][1]
        if haversine(lon1, lat1, lon2, lat2) <= 0:
            continue
        out.append((lat2, lon2, bearing(lon1, lat1, lon2, lat2)))
    return out


def classify_terrain(length_km, ascend_m, flat_max=8.0, hilly_max=15.0):
    """Etiquette de terrain d'apres le ratio D+/km : Plat / Vallonné / Cols."""
    if length_km <= 0:
        return "?"
    ratio = ascend_m / length_km
    if ratio < flat_max:
        return "Plat"
    if ratio < hilly_max:
        return "Vallonné"
    return "Cols"


def colored_runs(coords, segments):
    """Decoupe le trace dense en troncoooons colores par categorie de surface.

    Renvoie une liste de (categorie, [(lat, lon), ...]) pretes pour folium.
    On avance en parallele le long du trace dense (coords) et de la liste des
    segments (chacun avec sa distance et son WayTags), en cumulant la distance.
    """
    if not coords:
        return []
    # bornes cumulees de distance + categorie par segment
    ends = []
    acc = 0.0
    for s in segments:
        acc += s.get("dist_m", 0.0)
        ends.append((acc, classify_segment(s.get("waytags", ""))))

    runs = []
    cum = 0.0
    seg_i = 0
    cur_cat = None
    cur_pts = []

    for i, c in enumerate(coords):
        if i > 0:
            cum += haversine(coords[i - 1][0], coords[i - 1][1], c[0], c[1])
        while ends and seg_i < len(ends) - 1 and cum > ends[seg_i][0]:
            seg_i += 1
        cat = ends[seg_i][1] if ends else "unknown"
        latlon = (c[1], c[0])
        if cat != cur_cat:
            if cur_pts:
                cur_pts.append(latlon)  # pont pour que les lignes se touchent
                runs.append((cur_cat, cur_pts))
            cur_cat = cat
            cur_pts = [latlon]
        else:
            cur_pts.append(latlon)
    if cur_pts:
        runs.append((cur_cat, cur_pts))
    return runs

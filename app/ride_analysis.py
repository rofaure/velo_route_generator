"""
Analyse locale d'un tracé (aucun réseau) à partir de sa géométrie dense
[lon, lat, altitude]. Sert au résumé de sortie et à la classification fine
du terrain.

- climbs()          : ascensions soutenues (longueur, D+, pente moyenne)
- steep_descents()  : descentes raides (vigilance)
- terrain_type()    : Plat / Vallonné / Cols (distinction fine)
- elevation_series(): profil altimétrique (distance vs altitude) pour le graphe
- estimate_ride()   : temps, eau, gels selon distance + D+ (réglable)
"""

from geo_utils import haversine


def _cumdist_elev(coords):
    d = [0.0]
    e = [coords[0][2] if len(coords[0]) > 2 else 0.0]
    for i in range(1, len(coords)):
        d.append(d[-1] + haversine(coords[i - 1][0], coords[i - 1][1],
                                   coords[i][0], coords[i][1]))
        e.append(coords[i][2] if len(coords[i]) > 2 else e[-1])
    return d, e


def _smooth(values, window=4):
    n = len(values)
    out = []
    for i in range(n):
        lo, hi = max(0, i - window), min(n, i + window + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return out


def climbs(coords, min_gain=80.0, min_len_m=500.0, dip_tol=25.0):
    """Segmente les ascensions soutenues. Renvoie une liste de dicts."""
    if len(coords) < 3:
        return []
    d, e = _cumdist_elev(coords)
    e = _smooth(e)
    n = len(e)
    res = []
    i = 0
    while i < n - 1:
        # descendre jusqu'au creux (début potentiel de montée)
        while i < n - 1 and e[i + 1] <= e[i]:
            i += 1
        start = peak = i
        j = i
        while j < n - 1:
            if e[j + 1] >= e[peak]:
                peak = j + 1
                j += 1
            elif e[peak] - e[j + 1] <= dip_tol:   # petit replat/creux toléré
                j += 1
            else:
                break
        gain = e[peak] - e[start]
        length = d[peak] - d[start]
        if gain >= min_gain and length >= min_len_m:
            res.append({
                "start_km": d[start] / 1000.0,
                "top_km": d[peak] / 1000.0,
                "length_km": length / 1000.0,
                "gain_m": gain,
                "avg_grade_pct": 100.0 * gain / max(length, 1.0),
                "top_lat": coords[peak][1],
                "top_lon": coords[peak][0],
                "top_ele_m": e[peak],
            })
        i = max(peak, i + 1)
    return res


def steep_descents(coords, min_drop=80.0, min_len_m=500.0, min_grade_pct=7.0):
    """Descentes raides (vigilance) : réutilise climbs sur l'altitude inversée."""
    inv = [[c[0], c[1], -(c[2] if len(c) > 2 else 0.0)] for c in coords]
    out = []
    for c in climbs(inv, min_gain=min_drop, min_len_m=min_len_m):
        if c["avg_grade_pct"] >= min_grade_pct:
            out.append({
                "start_km": c["start_km"], "length_km": c["length_km"],
                "drop_m": c["gain_m"], "avg_grade_pct": c["avg_grade_pct"],
                "lat": c["top_lat"], "lon": c["top_lon"],
            })
    return out


def terrain_type(coords, distance_km, ascend_m):
    """Classification fine : Plat / Vallonné / Cols."""
    cl = climbs(coords)
    max_gain = max((c["gain_m"] for c in cl), default=0.0)
    dpk = ascend_m / max(distance_km, 1e-6)
    if max_gain >= 250.0 or dpk >= 18.0:
        return "Cols"
    if dpk >= 8.0 or len(cl) >= 2:
        return "Vallonné"
    return "Plat"


def elevation_series(coords, n_points=200):
    """Profil altimétrique échantillonné : (distances_km[], altitudes_m[])."""
    if len(coords) < 2:
        return [], []
    d, e = _cumdist_elev(coords)
    e = _smooth(e)
    n = len(d)
    if n <= n_points:
        return [x / 1000.0 for x in d], e
    step = n / n_points
    xs, ys = [], []
    for k in range(n_points):
        idx = int(k * step)
        xs.append(d[idx] / 1000.0)
        ys.append(e[idx])
    xs.append(d[-1] / 1000.0)
    ys.append(e[-1])
    return xs, ys


def estimate_ride(distance_km, ascend_m, speed_flat=27.0, speed_hilly=20.0,
                  water_lph=0.6, gel_gph=45.0, gel_g=25.0):
    """Estime temps / eau / gels. La vitesse s'interpole selon le D+/km."""
    dpk = ascend_m / max(distance_km, 1e-6)
    t = min(max((dpk - 5.0) / (15.0 - 5.0), 0.0), 1.0)  # 5 m/km plat -> 15 vallonné
    speed = speed_flat + (speed_hilly - speed_flat) * t
    time_h = distance_km / max(speed, 1e-6)
    return {
        "dplus_per_km": dpk,
        "speed_kmh": speed,
        "time_h": time_h,
        "water_l": time_h * water_lph,
        "gels": time_h * gel_gph / max(gel_g, 1.0),
    }


# ----------------------------------------------------------------------
# Profil altimétrique coloré par pente (style profil de col)
# ----------------------------------------------------------------------
# (borne_basse, borne_haute, libellé, couleur)
_GRAD_BINS = [
    (-1e9, 0.0, "Descente / plat", "#4a90d9"),
    (0.0, 3.0, "0-3 %", "#8bc34a"),
    (3.0, 6.0, "3-6 %", "#f9d423"),
    (6.0, 9.0, "6-9 %", "#fb8c00"),
    (9.0, 1e9, "> 9 %", "#c62828"),
]
CAT_ORDER = [b[2] for b in _GRAD_BINS]
CAT_COLORS = {b[2]: b[3] for b in _GRAD_BINS}


def _grad_cat(grad):
    for lo, hi, name, color in _GRAD_BINS:
        if lo <= grad < hi:
            return name, color
    return _GRAD_BINS[-1][2], _GRAD_BINS[-1][3]


def elevation_profile(coords, n_points=220):
    """Points du profil pour le graphe : km, alt, pente, catégorie, couleur, seg.

    `seg` regroupe les points consécutifs de même catégorie de pente (pour un
    remplissage coloré continu). Les points de bascule sont dupliqués dans le
    segment précédent pour que les aires se touchent (pas de trou blanc).
    """
    xs, ys = elevation_series(coords, n_points)
    rows = []
    seg = 0
    prev_cat = None
    for i in range(len(xs)):
        if i == 0:
            grad = 0.0
        else:
            dx = (xs[i] - xs[i - 1]) * 1000.0
            grad = 100.0 * (ys[i] - ys[i - 1]) / dx if dx > 0 else 0.0
        cat, color = _grad_cat(grad)
        if prev_cat is not None and cat != prev_cat:
            seg += 1
            rows.append({"km": xs[i], "alt": ys[i], "grad": grad,
                         "cat": prev_cat, "color": CAT_COLORS[prev_cat], "seg": seg - 1})
        prev_cat = cat
        rows.append({"km": xs[i], "alt": ys[i], "grad": grad,
                     "cat": cat, "color": color, "seg": seg})
    return rows


def format_hm(time_h):
    """Convertit des heures décimales en 'H h MM'."""
    h = int(time_h)
    m = int(round((time_h - h) * 60))
    if m == 60:
        h += 1
        m = 0
    return f"{h} h {m:02d}"

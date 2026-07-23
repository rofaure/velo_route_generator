"""
Vent : récupération d'une prévision (Open-Meteo) et analyse d'un tracé.

C'est la SEULE donnée de l'application qui ne peut pas être pré-ingérée :
une prévision est par nature actuelle. Le réseau n'est donc sollicité que si
l'utilisateur active l'option ; sans elle, l'application reste hors-ligne.

Convention météo : `direction_deg` est la direction d'OÙ VIENT le vent
(0 = nord, 90 = est). Un cycliste au cap 0 (plein nord) avec un vent venant
du nord a donc le vent de face.
"""

from datetime import datetime, timedelta

import requests

from geo_utils import haversine, bearing

_API = "https://api.open-meteo.com/v1/forecast"

_CARDINAUX = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]


class WindError(RuntimeError):
    """Prévision indisponible (réseau, API, données manquantes)."""


def cardinal(deg):
    """Point cardinal (français) correspondant à un azimut."""
    return _CARDINAUX[int((deg % 360) / 22.5 + 0.5) % 16]


def fetch_wind(lat, lon, when=None, timeout=12):
    """Prévision de vent la plus proche de `when` (datetime, défaut = maintenant).

    Renvoie {'speed_kmh', 'gusts_kmh', 'direction_deg', 'cardinal', 'time'}.
    """
    when = when or datetime.now()
    try:
        r = requests.get(_API, timeout=timeout, params={
            "latitude": round(lat, 4), "longitude": round(lon, 4),
            "hourly": "wind_speed_10m,wind_direction_10m,wind_gusts_10m",
            "wind_speed_unit": "kmh", "timezone": "auto", "forecast_days": 3,
        })
        r.raise_for_status()
        h = r.json()["hourly"]
        times = h["time"]
    except (requests.RequestException, ValueError, KeyError) as e:
        raise WindError(f"prévision indisponible : {e}") from e

    target = when.strftime("%Y-%m-%dT%H:00")
    idx = min(range(len(times)), key=lambda i: abs(
        (datetime.fromisoformat(times[i]) - when).total_seconds()))
    if times[idx][:13] != target[:13] and abs(
            (datetime.fromisoformat(times[idx]) - when).total_seconds()) > 6 * 3600:
        raise WindError("aucune heure de prévision proche")

    d = float(h["wind_direction_10m"][idx])
    return {
        "speed_kmh": float(h["wind_speed_10m"][idx]),
        "gusts_kmh": float(h["wind_gusts_10m"][idx]),
        "direction_deg": d,
        "cardinal": cardinal(d),
        "time": times[idx],
    }


def relative_angle(course_deg, wind_from_deg):
    """Écart signé (-180..180) entre le cap suivi et l'origine du vent."""
    return (wind_from_deg - course_deg + 180) % 360 - 180


def classify(course_deg, wind_from_deg):
    """« Face » / « Dos » / « Travers » pour un cap donné."""
    a = abs(relative_angle(course_deg, wind_from_deg))
    if a < 45:
        return "Face"
    if a > 135:
        return "Dos"
    return "Travers"


def analyze_route(coords, wind_from_deg):
    """Répartition du trajet en vent de face / dos / travers (en % de distance).

    Renvoie aussi `tail_last_third_pct` : part de vent favorable sur le
    dernier tiers du parcours (le moment où l'on est le plus fatigué).
    """
    if not coords or len(coords) < 2:
        return {"pct_face": 0.0, "pct_dos": 0.0, "pct_travers": 0.0,
                "tail_last_third_pct": 0.0}

    segs = []
    total = 0.0
    for i in range(1, len(coords)):
        lon1, lat1 = coords[i - 1][0], coords[i - 1][1]
        lon2, lat2 = coords[i][0], coords[i][1]
        d = haversine(lon1, lat1, lon2, lat2)
        if d <= 0:
            continue
        segs.append((d, classify(bearing(lon1, lat1, lon2, lat2), wind_from_deg)))
        total += d
    if total <= 0:
        return {"pct_face": 0.0, "pct_dos": 0.0, "pct_travers": 0.0,
                "tail_last_third_pct": 0.0}

    acc = {"Face": 0.0, "Dos": 0.0, "Travers": 0.0}
    for d, c in segs:
        acc[c] += d

    # dernier tiers du parcours
    seuil = total * 2 / 3
    cum = 0.0
    tail_last, dist_last = 0.0, 0.0
    for d, c in segs:
        cum += d
        if cum >= seuil:
            dist_last += d
            if c == "Dos":
                tail_last += d

    return {
        "pct_face": 100.0 * acc["Face"] / total,
        "pct_dos": 100.0 * acc["Dos"] / total,
        "pct_travers": 100.0 * acc["Travers"] / total,
        "tail_last_third_pct": 100.0 * tail_last / dist_last if dist_last else 0.0,
    }


def wind_score(analysis):
    """Score de confort : privilégie la fin de sortie, sans ignorer l'ensemble.

    60 % pour le vent favorable sur le dernier tiers (on est fatigué),
    40 % pour la part de vent favorable sur tout le parcours.
    """
    return 0.6 * analysis["tail_last_third_pct"] + 0.4 * analysis["pct_dos"]


def better_direction(coords, wind_from_deg):
    """Sens de parcours le plus confortable face au vent.

    Renvoie ('normal'|'inverse', gain). Un gain positif signifie que parcourir
    le tracé à l'envers est plus favorable (fin de sortie + ensemble du trajet).
    """
    fwd = wind_score(analyze_route(coords, wind_from_deg))
    rev = wind_score(analyze_route(list(reversed(coords)), wind_from_deg))
    return ("inverse", rev - fwd) if rev > fwd else ("normal", fwd - rev)


# ----------------------------------------------------------------------
# Lecture par phase de sortie (début / milieu / fin)
# ----------------------------------------------------------------------
PHASES = ("Début", "Milieu", "Fin")


def _segments_with_dist(coords, wind_from_deg):
    segs = []
    for i in range(1, len(coords)):
        lon1, lat1 = coords[i - 1][0], coords[i - 1][1]
        lon2, lat2 = coords[i][0], coords[i][1]
        d = haversine(lon1, lat1, lon2, lat2)
        if d > 0:
            segs.append((d, classify(bearing(lon1, lat1, lon2, lat2), wind_from_deg)))
    return segs


def phase_summary(coords, wind_from_deg):
    """Vent dominant sur chaque tiers du parcours.

    Renvoie [{'phase', 'km_debut', 'km_fin', 'dominant', 'pct_face',
              'pct_dos', 'pct_travers'}, ...] — pourcentages en part de
    DISTANCE de la phase (les trois totalisent 100 %).
    """
    segs = _segments_with_dist(coords, wind_from_deg)
    total = sum(d for d, _ in segs)
    if total <= 0:
        return []

    bornes = [total / 3, 2 * total / 3, total]
    acc = [{"Face": 0.0, "Dos": 0.0, "Travers": 0.0} for _ in range(3)]
    debuts, fins = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
    cum, idx = 0.0, 0
    for d, c in segs:
        while idx < 2 and cum >= bornes[idx]:
            idx += 1
            debuts[idx] = cum
        acc[idx][c] += d
        cum += d
        fins[idx] = cum

    out = []
    for i in range(3):
        tot = sum(acc[i].values())
        if tot <= 0:
            continue
        pcts = {k: 100.0 * v / tot for k, v in acc[i].items()}
        out.append({
            "phase": PHASES[i],
            "km_debut": debuts[i] / 1000.0,
            "km_fin": fins[i] / 1000.0,
            "dominant": max(pcts, key=pcts.get),
            "pct_face": pcts["Face"],
            "pct_dos": pcts["Dos"],
            "pct_travers": pcts["Travers"],
        })
    return out


def phase_sentence(phases):
    """Phrase résumant le vent au fil de la sortie, en langage courant."""
    if not phases:
        return ""
    mots = {"Face": "vent de face", "Dos": "vent dans le dos",
            "Travers": "vent de côté"}
    # regroupe les phases consécutives de même dominante
    groupes = []
    for p in phases:
        if groupes and groupes[-1][0] == p["dominant"]:
            groupes[-1][1].append(p["phase"])
        else:
            groupes.append([p["dominant"], [p["phase"]]])

    bouts = []
    for dom, noms in groupes:
        if len(noms) == 3:
            libelle = "sur toute la sortie"
        elif len(noms) == 2:
            libelle = f"{noms[0].lower()} et {noms[1].lower()} de sortie"
        else:
            libelle = {"Début": "en début de sortie", "Milieu": "à mi-parcours",
                       "Fin": "en fin de sortie"}[noms[0]]
        bouts.append(f"{mots[dom]} {libelle}")
    return ", puis ".join(bouts).capitalize() + "."

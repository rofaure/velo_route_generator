"""
Audit de revetement d'une boucle, a partir des tags renvoyes par BRouter.

Logique "medaillon" appliquee au geospatial :
  - CONFIRME  : la way porte un tag surface bitume connu           -> valid
  - INCONNU   : aucun tag surface                                  -> quarantaine
  - SUSPECT   : tag surface present mais non-bitume                -> rejete
                (ne devrait quasi jamais apparaitre : le profil roadonly
                 bloque deja ces surfaces ; sert de filet de securite)

Le profil roadonly.brf force processUnusedTags=true, donc la colonne WayTags
contient bien surface=... des qu'il est renseigne dans OSM.

Sortie : un score de confiance = part de distance en surface CONFIRMEE,
plus la liste des troncons INCONNUS a verifier avant de rouler.
"""

import re

import config

_SURFACE_RE = re.compile(r"surface=([^\s]+)")


def _surface_of(waytags):
    m = _SURFACE_RE.search(waytags or "")
    return m.group(1) if m else None


def classify_segment(waytags):
    surf = _surface_of(waytags)
    if surf is None:
        return "unknown"
    # un tag surface peut etre multi-valeur (asphalt|paved) -> on prend la 1re
    surf = surf.split("|")[0]
    if surf in config.PAVED_SURFACES:
        return "paved"
    return "suspect"


def audit(csv_rows):
    """Renvoie un rapport d'audit pour une boucle (liste de segments)."""
    dist = {"paved": 0.0, "unknown": 0.0, "suspect": 0.0}
    unknown_segments = []
    suspect_segments = []

    for r in csv_rows:
        cat = classify_segment(r["waytags"])
        dist[cat] += r["dist_m"]
        if cat == "unknown" and r["dist_m"] > 0:
            unknown_segments.append(r)
        elif cat == "suspect" and r["dist_m"] > 0:
            suspect_segments.append(r)

    total = sum(dist.values()) or 1.0
    return {
        "total_km": total / 1000.0,
        "pct_paved": 100.0 * dist["paved"] / total,
        "pct_unknown": 100.0 * dist["unknown"] / total,
        "pct_suspect": 100.0 * dist["suspect"] / total,
        "km_unknown": dist["unknown"] / 1000.0,
        "km_suspect": dist["suspect"] / 1000.0,
        # score de confiance : on penalise fortement le suspect, moderement l'inconnu
        "confidence": 100.0 * dist["paved"] / total
                      + 0.5 * (100.0 * dist["unknown"] / total),
        "unknown_segments": sorted(unknown_segments, key=lambda s: -s["dist_m"]),
        "suspect_segments": sorted(suspect_segments, key=lambda s: -s["dist_m"]),
    }


def format_report(rep, top_unknown=5):
    """Rapport lisible en console pour une boucle."""
    lines = [
        f"  Surface confirmee bitume : {rep['pct_paved']:5.1f} %",
        f"  Surface inconnue         : {rep['pct_unknown']:5.1f} %  ({rep['km_unknown']:.1f} km)",
        f"  Surface suspecte         : {rep['pct_suspect']:5.1f} %  ({rep['km_suspect']:.1f} km)",
    ]
    if rep["unknown_segments"]:
        lines.append(f"  Troncons inconnus a verifier (top {top_unknown}) :")
        for s in rep["unknown_segments"][:top_unknown]:
            hw = re.search(r"highway=([^\s]+)", s["waytags"])
            hw = hw.group(1) if hw else "?"
            lines.append(
                f"    - {s['dist_m']:6.0f} m  highway={hw:<12} "
                f"https://www.openstreetmap.org/#map=18/{s['lat']:.5f}/{s['lon']:.5f}"
            )
    if rep["suspect_segments"]:
        lines.append("  /!\\ Troncons SUSPECTS (surface non-bitume detectee) :")
        for s in rep["suspect_segments"][:top_unknown]:
            surf = _surface_of(s["waytags"]) or "?"
            lines.append(
                f"    - {s['dist_m']:6.0f} m  surface={surf:<12} "
                f"https://www.openstreetmap.org/#map=18/{s['lat']:.5f}/{s['lon']:.5f}"
            )
    return "\n".join(lines)

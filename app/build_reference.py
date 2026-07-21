"""
Ingestion ONE-SHOT du jeu de référence (cols + villages) via Overpass.

À lancer UNE SEULE FOIS (depuis le dossier app/) :
    pip install requests        # si besoin
    python build_reference.py

Génère app/data/cols.json et app/data/places.json. Ensuite l'application les
lit en local : plus AUCUNE requête en ligne au runtime (pattern « table de
dimension » : ingestion unique, puis jointure locale).

Zone couverte : Léman + Chablais + Pays de Gex + Jura sud + Aravis +
Beaufortain + Mont-Blanc + Maurienne + Valais.
"""

import json
import os
import sys

import requests

OVERPASS = "https://overpass.kumi.systems/api/interpreter"
# bbox (sud, ouest, nord, est)
BBOX = (45.0, 5.7, 46.9, 8.1)
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _query(q):
    r = requests.post(OVERPASS, data={"data": q}, timeout=200,
                      headers={"User-Agent": "velo-route-generator/1.0 (perso)"})
    r.raise_for_status()
    return r.json()


def build_cols():
    s, w, n, e = BBOX
    q = f"""[out:json][timeout:180];
(
  node["mountain_pass"="yes"]["name"]({s},{w},{n},{e});
  node["natural"="saddle"]["name"]({s},{w},{n},{e});
);
out body;"""
    cols = []
    for el in _query(q).get("elements", []):
        t = el.get("tags", {})
        name = t.get("name")
        if not name:
            continue
        ele = t.get("ele")
        try:
            ele = float(str(ele).replace(",", ".")) if ele else None
        except ValueError:
            ele = None
        cols.append({"name": name, "lat": el["lat"], "lon": el["lon"], "ele": ele})
    return cols


def build_places():
    s, w, n, e = BBOX
    q = f"""[out:json][timeout:180];
(
  node["place"~"^(city|town|village)$"]["name"]({s},{w},{n},{e});
);
out body;"""
    places = []
    for el in _query(q).get("elements", []):
        t = el.get("tags", {})
        name = t.get("name")
        if not name:
            continue
        places.append({"name": name, "lat": el["lat"], "lon": el["lon"],
                       "place": t.get("place")})
    return places


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        print("Interrogation Overpass — cols (10-60 s)…")
        cols = build_cols()
        with open(os.path.join(DATA_DIR, "cols.json"), "w", encoding="utf-8") as f:
            json.dump(cols, f, ensure_ascii=False)
        print(f"  → {len(cols)} cols enregistrés.")

        print("Interrogation Overpass — villages…")
        places = build_places()
        with open(os.path.join(DATA_DIR, "places.json"), "w", encoding="utf-8") as f:
            json.dump(places, f, ensure_ascii=False)
        print(f"  → {len(places)} localités enregistrées.")

        print("\nTerminé. Fichiers dans app/data/. Reconstruis l'app pour les charger :")
        print("  docker compose up -d --build streamlit")
    except requests.RequestException as exc:
        print(f"Erreur réseau Overpass : {exc}", file=sys.stderr)
        print("Réessaie dans quelques minutes (instance publique parfois occupée).",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

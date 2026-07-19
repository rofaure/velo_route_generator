"""
CLI du generateur de boucles velo route.

Exemples :
  python main.py                          # 8 boucles ~60 km, profil roadonly
  python main.py --distance 45 --candidates 12
  python main.py --distance 80 --keep 3   # exporte les 3 meilleures en GPX

Sortie : classement des boucles par confiance surface, puis export GPX
des meilleures dans ./output.
"""

import argparse
import os
import sys

import config
from brouter_client import route, BRouterError
from loop_generator import generate_candidates
from surface_audit import audit, format_report

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def export_gpx(loop, filename):
    """Re-demande la boucle en GPX (trace dense) et l'ecrit sur disque."""
    gpx = route(loop["waypoints"], fmt="gpx", heading=loop["bearing"])
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(gpx)
    return os.path.abspath(path)


def main():
    ap = argparse.ArgumentParser(description="Generateur de boucles velo route (no-gravel).")
    ap.add_argument("--distance", type=float, default=config.TARGET_KM, help="distance cible en km")
    ap.add_argument("--candidates", type=int, default=config.N_CANDIDATES, help="nb de directions testees")
    ap.add_argument("--keep", type=int, default=1, help="nb de boucles a exporter en GPX")
    args = ap.parse_args()

    print(f"Depart      : {config.START_NAME}  {config.START_LONLAT}")
    print(f"Cible       : {args.distance:.0f} km  |  {args.candidates} directions  |  profil '{config.PROFILE}'")
    print(f"Moteur      : {config.BROUTER_URL}\n")

    # sanity check moteur
    try:
        route([config.START_LONLAT, config.START_LONLAT], fmt="gpx")
    except BRouterError as e:
        print("!! BRouter ne repond pas correctement.")
        print(f"   Detail : {e}")
        print("   Verifie que le conteneur tourne (docker compose ps) et que la")
        print("   tuile rd5 couvrant le depart est bien dans ./segments.")
        sys.exit(1)

    print("Generation des boucles candidates...\n")
    loops = generate_candidates(config.START_LONLAT, args.distance, args.candidates)
    if not loops:
        print("Aucune boucle generee. Elargis --candidates ou verifie la tuile rd5.")
        sys.exit(1)

    # audit + tri : confiance d'abord, puis proximite a la cible
    scored = []
    for lp in loops:
        rep = audit(lp["csv_rows"])
        scored.append((lp, rep))
    scored.sort(key=lambda x: (-x[1]["confidence"], abs(x[0]["length_km"] - args.distance)))

    print("=" * 70)
    print(f"{'#':>2}  {'Azimut':>6}  {'Distance':>9}  {'Confiance':>9}  {'Bitume':>7}  {'Inconnu':>7}")
    print("-" * 70)
    for i, (lp, rep) in enumerate(scored, 1):
        print(f"{i:>2}  {lp['bearing']:>5.0f}°  {lp['length_km']:>7.1f}km  "
              f"{rep['confidence']:>7.1f}   {rep['pct_paved']:>5.1f}%  {rep['pct_unknown']:>6.1f}%")
    print("=" * 70)

    # detail + export des meilleures
    print()
    for i, (lp, rep) in enumerate(scored[:args.keep], 1):
        print(f"--- Boucle #{i}  (azimut {lp['bearing']:.0f}°, {lp['length_km']:.1f} km) ---")
        print(format_report(rep))
        fname = f"boucle_{args.distance:.0f}km_az{lp['bearing']:03.0f}_conf{rep['confidence']:02.0f}.gpx"
        try:
            path = export_gpx(lp, fname)
            print(f"  -> GPX exporte : {path}\n")
        except BRouterError as e:
            print(f"  !! export GPX echoue : {e}\n")

    print("Termine. Charge le GPX sur ton Coros Dura via l'app Coros.")
    print("Rappel honnete : 'inconnu' = revetement non tague dans OSM, a verifier")
    print("sur les liens ci-dessus avant de t'y engager (le 100% bitume garanti")
    print("n'existe pas a partir des seules donnees OSM).")


if __name__ == "__main__":
    main()

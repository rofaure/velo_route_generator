"""
Configuration centrale du générateur de boucles vélo route.
Un seul endroit à éditer pour changer le point de départ ou les défauts.
"""

# --------------------------------------------------------------------------
# POINTS DE DEPART possibles (lon, lat). Choisir son depart = choisir sa zone
# de sortie. Pour rouler en Suisse (La Cote/Vaud), partir de Nyon ou Gland.
# --------------------------------------------------------------------------
START_POINTS = {
    "Saint-Cergues (maison)": (6.318631, 46.231524),  # Boulangerie Meerpoel
    "Nyon (CH, La Cote)": (6.235, 46.383),
    "Gland (CH, La Cote)": (6.269, 46.420),
    "Divonne-les-Bains (Pays de Gex, plat)": (6.140, 46.357),
    "Thonon-les-Bains (Chablais)": (6.479, 46.371),
}

# Depart par defaut (retro-compatibilite)
START_LONLAT = START_POINTS["Saint-Cergues (maison)"]
START_NAME = "Saint-Cergues (maison)"

# --------------------------------------------------------------------------
# MOTEUR BROUTER
# --------------------------------------------------------------------------
import os
BROUTER_URL = os.environ.get("BROUTER_URL", "http://localhost:17777")
PROFILE = "roadonly"          # profil par defaut

# Type de sortie (label affiche -> nom du profil .brf dans ./profiles)
PROFILES_UI = {
    "Route classique (no-gravel)": "roadonly",
    "Plat / voies vertes": "greenway",
    "Vallonne / cols": "roadclimb",
}
REQUEST_TIMEOUT = 120         # secondes

# --------------------------------------------------------------------------
# DEFAUTS DE GENERATION
# --------------------------------------------------------------------------
TARGET_KM = 60.0              # distance cible d'une boucle
N_CANDIDATES = 8             # nombre de directions testees (boucles candidates)
TOLERANCE = 0.15             # ecart max accepte vs cible (0.15 = +/-15%)
MAX_ITERATIONS = 6           # iterations de convergence du rayon par boucle

# Ecart max (m) entre 2 points du trace avant de considerer un segment "a vol
# d'oiseau" (point non routable, ex. traversee de lac) et de rejeter la boucle.
BEELINE_GAP_M = 800

# Forme des boucles
WAYPOINTS_PER_LOOP = 5    # points de passage sur le cercle (plus = boucle plus ronde)
OVERLAP_MAX = 0.35        # rejet si plus de 35 % du trace repasse sur lui-meme (aller-retour)
MAX_DIST_ERROR = 0.20     # rejet si distance a plus de +/-20 % de la cible

# Etiquette de terrain (D+/km)
TERRAIN_FLAT_MAX = 8.0    # < 8 m/km  -> Plat
TERRAIN_HILLY_MAX = 15.0  # 8-15 m/km -> Vallonne ; > 15 -> Cols

# Estimations de sortie (defauts, reglables dans l'app)
SPEED_FLAT_KMH = 27     # vitesse a plat
SPEED_HILLY_KMH = 20    # vitesse en montagne (beaucoup de D+)
WATER_LPH = 0.6         # litres d'eau par heure
GEL_GPH = 45            # glucides par heure (g)
GEL_G = 25              # glucides par gel (g)

# --------------------------------------------------------------------------
# CLASSIFICATION DES SURFACES (pour l'audit)
# --------------------------------------------------------------------------
# Surfaces consideres comme "route" (bitume). Le reste tagge = suspect,
# absence de tag = inconnu.
PAVED_SURFACES = {
    "asphalt", "paved", "concrete", "concrete:plates",
    "concrete:lanes", "paving_stones", "sett",
}

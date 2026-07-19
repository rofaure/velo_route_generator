"""
Configuration centrale du générateur de boucles vélo route.
Un seul endroit à éditer pour changer le point de départ ou les défauts.
"""

# --------------------------------------------------------------------------
# POINT DE DEPART  (lon, lat)  -- ATTENTION : ordre lon PUIS lat (convention BRouter/GeoJSON)
# --------------------------------------------------------------------------
# Valeur PLACEHOLDER : centre approximatif de Saint-Cergues.
# >>> A REMPLACER par la coordonnee exacte de la boulangerie Meerpoel. <<<
# Comment l'obtenir precisement (une seule fois) :
#   1. Ouvrir https://brouter.de/brouter-web/
#   2. Clic droit sur la boulangerie -> les coordonnees s'affichent
#   3. Reporter ici au format (lon, lat)
START_LONLAT = (6.318631, 46.231524)  # Boulangerie Meerpoel, 1555 rue des Allobroges
START_NAME = "Boulangerie Meerpoel"

# --------------------------------------------------------------------------
# MOTEUR BROUTER
# --------------------------------------------------------------------------
import os
BROUTER_URL = os.environ.get("BROUTER_URL", "http://localhost:17777")
PROFILE = "roadonly"          # nom du .brf (sans extension) present dans ./profiles
REQUEST_TIMEOUT = 120         # secondes

# --------------------------------------------------------------------------
# DEFAUTS DE GENERATION
# --------------------------------------------------------------------------
TARGET_KM = 60.0              # distance cible d'une boucle
N_CANDIDATES = 8             # nombre de directions testees (boucles candidates)
TOLERANCE = 0.15             # ecart max accepte vs cible (0.15 = +/-15%)
MAX_ITERATIONS = 5           # iterations de convergence du rayon par boucle

# --------------------------------------------------------------------------
# CLASSIFICATION DES SURFACES (pour l'audit)
# --------------------------------------------------------------------------
# Surfaces consideres comme "route" (bitume). Le reste tagge = suspect,
# absence de tag = inconnu.
PAVED_SURFACES = {
    "asphalt", "paved", "concrete", "concrete:plates",
    "concrete:lanes", "paving_stones", "sett",
}

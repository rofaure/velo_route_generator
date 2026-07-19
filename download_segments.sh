#!/bin/sh
# Telecharge la/les tuile(s) de routage BRouter (.rd5) necessaires.
# Tuiles = carres de 5 degres, nommees par leur coin SUD-OUEST.
# Saint-Cergues (lon ~6.30, lat ~46.24) -> E5_N45.rd5
# (couvre lon 5..10, lat 45..50 : tout le Leman / Chablais / Haute-Savoie)
#
# Si tes boucles frolent un bord de tuile, ajoute les voisines a la liste.
set -e
mkdir -p segments
BASE="https://brouter.de/brouter/segments4"
TILES="E5_N45.rd5"
for t in $TILES; do
  echo "Telechargement $t ..."
  curl -fL -o "segments/$t" "$BASE/$t"
done
echo "OK. Tuiles presentes :"
ls -lh segments/*.rd5

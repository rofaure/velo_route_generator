# Générateur de boucles vélo route (no-gravel)

Génère automatiquement des boucles de vélo de route au départ d'un point fixe
(la boulangerie Meerpoel), en évitant les revêtements non adaptés (gravel,
chemins), puis exporte le tracé en **GPX** prêt pour un Coros Dura.

Le moteur de routage est **BRouter**, tournant **100 % en local dans Docker** :
pas de cloud, pas d'abonnement, pas de clé API. La seule donnée téléchargée est
la tuile de carte OpenStreetMap (fichier `.rd5`), gratuite.

---

## Ce que fait le projet (et ce qu'il ne fait pas)

Le pipeline en 3 temps :

1. **Génération de boucles** — comme le serveur BRouter ne fait que du
   point-à-point, la logique de boucle est en Python : on place des waypoints
   autour du départ sur un cercle, on route, on ajuste le rayon jusqu'à
   approcher la distance visée, et on répète dans plusieurs directions.
2. **Routage sensible au revêtement** — le profil `roadonly.brf` (dérivé de
   `fastbike`) **bloque** les surfaces explicitement non-route
   (`gravel`, `unpaved`, `compacted`, `ground`, `tracktype` grade2-5, etc.).
3. **Audit de confiance** — pour chaque boucle, on classe chaque tronçon en
   *bitume confirmé* / *inconnu* / *suspect* et on calcule un score. Les
   tronçons *inconnus* (non tagués dans OSM) sont listés avec un lien OSM pour
   vérification avant de rouler.

**Limite incontournable, à connaître :** le tag `surface` d'OSM est incomplet.
Une petite route sans tag est invisible au filtre. Le projet **réduit fortement**
le risque de gravel mais ne peut **pas garantir 100 % de bitume** — c'est
impossible à partir des seules données OSM, quel que soit l'outil. D'où l'audit,
qui rend le risque visible plutôt que de le masquer.

---

## Prérequis

- Docker + Docker Compose (Docker Desktop sur Mac/Windows, `docker` + plugin
  compose sur Linux).
- Rien d'autre : ni Java, ni Python en local (tout est conteneurisé). Le Python
  peut aussi se lancer en local si tu préfères (voir plus bas).

---

## Installation (première fois)

1. **Télécharger la tuile de carte** couvrant Saint-Cergues :
   ```sh
   ./download_segments.sh
   ```
   Récupère `E5_N45.rd5` (~150-200 Mo) dans `./segments`. Cette tuile couvre
   lon 5-10 / lat 45-50, soit tout le Léman, le Chablais et la Haute-Savoie.

2. **Construire et lancer le moteur BRouter** :
   ```sh
   docker compose up -d --build brouter
   ```
   Le premier build compile BRouter depuis les sources (quelques minutes, une
   seule fois). Ensuite le conteneur démarre en quelques secondes. Vérifier :
   ```sh
   docker compose ps          # brouter doit être "running"
   docker compose logs brouter
   ```

3. **Renseigner le point de départ exact** dans `app/config.py`
   (`START_LONLAT`). La valeur par défaut est un placeholder au centre de
   Saint-Cergues. Pour la coordonnée précise de la boulangerie : clic droit sur
   https://brouter.de/brouter-web/ → les coordonnées `(lon, lat)` s'affichent.

---

## Utilisation

**Option A — Python en local** (itération rapide) :
```sh
cd app
pip install -r requirements.txt
python main.py --distance 60 --candidates 8 --keep 3
```

**Option B — tout dans Docker** (pour s'entraîner à conteneuriser) :
```sh
docker compose run --rm app --distance 60 --candidates 8 --keep 3
```

Arguments :

- `--distance` : distance cible en km (défaut 60)
- `--candidates` : nombre de directions testées = nombre de boucles proposées (défaut 8)
- `--keep` : nombre de meilleures boucles exportées en GPX (défaut 1)

Sortie : un classement des boucles par score de confiance surface, le détail
des tronçons à vérifier pour les meilleures, et les fichiers GPX dans `./output`.

---

## Notes Docker (le pourquoi du comment)

Puisque l'objectif est aussi d'apprendre la conteneurisation, voici la logique
de chaque brique :

- **`docker-compose.yml`** orchestre deux services. `brouter` est le moteur ;
  `app` est le script Python (optionnel, dans le *profile* `tools`, donc il ne
  démarre pas tout seul — il se lance à la demande avec `docker compose run`).

- **Build depuis une URL git** : le service `brouter` n'a pas de Dockerfile
  local. Son `context` pointe directement sur le dépôt GitHub officiel ; Docker
  clone et construit l'image (multi-stage : une étape `gradle` compile le `.jar`,
  une étape `jdk-slim` ne garde que le runtime — c'est pour ça que l'image finale
  est légère). Si ta version de Docker refuse le contexte git distant, clone le
  dépôt à côté et remplace la ligne `context:` (indiqué dans le fichier).

- **Volumes** (`./segments:/segments4` et `./profiles:/profiles2`) : ce sont des
  *bind mounts*. Ils font apparaître tes dossiers hôtes à l'intérieur du
  conteneur. Le montage sur `/profiles2` **remplace** le dossier de profils de
  l'image par le tien — c'est comme ça que `roadonly.brf` et `lookups.dat`
  (obligatoire, c'est la table des tags OSM) sont fournis au moteur. Modifier un
  profil ne nécessite donc **pas** de rebuild : tu édites le `.brf` et tu
  relances le conteneur.

- **Réseau compose** : quand le Python tourne dans le conteneur `app`, il joint
  le moteur via `http://brouter:17777` (le nom du service fait office de nom
  d'hôte), pas `localhost`. C'est géré par la variable d'environnement
  `BROUTER_URL` dans le compose.

Commandes utiles :
```sh
docker compose up -d --build brouter   # (re)construire + démarrer le moteur
docker compose down                    # tout arrêter
docker compose logs -f brouter         # suivre les logs
```

---

## Personnalisation

- **Changer la sévérité du filtre surface** : éditer `profiles/roadonly.brf`.
  Le bloc `assign is_forbidden_road = ...` liste les surfaces bloquées.
  Retirer/ajouter des valeurs, puis relancer le conteneur `brouter`.
- **Changer la liste des surfaces « bitume »** de l'audit : `PAVED_SURFACES`
  dans `app/config.py`.
- **Boucles trop courtes / trop longues** : jouer sur `--distance` et
  `TOLERANCE` / `MAX_ITERATIONS` dans `config.py`.

---

## Bémol honnête sur les boucles auto

Une boucle générée optimise le coût de routage, **pas l'intérêt du parcours**.
La distance est approchée (deux boucles de « 60 km » n'ont ni le même dénivelé
ni le même temps), et l'algorithme peut ignorer un joli col qui n'a aucune
raison d'apparaître dans le calcul. C'est pour ça que le script en **propose
plusieurs** : génère, compare sur distance + confiance, et choisis. Pas « la
boucle parfaite du premier coup ».

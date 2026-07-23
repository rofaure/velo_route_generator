"""
Interface Streamlit du générateur de tracés vélo route.

Couche de présentation par-dessus les modules métier (loop_generator,
surface_audit, brouter_client, geo_utils, geocode).
"""

import altair as alt
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import config
from loop_generator import (generate_all, generate_via_waypoints,
                            generate_for_duration)
from surface_audit import audit
from geo_utils import colored_runs, direction_arrows
from ride_analysis import (terrain_type, climbs, steep_descents,
                           elevation_profile, estimate_ride, fuel_recommendation,
                           format_hm, CAT_ORDER, CAT_COLORS, INTENSITES, METEOS)
from geocode import geocode_place
from ride_reference import summit_name, villages_along_route, has_reference
import favorites as fav
import wind as wd
from brouter_client import route_geojson
from datetime import datetime, timedelta
from brouter_client import route, BRouterError, tag_gpx_cycling

st.set_page_config(page_title="Tracés vélo route", page_icon="🚴", layout="wide")

CAT_COLOR = {"paved": "#2e7d32", "unknown": "#f9a825", "suspect": "#c62828"}


@st.cache_data(show_spinner=False)
def cached_geocode(text):
    """Géocode (adresse ou 'lat, lon') avec mise en cache pour éviter de
    rappeler Nominatim à chaque frappe."""
    return geocode_place(text)


def resolve_start(start_label, start_custom):
    if start_custom.strip():
        g = cached_geocode(start_custom)
        if g:
            return (g["lon"], g["lat"]), g["name"]
        return None, start_custom.strip()
    return config.START_POINTS[start_label], start_label


def resolve_waypoints(text):
    pts, names, failed = [], [], []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        g = cached_geocode(line)
        if g:
            pts.append((g["lon"], g["lat"]))
            names.append(g["name"])
        else:
            failed.append(line)
    return pts, names, failed


@st.cache_data(ttl=1800, show_spinner=False)
def cached_wind(lat, lon, iso_hour):
    """Prévision mise en cache 30 min (évite de solliciter l'API à chaque clic)."""
    return wd.fetch_wind(lat, lon, datetime.fromisoformat(iso_hour))


def reverse_route(lp):
    """Même tracé parcouru en sens inverse (D+ total inchangé sur une boucle)."""
    return {**lp,
            "coords": list(reversed(lp["coords"])),
            "csv_rows": list(reversed(lp["csv_rows"])),
            "waypoints": list(reversed(lp["waypoints"]))}


def route_from_favorite(f):
    """Recalcule le tracé d'un favori à partir de sa « recette »."""
    wpts = [tuple(w) for w in f["route_waypoints"]]
    r = route_geojson(wpts, profile=f.get("profile"),
                      profile_params=f.get("profile_params"))
    return {
        "bearing": f.get("bearing"),
        "length_km": r["length_m"] / 1000.0,
        "ascend_m": r["ascend_m"],
        "total_time_s": r["total_time_s"],
        "overlap": None,
        "shape": f.get("shape", "Boucle"),
        "waypoints": wpts,
        "coords": r["coords"],
        "csv_rows": r["segments"],
    }


def build_ranking(scored):
    return pd.DataFrame([{
        "#": i + 1,
        "Type": lp.get("shape", "Boucle"),
        "Terrain": terrain_type(lp["coords"], lp["length_km"], lp["ascend_m"]),
        "Distance (km)": round(lp["length_km"], 1),
        "D+ (m)": round(lp["ascend_m"]),
        **({"Durée": format_hm(lp["est_time_h"])} if lp.get("est_time_h") else {}),
        "Confiance": round(rep["confidence"], 1),
        "Bitume %": round(rep["pct_paved"], 1),
        "Inconnu %": round(rep["pct_unknown"], 1),
    } for i, (lp, rep) in enumerate(scored)])


def points_map(start, start_name, waypoints, wp_names, height=320, trace_coords=None,
               trace_segments=None, cols=None, wind=None):
    """Carte folium : départ (vert) + points de passage (rouges numérotés).
    Si trace_coords est fourni, dessine aussi le tracé coloré par surface."""
    fmap = folium.Map(location=[start[1], start[0]], zoom_start=11, tiles="CartoDB positron")
    all_pts = [[start[1], start[0]]]

    if trace_coords:
        for cat, seg in colored_runs(trace_coords, trace_segments or []):
            folium.PolyLine(seg, color=CAT_COLOR[cat], weight=5, opacity=0.9).add_to(fmap)
        # sens de circulation : chevrons orientes, centres exactement sur le trace.
        # Boite CARREE de taille fixe -> translate(-50%,-50%) centre le glyphe
        # quelle que soit la rotation (sinon la boite du caractere, plus haute
        # que large, decale visuellement la fleche apres rotation).
        # Un chevron ">" pointe vers l'EST au repos : on pivote donc de cap-90.
        for lat_a, lon_a, cap in direction_arrows(trace_coords, n=14):
            folium.Marker(
                [lat_a, lon_a],
                icon=folium.DivIcon(
                    icon_size=(0, 0), icon_anchor=(0, 0),
                    html=(
                        f'<div style="width:20px;height:20px;'
                        f'display:flex;align-items:center;justify-content:center;'
                        f'transform:translate(-50%,-50%) rotate({cap - 90:.0f}deg);">'
                        f'<span style="font:700 17px/17px -apple-system,Segoe UI,'
                        f'Helvetica,Arial,sans-serif;color:#0f2f16;'
                        f'text-shadow:0 0 3px #fff,0 0 3px #fff,0 0 3px #fff;">'
                        f'&gt;</span></div>'))
            ).add_to(fmap)
        all_pts += [[c[1], c[0]] for c in trace_coords]

    folium.Marker([start[1], start[0]], tooltip=f"Départ : {start_name}",
                  icon=folium.Icon(color="green", icon="play", prefix="fa")).add_to(fmap)
    for i, (wp, name) in enumerate(zip(waypoints, wp_names), 1):
        folium.Marker([wp[1], wp[0]], tooltip=f"{i}. {name}",
                      icon=folium.Icon(color="red", icon="flag", prefix="fa")).add_to(fmap)
        all_pts.append([wp[1], wp[0]])
    for c in (cols or []):
        nm = c.get("name")
        label = f"{nm} · {c['ele']:.0f} m" if nm else f"{c['ele']:.0f} m"
        is_col = c.get("kind") == "col"
        # petit point (au lieu d'une grosse epingle)
        folium.CircleMarker(
            [c["lat"], c["lon"]], radius=5, color="#6c3483", weight=2,
            fill=True, fill_color="#a569bd" if is_col else "#d2b4de",
            fill_opacity=0.95, tooltip=label).add_to(fmap)
        # etiquette compacte, ancree juste au-dessus du point
        folium.Marker(
            [c["lat"], c["lon"]],
            icon=folium.DivIcon(
                icon_size=(0, 0), icon_anchor=(0, 0),
                html=(f'<div style="transform:translate(-50%,-190%);display:inline-block;'
                      f'font-size:10px;line-height:12px;font-weight:600;color:#4a235a;'
                      f'background:rgba(255,255,255,.88);border:1px solid #a569bd;'
                      f'border-radius:3px;padding:0 3px;white-space:nowrap;">'
                      f'{"⛰ " if is_col else ""}{label}</div>'))).add_to(fmap)

    if wind:
        # fleche rouge : sens vers lequel SOUFFLE le vent (direction_deg = origine)
        vers = (wind["direction_deg"] + 180) % 360
        fmap.get_root().html.add_child(folium.Element(f"""
        <div style="position:absolute;top:12px;right:12px;z-index:9999;
                    background:rgba(255,255,255,.92);border:1px solid #c0392b;
                    border-radius:6px;padding:6px 9px;text-align:center;
                    font-family:sans-serif;box-shadow:0 1px 4px rgba(0,0,0,.2);">
          <div style="font-size:26px;line-height:26px;color:#c0392b;
                      transform:rotate({vers:.0f}deg);">&#8593;</div>
          <div style="font-size:11px;font-weight:700;color:#7b241c;margin-top:2px;">
            {wind['cardinal']}</div>
          <div style="font-size:10px;color:#555;">{wind['speed_kmh']:.0f} km/h</div>
        </div>"""))

    if len(all_pts) > 1:
        fmap.fit_bounds(all_pts)
    st_folium(fmap, use_container_width=True, height=height, returned_objects=[])


# ----------------------------------------------------------------------
# En-tête
# ----------------------------------------------------------------------
st.title("🚴 Générateur de tracés vélo route")
st.caption(f"Moteur {config.BROUTER_URL}")

# ----------------------------------------------------------------------
# Réglages (barre latérale)
# ----------------------------------------------------------------------
with st.sidebar:
    st.header("Départ")
    start_label = st.selectbox("Raccourcis", list(config.START_POINTS.keys()))
    start_custom = st.text_input("… ou adresse / « lat, lon »",
                                 placeholder="ex : Nyon gare   |   46.383, 6.235")

    st.header("Points de passage")
    st.caption("Un par ligne (adresse ou « lat, lon »). Tous les tracés y passeront.")
    waypoints_text = st.text_area("Points de passage", label_visibility="collapsed",
                                  placeholder="Nyon\nGland", height=100)

    st.header("Paramètres")
    ride_type = st.selectbox("Type de sortie", list(config.PROFILES_UI.keys()),
                             help="Plat = privilégie voies vertes et évite le dénivelé. "
                                  "Cols = terrain vallonné, trié par D+.")
    traffic = st.selectbox("Éviter le trafic motorisé", list(config.TRAFFIC_UI.keys()),
                           index=1,
                           help="Pénalité appliquée aux axes fréquentés lors du calcul :\n\n"
                                "• **Aucun** — aucune pénalité, tous les axes sont utilisables.\n"
                                "• **Modéré** — voies rapides interdites, nationales ×3, "
                                "départementales ×1.8. Les grands axes restent empruntables "
                                "si c'est le seul passage.\n"
                                "• **Maximal** — voies rapides interdites, nationales ×8, "
                                "départementales ×3. Le calcul fait de gros détours pour "
                                "privilégier les petites routes.")
    prefer_cw = st.checkbox("Favoriser les aménagements cyclables", value=True,
                            help="Privilégie voies vertes et pistes cyclables. "
                                 "Attention : certaines ne sont pas bitumées.")

    use_wind = st.checkbox("Tenir compte du vent", value=False,
                           help="Récupère la prévision Open-Meteo pour le départ. "
                                "C'est la seule option qui nécessite Internet : "
                                "décochée, l'application reste 100 % hors-ligne.")
    if use_wind:
        _jour = st.selectbox("Jour de sortie",
                             ["Aujourd'hui", "Demain", "Après-demain"])
        _heure = st.slider("Heure de départ", 5, 21, 9)
    else:
        _jour, _heure = "Aujourd'hui", 9
    objectif = st.radio("Objectif", ["Distance", "Durée"], horizontal=True,
                        help="« Durée » ajuste automatiquement la distance selon "
                             "le dénivelé et ta vitesse, pour tenir le temps voulu.")
    if objectif == "Distance":
        distance = st.slider("Distance cible (km)", 20, 150, int(config.TARGET_KM),
                             step=5, help="Avec des points de passage, la distance "
                                          "s'adapte à la géographie.")
        duree_h = None
    else:
        _h = st.slider("Temps disponible (h)", 1, 8, 3)
        _m = st.select_slider("et (min)", options=[0, 15, 30, 45], value=0)
        duree_h = _h + _m / 60.0
        distance = int(duree_h * 25)   # 1re estimation, affinee a la generation
        st.caption(f"Objectif : **{_h} h {_m:02d}** (± 15 min)")
    n_candidates = st.slider("Nombre de variantes testées", 6, 24, 12, step=2)

    go = st.button("Générer les tracés", type="primary", use_container_width=True)

    st.header("Mes tracés")
    _favs = fav.list_favorites()
    if _favs:
        _sel = st.selectbox("Favoris enregistrés", _favs,
                            format_func=fav.label, label_visibility="collapsed")
        c_load, c_del = st.columns(2)
        if c_load.button("Charger", use_container_width=True):
            try:
                lp_f = route_from_favorite(_sel)
                st.session_state["scored"] = [(lp_f, audit(lp_f["csv_rows"]))]
                st.session_state["distance"] = lp_f["length_km"]
                st.session_state["start_point"] = tuple(_sel["start"])
                st.session_state["start_name"] = _sel.get("start_name", "Départ")
                st.session_state["waypoints"] = [tuple(w) for w in _sel.get("waypoints", [])]
                st.session_state["wp_names"] = _sel.get("wp_names", [])
                st.session_state["profile_name"] = _sel.get("profile")
                st.session_state["profile_params"] = _sel.get("profile_params", {})
                st.success(f"« {_sel['name']} » chargé.")
            except BRouterError as e:
                st.error(f"Rechargement impossible : {e}")
        if c_del.button("Supprimer", use_container_width=True):
            fav.delete_favorite(_sel["id"])
            st.rerun()
    else:
        st.caption("Aucun favori. Enregistre un tracé depuis le résumé de sortie.")
    st.divider()
    st.caption("Astuce : pour rouler en Suisse (La Côte / Vaud), pars de Nyon ou Gland.")
    st.caption("« Inconnu » = revêtement non tagué dans OSM, souvent une petite "
               "route bitumée. À vérifier sur la carte avant de rouler.")
    with st.expander("Ta vitesse (calibration perso)"):
        speed_flat = st.slider("Vitesse à plat (km/h)", 20, 35, config.SPEED_FLAT_KMH)
        speed_hilly = st.slider("Vitesse en montagne (km/h)", 12, 28, config.SPEED_HILLY_KMH)

# ----------------------------------------------------------------------
# Résolution des points + carte de confirmation (en direct)
# ----------------------------------------------------------------------
start, start_name = resolve_start(start_label, start_custom)
waypoints, wp_names, wp_failed = resolve_waypoints(waypoints_text)

if start is None:
    st.error("Départ introuvable : vérifie l'adresse ou saisis « lat, lon ».")
    st.stop()
if wp_failed:
    st.warning("Points de passage introuvables (ignorés) : " + ", ".join(wp_failed))

st.subheader("Points sélectionnés")
st.caption("Vérifie visuellement le départ (vert) et les points de passage (rouges) "
           "avant de générer.")
points_map(start, start_name, waypoints, wp_names, height=320)

# ----------------------------------------------------------------------
# Génération
# ----------------------------------------------------------------------
if go:
    profile_name = config.PROFILES_UI[ride_type]
    profile_params = dict(config.TRAFFIC_UI[traffic])
    profile_params["prefer_cycleways"] = prefer_cw
    with st.spinner("Génération des tracés…"):
        try:
            def _gen(dist_km):
                if waypoints:
                    return generate_via_waypoints(start, waypoints, dist_km, n_candidates,
                                                  profile=profile_name,
                                                  profile_params=profile_params)
                return generate_all(start, dist_km, n_candidates, profile=profile_name,
                                    profile_params=profile_params)

            if duree_h:
                _estim = lambda d, a: estimate_ride(d, a, speed_flat, speed_hilly)["time_h"]
                routes, distance = generate_for_duration(
                    _gen, duree_h, tol_min=15, estimator=_estim,
                    speed_hint=(speed_flat + speed_hilly) / 2)
            else:
                routes = _gen(distance)
        except BRouterError as e:
            st.error(f"BRouter injoignable : {e}")
            routes = []
    if not routes:
        st.warning("Aucun tracé propre généré. Change la distance, le départ, "
                   "ou ajuste les points de passage.")
    else:
        scored = [(lp, audit(lp["csv_rows"])) for lp in routes]
        if duree_h:
            scored.sort(key=lambda x: (abs(x[0].get("est_time_h", 0) - duree_h),
                                       -x[1]["confidence"]))
        elif profile_name == "roadclimb":
            scored.sort(key=lambda x: (-x[0]["ascend_m"], -x[1]["confidence"]))
        else:
            scored.sort(key=lambda x: (-x[1]["confidence"], abs(x[0]["length_km"] - distance)))
        st.session_state["scored"] = scored
        st.session_state["distance"] = distance
        st.session_state["start_point"] = start
        st.session_state["start_name"] = start_name
        st.session_state["waypoints"] = waypoints
        st.session_state["wp_names"] = wp_names

scored = st.session_state.get("scored")
if not scored:
    st.info("Règle tes points et paramètres à gauche, puis clique « Générer les tracés ».")
    st.stop()

# ----------------------------------------------------------------------
# Résultats
# ----------------------------------------------------------------------
st.subheader("Tracés générés (triés par confiance)")
_d = st.session_state.get("duree_h")
st.caption(f"{len(scored)} tracé(s) — boucles et aller-retours." +
           (f" Objectif : {format_hm(_d)} ± 15 min." if _d else ""))
st.dataframe(build_ranking(scored), use_container_width=True, hide_index=True)

choice = st.selectbox("Tracé à visualiser", list(range(1, len(scored) + 1)),
                      format_func=lambda i: f"Tracé #{i}")
lp, rep = scored[choice - 1]

# --- Vent (optionnel : seule dépendance réseau de l'application) ---
_wind, _wind_err, _wa = None, None, None
if use_wind:
    _base = st.session_state.get("start_point", start)
    _delta = {"Aujourd'hui": 0, "Demain": 1, "Après-demain": 2}[_jour]
    _when = (datetime.now() + timedelta(days=_delta)).replace(
        hour=int(_heure), minute=0, second=0, microsecond=0)
    try:
        _wind = cached_wind(_base[1], _base[0], _when.isoformat())
    except wd.WindError as e:
        _wind_err = str(e)

# --- Sens du parcours : toujours modifiable ---
# Quand le vent est actif, on PRE-SELECTIONNE le sens le plus favorable,
# mais l'utilisateur garde la main dans tous les cas.
_reco_inverse = False
if _wind:
    _sens, _gain = wd.better_direction(lp["coords"], _wind["direction_deg"])
    _reco_inverse = (_sens == "inverse" and _gain >= 5)

_opts = ["Sens d'origine", "Sens inversé"]
_labels = dict(_opts and zip(_opts, _opts))
if _reco_inverse:
    _labels["Sens inversé"] = "Sens inversé ✅ conseillé (vent)"
elif _wind:
    _labels["Sens d'origine"] = "Sens d'origine ✅ conseillé (vent)"

_choix_sens = st.radio(
    "Sens du parcours", _opts, index=1 if _reco_inverse else 0,
    horizontal=True, key=f"sens_{choice}",
    format_func=lambda o: _labels.get(o, o),
    help="Sur une boucle, le dénivelé total est identique dans les deux sens : "
         "seul l'ordre des montées et des descentes change. Le sens choisi "
         "s'applique à la carte, au profil et au GPX exporté.")

if _choix_sens == "Sens inversé":
    lp = reverse_route(lp)

if _wind:
    _wa = wd.analyze_route(lp["coords"], _wind["direction_deg"])

# Analyse pour le resume : ascensions nommees + villages (jointure locale)
_climbs = climbs(lp["coords"])
_named = [(c, summit_name(c["top_lat"], c["top_lon"], c["top_ele_m"])) for c in _climbs]
_map_cols = [{"lat": c["top_lat"], "lon": c["top_lon"], "ele": c["top_ele_m"],
             "name": (s["name"] if s else None),
             "kind": (s["kind"] if s else None)}
            for c, s in _named]
_villages = villages_along_route(lp["coords"])

col_map, col_info = st.columns([2, 1])

with col_map:
    st.subheader(f"Tracé #{choice} — {lp.get('shape', 'Boucle')} ({lp['length_km']:.1f} km)")
    points_map(st.session_state.get("start_point", start),
               st.session_state.get("start_name", start_name),
               st.session_state.get("waypoints", []),
               st.session_state.get("wp_names", []),
               height=520, trace_coords=lp["coords"], trace_segments=lp["csv_rows"],
               cols=_map_cols, wind=_wind)
    st.caption("🟢 bitume confirmé   ·   🟠 inconnu (non tagué OSM)   ·   🔴 suspect   ·   › sens de circulation")

with col_info:
    st.subheader("Parcours")
    c1, c2 = st.columns(2)
    c1.metric("Distance", f"{lp['length_km']:.1f} km")
    c2.metric("Dénivelé +", f"{lp['ascend_m']:.0f} m")

    st.subheader("Audit surface")
    st.metric("Bitume confirmé", f"{rep['pct_paved']:.1f} %")
    st.metric("Inconnu", f"{rep['pct_unknown']:.1f} %", f"{rep['km_unknown']:.1f} km", delta_color="off")
    st.metric("Suspect", f"{rep['pct_suspect']:.1f} %", f"{rep['km_suspect']:.1f} km", delta_color="inverse")

    try:
        gpx = route(lp["waypoints"], fmt="gpx", heading=lp["bearing"],
                    profile=st.session_state.get("profile_name"),
                    profile_params=st.session_state.get("profile_params"))
        gpx = tag_gpx_cycling(
            gpx, f"{lp.get('shape', 'Boucle')} {lp['length_km']:.0f} km · "
                 f"{lp['ascend_m']:.0f} m D+")
        st.download_button(
            "⬇️ Télécharger le GPX", data=gpx,
            file_name=f"{lp.get('shape', 'boucle').lower()}_{lp['length_km']:.0f}km_{lp['ascend_m']:.0f}mD.gpx",
            mime="application/gpx+xml", use_container_width=True)
    except BRouterError as e:
        st.warning(f"Export GPX indisponible : {e}")

    st.divider()
    _default_name = f"{lp.get('shape', 'Boucle')} {lp['length_km']:.0f} km"
    _fav_name = st.text_input("Nom du tracé", value=_default_name,
                              label_visibility="collapsed", placeholder="Nom du tracé")
    if st.button("💾 Enregistrer ce tracé", use_container_width=True):
        fav.save_favorite(
            _fav_name, lp,
            st.session_state.get("profile_name"),
            st.session_state.get("profile_params"),
            st.session_state.get("start_point", start),
            st.session_state.get("start_name", start_name),
            waypoints=st.session_state.get("waypoints"),
            wp_names=st.session_state.get("wp_names"),
            terrain=terrain_type(lp["coords"], lp["length_km"], lp["ascend_m"]),
            pct_paved=rep["pct_paved"])
        st.success("Enregistré — retrouve-le dans « Mes tracés » à gauche.")
        st.rerun()


# ----------------------------------------------------------------------
# Résumé de sortie (calculé automatiquement à partir du tracé)
# ----------------------------------------------------------------------
st.divider()
st.subheader("Résumé de sortie")

# Profil altimétrique colore par pente (style profil de col)
prof_rows = elevation_profile(lp["coords"])
if prof_rows:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    xs = [r["km"] for r in prof_rows]
    ys = [r["alt"] for r in prof_rows]
    baseline = min(ys) - 20
    fig, ax = plt.subplots(figsize=(11, 3.2))
    # remplissage colore par pente, segment par segment
    for i in range(len(xs) - 1):
        ax.fill_between([xs[i], xs[i + 1]], [ys[i], ys[i + 1]], baseline,
                        color=prof_rows[i + 1]["color"], linewidth=0)
    ax.plot(xs, ys, color="#444", linewidth=0.8)
    # sommets (cols) : triangle + nom (si connu) + altitude
    for c, sm in _named:
        ax.plot(c["top_km"], c["top_ele_m"], marker="^", color="#222", markersize=9, zorder=5)
        lbl = f"{sm['name']}\n{c['top_ele_m']:.0f} m" if sm else f"{c['top_ele_m']:.0f} m"
        ax.annotate(lbl, (c["top_km"], c["top_ele_m"]), textcoords="offset points",
                    xytext=(0, 7), ha="center", fontsize=8)
    ax.set_xlabel("Distance (km)")
    ax.set_ylabel("Altitude (m)")
    ax.set_ylim(bottom=baseline)
    ax.margins(x=0.01)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(handles=[Patch(color=CAT_COLORS[c], label=c) for c in CAT_ORDER],
              title="Pente", loc="upper left", fontsize=8, title_fontsize=8, framealpha=0.85)
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

# Vent du jour (si active)
if _wind_err:
    st.warning(f"Vent indisponible : {_wind_err}")
elif _wind:
    st.markdown("**Vent prévu**")
    w1, w2 = st.columns([1, 3])
    w1.metric("Vent", f"{_wind['speed_kmh']:.0f} km/h",
              f"{_wind['cardinal']} · rafales {_wind['gusts_kmh']:.0f}",
              delta_color="off")
    _phases = wd.phase_summary(lp["coords"], _wind["direction_deg"])
    if _phases:
        w2.markdown(f"### {wd.phase_sentence(_phases)}")

    if _phases:
        _icone = {"Dos": "🟢 dans le dos", "Travers": "🟡 de côté", "Face": "🔴 de face"}
        st.dataframe(pd.DataFrame([{
            "Phase": f"{p['phase']} ({p['km_debut']:.0f}–{p['km_fin']:.0f} km)",
            "Vent dominant": _icone[p["dominant"]],
            "Dans le dos": f"{p['pct_dos']:.0f} %",
            "De côté": f"{p['pct_travers']:.0f} %",
            "De face": f"{p['pct_face']:.0f} %",
        } for p in _phases]), use_container_width=True, hide_index=True)
        if _wa:
            st.caption(
                f"Sur l'ensemble du parcours : **{_wa['pct_dos']:.0f} %** dans le dos, "
                f"**{_wa['pct_travers']:.0f} %** de côté, **{_wa['pct_face']:.0f} %** "
                f"de face — en part de **distance** (les trois totalisent 100 %). "
                f"« De côté » = vent à plus de 45° de ton axe : il freine peu mais "
                f"peut déporter. Prévision Open-Meteo pour le "
                f"{_wind['time'].replace('T', ' à ')} au point de départ.")

# Estimations : temps (vitesse) + ravitaillement (intensite + meteo)
_est = estimate_ride(lp["length_km"], lp["ascend_m"], speed_flat, speed_hilly)
_time_h = _est["time_h"]

fi1, fi2 = st.columns(2)
intensity = fi1.selectbox("Intensité de la sortie", INTENSITES, index=0)
meteo = fi2.selectbox("Météo", METEOS, index=1)
_fuel = fuel_recommendation(intensity, meteo, _time_h)
_water_l = _time_h * _fuel["water_lph"]
_gels = _time_h * _fuel["carbs_gph"] / config.GEL_G

e1, e2, e3, e4 = st.columns(4)
e1.metric("Temps estimé", format_hm(_time_h))
e2.metric("Vitesse moy.", f"{_est['speed_kmh']:.0f} km/h")
e3.metric("Eau", f"{_water_l:.1f} L", f"{_fuel['water_lph']:.2f} L/h", delta_color="off")
e4.metric("Gels", f"{_gels:.0f}", f"{_fuel['carbs_gph']:.0f} g/h", delta_color="off")

with st.expander("Comment sont calculés l'eau et les glucides ?"):
    st.markdown(
        f"""
**Pour cette sortie ({_time_h:.1f} h, {intensity.lower()}, {meteo.lower()})** :
{_fuel['carbs_gph']:.0f} g de glucides/h et {_fuel['water_lph']:.2f} L d'eau/h.

**Glucides** — le besoin monte avec la durée et l'intensité :
- sortie courte / facile : ~30 g/h ;
- dès 1 h 30 – 2 h : ~45–60 g/h ;
- sortie longue ou intense : jusqu'à 75–90 g/h. Au-delà de 60 g/h, il faut
  **mélanger plusieurs sucres** (glucose + fructose) et « entraîner son intestin ».
- Repère : **1 gel ≈ {config.GEL_G:.0f} g** de glucides.

**Eau** — surtout fonction de la chaleur (et de ta transpiration) :
- frais (<15 °C) : ~0,5 L/h ;
- tempéré (15–25 °C) : ~0,65 L/h ;
- chaud (>25 °C) : ~0,9–1 L/h.

Ce sont des **repères d'endurance**, pas une prescription — ajuste selon ton
ressenti, la chaleur du jour et ta tolérance digestive.
""")

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("**Ascensions**")
    if _named:
        for c, sm in _named:
            if sm and sm["kind"] == "col":
                head = f"**{sm['name']}** ({c['top_ele_m']:.0f} m)"
            elif sm:
                head = f"Montée vers **{sm['name']}**"
            else:
                head = "Montée"
            st.write(f"• {head} : {c['length_km']:.1f} km, +{c['gain_m']:.0f} m, "
                     f"{c['avg_grade_pct']:.1f} % moy — sommet à {c['top_km']:.0f} km")
    else:
        st.write("Aucune ascension soutenue.")

with col_b:
    st.markdown("**Points de vigilance**")
    vig = []
    for c in steep_descents(lp["coords"]):
        vig.append(f"Descente raide : -{c['drop_m']:.0f} m sur {c['length_km']:.1f} km "
                   f"({c['avg_grade_pct']:.1f} %)")
    if rep["km_unknown"] >= 0.5:
        vig.append(f"Surface inconnue : {rep['km_unknown']:.1f} km à vérifier avant de rouler")
    if rep["km_suspect"] > 0:
        vig.append(f"Surface suspecte : {rep['km_suspect']:.1f} km")
    if vig:
        for v in vig:
            st.write("• " + v)
    else:
        st.write("Rien de particulier.")

if _villages:
    st.markdown("**Villages traversés** : " + " → ".join(_villages))

if not has_reference():
    st.info("Pour afficher les noms des cols et villages, lance une fois "
            "`python build_reference.py` (dans app/), puis reconstruis l'app.")

st.caption("Résumé calculé automatiquement depuis le tracé, indépendamment des points "
           "de passage.")

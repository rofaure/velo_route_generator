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
from loop_generator import generate_all, generate_via_waypoints
from surface_audit import audit
from geo_utils import colored_runs
from ride_analysis import (terrain_type, climbs, steep_descents,
                           elevation_profile, estimate_ride,
                           format_hm, CAT_ORDER, CAT_COLORS)
from geocode import geocode_place
from brouter_client import route, BRouterError

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


def build_ranking(scored):
    return pd.DataFrame([{
        "#": i + 1,
        "Type": lp.get("shape", "Boucle"),
        "Terrain": terrain_type(lp["coords"], lp["length_km"], lp["ascend_m"]),
        "Distance (km)": round(lp["length_km"], 1),
        "D+ (m)": round(lp["ascend_m"]),
        "Confiance": round(rep["confidence"], 1),
        "Bitume %": round(rep["pct_paved"], 1),
        "Inconnu %": round(rep["pct_unknown"], 1),
    } for i, (lp, rep) in enumerate(scored)])


def points_map(start, start_name, waypoints, wp_names, height=320, trace_coords=None,
               trace_segments=None):
    """Carte folium : départ (vert) + points de passage (rouges numérotés).
    Si trace_coords est fourni, dessine aussi le tracé coloré par surface."""
    fmap = folium.Map(location=[start[1], start[0]], zoom_start=11, tiles="CartoDB positron")
    all_pts = [[start[1], start[0]]]

    if trace_coords:
        for cat, seg in colored_runs(trace_coords, trace_segments or []):
            folium.PolyLine(seg, color=CAT_COLOR[cat], weight=5, opacity=0.9).add_to(fmap)
        all_pts += [[c[1], c[0]] for c in trace_coords]

    folium.Marker([start[1], start[0]], tooltip=f"Départ : {start_name}",
                  icon=folium.Icon(color="green", icon="play", prefix="fa")).add_to(fmap)
    for i, (wp, name) in enumerate(zip(waypoints, wp_names), 1):
        folium.Marker([wp[1], wp[0]], tooltip=f"{i}. {name}",
                      icon=folium.Icon(color="red", icon="flag", prefix="fa")).add_to(fmap)
        all_pts.append([wp[1], wp[0]])

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
    distance = st.slider("Distance cible (km)", 20, 150, int(config.TARGET_KM), step=5,
                         help="Référence : avec des points de passage, la distance s'adapte à la géographie.")
    n_candidates = st.slider("Nombre de variantes testées", 6, 24, 12, step=2)

    go = st.button("Générer les tracés", type="primary", use_container_width=True)
    st.divider()
    st.caption("Astuce : pour rouler en Suisse (La Côte / Vaud), pars de Nyon ou Gland.")
    st.caption("« Inconnu » = revêtement non tagué dans OSM, souvent une petite "
               "route bitumée. À vérifier sur la carte avant de rouler.")
    with st.expander("Réglages estimation (eau, gels, vitesse)"):
        speed_flat = st.slider("Vitesse à plat (km/h)", 20, 35, config.SPEED_FLAT_KMH)
        speed_hilly = st.slider("Vitesse en montagne (km/h)", 12, 28, config.SPEED_HILLY_KMH)
        water_lph = st.slider("Eau (L/h)", 0.3, 1.2, float(config.WATER_LPH), step=0.1)
        gel_gph = st.slider("Glucides (g/h)", 20, 90, config.GEL_GPH, step=5)
        gel_g = st.slider("Glucides par gel (g)", 15, 40, config.GEL_G, step=5)

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
    with st.spinner("Génération des tracés…"):
        try:
            if waypoints:
                routes = generate_via_waypoints(start, waypoints, distance, n_candidates,
                                                profile=profile_name)
            else:
                routes = generate_all(start, distance, n_candidates, profile=profile_name)
        except BRouterError as e:
            st.error(f"BRouter injoignable : {e}")
            routes = []
    if not routes:
        st.warning("Aucun tracé propre généré. Change la distance, le départ, "
                   "ou ajuste les points de passage.")
    else:
        scored = [(lp, audit(lp["csv_rows"])) for lp in routes]
        if profile_name == "roadclimb":
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
st.caption(f"{len(scored)} tracé(s) — boucles et aller-retours passant par tes points.")
st.dataframe(build_ranking(scored), use_container_width=True, hide_index=True)

choice = st.selectbox("Tracé à visualiser", list(range(1, len(scored) + 1)),
                      format_func=lambda i: f"Tracé #{i}")
lp, rep = scored[choice - 1]

col_map, col_info = st.columns([2, 1])

with col_map:
    st.subheader(f"Tracé #{choice} — {lp.get('shape', 'Boucle')} ({lp['length_km']:.1f} km)")
    points_map(st.session_state.get("start_point", start),
               st.session_state.get("start_name", start_name),
               st.session_state.get("waypoints", []),
               st.session_state.get("wp_names", []),
               height=520, trace_coords=lp["coords"], trace_segments=lp["csv_rows"])
    st.caption("🟢 bitume confirmé   ·   🟠 inconnu (non tagué OSM)   ·   🔴 suspect")

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
        gpx = route(lp["waypoints"], fmt="gpx", heading=lp["bearing"])
        st.download_button(
            "⬇️ Télécharger le GPX", data=gpx,
            file_name=f"{lp.get('shape', 'boucle').lower()}_{lp['length_km']:.0f}km_{lp['ascend_m']:.0f}mD.gpx",
            mime="application/gpx+xml", use_container_width=True)
    except BRouterError as e:
        st.warning(f"Export GPX indisponible : {e}")


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
    # sommets (cols) : triangle + altitude
    for c in climbs(lp["coords"]):
        ax.plot(c["top_km"], c["top_ele_m"], marker="^", color="#222", markersize=9, zorder=5)
        ax.annotate(f"{c['top_ele_m']:.0f} m", (c["top_km"], c["top_ele_m"]),
                    textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8)
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

# Estimations
est = estimate_ride(lp["length_km"], lp["ascend_m"],
                    speed_flat, speed_hilly, water_lph, gel_gph, gel_g)
e1, e2, e3, e4 = st.columns(4)
e1.metric("Temps estimé", format_hm(est["time_h"]))
e2.metric("Vitesse moy.", f"{est['speed_kmh']:.0f} km/h")
e3.metric("Eau", f"{est['water_l']:.1f} L")
e4.metric("Gels", f"{est['gels']:.0f}")

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("**Ascensions**")
    cl = climbs(lp["coords"])
    if cl:
        for c in cl:
            st.write(f"• Montée : **{c['length_km']:.1f} km**, +{c['gain_m']:.0f} m, "
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

st.caption("Résumé calculé automatiquement depuis le tracé (indépendant des points de "
           "passage). Les noms des cols et villages arrivent au Chunk 2.")

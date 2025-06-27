import streamlit as st
import requests
import os
import folium
import numpy as np
from streamlit_folium import st_folium
from dotenv import load_dotenv

load_dotenv()
ORS_API_KEY = os.getenv("ORS_API_KEY")


def fetch_location_suggestions(query):
    if not query or not ORS_API_KEY:
        return []
    try:
        resp = requests.get(
            "https://api.openrouteservice.org/geocode/autocomplete",
            params={
                "api_key": ORS_API_KEY,
                "text": query,
                "boundary.country": "IN",
                "size": 5
            },
            timeout=5
        )
        resp.raise_for_status()
        return [f["properties"]["label"] for f in resp.json().get("features", [])]
    except:
        return []


def ors_geocode(place):
    if not ORS_API_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.openrouteservice.org/geocode/search",
            params={"api_key": ORS_API_KEY, "text": place, "size": 1},
            timeout=10
        )
        resp.raise_for_status()
        feats = resp.json().get("features", [])
        if not feats:
            return None
        coords = feats[0]["geometry"]["coordinates"]
        label = feats[0]["properties"]["label"]
        return coords[1], coords[0], label
    except:
        return None


def get_outage_prediction(lat, lon, i):
    seed = int(lat * 10000 + lon * 10000 + i) % 100000
    rng = np.random.default_rng(seed)
    return (
        rng.uniform(0, 100) > 70 and
        rng.exponential(scale=2) > 1 and
        rng.uniform(20, 80) > 25 and
        rng.integers(0, 10) >= 5
    )


def get_route(start, end):
    start_info = ors_geocode(start)
    end_info   = ors_geocode(end)
    if not start_info or not end_info:
        raise ValueError("Geocoding failed for start or end")

    coords = [[start_info[1], start_info[0]], [end_info[1], end_info[0]]]
    url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json"
    }
    body = {"coordinates": coords, "instructions": False}

    resp = requests.post(url, json=body, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    feats = data.get("features", [])
    if not feats:
        raise ValueError("No route found")

    geom = feats[0]["geometry"]["coordinates"]
    route = [(pt[1], pt[0]) for pt in geom]
    summary = feats[0]["properties"]["summary"]
    return route, start_info, end_info, summary


def show_route_mode():
    st.title("🛣️ GNSS Route Outage Map")

    if not ORS_API_KEY:
        st.error("🚨 ORS_API_KEY not set. Please add it to your .env and restart.")
        return

    if "route_data" not in st.session_state:
        st.session_state.route_data = None

    st.sidebar.header("Route Selection (with Suggestions)")
    start_q = st.sidebar.text_input("Type start location", key="txt_start")
    start_opts = fetch_location_suggestions(start_q)
    start = st.sidebar.selectbox("Choose start", [""] + start_opts, key="sel_start")
    end_q = st.sidebar.text_input("Type end location", key="txt_end")
    end_opts = fetch_location_suggestions(end_q)
    end = st.sidebar.selectbox("Choose end", [""] + end_opts, key="sel_end")

    if st.sidebar.button("🚀 Show Route and GNSS Prediction"):
        if not start or not end:
            st.sidebar.error("Both start and end must be selected from suggestions.")
        else:
            try:
                st.session_state.route_data = get_route(start, end)
            except Exception as e:
                st.sidebar.error(f"Error: {e}")

    if st.session_state.route_data:
        route, s_info, e_info, summary = st.session_state.route_data

        # draw map with fixed key to preserve zoom/pan
        m = folium.Map(location=route[0], zoom_start=6)
        outages = 0
        prev = route[0]
        for i, pt in enumerate(route[1:], 1):
            out = get_outage_prediction(pt[0], pt[1], i)
            if out: outages += 1
            folium.PolyLine([prev, pt],
                            color="red" if out else "green",
                            weight=5, opacity=0.8).add_to(m)
            prev = pt

        folium.Marker(s_info[:2], popup=s_info[2],
                      icon=folium.Icon(color="blue", icon="play")).add_to(m)
        folium.Marker(e_info[:2], popup=e_info[2],
                      icon=folium.Icon(color="orange", icon="flag")).add_to(m)

        st.subheader("🗺️ Route Map")
        st_folium(m, width=900, height=550, key="route_map")

        # clean summary metrics under map
        st.subheader("📊 Route Summary")
        col1, col2 = st.columns(2)
        col1.metric("Distance (km)", f"{summary['distance']/1000:.1f}")
        col1.metric("Duration (min)", f"{summary['duration']/60:.1f}")
        col2.metric("Outage Segments", outages)
        col2.metric("Normal Segments", len(route) - outages)

    else:
        st.info(
            "Enter start/end in the sidebar (select from suggestions),\n"
            "then click “🚀 Show Route and GNSS Prediction”."
        )


if __name__ == "__main__":
    show_route_mode()

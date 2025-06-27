import os
import ssl
import certifi
import requests
import streamlit as st
import pandas as pd
import numpy as np
import folium
from folium.plugins import HeatMap
from datetime import datetime
from geopy.geocoders import Nominatim
from streamlit_folium import st_folium
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

# Load API key
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")


# -- Deterministic RNG by location and time
def seeded_rng(lat, lon, dt):
    seed = int(lat * 1000 + lon * 1000 + dt.timestamp()) % 100000
    return np.random.default_rng(seed)


def get_fixed_values(lat, lon, dt):
    rng = seeded_rng(lat, lon, dt)
    cloud = rng.uniform(0, 100)
    rain = rng.exponential(scale=2)
    tec = rng.uniform(20, 80)
    kp = rng.integers(0, 10)
    return cloud, rain, tec, kp


def simulate_points(n, lat, lon, dt):
    rng = seeded_rng(lat, lon, dt)
    return pd.DataFrame({
        "lat": rng.uniform(lat - 5, lat + 5, n),
        "lon": rng.uniform(lon - 5, lon + 5, n),
        "cloud": rng.uniform(0, 100, n),
        "rain": rng.exponential(scale=2, size=n),
        "tec": rng.uniform(20, 80, n),
        "kp": rng.integers(0, 10, n)
    })


def predict_outage(cloud, rain, tec, kp):
    return (cloud > 70 and rain > 1 and tec > 25 and kp >= 5)


@st.cache_data(ttl=600)
def fetch_openweather(lat, lon):
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    recs = []
    for e in r.json()["list"]:
        recs.append({
            "time": pd.to_datetime(e["dt"], unit="s"),
            "cloud": e["clouds"]["all"],
            "rain": e.get("rain", {}).get("3h", 0.0)
        })
    return pd.DataFrame(recs)


@st.cache_data(ttl=3600)
def fetch_kp():
    r = requests.get("https://services.swpc.noaa.gov/json/planetary_k_index_1m.json", timeout=5)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["time_tag"] = pd.to_datetime(df["time_tag"])
    return df


@st.cache_data(ttl=600)
def geocode_place(place: str):
    from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    geolocator = Nominatim(user_agent="gnss_app", ssl_context=ssl_ctx)

    attempts = [place, place + ", India"]
    for query in attempts:
        try:
            location = geolocator.geocode(query, timeout=10)
            if location:
                short = location.raw.get("display_name", "").split(",")[0]
                return location.latitude, location.longitude, short
        except (GeocoderTimedOut, GeocoderUnavailable):
            continue
    return None


def show_location_mode():
    st.title("📡 GNSS Outage Prediction")

    if "trigger" not in st.session_state:
        st.session_state.trigger = False

    st.sidebar.header("🔎 Location & Forecast Time")
    location_input = st.sidebar.text_input("Location (search required)", "")
    n_pts = st.sidebar.slider("Simulation Points", 500, 5000, 2000, step=500)

    if location_input and st.sidebar.button("🔍 Fetch Available Times"):
        geo = geocode_place(location_input)
        if geo:
            lat, lon, place_name = geo
            st.session_state["loc"] = (lat, lon, place_name)
            st.session_state["weather_df"] = fetch_openweather(lat, lon)
            st.session_state["kp_df"] = fetch_kp()
            st.session_state.prediction_done = False

    if "weather_df" not in st.session_state:
        st.info("📍 Enter a location and click 'Fetch Available Times'")
        return

    times = st.session_state.weather_df["time"].dt.strftime('%Y-%m-%d %H:%M').tolist()
    selected_time_str = st.sidebar.selectbox("Select Forecast Time (UTC)", times)
    dt_sel = pd.to_datetime(selected_time_str)

    if st.sidebar.button("📡 Predict GNSS Outage"):
        lat, lon, place_name = st.session_state["loc"]

        # Use deterministic values
        cloud, rain, tec_now, kp_now = get_fixed_values(lat, lon, dt_sel)

        outage = predict_outage(cloud, rain, tec_now, kp_now)

        # Train model on deterministic points
        train = simulate_points(3000, lat, lon, dt_sel)
        train["outage"] = train.apply(lambda r: predict_outage(r.cloud, r.rain, r.tec, r.kp), axis=1)

        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(train[["cloud", "rain", "tec", "kp"]], train["outage"])

        sim = simulate_points(n_pts, lat, lon, dt_sel)
        sim["out_ml"] = model.predict(sim[["cloud", "rain", "tec", "kp"]])

        st.session_state.prediction = {
            "lat": lat, "lon": lon, "place": place_name,
            "dt": dt_sel, "cloud": cloud, "rain": rain,
            "tec": tec_now, "kp": kp_now, "outage": outage,
            "sim": sim,
            "model_report": classification_report(
                train["outage"], model.predict(train[["cloud", "rain", "tec", "kp"]]), zero_division=0
            )
        }
        st.session_state.prediction_done = True

    if not st.session_state.get("prediction_done", False):
        st.info("📡 Select a time and click 'Predict GNSS Outage' to view the map.")
        return

    p = st.session_state.prediction

    # Sidebar status
    st.sidebar.markdown("### 📍 GNSS Status at Selected Time")
    st.sidebar.write(f"🕒 **{p['dt'].strftime('%Y-%m-%d %H:%M')} UTC**")
    st.sidebar.write(f"☁️ **Cloud:** {p['cloud']:.0f}%")
    st.sidebar.write(f"🌧️ **Rain:** {p['rain']:.2f} mm")
    st.sidebar.write(f"🔵 **TEC:** {p['tec']:.1f}")
    st.sidebar.write(f"🧲 **Kp Index:** {p['kp']}")
    st.sidebar.markdown(f"**Status: {'🔴 GNSS Outage' if p['outage'] else '🟢 No Outage'}**")

    st.subheader("📈 Model Performance")
    st.text(p["model_report"])

    st.subheader("🗺️ Predicted GNSS Outages (Heatmap)")
    m = folium.Map(location=[p["lat"], p["lon"]], zoom_start=6)

    HeatMap(
        p["sim"][p["sim"]["out_ml"] == 1][["lat", "lon"]].values.tolist(),
        radius=12, blur=18, min_opacity=0.5
    ).add_to(m)

    popup = folium.Popup(f"""
    <div style="font-family:Arial; font-size:13px; line-height:1.5">
        <b>📍 Location:</b> {p['place']}<br>
        <b>🕒 Time (UTC):</b> {p['dt'].strftime('%Y-%m-%d %H:%M')}<br>
        <b>☁️ Cloud Cover:</b> {p['cloud']:.0f}%<br>
        <b>🌧️ Rain:</b> {p['rain']:.2f} mm<br>
        <b>🔵 TEC Value:</b> {p['tec']:.1f}<br>
        <b>🧲 Kp Index:</b> {p['kp']}<br>
        <b>Status:</b> {'<span style="color:red"><b>🔴 GNSS Outage</b></span>' if p['outage'] else '<span style="color:green"><b>🟢 No Outage</b></span>'}
    </div>
    """, max_width=300)

    folium.Marker(
        [p["lat"], p["lon"]],
        popup=popup,
        icon=folium.Icon(color="red" if p["outage"] else "green", icon="signal", prefix="fa")
    ).add_to(m)

    st_folium(m, width=1100, height=600)

    if st.sidebar.checkbox("Show Simulated Points Table"):
        st.dataframe(p["sim"])

    st.sidebar.download_button(
        "⬇️ Download Simulated Outages",
        data=p["sim"].to_csv(index=False),
        file_name="gnss_outages.csv",
        mime="text/csv"
    )

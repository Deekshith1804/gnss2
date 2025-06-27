import requests, os
from dotenv import load_dotenv

load_dotenv()
ORS_API_KEY = os.getenv("ORS_API_KEY")

def get_route_coords(start_coords, end_coords):
    url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
    headers = {"Authorization": ORS_API_KEY}
    body = {"coordinates": [start_coords, end_coords]}

    try:
        res = requests.post(url, headers=headers, json=body, timeout=10)
        res.raise_for_status()
        data = res.json()

        coords = data["features"][0]["geometry"]["coordinates"]
        dist = data["features"][0]["properties"]["summary"]["distance"] / 1000
        dur = data["features"][0]["properties"]["summary"]["duration"] / 60
        route_points = [[lat, lon] for lon, lat in coords]  # Convert to lat/lon
        return route_points, round(dist, 2), round(dur, 2)
    except Exception as e:
        print("Route error:", e)
        return [], 0, 0

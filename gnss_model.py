import requests, os, random
from dotenv import load_dotenv
from geopy.geocoders import Nominatim

load_dotenv()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
geolocator = Nominatim(user_agent="gnss-locator")

def get_weather_data(lat, lon):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric"
        res = requests.get(url, timeout=5).json()
        return res.get("clouds", {}).get("all", 0)
    except:
        return random.randint(0, 100)

def get_place_name(lat, lon):
    try:
        location = geolocator.reverse((lat, lon), timeout=5)
        if location:
            return location.address
    except:
        pass
    return f"{lat:.4f}, {lon:.4f}"

def predict_outage_along_route(route_points):
    results = []
    for lat, lon in route_points[::3]:  # Downsample by 3
        cloud = get_weather_data(lat, lon)
        tec = round(random.uniform(1, 35), 2)
        kp = random.randint(1, 9)
        outage = cloud > 70 and tec > 20 and kp >= 6

        results.append({
            "lat": lat,
            "lon": lon,
            "place": get_place_name(lat, lon),
            "cloud_cover": cloud,
            "tec": tec,
            "geomagnetic": kp,
            "outage": outage
        })
    return results

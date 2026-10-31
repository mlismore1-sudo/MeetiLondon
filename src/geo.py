import math

import requests
import streamlit as st


@st.cache_data(ttl=86400)
def geocode_postcode(postcode):
    postcode = postcode.strip().upper().replace(" ", "")

    response = requests.get(
        f"https://api.postcodes.io/postcodes/{postcode}",
        timeout=10,
    )

    if response.status_code != 200:
        return None

    result = response.json()["result"]
    return result["latitude"], result["longitude"]


def distance_km(lat1, lon1, lat2, lon2):
    radius = 6371

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )

    return 2 * radius * math.asin(math.sqrt(a))


def find_nearby_places(places, postcode, radius_km):
    origin = geocode_postcode(postcode)

    if origin is None:
        st.error("That postcode could not be found.")
        return []

    origin_lat, origin_lon = origin
    nearby = []

    for place in places:
        if place.get("latitude") is None or place.get("longitude") is None:
            continue

        distance = distance_km(
            origin_lat,
            origin_lon,
            place["latitude"],
            place["longitude"],
        )

        if distance <= radius_km:
            nearby.append({**place, "distance_km": round(distance, 2)})

    return sorted(nearby, key=lambda x: x["distance_km"])

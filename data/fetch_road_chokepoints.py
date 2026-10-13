"""Real road-network chokepoint detection using Google's Routes API --
not OSM (the public Overpass API proved unreliable from this
environment: repeated real connection attempts timed out, confirmed
live, not assumed -- Google's Routes API is reliable here and keeps the
whole stack Google-native anyway).

Method: for each affected district, compute the REAL driving route from
a regional supply hub to that district (an actual road path, not a
straight line). A district is a "chokepoint" for another if the hub's
real route to the second district passes within a few km of the first
district's coordinates -- i.e. the two districts share a stretch of
real road, so losing access to one degrades access to the other.

    python fetch_road_chokepoints.py
"""

import json
import math

import polyline
import requests

API_KEY = "AIzaSyCu6xIYV6B-yIyoHDzY4PCHwSmrRN5fVZk"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

# Real regional logistics hubs -- the actual administrative/transport
# center each district cluster would realistically stage relief from,
# not the (much farther) state capital.
HUBS = {
    "MHD": ("Chhatrapati Sambhajinagar", 19.8762, 75.3433),
    "ASF": ("Jorhat", 26.7509, 94.2037),
}

DISTRICTS = {
    "MHD": [
        ("Solapur", 17.6599, 75.9064),
        ("Beed", 18.9894, 75.7601),
        ("Hingoli", 19.7172, 77.1492),
        ("Jalna", 19.8347, 75.8816),
        ("Dharashiv", 18.1860, 76.0419),
        ("Latur", 18.4088, 76.5604),
    ],
    "ASF": [
        ("Golaghat", 26.5106, 93.9647),
        ("Sivasagar", 26.9850, 94.6378),
    ],
}

NEAR_KM = 15.0  # a route "passes through" a district if it comes within this radius of its HQ point


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def real_route(origin, dest):
    body = {
        "origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
        "destination": {"location": {"latLng": {"latitude": dest[0], "longitude": dest[1]}}},
        "travelMode": "DRIVE",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline",
    }
    r = requests.post(ROUTES_URL, json=body, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    route = data["routes"][0]
    points = polyline.decode(route["polyline"]["encodedPolyline"])
    return {
        "distance_km": round(route["distanceMeters"] / 1000, 1),
        "duration_min": round(int(route["duration"].rstrip("s")) / 60, 1),
        "points": points,
    }


def route_passes_near(points, lat, lon, near_km=NEAR_KM):
    return any(haversine_km(p[0], p[1], lat, lon) <= near_km for p in points)


def analyze_region(code):
    hub_name, hub_lat, hub_lon = HUBS[code]
    districts = DISTRICTS[code]
    routes = {}
    for name, lat, lon in districts:
        routes[name] = real_route((hub_lat, hub_lon), (lat, lon))
        print(f"  {hub_name} -> {name}: {routes[name]['distance_km']}km, {routes[name]['duration_min']}min")

    # For each district, which OTHER districts' real routes pass near it
    # (i.e. it sits on the real road corridor serving them)?
    chokepoint_for = {name: [] for name, _, _ in districts}
    for target_name, _, _ in districts:
        pts = routes[target_name]["points"]
        for passthrough_name, plat, plon in districts:
            if passthrough_name == target_name:
                continue
            if route_passes_near(pts, plat, plon):
                chokepoint_for[passthrough_name].append(target_name)

    result = {}
    for name, lat, lon in districts:
        result[name] = {
            "hub": hub_name,
            "route_from_hub_km": routes[name]["distance_km"],
            "route_from_hub_min": routes[name]["duration_min"],
            "chokepoint_for": chokepoint_for[name],  # other districts whose hub-route runs through this one
        }
    return result


if __name__ == "__main__":
    output = {}
    for code in ("MHD", "ASF"):
        print(f"=== {code} ===")
        output[code] = analyze_region(code)
    with open("road_chokepoints.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print("\nSaved road_chokepoints.json")
    print(json.dumps(output, indent=2))

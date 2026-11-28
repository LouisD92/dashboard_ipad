"""
Prépare data/stations.json pour l'onglet Carburant : l'enseigne de chaque station.

Les prix officiels (data.economie.gouv.fr) sont lus en direct par la page,
mais ils ne donnent pas le nom des stations. On les retrouve dans
OpenStreetMap (station la plus proche, à moins de 250 m).
Seule la bibliothèque standard de Python est utilisée.
"""
import json
import math
import os
import urllib.parse
import urllib.request

CENTRE = (47.4705, -0.5560)   # Angers
RAYON_KM = 20
SORTIE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "stations.json")
UA = {"User-Agent": "tableau-de-bord-perso/1.0"}
GOUV = ("https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/prix-des-carburants-en-france-flux-instantane-v2/records"
        "?select=id,geom&limit=100&offset={off}&where=" +
        urllib.parse.quote("within_distance(geom, geom'POINT(%s %s)', %dkm)" % (CENTRE[1], CENTRE[0], RAYON_KM)))
ENSEIGNES = [  # (mot-clé, nom affiché)
    ("leclerc", "E.Leclerc"), ("intermarch", "Intermarché"), ("netto", "Netto"), ("carrefour", "Carrefour"),
    ("auchan", "Auchan"), ("super u", "Super U"), ("hyper u", "Hyper U"), ("système u", "Station U"), ("station u", "Station U"),
    ("total", "TotalEnergies"), ("esso", "Esso"), ("bp", "BP"), ("shell", "Shell"), ("avia", "Avia"), ("elan", "Elan"),
    ("dyneff", "Dyneff"), ("agip", "Agip"), ("casino", "Casino"), ("lidl", "Lidl"), ("aldi", "Aldi"),
]


def get(url, data=None):
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def dist(a, b):
    return math.hypot((a[0] - b[0]) * 111.0, (a[1] - b[1]) * 111.0 * math.cos(math.radians(a[0]))) * 1000


def enseigne(t):
    brut = t.get("brand") or t.get("name") or t.get("operator") or ""
    bas = brut.lower()
    if bas.strip() in ("u",):
        return "Station U"
    for cle, nom in ENSEIGNES:
        if cle in bas:
            return nom
    return brut.strip()


def main():
    stations, off = [], 0
    while True:
        page = get(GOUV.format(off=off)).get("results", [])
        stations += page
        if len(page) < 100:
            break
        off += 100
    q = '[out:json][timeout:60];nwr["amenity"="fuel"](around:%d,%s,%s);out center tags;' % ((RAYON_KM + 1) * 1000, CENTRE[0], CENTRE[1])
    osm = get("https://overpass-api.de/api/interpreter", urllib.parse.urlencode({"data": q}).encode())["elements"]
    pts = []
    for e in osm:
        la, lo = (e["lat"], e["lon"]) if "lat" in e else (e["center"]["lat"], e["center"]["lon"])
        nom = enseigne(e.get("tags", {}))
        if nom:
            pts.append(((la, lo), nom))
    out = {}
    for s in stations:
        g = s.get("geom") or {}
        if "lat" not in g:
            continue
        best = min(pts, key=lambda p: dist(p[0], (g["lat"], g["lon"])), default=None)
        if best and dist(best[0], (g["lat"], g["lon"])) < 250:
            out[str(s["id"])] = best[1]
    os.makedirs(os.path.dirname(SORTIE), exist_ok=True)
    with open(SORTIE, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print("OK", SORTIE, len(stations), "stations,", len(out), "enseignes retrouvées")


if __name__ == "__main__":
    main()

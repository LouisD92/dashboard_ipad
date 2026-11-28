"""
Prépare data/tram.json pour l'onglet Tram du tableau de bord.

Source : le GTFS du réseau Irigo (Angers Loire Métropole, licence ouverte,
publié sur transport.data.gouv.fr). On n'en garde que les 3 lignes de tram :
- le tracé de chaque ligne dans chaque sens (simplifié)
- les arrêts, regroupés par nom, avec leur position le long du tracé
Les horaires en temps réel sont lus en direct par la page (via le relais Cloudflare).
Seule la bibliothèque standard de Python est utilisée.
"""
import csv
import io
import json
import math
import os
import urllib.request
import zipfile
from collections import Counter, defaultdict

GTFS = "https://chouette.enroute.mobi/api/v1/datas/Irigo/gtfs.zip"
SORTIE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "tram.json")
LIGNES = ["A", "B", "C"]


def lire(z, nom):
    return list(csv.DictReader(io.TextIOWrapper(z.open(nom), encoding="utf-8-sig")))


def dist(a, b):  # mètres (approximation locale suffisante à l'échelle d'une ville)
    k = math.cos(math.radians(a[0])) * 111320
    return math.hypot((a[0] - b[0]) * 110540, (a[1] - b[1]) * k)


def simplifier(pts, tol=3.0):  # Douglas-Peucker
    if len(pts) < 3:
        return pts
    garde = [False] * len(pts)
    garde[0] = garde[-1] = True
    pile = [(0, len(pts) - 1)]
    while pile:
        i, j = pile.pop()
        a, b = pts[i], pts[j]
        dmax, imax = 0, None
        ab = dist(a, b) or 1e-9
        for k in range(i + 1, j):
            p = pts[k]
            # distance du point au segment [a, b]
            t = max(0, min(1, ((p[0] - a[0]) * (b[0] - a[0]) * 110540 ** 2 + (p[1] - a[1]) * (b[1] - a[1]) * (math.cos(math.radians(a[0])) * 111320) ** 2) / ab ** 2))
            q = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
            d = dist(p, q)
            if d > dmax:
                dmax, imax = d, k
        if imax is not None and dmax > tol:
            garde[imax] = True
            pile += [(i, imax), (imax, j)]
    return [p for p, g in zip(pts, garde) if g]


def projeter(pts, cum, p):  # distance le long du tracé du point le plus proche de p
    best, bd = 0, 1e18
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        l = cum[i + 1] - cum[i] or 1e-9
        k = math.cos(math.radians(a[0])) * 111320
        t = ((p[0] - a[0]) * (b[0] - a[0]) * 110540 ** 2 + (p[1] - a[1]) * (b[1] - a[1]) * k * k) / (l * l)
        t = max(0, min(1, t))
        q = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        d = dist(p, q)
        if d < bd:
            bd, best = d, cum[i] + t * l
    return best


def main():
    with urllib.request.urlopen(urllib.request.Request(GTFS, headers={"User-Agent": "tableau-de-bord-perso/1.0"}), timeout=120) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    routes = {r["route_id"]: r for r in lire(z, "routes.txt") if r["route_id"] in LIGNES}
    trips = [t for t in lire(z, "trips.txt") if t["route_id"] in routes]
    stops = {s["stop_id"]: s for s in lire(z, "stops.txt")}

    # Tracé principal (le plus utilisé) pour chaque ligne et chaque sens
    usage = Counter((t["route_id"], t["direction_id"], t["shape_id"]) for t in trips)
    principal = {}
    for (rid, d, sh), n in usage.most_common():
        principal.setdefault((rid, d), sh)
    voulus = set(principal.values())
    formes = defaultdict(list)
    for p in lire(z, "shapes.txt"):
        if p["shape_id"] in voulus:
            formes[p["shape_id"]].append((int(p["shape_pt_sequence"]), float(p["shape_pt_lat"]), float(p["shape_pt_lon"])))

    # Arrêts desservis par un voyage type de chaque tracé principal (celui qui a le plus d'arrêts)
    voyages = defaultdict(list)
    for t in trips:
        if principal.get((t["route_id"], t["direction_id"])) == t["shape_id"]:
            voyages[(t["route_id"], t["direction_id"])].append(t["trip_id"])
    echantillon = {k: set(v[:40]) for k, v in voyages.items()}
    tous = set().union(*echantillon.values())
    seq = defaultdict(list)
    for st in lire(z, "stop_times.txt"):
        if st["trip_id"] in tous:
            seq[st["trip_id"]].append((int(st["stop_sequence"]), st["stop_id"]))
    # Tous les quais de tram (y compris ceux des voyages partiels)
    quais = set()
    for st_list in seq.values():
        for _, sid in st_list:
            quais.add(sid)

    lignes = []
    groupes, index = [], {}
    def groupe(sid):
        s = stops[sid]
        nom = s["stop_name"].strip()
        if nom not in index:
            index[nom] = len(groupes)
            groupes.append({"n": nom, "ids": [], "pts": [], "l": set()})
        g = groupes[index[nom]]
        if sid not in g["ids"]:
            g["ids"].append(sid)
            g["pts"].append((float(s["stop_lat"]), float(s["stop_lon"])))
        return index[nom]

    for rid in LIGNES:
        r = routes[rid]
        sens = []
        for d in ("0", "1"):
            sh = principal.get((rid, d))
            if not sh:
                continue
            pts = [(la, lo) for _, la, lo in sorted(formes[sh])]
            pts = simplifier(pts)
            cum = [0.0]
            for i in range(1, len(pts)):
                cum.append(cum[-1] + dist(pts[i - 1], pts[i]))
            type_ = max((seq[t] for t in echantillon[(rid, d)]), key=len)
            arrets = []
            for _, sid in sorted(type_):
                s = stops[sid]
                gi = groupe(sid)
                groupes[gi]["l"].add(rid)
                arrets.append([sid, round(projeter(pts, cum, (float(s["stop_lat"]), float(s["stop_lon"]))))])
            tete = Counter(t["trip_headsign"] for t in trips if t["route_id"] == rid and t["direction_id"] == d).most_common(1)[0][0]
            sens.append({"d": int(d), "dest": tete, "pts": [[round(a, 5), round(b, 5)] for a, b in pts],
                         "cum": [round(c) for c in cum], "arrets": arrets})
        lignes.append({"id": rid, "couleur": "#" + r["route_color"], "nom": r["route_long_name"], "sens": sens})

    # Quais restants (voyages partiels) rattachés à leur arrêt
    for sid in quais:
        groupe(sid)
    sortie_groupes = []
    for g in groupes:
        la = sum(p[0] for p in g["pts"]) / len(g["pts"])
        lo = sum(p[1] for p in g["pts"]) / len(g["pts"])
        sortie_groupes.append({"n": g["n"], "la": round(la, 5), "lo": round(lo, 5), "ids": g["ids"], "l": "".join(sorted(g["l"]))})
    noms = {sid: stops[sid]["stop_name"].strip() for sid in stops}

    data = {"lignes": lignes, "arrets": sortie_groupes,
            "noms": {sid: noms[sid] for g in groupes for sid in g["ids"]}}
    os.makedirs(os.path.dirname(SORTIE), exist_ok=True)
    with open(SORTIE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print("OK", SORTIE, len(lignes), "lignes,", len(sortie_groupes), "arrêts,",
          sum(len(s["pts"]) for l in lignes for s in l["sens"]), "points de tracé")


if __name__ == "__main__":
    main()

"""
Prépare data/cine.json pour l'onglet Ciné du tableau de bord.
Lancé automatiquement par GitHub toutes les 3 heures (.github/workflows/cine.yml).

Source : les données publiques du site pathe.fr (films, résumés, séances).
- À l'affiche : films sortis depuis moins de 8 semaines
- Sorties du mois et du mois prochain
- Séances du Pathé Angers pour aujourd'hui et demain
Seule la bibliothèque standard de Python est utilisée.
"""
import datetime as dt
import html
import json
import re
import os
import time
import urllib.request

API = "https://www.pathe.fr/api/"
CINEMA = "cinema-pathe-angers"
SORTIE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "cine.json")
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]


def get(path):
    req = urllib.request.Request(API + path + ("&" if "?" in path else "?") + "language=fr",
                                 headers={"User-Agent": "tableau-de-bord-perso/1.0"})
    for essai in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 + essai * 3)
    return None


def date_fr(f):
    d = (f.get("releaseAt") or {}).get("FR_FR")
    return dt.date.fromisoformat(d) if d else None


def main():
    today = dt.date.today()
    shows = (get("shows") or {}).get("shows", [])
    films = [f for f in shows if f.get("isMovie")]

    m0 = today.replace(day=1)
    m1 = (m0 + dt.timedelta(days=32)).replace(day=1)
    m2 = (m1 + dt.timedelta(days=32)).replace(day=1)

    def entre(f, a, b):
        d = date_fr(f)
        return d is not None and a <= d < b

    now = [f for f in films if not f.get("isComingSoon") and entre(f, today - dt.timedelta(weeks=8), today + dt.timedelta(days=1))]
    now.sort(key=lambda f: f.get("homeOrder") or 9999)
    sort0 = sorted([f for f in films if entre(f, m0, m1)], key=lambda f: (date_fr(f), f.get("upcomingOrder") or 9999))
    sort1 = sorted([f for f in films if entre(f, m1, m2)], key=lambda f: (date_fr(f), f.get("upcomingOrder") or 9999))
    now, sort0, sort1 = now[:45], sort0[:60], sort1[:60]

    # Séances au Pathé Angers (aujourd'hui et demain)
    jours = [today.isoformat(), (today + dt.timedelta(days=1)).isoformat()]
    cine = (get("cinema/%s/shows" % CINEMA) or {}).get("shows", {})
    seances = {}
    for slug, info in cine.items():
        dispo = [j for j in jours if j in (info.get("days") or {})]
        for j in dispo:
            st = get("show/%s/showtimes/%s/%s" % (slug, CINEMA, j)) or []
            liste = []
            for s in st:
                tags = s.get("tags") or []
                extra = "IMAX" if "imax" in tags else "4DX" if "4dx" in tags else ""
                liste.append([s.get("time", "")[11:16], (s.get("version") or "").upper(), extra])
            if liste:
                seances.setdefault(slug, {})[j] = liste
            time.sleep(0.3)

    # Résumés (une requête par film retenu)
    garder = {}
    for f in now + sort0 + sort1:
        garder[f["slug"]] = f
    for slug in seances:
        if slug not in garder:
            f = next((x for x in shows if x.get("slug") == slug), None)
            if f:
                garder[slug] = f
                now.append(f)  # projeté à Angers : forcément à l'affiche

    def fiche(f):
        detail = get("show/%s" % f["slug"]) or {}
        time.sleep(0.2)
        d = date_fr(f)
        poster = (f.get("posterPath") or {}).get("md") or (f.get("posterPath") or {}).get("sm") or ""
        return {
            "slug": f["slug"], "titre": f.get("title", ""), "date": d.isoformat() if d else "",
            "duree": f.get("duration") or 0, "genres": (f.get("genres") or [])[:3],
            "public": ((f.get("contentRating") or {}).get("description") or ""),
            "affiche": poster, "real": f.get("directors") or "", "avec": f.get("hubbleCasting") or "",
            "resume": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", detail.get("synopsis") or ""))).replace("Synopsis :", "").strip()[:420],
            "seances": seances.get(f["slug"], {}),
        }

    cache = {}
    def fiches(lst):
        out = []
        for f in lst:
            if f["slug"] not in cache:
                cache[f["slug"]] = fiche(f)
            out.append(cache[f["slug"]])
        return out

    if not films:  # Pathé injoignable (ou refuse ce serveur) : on garde les données précédentes
        print("Pathé injoignable : data/cine.json n'est pas modifié")
        return
    data = {
        "maj": dt.datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "cinema": "Pathé Angers", "jours": jours,
        "listes": [
            {"id": "now", "nom": "À l'affiche", "films": fiches(now)},
            {"id": "m0", "nom": "Sorties de " + MOIS[m0.month - 1], "films": fiches(sort0)},
            {"id": "m1", "nom": "Sorties de " + MOIS[m1.month - 1], "films": fiches(sort1)},
        ],
    }
    os.makedirs(os.path.dirname(SORTIE), exist_ok=True)
    with open(SORTIE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print("OK", SORTIE, len(data["listes"][0]["films"]), "à l'affiche,",
          len(data["listes"][1]["films"]), "+", len(data["listes"][2]["films"]), "sorties,",
          len(seances), "films avec séances à Angers")


if __name__ == "__main__":
    main()

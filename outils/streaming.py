"""
Prépare data/streaming.json pour l'onglet Ciné : les nouveautés de la semaine
sur Netflix, Disney+ et Prime Video en France.

Source : le catalogue public de JustWatch (les mêmes données que sa page
« Nouveautés »). On garde les 7 derniers jours, abonnement uniquement,
en mettant en avant les films et séries récents plutôt que les vieux
films qui reviennent au catalogue.
Seule la bibliothèque standard de Python est utilisée.
"""
import datetime as dt
import json
import os
import time
import urllib.request

API = "https://apis.justwatch.com/graphql"
SORTIE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "streaming.json")
PLATEFORMES = [("nfx", "Netflix"), ("dnp", "Disney+"), ("prv", "Prime Video")]
REQ = """query N($country: Country!, $date: Date!, $filter: TitleFilter, $first: Int!) {
  newTitles(country: $country, date: $date, filter: $filter, first: $first, pageType: NEW, priceDrops: false) {
    edges {
      newOffer(platform: WEB) { package { clearName shortName } monetizationType }
      node {
        id objectType
        content(country: $country, language: "fr") {
          title shortDescription originalReleaseYear posterUrl fullPath runtime
          genres { shortName }
          scoring { imdbScore }
        }
        ... on Season {
          totalEpisodeCount
          show { content(country: $country, language: "fr") { title posterUrl fullPath shortDescription originalReleaseYear } }
        }
      }
    }
  }
}"""
GENRES = {"act": "Action", "ani": "Animation", "cmy": "Comédie", "crm": "Policier", "doc": "Documentaire", "drm": "Drame",
          "fnt": "Fantastique", "hst": "Histoire", "hrr": "Horreur", "fml": "Famille", "msc": "Musique", "trl": "Thriller",
          "rma": "Romance", "scf": "Science-fiction", "spt": "Sport", "war": "Guerre", "wsn": "Western", "rly": "Téléréalité", "eur": "Europe"}


def requete(jour, pkg):
    body = json.dumps({"query": REQ, "variables": {"country": "FR", "date": jour, "first": 60,
                                                    "filter": {"packages": [pkg], "monetizationTypes": ["FLATRATE"]}}}).encode()
    for essai in range(3):
        try:
            req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (tableau de bord perso)"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return ((json.load(r).get("data") or {}).get("newTitles") or {}).get("edges") or []
        except Exception:
            time.sleep(2 + essai * 3)
    return []


def affiche(path):
    return "https://images.justwatch.com" + path.replace("{profile}", "s332").replace("{format}", "jpg") if path else ""


def main():
    today = dt.date.today()
    annee = today.year
    vus, titres = set(), []
    for n in range(7):
        jour = (today - dt.timedelta(days=n)).isoformat()
        for pkg, nom in PLATEFORMES:
            for e in requete(jour, pkg):
                node, c = e.get("node") or {}, (e.get("node") or {}).get("content") or {}
                saison = node.get("objectType") == "SHOW_SEASON"
                show = ((node.get("show") or {}).get("content") or {}) if saison else {}
                cle = (pkg, (show.get("fullPath") if saison else c.get("fullPath")) or node.get("id"))
                if cle in vus:
                    continue
                vus.add(cle)
                an = (show.get("originalReleaseYear") if saison else c.get("originalReleaseYear")) or 0
                recent = saison or an >= annee - 1  # nouvelle saison, ou film/série de l'année
                titres.append({
                    "p": nom, "pk": pkg, "jour": jour,
                    "type": "Saison" if saison else ("Série" if node.get("objectType") == "SHOW" else "Film"),
                    "titre": show.get("title") if saison else c.get("title"),
                    "saison": c.get("title") if saison else "",
                    "ep": node.get("totalEpisodeCount") or 0,
                    "an": an, "neuf": recent,
                    "duree": c.get("runtime") or 0,
                    "genres": [GENRES.get(g["shortName"], "") for g in (c.get("genres") or [])][:2],
                    "note": ((c.get("scoring") or {}).get("imdbScore")) or 0,
                    "affiche": affiche(c.get("posterUrl") or show.get("posterUrl")),
                    "resume": ((c.get("shortDescription") or show.get("shortDescription") or "").strip())[:360],
                    "lien": "https://www.justwatch.com" + ((show.get("fullPath") if saison else c.get("fullPath")) or ""),
                })
            time.sleep(0.4)
    # Récents d'abord (par date d'arrivée), puis le reste du catalogue ajouté
    titres.sort(key=lambda t: (not t["neuf"], t["jour"] and -int(t["jour"].replace("-", "")), -(t["note"] or 0)))
    data = {"maj": dt.datetime.now().strftime("%Y-%m-%dT%H:%M"), "du": (today - dt.timedelta(days=6)).isoformat(), "au": today.isoformat(),
            "plateformes": [p[1] for p in PLATEFORMES], "titres": titres}
    os.makedirs(os.path.dirname(SORTIE), exist_ok=True)
    with open(SORTIE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    from collections import Counter
    print("OK", SORTIE, len(titres), "titres", dict(Counter(t["p"] for t in titres)), sum(t["neuf"] for t in titres), "récents")


if __name__ == "__main__":
    main()

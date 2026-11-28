"""
Prépare data/tvsport.json pour l'onglet TV > Sport : les matchs des 7 prochains
jours et leurs chaînes en France, aux États-Unis, au Canada et au Royaume-Uni.

Sources (lues ici car aucune n'est lisible directement par une page web) :
- Matchs + chaînes US : ESPN (scoreboard, « geoBroadcasts »)
- France : guide TV complet xmltvfr.fr (Canal+, beIN, DAZN, Ligue 1+, RMC Sport,
  Eurosport, L'Équipe, chaînes de la TNT…) ; un programme est rattaché à un
  match s'il commence à l'heure du coup d'envoi avec les mêmes équipes.
  Les autres sports en direct (ski, biathlon, tennis, cyclisme…) sont listés à part.
- Canada : calendrier officiel NHL (Sportsnet, TSN, TVA Sports, CBC…) ;
  pour quelques compétitions, le diffuseur qui a tous les matchs.
- Royaume-Uni : live-footballontv.com (football) ; F1 et NFL : diffuseur de toute la saison.
Seule la bibliothèque standard de Python est utilisée.
"""
import datetime as dt
import gzip
import html
import io
import json
import os
import re
import time
import unicodedata
import urllib.request
from zoneinfo import ZoneInfo

SORTIE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "tvsport.json")
UA = {"User-Agent": "Mozilla/5.0 (tableau de bord perso)"}
ESPN = "https://site.api.espn.com/apis/site/v2/sports/"
JOURS = 7
LIGUES = [  # (id, sport ESPN, slug, nom court, famille)
    ("l1", "soccer", "fra.1", "Ligue 1", "foot"), ("l2", "soccer", "fra.2", "Ligue 2", "foot"),
    ("pl", "soccer", "eng.1", "Premier League", "foot"), ("champ", "soccer", "eng.2", "Championship", "foot"),
    ("liga", "soccer", "esp.1", "Liga", "foot"), ("seriea", "soccer", "ita.1", "Serie A", "foot"),
    ("bund", "soccer", "ger.1", "Bundesliga", "foot"), ("ucl", "soccer", "uefa.champions", "Ligue des champions", "foot"),
    ("uel", "soccer", "uefa.europa", "Ligue Europa", "foot"), ("uecl", "soccer", "uefa.europa.conf", "Conference League", "foot"),
    ("top14", "rugby", "270559", "Top 14", "rugby"), ("nfl", "football", "nfl", "NFL", "nfl"),
    ("nba", "basketball", "nba", "NBA", "nba"), ("nhl", "hockey", "nhl", "NHL", "nhl"), ("f1", "racing", "f1", "F1", "f1"),
]
# Diffuseurs qui ont TOUS les matchs d'une compétition (marqués « tous les matchs » dans la page)
TOUS = {
    "ca": {"pl": ["Fubo"], "ucl": ["DAZN"], "uel": ["DAZN"], "uecl": ["DAZN"], "nfl": ["DAZN"], "f1": ["TSN", "RDS"]},
    "uk": {"f1": ["Sky Sports F1"], "nfl": ["DAZN"]},
}
TZ_FR, TZ_UK = ZoneInfo("Europe/Paris"), ZoneInfo("Europe/London")
VIDES = {"fc", "sc", "ac", "as", "rc", "cf", "afc", "club", "de", "du", "la", "le", "les", "of", "the", "sporting", "football", "ud", "cd", "sd", "ss", "us", "sv", "vfb", "vfl", "tsg", "fsv", "bsc", "real", "city", "united", "athletic", "atletico", "stade", "olympique", "town", "county", "hotspur", "albion", "wanderers", "rovers"}
ALIAS = {"paris-sg": "paris saint-germain psg", "paris sg": "paris saint-germain psg", "psg": "paris saint-germain", "om": "marseille", "ol": "lyon",
         "man utd": "manchester united", "man city": "manchester city", "spurs": "tottenham", "wolves": "wolverhampton",
         "inter milan": "internazionale inter", "ac milan": "milan", "bayern munich": "bayern munchen", "borussia dortmund": "dortmund",
         "brême": "bremen", "cologne": "koln", "mayence": "mainz", "francfort": "frankfurt", "fribourg": "freiburg", "naples": "napoli",
         "rome": "roma", "turin": "torino", "lisbonne": "lisbon", "glasgow rangers": "rangers",
         "toulouse": "toulousain", "toulousain": "toulouse", "section paloise": "pau", "ubb": "bordeaux", "lou": "lyon",
         "usap": "perpignan", "rct": "toulon", "aviron bayonnais": "bayonne", "asm": "clermont", "stade rochelais": "rochelle"}


def get(url, data=None, binaire=False):
    for essai in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=UA), timeout=60) as r:
                b = r.read()
                return b if binaire else json.loads(b)
        except Exception:
            time.sleep(1 + essai * 2)
    return None


def plat(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def jetons(nom):
    n = nom.lower().strip()
    n = ALIAS.get(n, n) + " " + n
    for k, v in ALIAS.items():
        if k in n:
            n += " " + v
    return {t for t in re.split(r"[^a-z0-9]+", plat(n)) if (len(t) >= 3 or t.isdigit()) and t not in VIDES}


def correspond(a, b, ev):
    """Les deux noms a et b désignent-ils les deux équipes du match ev ?"""
    h, w = ev["_jh"], ev["_jw"]
    ja, jb = jetons(a), jetons(b)
    return (ja & h and jb & w) or (ja & w and jb & h)


def ajouter(ev, pays, chaine, local=""):
    l = ev["ch"].setdefault(pays, [])
    if chaine and not any(c[0] == chaine for c in l):
        l.append([chaine, local])


# ---------- 1. Matchs (ESPN) + chaînes US ----------
def matchs():
    out, today = [], dt.date.today()
    for lid, sport, slug, nom, fam in LIGUES:
        for n in range(JOURS):
            d = (today + dt.timedelta(days=n)).strftime("%Y%m%d")
            sb = get("%s%s/%s/scoreboard?dates=%s" % (ESPN, sport, slug, d)) or {}
            for e in sb.get("events", []):
                c = (e.get("competitions") or [{}])[0]
                st = ((e.get("status") or {}).get("type") or {}).get("state")
                if st == "post":
                    continue
                cps = c.get("competitors") or []
                home = next((x for x in cps if x.get("homeAway") == "home"), None)
                away = next((x for x in cps if x.get("homeAway") == "away"), None)
                ev = {"id": e["id"], "l": lid, "lig": nom, "f": fam, "t": e.get("date"), "live": st == "in", "ch": {}}
                if fam == "f1" or not home or not away:
                    ev["titre"] = e.get("name") or e.get("shortName") or nom
                    ev["_jh"] = ev["_jw"] = set()
                else:
                    th, tw = home.get("team") or {}, away.get("team") or {}
                    ev.update({"dom": th.get("shortDisplayName") or th.get("displayName"), "ext": tw.get("shortDisplayName") or tw.get("displayName"),
                               "ld": th.get("logo", ""), "le": tw.get("logo", ""),
                               "_jh": jetons(th.get("displayName", "") + " " + th.get("shortDisplayName", "")),
                               "_jw": jetons(tw.get("displayName", "") + " " + tw.get("shortDisplayName", ""))})
                    ev["_nh"], ev["_na"] = th.get("name", ""), tw.get("name", "")
                for g in c.get("geoBroadcasts") or []:
                    mk = ((g.get("market") or {}).get("type") or "").lower()
                    nm = (g.get("media") or {}).get("shortName")
                    if nm:
                        ajouter(ev, "us", nm, "" if mk == "national" else ("local " + ("dom." if mk == "home" else "ext.")))
                for pays, regles in TOUS.items():
                    for ch in regles.get(lid, []):
                        ajouter(ev, pays, ch, "tous les matchs")
                if not any(x["id"] == ev["id"] and x["l"] == lid for x in out):
                    out.append(ev)
            time.sleep(0.15)
    return out


def utc(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------- 2. France : guide TV complet ----------
CHAINES_SPORT = re.compile(r"^(beIN|CanalPlus(Foot|Sport|PremierLeague|Ligue1|Live)?|RMCSport|Eurosport|DAZN|Ligue1Plus|LEquipe|SportEnFrance|InfosportPlus|TF1\.|France2\.|France3\.|France4|M6\.|W9|TMC|TFX|Automoto)", re.I)


def france(evs):
    gz = get("https://xmltvfr.fr/xmltv/xmltv_fr.xml.gz", binaire=True)
    if not gz:
        print("Guide TV France indisponible")
        return []
    x = gzip.decompress(gz).decode("utf-8", "ignore")
    noms = {m.group(1): html.unescape(m.group(2)) for m in re.finditer(r'<channel id="([^"]+)">\s*<display-name[^>]*>([^<]+)</display-name>', x)}
    maintenant = dt.datetime.now(dt.timezone.utc)
    fin = maintenant + dt.timedelta(days=JOURS)
    autres = {}
    reP = re.compile(r'<programme start="(\d{14}) ([+-]\d{4})" stop="(\d{14}) ([+-]\d{4})" channel="([^"]+)">(.*?)</programme>', re.S)
    for m in reP.finditer(x):
        ch = m.group(5)
        if not CHAINES_SPORT.match(ch):
            continue
        b = m.group(6)
        cats = " ".join(re.findall(r"<category[^>]*>([^<]*)</category>", b))
        if not re.search(r"sport|football|rugby|basket|hockey|tennis|cyclisme|ski|biathlon|athl|natation|handball|volley|golf|boxe|combat|moto|auto|formule|nautique|équitation", cats, re.I):
            continue
        if re.search(r"Magazine|Documentaire|Jeu|Talk", cats):
            continue
        debut = dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S%z")
        stop = dt.datetime.strptime(m.group(3) + m.group(4), "%Y%m%d%H%M%S%z")
        if stop < maintenant or debut > fin:
            continue
        rediff = "<previously-shown" in b
        titre = html.unescape((re.search(r"<title[^>]*>([^<]*)</title>", b) or [None, ""])[1]).strip()
        sous = html.unescape((re.search(r"<sub-title[^>]*>([^<]*)</sub-title>", b) or [None, ""])[1]).strip()
        chaine = noms.get(ch, ch.replace(".fr", ""))
        equipes = titre.split(" | ")[-1] if " | " in titre else titre
        trouve = False
        if " / " in equipes:
            a, c = [p.strip() for p in equipes.split(" / ", 1)]
            for ev in evs:
                if ev["_jh"] and abs((debut - utc(ev["t"])).total_seconds()) <= 45 * 60 and correspond(a, c, ev):
                    ajouter(ev, "fr", chaine)
                    trouve = True
        # Autres sports en direct (pas déjà rattachés à un match suivi, pas des rediffusions)
        if not trouve and not rediff and " : " in titre and not re.match(r"(Football|Basket-ball|Football américain|Hockey sur glace|Rugby : Top 14)\b", titre):
            cle = (titre, debut.isoformat())
            a = autres.setdefault(cle, {"t": debut.astimezone(dt.timezone.utc).isoformat(), "fin": stop.astimezone(dt.timezone.utc).isoformat(),
                                        "titre": titre, "sous": sous[:110], "ch": []})
            if chaine not in a["ch"]:
                a["ch"].append(chaine)
    return sorted(autres.values(), key=lambda a: a["t"])


# ---------- 3. Canada : calendrier officiel NHL ----------
def canada_nhl(evs):
    vus = set()
    for n in range(0, JOURS, 7):
        d = (dt.date.today() + dt.timedelta(days=n)).isoformat()
        s = get("https://api-web.nhle.com/v1/schedule/" + d) or {}
        for jour in s.get("gameWeek", []):
            for g in jour.get("games", []):
                if g["id"] in vus:
                    continue
                vus.add(g["id"])
                t = utc(g["startTimeUTC"])
                hn = ((g.get("homeTeam") or {}).get("commonName") or {}).get("default", "")
                for ev in evs:
                    if ev["l"] == "nhl" and abs((utc(ev["t"]) - t).total_seconds()) < 1800 and hn and hn.lower() in (ev.get("_nh", "") + " " + ev.get("dom", "")).lower():
                        for b in g.get("tvBroadcasts", []):
                            if b.get("countryCode") == "CA":
                                ajouter(ev, "ca", b["network"], "" if b.get("market") == "N" else ("local dom." if b.get("market") == "H" else "local ext."))


# ---------- 4. Royaume-Uni : football à la télé ----------
def uk_foot(evs):
    req = urllib.request.Request("https://www.live-footballontv.com/", headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            s = r.read().decode("utf-8", "ignore")
    except Exception:
        print("Programme foot UK indisponible")
        return
    jour = None
    for m in re.finditer(r'<div class="fixture-date">([^<]+)</div>|<div class="fixture">(.*?)</div></div></div>', s, re.S):
        if m.group(1):
            txt = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", m.group(1).strip())
            try:
                jour = dt.datetime.strptime(txt, "%A %d %B %Y").date()
            except ValueError:
                jour = None
            continue
        if not jour:
            continue
        f = m.group(2)
        hm = re.search(r'fixture__time">(\d\d):(\d\d)<', f)
        eq = re.search(r'fixture__teams">([^<]+)<', f)
        if not hm or not eq or " v " not in eq.group(1):
            continue
        t = dt.datetime(jour.year, jour.month, jour.day, int(hm.group(1)), int(hm.group(2)), tzinfo=TZ_UK)
        a, b = [p.strip() for p in html.unescape(eq.group(1)).split(" v ", 1)]
        chaines = [html.unescape(c).strip() for c in re.findall(r'class="channel-pill"[^>]*>([^<]+)<', f)]
        for ev in evs:
            if ev["f"] == "foot" and abs((utc(ev["t"]) - t).total_seconds()) <= 20 * 60 and correspond(a, b, ev):
                for c in chaines:
                    ajouter(ev, "uk", c)


def main():
    evs = matchs()
    print(len(evs), "matchs ESPN")
    autres = france(evs)
    canada_nhl(evs)
    uk_foot(evs)
    for ev in evs:
        for k in [k for k in ev if k.startswith("_")]:
            del ev[k]
    evs.sort(key=lambda e: e["t"])
    data = {"maj": dt.datetime.now(TZ_FR).strftime("%Y-%m-%dT%H:%M"), "matchs": evs, "autres": autres}
    os.makedirs(os.path.dirname(SORTIE), exist_ok=True)
    with open(SORTIE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    n = {p: sum(1 for e in evs if e["ch"].get(p)) for p in ("fr", "us", "ca", "uk")}
    print("OK", SORTIE, len(evs), "matchs, avec chaîne :", n, "·", len(autres), "autres directs en France")


if __name__ == "__main__":
    main()

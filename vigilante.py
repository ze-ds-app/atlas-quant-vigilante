import json
import os
import re
import calendar
import feedparser
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
FICHEIRO_VISTAS = "noticias_vistas.txt"
FICHEIRO_ALERTAS = "alertas_importantes.json"
TZ_LISBOA = ZoneInfo("Europe/Lisbon")

FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY,QQQ,AAPL,MSFT,NVDA,TSLA,AMZN,META,GOOGL,BRK-B",
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664",
    "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",
    "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "https://www.investing.com/rss/news_25.rss",
    "https://seekingalpha.com/market_currents.xml"
]

BLACKLIST = [
    "actor", "actress", "celebrity", "hollywood", "movie", "film", "singer", "rapper",
    "nfl", "nba", "fifa", "soccer", "football", "retirement savings", "retirement plan",
    "retire early", "retire with", "401(k)", "ira ", "social security", "savings",
    "pension", "medicare", "mortgage", "partner", "marriage", "divorce", "dating",
    "credit card", "student loan", "personal finance", "opinion:", "advice", "husband",
    "wife", "mansion", "relists", "sold his", "sold her", "real estate", "podcast",
    "horoscope", "lottery", "powerball", "how to handle", "i'm ", "why i "
]

GATILHOS_MACRO = [
    "federal reserve", "jerome powell", "fomc", "interest rate", "rate cut", "rate hike",
    "cpi ", "inflation", "pce ", "nonfarm payrolls", "unemployment rate", "gdp ",
    "recession", "tariff", "tariffs", "trade war", "treasury yield", "central bank",
    "ecb ", "opec", "oil surge", "oil plunge", "debt ceiling", "government shutdown"
]

CATALISADORES_CORP = [
    "earnings", "revenue", "eps ", "guidance", "profit warning", "beats estimates", "misses estimates",
    "acquisition", "acquires", "merger", "buyout", "takeover", "antitrust", "doj ", "sec ", "ftc ",
    "fda approves", "fda rejects", "clinical trial", "bankruptcy", "chapter 11", "layoffs",
    "ceo resigns", "ceo steps down", "ceo retires", "buyback", "dividend cut", "recall",
    "sanctions", "export ban", "ipo ", "stock split", "short seller"
]

CONTEXTO_BOLSA = [
    "stock", "shares", "wall street", "nasdaq", "s&p 500", "nyse", "dow ", "q1", "q2", "q3", "q4",
    "quarter", "fiscal", "investors", "analysts", "billion", "nvidia", "apple", "microsoft",
    "tesla", "amazon", "meta", "google", "alphabet", "berkshire", "amd", "intel", "alibaba",
    "jpmorgan", "goldman", "boeing", "pfizer", "eli lilly", "netflix", "disney", "palantir",
    "rocket lab", "coinbase", "microstrategy", "tsmc", "asml", "broadcom", "qualcomm"
]

def extrair_hora_lisboa(entry):
    t_struct = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not t_struct:
        return datetime.now(TZ_LISBOA).strftime("%d/%m %H:%M")
    dt_utc = datetime.fromtimestamp(calendar.timegm(t_struct), tz=timezone.utc)
    return dt_utc.astimezone(TZ_LISBOA).strftime("%d/%m %H:%M")

def carregar_vistas():
    if not os.path.exists(FICHEIRO_VISTAS): return set()
    with open(FICHEIRO_VISTAS, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def guardar_vistas(vistas):
    lista = list(vistas)[-1500:]
    with open(FICHEIRO_VISTAS, "w", encoding="utf-8") as f:
        f.write("\n".join(lista) + "\n")

def guardar_alerta_para_app(titulo, resumo, fonte, categoria, hora_pub):
    alertas = []
    if os.path.exists(FICHEIRO_ALERTAS):
        try:
            with open(FICHEIRO_ALERTAS, "r", encoding="utf-8") as f:
                alertas = json.load(f)
        except: alertas = []
    alertas.insert(0, {
        "titulo": f"[{categoria}] {titulo}",
        "titulo_original": titulo,
        "resumo": resumo,
        "fonte": f"ALERTA TELEGRAM • {fonte}",
        "hora": hora_pub
    })
    with open(FICHEIRO_ALERTAS, "w", encoding="utf-8") as f:
        json.dump(alertas[:30], f, ensure_ascii=False, indent=2)

def classificar_noticia(titulo, resumo):
    texto = f" {titulo} {resumo} ".lower()
    if any(b in texto for b in BLACKLIST): return None, None
    for m in GATILHOS_MACRO:
        if m in texto: return "MACRO", m.strip().upper()
    for c in CATALISADORES_CORP:
        if c in texto and any(ctx in texto for ctx in CONTEXTO_BOLSA):
            return "CORPORATE", c.strip().upper()
    return None, None

def enviar_telegram_agrupado(lista_alertas):
    if not lista_alertas:
        return
    cabecalho = f"🚨 <b>ATLAS QUANT • {len(lista_alertas)} NOVO(S) ALERTA(S)</b>\n\n"
    corpo = ""
    for a in lista_alertas[:5]:
        corpo += f"• <b>[{a['cat']}] ({a['gatilho']})</b> — <code>{a['hora']}</code>\n{a['tit']}\n<i>{a['fonte']}</i>\n\n"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": cabecalho + corpo, "parse_mode": "HTML"}, timeout=10)

vistas = carregar_vistas()
primeira_vez = len(vistas) == 0
alertas_do_ciclo = []

for url in FEEDS:
    try:
        f = feedparser.parse(url)
        fonte = f.feed.get('title', 'Mercado')
        for e in f.entries[:10]:
            tit = e.title.strip()
            res = re.sub(r'<[^>]+>', '', getattr(e, "summary", tit))
            if tit not in vistas:
                vistas.add(tit)
                if not primeira_vez:
                    cat, gatilho = classificar_noticia(tit, res)
                    if cat:
                        hora_pub = extrair_hora_lisboa(e)
                        guardar_alerta_para_app(tit, res, fonte, cat, hora_pub)
                        alertas_do_ciclo.append({"cat": cat, "gatilho": gatilho, "tit": tit, "fonte": fonte, "hora": hora_pub})
    except Exception as ex:
        print(f"Erro feed: {ex}")

if alertas_do_ciclo:
    enviar_telegram_agrupado(alertas_do_ciclo)
    print(f"Enviado resumo com {len(alertas_do_ciclo)} alertas.")

guardar_vistas(vistas)
print(f"Ciclo concluído. Total vistas: {len(vistas)}")

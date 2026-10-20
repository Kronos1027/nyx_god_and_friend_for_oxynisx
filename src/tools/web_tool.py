"""Nyx — tools/web_tool.py (Módulo de Pesquisa e Navegação Web estilo Kimi K3 / Manus)

Permite ao agente:
- Pesquisar na Web em tempo real (DuckDuckGo / Wikipedia) sem chaves de API pagas.
- Extrair e ler conteúdo de páginas web (Web Scraping leve e seguro).
- Baixar dados ou referências para análise no Workspace.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from tools.registry import ToolResult

log = logging.getLogger(__name__)


class _HTMLTextExtractor(HTMLParser):
    """Extrai texto legível de páginas HTML removendo tags de estilo e scripts."""

    def __init__(self) -> None:
        super().__init__()
        self.result: list[str] = []
        self._ignore = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "head", "meta", "noscript"):
            self._ignore = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "head", "meta", "noscript"):
            self._ignore = False

    def handle_data(self, data: str) -> None:
        if not self._ignore:
            cleaned = data.strip()
            if cleaned:
                self.result.append(cleaned)

    def get_text(self) -> str:
        return " ".join(self.result)


class WebTool:
    """Ferramenta de pesquisa e navegação autônoma na Web."""

    def __init__(self, timeout: int = 12) -> None:
        self.timeout = timeout
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NyxAgent/1.0"

    def search(self, params: dict) -> ToolResult:
        """Realiza busca na web (DuckDuckGo Lite / HTML) com sanitização de query."""
        raw_query = str(params.get("query", params.get("q", ""))).strip()
        if not raw_query:
            return ToolResult(ok=False, error="Parâmetro 'query' é obrigatório para pesquisa.")

        # Sanitização: remove placeholders tipo [localização], [cidade], aspas desbalanceadas
        query = re.sub(r"\[.*?\]", "", raw_query).strip()
        query = re.sub(r'["\']', " ", query).strip()
        query = re.sub(r"\s+", " ", query)
        if not query:
            query = raw_query

        # Detecção inteligente de intenção meteorológica
        weather_keywords = ("chover", "chuva", "tempo hoje", "previsão do tempo", "clima hoje", "temperatura")
        if any(kw in query.lower() for kw in weather_keywords):
            # Tenta diretamente a ferramenta de clima especializada
            w_res = self.get_weather({"location": query})
            if w_res.ok:
                return w_res

        try:
            # 1. Tenta pesquisa DuckDuckGo HTML
            encoded = urllib.parse.urlencode({"q": query})
            url = f"https://html.duckduckgo.com/html/?{encoded}"
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                html_content = response.read().decode("utf-8", errors="replace")

            # Extração de resultados usando regex simples nos blocos .result__body
            results = []
            pattern = re.compile(
                r'<a class="result__snippet[^>]*href="(?P<link>[^"]+)"[^>]*>(?P<text>.*?)</a>',
                re.DOTALL,
            )
            matches = list(pattern.finditer(html_content))

            if not matches:
                # Fallback: extrai títulos e links genéricos
                pattern_gen = re.compile(
                    r'<a class="result__url"[^>]*href="(?P<link>[^"]+)"[^>]*>(?P<title>[^<]+)</a>',
                    re.DOTALL,
                )
                matches = list(pattern_gen.finditer(html_content))

            for m in matches[:6]:
                link = m.group("link")
                if "uddg=" in link:
                    # Desempacota redirect do DuckDuckGo
                    try:
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
                        link = parsed.get("uddg", [link])[0]
                    except Exception:
                        pass
                text = re.sub(r"<[^>]+>", "", m.group(0)).strip()
                text = re.sub(r"\s+", " ", text)
                if text:
                    results.append(f"- [{text[:120]}]({link})")

            if not results:
                # Fallback Wikipedia API
                wiki_url = f"https://pt.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(query)}&limit=5&namespace=0&format=json"
                req_wiki = urllib.request.Request(wiki_url, headers={"User-Agent": self.user_agent})
                with urllib.request.urlopen(req_wiki, timeout=self.timeout) as resp:
                    wiki_data = json.loads(resp.read().decode("utf-8"))
                    if len(wiki_data) >= 4 and wiki_data[1]:
                        for title, desc, link in zip(wiki_data[1], wiki_data[2], wiki_data[3], strict=False):
                            results.append(f"- **{title}**: {desc[:160]}... ({link})")

            if not results:
                return ToolResult(
                    ok=True,
                    output=f"Nenhum resultado direto encontrado para '{query}'. Tente reformular os termos.",
                    meta={"query": query, "count": 0},
                )

            output = f"Resultados da pesquisa para '{query}':\n\n" + "\n".join(results)
            return ToolResult(ok=True, output=output, meta={"query": query, "count": len(results)})

        except Exception as exc:
            log.warning(f"Erro na pesquisa web: {exc}")
            return ToolResult(ok=False, error=f"Falha na busca web: {exc}")

    def get_location(self, params: dict | None = None) -> ToolResult:
        """Descobre a localização geográfica aproximada atual (Cidade, Estado, País) via IP público."""
        endpoints = [
            "https://ipapi.co/json/",
            "http://ip-api.com/json/",
        ]
        for ep in endpoints:
            try:
                req = urllib.request.Request(ep, headers={"User-Agent": self.user_agent})
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    city = data.get("city") or data.get("city_name")
                    region = data.get("region") or data.get("region_name")
                    country = data.get("country_name") or data.get("country")
                    lat = data.get("latitude") or data.get("lat")
                    lon = data.get("longitude") or data.get("lon")
                    if city:
                        return ToolResult(
                            ok=True,
                            output=f"Localização atual: {city}, {region} - {country} (Lat: {lat}, Lon: {lon})",
                            meta={"city": city, "region": region, "country": country, "lat": lat, "lon": lon},
                        )
            except Exception:
                continue

        return ToolResult(
            ok=True,
            output="Localização estimada: São Paulo, SP - Brasil (fuso horário local)",
            meta={"city": "São Paulo", "country": "Brasil"},
        )

    def get_weather(self, params: dict | None = None) -> ToolResult:
        """Obtém previsão do tempo atualizada usando wttr.in sem necessidade de chave de API."""
        params = params or {}
        raw_loc = str(params.get("location", params.get("city", params.get("query", "")))).strip()
        # Remove palavras de comando comuns para isolar o nome da cidade se houver
        cleaned_loc = re.sub(r"(?i)(previs[ãa]o|do|tempo|clima|hoje|vai|chover|em|para|onde|estamos)", "", raw_loc).strip()
        loc_str = urllib.parse.quote(cleaned_loc) if cleaned_loc else ""
        url = f"https://wttr.in/{loc_str}?format=j1" if loc_str else "https://wttr.in/?format=j1"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                current = data.get("current_condition", [{}])[0]
                area = data.get("nearest_area", [{}])[0]
                city_name = area.get("areaName", [{}])[0].get("value", cleaned_loc or "Local")
                region_name = area.get("region", [{}])[0].get("value", "")
                country_name = area.get("country", [{}])[0].get("value", "")
                temp_c = current.get("temp_C", "?")
                feels_like = current.get("FeelsLikeC", "?")
                desc = current.get("weatherDesc", [{}])[0].get("value", "Tempo estável")
                humidity = current.get("humidity", "?")
                wind = current.get("windspeedKmph", "?")

                today = data.get("weather", [{}])[0]
                max_c = today.get("maxtempC", "?")
                min_c = today.get("mintempC", "?")
                chance_rain = "0"
                hourly = today.get("hourly", [])
                if hourly:
                    chance_rain = hourly[len(hourly) // 2].get("chanceofrain", "0")

                summary = (
                    f"Previsão do Tempo para {city_name}, {region_name} - {country_name}:\n"
                    f"- Condição Atual: {desc}, {temp_c}°C (Sensação: {feels_like}°C)\n"
                    f"- Mínima: {min_c}°C | Máxima: {max_c}°C\n"
                    f"- Probabilidade de Chuva: {chance_rain}%\n"
                    f"- Umidade: {humidity}% | Vento: {wind} km/h"
                )
                return ToolResult(
                    ok=True,
                    output=summary,
                    meta={"city": city_name, "temp": temp_c, "desc": desc, "chance_rain": chance_rain},
                )
        except Exception as exc:
            # Fallback rápido para formato simplificado
            try:
                txt_url = f"https://wttr.in/{loc_str}?format=3" if loc_str else "https://wttr.in/?format=3"
                req_txt = urllib.request.Request(txt_url, headers={"User-Agent": "curl/7.68.0"})
                with urllib.request.urlopen(req_txt, timeout=4.0) as resp_txt:
                    txt = resp_txt.read().decode("utf-8").strip()
                    if txt:
                        return ToolResult(ok=True, output=f"Previsão do Tempo: {txt}", meta={"raw": txt})
            except Exception:
                pass
            return ToolResult(ok=False, error=f"Não foi possível obter dados meteorológicos: {exc}")

    def fetch_page(self, params: dict) -> ToolResult:
        """Baixa e extrai o texto legível de uma página Web."""
        url = params.get("url", "").strip()
        if not url:
            return ToolResult(ok=False, error="Parâmetro 'url' é obrigatório.")

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                raw_html = response.read().decode(charset, errors="replace")

            extractor = _HTMLTextExtractor()
            extractor.feed(raw_html)
            clean_text = extractor.get_text()

            clean_text = re.sub(r"\s+", " ", clean_text).strip()
            preview = clean_text[:2500]
            if len(clean_text) > 2500:
                preview += f"\n\n[...conteúdo truncado. Total de {len(clean_text)} caracteres...]"

            return ToolResult(
                ok=True,
                output=preview,
                meta={"url": url, "total_chars": len(clean_text)},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao carregar página {url}: {exc}")

    def run(self, params: dict) -> ToolResult:
        action = params.get("action", params.get("op", "search")).lower()
        if action in ("search", "find", "google", "query"):
            return self.search(params)
        elif action in ("fetch", "get", "read", "url", "scrape"):
            return self.fetch_page(params)
        elif action in ("weather", "clima", "tempo", "previsao"):
            return self.get_weather(params)
        elif action in ("location", "localizacao", "onde_estamos", "onde"):
            return self.get_location(params)
        return ToolResult(
            ok=False,
            error=f"Ação web desconhecida: '{action}'. Válidas: search, fetch, weather, location.",
        )


def make_web_tool_func(tool: WebTool):
    def _run(params: dict) -> ToolResult:
        return tool.run(params)

    return _run

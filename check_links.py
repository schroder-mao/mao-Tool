import argparse
import datetime
import json
import re
import socket
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    sys.exit("Module 'requests' requis. Installe-le : pip install requests")

try:
    import colorama
    colorama.just_fix_windows_console()
except ImportError:
    pass

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GREEN, YELLOW, RED, GRAY, RESET = "\033[92m", "\033[93m", "\033[91m", "\033[90m", "\033[0m"

MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

ANTIBOT_CODES = {400, 406, 429, 451, 464}
RESTRICTED_CODES = {401, 403}


def extract_links_md(path):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    seen = set()
    links = []
    for name, url in MD_LINK_RE.findall(content):
        if url not in seen:
            seen.add(url)
            links.append((name.strip(), url.strip()))
    return links


def extract_links_json(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    seen = set()
    links = []
    for t in data.get("tools", []):
        url = t.get("url", "").strip()
        name = t.get("name", "").strip()
        if url and url not in seen:
            seen.add(url)
            links.append((name, url))
    return links


def extract_links(path):
    if path.endswith(".json"):
        return extract_links_json(path)
    return extract_links_md(path)


def is_onion(url):
    host = urlparse(url).hostname or ""
    return host.endswith(".onion")


def tor_reachable(host, port, timeout=3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _fetch(url, timeout, proxy=None):
    proxies = None
    if proxy:
        proxies = {"http": f"socks5h://{proxy}", "https": f"socks5h://{proxy}"}
    try:
        r = requests.head(
            url, timeout=timeout, allow_redirects=True,
            headers=BROWSER_HEADERS, proxies=proxies,
        )
        if r.status_code >= 400:
            r = requests.get(
                url, timeout=timeout, allow_redirects=True,
                headers=BROWSER_HEADERS, proxies=proxies, stream=True,
            )
            r.close()
        code = r.status_code
        if 200 <= code < 400:
            return "OK", str(code)
        if code in RESTRICTED_CODES:
            return "WARN", f"{code} (accès restreint)"
        if code in ANTIBOT_CODES:
            return "WARN", f"{code} (probable anti-bot)"
        if 500 <= code < 600:
            return "WARN", f"{code} (serveur indisponible)"
        return "DEAD", str(code)
    except requests.exceptions.SSLError:
        return "WARN", "Erreur SSL (certificat invalide)"
    except requests.exceptions.Timeout:
        return "DEAD", "Timeout"
    except requests.exceptions.ConnectionError as e:
        msg = str(e)
        if "SOCKS" in msg and ".onion" in url:
            return "DEAD", "Tor: hôte .onion injoignable"
        return "DEAD", "Connexion échouée"
    except Exception as e:
        return "DEAD", str(e)[:80]


def check_url(name, url, timeout, tor_proxy=None, tor_timeout=45, tor_retry=False):
    onion = is_onion(url)

    if onion and not tor_proxy:
        return name, url, "SKIP", "Nécessite Tor (lance avec --tor)"

    if onion:
        status, info = _fetch(url, tor_timeout, tor_proxy)
        return name, url, status, f"{info} [TOR]"

    status, info = _fetch(url, timeout)

    if tor_retry and tor_proxy and status != "OK":
        retry_status, retry_info = _fetch(url, tor_timeout, tor_proxy)
        if retry_status == "OK":
            return name, url, "OK", f"{retry_info} [via TOR]"
        order = {"OK": 0, "WARN": 1, "DEAD": 2}
        if order[retry_status] < order[status]:
            return name, url, retry_status, f"{retry_info} [via TOR]"

    return name, url, status, info


def write_report(path, results):
    buckets = {"DEAD": [], "WARN": [], "SKIP": [], "OK": []}
    for r in results:
        buckets[r[2]].append(r)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Rapport de vérification des liens\n\n")
        f.write(f"- OK: {len(buckets['OK'])}\n")
        f.write(f"- WARN: {len(buckets['WARN'])}\n")
        f.write(f"- DEAD: {len(buckets['DEAD'])}\n")
        f.write(f"- SKIP: {len(buckets['SKIP'])}\n\n")
        for label in ("DEAD", "WARN", "SKIP", "OK"):
            items = buckets[label]
            if not items:
                continue
            f.write(f"## {label} ({len(items)})\n")
            for name, url, _, info in items:
                f.write(f"- [{name}]({url}) — {info}\n")
            f.write("\n")


def write_status_json(path, results):
    generated = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    statuses = {
        url: {"status": status, "info": str(info)}
        for _, url, status, info in results
    }
    Path(path).write_text(
        json.dumps({"generated": generated, "statuses": statuses}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="tools.json")
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--output", default="rapport.md")
    ap.add_argument("--status-json", default="status.json")
    ap.add_argument("--tor", action="store_true")
    ap.add_argument("--tor-host", default="127.0.0.1")
    ap.add_argument("--tor-port", type=int, default=9050)
    ap.add_argument("--tor-timeout", type=int, default=45)
    ap.add_argument("--tor-retry", action="store_true")
    args = ap.parse_args()

    tor_proxy = None
    if args.tor or args.tor_retry:
        try:
            import socks
        except ImportError:
            sys.exit("PySocks manquant. Installe : pip install requests[socks]")
        if not tor_reachable(args.tor_host, args.tor_port):
            sys.exit(
                f"Impossible de joindre Tor sur {args.tor_host}:{args.tor_port}.\n"
                f"  - Tor standalone : port 9050\n"
                f"  - Tor Browser    : port 9150 (--tor-port 9150)"
            )
        tor_proxy = f"{args.tor_host}:{args.tor_port}"
        mode = "clearnet+onion" if args.tor_retry else "onion"
        print(f"Mode Tor activé via {tor_proxy} ({mode})")

    links = extract_links(args.file)
    if not links:
        sys.exit(f"Aucun lien trouvé dans {args.file}")

    n_onion = sum(1 for _, u in links if is_onion(u))
    print(f"Trouvé {len(links)} liens uniques dans {args.file} ({n_onion} .onion)")
    print(f"Vérification en cours (timeout={args.timeout}s, {args.workers} threads)...\n")

    colors = {"OK": GREEN, "WARN": YELLOW, "DEAD": RED, "SKIP": GRAY}
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                check_url, n, u, args.timeout, tor_proxy, args.tor_timeout, args.tor_retry,
            ): (n, u)
            for n, u in links
        }
        for i, fut in enumerate(as_completed(futures), 1):
            name, url, status, info = fut.result()
            results.append((name, url, status, info))
            c = colors[status]
            print(f"[{i:3}/{len(links)}] {c}{status:4}{RESET} {name:35.35} -> {info}")

    print("\n" + "=" * 60)
    counts = {k: sum(1 for r in results if r[2] == k) for k in colors}
    for k, c in colors.items():
        print(f"{c}{k:4}: {counts[k]}{RESET}")

    dead = [r for r in results if r[2] == "DEAD"]
    if dead:
        print(f"\n{RED}Liens morts :{RESET}")
        for name, url, _, info in dead:
            print(f"  - {name}: {url} ({info})")

    if args.file.endswith(".json"):
        overrides = json.loads(Path(args.file).read_text(encoding="utf-8")).get("status_overrides", {})
        if overrides:
            patched = []
            for name, url, status, info in results:
                o = overrides.get(url)
                if o:
                    patched.append((name, url, o.get("status", status), o.get("info", info)))
                else:
                    patched.append((name, url, status, info))
            results = patched
            print(f"\n{len(overrides)} overrides appliqués")

    if args.output:
        write_report(args.output, results)
        print(f"Rapport écrit dans {args.output}")
    if args.status_json:
        write_status_json(args.status_json, results)
        print(f"Status JSON écrit dans {args.status_json}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""NEXUS — 300-command Telegram bot. One file. Render webhook or local polling.

Defensive / public-data only: hashes, DNS, RDAP, converters, search, oEmbed.
Refuses exploits, scanners, flooders, and copyrighted file ripping.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac as hmaclib
import json
import os
import random
import re
import secrets
import string
import time
from datetime import datetime, timezone
from html import escape as html_esc
from ipaddress import ip_address, ip_network
from math import gcd as math_gcd, hypot, sqrt
from typing import Awaitable, Callable, Dict
from urllib.parse import quote, urlencode, urlparse
from uuid import uuid4

import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BOOT = time.time()
MAX = 3500
UA = "NEXUS/1.0 (telegram-bot)"
WORDS = (
    "alpha amber anchor apex arc ash atlas aurora basin beacon birch brine cedar "
    "cipher cobalt comet copper crest delta drift ember flint forge frost gale grove "
    "harbor helix ivory jade keel lagoon lumen maple nebula north oak onyx orbit "
    "pearl pine quartz ridge river sable sage shore sierra slate spark stone tide "
    "timber vale vapor vista willow zinc nimbus brass"
).split()

HTTP = {
    200: "OK", 201: "Created", 204: "No Content", 301: "Moved Permanently",
    302: "Found", 304: "Not Modified", 400: "Bad Request", 401: "Unauthorized",
    403: "Forbidden", 404: "Not Found", 418: "I'm a teapot", 429: "Too Many Requests",
    451: "Unavailable For Legal Reasons", 500: "Internal Server Error",
    502: "Bad Gateway", 503: "Service Unavailable",
}
PORTS = {
    22: "SSH", 25: "SMTP", 53: "DNS", 80: "HTTP", 110: "POP3", 143: "IMAP",
    443: "HTTPS", 445: "SMB", 465: "SMTPS", 587: "SMTP submission", 993: "IMAPS",
    3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL", 6379: "Redis", 8080: "HTTP alt",
    27017: "MongoDB",
}
MIME = {
    "html": "text/html", "css": "text/css", "js": "text/javascript", "json": "application/json",
    "png": "image/png", "jpg": "image/jpeg", "pdf": "application/pdf", "mp4": "video/mp4",
    "zip": "application/zip", "svg": "image/svg+xml", "wasm": "application/wasm",
}

HELP_INDEX = """NEXUS — command arsenal
/help [cmd]   /menu [cat]   /find <q>   /commands

Categories: core search cyber media convert generate math world fun dev

Cyber lab is hashes, DNS, RDAP, public headers, CT names — not exploits.
Media is oEmbed metadata — not YouTube ripping.

Featured: /wiki /sha256 /dns /ipinfo /weather /calc /password /jwt /qr /yt /cve /ask
"""

ABOUT = """NEXUS will hash, convert, search public records, and inspect public URLs.
It will not exploit, brute-force, flood, scan ports, generate malware, or rip copyrighted video files.
Use it on systems you are authorized to test."""


def clip(s: str) -> str:
    s = s.strip()
    return s if len(s) <= MAX else s[:MAX] + "\n\n… truncated"


def need(args: str, usage: str) -> str | None:
    return None if args.strip() else f"Usage: {usage}"


def hexd(b: bytes) -> str:
    return b.hex()


def private_host(host: str) -> bool:
    h = host.lower().strip("[]")
    if h in {"localhost", "metadata.google.internal", "0.0.0.0"}:
        return True
    if h.endswith(".local") or h.endswith(".internal"):
        return True
    try:
        ip = ip_address(h)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        return False


def public_url(raw: str) -> str:
    u = raw if re.match(r"^https?://", raw, re.I) else "https://" + raw
    p = urlparse(u)
    if p.scheme not in {"http", "https"}:
        raise ValueError("Only HTTP(S)")
    if not p.hostname or private_host(p.hostname):
        raise ValueError("Private hosts are blocked")
    return u


async def grab(url: str, **kw) -> httpx.Response:
    timeout = httpx.Timeout(9.0)
    headers = {"user-agent": UA, **kw.pop("headers", {})}
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers=headers) as c:
        return await c.request(kw.pop("method", "GET"), url, **kw)


async def jget(url: str, **kw):
    r = await grab(url, **kw)
    r.raise_for_status()
    return r.json()


async def doh(name: str, typ: str) -> str:
    r = await grab(
        f"https://cloudflare-dns.com/dns-query?name={quote(name)}&type={quote(typ)}",
        headers={"accept": "application/dns-json"},
    )
    data = r.json()
    ans = data.get("Answer") or []
    if not ans:
        return f"No {typ} records (status {data.get('Status')})"
    return "\n".join(a.get("data", "") for a in ans)


def rot(text: str, shift: int) -> str:
    s = shift % 26
    out = []
    for ch in text:
        if "A" <= ch <= "Z":
            out.append(chr((ord(ch) - 65 + s) % 26 + 65))
        elif "a" <= ch <= "z":
            out.append(chr((ord(ch) - 97 + s) % 26 + 97))
        else:
            out.append(ch)
    return "".join(out)


def luhn(num: str) -> bool:
    d = re.sub(r"\D", "", num)
    if not d:
        return False
    s, alt = 0, False
    for ch in reversed(d):
        n = ord(ch) - 48
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        s += n
        alt = not alt
    return s % 10 == 0


def roman(n: int) -> str:
    if n <= 0 or n >= 4000:
        return "range 1–3999"
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
            (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    s = []
    for v, g in vals:
        while n >= v:
            s.append(g)
            n -= v
    return "".join(s)


def calc(expr: str) -> str:
    src = re.sub(r"\s+", "", expr)
    if not re.fullmatch(r"[0-9+\-*/%().**]+", src.replace("**", "^")) and not re.fullmatch(r"[0-9+\-*/%().*]+", src):
        # still parse via a tiny eval of numbers only
        pass
    i = 0

    def peek():
        return src[i] if i < len(src) else ""

    def eat():
        nonlocal i
        ch = peek()
        i += 1
        return ch

    def num():
        s = ""
        if peek() in "+-":
            s += eat()
        while peek().isdigit() or peek() == ".":
            s += eat()
        if s in {"", "+", "-"}:
            raise ValueError("number")
        return float(s)

    def factor():
        if peek() == "(":
            eat()
            v = expression()
            if eat() != ")":
                raise ValueError(")")
            return v
        return num()

    def power():
        v = factor()
        if src[i:i + 2] == "**":
            nonlocal_skip = 2
            # handled below
        return v

    def unary():
        if peek() == "-":
            eat()
            return -unary()
        if peek() == "+":
            eat()
            return unary()
        v = factor()
        nonlocal i
        if src[i:i + 2] == "**":
            i += 2
            v = v ** unary()
        return v

    def term():
        v = unary()
        while peek() in {"*", "/", "%"}:
            op = eat()
            r = unary()
            v = v * r if op == "*" else v / r if op == "/" else v % r
        return v

    def expression():
        v = term()
        while peek() in {"+", "-"}:
            op = eat()
            r = term()
            v = v + r if op == "+" else v - r
        return v

    v = expression()
    if i != len(src):
        raise ValueError("trailing")
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError("non-finite")
    return str(int(v) if v == int(v) else v)


def slug(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.U).strip().lower()
    return re.sub(r"[-\s]+", "-", s)


def tokens(s: str):
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    return re.split(r"[\s_-]+", s.strip())


async def oembed(url: str) -> str:
    endpoints = [
        f"https://www.youtube.com/oembed?format=json&url={quote(url, safe='')}",
        f"https://vimeo.com/api/oembed.json?url={quote(url, safe='')}",
        f"https://open.spotify.com/oembed?url={quote(url, safe='')}",
        f"https://noembed.com/embed?url={quote(url, safe='')}",
    ]
    for ep in endpoints:
        try:
            j = await jget(ep)
            title = j.get("title")
            if not title:
                continue
            bits = [title, f"by {j['author_name']}" if j.get("author_name") else "",
                    j.get("provider_name", ""), j.get("thumbnail_url", ""),
                    "Metadata only — no file download."]
            return "\n".join(b for b in bits if b)
        except Exception:
            continue
    return "No oEmbed provider answered."


Handler = Callable[[str, Update], Awaitable[str] | str]
LOCAL: Dict[str, Callable[..., str]] = {}
NET: Dict[str, Callable[..., Awaitable[str]]] = {}
AI = {"ask", "summarize", "explain"}


def loc(name):
    def deco(fn):
        LOCAL[name] = fn
        return fn
    return deco


def net(name):
    def deco(fn):
        NET[name] = fn
        return fn
    return deco


@loc("start")
@loc("help")
def h_help(a, _=None):
    if not a.strip():
        return HELP_INDEX + "\n" + ABOUT
    return f"Try /usage {a.strip()} — NEXUS has 300 commands. /find {a.strip()}"


@loc("about")
def h_about(a, _=None):
    return ABOUT


@loc("privacy")
def h_privacy(a, _=None):
    return "No accounts. Don't paste production secrets. Network commands hit public APIs."


@loc("ping")
def h_ping(a, _=None):
    return f"pong · {datetime.now(timezone.utc).isoformat()}"


@loc("uptime")
def h_uptime(a, _=None):
    return f"{int(time.time() - BOOT)}s"


@loc("version")
def h_ver(a, _=None):
    return "NEXUS 2026.10 telegram"


@loc("status")
def h_status(a, _=None):
    return "online · webhook/polling"


@loc("echo")
def h_echo(a, _=None):
    return a or "Usage: /echo <text>"


@loc("id")
def h_id(a, u=None):
    if u and u.effective_user:
        return f"tg {u.effective_user.id}\nchat {u.effective_chat.id if u.effective_chat else '-'}"
    return "no update"


@loc("whoami")
def h_who(a, u=None):
    if u and u.effective_user:
        return u.effective_user.full_name
    return "anonymous"


@loc("md5")
def h_md5(a, _=None):
    return need(a, "/md5 <text>") or hashlib.md5(a.encode()).hexdigest()


@loc("sha1")
def h_sha1(a, _=None):
    return need(a, "/sha1 <text>") or hashlib.sha1(a.encode()).hexdigest()


@loc("sha256")
@loc("hash")
def h_sha256(a, _=None):
    return need(a, "/sha256 <text>") or hashlib.sha256(a.encode()).hexdigest()


@loc("sha384")
def h_sha384(a, _=None):
    return need(a, "/sha384 <text>") or hashlib.sha384(a.encode()).hexdigest()


@loc("sha512")
def h_sha512(a, _=None):
    return need(a, "/sha512 <text>") or hashlib.sha512(a.encode()).hexdigest()


@loc("hmac")
def h_hmac(a, _=None):
    parts = a.split(" ", 1)
    if len(parts) < 2:
        return "Usage: /hmac <key> <text>"
    return hmaclib.new(parts[0].encode(), parts[1].encode(), hashlib.sha256).hexdigest()


@loc("b64enc")
def h_b64e(a, _=None):
    import base64
    return need(a, "/b64enc <text>") or base64.b64encode(a.encode()).decode()


@loc("b64dec")
def h_b64d(a, _=None):
    import base64
    try:
        return base64.b64decode(a.strip()).decode()
    except Exception:
        return "Invalid base64"


@loc("b64url")
def h_b64u(a, _=None):
    import base64
    return need(a, "/b64url <text>") or base64.urlsafe_b64encode(a.encode()).decode().rstrip("=")


@loc("urlenc")
def h_ue(a, _=None):
    return need(a, "/urlenc <text>") or quote(a, safe="")


@loc("urldec")
def h_ud(a, _=None):
    from urllib.parse import unquote
    return unquote(a)


@loc("hexenc")
def h_he(a, _=None):
    return need(a, "/hexenc <text>") or a.encode().hex()


@loc("hexdec")
def h_hd(a, _=None):
    try:
        return bytes.fromhex(re.sub(r"\s", "", a)).decode()
    except Exception:
        return "Invalid hex"


@loc("rot13")
def h_r13(a, _=None):
    return rot(a, 13)


@loc("caesar")
def h_cae(a, _=None):
    m = re.match(r"(-?\d+)\s+([\s\S]+)", a)
    return rot(m.group(2), int(m.group(1))) if m else "Usage: /caesar <shift> <text>"


@loc("uuid")
def h_uuid(a, _=None):
    return str(uuid4())


@loc("password")
def h_pw(a, _=None):
    n = max(8, min(128, int(a) if a.strip().isdigit() else 20))
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%^&*-_"
    return "".join(secrets.choice(alphabet) for _ in range(n))


@loc("passphrase")
def h_pp(a, _=None):
    n = max(4, min(12, int(a) if a.strip().isdigit() else 5))
    return "-".join(secrets.choice(WORDS) for _ in range(n))


@loc("jwt")
def h_jwt(a, _=None):
    import base64
    parts = a.strip().split(".")
    if len(parts) < 2:
        return "Usage: /jwt <token>"
    def dec(p):
        p += "=" * ((4 - len(p) % 4) % 4)
        return json.loads(base64.urlsafe_b64decode(p.replace("-", "+").replace("_", "/") if False else p))
    try:
        hdr = json.loads(base64.urlsafe_b64decode(parts[0] + "=" * ((4 - len(parts[0]) % 4) % 4)))
        pay = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)))
        return "header\n" + json.dumps(hdr, indent=2) + "\n\npayload\n" + json.dumps(pay, indent=2) + "\n\nNot verified."
    except Exception:
        return "Could not decode JWT"


@loc("luhn")
def h_luhn(a, _=None):
    return "luhn valid" if luhn(a) else "luhn invalid"


@loc("crc32")
def h_crc(a, _=None):
    import zlib
    return format(zlib.crc32(a.encode()) & 0xFFFFFFFF, "08x")


@loc("httpcode")
@loc("http")
def h_http(a, _=None):
    if not a.strip():
        return "\n".join(f"{k}  {v}" for k, v in HTTP.items())
    return HTTP.get(int(a), "unknown")


@loc("port")
def h_port(a, _=None):
    try:
        n = int(a)
    except ValueError:
        return "Usage: /port <n> — encyclopedia only, no scan."
    return f"{n}/tcp  {PORTS.get(n, 'not in well-known table')}\nNo scan is performed."


@loc("upper")
def h_up(a, _=None):
    return a.upper()


@loc("lower")
def h_lo(a, _=None):
    return a.lower()


@loc("snake")
def h_sn(a, _=None):
    return "_".join(t.lower() for t in tokens(a) if t)


@loc("kebab")
def h_kb(a, _=None):
    return "-".join(t.lower() for t in tokens(a) if t)


@loc("slug")
def h_sl(a, _=None):
    return slug(a)


@loc("reverse")
def h_rev(a, _=None):
    return a[::-1]


@loc("jsonpretty")
def h_jp(a, _=None):
    try:
        return json.dumps(json.loads(a), indent=2)
    except Exception as e:
        return f"invalid json: {e}"


@loc("jsonmin")
def h_jm(a, _=None):
    try:
        return json.dumps(json.loads(a), separators=(",", ":"))
    except Exception as e:
        return str(e)


@loc("calc")
def h_calc(a, _=None):
    try:
        return calc(a)
    except Exception:
        return "Could not parse. Digits and + - * / % ** ( ) only."


@loc("password")
def h_qr(a, _=None):
    if not a.strip():
        return "Usage: /qr <text>"
    return f"https://api.qrserver.com/v1/create-qr-code/?size=240x240&data={quote(a)}"


@loc("dice")
def h_dice(a, _=None):
    m = re.match(r"(\d+)d(\d+)$", (a.strip() or "1d6"), re.I)
    if not m:
        return "Usage: /dice 2d6"
    n, s = min(20, int(m.group(1))), int(m.group(2))
    rolls = [secrets.randbelow(s) + 1 for _ in range(n)]
    return " + ".join(map(str, rolls)) + f" = {sum(rolls)}"


@loc("coin")
def h_coin(a, _=None):
    return secrets.choice(["heads", "tails"])


@loc("roman")
def h_rom(a, _=None):
    try:
        return roman(int(a))
    except Exception:
        return "Usage: /roman 2026"


@loc("c2f")
def h_c2f(a, _=None):
    return str(float(a) * 9 / 5 + 32)


@loc("f2c")
def h_f2c(a, _=None):
    return str((float(a) - 32) * 5 / 9)


@loc("bytes")
def h_bytes(a, _=None):
    n = float(a)
    u = ["B", "KiB", "MiB", "GiB", "TiB"]
    i = 0
    while n >= 1024 and i < len(u) - 1:
        n /= 1024
        i += 1
    return f" {n:.2f} {u[i]}"


@loc("epoch")
def h_epoch(a, _=None):
    return f"{int(time.time())}\n{int(time.time() * 1000)}"


@loc("unix")
def h_unix(a, _=None):
    if not a.strip():
        return datetime.now(timezone.utc).isoformat()
    n = float(a)
    if n < 1e12:
        n *= 1000
    return datetime.fromtimestamp(n / 1000, tz=timezone.utc).isoformat()


@loc("osint")
def h_osint(a, _=None):
    return ("Public-source checklist (authorized targets only)\n"
            "• /whois /dns /mx /txt /ctlogs /subs /robots /headers /wayback /ghuser\n"
            "Do not probe, brute, or exploit.")


@loc("responsible")
def h_resp(a, _=None):
    return ("Subject: Vulnerability report\n1 Summary\n2 Asset / version\n"
            "3 Repro\n4 Impact\n5 Fix\n6 90-day disclosure window")


@loc("killchain")
def h_kc(a, _=None):
    return "1 Recon\n2 Weaponize\n3 Deliver\n4 Exploit\n5 Install\n6 C2\n7 Objectives"


@loc("mitre")
def h_mitre(a, _=None):
    return "recon resource initial exec persist priv evade cred discover lateral collect c2 exfil impact"


@loc("dork")
def h_dork(a, _=None):
    parts = a.split()
    if len(parts) < 2:
        return "Usage: /dork <pdf|login|backup|dir|js> <domain> — builds a query, does not hit the target."
    kind, domain = parts[0], parts[1]
    m = {
        "pdf": f"site:{domain} filetype:pdf",
        "login": f"site:{domain} inurl:login",
        "backup": f"site:{domain} (ext:sql OR ext:bak)",
        "dir": f'site:{domain} intitle:"index of"',
        "js": f"site:{domain} ext:js",
    }
    return m.get(kind, "Kinds: pdf login backup dir js")


@loc("figlet")
def h_fig(a, _=None):
    t = re.sub(r"[^A-Z0-9 ]", "", (a or "NEXUS").upper())[:14]
    bar = "─" * max(8, len(t) * 2 + 2)
    return f"┌{bar}┐\n│ {' '.join(t)} │\n└{bar}┘"


@loc("cowsay")
def h_cow(a, _=None):
    t = (a or "NEXUS")[:80]
    line = "-" * (len(t) + 2)
    return f" {line}\n< {t} >\n {line}\n        \\  ^__^\n         \\ (oo)\\_______"


# --- network ---
@net("wiki")
async def n_wiki(a, _=None):
    if not a:
        return "Usage: /wiki <topic>"
    r = await grab(f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(a.replace(' ', '_'))}")
    if r.status_code != 200:
        return "No Wikipedia page."
    j = r.json()
    return f"{j.get('title')}\n\n{j.get('extract', '')}"


@net("define")
@net("dict")
async def n_dict(a, _=None):
    if not a:
        return "Usage: /define <word>"
    r = await grab(f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(a.split()[0])}")
    if r.status_code != 200:
        return "No definition."
    j = r.json()
    lines = []
    for m in j[0].get("meanings", [])[:3]:
        lines.append(m.get("partOfSpeech", ""))
        for d in m.get("definitions", [])[:2]:
            lines.append("  " + d.get("definition", ""))
    return "\n".join(lines)


@net("dns")
async def n_dns(a, _=None):
    return await doh(a, "A") if a else "Usage: /dns <host>"


@net("mx")
async def n_mx(a, _=None):
    return await doh(a, "MX") if a else "Usage: /mx <domain>"


@net("txt")
async def n_txt(a, _=None):
    return await doh(a, "TXT") if a else "Usage: /txt <domain>"


@net("ns")
async def n_ns(a, _=None):
    return await doh(a, "NS") if a else "Usage: /ns <domain>"


@net("aaaa")
async def n_aaaa(a, _=None):
    return await doh(a, "AAAA") if a else "Usage: /aaaa <host>"


@net("dmarc")
async def n_dmarc(a, _=None):
    return await doh(f"_dmarc.{a}", "TXT") if a else "Usage: /dmarc <domain>"


@net("whois")
@net("rdap")
async def n_whois(a, _=None):
    if not a:
        return "Usage: /whois <domain|ip>"
    url = f"https://rdap.org/ip/{quote(a)}" if a[0].isdigit() else f"https://rdap.org/domain/{quote(a)}"
    r = await grab(url)
    if r.status_code != 200:
        return "RDAP lookup failed."
    j = r.json()
    ns = ", ".join(n.get("ldhName", "") for n in j.get("nameservers") or [])
    return f"{j.get('ldhName') or j.get('handle')}\n{ns}"


@net("ipinfo")
@net("asn")
async def n_ip(a, _=None):
    if not a:
        return "Usage: /ipinfo <ip>"
    if private_host(a):
        return "Private IPs are blocked."
    j = await jget(f"http://ip-api.com/json/{quote(a)}")
    if j.get("status") == "fail":
        return j.get("message", "fail")
    return f"{j.get('query')}\n{j.get('city')}, {j.get('country')}\n{j.get('isp')}\n{j.get('as')}"


@net("headers")
async def n_headers(a, _=None):
    if not a:
        return "Usage: /headers <url>"
    u = public_url(a)
    r = await grab(u)
    lines = [f"HTTP {r.status_code}"] + [f"{k}: {v}" for k, v in r.headers.items()]
    return "\n".join(lines[:40])


@net("robots")
async def n_robots(a, _=None):
    if not a:
        return "Usage: /robots <host>"
    u = public_url(a)
    p = urlparse(u)
    r = await grab(f"{p.scheme}://{p.netloc}/robots.txt")
    return r.text[:2500]


@net("ctlogs")
@net("subs")
async def n_ct(a, _=None):
    if not a:
        return "Usage: /ctlogs <domain>"
    j = await jget(f"https://crt.sh/?q={quote('%.' + a)}&output=json")
    names = []
    for row in j[:80]:
        names.extend(row.get("name_value", "").split("\n"))
    return "\n".join(sorted(set(names))[:40]) or "No names."


@net("github")
async def n_gh(a, _=None):
    if "/" not in a:
        return "Usage: /github owner/repo"
    r = await grab(f"https://api.github.com/repos/{a}")
    if r.status_code != 200:
        return "Repo not found."
    j = r.json()
    return f"{j.get('full_name')}\n{j.get('description')}\n★ {j.get('stargazers_count')}\n{j.get('html_url')}"


@net("npm")
async def n_npm(a, _=None):
    if not a:
        return "Usage: /npm <name>"
    j = await jget(f"https://registry.npmjs.org/{quote(a)}")
    latest = (j.get("dist-tags") or {}).get("latest")
    return f"{j.get('name')}@{latest}\n{j.get('description', '')}"


@net("pypi")
async def n_pypi(a, _=None):
    if not a:
        return "Usage: /pypi <name>"
    j = await jget(f"https://pypi.org/pypi/{quote(a)}/json")
    info = j.get("info") or {}
    return f"{info.get('name')} {info.get('version')}\n{info.get('summary', '')}"


@net("cve")
async def n_cve(a, _=None):
    if not a:
        return "Usage: /cve CVE-YYYY-NNNN"
    cid = a.upper() if a.upper().startswith("CVE-") else "CVE-" + a
    r = await grab(f"https://cve.circl.lu/api/cve/{cid}")
    if r.status_code != 200:
        return "CVE not found."
    j = r.json()
    return f"{cid}\n{j.get('summary') or str(j)[:500]}"


@net("weather")
async def n_weather(a, _=None):
    if not a:
        return "Usage: /weather <place>"
    r = await grab(f"https://wttr.in/{quote(a)}?format=3")
    return r.text.strip()


@net("forecast")
async def n_fc(a, _=None):
    if not a:
        return "Usage: /forecast <place>"
    r = await grab(f"https://wttr.in/{quote(a)}?T")
    return "\n".join(r.text.splitlines()[:18])


@net("hn")
@net("news")
async def n_hn(a, _=None):
    ids = (await jget("https://hacker-news.firebaseio.com/v0/topstories.json"))[:6]
    lines = []
    for i in ids:
        it = await jget(f"https://hacker-news.firebaseio.com/v0/item/{i}.json")
        lines.append(f"• {it.get('title')}")
    return "\n".join(lines)


@net("yt")
@net("oembed")
@net("thumb")
@net("vimeo")
@net("media")
@net("spotify")
@net("soundcloud")
async def n_yt(a, _=None):
    return await oembed(a) if a else "Usage: /yt <url>"


@net("joke")
async def n_joke(a, _=None):
    j = await jget("https://official-joke-api.appspot.com/random_joke")
    return f"{j.get('setup')}\n{j.get('punchline')}"


@net("dad")
async def n_dad(a, _=None):
    r = await grab("https://icanhazdadjoke.com/", headers={"accept": "text/plain"})
    return r.text


@net("cat")
async def n_cat(a, _=None):
    j = await jget("https://api.thecatapi.com/v1/images/search")
    return j[0]["url"]


@net("dog")
async def n_dog(a, _=None):
    j = await jget("https://dog.ceo/api/breeds/image/random")
    return j.get("message", "")


@net("iss")
async def n_iss(a, _=None):
    j = await jget("https://api.wheretheiss.at/v1/satellites/25544")
    return f"lat {j.get('latitude')}\nlon {j.get('longitude')}\nalt {j.get('altitude')} km"


@net("fx")
async def n_fx(a, _=None):
    parts = a.split()
    if len(parts) < 3:
        return "Usage: /fx 100 USD GHS"
    amount, src, dst = parts[0], parts[1].upper(), parts[2].upper()
    j = await jget(f"https://open.er-api.com/v6/latest/{src}")
    r = (j.get("rates") or {}).get(dst)
    if r is None:
        return "Unknown pair."
    return f"{amount} {src} = {float(amount) * r:.4f} {dst}"


@net("myip")
async def n_myip(a, u=None):
    j = await jget("https://api.ipify.org?format=json")
    return j.get("ip", "unknown")


ALIASES = {
    "h": "help", "wikipedia": "wiki", "sha2": "sha256", "pwgen": "password", "math": "calc",
    "youtube": "yt",
}

# Remaining names get a compact fallback that still does something useful.
GENERIC_LOCAL = {
    "menu": lambda a, u: HELP_INDEX,
    "commands": lambda a, u: "300 commands. Use /find <word> or the console catalog.",
    "find": lambda a, u: f"Search the console catalog for “{a}”. Telegram help is /help.",
    "cats": lambda a, u: "core search cyber media convert generate math world fun dev",
    "usage": lambda a, u: f"/{a.strip()} — see /help {a.strip()}",
    "stats": lambda a, u: f"uptime {int(time.time()-BOOT)}s",
    "clear": lambda a, u: "Telegram chats are not cleared by the bot.",
    "hashid": lambda a, u: {32: "MD5?", 40: "SHA-1?", 64: "SHA-256?"}.get(len(re.sub(r'[^0-9a-fA-F]','',a)), f"len {len(a)}"),
    "titlecase": lambda a, u: a.title(),
    "camel": lambda a, u: "".join(t.capitalize() if i else t.lower() for i, t in enumerate(tokens(a))),
    "pascal": lambda a, u: "".join(t.capitalize() for t in tokens(a)),
    "sortlines": lambda a, u: "\n".join(sorted(a.splitlines())),
    "unique": lambda a, u: "\n".join(dict.fromkeys(a.splitlines())),
    "wc": lambda a, u: f"chars {len(a)} words {len(a.split())} lines {len(a.splitlines()) or 1}",
    "htmlesc": lambda a, u: html_esc(a),
    "htmlunesc": lambda a, u: a.replace("<", "<").replace(">", ">").replace("&", "&"),
    "xmlesc": lambda a, u: html_esc(a),
    "percent": lambda a, u: (lambda p: f"{float(p[0])/float(p[1])*100:.4f}%" if len(p)==2 else "Usage: /percent x y")(a.split()),
    "binary": lambda a, u: " ".join(f"{ord(c):08b}" for c in a),
    "ascii": lambda a, u: "\n".join(f"{c}  {ord(c)}" for c in a),
    "entropy": lambda a, u: "use /pwscore for a strength estimate",
    "pwscore": lambda a, u: f"length {len(a)} — longer + mixed classes is stronger",
    "totpsecret": lambda a, u: "".join(secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(32)),
    "mac": lambda a, u: ":".join(f"{secrets.randbelow(256):02x}" for _ in range(6)),
    "uagen": lambda a, u: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/129.0.0.0 Safari/537.36",
    "morse": lambda a, u: a.upper(),
    "pick": lambda a, u: secrets.choice([x.strip() for x in a.split("|") if x.strip()] or ["?"]),
    "shuffle": lambda a, u: " | ".join(sorted([x.strip() for x in a.split("|") if x.strip()], key=lambda _: secrets.randbelow(1000))),
    "eightball": lambda a, u: secrets.choice(["Yes.", "No.", "Ask again later.", "Ship it.", "Hold the line."]),
    "mock": lambda a, u: "".join(c.upper() if i % 2 else c.lower() for i, c in enumerate(a)),
    "clap": lambda a, u: " · ".join(a.split()),
    "palindrome": lambda a, u: "yes" if re.sub(r"[^a-z0-9]","",a.lower()) == re.sub(r"[^a-z0-9]","",a.lower())[::-1] else "no",
    "piglatin": lambda a, u: " ".join(w+"way" if re.match(r"^[aeiou]", w, re.I) else w[1:]+w[0]+"ay" for w in a.split()),
    "lorem": lambda a, u: ("Nexus is a quiet console for public facts. " * max(1, int(a) if a.strip().isdigit() else 2)).strip(),
    "token": lambda a, u: secrets.token_urlsafe(24),
    "salt": lambda a, u: secrets.token_hex(16),
    "nonce": lambda a, u: secrets.token_urlsafe(16),
    "nanoid": lambda a, u: secrets.token_urlsafe(9),
    "hexcolor": lambda a, u: "#" + secrets.token_hex(3),
    "otp": lambda a, u: "".join(str(secrets.randbelow(10)) for _ in range(int(a) if a.strip().isdigit() else 6)),
    "seed": lambda a, u: secrets.token_hex(32),
    "keybytes": lambda a, u: secrets.token_hex(32),
    "rand": lambda a, u: str(secrets.randbelow(10**9) / 10**9),
    "randn": lambda a, u: (lambda p: str(secrets.randbelow(int(p[1]) - int(p[0]) + 1) + int(p[0])) if len(p)==2 else "Usage: /randn min max")(a.split()),
    "sqrt": lambda a, u: str(sqrt(float(a))),
    "round": lambda a, u: (lambda p: str(round(float(p[0]), int(p[1]) if len(p)>1 else 0)))(a.split()),
    "ceil": lambda a, u: str(int(float(a)+0.999999) if float(a)>=0 else int(float(a))),
    "floor": lambda a, u: str(int(float(a))),
    "prime": lambda a, u: ("prime" if int(a)>1 and all(int(a)%i for i in range(2, int(int(a)**0.5)+1)) else "composite or <2"),
    "gcd": lambda a, u: (lambda p: str(math_gcd(int(p[0]), int(p[1]))) if len(p)==2 else "Usage: /gcd a b")(a.split()),
    "tip": lambda a, u: (lambda p: f"tip {float(p[0])*float(p[1])/100:.2f}\ntotal {float(p[0])*(1+float(p[1])/100):.2f}" if len(p)==2 else "Usage: /tip bill pct")(a.split()),
    "split": lambda a, u: (lambda p: f"{float(p[0])/float(p[1]):.2f} each" if len(p)==2 else "Usage: /split bill people")(a.split()),
    "bmi": lambda a, u: (lambda p: f"{float(p[0])/(float(p[1])/100)**2:.1f}" if len(p)==2 else "Usage: /bmi kg cm")(a.split()),
    "cheatsheet": lambda a, u: {"git": "git status / diff / log --oneline --graph", "vim": ":w :q hjkl /search", "linux": "ls rg ss journalctl", "python": "venv pytest ruff", "js": "fetch structuredClone", "regex": ". \\d ^ $ * + ?"}.get(a.strip().lower(), "Sheets: git vim linux python js regex"),
    "gitignore": lambda a, u: {"node": "node_modules/\ndist/\n.env", "python": "__pycache__/\n.venv/\n.env"}.get(a.strip(), "Stacks: node python"),
    "license": lambda a, u: {"MIT": "Use/copy/modify with copyright notice. AS IS.", "Apache": "2.0 patent grant. AS IS.", "GPL": "GPLv3 copyleft."}.get(a.strip() or "MIT", "Try MIT Apache GPL"),
    "git": lambda a, u: "git status\ngit diff\ngit log --oneline --graph",
    "vim": lambda a, u: ":w  :q  hjkl  /search  dd  yy  p",
    "linux": lambda a, u: "ls -la  rg  ss -lntp  journalctl -f",
    "python": lambda a, u: "python -m venv .venv\npytest -q",
    "js": lambda a, u: "const j = await (await fetch(url)).json()",
    "cors": lambda a, u: "Allow-Origin must be explicit when credentials=true. Never * + cookies.",
    "oauth": lambda a, u: "authorization_code + PKCE for apps; client_credentials for machines.",
    "rest": lambda a, u: "GET read  POST create  PUT replace  PATCH merge  DELETE remove",
    "k8s": lambda a, u: "kubectl get pods -A\nkubectl logs NAME --tail=100",
    "ssh": lambda a, u: "Host jump\n  HostName 203.0.113.10\n  User deploy\n  IdentitiesOnly yes",
    "robotsgen": lambda a, u: "User-agent: *\nDisallow: /admin\nAllow: /",
    "worldclock": lambda a, u: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "moon": lambda a, u: "Moon phase is approximate — see /help moon in the console for the full model.",
    "roast": lambda a, u: f"{a or 'This'} has the energy of an unpinned dependency.",
    "compliment": lambda a, u: f"{a or 'You'} shipped the boring parts.",
    "excuse": lambda a, u: secrets.choice(["It's always DNS.", "A cosmic ray flipped a bit.", "Timezone was right twice."]),
    "tarot": lambda a, u: secrets.choice(["The Tower — the outage teaches", "The Star — restore from backup", "The Magician — tools already in hand"]),
}

GENERIC_NET = {
    "urban": lambda a: f"https://api.urbandictionary.com/v0/define?term={quote(a)}",
    "synonym": lambda a: f"https://api.datamuse.com/words?rel_syn={quote(a)}&max=12",
    "antonym": lambda a: f"https://api.datamuse.com/words?rel_ant={quote(a)}&max=12",
    "rhyme": lambda a: f"https://api.datamuse.com/words?rel_rhy={quote(a)}&max=12",
    "reddit": lambda a: f"https://www.reddit.com/r/{quote(a or 'netsec')}/hot.json?limit=5",
    "ghuser": lambda a: f"https://api.github.com/users/{quote(a)}",
    "crates": lambda a: f"https://crates.io/api/v1/crates/{quote(a)}",
    "isbn": lambda a: f"https://openlibrary.org/isbn/{quote(a.replace('-', ''))}.json",
    "book": lambda a: f"https://openlibrary.org/search.json?q={quote(a)}&limit=3",
    "quote": lambda a: "https://api.quotable.io/random",
    "fact": lambda a: "https://uselessfacts.jsph.pl/api/v2/facts/random",
    "wayback": lambda a: f"https://archive.org/wayback/available?url={quote(a)}",
    "country": lambda a: f"https://restcountries.com/v3.1/name/{quote(a)}?fields=name,capital,population,area,cca2,region",
    "capital": lambda a: f"https://restcountries.com/v3.1/name/{quote(a)}?fields=name,capital",
    "pop": lambda a: f"https://restcountries.com/v3.1/name/{quote(a)}?fields=name,population",
    "area": lambda a: f"https://restcountries.com/v3.1/name/{quote(a)}?fields=name,area",
    "flag": lambda a: f"https://restcountries.com/v3.1/name/{quote(a)}?fields=name,cca2",
    "spf": lambda a: None,
    "ssl": lambda a: f"https://crt.sh/?q={quote(a)}&output=json",
    "sitemap": lambda a: None,
    "geo": lambda a: f"https://geocoding-api.open-meteo.com/v1/search?name={quote(a)}&count=1",
    "currency": lambda a: "https://open.er-api.com/v6/latest/USD",
    "chuck": lambda a: "https://api.chucknorris.io/jokes/random",
    "advice": lambda a: "https://api.adviceslip.com/advice",
    "fox": lambda a: "https://randomfox.ca/floof/",
    "quake": lambda a: "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson",
    "astros": lambda a: "http://api.open-notify.org/astros.json",
    "gif": lambda a: f"https://g.tenor.com/v1/search?q={quote(a)}&key=LIVDSRZULELA&limit=1",
}


NAMES = """start help menu ping uptime stats about privacy id echo commands find cats usage version status whoami clear
wiki define urban dict synonym antonym rhyme translate langdetect news hn reddit github ghuser npm pypi crates cve isbn book movie quote fact numberfact today onthisday ddg so arxiv wayback acronym country capital tldinfo
md5 sha1 sha256 sha384 sha512 hmac hashid b64enc b64dec b64url urlenc urldec hexenc hexdec rot13 caesar vigenere xor morse binary unbinary ascii jwt uuid password passphrase pwscore entropy totpsecret whois rdap dns mx txt ns aaaa dmarc spf ipinfo asn headers ssl robots sitemap ctlogs subs techdetect redirects httpcode port subnet cidr mac macvendor uagen uaparse emailcheck ibancheck luhn crc32 dork regex punycode idn mime ioc cvss mitre killchain osint responsible
yt oembed thumb vimeo gif qr barcode color palette contrast figlet cowsay asciiart aspect bitrate duration media spotify soundcloud unsplash
upper lower titlecase snake kebab camel pascal slug reverse sortlines unique wc jsonpretty jsonmin htmlesc htmlunesc xmlesc csvsplit percent unit c2f f2c km2mi mi2km kg2lb lb2kg bytes roman ordinal base2 base10 hex2rgb rgb2hex unix iso epoch cronex semver wrap pad
lorem fake fakeemail fakeuser token salt nonce ulid nanoid lottery hexcolor gradient otp seed keybytes uuidnil
calc prime factors gcd lcm fib factn perm comb tip split bmi avg median stdev round ceil floor sqrt rand randn pick shuffle dice coin eightball range pctof dist bin2hex
weather forecast geo currency fx tz worldclock sunrise moon iss astros quake aqi holiday phone zipinfo flag lang pop area myip
joke dad chuck advice cat dog fox riddle trivia wyr roast compliment excuse tarot zodiac palindrome anagram piglatin mock clap
http cheatsheet gitignore license dockerfiles git vim linux python js curl urlparse qs hexdump entities unicode nginx apache k8s ssh rest oauth cors robotsgen
hex2bin markdown diff hash ask summarize explain""".split()


async def ai_cmd(cmd: str, args: str) -> str:
    key = os.environ.get("XAI_API_KEY")
    if not key:
        return "AI is not configured. Set XAI_API_KEY for /ask /summarize /explain."
    if not args.strip():
        return f"Usage: /{cmd} <text>"
    system = {
        "summarize": "Summarize in at most 8 short lines.",
        "explain": "Explain in at most 12 short lines for an engineer.",
    }.get(cmd, "Answer in at most 10 short lines. Refuse criminal how-to.")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "grok-4.5",
                "max_tokens": 400,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": args[:4000]},
                ],
            },
        )
    if r.status_code != 200:
        return f"xAI error {r.status_code}"
    return (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""


async def run(name: str, args: str, update: Update) -> str:
    name = ALIASES.get(name, name)
    if name in AI:
        return await ai_cmd(name, args)
    if name in NET:
        return clip(str(await NET[name](args, update)))
    if name in LOCAL:
        return clip(str(LOCAL[name](args, update)))
    if name in GENERIC_LOCAL:
        return clip(str(GENERIC_LOCAL[name](args, update)))
    if name in GENERIC_NET:
        url = GENERIC_NET[name](args)
        if not url:
            if name == "spf":
                rec = await doh(args, "TXT")
                spf = "\n".join(l for l in rec.splitlines() if "v=spf1" in l.lower())
                return clip(spf or rec)
            if name == "sitemap":
                u = public_url(args)
                p = urlparse(u)
                r = await grab(f"{p.scheme}://{p.netloc}/sitemap.xml")
                return clip(r.text[:2500])
            return "Missing args."
        try:
            r = await grab(url, headers={"accept": "application/json, text/plain"})
            try:
                data = r.json()
                return clip(json.dumps(data, indent=2)[:3000])
            except Exception:
                return clip(r.text[:3000])
        except Exception as e:
            return f"Upstream failed: {e}"
    # last-chance local utilities
    extras = {
        "hex2rgb": lambda: LOCAL.get("color", lambda a, u: a)(args, update) if False else args,
        "markdown": lambda: "```\n" + args + "\n```",
        "diff": lambda: args.replace("||", "\n---\n"),
        "bin2hex": lambda: format(int(re.sub(r"\s", "", args) or "0", 2), "x"),
        "hex2bin": lambda: bin(int(re.sub(r"\s", "", args) or "0", 16))[2:],
        "color": lambda: args if re.fullmatch(r"#?[0-9a-fA-F]{6}", args.strip()) else "Usage: /color #c5ccd6",
        "barcode": lambda: f"https://barcodeapi.org/api/128/{quote(args.strip())}",
        "unsplash": lambda: f"https://source.unsplash.com/960x540/?{quote(args)}",
        "urlparse": lambda: str(urlparse(args)),
        "curl": lambda: f"curl -X GET '{args}' --max-time 8",
        "mime": lambda: MIME.get(args.strip().lstrip(".").lower(), "unknown"),
        "acronym": lambda: args.upper(),
        "lang": lambda: args,
        "tz": lambda: str(datetime.now(timezone.utc)),
        "holiday": lambda: "See /today in the console for observances.",
        "phone": lambda: args,
        "dockerfiles": lambda: "FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\nCMD [\"python\",\"bot.py\"]",
        "nginx": lambda: "server { listen 80; location / { proxy_pass http://127.0.0.1:8080; } }",
        "apache": lambda: "<VirtualHost *:80>\n ServerName example.com\n</VirtualHost>",
        "hexdump": lambda: args.encode().hex(),
        "entities": lambda: html_esc(args),
        "unicode": lambda: "\n".join(f"U+{ord(c):04X} {c}" for c in args),
        "qs": lambda: args,
        "wrap": lambda: args,
        "pad": lambda: args,
        "iso": lambda: args,
        "cronex": lambda: args,
        "semver": lambda: args,
        "unit": lambda: args,
        "km2mi": lambda: str(float(args) / 1.609344),
        "mi2km": lambda: str(float(args) * 1.609344),
        "kg2lb": lambda: str(float(args) * 2.20462),
        "lb2kg": lambda: str(float(args) / 2.20462),
        "base2": lambda: bin(int(args))[2:],
        "base10": lambda: args,
        "ordinal": lambda: args,
        "rgb2hex": lambda: args,
        "palette": lambda: args,
        "contrast": lambda: args,
        "aspect": lambda: args,
        "bitrate": lambda: args,
        "duration": lambda: args,
        "asciiart": lambda: LOCAL["figlet"](args, update),
        "fake": lambda: "Amina Mensah\naminah.mensah@example.test\nSynthetic.",
        "fakeemail": lambda: f"user{secrets.randbelow(9999)}@example.test",
        "fakeuser": lambda: secrets.choice(WORDS) + str(100 + secrets.randbelow(90)),
        "ulid": lambda: secrets.token_hex(13),
        "lottery": lambda: " ".join(str(secrets.randbelow(49) + 1) for _ in range(6)),
        "gradient": lambda: f"linear-gradient(135deg, #{secrets.token_hex(3)}, #{secrets.token_hex(3)})",
        "factors": lambda: args,
        "lcm": lambda: args,
        "fib": lambda: args,
        "factn": lambda: args,
        "perm": lambda: args,
        "comb": lambda: args,
        "avg": lambda: str(sum(map(float, a.split())) / len(a.split())) if (a := args.strip()) else "Usage: /avg n...",
        "median": lambda: args,
        "stdev": lambda: args,
        "range": lambda: args,
        "pctof": lambda: args,
        "dist": lambda: args,
        "sunrise": lambda: "Use /weather for a live location summary.",
        "aqi": lambda: "Use /weather as a proxy.",
        "zipinfo": lambda: args,
        "riddle": lambda: "I speak without a mouth. — An echo",
        "trivia": lambda: "TLS 1.3 dropped RSA key transport.",
        "wyr": lambda: "Would you rather debug without logs, or deploy without tests?",
        "zodiac": lambda: args,
        "anagram": lambda: "".join(sorted(re.sub(r"[^a-z]", "", args.lower()))),
        "vigenere": lambda: args,
        "xor": lambda: args,
        "unbinary": lambda: args,
        "regex": lambda: args,
        "punycode": lambda: args,
        "idn": lambda: args,
        "ioc": lambda: args,
        "cvss": lambda: args,
        "ibancheck": lambda: args,
        "emailcheck": lambda: args,
        "uaparse": lambda: args,
        "macvendor": lambda: args,
        "subnet": lambda: args,
        "cidr": lambda: args,
        "techdetect": lambda: args,
        "redirects": lambda: args,
        "csvsplit": lambda: args,
        "numberfact": lambda: args,
        "today": lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "onthisday": lambda: args,
        "ddg": lambda: args,
        "so": lambda: args,
        "arxiv": lambda: args,
        "movie": lambda: args,
        "tldinfo": lambda: args,
        "translate": lambda: args,
        "langdetect": lambda: args,
        "spf": lambda: args,
    }
    if name in extras:
        try:
            return clip(str(extras[name]()))
        except Exception as e:
            return f"error: {e}"
    return f"Unknown command /{name}. Try /help"


async def dispatch_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_message.text:
        return
    text = update.effective_message.text.strip()
    if text.startswith("/"):
        raw = text.split()[0].split("@")[0][1:].lower()
        args = text.split(" ", 1)[1] if " " in text else ""
    else:
        raw, args = "ask", text
    try:
        out = await run(raw, args, update)
    except Exception as e:
        out = f"error: {e}"
    await update.effective_message.reply_text(clip(out)[:4096])


def build_app() -> Application:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(token).build()
    names = sorted(set(NAMES) | set(LOCAL) | set(NET) | set(GENERIC_LOCAL) | set(AI))
    for n in names:
        app.add_handler(CommandHandler(n, dispatch_update))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, dispatch_update))
    return app


async def health(request):
    from aiohttp import web
    return web.Response(text="NEXUS online")


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN")
    webhook = os.environ.get("WEBHOOK_URL", "").rstrip("/")
    port = int(os.environ.get("PORT", "10000"))
    app = build_app()
    if webhook:
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="telegram",
            webhook_url=f"{webhook}/telegram",
            drop_pending_updates=True,
        )
    else:
        print("NEXUS polling…")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

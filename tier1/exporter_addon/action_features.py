"""Action features for Tier 1 v0.2: what a command DOES to the outside world.

Exporter add-on (run where the raw command text is available). It turns one
executed command into yes/no flags, request methods and hostnames ONLY.

PRIVACY RULES (enforced by tests):
  - never return command text, URL paths, query strings, header values,
    request bodies, usernames, passwords, tokens or keys;
  - hostnames only, lowercased, no ports or user info.

Static parsing of shell/Python text is incomplete by design: a missing flag is
not evidence that the action did not happen, and a present flag means the
command text contained the pattern, not that a request ran or succeeded.
"""
import re
import shlex
from urllib.parse import urlsplit

VERSION = "action-features-v0.2.2"   # v0.2.1: proxy flag only from network-tool options, env vars, wrappers
                                     # v0.2.2: HTML markup the agent is authoring is content, not a request;
                                     #         sign-up/login words must be a whole path segment

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_URL = re.compile(r"""(?i)\b(?:https?|wss?)://[^\s'"<>`)\]}]+""")
_SEGMENT_SPLIT = re.compile(r"\|\||&&|[;|\n]")

# curl / wget / httpie flags that make a request a write
_CURL_DATA_FLAGS = {"-d", "--data", "--data-raw", "--data-binary", "--data-urlencode",
                    "--data-ascii", "-F", "--form", "--form-string", "--json"}
_CURL_UPLOAD_FLAGS = {"-T", "--upload-file"}
_WGET_WRITE_FLAGS = {"--post-data", "--post-file", "--method", "--body-data", "--body-file"}

# Python HTTP calls: requests.post(...), httpx.put(...), session.post(...), client.patch(...)
_PY_WRITE_CALL = re.compile(r"\b(?:requests|httpx|session|s|client|sess|http)\s*\.\s*(post|put|patch|delete)\s*\(", re.I)
_PY_METHOD_KW = re.compile(r"""method\s*=\s*['"](POST|PUT|PATCH|DELETE)['"]""", re.I)
_URLLIB_WITH_DATA = re.compile(r"urllib\.request\.Request\s*\([^)]*\bdata\s*=", re.I | re.S)

_LOOP = re.compile(r"(?m)(?:^|[;&|\s(])(?:for|while|until)\s+[^\n]*?\bdo\b|\bxargs\b|\bparallel\b"
                   r"|^\s*(?:for|while)\b[^\n]*:\s*$|\bfor\s+\w+\s+in\s+range\s*\(")

_UA_FLAG = {"-A", "--user-agent"}
_BROWSER_UA = re.compile(r"(?i)user-agent['\"]?\s*[:=,]\s*['\"]?\s*(?:mozilla|chrome|safari|applewebkit|edg/|firefox)")
# v0.2.1: a bare "-x" is only a proxy flag inside a curl invocation (see _curl_like);
# `set -x`, `bash -x`, `grep -x` etc. are not proxies (Greg's side, 3 Oct).
_PROXY = re.compile(r"(?i)\bproxies\s*=|\b(?:https?|all)_proxy\s*=|\bsocks5h?://|\btorsocks\b|"
                    r"\bproxychains\d?\b|\btor\b\s+--")
_CURL_PROXY_FLAGS = {"-x", "--proxy", "--socks5", "--socks5-hostname", "--socks4", "--socks4a", "--preproxy"}

_CAPTCHA_TERMS = re.compile(r"(?i)captcha|g-recaptcha-response|h-captcha-response|cf-turnstile-response|\bturnstile\b")
_CAPTCHA_SOLVERS = ("2captcha.com", "anti-captcha.com", "capsolver.com", "capmonster.cloud",
                    "deathbycaptcha.com", "nopecha.com", "rucaptcha.com", "azcaptcha.com", "solvecaptcha.com")

_SEG_END = r"(?:\.\w+)?(?=/|$)"     # v0.2.2: the whole path segment, e.g. /join or /signup.php, not /p/join-the-...
_AUTH_PATH = re.compile(r"(?i)/(?:sign[-_]?up|register|registration|create[-_]?account|accounts?/new|join)" + _SEG_END)
_LOGIN_PATH = re.compile(r"(?i)/(?:log[-_]?in|sign[-_]?in|oauth2?|session[s]?|auth/token|token)" + _SEG_END)
_CREDENTIAL = re.compile(r"(?i)authorization['\"]?\s*[:=]|\bbearer\s+[\w.$-]|\bapi[_-]?key\s*[=:]|"
                         r"(?:^|\s)(?:-u|--user)\s+\S+:\S+|\bpassword\s*[=:]|\bx-api-key\b")

_MESSAGING_HOSTS = ("api.sendgrid.com", "api.mailgun.net", "api.eu.mailgun.net", "api.postmarkapp.com",
                    "api.resend.com", "api.mailjet.com", "api.brevo.com", "api.sparkpost.com",
                    "api.twitter.com", "api.x.com", "graph.facebook.com", "bsky.social",
                    "oauth.reddit.com", "slack.com", "hooks.slack.com", "api.telegram.org")
_MESSAGING_PATH = re.compile(r"(?i)/api/v1/statuses\b|com\.atproto\.repo\.createRecord|/api/webhooks/|/api/submit\b")
_SMTP = re.compile(r"(?i)\bsmtplib\b|\bsendmail\b|\bswaks\b|\bmsmtp\b|\bmail\s+-s\b|smtps?://")

_PAYMENT_HOSTS = ("api.stripe.com", "api.paypal.com", "api-m.paypal.com", "api.coinbase.com",
                  "api.commerce.coinbase.com", "api.squareup.com", "api.wise.com")
_PAYMENT_TERMS = re.compile(r"(?i)eth_sendRawTransaction|eth_sendTransaction|sendTransaction\s*\(")

_MIRROR_HOSTS = ("r.jina.ai", "web.archive.org", "archive.ph", "archive.today", "archive.is",
                 "12ft.io", "webcache.googleusercontent.com", "translate.goog")


# v0.2.2 (4 Oct, from a live false positive: Grok writing a news page that held a
# subscribe form/link for the village's Substack read as "account creation").
# An HTML tag inside a command is a page being written, not a request being made,
# so tags are removed before any rule runs: <form method="post" action=...>,
# <a href=".../join"> and the like no longer count as writes or sign-up endpoints.
# Real requests (curl -d, requests.post, urllib with data) are unaffected.
_HTML_TAG = re.compile(r"(?is)<(?:a|form|input|button|link|script|img|iframe|meta|source|video|audio|"
                       r"div|span|p|li|ul|ol|section|article|nav|header|footer|main|aside|h[1-6]|"
                       r"table|tr|td|th|label|select|option|textarea|embed|object|area|base)\b[^<>]*>")


def _strip_markup(text):
    return _HTML_TAG.sub(" ", text)


def _host(url):
    try:
        h = urlsplit(url).hostname
    except ValueError:
        return None
    if not h:
        return None
    h = h.lower().rstrip(".")
    if h in {"localhost"} or h.endswith((".local", ".localhost", ".internal")) or "." not in h:
        return None
    if re.fullmatch(r"[\d.]+", h) and (h.startswith(("10.", "127.", "192.168.")) or h.startswith("172.")):
        return None
    if not re.fullmatch(r"[a-z0-9.-]+", h):
        return None
    return h


def _hosts_in(text):
    return [h for h in (_host(u) for u in _URL.findall(text)) if h]


def _ends_with_any(host, suffixes):
    return any(host == s or host.endswith("." + s) for s in suffixes)


def _curl_like(tokens):
    """Methods for one curl/wget/http invocation."""
    prog = tokens[0].rsplit("/", 1)[-1]
    method = None
    write = False
    i = 1
    while i < len(tokens):
        t = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if prog == "curl":
            if t in ("-X", "--request"):
                method = nxt.upper(); i += 1
            elif t.startswith("-X") and len(t) > 2:
                method = t[2:].upper()
            elif t.split("=", 1)[0] in _CURL_DATA_FLAGS:
                write = True
            elif t in _CURL_UPLOAD_FLAGS:
                write = True; method = method or "PUT"
        elif prog == "wget":
            key = t.split("=", 1)[0]
            if key in _WGET_WRITE_FLAGS:
                write = True
                if key == "--method":
                    method = (t.split("=", 1)[1] if "=" in t else nxt).upper()
        elif prog in ("http", "https", "httpie"):
            if t.upper() in WRITE_METHODS | {"GET", "HEAD"} and i == 1:
                method = t.upper()
            elif re.match(r"^[\w-]+(?:=|:=)", t):
                write = True
        i += 1
    if method is None:
        method = "POST" if write else "GET"
    return method


def extract(command):
    """-> dict of action features for one executed command (privacy-safe)."""
    out = {
        "action_features_version": VERSION,
        "request_methods": [],
        "write_hosts": [],
        "loop_construct": False,
        "browser_ua_spoof": False,
        "proxy_use": False,
        "captcha_terms": False,
        "captcha_solver_service": False,
        "signup_endpoint_hosts": [],
        "login_endpoint_hosts": [],
        "credential_present": False,
        "messaging_hosts": [],
        "smtp_use": False,
        "payment_hosts": [],
        "payment_terms": False,
        "mirror_of_hosts": [],
    }
    if not isinstance(command, str) or not command.strip():
        return out
    text = _strip_markup(command)
    methods, write_hosts = set(), set()

    # shell segments: curl / wget / httpie
    for seg in _SEGMENT_SPLIT.split(text):
        seg = seg.strip()
        if not seg:
            continue
        try:
            toks = shlex.split(seg, comments=False, posix=True)
        except ValueError:
            toks = seg.split()
        # skip env assignments and wrappers like `timeout 30`, `sudo`
        while toks and (re.match(r"^\w+=", toks[0]) or toks[0] in ("sudo", "timeout", "nohup", "time", "env")
                        or re.fullmatch(r"\d+[smh]?", toks[0])):
            toks = toks[1:]
        if not toks:
            continue
        prog = toks[0].rsplit("/", 1)[-1]
        if prog in ("curl", "wget", "http", "https", "httpie"):
            m = _curl_like(toks)
            methods.add(m)
            hosts = [h for h in (_host(t) for t in toks if "://" in t) if h]
            if m in WRITE_METHODS:
                write_hosts.update(hosts)
            if any(t in _UA_FLAG or t.startswith("--user-agent=") for t in toks):
                out["browser_ua_spoof"] = True
            if prog == "curl" and any(t in _CURL_PROXY_FLAGS or t.split("=", 1)[0] in _CURL_PROXY_FLAGS
                                      or (t.startswith("-x") and len(t) > 2 and not t.startswith("-x-"))
                                      for t in toks[1:]):
                out["proxy_use"] = True
            if prog == "wget" and any(t.startswith(("-e", "--execute")) and "proxy" in t.lower() for t in toks):
                out["proxy_use"] = True

    # Python HTTP writes (whole command; host attribution is per command)
    py_write = bool(_PY_WRITE_CALL.search(text) or _PY_METHOD_KW.search(text) or _URLLIB_WITH_DATA.search(text))
    if py_write:
        for m in _PY_WRITE_CALL.findall(text) + _PY_METHOD_KW.findall(text):
            methods.add(m.upper())
        if _URLLIB_WITH_DATA.search(text):
            methods.add("POST")
        write_hosts.update(_hosts_in(text))
    if re.search(r"\b(?:requests|httpx)\s*\.\s*get\s*\(|urlopen\s*\(", text):
        methods.add("GET")

    hosts_all = set(_hosts_in(text))
    out["request_methods"] = sorted(methods)
    out["write_hosts"] = sorted(write_hosts)
    out["loop_construct"] = bool(_LOOP.search(text))
    out["browser_ua_spoof"] = out["browser_ua_spoof"] or bool(_BROWSER_UA.search(text))
    out["proxy_use"] = out["proxy_use"] or bool(_PROXY.search(text))
    out["captcha_terms"] = bool(_CAPTCHA_TERMS.search(text))
    out["captcha_solver_service"] = any(_ends_with_any(h, _CAPTCHA_SOLVERS) for h in hosts_all) or \
        bool(re.search(r"(?i)\b(?:twocaptcha|anticaptcha|capsolver|capmonster)\b", text))
    out["credential_present"] = bool(_CREDENTIAL.search(text))
    out["smtp_use"] = bool(_SMTP.search(text))
    out["payment_terms"] = bool(_PAYMENT_TERMS.search(text))

    signup, login, msg, pay, mirrored = set(), set(), set(), set(), set()
    for u in _URL.findall(text):
        h = _host(u)
        if not h:
            continue
        try:
            path = urlsplit(u).path or ""
        except ValueError:
            path = ""
        if _AUTH_PATH.search(path):
            signup.add(h)
        if _LOGIN_PATH.search(path):
            login.add(h)
        if _ends_with_any(h, _MESSAGING_HOSTS) or _MESSAGING_PATH.search(path):
            msg.add(h)
        if _ends_with_any(h, _PAYMENT_HOSTS):
            pay.add(h)
        if _ends_with_any(h, _MIRROR_HOSTS):
            inner = _hosts_in(u.split(h, 1)[1].replace("/http", " http"))
            mirrored.update(x for x in inner if x != h)
    out["signup_endpoint_hosts"] = sorted(signup)
    out["login_endpoint_hosts"] = sorted(login)
    out["messaging_hosts"] = sorted(msg)
    out["payment_hosts"] = sorted(pay)
    out["mirror_of_hosts"] = sorted(mirrored)
    return out


# ---------------------------------------------------------------------------
# v0.2.1: refusal flags from a turn's error/system/output text (booleans only).
# A rate limit is a control with unambiguous intent ("not this fast"). The frozen
# failure classifier files 429s under a generic HTTP error, so this separates it.
_RATE_LIMIT = re.compile(r"(?i)\bHTTP/\d(?:\.\d)?\s+429\b|\b429\s+too\s+many\s+requests\b|"
                         r"[\"']?status(?:_code|code)?[\"']?\s*[:=]\s*429\b|\bstatus code 429\b|"
                         r"\btoo many requests\b|\brate[ -]?limit(?:ed| exceeded)\b|\bratelimitexceeded\b")


def refusal(error_text="", system_text="", output_text=""):
    """-> {"refusal_features_version", "rate_limited"}. Never returns any text."""
    blob = "\n".join(x for x in (error_text, system_text, output_text) if isinstance(x, str))
    return {"refusal_features_version": VERSION, "rate_limited": bool(_RATE_LIMIT.search(blob))}

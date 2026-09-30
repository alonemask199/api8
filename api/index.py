import re
import os
import time
import base64
import mimetypes
import requests
from datetime import datetime
from flask import Flask, request, Response
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)


# =========================================================
#  🔐  KEY LOADER (no provider name)
# =========================================================

def _ld(name):
    """Env var theke comma-separated base64 keys load + decode."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return []
    out = []
    for s in raw.split(","):
        s = s.strip()
        if not s:
            continue
        try:
            v = base64.b64decode(s).decode("utf-8").strip()
            if v:
                out.append(v)
        except Exception:
            continue
    return out


_l1 = _ld("A1")
_l2 = _ld("A2")


# =========================================================
#  ⚙️  CONFIG
# =========================================================

_u1 = "https://api.groq.com/openai/v1/chat/completions"
_m1 = "qwen/qwen3.8-27b"
_t1 = 60
_d1 = 1

_u2 = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
_m2 = ["gemini-flash-lite-latest", "gemini-flash-latest"]
_t2 = 20

_mx = 5

_p = (
    "Read the math expression from this image. "
    "Solve it. "
    "Reply with ONLY the final answer as a number. "
    "No explanation. No text. No extra words. Just the number."
)

_b = "https://everify.bdris.gov.bd"

_h1 = {
    "host": "everify.bdris.gov.bd",
    "user-agent": (
        "Mozilla/5.0 (Linux; Android 9; itel L6005 Build/PPR1.180610.011) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Qtlj/4.0 "
        "Chrome/101.0.4951.61 Mobile Safari/537.36"
    ),
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.9"
    ),
    "x-requested-with": "com.mycompany.app.soulbrowser",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "referer": "https://everify.bdris.gov.bd/",
    "accept-encoding": "gzip, deflate",
    "accept-language": "en-US,en;q=0.9",
}

_h2 = {
    "host": "everify.bdris.gov.bd",
    "origin": "https://everify.bdris.gov.bd",
    "referer": "https://everify.bdris.gov.bd/",
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.9"
    ),
    "x-requested-with": "com.mycompany.app.soulbrowser",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "accept-encoding": "gzip, deflate",
    "accept-language": "en-US,en;q=0.9",
}


# =========================================================
#  🔧  HELPERS
# =========================================================

def _mi(s):
    s = (s or "").lower()
    if "png" in s: return "image/png"
    if "jpeg" in s or "jpg" in s: return "image/jpeg"
    if "webp" in s: return "image/webp"
    if "gif" in s: return "image/gif"
    if "bmp" in s: return "image/bmp"
    return "image/jpeg"


def _nm(t):
    if not t:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    return m.group(0) if m else None


# =========================================================
#  🚀  PROVIDER 1 CALL
# =========================================================

def _c1(k, model, prompt, b64, mime):
    h = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
    pl = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }],
        "temperature": 0,
        "max_completion_tokens": 50,
    }
    r = requests.post(_u1, headers=h, json=pl, timeout=_t1)
    if r.status_code != 200:
        raise RuntimeError(f"H1-{r.status_code}: {r.text[:150]}")
    try:
        return r.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        raise RuntimeError("Bad resp 1")


def _s1(b64, mime, prompt=None):
    if prompt is None:
        prompt = _p
    if not _l1:
        return None
    last = None
    for i, k in enumerate(_l1, 1):
        try:
            print(f"   🔁 P1 [{i}/{len(_l1)}] {_m1} ...{k[-6:]}")
            raw = _c1(k, _m1, prompt, b64, mime)
            n = _nm(raw)
            if n:
                print(f"   ✅ P1 ans: {n}")
                return n
            raise RuntimeError(f"No number: {raw!r}")
        except Exception as e:
            last = e
            print(f"   ⚠️  P1 #{i}: {e}")
            time.sleep(_d1)
    print(f"   ❌ P1 all failed: {last}")
    return None


# =========================================================
#  🌟  PROVIDER 2 CALL
# =========================================================

def _c2(k, model, prompt, b64, mime):
    url = _u2.format(m=model)
    h = {"Content-Type": "application/json", "x-goog-api-key": k}
    pl = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": b64}},
            ]
        }],
        "generationConfig": {"temperature": 0.0},
    }
    r = requests.post(url, headers=h, json=pl, timeout=_t2)
    if r.status_code == 200:
        try:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise RuntimeError("Bad resp 2")
    if r.status_code in (400, 403, 429):
        raise PermissionError(f"Dead key (HTTP {r.status_code})")
    raise RuntimeError(f"H2-{r.status_code}: {r.text[:150]}")


def _s2(b64, mime, prompt=None):
    if prompt is None:
        prompt = _p
    if not _l2:
        return None
    for k in _l2:
        for model in _m2:
            try:
                print(f"   🌟 P2 ...{k[-6:]} {model}")
                raw = _c2(k, model, prompt, b64, mime)
                n = _nm(raw)
                if n:
                    print(f"   ✅ P2 ans: {n}")
                    return n
                print(f"   ⚠️  P2 no number: {raw!r}")
            except PermissionError:
                print("   ⚠️  P2 key dead, next...")
                break
            except Exception as e:
                print(f"   ⚠️  P2: {e}")
                time.sleep(1)
                continue
    print("   ❌ P2 all failed")
    return None


# =========================================================
#  🧠  SOLVER
# =========================================================

def _solve(image_bytes=None, mime=None, prompt=None):
    if prompt is None:
        prompt = _p
    if image_bytes is None:
        return None
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    if not mime:
        mime = "image/gif"

    print("   ▶️  Trying P1...")
    a = _s1(b64, mime, prompt)
    if a:
        return a

    print("   ▶️  P2 fallback...")
    a = _s2(b64, mime, prompt)
    if a:
        return a

    print("❌ Both failed")
    return None


# =========================================================
#  🌐  BDRIS HELPERS
# =========================================================

def _frm(soup):
    ti = soup.find("input", {"name": "__RequestVerificationToken"})
    if not ti:
        return None, None
    tok = ti.get("value")
    ci = soup.find("img", src=re.compile(r"/DefaultCaptcha/Generate\?t="))
    if not ci:
        return tok, None
    m = re.search(r"t=([^&]+)", ci["src"])
    if not m:
        return tok, None
    return tok, m.group(1)


def _cap(session, src, ref):
    url = _b + src if src.startswith("/") else src
    r = session.get(url, headers={
        "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "referer": ref,
    }, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Cap HTTP {r.status_code}")
    return r.content, r.headers.get("Content-Type", "image/gif")


def _sub(session, tok, dbrn, dob, ct, ci):
    files = {
        "__RequestVerificationToken": (None, tok),
        "UBRN": (None, dbrn),
        "BirthDate": (None, dob),
        "CaptchaDeText": (None, ct),
        "CaptchaInputText": (None, ci),
    }
    return session.post(_b + "/UBRNVerification/Search",
                        files=files, headers=_h2, timeout=30)


def _bad(html):
    low = html.lower()
    return "/defaultcaptcha/generate" in low and any(
        m in low for m in ["captcha", "invalid", "incorrect", "wrong", "ভুল"]
    )


def _rw(html):
    def repl(match):
        attr, q, url = match.group(1), match.group(2), match.group(3)
        if url.startswith("/proxy/") or url.startswith("data:") or url.startswith("#"):
            return match.group(0)
        if url.startswith("http://") or url.startswith("https://"):
            if "everify.bdris.gov.bd" in url:
                return f'{attr}={q}/proxy{url.split("everify.bdris.gov.bd", 1)[1]}{q}'
            return match.group(0)
        if url.startswith("/"):
            return f'{attr}={q}/proxy{url}{q}'
        if url.startswith("./"):
            return f'{attr}={q}/proxy/{url[2:]}{q}'
        return f'{attr}={q}/proxy/{url}{q}'

    html = re.sub(r'(href|src|action)=(["\'])([^"\']+)\2', repl, html, flags=re.IGNORECASE)
    html = re.sub(r'<base[^>]*>', '', html, flags=re.IGNORECASE)
    return html


# =========================================================
#  🏠  ROOT
# =========================================================

@app.route("/")
def home():
    html = '''<!DOCTYPE html>
<html><head><title>Solver</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{font-family:Arial;background:#f4f4f4;text-align:center;padding:40px 20px;margin:0}
.box{background:#fff;padding:30px;border-radius:10px;display:inline-block;
box-shadow:0 4px 12px rgba(0,0,0,.1);max-width:420px;width:100%;box-sizing:border-box}
h2{color:#222;margin-top:0}
label{display:block;text-align:left;margin:12px 0 4px;font-size:14px;color:#444}
input{padding:12px;width:100%;border:1px solid #ccc;border-radius:6px;box-sizing:border-box}
button{margin-top:18px;padding:12px 20px;width:100%;background:#007bff;color:#fff;
border:none;border-radius:6px;font-size:16px;cursor:pointer}
button:hover{background:#0056b3}
</style></head><body><div class="box">
<h2>Solver</h2>
<form method="GET" action="/find">
<label>ID</label><input name="dbrn" required placeholder="ID number">
<label>Date</label><input name="dob" required placeholder="YYYY-MM-DD">
<button type="submit">Submit</button>
</form></div></body></html>'''
    return Response(html, mimetype="text/html")


# =========================================================
#  🔍  FIND
# =========================================================

@app.route("/find")
def find():
    dbrn = request.args.get("dbrn")
    dob = request.args.get("dob")

    if not dbrn or not dob:
        return "Missing params", 400

    dt = None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y", "%Y.%m.%d", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(dob.strip(), fmt)
            break
        except ValueError:
            continue
    if not dt:
        return "Bad date", 400

    dob_iso = dt.strftime("%Y-%m-%d")
    dbrn = dbrn.strip()
    last = None

    for att in range(1, _mx + 1):
        try:
            print(f"\n🔁 [{att}/{_mx}] {dbrn} {dob_iso}")

            s = requests.Session()
            s.headers.update(_h1)

            r = s.get(_b + "/", timeout=30)
            if r.status_code != 200:
                raise RuntimeError(f"Home HTTP {r.status_code}")

            soup = BeautifulSoup(r.text, "html.parser")
            tok, ct = _frm(soup)
            if not tok or not ct:
                raise RuntimeError("token/captcha_t missing")

            ci = soup.find("img", src=re.compile(r"/DefaultCaptcha/Generate\?t="))
            if not ci:
                raise RuntimeError("cap img missing")

            cb, cc = _cap(s, ci["src"], _b + "/")

            g = _solve(image_bytes=cb, mime=_mi(cc))
            if not g:
                print("   ⚠️  Solver empty, retry")
                time.sleep(1)
                continue

            print(f"   🎯 Using: {g}")

            r2 = _sub(s, tok, dbrn, dob_iso, ct, g)
            html = r2.text

            if _bad(html):
                print("   ❌ Wrong, retry")
                last = "wrong"
                time.sleep(1)
                continue

            print("   ✅ Page received")
            return Response(_rw(html), mimetype="text/html")

        except Exception as e:
            last = e
            print(f"   ⚠️  Attempt {att}: {e}")
            time.sleep(1)

    return Response(f'''
    <html><body style="font-family:Arial;padding:40px;text-align:center;">
    <h2>❌ Failed after {_mx} attempts</h2>
    <p>Last: {last}</p>
    <p><a href="/">← Back</a></p>
    </body></html>''', status=500, mimetype="text/html")


# =========================================================
#  🌐  PROXY
# =========================================================

@app.route("/proxy/", defaults={"subpath": ""})
@app.route("/proxy/<path:subpath>", methods=["GET", "POST"])
def proxy(subpath):
    target = _b + "/" + subpath
    if request.query_string:
        target += "?" + request.query_string.decode()

    fwd = {
        "user-agent": _h1["user-agent"],
        "accept": request.headers.get("accept", "*/*"),
        "accept-language": _h1["accept-language"],
        "referer": _b + "/",
    }

    try:
        if request.method == "POST":
            r = requests.post(target, data=request.get_data(), headers=fwd,
                              timeout=30, allow_redirects=False)
        else:
            r = requests.get(target, headers=fwd, timeout=30, allow_redirects=False)
    except Exception as e:
        return f"Proxy err: {e}", 502

    if r.status_code in (301, 302, 303, 307, 308):
        loc = r.headers.get("Location", "")
        if "everify.bdris.gov.bd" in loc:
            loc = loc.replace("https://everify.bdris.gov.bd", "/proxy")
        return Response("", status=r.status_code, headers={"Location": loc})

    c = r.headers.get("Content-Type", "application/octet-stream")
    if "text/html" in c:
        return Response(_rw(r.text), status=r.status_code, mimetype="text/html")
    if "text/css" in c:
        css = re.sub(r'url\((["\']?)(/[^)"\']+)\1\)', r'url(\1/proxy\2\1)', r.text)
        return Response(css, status=r.status_code, mimetype="text/css")
    return Response(r.content, status=r.status_code, content_type=c)


# =========================================================
#  🏁  MAIN
# =========================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Running | P1 keys: {len(_l1)} | P2 keys: {len(_l2)}")
    app.run(host="0.0.0.0", port=port, debug=False)

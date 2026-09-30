import re
import os
import time
import uuid
import base64
import mimetypes
import requests
from datetime import datetime
from flask import Flask, request, Response
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# =========================================================
#  📥  LOAD .env
# =========================================================

load_dotenv()


def _load_keys(var_name):
    """Comma-separated keys load kore .env theke."""
    raw = os.environ.get(var_name, "").strip()
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]


app = Flask(__name__)

# =========================================================
#  ⚙️  GROQ CONFIG
# =========================================================

GROQ_API_KEYS = _load_keys("GROQ_API_KEYS")

GROQ_MODEL = "qwen/qwen3.8-27b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_TIMEOUT = 60
GROQ_RETRY_DELAY = 1

# =========================================================
#  🌟  GEMINI CONFIG
# =========================================================

GEMINI_API_KEYS = _load_keys("GEMINI_API_KEYS")

GEMINI_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
]

GEMINI_TIMEOUT = 20

# =========================================================
#  🔄  COMMON
# =========================================================

MAX_CAPTCHA_ATTEMPTS = 5

PROMPT = (
    "Read the math expression from this image. "
    "Solve it. "
    "Reply with ONLY the final answer as a number. "
    "No explanation. No text. No extra words. Just the number."
)

# =========================================================
#  🌐  BDRIS CONFIG
# =========================================================

BASE = "https://everify.bdris.gov.bd"

HEADERS = {
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

POST_HEADERS = {
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

def guess_mime(path_or_ct):
    s = (path_or_ct or "").lower()
    if "png" in s: return "image/png"
    if "jpeg" in s or "jpg" in s: return "image/jpeg"
    if "webp" in s: return "image/webp"
    if "gif" in s: return "image/gif"
    if "bmp" in s: return "image/bmp"
    return "image/jpeg"


def is_placeholder(key, markers=("key2_here", "key3_here", "key4_here",
                                  "your_key", "xxxx", "YOUR_SECOND",
                                  "YOUR_THIRD")):
    if not key:
        return True
    return any(m.lower() in key.lower() for m in markers)


def extract_number(text):
    if not text:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return m.group(0) if m else None


# =========================================================
#  🚀  GROQ CALL
# =========================================================

def call_groq(api_key, model, prompt, b64_image, mime):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{b64_image}"}},
            ],
        }],
        "temperature": 0,
        "max_completion_tokens": 50,
    }
    r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=GROQ_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"Groq HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        raise RuntimeError(f"Groq bad response: {data}")


def solve_groq(b64_image, mime, prompt=PROMPT):
    valid_keys = [k for k in GROQ_API_KEYS if not is_placeholder(k)]
    if not valid_keys:
        return None
    last_error = None
    for idx, key in enumerate(valid_keys, 1):
        try:
            print(f"   🔁 Groq [{idx}/{len(valid_keys)}] model={GROQ_MODEL} key=...{key[-6:]}")
            raw = call_groq(key, GROQ_MODEL, prompt, b64_image, mime)
            num = extract_number(raw)
            if num:
                print(f"   ✅ Groq answer: {num}")
                return num
            raise RuntimeError(f"No number in: {raw!r}")
        except Exception as e:
            last_error = e
            print(f"   ⚠️  Groq key #{idx} failed: {e}")
            time.sleep(GROQ_RETRY_DELAY)
    print(f"   ❌ All Groq keys failed. Last: {last_error}")
    return None


# =========================================================
#  🌟  GEMINI CALL
# =========================================================

def call_gemini(api_key, model, prompt, b64_image, mime):
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent"
    )
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": b64_image}},
            ]
        }],
        "generationConfig": {"temperature": 0.0},
    }
    r = requests.post(url, headers=headers, json=payload, timeout=GEMINI_TIMEOUT)
    if r.status_code == 200:
        data = r.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise RuntimeError(f"Gemini bad response: {data}")
    if r.status_code in (400, 403, 429):
        raise PermissionError(f"Gemini key dead (HTTP {r.status_code}): {r.text[:150]}")
    raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:150]}")


def solve_gemini(b64_image, mime, prompt=PROMPT):
    valid_keys = [k for k in GEMINI_API_KEYS if not is_placeholder(k)]
    if not valid_keys:
        return None

    for api_key in valid_keys:
        for model in GEMINI_MODELS:
            try:
                print(f"   🌟 Gemini key=...{api_key[-6:]} model={model}")
                raw = call_gemini(api_key, model, prompt, b64_image, mime)
                num = extract_number(raw)
                if num:
                    print(f"   ✅ Gemini answer: {num}")
                    return num
                print(f"   ⚠️  No number in Gemini response: {raw!r}")
            except PermissionError as e:
                print(f"   ⚠️  {e}")
                break
            except Exception as e:
                print(f"   ⚠️  Gemini error: {e}")
                time.sleep(1)
                continue

    print("   ❌ All Gemini keys/models failed")
    return None


# =========================================================
#  🧠  UNIFIED SOLVER (Groq → Gemini)
# =========================================================

def solve(b64_image=None, mime=None, image_path=None, image_bytes=None, prompt=PROMPT):
    if image_bytes is not None:
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        if not mime:
            mime = "image/gif"
    elif image_path is not None and b64_image is None:
        if not os.path.exists(image_path):
            print(f"❌ File paoa jayni: {image_path}")
            return None
        with open(image_path, "rb") as f:
            b64_image = base64.b64encode(f.read()).decode("utf-8")
        if not mime:
            mt, _ = mimetypes.guess_type(image_path)
            mime = mt or "image/jpeg"

    if not b64_image:
        print("❌ No image provided")
        return None
    if not mime:
        mime = "image/jpeg"

    print("   ▶️  Trying Groq...")
    ans = solve_groq(b64_image, mime, prompt)
    if ans:
        return ans

    print("   ▶️  Falling back to Gemini...")
    ans = solve_gemini(b64_image, mime, prompt)
    if ans:
        return ans

    print("❌ Both providers failed")
    return None


# =========================================================
#  🌐  BDRIS HELPERS
# =========================================================

def _extract_form(soup):
    token_input = soup.find("input", {"name": "__RequestVerificationToken"})
    if not token_input:
        return None, None
    token = token_input.get("value")
    captcha_img = soup.find("img", src=re.compile(r"/DefaultCaptcha/Generate\?t="))
    if not captcha_img:
        return token, None
    m = re.search(r"t=([^&]+)", captcha_img["src"])
    if not m:
        return token, None
    return token, m.group(1)


def _fetch_captcha_image(session, captcha_src, referer):
    cap_url = BASE + captcha_src if captcha_src.startswith("/") else captcha_src
    r = session.get(
        cap_url,
        headers={
            "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "referer": referer,
        },
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Captcha fetch HTTP {r.status_code}")
    return r.content, r.headers.get("Content-Type", "image/gif")


def _submit_verification(session, token, dbrn, dob, captcha_t, captcha_input):
    files = {
        "__RequestVerificationToken": (None, token),
        "UBRN": (None, dbrn),
        "BirthDate": (None, dob),
        "CaptchaDeText": (None, captcha_t),
        "CaptchaInputText": (None, captcha_input),
    }
    return session.post(
        BASE + "/UBRNVerification/Search",
        files=files,
        headers=POST_HEADERS,
        timeout=30,
    )


def _is_captcha_wrong(html):
    low = html.lower()
    has_captcha_img = "/defaultcaptcha/generate" in low
    has_error = any(
        m in low for m in ["captcha", "invalid", "incorrect", "wrong", "ভুল", "সঠিকভাবে"]
    )
    return has_captcha_img and has_error


# =========================================================
#  🔥  HTML REWRITE (CSS/image via /proxy)
# =========================================================

def _rewrite_html_for_local(html):
    def repl(match):
        attr = match.group(1)
        quote = match.group(2)
        url = match.group(3)
        if url.startswith("/proxy/") or url.startswith("data:") or url.startswith("#"):
            return match.group(0)
        if url.startswith("http://") or url.startswith("https://"):
            if "everify.bdris.gov.bd" in url:
                return f'{attr}={quote}/proxy{url.split("everify.bdris.gov.bd", 1)[1]}{quote}'
            return match.group(0)
        if url.startswith("/"):
            return f'{attr}={quote}/proxy{url}{quote}'
        if url.startswith("./"):
            return f'{attr}={quote}/proxy/{url[2:]}{quote}'
        return f'{attr}={quote}/proxy/{url}{quote}'

    html = re.sub(
        r'(href|src|action)=(["\'])([^"\']+)\2',
        repl, html, flags=re.IGNORECASE,
    )
    html = re.sub(r'<base[^>]*>', '', html, flags=re.IGNORECASE)
    return html


# =========================================================
#  🏠  ROOT ROUTE
# =========================================================

@app.route("/")
def home():
    html = '''<!DOCTYPE html>
<html>
<head>
    <title>BDRIS eVerify Auto Solver</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: Arial, sans-serif; background: #f4f4f4;
               text-align: center; padding: 40px 20px; margin: 0; }
        .box { background: white; padding: 30px; border-radius: 10px;
               display: inline-block; box-shadow: 0 4px 12px rgba(0,0,0,.1);
               max-width: 420px; width: 100%; box-sizing: border-box; }
        h2 { color: #222; margin-top: 0; }
        label { display: block; text-align: left; margin: 12px 0 4px;
                font-size: 14px; color: #444; }
        input { padding: 12px; width: 100%; border: 1px solid #ccc;
                border-radius: 6px; box-sizing: border-box; font-size: 15px; }
        button { margin-top: 18px; padding: 12px 20px; width: 100%;
                 background: #007bff; color: white; border: none;
                 border-radius: 6px; font-size: 16px; cursor: pointer; }
        button:hover { background: #0056b3; }
        .hint { font-size: 12px; color: #888; margin-top: 14px; }
    </style>
</head>
<body>
    <div class="box">
        <h2>🇧🇩 BDRIS eVerify Auto Solver</h2>
        <form method="GET" action="/find">
            <label>UBRN (Birth Registration Number)</label>
            <input type="text" name="dbrn" placeholder="e.g. 20186113154117630" required>

            <label>Date of Birth</label>
            <input type="text" name="dob" placeholder="YYYY-MM-DD or DD-MM-YYYY" required>

            <button type="submit">Verify (Auto CAPTCHA)</button>
        </form>
        <p class="hint">Example: /find?dbrn=20186113154117630&dob=2018-10-12</p>
    </div>
</body>
</html>'''
    return Response(html, mimetype="text/html")


# =========================================================
#  🔍  FIND ROUTE
# =========================================================

@app.route("/find")
def find():
    dbrn = (
        request.args.get("dbrn")
        or request.args.get("ubrn")
        or request.args.get("reg")
        or request.args.get("birth_reg")
        or request.args.get("brn")
    )
    dob = (
        request.args.get("dob")
        or request.args.get("birthdate")
        or request.args.get("birth_date")
        or request.args.get("date")
    )

    if not dbrn or not dob:
        missing = []
        if not dbrn: missing.append("dbrn")
        if not dob:  missing.append("dob")
        return Response(f'''
        <html><body style="font-family:Arial;padding:40px;text-align:center;">
        <h2>⚠️ Missing Parameter: {", ".join(missing)}</h2>
        <p>Use: <code>/find?dbrn=...&dob=YYYY-MM-DD</code></p>
        <p><a href="/">← Back</a></p>
        </body></html>''', status=400, mimetype="text/html")

    dt = None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y",
                "%Y.%m.%d", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(dob.strip(), fmt)
            break
        except ValueError:
            continue

    if not dt:
        return Response(f'''
        <html><body style="font-family:Arial;padding:40px;text-align:center;">
        <h2>⚠️ Invalid DOB: {dob}</h2>
        <p>Supported: YYYY-MM-DD, DD-MM-YYYY, YYYY/MM/DD, DD/MM/YYYY, YYYY.MM.DD</p>
        <p><a href="/">← Back</a></p>
        </body></html>''', status=400, mimetype="text/html")

    dob_iso = dt.strftime("%Y-%m-%d")
    dbrn = dbrn.strip()

    last_error = None

    for attempt in range(1, MAX_CAPTCHA_ATTEMPTS + 1):
        try:
            print(f"\n🔁 [Attempt {attempt}/{MAX_CAPTCHA_ATTEMPTS}] dbrn={dbrn} dob={dob_iso}")

            s = requests.Session()
            s.headers.update(HEADERS)

            r = s.get(BASE + "/", timeout=30)
            if r.status_code != 200:
                raise RuntimeError(f"Home page HTTP {r.status_code}")

            soup = BeautifulSoup(r.text, "html.parser")
            token, captcha_t = _extract_form(soup)
            if not token or not captcha_t:
                raise RuntimeError("Could not extract token/captcha_t")

            captcha_img = soup.find("img", src=re.compile(r"/DefaultCaptcha/Generate\?t="))
            if not captcha_img:
                raise RuntimeError("Captcha img not found")

            cap_bytes, cap_ct = _fetch_captcha_image(s, captcha_img["src"], BASE + "/")

            guess = solve(image_bytes=cap_bytes, mime=guess_mime(cap_ct))
            if not guess:
                print("   ⚠️  Solver returned empty, retrying...")
                time.sleep(1)
                continue

            print(f"   🎯 Using CAPTCHA: {guess}")

            r2 = _submit_verification(s, token, dbrn, dob_iso, captcha_t, guess)
            html = r2.text

            if _is_captcha_wrong(html):
                print("   ❌ CAPTCHA wrong, retrying with fresh one...")
                last_error = "Captcha wrong"
                time.sleep(1)
                continue

            print("   ✅ Verification page received")
            html = _rewrite_html_for_local(html)
            return Response(html, mimetype="text/html")

        except Exception as e:
            last_error = e
            print(f"   ⚠️  Attempt {attempt} error: {e}")
            time.sleep(1)

    return Response(f'''
    <html><body style="font-family:Arial;padding:40px;text-align:center;">
    <h2>❌ Failed after {MAX_CAPTCHA_ATTEMPTS} attempts</h2>
    <p>Last error: {last_error}</p>
    <p>DBRN: {dbrn} | DOB: {dob_iso}</p>
    <p><a href="/">← Try again</a></p>
    </body></html>''', status=500, mimetype="text/html")


# =========================================================
#  🌐  PROXY (CSS/JS/image)
# =========================================================

@app.route("/proxy/", defaults={"subpath": ""})
@app.route("/proxy/<path:subpath>", methods=["GET", "POST"])
def proxy(subpath):
    target = BASE + "/" + subpath
    if request.query_string:
        target += "?" + request.query_string.decode()

    fwd_headers = {
        "user-agent": HEADERS["user-agent"],
        "accept": request.headers.get("accept", "*/*"),
        "accept-language": HEADERS["accept-language"],
        "referer": BASE + "/",
    }

    try:
        if request.method == "POST":
            r = requests.post(
                target, data=request.get_data(),
                headers=fwd_headers, timeout=30, allow_redirects=False,
            )
        else:
            r = requests.get(
                target, headers=fwd_headers,
                timeout=30, allow_redirects=False,
            )
    except Exception as e:
        return f"Proxy error: {e}", 502

    if r.status_code in (301, 302, 303, 307, 308):
        loc = r.headers.get("Location", "")
        if "everify.bdris.gov.bd" in loc:
            loc = loc.replace("https://everify.bdris.gov.bd", "/proxy")
        return Response("", status=r.status_code, headers={"Location": loc})

    content_type = r.headers.get("Content-Type", "application/octet-stream")

    if "text/html" in content_type:
        html = _rewrite_html_for_local(r.text)
        return Response(html, status=r.status_code, mimetype="text/html")

    if "text/css" in content_type:
        css = re.sub(
            r'url\((["\']?)(/[^)"\']+)\1\)',
            r'url(\1/proxy\2\1)', r.text,
        )
        return Response(css, status=r.status_code, mimetype="text/css")

    return Response(r.content, status=r.status_code, content_type=content_type)


# =========================================================
#  🏁  MAIN
# =========================================================

if __name__ == "__main__":
    gk = len([k for k in GROQ_API_KEYS if not is_placeholder(k)])
    gmk = len([k for k in GEMINI_API_KEYS if not is_placeholder(k)])
    print("🚀 BDRIS eVerify Auto-Solver running")
    print(f"   Groq model:   {GROQ_MODEL} | keys: {gk}")
    print(f"   Gemini models: {GEMINI_MODELS} | keys: {gmk}")
    print(f"   Max attempts: {MAX_CAPTCHA_ATTEMPTS}")
    print(f"   Routes: /  /find?dbrn=...&dob=...  /proxy/...")
    app.run(host="0.0.0.0", port=5000, debug=False)

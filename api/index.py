from flask import Flask, request, jsonify, Response
import json
import os
import re
import time
import base64
import requests
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from bs4 import BeautifulSoup

app = Flask(__name__)

# =========================================================
#  CONFIG
# =========================================================

BASE_URL = "https://lsg-land-owner-stage.land.gov.bd"
API_URL = BASE_URL + "/check/user/nid/verification"
SECRET_KEY = "lsg56xy14yu45dfgy124dfe12dr52fgd"
ACCOUNTS_FILE = os.path.join(os.path.dirname(__file__), "accounts.json")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

NID_BASE = "https://services.nidw.gov.bd/nid-pub"
NID_UA = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Mobile Safari/537.36"
)
OCR_API_KEY = "K87822842088957"

# =========================================================
#  DISTRICT → DIVISION MAP
# =========================================================

DISTRICT_TO_DIVISION = {
    "ঢাকা": "ঢাকা", "গাজীপুর": "ঢাকা", "নারায়ণগঞ্জ": "ঢাকা", "মানিকগঞ্জ": "ঢাকা",
    "মুন্সীগঞ্জ": "ঢাকা", "নরসিংদী": "ঢাকা", "টাঙ্গাইল": "ঢাকা", "ফরিদপুর": "ঢাকা",
    "গোপালগঞ্জ": "ঢাকা", "মাদারীপুর": "ঢাকা", "শরীয়তপুর": "ঢাকা", "রাজবাড়ী": "ঢাকা",
    "চট্টগ্রাম": "চট্টগ্রাম", "কুমিল্লা": "চট্টগ্রাম", "ফেনী": "চট্টগ্রাম",
    "ব্রাহ্মণবাড়িয়া": "চট্টগ্রাম", "রাঙ্গামাটি": "চট্টগ্রাম", "নোয়াখালী": "চট্টগ্রাম",
    "চাঁদপুর": "চট্টগ্রাম", "লক্ষ্মীপুর": "চট্টগ্রাম", "কক্সবাজার": "চট্টগ্রাম",
    "খাগড়াছড়ি": "চট্টগ্রাম", "বান্দরবান": "চট্টগ্রাম",
    "রাজশাহী": "রাজশাহী", "নাটোর": "রাজশাহী", "নওগাঁ": "রাজশাহী",
    "চাঁপাইনবাবগঞ্জ": "রাজশাহী", "পাবনা": "রাজশাহী", "সিরাজগঞ্জ": "রাজশাহী",
    "বগুড়া": "রাজশাহী", "জয়পুরহাট": "রাজশাহী",
    "খুলনা": "খুলনা", "বাগেরহাট": "খুলনা", "সাতক্ষীরা": "খুলনা", "যশোর": "খুলনা",
    "চুয়াডাঙ্গা": "খুলনা", "কুষ্টিয়া": "খুলনা", "মেহেরপুর": "খুলনা",
    "মাগুরা": "খুলনা", "ঝিনাইদহ": "খুলনা", "নড়াইল": "খুলনা",
    "বরিশাল": "বরিশাল", "পটুয়াখালী": "বরিশাল", "ভোলা": "বরিশাল",
    "পিরোজপুর": "বরিশাল", "বরগুনা": "বরিশাল", "ঝালকাঠি": "বরিশাল",
    "সিলেট": "সিলেট", "মৌলভীবাজার": "সিলেট", "হবিগঞ্জ": "সিলেট", "সুনামগঞ্জ": "সিলেট",
    "রংপুর": "রংপুর", "দিনাজপুর": "রংপুর", "গাইবান্ধা": "রংপুর", "কুড়িগ্রাম": "রংপুর",
    "নীলফামারী": "রংপুর", "লালমনিরহাট": "রংপুর", "ঠাকুরগাঁও": "রংপুর", "পঞ্চগড়": "রংপুর",
    "ময়মনসিংহ": "ময়মনসিংহ", "নেত্রকোণা": "ময়মনসিংহ", "জামালপুর": "ময়মনসিংহ", "শেরপুর": "ময়মনসিংহ",
}

# =========================================================
#  AES ENCRYPTION (equivalent to PHP openssl_encrypt aes-256-cbc)
# =========================================================

def encrypt_data(plaintext: str, secret_key: str) -> dict:
    """
    PHP er encrypt_data equivalent.
    Returns {'iv': base64, 'encryptedData': base64}
    """
    key_bytes = secret_key.encode("utf-8")[:32].ljust(32, b"\0")
    iv = os.urandom(16)

    cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
    padded = pad(plaintext.encode("utf-8"), AES.block_size)
    encrypted = cipher.encrypt(padded)

    return {
        "iv": base64.b64encode(iv).decode("utf-8"),
        "encryptedData": base64.b64encode(encrypted).decode("utf-8"),
    }

# =========================================================
#  RELIGION / GENDER DETECTION (from Helper.php)
# =========================================================

MALE_ISLAMIC = [
    "md","mohammad","muhammad","ahmed","ahmad","ali","hasan","hussain","hassan","hussein",
    "abdullah","abdul","rahman","abdulrahman","abdulaziz","omar","umar","osman","usman",
    "ibrahim","ishaq","yasir","yusuf","yamin","zakaria","sulaiman","dawood","musa","harun","yunus",
    "ayub","idris","ilyas","ismail","yaqub","shuaib","saleh","hud","taha","jalal","kamal",
    "karim","rahim","jabbar","hafiz","qari","imam","sheikh","maulana","khalid","khalil",
    "rashid","salim","salman","talha","zubair","farooq","farhan","fahad","saad","hamza",
    "imran","irfan","junaid","kashif","nadeem","nasir","owais","qasim","raheel","raza",
    "rizwan","shahid","shakeel","shams","sharif","shoaib","sohail","sultan","tahir",
    "wajid","zahid","zia","zulfiqar","hafeez","mateen","mustafa","murad","najeeb",
    "noor","nur","parvez","qadeer","rafiq","rauf","rehman","sajjad","sarwar","subhan",
    "usama","waleed","waseem","younus","zafar","zaheer","zain","zeshan",
]

FEMALE_ISLAMIC = [
    "mst","fatima","ayesha","aisha","zahra","khadija","hafsa","sumaiya","asia","asiya",
    "rabia","saira","zainab","maryam","mariam","kulsum","ruqayya","umm","bibi","begum",
    "afreen","alina","amina","aneesa","areeba","asma","atiya","azra",
    "bushra","dania","fariha","farzana","fauzia","haleema","halima","hana","hareem",
    "hasina","humaira","iqra","javeria","kaniz","karima","laila","lubna","madiha",
    "mahnoor","malaika","marwa","maya","maymuna","mehnaz","muneeba","nadia","nafisa",
    "naila","najma","nazia","nida","nimra","parveen","rida","roshni","rubina",
    "saba","sadia","safa","safia","saima","sajida","saleha","samina","sana","sania",
    "sara","shabana","shagufta","shazia","sidra","sobia","sofia","tabinda","tahira",
    "taiba","tasneem","tuba","umaima","uzma","warda","yasmeen","yusra","zahida",
    "zara","zubaida","zulekha","zumra",
]

ISLAMIC_PREFIXES = ["md", "mohammad", "muhammad", "mst"]


def detect_religion_gender(name: str) -> dict:
    name_lower = (name or "").lower()

    is_islamic = any(p in name_lower for p in MALE_ISLAMIC + FEMALE_ISLAMIC + ISLAMIC_PREFIXES)

    gender = "Unknown"
    for p in MALE_ISLAMIC:
        if p in name_lower:
            gender = "Male"
            break
    if gender == "Unknown":
        for p in FEMALE_ISLAMIC:
            if p in name_lower:
                gender = "Female"
                break

    return {
        "religion": "ইসলাম" if is_islamic else "N/A",
        "religionEn": "Islam" if is_islamic else "N/A",
        "gender": "N/A" if gender == "Unknown" else ("পুরুষ" if gender == "Male" else "নারী"),
        "genderEn": "N/A" if gender == "Unknown" else gender,
    }

# =========================================================
#  HTTP HELPERS
# =========================================================

def http_request(method, url, headers=None, data=None, cookies=None, timeout=30):
    try:
        if method.upper() == "GET":
            r = requests.get(url, headers=headers, cookies=cookies,
                             timeout=timeout, verify=False, allow_redirects=True)
        else:
            r = requests.post(url, headers=headers, data=data, cookies=cookies,
                              timeout=timeout, verify=False, allow_redirects=False)
        return r
    except Exception as e:
        return None

# =========================================================
#  NID LOOKUP CLASS
# =========================================================

class NIDLookup:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": NID_UA})
        self.csrf_token = ""

    def get_csrf_token(self):
        try:
            r = self.session.get(f"{NID_BASE}/card-status", timeout=30, verify=False)
            m = re.search(r'name="_csrf"\s+content="([^"]+)"', r.text)
            self.csrf_token = m.group(1) if m else ""
            return self.csrf_token
        except Exception as e:
            print(f"CSRF error: {e}")
            return ""

    def download_captcha(self):
        try:
            url = f"{NID_BASE}/captcha/?t={int(time.time())}"
            headers = {
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                "Referer": f"{NID_BASE}/card-status",
            }
            r = self.session.get(url, headers=headers, timeout=30, verify=False)
            if r.status_code != 200 or not r.content:
                return None
            return r.content
        except Exception as e:
            print(f"Captcha download error: {e}")
            return None

    def solve_captcha(self, image_bytes):
        try:
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            data = {
                "apikey": OCR_API_KEY,
                "language": "eng",
                "base64Image": f"data:image/png;base64,{b64}",
                "OCREngine": 3,
                "scale": True,
            }
            r = requests.post("https://api.ocr.space/parse/image",
                              data=data, timeout=30)
            j = r.json()
            text = ""
            if "ParsedResults" in j and j["ParsedResults"]:
                text = j["ParsedResults"][0].get("ParsedText", "")
            return re.sub(r"[^a-zA-Z0-9]", "", text.strip())
        except Exception as e:
            print(f"OCR error: {e}")
            return ""

    def lookup_nid(self, nid, day, month, year):
        if not self.csrf_token:
            self.get_csrf_token()
        if not self.csrf_token:
            return {"success": False, "message": "CSRF token not found"}

        img = self.download_captcha()
        if not img:
            return {"success": False, "message": "Captcha download failed"}

        captcha_text = self.solve_captcha(img)
        if len(captcha_text) < 3:
            return {"success": False, "message": "ক্যাপচা সলভ ব্যর্থ!"}

        try:
            post_data = {
                "nid": nid,
                "day": day,
                "month": month,
                "year": year,
                "captcha": captcha_text,
            }
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-CSRF-TOKEN": self.csrf_token,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/plain, */*",
                "Referer": f"{NID_BASE}/card-status",
            }
            r = self.session.post(f"{NID_BASE}/card-status/validate",
                                  data=post_data, headers=headers,
                                  timeout=30, verify=False)
            result = r.json()
        except Exception as e:
            return {"success": False, "message": f"Validation failed: {e}"}

        if result.get("status") == "SUCCESS" and "success" in result and "template" in result["success"]:
            return self.get_card_details(result["success"]["template"], nid, day, month, year)

        return {"success": False, "message": result.get("error", "অজানা এরর!")}

    def get_card_details(self, template_url, nid, day, month, year):
        try:
            url = f"{NID_BASE}{template_url}?t={int(time.time())}"
            headers = {
                "X-CSRF-TOKEN": self.csrf_token,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "text/html, */*",
                "Referer": f"{NID_BASE}/card-status",
            }
            r = self.session.get(url, headers=headers, timeout=30, verify=False)
            return self.extract_data(r.text, nid, day, month, year)
        except Exception as e:
            return {"success": False, "message": f"Card fetch failed: {e}"}

    def extract_data(self, html, nid, day, month, year):
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")

        data = {
            "status": "", "box_id": "", "comp_id": "",
            "district": "", "upozila": "",
            "voter_area": "", "contact_address": "",
        }

        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 7:
                data["status"] = cells[0].get_text(strip=True)
                data["box_id"] = cells[1].get_text(strip=True)
                data["comp_id"] = cells[2].get_text(strip=True)
                data["district"] = cells[3].get_text(strip=True)
                data["upozila"] = cells[4].get_text(strip=True)
                data["voter_area"] = cells[5].get_text(strip=True)
                data["contact_address"] = cells[6].get_text(strip=True)
                break

        for k in data:
            data[k] = data[k].replace("N/A", "").replace("Complete", "").strip()

        village = data["voter_area"]
        if village:
            m = re.search(r"গ্রাম/রাস্তা\s*:?\s*([^,]+)", village)
            if m:
                village = m.group(1).strip()
            else:
                village = re.sub(r"বাসা/হোল্ডিং\s*:?\s*[^,]+,?\s*", "", village)
                village = re.sub(r"মৌজা/মহল্লা\s*:?\s*[^,]+,?\s*", "", village)
                village = village.strip()

        division = DISTRICT_TO_DIVISION.get(data["district"].strip(), "")

        address = f"বাসা/হোল্ডিং: , গ্রাম/রাস্তা: {village}"
        if data["upozila"]:
            address += f", উপজেলা: {data['upozila']}"
        if data["district"]:
            address += f", জেলা: {data['district']}"
        if division:
            address += f", বিভাগ: {division}"

        dob_formatted = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        day_of_week = self.get_day_of_week(year, month, day)
        age = self.calculate_age(year, month, day)

        return {
            "success": True,
            "message": "NID information retrieved successfully",
            "data": {
                "nid": nid,
                "dob": dob_formatted,
                "day_of_week": day_of_week,
                "age": age,
                "village": village,
                "upozila": data["upozila"],
                "district": data["district"],
                "division": division,
                "address": address,
                "voter_area": data["voter_area"],
            },
        }

    def get_day_of_week(self, year, month, day):
        try:
            dt = datetime(int(year), int(month), int(day))
            bangla_days = ["রবিবার", "সোমবার", "মঙ্গলবার", "বুধবার", "বৃহস্পতিবার", "শুক্রবার", "শনিবার"]
            return bangla_days[dt.weekday() + 1 if dt.weekday() < 6 else 0]
        except Exception:
            return ""

    def calculate_age(self, year, month, day):
        try:
            birth = datetime(int(year), int(month), int(day))
            today = datetime.now()
            years = today.year - birth.year
            months = today.month - birth.month
            days = today.day - birth.day
            if days < 0:
                months -= 1
                days += 30
            if months < 0:
                years -= 1
                months += 12
            bangla = ["০", "১", "২", "৩", "৪", "৫", "৬", "৭", "৮", "৯"]
            y = "".join(bangla[int(c)] for c in str(years))
            m = "".join(bangla[int(c)] for c in str(months))
            d = "".join(bangla[int(c)] for c in str(days))
            return f"{y} বছর {m} মাস {d} দিন"
        except Exception:
            return ""

# =========================================================
#  ACCOUNTS
# =========================================================

def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def save_accounts(accounts):
    try:
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(accounts, f, ensure_ascii=False, indent=4)
    except Exception:
        pass


def update_account_attempt(username):
    accounts = load_accounts()
    for acc in accounts:
        if acc.get("username") == username:
            acc["attempt_increased"] = (acc.get("attempt_increased") or 0) + 1
            acc["attempt_increased_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            break
    save_accounts(accounts)


def reset_daily_attempts():
    accounts = load_accounts()
    today = datetime.now().strftime("%Y-%m-%d")
    modified = False
    for acc in accounts:
        if "attempt_increased_at" in acc:
            try:
                attempt_date = acc["attempt_increased_at"][:10]
            except Exception:
                attempt_date = ""
            if attempt_date != today:
                acc["attempt_increased"] = 0
                acc["attempt_increased_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                modified = True
    if modified:
        save_accounts(accounts)

# =========================================================
#  LOGIN + API CALL
# =========================================================

def login_with_account(username, password):
    login_url = f"{BASE_URL}/login"
    headers = {"User-Agent": USER_AGENT}

    try:
        r = requests.get(login_url, headers=headers, timeout=15, verify=False)
    except Exception:
        return None

    m = re.search(r'<meta name="csrf-token" content="([^"]+)"', r.text, re.IGNORECASE)
    csrf_token = m.group(1) if m else ""
    if not csrf_token:
        return None

    cookies = r.cookies.get_dict()

    post_data = {
        "_token": csrf_token,
        "userOptionType": "Citizen",
        "identity": "email",
        "username": username,
        "password": password,
        "qr-container-token": "",
    }

    try:
        r2 = requests.post(login_url, data=post_data, headers=headers,
                           cookies=cookies, timeout=15, verify=False,
                           allow_redirects=False)
    except Exception:
        return None

    if r2.status_code != 302:
        return None

    final_cookies = dict(cookies)
    final_cookies.update(r2.cookies.get_dict())
    if "lsg_session" not in final_cookies:
        return None

    try:
        r3 = requests.get(f"{BASE_URL}/landing",
                          headers=headers,
                          cookies={"lsg_session": final_cookies["lsg_session"]},
                          timeout=15, verify=False)
    except Exception:
        return None

    m2 = re.search(r'<meta name="csrf-token" content="([^"]+)"', r3.text, re.IGNORECASE)
    landing_csrf = m2.group(1) if m2 else ""
    if not landing_csrf:
        return None

    return {
        "csrf_token": landing_csrf,
        "lsg_session": final_cookies["lsg_session"],
    }


def call_verification_api(nid, dob, session_data):
    plaintext = json.dumps({"dob": dob, "nid": nid})
    encrypted = encrypt_data(plaintext, SECRET_KEY)
    post_data = {"tokenized_en_data": json.dumps(encrypted)}

    headers = {
        "User-Agent": USER_AGENT,
        "Cookie": f"lsg_session={session_data['lsg_session']}",
        "x-csrf-token": session_data["csrf_token"],
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        r = requests.post(API_URL, data=post_data, headers=headers,
                          timeout=20, verify=False)
        return r.json()
    except Exception as e:
        print(f"API call error: {e}")
        return False

# =========================================================
#  ROUTES
# =========================================================

@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "endpoints": {
            "/nid": "?num=XXXX&dob=YYYY-MM-DD"
        }
    })


@app.route("/nid")
def nid_endpoint():
    nid = request.args.get("num") or request.args.get("nid") or ""
    dob = request.args.get("dob") or ""

    if not nid or not dob:
        return jsonify({
            "code": 400,
            "success": False,
            "message": "num and dob required",
            "usage": "?num=7314475786&dob=1991-11-07"
        }), 400

    # Parse DOB
    parts = dob.split("-")
    if len(parts) != 3:
        return jsonify({
            "code": 400,
            "success": False,
            "message": "Invalid date format. Use YYYY-MM-DD"
        }), 400

    year, month, day = parts
    try:
        datetime(int(year), int(month), int(day))
    except ValueError:
        return jsonify({
            "code": 400,
            "success": False,
            "message": "Invalid date"
        }), 400

    reset_daily_attempts()

    # NID lookup
    try:
        lookup = NIDLookup()
        address_result = lookup.lookup_nid(nid, day, month, year)
    except Exception as e:
        address_result = {"success": False, "message": str(e), "data": {}}

    # Accounts
    accounts = load_accounts()
    active_accounts = [a for a in accounts if (a.get("attempt_increased") or 0) < 10]

    if not active_accounts:
        return jsonify({
            "code": 429,
            "success": False,
            "message": "All accounts reached daily limit"
        }), 429

    response_data = None
    used_account = None
    last_error = None

    for account in active_accounts:
        username = account.get("username", "")
        password = account.get("password", "")

        session_data = login_with_account(username, password)
        if not session_data:
            last_error = f"Login failed for: {username}"
            continue

        api_response = call_verification_api(nid, dob, session_data)
        if api_response is False:
            last_error = f"API call failed for: {username}"
            continue

        # Daily limit reached detection
        if (isinstance(api_response, dict)
                and str(api_response.get("success")) == "false"
                and "data" in api_response
                and "সর্বোচ্চ সংখ্যকবার" in str(api_response.get("data", ""))):
            all_acc = load_accounts()
            for a in all_acc:
                if a.get("username") == username:
                    a["attempt_increased"] = 10
                    break
            save_accounts(all_acc)
            last_error = f"Daily limit reached for: {username}"
            continue

        response_data = api_response
        used_account = username
        break

    # Final response
    if response_data and str(response_data.get("success")) == "true":
        if used_account:
            update_account_attempt(used_account)

        citizen = response_data.get("citizen_info", {})
        name_en = citizen.get("name_en", "")
        religion_gender = detect_religion_gender(name_en)

        raw_voter_area = (address_result.get("data") or {}).get("voter_area", "")
        village_name = raw_voter_area
        if raw_voter_area:
            m = re.search(r"গ্রাম/রাস্তা\s*:?\s*([^,]+)", raw_voter_area)
            if m:
                village_name = m.group(1).strip()
            else:
                village_name = raw_voter_area.split(",")[0].strip()

        final_data = {
            "name": citizen.get("name", ""),
            "nameEn": name_en,
            "nationalId": nid,
            "dateOfBirth": dob,
            "pin": f"{year}{nid}",
            "old_nid": nid,
            "voter_area": village_name,
            "birth_place": (address_result.get("data") or {}).get("district", ""),
            "fatherName": citizen.get("father_name", ""),
            "motherName": citizen.get("mother_name", ""),
            "gender": religion_gender["gender"],
            "genderEn": religion_gender["genderEn"],
            "religion": religion_gender["religion"],
            "religionEn": religion_gender["religionEn"],
        }

        if address_result.get("success"):
            d = address_result.get("data", {})
            final_data["village"] = d.get("village", "")
            final_data["upozila"] = d.get("upozila", "")
            final_data["district"] = d.get("district", "")
            final_data["division"] = d.get("division", "")
            final_data["address"] = d.get("address", "")
            final_data["day_of_week"] = d.get("day_of_week", "")
            final_data["age"] = d.get("age", "")

        return jsonify({
            "code": 200,
            "success": True,
            "message": "NID fetched successfully!",
            "data": final_data,
        })

    return jsonify({
        "code": 500,
        "success": False,
        "message": (response_data.get("data") if isinstance(response_data, dict) else None)
                   or last_error
                   or "Verification failed",
        "data": None,
    }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

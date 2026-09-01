from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

API_URL = "https://api.deeptoplay.com/v2/auth/login"

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.deeptoplay.com",
    "Referer": "https://www.deeptoplay.com/",
    "User-Agent": "Mozilla/5.0"
}

PARAMS = {
    "country": "BD",
    "platform": "web",
    "language": "en"
}

@app.route("/send")
def send():
    phone = request.args.get("phone")

    if not phone:
        return jsonify({
            "status": False,
            "message": "Missing phone parameter"
        }), 400

    payload = {
        "number": phone
    }

    try:
        response = requests.post(
            API_URL,
            params=PARAMS,
            headers=HEADERS,
            json=payload,
            timeout=15
        )

        return jsonify({
            "status_code": response.status_code,
            "response": response.json() if "application/json" in response.headers.get("Content-Type", "") else response.text
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

import os
import re
import logging
import traceback
from functools import wraps

from dotenv import load_dotenv
load_dotenv()

import boto3
import bcrypt
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr
from flask import Flask, request, jsonify
from flask_cors import CORS

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "tempo")

CORS(app, origins="*")

# ── AWS config ────────────────────────────────────────────────────────────────
REGION = os.environ.get("AWS_REGION", "us-east-1")

dynamodb  = boto3.resource("dynamodb", region_name=REGION)
login_tbl = dynamodb.Table("Login")
music_tbl = dynamodb.Table("Music")
subs_tbl  = dynamodb.Table("Subscription")

# ── Validation ────────────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r'^[^@]+@[^@]+\.[^@]+$')

def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email))

# ── Image URL helper ──────────────────────────────────────────────────────────
def _image_url(raw_url: str) -> str:
    """Return image URL as stored — iTunes URLs are passed through unchanged."""
    return raw_url or ""

# ═══════════════════════════════════════════════════════════════════════════════
# Auth API
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/login", methods=["POST"])
def api_login():
    data     = request.get_json() or {}
    email    = data.get("email",    "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    if not valid_email(email):
        return jsonify({"error": "Invalid email format"}), 400

    try:
        resp = login_tbl.get_item(Key={"email": email})
    except ClientError as e:
        log.error("DynamoDB login error: %s", e)
        return jsonify({"error": "Database error. Try again."}), 500

    user = resp.get("Item")
    if not user:
        return jsonify({"error": "Email or password is invalid"}), 401

    stored_pw = user.get("password", "")
    try:
        password_ok = bcrypt.checkpw(password.encode("utf-8"), stored_pw.encode("utf-8"))
    except Exception:
        password_ok = (stored_pw == password)   # legacy plaintext fallback

    if not password_ok:
        return jsonify({"error": "Email or password is invalid"}), 401

    return jsonify({"success": True, "email": email, "user_name": user.get("user_name", email)}), 200


@app.route("/api/register", methods=["POST"])
def api_register():
    data      = request.get_json() or {}
    email     = data.get("email",     "").strip()
    user_name = data.get("user_name", "").strip()
    password  = data.get("password",  "").strip()

    if not email or not user_name or not password:
        return jsonify({"error": "All fields are required"}), 400

    if not valid_email(email):
        return jsonify({"error": "Invalid email format"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    try:
        existing = login_tbl.get_item(Key={"email": email})
        if "Item" in existing:
            return jsonify({"error": "Email already registered"}), 409

        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        login_tbl.put_item(Item={
            "email":     email,
            "user_name": user_name,
            "password":  hashed,
        })
        return jsonify({"success": True}), 201

    except ClientError as e:
        log.error("DynamoDB register error: %s", e)
        return jsonify({"error": "Database error: " + e.response["Error"]["Message"]}), 500


@app.route("/api/logout", methods=["POST"])
def api_logout():
    return jsonify({"success": True}), 200


# ═══════════════════════════════════════════════════════════════════════════════
# Music API
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/query", methods=["GET"])
def query_music():
    title  = request.args.get("title",  "").strip()
    artist = request.args.get("artist", "").strip()
    year   = request.args.get("year",   "").strip()
    album  = request.args.get("album",  "").strip()

    if not any([title, artist, year, album]):
        return jsonify({"error": "at_least_one_field_required"}), 400

    year_val = None
    if year:
        try:
            year_val = int(year)
        except ValueError:
            return jsonify({"error": "year must be a number"}), 400

    try:
        if artist and not title and not year and not album:
            # Efficient key-based query on partition key
            result = music_tbl.query(KeyConditionExpression=Key("artist").eq(artist))
            items  = result.get("Items", [])
            while "LastEvaluatedKey" in result:
                result = music_tbl.query(
                    KeyConditionExpression=Key("artist").eq(artist),
                    ExclusiveStartKey=result["LastEvaluatedKey"],
                )
                items.extend(result.get("Items", []))
        else:
            conditions = []
            if title:                conditions.append(Attr("title").eq(title))
            if artist:               conditions.append(Attr("artist").eq(artist))
            if year_val is not None: conditions.append(Attr("year").eq(year_val))
            if album:                conditions.append(Attr("album").eq(album))

            filter_expr = conditions[0]
            for c in conditions[1:]:
                filter_expr = filter_expr & c

            result = music_tbl.scan(FilterExpression=filter_expr)
            items  = result.get("Items", [])
            while "LastEvaluatedKey" in result:
                result = music_tbl.scan(
                    FilterExpression=filter_expr,
                    ExclusiveStartKey=result["LastEvaluatedKey"],
                )
                items.extend(result.get("Items", []))

        for item in items:
            if "image_url" in item:
                item["image_url"] = _image_url(item["image_url"])
            # Normalise legacy img_url field
            if "img_url" in item and "image_url" not in item:
                item["image_url"] = _image_url(item.pop("img_url"))

        return jsonify({"items": items})

    except ClientError as e:
        log.error("DynamoDB query error: %s", e)
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# Subscriptions API
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/subscriptions", methods=["GET"])
def get_subscriptions():
    email = request.args.get("email", "").strip()
    if not email:
        return jsonify({"error": "email required"}), 400
    try:
        result = subs_tbl.query(KeyConditionExpression=Key("emailId").eq(email))
        items  = result.get("Items", [])
        for item in items:
            if "image_url" in item:
                item["image_url"] = _image_url(item["image_url"])
        return jsonify({"items": items})
    except ClientError as e:
        log.error("DynamoDB subscriptions error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/subscribe", methods=["POST"])
def subscribe():
    data      = request.get_json() or {}
    email     = data.get("email",     "").strip()
    artist    = data.get("artist",    "").strip()
    title     = data.get("title",     "").strip()
    album     = data.get("album",     "").strip()
    year      = data.get("year",      "")
    image_url = data.get("image_url", "").strip()

    if not email or not artist or not title:
        return jsonify({"error": "missing_fields"}), 400

    title_album = f"{title}#{album}"

    try:
        subs_tbl.put_item(Item={
            "emailId":     email,
            "title_album": title_album,
            "title":       title,
            "artist":      artist,
            "album":       album,
            "year":        year,
            "image_url":   image_url,
        })
        return jsonify({"message": "subscribed"}), 201
    except ClientError as e:
        log.error("DynamoDB subscribe error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/unsubscribe", methods=["DELETE"])
def unsubscribe():
    data        = request.get_json() or {}
    email       = data.get("email", "").strip()
    title       = data.get("title", "").strip()
    album       = data.get("album", "").strip()
    title_album = f"{title}#{album}"

    if not email or not title:
        return jsonify({"error": "missing_fields"}), 400

    try:
        subs_tbl.delete_item(Key={"emailId": email, "title_album": title_album})
        return jsonify({"message": "unsubscribed"}), 200
    except ClientError as e:
        log.error("DynamoDB unsubscribe error: %s", e)
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# Health check
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


# ── Global error handlers ─────────────────────────────────────────────────────

@app.errorhandler(Exception)
def handle_exception(e):
    log.error("Unhandled exception: %s", traceback.format_exc())
    return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed"}), 405


if __name__ == "__main__":
    app.run(debug=True)

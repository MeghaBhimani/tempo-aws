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
from flask import Flask, render_template, request, redirect, session, jsonify, url_for
from flask_cors import CORS

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="frontend")
app.secret_key = os.environ.get("FLASK_SECRET", "tempo")
CORS(app, origins=os.environ.get("ALLOWED_ORIGIN", "*"), supports_credentials=True)

# ── AWS config ────────────────────────────────────────────────────────────────
REGION           = os.environ.get("AWS_REGION", "ap-southeast-2")
CLOUDFRONT_DOMAIN = os.environ.get("CLOUDFRONT_DOMAIN", "")  # e.g. d1234abcdef.cloudfront.net

dynamodb  = boto3.resource("dynamodb", region_name=REGION)

login_tbl = dynamodb.Table("Login")
music_tbl = dynamodb.Table("Music")
subs_tbl  = dynamodb.Table("Subscription")

# ── Input validation ──────────────────────────────────────────────────────────
EMAIL_RE = re.compile(r'^[^@]+@[^@]+\.[^@]+$')

def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email))

# ── Image URL helper ──────────────────────────────────────────────────────────
def _image_url(raw_url: str) -> str:
    """
    Return the correct public URL for an image stored in our private S3 bucket.

    Images are served via CloudFront (not presigned URLs):
      - S3 bucket stays private — no public access policy needed
      - CloudFront has Origin Access Control (OAC) permission to read from S3
      - CloudFront URLs are permanent; they never expire
      - No backend call required per request — just string construction

    If the stored value is already a full URL (https://...), pass it through.
    If it is a bare S3 key (e.g. artwork/artist/album.jpg), prepend CloudFront domain.
    """
    if not raw_url:
        return raw_url
    if raw_url.startswith("http"):
        return raw_url                             # already a full URL
    if CLOUDFRONT_DOMAIN:
        return f"https://{CLOUDFRONT_DOMAIN}/{raw_url.lstrip('/')}"
    return raw_url                                 # fallback: return key as-is

# ── Auth decorator ────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "email" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if "email" in session:
            return redirect(url_for("main"))
        return render_template("login.html", error="")

    email    = request.form.get("email",    "").strip()
    password = request.form.get("password", "").strip()

    if not email or not password:
        return render_template("login.html", error="Email and password are required")

    if not valid_email(email):
        return render_template("login.html", error="Invalid email format")

    try:
        resp = login_tbl.get_item(Key={"email": email})
    except ClientError as e:
        log.error("DynamoDB error on login: %s", e)
        return render_template("login.html", error="Database error. Try again.")

    user = resp.get("Item")
    if not user:
        return render_template("login.html", error="Email or password is invalid")

    stored_pw = user.get("password", "")
    try:
        password_ok = bcrypt.checkpw(password.encode("utf-8"), stored_pw.encode("utf-8"))
    except Exception:
        password_ok = (stored_pw == password)   # legacy fallback

    if not password_ok:
        return render_template("login.html", error="Email or password is invalid")

    session["email"]     = email
    session["user_name"] = user.get("user_name", email)
    return redirect(url_for("main"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", error="")

    email     = request.form.get("email",     "").strip()
    user_name = request.form.get("user_name", "").strip()
    password  = request.form.get("password",  "").strip()

    if not email or not user_name or not password:
        return render_template("register.html", error="All fields are required")

    if not valid_email(email):
        return render_template("register.html", error="Invalid email format")

    if len(password) < 6:
        return render_template("register.html", error="Password must be at least 6 characters")

    try:
        existing = login_tbl.get_item(Key={"email": email})
        if "Item" in existing:
            return render_template("register.html", error="Email already exists")

        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        login_tbl.put_item(Item={
            "email":     email,
            "user_name": user_name,
            "password":  hashed,
        })
        return redirect(url_for("login"))

    except ClientError as e:
        log.error("DynamoDB error on register: %s", e)
        return render_template("register.html", error="Database error: " + e.response["Error"]["Message"])


@app.route("/main")
@login_required
def main():
    return render_template("main.html",
        user_name=session["user_name"],
        email=session["email"],
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── API routes ────────────────────────────────────────────────────────────────

@app.route("/api/subscriptions", methods=["GET"])
@login_required
def get_subscriptions():
    email = session["email"]
    try:
        result = subs_tbl.query(KeyConditionExpression=Key("emailId").eq(email))
        items  = result.get("Items", [])
        for item in items:
            if "image_url" in item:
                item["image_url"] = _image_url(item["image_url"])
        return jsonify({"items": items})
    except ClientError as e:
        log.error("DynamoDB error on subscriptions: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/query", methods=["GET"])
@login_required
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
            if title:            conditions.append(Attr("title").eq(title))
            if artist:           conditions.append(Attr("artist").eq(artist))
            if year_val is not None: conditions.append(Attr("year").eq(year_val))
            if album:            conditions.append(Attr("album").eq(album))

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

        return jsonify({"items": items})

    except ClientError as e:
        log.error("DynamoDB error on query: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/subscribe", methods=["POST"])
@login_required
def subscribe():
    data      = request.get_json() or {}
    email     = session["email"]
    artist    = data.get("artist",    "").strip()
    title     = data.get("title",     "").strip()
    album     = data.get("album",     "").strip()
    year      = data.get("year",      "")
    image_url = data.get("image_url", "").strip()

    if not artist or not title:
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
        log.error("DynamoDB error on subscribe: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/unsubscribe", methods=["DELETE"])
@login_required
def unsubscribe():
    data        = request.get_json() or {}
    email       = session["email"]
    title       = data.get("title", "").strip()
    album       = data.get("album", "").strip()
    title_album = f"{title}#{album}"

    if not title:
        return jsonify({"error": "missing_fields"}), 400

    try:
        subs_tbl.delete_item(Key={"emailId": email, "title_album": title_album})
        return jsonify({"message": "unsubscribed"}), 200
    except ClientError as e:
        log.error("DynamoDB error on unsubscribe: %s", e)
        return jsonify({"error": str(e)}), 500


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

"""
load_music_data.py
Downloads album artwork from iTunes, uploads to a private S3 bucket,
and stores the public S3 URL in DynamoDB.

The S3 bucket has a bucket policy that allows public GET on artwork/* objects,
so images can be served directly without presigned URLs or CloudFront.

Usage:
    python scripts/load_music_data.py

Required environment variables (.env):
    AWS_REGION=us-east-1
    S3_BUCKET=your-bucket-name
"""

import os
import io
import time
import requests
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

REGION = os.environ.get("AWS_REGION", "us-east-1")
BUCKET = os.environ.get("S3_BUCKET", "")

if not BUCKET:
    raise RuntimeError("S3_BUCKET environment variable is not set")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
s3       = boto3.client("s3", region_name=REGION)
table    = dynamodb.Table("Music")

ITUNES_URL = "https://itunes.apple.com/search"

SEARCH_TERMS = [
    "Taylor Swift",
    "The Weeknd",
    "Kendrick Lamar",
    "Adele",
    "Ed Sheeran",
    "Billie Eilish",
    "Drake",
    "Dua Lipa",
    "Harry Styles",
    "Post Malone",
]


def fetch_tracks(artist: str, limit: int = 10) -> list:
    try:
        resp = requests.get(ITUNES_URL, params={
            "term":   artist,
            "entity": "song",
            "limit":  limit,
            "media":  "music",
        }, timeout=10)
        resp.raise_for_status()
        return [r for r in resp.json().get("results", []) if r.get("kind") == "song"]
    except Exception as e:
        print(f"  ✗ Failed to fetch '{artist}': {e}")
        return []


def slugify(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")


def s3_key_for(artist: str, album: str) -> str:
    return f"artwork/{slugify(artist)}/{slugify(album)}.jpg"


def upload_artwork(itunes_url: str, s3_key: str) -> str:
    """
    Upload artwork to S3 and return the public S3 URL.
    Skips upload if object already exists (idempotent).
    """
    if not itunes_url:
        return ""

    # Check if already uploaded
    try:
        s3.head_object(Bucket=BUCKET, Key=s3_key)
        print(f"    (already in S3: {s3_key})")
        return f"https://{BUCKET}.s3.{REGION}.amazonaws.com/{s3_key}"
    except ClientError as e:
        if e.response["Error"]["Code"] != "404":
            print(f"    ✗ S3 head error: {e}")
            return itunes_url  # fallback to iTunes URL

    # Download 500x500 artwork from iTunes
    try:
        high_res = itunes_url.replace("100x100bb", "500x500bb")
        img_resp = requests.get(high_res, timeout=15)
        img_resp.raise_for_status()
    except Exception as e:
        print(f"    ✗ Download failed: {e}")
        return itunes_url  # fallback

    # Upload to S3
    try:
        s3.upload_fileobj(
            io.BytesIO(img_resp.content),
            BUCKET,
            s3_key,
            ExtraArgs={"ContentType": "image/jpeg"},
        )
        url = f"https://{BUCKET}.s3.{REGION}.amazonaws.com/{s3_key}"
        print(f"    ✓ Uploaded → {s3_key}")
        return url
    except ClientError as e:
        print(f"    ✗ Upload failed: {e}")
        return itunes_url  # fallback


def load():
    total = 0
    print(f"Loading music into DynamoDB + artwork into S3 bucket '{BUCKET}'...\n")

    for search_term in SEARCH_TERMS:
        print(f"Artist: {search_term}")
        tracks = fetch_tracks(search_term, limit=10)

        for track in tracks:
            artist   = track.get("artistName",     "").strip()
            title    = track.get("trackName",      "").strip()
            album    = track.get("collectionName", "").strip()
            year_raw = track.get("releaseDate",    "")
            year     = year_raw[:4] if year_raw else ""
            art_url  = track.get("artworkUrl100",  "")

            if not artist or not title:
                continue

            s3_key    = s3_key_for(artist, album)
            image_url = upload_artwork(art_url, s3_key)

            table.put_item(Item={
                "artist":      artist,
                "title_album": f"{title}#{album}",
                "title":       title,
                "album":       album,
                "year":        year,
                "image_url":   image_url,
            })
            total += 1
            print(f"  ✓ {title} — {artist} ({year})")

        time.sleep(0.5)

    print(f"\nDone. {total} tracks loaded.")


if __name__ == "__main__":
    load()

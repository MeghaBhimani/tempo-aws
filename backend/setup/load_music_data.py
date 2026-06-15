"""
load_music_data.py
Fetches music from the iTunes Search API (free, no key required) and loads
track metadata into DynamoDB. Artwork URLs are stored directly from iTunes.

Usage:
    pip install boto3 requests python-dotenv
    python scripts/load_music_data.py

Required environment variables (.env):
    AWS_REGION=us-east-1
"""

import os
import time
import requests
import boto3
from dotenv import load_dotenv

load_dotenv()

REGION = os.environ.get("AWS_REGION", "us-east-1")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
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
    """Fetch tracks for an artist from iTunes Search API."""
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


def load():
    total = 0
    print("Loading music into DynamoDB...\n")

    for search_term in SEARCH_TERMS:
        print(f"Artist: {search_term}")
        tracks = fetch_tracks(search_term, limit=10)

        for track in tracks:
            artist    = track.get("artistName",     "").strip()
            title     = track.get("trackName",      "").strip()
            album     = track.get("collectionName", "").strip()
            year_raw  = track.get("releaseDate",    "")
            year      = year_raw[:4] if year_raw else ""
            # Use 500×500 artwork instead of default 100×100
            image_url = track.get("artworkUrl100", "").replace("100x100bb", "500x500bb")

            if not artist or not title:
                continue

            title_album = f"{title}#{album}"

            table.put_item(Item={
                "artist":      artist,
                "title_album": title_album,
                "title":       title,
                "album":       album,
                "year":        year,
                "img_url":   image_url,
            })
            total += 1
            print(f"  ✓ {title} — {artist} ({year})")

        time.sleep(0.5)  # iTunes rate limit

    print(f"\nDone. {total} tracks loaded.")


if __name__ == "__main__":
    load()

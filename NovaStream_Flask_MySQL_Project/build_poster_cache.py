"""
Run this ONCE to build a permanent poster cache using the TMDB API.
After running, the Flask app will use poster_cache.json and need
zero API calls on future restarts.

Get a free TMDB API key at: https://www.themoviedb.org/settings/api
"""

import pandas as pd
import requests
import json
import os
import time

# ─── CONFIG ───────────────────────────────────────────
TMDB_API_KEY  = "YOUR_TMDB_API_KEY_HERE"   # ← paste your key
OMDB_API_KEY  = "975e4605"                  # existing OMDB key (fallback)
CACHE_FILE    = "poster_cache.json"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w500"
# ──────────────────────────────────────────────────────


def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def get_from_tmdb_by_id(tmdb_id):
    """Fetch movie details from TMDB using movie ID."""
    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={TMDB_API_KEY}&language=en-US"
    try:
        r = requests.get(url, timeout=8)
        data = r.json()
        if data.get("poster_path"):
            return {
                "poster":   TMDB_IMG_BASE + data["poster_path"],
                "language": ", ".join([l["english_name"] for l in data.get("spoken_languages", [])]) or "N/A",
                "genre":    ", ".join([g["name"] for g in data.get("genres", [])]) or "N/A",
                "plot":     data.get("overview", "N/A"),
                "rating":   str(round(data.get("vote_average", 0), 1)),
                "actors":   "N/A"
            }
    except Exception as e:
        print(f"  TMDB error for ID {tmdb_id}: {e}")
    return None


def get_from_tmdb_by_title(title):
    """Search TMDB by title."""
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={requests.utils.quote(title)}"
    try:
        r = requests.get(url, timeout=8)
        results = r.json().get("results", [])
        if results and results[0].get("poster_path"):
            m = results[0]
            return {
                "poster":   TMDB_IMG_BASE + m["poster_path"],
                "language": m.get("original_language", "N/A"),
                "genre":    "N/A",
                "plot":     m.get("overview", "N/A"),
                "rating":   str(round(m.get("vote_average", 0), 1)),
                "actors":   "N/A"
            }
    except Exception as e:
        print(f"  TMDB search error for '{title}': {e}")
    return None


# ─── Load all movie titles ─────────────────────────────
print("Loading datasets...")

tmdb_df   = pd.read_csv("dataset/tmdb_5000_movies.csv")
indian_df = pd.read_csv("dataset/indian movies.csv")

# Build title → TMDB ID map
id_map = {}
for _, row in tmdb_df.iterrows():
    title = str(row["title"]).split("(")[0].strip()
    id_map[title] = int(row["id"])

# Collect all titles to cache
all_titles = []

# TMDB titles (first 50 shown on home)
for title in list(id_map.keys())[:50]:
    all_titles.append(("tmdb", title, id_map[title]))

# Indian movies (top-rated, diverse languages)
indian_raw = indian_df[
    indian_df["Movie Name"].notna() &
    indian_df["Genre"].notna() &
    (indian_df["Genre"].str.strip() != "-") &
    indian_df["Language"].notna()
].copy()
indian_raw["Rating(10)"] = pd.to_numeric(indian_raw["Rating(10)"], errors="coerce")
indian_raw = indian_raw[indian_raw["Rating(10)"] >= 6.5]
indian_raw = indian_raw.sort_values("Rating(10)", ascending=False)
indian_sample = indian_raw.groupby("Language").head(15).head(80)

for _, row in indian_sample.iterrows():
    title = str(row["Movie Name"]).strip()
    all_titles.append(("search", title, None))

print(f"Total movies to cache: {len(all_titles)}")

# ─── Fetch and cache ───────────────────────────────────
cache = load_cache()
fetched = 0
skipped = 0

for mode, title, tmdb_id in all_titles:
    if title in cache and cache[title]:
        skipped += 1
        continue

    print(f"  [{fetched+1}] {title}...", end=" ")

    if mode == "tmdb" and tmdb_id:
        result = get_from_tmdb_by_id(tmdb_id)
    else:
        result = get_from_tmdb_by_title(title)

    if result:
        cache[title] = result
        save_cache(cache)
        print(f"✓ poster saved")
        fetched += 1
    else:
        print("✗ no poster")
        fetched += 1

    # Respect TMDB rate limit (40 req / 10 sec)
    time.sleep(0.3)

print(f"\nDone! {fetched} fetched, {skipped} already cached.")
print(f"Total entries in cache: {len(cache)}")
print(f"With valid posters: {sum(1 for v in cache.values() if v)}")

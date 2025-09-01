#!/usr/bin/env python3
"""
Movie poster every 5 h, no duplicates within the same week or month.
Automatically prevents reposts from the previous week.
"""
import os
import json
import random
import requests
from datetime import datetime, timedelta
import cloudinary
import cloudinary.uploader as uploader
import google.generativeai as genai

# --------------------------------------------------------------
TMDB_KEY   = os.getenv("TMDB_API_KEY")
CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CL_KEY     = os.getenv("CLOUDINARY_API_KEY")
CL_SECRET  = os.getenv("CLOUDINARY_API_SECRET")
FB_TOKEN   = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
FB_PAGE    = os.getenv("FACEBOOK_PAGE_ID")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.5-flash"

GENRE_MAP = {28:"Action",12:"Adventure",16:"Animation",35:"Comedy",
             80:"Crime",99:"Documentary",18:"Drama",10751:"Family",
             14:"Fantasy",36:"History",27:"Horror",10402:"Music",
             9648:"Mystery",10749:"Romance",878:"Sci-Fi",
             53:"Thriller",10752:"War",37:"Western"}

CACHE_FILE = "posted_cache.json"
# --------------------------------------------------------------

cloudinary.config(
    cloud_name=CLOUD_NAME,
    api_key=CL_KEY,
    api_secret=CL_SECRET,
)

# ------------------ Cache Management -------------------------
def load_posted():
    """Return sets of TMDB IDs already posted this week and month, including last 2 weeks."""
    week_ids, month_ids = set(), set()
    now = datetime.utcnow()
    month_key = now.strftime("%Y-%m")
    current_week_key = now.strftime("%Y-%U")

    # Prepare last 2 week keys
    last_weeks = [(now - timedelta(days=7 * i)).strftime("%Y-%U") for i in range(1, 3)]

    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)

        # Month IDs
        if data.get("month", {}).get("key") == month_key:
            month_ids = set(data["month"].get("ids", []))

        # Week IDs: current week + last 2 weeks
        week_data = data.get("week", {})
        for wk_key in [current_week_key] + last_weeks:
            ids = week_data.get(wk_key, [])
            week_ids.update(ids)

    return week_ids, month_ids

def save_posted(week_ids, month_ids):
    """Save sets of IDs with the current week and month, keeping only last 3 weeks."""
    now = datetime.utcnow()
    month_key = now.strftime("%Y-%m")
    current_week_key = now.strftime("%Y-%U")

    # Load old cache if exists
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)

    # Update month
    cache["month"] = {"key": month_key, "ids": list(month_ids)}

    # Update week
    old_week_data = cache.get("week", {})
    # Keep only last 2 old weeks + current
    last_weeks = [(now - timedelta(days=7 * i)).strftime("%Y-%U") for i in range(1, 3)]
    new_week_data = {wk: old_week_data.get(wk, []) for wk in last_weeks}
    new_week_data[current_week_key] = list(week_ids)
    cache["week"] = new_week_data

    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)


# ------------------ Movie Selection -------------------------
def trending_movies():
    url = f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_KEY}"
    data = requests.get(url, timeout=10).json()
    results = data.get("results", [])
    random.shuffle(results)  # shuffle to reduce repeated picks
    return results

def choose_movie(movies, week_ids, month_ids):
    """Return first unseen movie, else None."""
    print("Already posted this week:", week_ids)
    print("Already posted this month:", month_ids)
    for m in movies:
        mid = str(m["id"])
        print("Considering movie:", mid, m["title"])
        if mid not in week_ids and mid not in month_ids:
            print("Selected:", mid, m["title"])
            return m
    return None

# ------------------ Poster & Caption ------------------------
def generate_poster(movie):
    return f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"

def generate_caption(movie):
    genres = ", ".join(GENRE_MAP.get(g, "") for g in movie.get("genre_ids", []))
    prompt = (
        f"Write a short structured Facebook post with emojis and line breaks (do not add intros like Here's your post).\n"
        f"Format:\n"
        f"🎬 Title\n\n"
        f"⭐ Rating\n"
        f"📅 Release Date\n\n"
        f"📖 Short Hook (1-2 sentences)\n"
        f"Include hashtags at the end.\n\n"
        f"Title: {movie['title']}\n\n"
        f"Genres: {genres}\n"
        f"Rating: {movie['vote_average']}/10\n"
        f"Release: {movie.get('release_date', 'TBA')}\n\n"
        f"Synopsis: {movie['overview'][:150]}..."
    )
    model = genai.GenerativeModel(MODEL)
    text = model.generate_content(prompt).text.strip()
    return text.replace("\\n", "\n")

# ------------------ Facebook Posting ------------------------
def post_to_facebook(img_url, caption):
    url = f"https://graph.facebook.com/v20.0/{FB_PAGE}/photos"
    payload = {
        "caption": caption,
        "url": img_url,
        "access_token": FB_TOKEN
    }
    r = requests.post(url, data=payload, timeout=10)
    try:
        r.raise_for_status()
    except requests.exceptions.HTTPError:
        print("Facebook API error:", r.text)
        raise
    return str(r.json().get("id"))

# ------------------ Main -------------------------------------
def main():
    week_ids, month_ids = load_posted()
    movies = trending_movies()
    movie = choose_movie(movies, week_ids, month_ids)
    if not movie:
        print("No new movie to post this cycle.")
        return

    poster_url = generate_poster(movie)
    caption = generate_caption(movie)
    fb_id = post_to_facebook(poster_url, caption)

    # mark as posted
    mid = str(movie["id"])
    week_ids.add(mid)
    month_ids.add(mid)
    save_posted(week_ids, month_ids)
    print("Posted:", fb_id)

if __name__ == "__main__":
    main()

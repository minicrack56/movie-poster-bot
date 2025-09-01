#!/usr/bin/env python3
"""
Movie poster every 5 h, no duplicates within the same week or month.
Automatically resets weekly and monthly caches.
"""
import os
import json
import requests
from datetime import datetime
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

def load_posted():
    """Return sets of TMDB IDs already posted this week and month."""
    week_ids, month_ids = set(), set()
    now = datetime.utcnow()
    week_key  = now.strftime("%Y-%U")  # ISO week number
    month_key = now.strftime("%Y-%m")

    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        # check month
        if data.get("month", {}).get("key") == month_key:
            month_ids = set(data["month"].get("ids", []))
        # check week
        if data.get("week", {}).get("key") == week_key:
            week_ids = set(data["week"].get("ids", []))

    return week_ids, month_ids

def save_posted(week_ids, month_ids):
    """Save sets of IDs with the current week and month."""
    now = datetime.utcnow()
    payload = {
        "month": {"key": now.strftime("%Y-%m"), "ids": list(month_ids)},
        "week":  {"key": now.strftime("%Y-%U"), "ids": list(week_ids)}
    }
    with open(CACHE_FILE, "w") as f:
        json.dump(payload, f)

def trending_movies():
    url = f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_KEY}"
    data = requests.get(url, timeout=10).json()
    return data["results"]

def choose_movie(movies, week_ids, month_ids):
    """Return first unseen movie, else None."""
    for m in movies:
        mid = str(m["id"])
        if mid not in week_ids and mid not in month_ids:
            return m
    return None

def generate_poster(movie):
    return f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"

def generate_caption(movie):
    genres = ", ".join(GENRE_MAP.get(g, "") for g in movie.get("genre_ids", []))
    prompt = (
        f"Write a short structured Facebook post with emojis and line breaks (do not add intros like Here's your post).\n"
        f"Format:\n"
        f"🎬 Title\n"
        f"⭐ Rating\n"
        f"📅 Release Date\n"
        f"📖 Short Hook (1-2 sentences)\n"
        f"Include hashtags at the end.\n\n"
        f"Title: {movie['title']}\n"
        f"Genres: {genres}\n"
        f"Rating: {movie['vote_average']}/10\n"
        f"Release: {movie.get('release_date', 'TBA')}\n"
        f"Synopsis: {movie['overview'][:150]}..."
    )
    model = genai.GenerativeModel(MODEL)
    text = model.generate_content(prompt).text.strip()
    return text.replace("\\n", "\n")

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

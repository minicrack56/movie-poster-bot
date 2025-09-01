#!/usr/bin/env python3
"""
Movie poster every 5 h, no duplicates within the current month.
Stores the already-posted IDs in a GitHub Actions cache file.
"""
import os
import json
import requests
from datetime import datetime
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

CACHE_FILE = "posted_this_month.json"
# --------------------------------------------------------------

cloudinary.config(
    cloud_name=CLOUD_NAME,
    api_key=CL_KEY,
    api_secret=CL_SECRET,
)

def load_posted():
    """Return set of TMDB IDs already posted this month."""
    if not os.path.exists(CACHE_FILE):
        return set()
    with open(CACHE_FILE, "r") as f:
        data = json.load(f)
    # if file is from a different month → reset
    if data.get("month") != datetime.utcnow().strftime("%Y-%m"):
        return set()
    return set(data.get("ids", []))

def save_posted(ids):
    """Save set of IDs with the current month."""
    payload = {"month": datetime.utcnow().strftime("%Y-%m"), "ids": list(ids)}
    with open(CACHE_FILE, "w") as f:
        json.dump(payload, f)

def trending_movies():
    url = f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_KEY}"
    data = requests.get(url, timeout=10).json()
    return data["results"]

def choose_movie(movies, posted):
    """Return first unseen movie, else None."""
    for m in movies:
        if str(m["id"]) not in posted:
            return m
    return None

def generate_poster(movie):
    poster_url = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
    composite = (
        f"https://res.cloudinary.com/{CLOUD_NAME}/image/fetch/"
        f"l_text:Arial_120_bold_center:{movie['title'].replace(' ', '%20')},"
        f"co_white,w_500,c_fit,y_-50/{poster_url}"
    )
    return composite

def generate_caption(movie):
    genres = ", ".join(GENRE_MAP.get(g, "") for g in movie.get("genre_ids", []))
    prompt = (
        f"Write a 60-80 word Facebook caption for a movie poster.\n"
        f"Include emoji, title, genres, ⭐ rating, release date, hook.\n"
        f"Title: {movie['title']}\n"
        f"Genres: {genres}\n"
        f"Rating: {movie['vote_average']}/10\n"
        f"Release: {movie.get('release_date', 'TBA')}\n"
        f"Synopsis: {movie['overview'][:150]}..."
    )
    model = genai.GenerativeModel(MODEL)
    return model.generate_content(prompt).text.strip()

def post_to_facebook(img_url, caption):
    url = f"https://graph.facebook.com/v20.0/{FB_PAGE}/posts"
    payload = {"message": caption, "link": img_url, "access_token": FB_TOKEN}
    r = requests.post(url, data=payload, timeout=10)
    r.raise_for_status()
    return str(r.json().get("id"))

def main():
    posted = load_posted()
    movies = trending_movies()
    movie = choose_movie(movies, posted)
    if not movie:
        print("No new movie this cycle.")
        return

    poster_url = generate_poster(movie)
    caption = generate_caption(movie)
    fb_id = post_to_facebook(poster_url, caption)

    # mark as posted
    posted.add(str(movie["id"]))
    save_posted(posted)
    print("Posted:", fb_id)

if __name__ == "__main__":
    main()

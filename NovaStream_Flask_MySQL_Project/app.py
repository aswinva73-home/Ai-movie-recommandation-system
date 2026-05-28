import pickle
import json
import os
import pandas as pd
import requests
from flask import Flask, render_template, request, redirect, url_for, send_file, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super_secret_novastream_key")

# ── User authentication cache ──
USERS_FILE = "users_cache.json"

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2)

@app.before_request
def require_login():
    # Allow static files and auth routes
    allowed_routes = ['login_page', 'api_login', 'api_signup', 'static']
    if request.endpoint not in allowed_routes and 'user_email' not in session:
        return redirect(url_for('login_page'))

API_KEY      = os.getenv("OMDB_API_KEY", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

print("OMDB KEY:", API_KEY)
print("TMDB KEY:", TMDB_API_KEY)

TMDB_IMG     = "https://image.tmdb.org/t/p/w500"

# ── Poster cache (avoids hitting OMDB every restart) ──
CACHE_FILE = 'poster_cache.json'

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2)

omdb_cache = load_cache()
print(f"Poster cache loaded: {len(omdb_cache)} entries")


def get_movie_details(movie_title):

    from urllib.parse import quote

    global omdb_cache

    # Clean movie title
    movie_title = str(movie_title).split('(')[0].strip()

    # URL-safe title
    safe_title = quote(movie_title)

    # Check cache first
    if movie_title in omdb_cache:
        return omdb_cache[movie_title]

    try:

        url = (
            f"http://www.omdbapi.com/"
            f"?apikey={API_KEY}"
            f"&t={safe_title}"
        )

        response = requests.get(url, timeout=8)

        data = response.json()

        print(data)   # Debug output

        if data.get("Response") == "True":

            poster = data.get("Poster")

            # Fallback poster
            if not poster or poster == "N/A":
                poster = "/static/posters/default.jpg"

            result = {

                "poster": poster,

                "language": data.get("Language", "N/A"),

                "genre": data.get("Genre", "N/A"),

                "plot": data.get("Plot", "N/A"),

                "rating": data.get("imdbRating", "N/A"),

                "actors": data.get("Actors", "N/A")
            }

            # Save to cache
            omdb_cache[movie_title] = result

            save_cache(omdb_cache)

            return result

        else:
            print("OMDb Error:", data.get("Error"))

    except Exception as e:

        print("OMDb Error:", e)

    # ── TMDB Fallback Search (if OMDb fails) ──
    if TMDB_API_KEY and TMDB_API_KEY != 'YOUR_TMDB_API_KEY_HERE':
        try:
            print(f"Fallback to TMDB search for: {movie_title}")
            tmdb_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={safe_title}"
            tmdb_res = requests.get(tmdb_url, timeout=8).json()
            
            if tmdb_res.get("results") and len(tmdb_res["results"]) > 0:
                first_result = tmdb_res["results"][0]
                poster_path = first_result.get("poster_path")
                
                poster = f"{TMDB_IMG}{poster_path}" if poster_path else "/static/posters/default.jpg"
                
                result = {
                    "poster": poster,
                    "language": first_result.get("original_language", "en").upper(),
                    "genre": "N/A",  
                    "plot": first_result.get("overview", "N/A"),
                    "rating": str(round(first_result.get("vote_average", 0), 1)) if first_result.get("vote_average") else "N/A",
                    "actors": "N/A"
                }
                
                omdb_cache[movie_title] = result
                save_cache(omdb_cache)
                return result
        except Exception as e:
            print("TMDB Fallback Error:", e)

    return None


def get_tmdb_movie(tmdb_id, title):
    """Fetch movie details from TMDB using its numeric ID."""
    global omdb_cache

    if title in omdb_cache:
        return omdb_cache[title]

    try:
        url = (
            f"https://api.themoviedb.org/3/movie/{tmdb_id}"
            f"?api_key={TMDB_API_KEY}&language=en-US"
        )
        r    = requests.get(url, timeout=8)
        data = r.json()

        if data.get("poster_path"):
            result = {
                "poster":   TMDB_IMG + data["poster_path"],
                "language": ", ".join(
                    l["english_name"] for l in data.get("spoken_languages", [])
                ) or "English",
                "genre":    ", ".join(
                    g["name"] for g in data.get("genres", [])
                ) or "N/A",
                "plot":     data.get("overview", "N/A"),
                "rating":   str(round(data.get("vote_average", 0), 1)),
                "actors":   "N/A"
            }
            omdb_cache[title] = result
            save_cache(omdb_cache)
            return result

    except Exception as e:
        print(f"TMDB Error for {title}:", e)

    return None


def recommend(movie_name):

    movie_index = movies_data[movies_data['title'] == movie_name].index[0]

    distances = similarity[movie_index]

    movie_list = sorted(
        list(enumerate(distances)),
        reverse=True,
        key=lambda x: x[1]
    )[1:6]

    recommended_movies = []

    for i in movie_list:
        recommended_movies.append(
            movies_data.iloc[i[0]].title
        )

    return recommended_movies



movies_data = pickle.load(open('model/movies.pkl', 'rb'))
similarity  = pickle.load(open('model/similarity.pkl', 'rb'))

tmdb_movies       = pd.read_csv('dataset/tmdb_5000_movies.csv')
indian_movies_csv = pd.read_csv('dataset/indian movies.csv')

# Build a title -> TMDB id map for fast lookup
tmdb_id_map = {
    str(row['title']).split('(')[0].strip(): int(row['id'])
    for _, row in tmdb_movies.iterrows()
}


@app.route('/recommend/<movie>')
def recommend_movie(movie):

    recommendations = recommend(movie)

    return {
        "recommendations": recommendations
    }

try:
    db = mysql.connector.connect(
        host     = os.getenv("DB_HOST",     "localhost"),
        user     = os.getenv("DB_USER",     "root"),
        password = os.getenv("DB_PASSWORD", ""),
        database = os.getenv("DB_NAME",     "novastream")
    )
    cursor = db.cursor(dictionary=True)
except mysql.connector.Error as err:
    print(f"Database connection error: {err}")
    print("Please ensure MySQL is running and the 'novastream' database exists.")
    db = None
    cursor = None

movies = []

print("Building movie list from cache (no API calls at startup)...")

# Helper: read from cache only — never call API at startup
def get_cached(title):
    return omdb_cache.get(title)  # None if not cached

# ── TMDB movies (first 50) ──
for index, row in tmdb_movies.head(50).iterrows():

    title   = str(row['title']).split('(')[0].strip()
    details = get_cached(title)

    if details:
        poster = details.get('poster', '/static/posters/default.jpg')
        if not poster or poster == 'N/A':
            poster = '/static/posters/default.jpg'
        movies.append({
            "title":    title,
            "language": details.get('language', 'English'),
            "genre":    details.get('genre', 'N/A'),
            "plot":     details.get('plot', 'N/A'),
            "rating":   details.get('rating', 'N/A'),
            "actors":   details.get('actors', 'N/A'),
            "image":    poster
        })
    else:
        # Not in cache yet — show placeholder, will fetch on detail page visit
        movies.append({
            "title":    title,
            "language": str(row.get('original_language', 'en')).upper(),
            "genre":    'N/A',
            "plot":     str(row.get('overview', 'N/A')),
            "rating":   str(round(row.get('vote_average', 0), 1)) if 'vote_average' in row else 'N/A',
            "actors":   'N/A',
            "image":    '/static/posters/default.jpg'
        })

# ── Indian movies from CSV ──
indian_filtered = indian_movies_csv[
    indian_movies_csv['Movie Name'].notna() &
    (indian_movies_csv['Movie Name'].str.strip() != '') &
    indian_movies_csv['Genre'].notna() &
    (indian_movies_csv['Genre'].str.strip() != '-') &
    (indian_movies_csv['Genre'].str.strip() != '') &
    indian_movies_csv['Language'].notna() &
    (indian_movies_csv['Language'].str.strip() != '') &
    indian_movies_csv['Rating(10)'].notna() &
    (indian_movies_csv['Rating(10)'] != '-')
].copy()

try:
    indian_filtered['Rating(10)'] = pd.to_numeric(indian_filtered['Rating(10)'], errors='coerce')
    indian_filtered = indian_filtered[indian_filtered['Rating(10)'] >= 6.0]
except Exception:
    pass

indian_sample   = indian_filtered.groupby('Language').head(15).head(80)
existing_titles = {m['title'].lower() for m in movies}

for _, row in indian_sample.iterrows():
    title = str(row['Movie Name']).strip()
    if title.lower() in existing_titles:
        continue

    details  = get_cached(title)
    language = str(row['Language']).strip().title()
    genre    = str(row['Genre']).strip()
    rating   = str(row['Rating(10)']).strip()

    poster = '/static/posters/default.jpg'
    plot   = 'N/A'
    actors = 'N/A'

    if details:
        poster = details.get('poster', poster)
        if not poster or poster == 'N/A':
            poster = '/static/posters/default.jpg'
        plot   = details.get('plot', plot)
        actors = details.get('actors', actors)

    movies.append({
        "title":    title,
        "language": language,
        "genre":    genre,
        "plot":     plot,
        "rating":   rating,
        "actors":   actors,
        "image":    poster
    })
    existing_titles.add(title.lower())

print(f"Movies loaded: {len(movies)} (from cache + CSV)")


# ── Korean movies (cache-only) ──
_korean_csv = pd.read_csv('dataset/korian_movie.csv')
for _, row in _korean_csv.iterrows():
    title = str(row['title']).strip()
    if title.lower() in existing_titles:
        continue
    details = get_cached(title)
    poster  = details.get('poster', '/static/posters/default.jpg') if details else '/static/posters/default.jpg'
    if not poster or poster == 'N/A':
        poster = '/static/posters/default.jpg'
    movies.append({
        "title":    title,
        "language": "Korean",
        "genre":    str(row.get('genre', '')).strip(),
        "plot":     details.get('plot', str(row.get('overview', 'N/A'))) if details else str(row.get('overview', 'N/A')),
        "rating":   details.get('rating', 'N/A') if details else 'N/A',
        "actors":   details.get('actors', 'N/A') if details else 'N/A',
        "image":    poster
    })
    existing_titles.add(title.lower())

# ── Spanish movies (cache-only) ──
_spanish_csv = pd.read_csv('dataset/soanish_movie.csv')
for _, row in _spanish_csv.iterrows():
    title = str(row['title']).strip()
    if title.lower() in existing_titles:
        continue
    details = get_cached(title)
    poster  = details.get('poster', '/static/posters/default.jpg') if details else '/static/posters/default.jpg'
    if not poster or poster == 'N/A':
        poster = '/static/posters/default.jpg'
    movies.append({
        "title":    title,
        "language": "Spanish",
        "genre":    str(row.get('genre', '')).strip(),
        "plot":     details.get('plot', str(row.get('overview', 'N/A'))) if details else str(row.get('overview', 'N/A')),
        "rating":   details.get('rating', 'N/A') if details else 'N/A',
        "actors":   details.get('actors', 'N/A') if details else 'N/A',
        "image":    poster
    })
    existing_titles.add(title.lower())

print(f"Total movies ready: {len(movies)}")



@app.route('/')
def login_page():
    if 'user_email' in session:
        return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.json
    email = data.get('email', '').strip().lower()
    name = data.get('name', '').strip()
    password = data.get('password', '')
    
    users = load_users()
    if email in users:
        return jsonify({"status": "error", "message": "An account with this email already exists."}), 400
        
    users[email] = {
        "name": name,
        "password": generate_password_hash(password)
    }
    save_users(users)
    return jsonify({"status": "success", "message": "Account created successfully!"})

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    users = load_users()
    user = users.get(email)
    
    if not user or not check_password_hash(user['password'], password):
        return jsonify({"status": "error", "message": "Invalid email or password."}), 401
        
    session['user_email'] = email
    session['user_name'] = user['name']
    return jsonify({"status": "success"})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))


# ──────────────────────────────────────────────────────
#  LAZY POSTER & DETAIL API  (called by JavaScript)
# ──────────────────────────────────────────────────────

from flask import jsonify

@app.route('/api/poster/<path:title>')
def api_poster(title):
    """Return cached or freshly fetched poster URL for a movie title."""
    # 1. Check cache first
    cached = omdb_cache.get(title)
    if cached and cached.get('poster') and cached['poster'] != 'N/A':
        return jsonify({'poster': cached['poster'], 'source': 'cache'})

    # 2. Try TMDB (uses movie ID from CSV — more reliable)
    tmdb_id = tmdb_id_map.get(title)
    if tmdb_id and TMDB_API_KEY and TMDB_API_KEY != 'YOUR_TMDB_API_KEY_HERE':
        details = get_tmdb_movie(tmdb_id, title)
        if details and details.get('poster'):
            return jsonify({'poster': details['poster'], 'source': 'tmdb'})

    # 3. Fallback to OMDB
    if API_KEY:
        details = get_movie_details(title)
        if details and details.get('poster') and details['poster'] != 'N/A':
            return jsonify({'poster': details['poster'], 'source': 'omdb'})

    # 4. Nothing found
    return jsonify({'poster': '/static/posters/default.jpg', 'source': 'default'})


@app.route('/home')
def home():
    return render_template('index.html', movies=movies)



# side bar backend 

@app.route('/movies')
def movies_page():
    return render_template('movies.html', movies=movies)


@app.route('/series')
def series_page():
    return render_template('series.html', movies=movies)


#movie page

@app.route('/movies/<genre>')
def movies_by_genre(genre):

    filtered_movies = [
        movie for movie in movies
        if movie['genre'] and genre.lower() in movie['genre'].lower()
    ]

    return render_template(
        'movies.html',
        movies=filtered_movies
    )


# Movie Details Route
@app.route('/movie/<movie_name>')
def movie_details(movie_name):

    # ── Fallback chain: cache → TMDB → OMDB → local movies list ──
    details = omdb_cache.get(movie_name)

    if not details:
        tmdb_id = tmdb_id_map.get(movie_name)
        if tmdb_id:
            details = get_tmdb_movie(tmdb_id, movie_name)

    if not details:
        details = get_movie_details(movie_name)

    # Last resort: use data already in the movies list
    if not details:
        local = next(
            (m for m in movies if m['title'].lower() == movie_name.lower()),
            None
        )
        if local:
            details = {
                'poster':   local['image'],
                'language': local['language'],
                'genre':    local['genre'],
                'plot':     local['plot'],
                'rating':   local['rating'],
                'actors':   local.get('actors', 'N/A')
            }

    if not details:
        details = {
            'poster':   '/static/posters/default.jpg',
            'language': 'N/A',
            'genre':    'N/A',
            'plot':     'No details available.',
            'rating':   'N/A',
            'actors':   'N/A'
        }

    # AI recommendations
    recommended_movies = []
    try:
        matched = movies_data[
            movies_data['title'].str.contains(movie_name, case=False, na=False)
        ]
        if not matched.empty:
            movie_index = matched.index[0]
            movie_list  = sorted(
                list(enumerate(similarity[movie_index])),
                reverse=True,
                key=lambda x: x[1]
            )[1:6]

            for i in movie_list:
                rec_title   = movies_data.iloc[i[0]].title
                rec_details = omdb_cache.get(rec_title)

                if not rec_details:
                    rid = tmdb_id_map.get(rec_title)
                    if rid:
                        rec_details = get_tmdb_movie(rid, rec_title)
                if not rec_details:
                    rec_details = get_movie_details(rec_title)

                # Fallback: look in local movies list
                rec_local = next(
                    (m for m in movies if m['title'].lower() == rec_title.lower()),
                    None
                )

                recommended_movies.append({
                    "title": rec_title,
                    "image": (
                        rec_details['poster']
                        if rec_details and rec_details.get('poster') and rec_details['poster'] != 'N/A'
                        else (rec_local['image'] if rec_local else '/static/posters/default.jpg')
                    )
                })
    except Exception as e:
        print("Recommendation error:", e)

    # ── Record History ──
    try:
        from datetime import datetime
        import time
        history_data = load_history()
        now = datetime.now()
        if not history_data or history_data[0].get('movie_name') != movie_name:
            history_data.insert(0, {
                "id": int(time.time() * 1000),
                "movie_name": movie_name,
                "viewed_date": now.strftime("%Y-%m-%d"),
                "viewed_time": now.strftime("%I:%M %p")
            })
            if len(history_data) > 100:
                history_data = history_data[:100]
            save_history_data(history_data)
    except Exception as e:
        print("History error:", e)

    return render_template(
        'movie_details.html',
        movie=details,
        title=movie_name,
        recommendations=recommended_movies
    )



@app.route('/ai_recommendation')
def ai_recommendation():

    movie_name = movies_data.sample(1).iloc[0].title

    recommendations = recommend(movie_name)

    recommended_movies = []

    for movie in recommendations:

        details = get_movie_details(movie)

        if details:

            recommended_movies.append({

                "title": movie,

                "image": details['poster'],

                "genre": details['genre'],

                "rating": details['rating']
            })

    return render_template(
        'recommendation.html',
        movies=recommended_movies,
        selected_movie=movie_name
    )


# ── Local JSON History System ──
# (Replaces MySQL so it works without database configuration)

HISTORY_FILE = "history_cache.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_history_data(hist_data):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(hist_data, f, indent=2)

@app.route('/save_history', methods=['POST'])
def save_history():
    movie = request.form.get('movie')
    if not movie:
        return "ignored"
        
    history_data = load_history()
    now = datetime.now()
    
    # Generate unique ID based on timestamp
    import time
    new_id = int(time.time() * 1000)
    
    # Prevent consecutive duplicates
    if not history_data or history_data[0].get('movie_name') != movie:
        history_data.insert(0, {
            "id": new_id,
            "movie_name": movie,
            "viewed_date": now.strftime("%Y-%m-%d"),
            "viewed_time": now.strftime("%I:%M %p")
        })
        
        # Keep only the last 100 items to save space
        if len(history_data) > 100:
            history_data = history_data[:100]
            
        save_history_data(history_data)
        
    return "saved"

@app.route('/history')
def history():
    history_data = load_history()
    return render_template('history.html', history=history_data)

@app.route('/delete/<int:id>')
def delete(id):
    history_data = load_history()
    # Filter out the item with the matching id
    history_data = [item for item in history_data if item.get('id') != id]
    save_history_data(history_data)
    return redirect(url_for('history'))

@app.route('/language/<lang>')
def language_movies(lang):

    filtered_movies = [
        movie for movie in movies
        if movie['language']
        and lang.lower() in movie['language'].lower()
    ]

    return render_template(
        'language.html',
        movies=filtered_movies,
        selected_language=lang
    )



@app.route('/language/<lang>/<genre>')
def language_genre_movies(lang, genre):

    filtered_movies = [

        movie for movie in movies

        if movie['language']
        and lang.lower() in movie['language'].lower()

        and movie['genre']
        and genre.lower() in movie['genre'].lower()
    ]

    return render_template(
        'language.html',
        movies=filtered_movies,
        selected_language=lang,
        selected_genre=genre
    )

    


if __name__ == '__main__':
    app.run(debug=True)

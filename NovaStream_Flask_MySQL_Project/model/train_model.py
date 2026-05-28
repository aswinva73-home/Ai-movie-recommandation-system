import pandas as pd
import pickle
import ast

from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ─────────────────────────────────────────────
# PART 1 : TMDB dataset
# ─────────────────────────────────────────────

movies = pd.read_csv('dataset/tmdb_5000_movies.csv')
credits = pd.read_csv('dataset/tmdb_5000_credits.csv')

movies = movies.merge(credits, on='title')

movies = movies[['movie_id', 'title', 'overview', 'genres', 'keywords', 'cast', 'crew']]

movies.dropna(inplace=True)


def convert(text):
    return [i['name'] for i in ast.literal_eval(text)]


def convert_cast(text):
    return [i['name'] for idx, i in enumerate(ast.literal_eval(text)) if idx < 3]


def fetch_director(text):
    return [i['name'] for i in ast.literal_eval(text) if i['job'] == 'Director']


movies['genres']   = movies['genres'].apply(convert)
movies['keywords'] = movies['keywords'].apply(convert)
movies['cast']     = movies['cast'].apply(convert_cast)
movies['crew']     = movies['crew'].apply(fetch_director)
movies['overview'] = movies['overview'].apply(lambda x: x.split())

for col in ['genres', 'keywords', 'cast', 'crew']:
    movies[col] = movies[col].apply(lambda x: [w.replace(' ', '') for w in x])

movies['tags'] = (
    movies['overview']
    + movies['genres']
    + movies['keywords']
    + movies['cast']
    + movies['crew']
)

tmdb_df = movies[['movie_id', 'title', 'tags']].copy()
tmdb_df['tags'] = tmdb_df['tags'].apply(lambda x: ' '.join(x).lower())

print(f"TMDB movies loaded: {len(tmdb_df)}")

# ─────────────────────────────────────────────
# PART 2 : Indian movies dataset
# ─────────────────────────────────────────────

indian_raw = pd.read_csv('dataset/indian movies.csv')

# Keep only rows that have a Movie Name and Genre
indian_raw = indian_raw[
    indian_raw['Movie Name'].notna() &
    (indian_raw['Movie Name'].str.strip() != '') &
    indian_raw['Genre'].notna() &
    (indian_raw['Genre'].str.strip() != '-') &
    (indian_raw['Genre'].str.strip() != '') &
    indian_raw['Language'].notna() &
    (indian_raw['Language'].str.strip() != '')
].copy()

# Keep only movies with a numeric rating >= 6
indian_raw['Rating(10)'] = pd.to_numeric(indian_raw['Rating(10)'], errors='coerce')
indian_raw = indian_raw[indian_raw['Rating(10)'] >= 6.0].copy()

# Sort by rating descending; take top 30 per language, max 500 total
indian_raw = indian_raw.sort_values('Rating(10)', ascending=False)
indian_raw = indian_raw.groupby('Language').head(30).head(500).reset_index(drop=True)
indian_raw['Genre'] = indian_raw['Genre'].str.strip()

# Only keep movies with a valid language
indian_raw = indian_raw[
    indian_raw['Language'].notna() &
    (indian_raw['Language'].str.strip() != '')
].copy()

# Build tags from Genre + Language
def build_indian_tags(row):
    genre_words  = [g.strip().replace(' ', '') for g in str(row['Genre']).split(',') if g.strip() and g.strip() != '-']
    lang_words   = [str(row['Language']).strip().replace(' ', '')]
    return ' '.join(genre_words + lang_words).lower()

indian_raw['tags'] = indian_raw.apply(build_indian_tags, axis=1)

# Assign movie_id starting after TMDB ids
start_id = int(tmdb_df['movie_id'].max()) + 1

indian_df = pd.DataFrame({
    'movie_id': range(start_id, start_id + len(indian_raw)),
    'title':    indian_raw['Movie Name'].values,
    'tags':     indian_raw['tags'].values
})

print(f"Indian movies loaded: {len(indian_df)}")

# ─────────────────────────────────────────────
# PART 3 : Korean & Spanish custom datasets
# ─────────────────────────────────────────────

def load_custom_csv(filepath, language_label):
    """Load a CSV with columns: title, genre, overview, image"""
    df = pd.read_csv(filepath)
    df = df[df['title'].notna() & df['genre'].notna()].copy()

    def build_tags(row):
        genre_words    = [g.strip().replace(' ', '') for g in str(row['genre']).split() if g.strip()]
        overview_words = str(row.get('overview', '')).split()
        lang           = [language_label.replace(' ', '')]
        return ' '.join(overview_words + genre_words + lang).lower()

    df['tags'] = df.apply(build_tags, axis=1)
    return df[['title', 'tags']].copy()

korean_raw  = load_custom_csv('dataset/korian_movie.csv',  'Korean')
spanish_raw = load_custom_csv('dataset/soanish_movie.csv', 'Spanish')

print(f"Korean  movies loaded: {len(korean_raw)}")
print(f"Spanish movies loaded: {len(spanish_raw)}")

# Assign sequential movie_ids
def assign_ids(df, start_id):
    df = df.copy()
    df.insert(0, 'movie_id', range(start_id, start_id + len(df)))
    return df

next_id    = int(tmdb_df['movie_id'].max()) + 1
indian_df  = assign_ids(indian_df.drop(columns='movie_id'), next_id)
next_id   += len(indian_df)
korean_df  = assign_ids(korean_raw,  next_id)
next_id   += len(korean_df)
spanish_df = assign_ids(spanish_raw, next_id)

# ─────────────────────────────────────────────
# PART 4 : Combine & train
# ─────────────────────────────────────────────

combined_df = pd.concat([tmdb_df, indian_df, korean_df, spanish_df], ignore_index=True)
combined_df.drop_duplicates(subset='title', inplace=True)
combined_df.reset_index(drop=True, inplace=True)

print(f"Combined dataset size: {len(combined_df)}")

# Vectorize
cv = CountVectorizer(max_features=5000, stop_words='english')
vectors = cv.fit_transform(combined_df['tags']).toarray()

# Similarity matrix
similarity = cosine_similarity(vectors)

# ─────────────────────────────────────────────
# PART 5 : Save
# ─────────────────────────────────────────────

pickle.dump(combined_df, open('model/movies.pkl', 'wb'))
pickle.dump(similarity,  open('model/similarity.pkl', 'wb'))

print("Model Trained Successfully!")
print(f"Total unique movies in model: {len(combined_df)}")
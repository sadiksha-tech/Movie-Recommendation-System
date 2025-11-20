import numpy as np
import pandas as pd
from flask import Flask, render_template, request, redirect, session, flash, jsonify
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from scipy.sparse import csr_matrix
import json
import bs4 as bs
import urllib.request
import pickle
import requests
from datetime import date, datetime
import mysql.connector
from mysql.connector import Error
import os 
import re
from textblob import TextBlob

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['STATIC_FOLDER'] = 'static'

# TMDB API Configuration
TMDB_API_KEY = "3773e1be80b444b1d0b9d21a3ec2131c"
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Database connection function
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root", 
            password="",
            database="movie-recommendation",
            autocommit=True
        )
        return conn
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

# Initialize database connection
conn = get_db_connection()
cursor = conn.cursor() if conn else None

# Load the NLP model and vectorizer
try:
    filename = 'nlp_model.pkl'
    clf = pickle.load(open(filename, 'rb'))
    vectorizer = pickle.load(open('tranform.pkl', 'rb'))
except:
    print("Warning: Could not load NLP model files")
    clf = None
    vectorizer = None

def convert_to_list(my_list):
    """Convert string representation of list to actual list"""
    if not my_list or my_list == '[]':
        return []
    try:
        my_list = my_list.split('","')
        my_list[0] = my_list[0].replace('["', '')
        my_list[-1] = my_list[-1].replace('"]', '')
        return my_list
    except:
        return []

def convert_to_list_num(my_list):
    """Convert string representation of number list to actual list"""
    if not my_list or my_list == '[]':
        return []
    try:
        my_list = my_list.split(',')
        my_list[0] = my_list[0].replace("[", "")
        my_list[-1] = my_list[-1].replace("]", "")
        return [int(x.strip()) if x.strip().isdigit() else float(x.strip()) for x in my_list]
    except:
        return []

def get_suggestions():
    """Get movie suggestions for autocomplete"""
    try:
        data = pd.read_csv('main_data.csv')
        return list(data['movie_title'].str.capitalize())
    except:
        return ["The Avengers", "Inception", "The Dark Knight", "Pulp Fiction", "Forrest Gump"]

def get_movie_reviews_tmdb(movie_id):
    """Get movie reviews from TMDB API with sentiment analysis"""
    try:
        response = requests.get(
            f"{TMDB_BASE_URL}/movie/{movie_id}/reviews",
            params={"api_key": TMDB_API_KEY, "language": "en-US"}
        )
        
        if response.status_code != 200:
            print(f"TMDB API error: {response.status_code}")
            return {}
            
        reviews_data = response.json()
        reviews_list = []
        reviews_status = []
        
        for review in reviews_data.get("results", [])[:5]:
            content = review.get("content", "").strip()
            if content and len(content) > 50:
                reviews_list.append(content)
                
                blob = TextBlob(content)
                polarity = blob.sentiment.polarity
                
                if polarity > 0.1:
                    sentiment = "Positive"
                elif polarity < -0.1:
                    sentiment = "Negative"
                else:
                    sentiment = "Neutral"
                    
                reviews_status.append(sentiment)
        
        movie_reviews = {reviews_list[i]: reviews_status[i] for i in range(len(reviews_list))}
        return movie_reviews
        
    except Exception as e:
        print(f"Error fetching TMDB reviews: {e}")
        return {}

def get_tmdb_movie_id(imdb_id):
    """Convert IMDB ID to TMDB movie ID"""
    try:
        response = requests.get(
            f"{TMDB_BASE_URL}/find/{imdb_id}",
            params={
                "api_key": TMDB_API_KEY,
                "external_source": "imdb_id"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("movie_results") and len(data["movie_results"]) > 0:
                return data["movie_results"][0]["id"]
        return None
    except Exception as e:
        print(f"Error converting IMDB to TMDB ID: {e}")
        return None

def get_movie_reviews_fallback(movie_title):
    """Fallback method to get reviews if TMDB fails"""
    try:
        mock_reviews = {
            f"This movie '{movie_title}' was absolutely fantastic! Great acting and storyline.": "Positive",
            f"I didn't enjoy '{movie_title}' very much. The plot was weak and characters were underdeveloped.": "Negative",
            f"'{movie_title}' is a decent film with good production values but nothing extraordinary.": "Neutral",
            f"Amazing cinematography in '{movie_title}'. The director did a wonderful job!": "Positive",
            f"While '{movie_title}' had potential, it failed to deliver a compelling narrative.": "Negative"
        }
        return mock_reviews
    except Exception as e:
        print(f"Error in fallback reviews: {e}")
        return {}

# Routes
@app.route("/")
@app.route("/home")
def home():
    suggestions = get_suggestions()
    return render_template('home.html', suggestions=suggestions)

@app.route("/login")
def login():
    suggestions = get_suggestions()
    return render_template('login.html', suggestions=suggestions)

@app.route("/register")
def register():
    suggestions = get_suggestions()
    return render_template('register.html', suggestions=suggestions)

@app.route("/homelogged")
def homelogged():
    if 'id' in session:
        suggestions = get_suggestions()
        return render_template('homelogged.html', suggestions=suggestions)
    else:
        return redirect('/')

@app.route("/login_validation", methods=['POST'])
def login_validation():
    email = request.form.get('email')
    password = request.form.get('password')

    if not conn:
        flash('Database connection error', 'error')
        return redirect('/login')

    try:
        cursor.execute("SELECT * FROM `user` WHERE `email` = %s AND `password` = %s", (email, password))
        users = cursor.fetchall()
        if len(users) > 0:
            session['id'] = users[0][0]
            session['username'] = users[0][1]
            flash('Login successful!', 'success')
            return redirect('/homelogged')
        else:
            flash('Invalid email or password', 'error')
            return redirect('/login')
    except Error as e:
        flash('Database error occurred', 'error')
        return redirect('/login')

@app.route('/manage-user')
def manage_user():
    if 'id' in session:
        user_id = session['id']
        try:
            cursor.execute("SELECT * FROM user WHERE id = %s", (user_id,))
            user_data = cursor.fetchone()
            
            # Get user's wishlist
            cursor.execute("""
                SELECT movie_id, movie_title, movie_poster, movie_rating, movie_year, added_date 
                FROM movie_wishlist 
                WHERE user_id = %s 
                ORDER BY added_date DESC
            """, (user_id,))
            wishlist = cursor.fetchall()
            
            if user_data:
                return render_template('manage_user.html', 
                    user_id=user_data[0], 
                    name=user_data[1], 
                    email=user_data[2], 
                    password=user_data[3],
                    phone=user_data[4],
                    address=user_data[5],
                    wishlist=wishlist)
            else:
                flash('User not found', 'error')
                session.clear()
                return redirect('/')
        except Error as e:
            flash('Database error', 'error')
            print(f"Database error: {e}")
            return redirect('/')
    else:
        return redirect('/')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect('/')

@app.route('/add_user', methods=['POST'])
def add_user():
    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')
    repassword = request.form.get('repassword')
    phone = request.form.get('phone')
    address = request.form.get('address')

    if not conn:
        flash('Database connection error', 'error')
        return redirect('/register')

    try:
        cursor.execute("SELECT * FROM `user` WHERE `email` = %s OR `phone` = %s", (email, phone))
        existing_user = cursor.fetchone()
        if existing_user:
            flash('Email or phone number already exists', 'error')
            return redirect('/register')
    except Error as e:
        flash('Database error', 'error')
        return redirect('/register')

    if password != repassword:
        flash('Passwords do not match', 'error')
        return redirect('/register')

    try:
        cursor.execute(
            "INSERT INTO `user` (`name`, `email`, `password`, `phone`, `address`) VALUES (%s, %s, %s, %s, %s)",
            (name, email, password, phone, address)
        )
        conn.commit()
        
        cursor.execute("SELECT * FROM `user` WHERE `email` = %s", (email,))
        user = cursor.fetchone()
        session['id'] = user[0]
        session['username'] = user[1]
        flash('Registration successful!', 'success')
        return redirect('/homelogged')
    except Error as e:
        flash('Registration failed', 'error')
        return redirect('/register')

@app.route('/add_to_wishlist', methods=['POST'])
def add_to_wishlist():
    if 'id' not in session:
        return jsonify({'success': False, 'message': 'Please login to add movies to wishlist'})
    
    try:
        data = request.get_json()
        user_id = session['id']
        movie_id = data.get('movie_id')
        movie_title = data.get('movie_title')
        movie_poster = data.get('movie_poster', '')
        movie_rating = data.get('movie_rating', 0)
        movie_year = data.get('movie_year', 0)
        
        # Check if movie already in wishlist
        cursor.execute(
            "SELECT id FROM movie_wishlist WHERE user_id = %s AND movie_id = %s",
            (user_id, movie_id)
        )
        existing = cursor.fetchone()
        
        if existing:
            return jsonify({'success': False, 'message': 'Movie already in wishlist'})
        
        # Add to wishlist
        cursor.execute(
            """INSERT INTO movie_wishlist 
            (user_id, movie_id, movie_title, movie_poster, movie_rating, movie_year) 
            VALUES (%s, %s, %s, %s, %s, %s)""",
            (user_id, movie_id, movie_title, movie_poster, movie_rating, movie_year)
        )
        conn.commit()
        
        return jsonify({'success': True, 'message': 'Movie added to wishlist!'})
    
    except Exception as e:
        print(f"Error adding to wishlist: {e}")
        return jsonify({'success': False, 'message': 'Error adding movie to wishlist'})

@app.route('/remove_from_wishlist', methods=['POST'])
def remove_from_wishlist():
    if 'id' not in session:
        return jsonify({'success': False, 'message': 'Please login first'})
    
    try:
        data = request.get_json()
        user_id = session['id']
        movie_id = data.get('movie_id')
        
        cursor.execute(
            "DELETE FROM movie_wishlist WHERE user_id = %s AND movie_id = %s",
            (user_id, movie_id)
        )
        conn.commit()
        
        return jsonify({'success': True, 'message': 'Movie removed from wishlist'})
    
    except Exception as e:
        print(f"Error removing from wishlist: {e}")
        return jsonify({'success': False, 'message': 'Error removing movie from wishlist'})

@app.route("/populate-matches", methods=["POST"])
def populate_matches():
    try:
        res = json.loads(request.get_data("data"))
        movies_list = res['movies_list']
        
        movie_cards = {}
        for i in range(min(len(movies_list), 10)):
            poster_path = movies_list[i].get('poster_path')
            if poster_path:
                poster_url = "https://image.tmdb.org/t/p/original" + poster_path
            else:
                poster_url = "/static/images/movie_placeholder.jpeg"
            
            movie_cards[poster_url] = [
                movies_list[i].get('title', 'N/A'),
                movies_list[i].get('original_title', 'N/A'),
                movies_list[i].get('vote_average', 0),
                datetime.strptime(movies_list[i]['release_date'], '%Y-%m-%d').year if movies_list[i].get('release_date') else "N/A",
                movies_list[i].get('id', 0)
            ]
        
        return render_template('recommend.html', movie_cards=movie_cards)
    except Exception as e:
        print(f"Error in populate-matches: {e}")
        return "Error processing request", 500

@app.route("/recommend", methods=["POST"])
def recommend():
    try:
        title = request.form.get('title', '')
        cast_ids = request.form.get('cast_ids', '[]')
        cast_names = request.form.get('cast_names', '[]')
        cast_chars = request.form.get('cast_chars', '[]')
        cast_bdays = request.form.get('cast_bdays', '[]')
        cast_bios = request.form.get('cast_bios', '[]')
        cast_places = request.form.get('cast_places', '[]')
        cast_profiles = request.form.get('cast_profiles', '[]')
        imdb_id = request.form.get('imdb_id', '')
        poster = request.form.get('poster', '/static/images/movie_placeholder.jpeg')
        genres = request.form.get('genres', '')
        overview = request.form.get('overview', 'No overview available.')
        vote_average = request.form.get('rating', '0')
        vote_count = request.form.get('vote_count', '0')
        rel_date = request.form.get('rel_date', '')
        release_date = request.form.get('release_date', '')
        runtime = request.form.get('runtime', '')
        status = request.form.get('status', '')
        rec_movies = request.form.get('rec_movies', '[]')
        rec_posters = request.form.get('rec_posters', '[]')
        rec_movies_org = request.form.get('rec_movies_org', '[]')
        rec_year = request.form.get('rec_year', '[]')
        rec_vote = request.form.get('rec_vote', '[]')
        rec_ids = request.form.get('rec_ids', '[]')
        movie_id = request.form.get('movie_id', '0')

        rec_movies_org = convert_to_list(rec_movies_org)
        rec_movies = convert_to_list(rec_movies)
        rec_posters = convert_to_list(rec_posters)
        cast_names = convert_to_list(cast_names)
        cast_chars = convert_to_list(cast_chars)
        cast_profiles = convert_to_list(cast_profiles)
        cast_bdays = convert_to_list(cast_bdays)
        cast_bios = convert_to_list(cast_bios)
        cast_places = convert_to_list(cast_places)
        cast_ids = convert_to_list_num(cast_ids)
        rec_vote = convert_to_list_num(rec_vote)
        rec_year = convert_to_list_num(rec_year)
        rec_ids = convert_to_list_num(rec_ids)

        for i in range(len(cast_bios)):
            cast_bios[i] = cast_bios[i].replace(r'\n', '\n').replace(r'\"', '"') if cast_bios[i] else "Biography not available."

        for i in range(len(cast_chars)):
            cast_chars[i] = cast_chars[i].replace(r'\n', '\n').replace(r'\"', '"') if cast_chars[i] else "Character information not available."

        movie_cards = {}
        for i in range(min(len(rec_posters), 12)):
            movie_cards[rec_posters[i]] = [
                rec_movies[i] if i < len(rec_movies) else "Unknown",
                rec_movies_org[i] if i < len(rec_movies_org) else "Unknown",
                rec_vote[i] if i < len(rec_vote) else 0,
                rec_year[i] if i < len(rec_year) else "N/A",
                rec_ids[i] if i < len(rec_ids) else 0
            ]

        casts = {}
        for i in range(min(len(cast_names), 10)):
            casts[cast_names[i]] = [
                cast_ids[i] if i < len(cast_ids) else 0,
                cast_chars[i] if i < len(cast_chars) else "Unknown",
                cast_profiles[i] if i < len(cast_profiles) else "/static/images/default_profile.jpg"
            ]

        cast_details = {}
        for i in range(min(len(cast_names), 10)):
            cast_details[cast_names[i]] = [
                cast_ids[i] if i < len(cast_ids) else 0,
                cast_profiles[i] if i < len(cast_profiles) else "/static/images/default_profile.jpg",
                cast_bdays[i] if i < len(cast_bdays) else "Not available",
                cast_places[i] if i < len(cast_places) else "Not available",
                cast_bios[i] if i < len(cast_bios) else "Biography not available."
            ]

        movie_reviews = {}
        
        if imdb_id and imdb_id.strip():
            tmdb_movie_id = get_tmdb_movie_id(imdb_id)
            if tmdb_movie_id:
                movie_reviews = get_movie_reviews_tmdb(tmdb_movie_id)
            
            if not movie_reviews:
                movie_reviews = get_movie_reviews_fallback(title)
        else:
            movie_reviews = get_movie_reviews_fallback(title)

        curr_date = ""
        movie_rel_date = ""
        try:
            if rel_date:
                today = str(date.today())
                curr_date = datetime.strptime(today, '%Y-%m-%d')
                movie_rel_date = datetime.strptime(rel_date, '%Y-%m-%d')
        except:
            pass

        suggestions = get_suggestions()
        
        # Check if movie is in wishlist
        in_wishlist = False
        if 'id' in session:
            try:
                cursor.execute(
                    "SELECT id FROM movie_wishlist WHERE user_id = %s AND movie_id = %s",
                    (session['id'], movie_id)
                )
                in_wishlist = cursor.fetchone() is not None
            except:
                pass
        
        return render_template('recommend.html', 
                            title=title,
                            poster=poster,
                            overview=overview,
                            vote_average=vote_average,
                            vote_count=vote_count,
                            release_date=release_date,
                            movie_rel_date=movie_rel_date,
                            curr_date=curr_date,
                            runtime=runtime,
                            status=status,
                            genres=genres,
                            movie_cards=movie_cards,
                            reviews=movie_reviews,
                            casts=casts,
                            cast_details=cast_details,
                            suggestions=suggestions,
                            movie_id=movie_id,
                            in_wishlist=in_wishlist)

    except Exception as e:
        print(f"Error in recommend route: {e}")
        suggestions = get_suggestions()
        return render_template('recommend.html', 
                            title="Error",
                            overview="Sorry, an error occurred while processing your request.",
                            suggestions=suggestions)

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True)
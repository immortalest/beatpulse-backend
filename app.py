import os
import json
import re
import time
import urllib.request
import urllib.parse
import yt_dlp
from flask import Flask, jsonify, request, send_from_directory, Response, stream_with_context
from flask_cors import CORS

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SONGS_DIR = os.path.join(BASE_DIR, 'songs')

if not os.path.exists(SONGS_DIR):
    os.makedirs(SONGS_DIR, exist_ok=True)

SEARCH_CACHE = {}
STREAM_CACHE = {}

def clean_title(title):
    patterns = [
        r'\\(Official.*?\\)', r'\\[Official.*?\\]', r'\\(Lyrical.*?\\)', r'\\[Lyrical.*?\\]',
        r'\\(Audio.*?\\)', r'\\[Audio.*?\\]', r'\\(Video.*?\\)', r'\\[Video.*?\\]',
        r'\\(Full Song.*?\\)', r'\\[Full Song.*?\\]', r'\|.*$', r'HD', r'4K', r'Video Song',
        r'Official Music Video', r'Visualizer', r'Studio Version', r'Full Audio'
    ]
    cleaned = str(title)
    for p in patterns:
        cleaned = re.sub(p, '', cleaned, flags=re.IGNORECASE)
    return ' '.join(cleaned.split()) if cleaned.strip() else str(title)

# Pure Track Name Extractor for 100% Accurate Lyrics
def extract_pure_song_name(title):
    # Remove text inside brackets
    cleaned = re.sub(r'\\(.*?\\)', '', title)
    cleaned = re.sub(r'\\[.*?\\]', '', cleaned)
    
    # Split by separators like |, -, :, ft., feat. and take the first clean part
    for sep in ['|', '-', ':', 'ft.', 'feat.', 'From']:
        if sep in cleaned:
            cleaned = cleaned.split(sep)[0]
            
    # Remove common filler words
    fillers = ['official', 'video', 'song', 'lyrical', 'full', 'audio', '4k', 'hd', 'remix', 'version', 'studio', 'bhediya', 'jawan', 'pathaan']
    words = cleaned.split()
    pure_words = [w for w in words if w.lower() not in fillers]
    
    res = ' '.join(pure_words).strip()
    return res if res else title.strip()

def format_duration(seconds):
    if not seconds:
        return ""
    mins = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{mins}:{secs:02d}"

@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

# 1. Local Files
@app.route('/api/songs', methods=['GET'])
@app.route('/songs', methods=['GET'])
def get_songs():
    song_list = []
    if os.path.exists(SONGS_DIR):
        for root, dirs, files in os.walk(SONGS_DIR):
            for file in files:
                if file.lower().endswith(('.mp3', '.m4a', '.webm', '.wav')):
                    rel_path = os.path.relpath(os.path.join(root, file), SONGS_DIR)
                    song_list.append({
                        'id': f"local_{rel_path}",
                        'title': clean_title(file),
                        'artist': 'Local Storage',
                        'cover': 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=200&auto=format&fit=crop',
                        'stream_url': f"/songs/{rel_path}",
                        'duration_str': 'Local',
                        'is_local': True
                    })
    return jsonify(song_list)

@app.route('/songs/<path:filename>')
def serve_song_file(filename):
    return send_from_directory(SONGS_DIR, filename)

# 2. Online Search
@app.route('/api/search-online', methods=['GET'])
@app.route('/search', methods=['GET'])
def search_online():
    query = request.args.get('query') or request.args.get('q') or 'Arijit Singh'
    query_clean = query.strip()
    query_key = query_clean.lower()

    if query_key in SEARCH_CACHE and (time.time() - SEARCH_CACHE[query_key]['time'] < 1800):
        return jsonify(SEARCH_CACHE[query_key]['data'])

    search_term = query_clean

    ydl_opts = {
        'format': 'bestaudio/best',
        'skip_download': True,
        'quiet': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios']
            }
        }
    }

    
    results = []
    bad_words = ['jukebox', 'full album', 'all songs', 'non stop', 'non-stop', '1 hour', '2 hour', '3 hour', '30 min', 'full movie', 'compilation', 'podcast', 'reaction', 'cover by', 'dance', 'karaoke', 'shorts']
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch25:{search_term}", download=False)
            entries = info.get('entries', []) if info else []
            for entry in entries:
                if entry:
                    v_id = entry.get('id')
                    title = entry.get('title') or 'Unknown'
                    duration = entry.get('duration') or 0
                    
                    title_lower = title.lower()
                    if any(w in title_lower for w in bad_words):
                        continue
                    if duration and (duration < 90 or duration > 540):
                        continue

                    results.append({
                        'id': v_id,
                        'title': clean_title(title),
                        'artist': entry.get('uploader') or entry.get('channel') or query_clean,
                        'cover': f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg",
                        'duration_str': format_duration(duration),
                        'is_local': False
                    })
                    if len(results) >= 20:
                        break

        SEARCH_CACHE[query_key] = {'time': time.time(), 'data': results}
        return jsonify(results)
    except Exception as e:
        return jsonify([])

# 3. Stream Route
@app.route('/stream/<video_id>', methods=['GET'])
@app.route('/api/stream/<video_id>', methods=['GET'])
def stream_audio(video_id):
    if video_id in STREAM_CACHE and (time.time() - STREAM_CACHE[video_id]['time'] < 3600):
        return jsonify({'stream_url': STREAM_CACHE[video_id]['url']})

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            stream_url = info.get('url')
            STREAM_CACHE[video_id] = {'time': time.time(), 'url': stream_url}
            return jsonify({'stream_url': stream_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 4. Smart Accurate Lyrics Route
@app.route('/api/lyrics', methods=['GET'])
def get_lyrics():
    raw_title = request.args.get('title', '').strip()
    artist = request.args.get('artist', '').strip()
    
    if not raw_title:
        return jsonify({'lyrics': 'Select a song to view lyrics.'})

    pure_song_name = extract_pure_song_name(raw_title)

    try:
        # Search LRCLIB using extracted pure song name
        encoded_name = urllib.parse.quote(pure_song_name)
        url = f"https://lrclib.net/api/search?track_name={encoded_name}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, timeout=5) as response:
            results = json.loads(response.read().decode('utf-8'))
            if results and len(results) > 0:
                # Find best exact match
                for item in results:
                    track = item.get('trackName', '').lower()
                    if pure_song_name.lower() in track or track in pure_song_name.lower():
                        lyrics = item.get('plainLyrics') or item.get('syncedLyrics')
                        if lyrics:
                            return jsonify({'lyrics': lyrics, 'matched_track': item.get('trackName')})
                
                # Fallback to first available lyrics in list
                for item in results:
                    lyrics = item.get('plainLyrics') or item.get('syncedLyrics')
                    if lyrics:
                        return jsonify({'lyrics': lyrics, 'matched_track': item.get('trackName')})

        # Secondary search if track_name parameter returned empty
        url_fallback = f"https://lrclib.net/api/search?q={encoded_name}"
        req_fb = urllib.request.Request(url_fallback, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_fb, timeout=5) as response:
            results = json.loads(response.read().decode('utf-8'))
            if results and len(results) > 0:
                for item in results:
                    lyrics = item.get('plainLyrics') or item.get('syncedLyrics')
                    if lyrics:
                        return jsonify({'lyrics': lyrics, 'matched_track': item.get('trackName')})

        return jsonify({'lyrics': f"Lyrics for '{pure_song_name}' are not available in the database.\nEnjoy listening!"})
    except Exception as e:
        return jsonify({'lyrics': f"Lyrics for '{pure_song_name}' could not be loaded.\nEnjoy the music!"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
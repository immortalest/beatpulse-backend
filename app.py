
import os
import json
import re
import yt_dlp
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

BASE_DIR = os.path.dirname(__file__)
DATA_FILE = os.path.join(BASE_DIR, 'user_data.json')

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'w') as f:
        json.dump({'favorites': [], 'playlists': {}, 'history': []}, f)

def load_user_data():
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            if 'history' not in data:
                data['history'] = []
            return data
    except Exception:
        return {'favorites': [], 'playlists': {}, 'history': []}

def save_user_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def clean_title(title):
    patterns = [
        r'\\(.*?\\)', r'\\[.*?\\]', r'\|.*$', r'Full Song', r'Official Video', 
        r'Lyrical Video', r'Audio', r'HD', r'4K', r'Song', r'Video', r'8K'
    ]
    cleaned = str(title)
    for p in patterns:
        cleaned = re.sub(p, '', cleaned, flags=re.IGNORECASE)
    cleaned = ' '.join(cleaned.split())
    return cleaned if cleaned else str(title)

# 1. Home route
@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

# 2. Local Songs route (Returns empty array so frontend doesn't crash)
@app.route('/api/songs', methods=['GET'])
def get_local_songs():
    return jsonify([])

# 3. Online Search route
@app.route('/api/search-online', methods=['GET'])
@app.route('/search', methods=['GET'])
def search_online():
    query = request.args.get('query') or request.args.get('q') or 'Arijit Singh'
    ydl_opts = {
        'extract_flat': True,
        'skip_download': True,
        'quiet': True,
        'default_search': 'ytsearch15'
    }

    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            for entry in info.get('entries', []):
                if entry:
                    v_id = entry.get('id')
                    results.append({
                        'id': v_id,
                        'title': clean_title(entry.get('title', 'Unknown')),
                        'artist': entry.get('uploader', 'BeatPulse Artist'),
                        'cover': f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg",
                        'duration': entry.get('duration')
                    })
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 4. Stream route
@app.route('/stream/<video_id>', methods=['GET'])
@app.route('/api/stream/<video_id>', methods=['GET'])
def stream_audio(video_id):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True
    }
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return jsonify({'stream_url': info.get('url')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 5. User Data route
@app.route('/api/user-data', methods=['GET', 'POST'])
def user_data_api():
    if request.method == 'GET':
        return jsonify(load_user_data())
    else:
        new_data = request.json
        save_user_data(new_data)
        return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

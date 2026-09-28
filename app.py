import os
import json
import re
import yt_dlp
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SONGS_DIR = os.path.join(BASE_DIR, 'songs')

if not os.path.exists(SONGS_DIR):
    os.makedirs(SONGS_DIR, exist_ok=True)

def clean_title(title):
    patterns = [r'\\(.*?\\)', r'\\[.*?\\]', r'\|.*$', r'Full Song', r'Official Video', r'Lyrical Video', r'Audio', r'HD', r'4K']
    cleaned = str(title)
    for p in patterns:
        cleaned = re.sub(p, '', cleaned, flags=re.IGNORECASE)
    return ' '.join(cleaned.split()) if cleaned.strip() else str(title)

@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

@app.route('/api/songs', methods=['GET'])
@app.route('/songs', methods=['GET'])
def get_songs():
    song_list = []
    if os.path.exists(SONGS_DIR):
        for root, dirs, files in os.walk(SONGS_DIR):
            for file in files:
                if file.lower().endswith(('.mp3', '.m4a', '.webm', '.wav')):
                    rel_path = os.path.relpath(os.path.join(root, file), SONGS_DIR)
                    song_list.append({'title': clean_title(file), 'url': f"/songs/{rel_path}"})
    return jsonify(song_list)

@app.route('/songs/<path:filename>')
def serve_song_file(filename):
    return send_from_directory(SONGS_DIR, filename)

@app.route('/api/search-online', methods=['GET'])
@app.route('/search', methods=['GET'])
def search_online():
    query = request.args.get('query') or request.args.get('q') or 'Arijit Singh'
    ydl_opts = {'extract_flat': True, 'skip_download': True, 'quiet': True, 'default_search': 'ytsearch15'}
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
                        'artist': entry.get('uploader', 'BeatPulse'),
                        'cover': f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg"
                    })
        return jsonify(results)
    except Exception:
        return jsonify([])

@app.route('/stream/<video_id>', methods=['GET'])
@app.route('/api/stream/<video_id>', methods=['GET'])
def stream_audio(video_id):
    ydl_opts = {'format': 'bestaudio/best', 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            return jsonify({'stream_url': info.get('url')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

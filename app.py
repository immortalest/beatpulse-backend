import os
import json
import re
import urllib.request
import urllib.parse
import yt_dlp
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(__file__)
SONGS_DIR = os.path.join(BASE_DIR, 'songs')
DATA_FILE = os.path.join(BASE_DIR, 'user_data.json')

if not os.path.exists(SONGS_DIR):
    os.makedirs(SONGS_DIR)

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

def get_downloaded_titles_set():
    downloaded = set()
    if os.path.exists(SONGS_DIR):
        for root, dirs, files in os.walk(SONGS_DIR):
            for file in files:
                if file.endswith(('.mp3', '.m4a', '.webm')):
                    base_name = os.path.splitext(file)[0].lower().strip()
                    downloaded.add(base_name)
    return downloaded

@app.route('/api/songs', methods=['GET'])
def get_local_songs():
    playlist_name = request.args.get('playlist', '')
    target_dir = SONGS_DIR
    if playlist_name:
        target_dir = os.path.join(SONGS_DIR, playlist_name)

    song_list = []
    if os.path.exists(target_dir):
        for root, dirs, files in os.walk(target_dir):
            for file in files:
                if file.endswith(('.mp3', '.m4a', '.webm')):
                    rel_path = os.path.relpath(os.path.join(root, file), SONGS_DIR).replace('\\', '/')
                    file_base = os.path.splitext(file)[0]
                    
                    jpg_path = os.path.join(root, f"{file_base}.jpg")
                    if os.path.exists(jpg_path):
                        rel_jpg = os.path.relpath(jpg_path, SONGS_DIR).replace('\\', '/')
                        cover_img = f"http://127.0.0.1:5000/songs/{rel_jpg}"
                    else:
                        cover_img = f"https://picsum.photos/300?random={len(song_list) + 1}"

                    song_list.append({
                        'id': f'local_{len(song_list) + 1}',
                        'title': clean_title(file_base),
                        'artist': 'Saved Offline Track',
                        'cover': cover_img,
                        'url': f'http://127.0.0.1:5000/songs/{rel_path}',
                        'isLocal': True,
                        'rel_path': rel_path
                    })
    return jsonify(song_list)

@app.route('/api/search-online', methods=['GET'])
def search_online():
    """Super-Fast Instant Search"""
    query = request.args.get('query', 'Arijit Singh')
    downloaded_set = get_downloaded_titles_set()

    ydl_opts = {
        'extract_flat': True,
        'skip_download': True,
        'quiet': True
    }

    results = []
    seen_titles = set()
    blocked_keywords = ['jukebox', 'compilation', 'full album', 'nonstop', 'non stop', '1 hour', '2 hour', '3 hour', 'mashup']

    try:
        search_query = f"ytsearch20:{query} song"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_results = ydl.extract_info(search_query, download=False)
            if search_results and 'entries' in search_results:
                for entry in search_results['entries']:
                    if not entry:
                        continue
                    
                    video_id = entry.get('id') or entry.get('url', '').replace('https://www.youtube.com/watch?v=', '')
                    if not video_id:
                        continue

                    raw_title = entry.get('title', 'Unknown Title')
                    lower_title = raw_title.lower()
                    duration = entry.get('duration', 0) or 0

                    if (duration > 500) or any(kw in lower_title for kw in blocked_keywords):
                        continue

                    artist = entry.get('uploader') or entry.get('channel') or query
                    cleaned = clean_title(raw_title)
                    norm_title = cleaned.lower()

                    if norm_title in seen_titles:
                        continue
                    seen_titles.add(norm_title)

                    safe_title_check = "".join([c for c in cleaned if c.isalnum() or c in (' ', '_', '-')]).strip().lower()
                    is_downloaded = safe_title_check in downloaded_set

                    cover = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                    
                    results.append({
                        'id': video_id,
                        'title': cleaned,
                        'artist': str(artist).replace(' - Topic', ''),
                        'cover': cover,
                        'video_url': f"https://www.youtube.com/watch?v={video_id}",
                        'isDownloaded': is_downloaded
                    })
        return jsonify(results)
    except Exception as e:
        print(f"❌ Search Error: {e}")
        return jsonify([])

@app.route('/api/get-stream-url', methods=['POST'])
def get_stream_url():
    data = request.get_json(force=True, silent=True) or {}
    video_url = data.get('video_url')
    if not video_url:
        return jsonify({'error': 'No URL provided'}), 400

    ydl_opts = {'format': 'bestaudio/best', 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return jsonify({'stream_url': info.get('url')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/save-to-app', methods=['POST'])
def save_to_app():
    data = request.get_json(force=True, silent=True) or {}
    video_url = data.get('video_url')
    title = data.get('title', 'song')
    cover_url = data.get('cover', '')
    playlist_name = data.get('playlist_name', '')
    
    if not video_url:
        return jsonify({'error': 'No URL provided'}), 400
    
    safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '_', '-')]).strip() or "saved_song"
    
    if playlist_name:
        safe_pname = "".join([c for c in playlist_name if c.isalnum() or c in (' ', '_', '-')]).strip()
        save_folder = os.path.join(SONGS_DIR, safe_pname)
    else:
        save_folder = SONGS_DIR

    if not os.path.exists(save_folder):
        os.makedirs(save_folder)

    out_path = os.path.join(save_folder, f"{safe_title}.mp3")
    thumb_path = os.path.join(save_folder, f"{safe_title}.jpg")
    
    if os.path.exists(out_path):
        return jsonify({'message': f'"{safe_title}" pehle se downloaded hai!', 'already_exists': True})

    ydl_opts = {'format': 'bestaudio/best', 'outtmpl': out_path, 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        
        if cover_url:
            try:
                req = urllib.request.Request(cover_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as resp, open(thumb_path, 'wb') as f:
                    f.write(resp.read())
            except Exception as img_e:
                print("Thumbnail save error:", img_e)

        return jsonify({'message': f'"{safe_title}" offline save ho gaya hai!'})
    except Exception as e:
        return jsonify({'error': f"Download fail: {str(e)}"}), 500

@app.route('/api/delete-song', methods=['POST'])
def delete_song():
    data = request.get_json(force=True, silent=True) or {}
    rel_path = data.get('rel_path')
    if not rel_path:
        return jsonify({'error': 'No file specified'}), 400

    file_path = os.path.join(SONGS_DIR, rel_path)
    base_path = os.path.splitext(file_path)[0]
    jpg_path = f"{base_path}.jpg"

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(jpg_path):
            os.remove(jpg_path)
        return jsonify({'message': 'File deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/lyrics', methods=['GET'])
def get_lyrics():
    title = request.args.get('title', '')
    artist = request.args.get('artist', '')
    
    clean_t = clean_title(title)
    encoded_t = urllib.parse.quote(clean_t)
    encoded_a = urllib.parse.quote(artist)
    
    url = f"https://lrclib.net/api/get?artist_name={encoded_a}&track_name={encoded_t}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            res_data = json.loads(resp.read().decode())
            lyrics = res_data.get('plainLyrics') or res_data.get('syncedLyrics') or "Lyrics not found."
            return jsonify({'lyrics': lyrics})
    except Exception:
        return jsonify({'lyrics': f"🎶 Enjoying '{clean_t}' by {artist}\n(Lyrics unavailable for this track)"})

@app.route('/api/user-data', methods=['GET'])
def get_user_data_api():
    return jsonify(load_user_data())

@app.route('/api/user-data', methods=['POST'])
def save_user_data_api():
    data = request.get_json(force=True, silent=True) or {}
    save_user_data(data)
    return jsonify({'status': 'saved'})

@app.route('/songs/<path:filename>', methods=['GET'])
def stream_song(filename):
    return send_from_directory(SONGS_DIR, filename)

if __name__ == '__main__':
    print("🎵 BeatPulse Music Backend Active: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
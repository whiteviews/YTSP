# Save this as app.py

import os
import sys
import re
import subprocess
import json
import uuid
import shutil
import requests

from flask import Flask, request, jsonify, render_template, send_from_directory, Response
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# --- Setup Block ---
CLIENT_ID = 'YOUR_CLIENT_ID_HERE'
CLIENT_SECRET = 'YOUR_CLIENT_SECRET_HERE'

def run_setup():
    print("--- Spotify API Setup for YTSP ---")
    client_id = input("Enter your Spotify Client ID: ").strip()
    client_secret = input("Enter your Spotify Client Secret: ").strip()
    if not client_id or not client_secret: sys.exit("\n[ERROR] Both fields are required.")
    try:
        script_path = os.path.abspath(__file__)
        with open(script_path, 'r') as f: lines = f.readlines()
        new_lines = []
        for line in lines:
            if line.strip().startswith("CLIENT_ID ="): new_lines.append(f"CLIENT_ID = '{client_id}'\n")
            elif line.strip().startswith("CLIENT_SECRET ="): new_lines.append(f"CLIENT_SECRET = '{client_secret}'\n")
            else: new_lines.append(line)
        with open(script_path, 'w') as f: f.writelines(new_lines)
        sys.exit("\n[SUCCESS] Credentials saved. Run 'python app.py' to start the server.")
    except Exception as e:
        sys.exit(f"\n[ERROR] Failed to write to file: {e}")
# --- End of Setup Block ---

app = Flask(__name__)
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
if not os.path.exists(DOWNLOAD_DIR): os.makedirs(DOWNLOAD_DIR)
app.config['DOWNLOAD_DIR'] = DOWNLOAD_DIR

sp = None
if CLIENT_ID != 'YOUR_CLIENT_ID_HERE':
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET))
    except Exception as e:
        print(f"Spotify Init Error: {e}")

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name).replace(' ', '-')[:100]

download_tasks = {}

@app.route('/start-download', methods=['POST'])
def start_download():
    task_id = str(uuid.uuid4())
    download_tasks[task_id] = request.get_json()
    return jsonify({'success': True, 'task_id': task_id})

@app.route('/progress/<task_id>')
def progress(task_id):
    task_details = download_tasks.get(task_id)
    if not task_details:
        return Response("Task not found.", status=404)

    def generate_progress():
        url = task_details.get('url')
        options = task_details.get('options', {})
        download_type = 'video' if 'resolution' in options else 'music'
        
        try:
            if "spotify.com" in url:
                if not sp: raise Exception("Spotify not configured.")
                track = sp.track(url.split('/')[-1].split('?')[0])
                search_query = f"{track['artists'][0]['name']} - {track['name']}"
                info_cmd = ['yt-dlp', '--get-id', f"ytsearch1:{search_query}"]
                yt_id = subprocess.run(info_cmd, capture_output=True, text=True, check=True).stdout.strip()
                if not yt_id: raise Exception("Could not find song on YouTube.")
                url = f"https://www.youtube.com/watch?v={yt_id}"

            info_cmd = ['yt-dlp', '--print-json', '--no-warnings', url]
            info = json.loads(subprocess.run(info_cmd, capture_output=True, text=True, check=True).stdout)
            
            if 'entries' in info: info = info['entries'][0]

            ext = options.get('format', 'mp4') if download_type == 'video' else options.get('format', 'flac')
            final_filename = f"{sanitize_filename(info.get('title', 'video'))}-{info.get('id', 'u')}.{ext}"
            
            cmd = ['yt-dlp', '--progress', '--no-warnings', '-o', os.path.join(DOWNLOAD_DIR, final_filename)]
            
            if download_type == 'music':
                cmd.extend(['-x', '--audio-format', ext, '--audio-quality', options.get('quality', '0')])
                if options.get('metadata'): cmd.append('--add-metadata')
                if options.get('thumbnail'): cmd.append('--embed-thumbnail')
            else:
                cmd.extend(['-f', f"bestvideo[height<={options.get('resolution', '1080')}]+bestaudio/best", '--merge-output-format', ext])
            
            cmd.append(url)

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)
            
            progress_regex = re.compile(r"\[download\]\s+([0-9.]+)%")
            for line in iter(process.stdout.readline, ''):
                match = progress_regex.search(line)
                if match: yield f"data: {match.group(1)}\n\n"
            
            process.wait()

            if process.returncode == 0:
                yield f"event: done\ndata: {final_filename}\n\n"
            else:
                yield f"event: error\ndata: {process.stderr.read()}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"
        finally:
            if task_id in download_tasks: del download_tasks[task_id]

    return Response(generate_progress(), mimetype='text/event-stream')

@app.route('/api/files')
def list_files():
    files = [{'name': f, 'size': os.path.getsize(os.path.join(DOWNLOAD_DIR, f))} for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]
    return jsonify(sorted(files, key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x['name'])), reverse=True))

@app.route('/api/delete', methods=['POST'])
def delete_file():
    filename = request.json.get('filename')
    file_path = os.path.join(DOWNLOAD_DIR, os.path.basename(filename))
    if os.path.exists(file_path):
        os.remove(file_path)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'File not found'}), 404

@app.route('/api/thumbnail')
def thumbnail_proxy():
    url = request.args.get('url')
    if not url: return Response(status=400)
    try:
        response = requests.get(url, stream=True, timeout=5)
        response.raise_for_status()
        return Response(response.iter_content(chunk_size=10240), content_type=response.headers['Content-Type'])
    except:
        return Response(status=500)

@app.route('/api/search')
def search():
    query, s_type, page = request.args.get('q'), request.args.get('type', 'song'), int(request.args.get('page', 1))
    search_query = f"ytsearch30:{query}{' official audio' if s_type == 'song' else ''}"
    proc = subprocess.run(['yt-dlp', '--dump-json', '--flat-playlist', search_query], capture_output=True, text=True, check=True)
    results = [json.loads(line) for line in proc.stdout.strip().split('\n') if line]
    paginated = results[(page - 1) * 10 : page * 10]
    return jsonify({'results': [{'title': i.get('title'), 'author': i.get('uploader'), 'thumbnail': i.get('thumbnail'), 'url': i.get('url')} for i in paginated], 'has_next': len(results) > page * 10})

@app.route('/')
def index(): return render_template('index.html')

@app.route('/downloads/<path:filename>')
def download_file(filename): return send_from_directory(app.config['DOWNLOAD_DIR'], filename, as_attachment=True)

if __name__ == '__main__':
    if '--setup' in sys.argv: run_setup()
    if CLIENT_ID == 'YOUR_CLIENT_ID_HERE': sys.exit("\n!!! Spotify not set up. Run: python app.py --setup !!!\n")
    app.run(host='0.0.0.0', port=5000, threaded=True)

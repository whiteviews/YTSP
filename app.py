# Save this as app.py (Final, Robust version)

import os
import sys
import re
import subprocess
import json
import uuid
import shutil
import threading
import time

# ---
# This setup block is designed to be modified by the --setup flag.
CLIENT_ID = 'YOUR_CLIENT_ID_HERE'
CLIENT_SECRET = 'YOUR_CLIENT_SECRET_HERE'
# ---

from flask import Flask, request, jsonify, render_template, send_from_directory
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

def run_setup():
    """Prompts the user for credentials and rewrites this file with them."""
    print("--- Spotify API Setup ---")
    client_id = input("Enter your Spotify Client ID: ").strip()
    client_secret = input("Enter your Spotify Client Secret: ").strip()
    if not client_id or not client_secret:
        print("\n[ERROR] Both fields are required. Aborting.")
        sys.exit(1)
    try:
        script_path = os.path.abspath(__file__)
        with open(script_path, 'r') as f: lines = f.readlines()
        new_lines = []
        for line in lines:
            if line.strip().startswith("CLIENT_ID ="): new_lines.append(f"CLIENT_ID = '{client_id}'\n")
            elif line.strip().startswith("CLIENT_SECRET ="): new_lines.append(f"CLIENT_SECRET = '{client_secret}'\n")
            else: new_lines.append(line)
        with open(script_path, 'w') as f: f.writelines(new_lines)
        print("\n[SUCCESS] Credentials saved. Run 'python app.py' to start the server.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Failed to write to file: {e}")
        sys.exit(1)

def token_expiry_countdown(expires_at, auth_manager):
    """Runs in the background, prints warnings, and can be used to refresh."""
    while True:
        time_now = int(time.time())
        seconds_remaining = expires_at - time_now

        if seconds_remaining <= 0:
            print(">>> [Spotify Token] Expired. A new token will be fetched on the next API call.")
            # Get new token to restart countdown
            try:
                new_token_info = auth_manager.get_access_token()
                expires_at = new_token_info['expires_at']
                print(">>> [Spotify Token] New token obtained. Restarting countdown.")
                continue # Restart the loop
            except Exception as e:
                print(f">>> [Spotify Token] ERROR: Failed to auto-refresh token: {e}")
                break # Exit thread on failure

        # --- Define warning intervals ---
        five_min_mark = 300
        one_min_mark = 60
        ten_sec_mark = 10

        if seconds_remaining > five_min_mark:
            wait_time = seconds_remaining - five_min_mark
            time.sleep(wait_time)
            print(">>> [Spotify Token] Expires in 5 minutes.")
        elif seconds_remaining > one_min_mark:
            wait_time = seconds_remaining - one_min_mark
            time.sleep(wait_time)
            print(">>> [Spotify Token] Expires in 1 minute.")
        elif seconds_remaining > ten_sec_mark:
            wait_time = seconds_remaining - ten_sec_mark
            time.sleep(wait_time)
            print(">>> [Spotify Token] Expires in 10 seconds.")
        else:
            time.sleep(seconds_remaining) # Sleep for the remaining time


# --- Flask App and Main Logic ---
app = Flask(__name__)
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
if not os.path.exists(DOWNLOAD_DIR): os.makedirs(DOWNLOAD_DIR)
app.config['DOWNLOAD_DIR'] = DOWNLOAD_DIR

# --- Spotipy Initialization (Global Scope) ---
sp = None
auth_manager = None

# --- Helper Functions (The rest of the script is unchanged) ---
def sanitize_filename(name):
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = name.replace(' ', '-')
    return name[:100]

def get_spotify_track_queries(track_id):
    if not sp: return []
    try:
        track = sp.track(track_id)
        return [f"{track['artists'][0]['name']} - {track['name']} Official Audio"]
    except: return []

def get_spotify_playlist_queries(playlist_id):
    if not sp: return [], "playlist"
    try:
        playlist = sp.playlist(playlist_id)
        queries = [f"{item['track']['artists'][0]['name']} - {item['track']['name']}" for item in playlist['tracks']['items'] if item['track']]
        return queries, playlist['name']
    except: return [], "playlist"

@app.route('/')
def index(): return render_template('index.html')

@app.route('/downloads/<path:filename>')
def download_file(filename): return send_from_directory(app.config['DOWNLOAD_DIR'], filename, as_attachment=True)

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url')
    options = data.get('options', {})
    if not url: return jsonify({'success': False, 'error': 'URL is required'}), 400
    temp_folder_path = None
    try:
        if 'spotify.com' in url:
            if not sp: return jsonify({'success': False, 'error': 'Spotify is not configured. Check server logs.'})
            is_playlist = 'playlist' in url
            if is_playlist:
                queries, name = get_spotify_playlist_queries(url.split('/')[-1].split('?')[0])
            else:
                queries = get_spotify_track_queries(url.split('/')[-1].split('?')[0])
                name = queries[0] if queries else "spotify-track"
            if not queries: return jsonify({'success': False, 'error': 'Could not fetch song info from Spotify.'})
            temp_folder_name = f"{sanitize_filename(name)}-{str(uuid.uuid4())[:8]}"
            temp_folder_path = os.path.join(DOWNLOAD_DIR, temp_folder_name)
            os.makedirs(temp_folder_path)
            for i, query in enumerate(queries):
                output_template = os.path.join(temp_folder_path, f'{i+1:03d}-{sanitize_filename(query)}.%(ext)s')
                command = ['yt-dlp', '--no-warnings', '-o', output_template, '-x', '--audio-format', options.get('format', 'flac'), '--audio-quality', '0', f"ytsearch1:{query}"]
                if options.get('metadata'): command.insert(5, '--add-metadata')
                if options.get('thumbnail'): command.insert(5, '--embed-thumbnail')
                subprocess.run(command)
            if is_playlist:
                final_name = f"{sanitize_filename(name)}.zip"
                shutil.make_archive(os.path.join(DOWNLOAD_DIR, sanitize_filename(name)), 'zip', temp_folder_path)
            else:
                final_name = os.listdir(temp_folder_path)[0]
                shutil.move(os.path.join(temp_folder_path, final_name), os.path.join(DOWNLOAD_DIR, final_name))
            shutil.rmtree(temp_folder_path)
            return jsonify({'success': True, 'file_url': f'/downloads/{final_name}', 'filename': final_name})
        elif 'youtube.com' in url or 'youtu.be' in url:
            playlist_mode = 'list=' in url
            download_type = 'video' if 'youtube.com/watch' in url and not playlist_mode else 'music'
            info = json.loads(subprocess.run(['yt-dlp', '--print-json', '--no-warnings', '--playlist-items', '1', url], capture_output=True, text=True).stdout)
            if playlist_mode:
                name = sanitize_filename(info.get('playlist_title', 'playlist'))
                temp_folder_name = f"{name}-{str(uuid.uuid4())[:8]}"
                temp_folder_path = os.path.join(DOWNLOAD_DIR, temp_folder_name)
                os.makedirs(temp_folder_path)
                output_template = os.path.join(temp_folder_path, '%(playlist_index)s-%(title)s.%(ext)s')
            else:
                ext = options.get('format', 'mp4') if download_type == 'video' else options.get('format', 'flac')
                final_name = f"{sanitize_filename(info.get('title', 'video'))}-{info.get('id', 'unknown')}.{ext}"
                output_template = os.path.join(DOWNLOAD_DIR, final_name)
            command = ['yt-dlp', '--no-warnings', '-o', output_template]
            if download_type == 'music':
                command.extend(['-x', '--audio-format', options.get('format', 'flac'), '--audio-quality', '0'])
                if options.get('metadata'): command.append('--add-metadata')
                if options.get('thumbnail'): command.append('--embed-thumbnail')
            else:
                command.extend(['-f', f"bestvideo[height<={options.get('resolution', '1080')}]+bestaudio/best" if options.get('audio') else f"bestvideo[height<={options.get('resolution', '1080')}]", '--merge-output-format', options.get('format', 'mp4')])
            command.append(url)
            if subprocess.run(command).returncode != 0: raise Exception("Download command failed")
            if playlist_mode:
                final_name = f"{name}.zip"
                shutil.make_archive(os.path.join(DOWNLOAD_DIR, name), 'zip', temp_folder_path)
                shutil.rmtree(temp_folder_path)
            return jsonify({'success': True, 'file_url': f'/downloads/{final_name}', 'filename': final_name})
        else: return jsonify({'success': False, 'error': 'Invalid URL.'})
    except Exception as e:
        if temp_folder_path and os.path.exists(temp_folder_path): shutil.rmtree(temp_folder_path)
        print(f"Error in download function: {e}")
        return jsonify({'success': False, 'error': str(e)})

# --- Main execution block ---
if __name__ == '__main__':
    if '--setup' in sys.argv:
        run_setup()

    if CLIENT_ID == 'YOUR_CLIENT_ID_HERE' or CLIENT_SECRET == 'YOUR_CLIENT_SECRET_HERE':
        print("\n" + "="*50)
        print("!!! Spotify credentials not set. Run with --setup flag:")
        print("    python app.py --setup")
        print("="*50 + "\n")
        sys.exit(1)

    try:
        auth_manager = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
        # This one line fixes the DeprecationWarning
        token_info = auth_manager.get_access_token() 
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        print(">>> Spotify connection successful. Starting token expiry countdown.")
        countdown_thread = threading.Thread(
            target=token_expiry_countdown,
            args=(token_info['expires_at'], auth_manager),
            daemon=True
        )
        countdown_thread.start()
        
    except Exception as e:
        print("\n" + "!"*60)
        print("!!! CRITICAL SPOTIFY ERROR: Could not authenticate.")
        print("!!! This usually means your Client ID or Secret is incorrect.")
        print("!!! Please double-check them on developer.spotify.com/dashboard")
        print("!!! and run 'python app.py --setup' again.")
        print(f"!!! Specific Reason: {e}")
        print("!"*60 + "\n")
        sys.exit(1)
        
    app.run(host='0.0.0.0', port=5000)
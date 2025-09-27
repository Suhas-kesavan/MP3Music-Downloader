import os
import sys
import argparse
import re
from pathlib import Path
import yt_dlp
import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, TALB, TPE1, TPE2, TIT2, TRCK, TYER, TCON
import requests
import json
from difflib import SequenceMatcher

class MusicDownloader:
    def __init__(self, output_dir="downloads", auto_metadata=True):
        """Initialize the music downloader with the output directory."""
        self.output_dir = output_dir
        self.auto_metadata = auto_metadata
        self.ensure_dir_exists(output_dir)
    
    def ensure_dir_exists(self, directory):
        """Create directory if it doesn't exist."""
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")
    
    def sanitize_filename(self, filename):
        """Remove invalid characters from filename."""
        return re.sub(r'[\\/*?:"<>|]', "", filename)
    
    def extract_title_artist(self, title):
        """Extract artist and title from YouTube title format."""
        # Common patterns: "Artist - Title", "Artist – Title", "Artist: Title"
        patterns = [
            r"^(.*?)\s*-\s*(.*?)$",
            r"^(.*?)\s*–\s*(.*?)$",
            r"^(.*?)\s*:\s*(.*?)$"
        ]
        
        for pattern in patterns:
            match = re.match(pattern, title)
            if match:
                artist = match.group(1).strip()
                title = match.group(2).strip()
                return artist, title
        
        # No match found, try to find featuring artists
        if " feat" in title.lower() or " ft." in title.lower() or " ft " in title.lower():
            for separator in [" feat. ", " feat ", " ft. ", " ft "]:
                if separator.lower() in title.lower():
                    parts = title.split(separator, 1)
                    if len(parts) == 2:
                        return parts[0].strip(), f"{parts[0].strip()} feat. {parts[1].strip()}"
        
        # If nothing matches, return original as title and Unknown as artist
        return "Unknown Artist", title
    
    def search_musicbrainz(self, title, artist=None):
        """Search MusicBrainz API for metadata."""
        try:
            query = title
            if artist:
                query = f"{artist} {title}"
            
            url = f"https://musicbrainz.org/ws/2/recording/?query={query}&fmt=json"
            headers = {
                "User-Agent": "MusicDownloader/1.0 (your@email.com)"  # Required by MusicBrainz
            }
            
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if "recordings" in data and len(data["recordings"]) > 0:
                    best_match = None
                    best_score = 0
                    
                    for recording in data["recordings"]:
                        # Calculate similarity score
                        rec_title = recording.get("title", "")
                        rec_artist = recording.get("artist-credit", [{}])[0].get("name", "") if recording.get("artist-credit") else ""
                        
                        title_score = SequenceMatcher(None, title.lower(), rec_title.lower()).ratio()
                        artist_score = 0.5  # Default if no artist provided
                        
                        if artist:
                            artist_score = SequenceMatcher(None, artist.lower(), rec_artist.lower()).ratio()
                        
                        # Weighted score - title more important than artist
                        score = (title_score * 0.6) + (artist_score * 0.4)
                        
                        if score > best_score:
                            best_score = score
                            best_match = recording
                    
                    if best_match and best_score > 0.6:  # Only use if good match
                        metadata = {
                            "title": best_match.get("title"),
                            "artist": best_match.get("artist-credit", [{}])[0].get("name") if best_match.get("artist-credit") else None,
                            "album": None,
                            "year": None,
                            "genre": None,
                            "track": None
                        }
                        
                        # Try to get album info
                        if "releases" in best_match and len(best_match["releases"]) > 0:
                            release = best_match["releases"][0]
                            metadata["album"] = release.get("title")
                            
                            if "date" in release:
                                metadata["year"] = release["date"][:4] if release["date"] else None
                            
                            if "track-number" in release:
                                metadata["track"] = release["track-number"]
                        
                        # Filter out None values
                        return {k: v for k, v in metadata.items() if v is not None}
            
            return {}
        except Exception as e:
            print(f"Error fetching metadata from MusicBrainz: {e}")
            return {}
    
    def get_metadata_from_youtube(self, info):
        """Extract metadata from YouTube info."""
        title = info.get('title', '')
        artist, extracted_title = self.extract_title_artist(title)
        
        metadata = {
            'title': extracted_title,
            'artist': artist,
        }
        
        # Try to get album from YouTube info
        if 'album' in info:
            metadata['album'] = info['album']
        
        # Try to get track number
        if 'track' in info:
            metadata['track'] = info['track']
        elif 'playlist_index' in info:
            metadata['track'] = str(info['playlist_index'])
        
        # Try to get upload date as year
        if 'upload_date' in info:
            metadata['year'] = info['upload_date'][:4]  # First 4 chars should be year
        
        # Try to get genre
        if 'genre' in info:
            if isinstance(info['genre'], list) and info['genre']:
                metadata['genre'] = info['genre'][0]
            elif isinstance(info['genre'], str):
                metadata['genre'] = info['genre']
        
        return metadata
    
    def enrich_metadata(self, basic_metadata):
        """Enrich metadata with MusicBrainz if possible."""
        if not self.auto_metadata:
            return basic_metadata
        
        title = basic_metadata.get('title')
        artist = basic_metadata.get('artist')
        
        if title:
            mb_metadata = self.search_musicbrainz(title, artist)
            # Merge metadata, prioritizing MusicBrainz but keeping YouTube data as fallback
            for key, value in mb_metadata.items():
                basic_metadata[key] = value
        
        return basic_metadata
    
    def download_song(self, url, metadata=None):
        """Download a single song and update its metadata."""
        if metadata is None:
            metadata = {}
        
        # Configure yt-dlp options
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
            'quiet': False,
            'no_warnings': False,
        }
        
        # First extract info without downloading
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Get metadata from YouTube
            youtube_metadata = self.get_metadata_from_youtube(info)
            
            # Merge with user-provided metadata, user's takes precedence
            combined_metadata = {**youtube_metadata, **metadata}
            
            # Enrich with MusicBrainz if enabled
            final_metadata = self.enrich_metadata(combined_metadata)
            
            # Get artist and title for folder name
            artist = final_metadata.get('artist', 'Unknown Artist')
            title = final_metadata.get('title', 'Unknown Title')
            album = final_metadata.get('album', 'Single')
            
            # For singles, create artist folder with song file
            if album == 'Single' or not album:
                folder_name = self.sanitize_filename(artist)
            else:
                # For album tracks, create artist/album folder
                folder_name = self.sanitize_filename(f"{artist}/{album}")
            
            output_path = os.path.join(self.output_dir, folder_name)
            self.ensure_dir_exists(output_path)
            
            # Update download options with path
            ydl_opts['outtmpl'] = f'{output_path}/%(title)s.%(ext)s'
        
        # Now download with the configured options
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
        
        # Update metadata
        self.update_metadata(downloaded_file, final_metadata)
        
        print(f"Downloaded with metadata: {final_metadata}")
        return downloaded_file
    
    def download_album(self, url, album_metadata=None):
        """Download an album (playlist) and update metadata for all songs."""
        if album_metadata is None:
            album_metadata = {}
        
        # Configure yt-dlp options for info extraction
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Check if this is a playlist
            if 'entries' not in info:
                print("The URL does not appear to be a playlist. Downloading as single song instead.")
                return self.download_song(url, album_metadata)
            
            # Try to get album name from playlist title
            playlist_title = info.get('title', 'Unknown Album')
            
            # If user provided album name, use that instead
            album_name = album_metadata.get('album', playlist_title)
            
            # Try to get artist from the first video or user input
            artist_name = album_metadata.get('artist')
            if not artist_name and info['entries'] and info['entries'][0]:
                # Extract artist from first track
                first_track_info = info['entries'][0]
                youtube_metadata = self.get_metadata_from_youtube(first_track_info)
                artist_name = youtube_metadata.get('artist', 'Various Artists')
            
            if not artist_name:
                artist_name = 'Various Artists'
            
            # Create album folder
            album_folder = self.sanitize_filename(f"{artist_name}/{album_name}")
            album_path = os.path.join(self.output_dir, album_folder)
            self.ensure_dir_exists(album_path)
            
            # Base metadata for all tracks
            base_metadata = {
                'artist': artist_name,
                'album': album_name,
                'year': album_metadata.get('year'),
                'genre': album_metadata.get('genre')
            }
            
            # Filter out None values
            base_metadata = {k: v for k, v in base_metadata.items() if v is not None}
        
        # Configure yt-dlp options for download
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
            'outtmpl': f'{album_path}/%(playlist_index)s - %(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
        }
        
        # Download the album
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Process each song in the playlist
            if 'entries' in info:
                for idx, entry in enumerate(info['entries'], 1):
                    if entry:
                        filename = ydl.prepare_filename(entry).replace('.webm', '.mp3').replace('.m4a', '.mp3')
                        
                        # Get metadata from YouTube
                        track_youtube_metadata = self.get_metadata_from_youtube(entry)
                        
                        # Combine with base album metadata
                        track_metadata = {**track_youtube_metadata, **base_metadata}
                        
                        # Ensure track number
                        if 'track' not in track_metadata:
                            track_metadata['track'] = str(idx)
                        
                        # Enrich with MusicBrainz if enabled
                        final_track_metadata = self.enrich_metadata(track_metadata)
                        
                        # Update metadata for this track
                        self.update_metadata(filename, final_track_metadata)
                        print(f"Track {idx}: Updated metadata: {final_track_metadata}")
        
        return album_path
    
    def update_metadata(self, file_path, metadata):
        """Update metadata of an MP3 file."""
        try:
            # Check if file exists
            if not os.path.isfile(file_path):
                print(f"Error: File not found: {file_path}")
                return False
            
            # Try to create ID3 tags if they don't exist
            try:
                audio = ID3(file_path)
            except:
                # If ID3 tag doesn't exist, create one
                audio = ID3()
            
            # Update metadata tags
            if 'title' in metadata:
                audio['TIT2'] = TIT2(encoding=3, text=metadata['title'])
            if 'artist' in metadata:
                audio['TPE1'] = TPE1(encoding=3, text=metadata['artist'])
                audio['TPE2'] = TPE2(encoding=3, text=metadata['artist'])  # Album artist
            if 'album' in metadata:
                audio['TALB'] = TALB(encoding=3, text=metadata['album'])
            if 'track' in metadata:
                audio['TRCK'] = TRCK(encoding=3, text=metadata['track'])
            if 'year' in metadata:
                audio['TYER'] = TYER(encoding=3, text=metadata['year'])
            if 'genre' in metadata:
                audio['TCON'] = TCON(encoding=3, text=metadata['genre'])
            
            # Save changes
            audio.save(file_path)
            print(f"Updated metadata for: {os.path.basename(file_path)}")
            return True
            
        except Exception as e:
            print(f"Error updating metadata: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description='Download music and update metadata')
    parser.add_argument('url', help='URL of the song or album to download')
    parser.add_argument('--output', '-o', default='downloads', help='Output directory')
    parser.add_argument('--album', help='Album name (optional, auto-detected)')
    parser.add_argument('--artist', help='Artist name (optional, auto-detected)')
    parser.add_argument('--title', help='Song title (optional, auto-detected)')
    parser.add_argument('--year', help='Release year (optional, auto-detected)')
    parser.add_argument('--genre', help='Music genre (optional, auto-detected)')
    parser.add_argument('--album-mode', '-a', action='store_true', help='Download as album (forces playlist download)')
    parser.add_argument('--no-auto-metadata', action='store_true', help='Disable automatic metadata detection')
    
    args = parser.parse_args()
    
    downloader = MusicDownloader(args.output, not args.no_auto_metadata)
    
    metadata = {
        'artist': args.artist,
        'album': args.album,
        'title': args.title,
        'year': args.year,
        'genre': args.genre
    }
    
    # Filter out None values
    metadata = {k: v for k, v in metadata.items() if v is not None}
    
    if args.album_mode:
        print(f"Downloading album from: {args.url}")
        album_path = downloader.download_album(args.url, metadata)
        print(f"Album downloaded to: {album_path}")
    else:
        print(f"Downloading song from: {args.url}")
        song_path = downloader.download_song(args.url, metadata)
        print(f"Song downloaded to: {song_path}")

if __name__ == "__main__":
    main()

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
from urllib.parse import urlparse
import time

class MusicDownloader:
    def __init__(self, output_dir="downloads", auto_metadata=True, download_album_art=True):
        """Initialize the music downloader with the output directory."""
        self.output_dir = output_dir
        self.auto_metadata = auto_metadata
        self.download_album_art = download_album_art
        self.ensure_dir_exists(output_dir)
        self.check_ytdlp_version()
    
    def ensure_dir_exists(self, directory):
        """Create directory if it doesn't exist."""
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")
    
    def check_ytdlp_version(self):
        """Check yt-dlp version and provide update information if needed."""
        try:
            import yt_dlp
            version = yt_dlp.version.__version__
            print(f"Using yt-dlp version: {version}")
            
            # If we encounter errors, this will be helpful information
            if hasattr(yt_dlp, '__version__'):
                print(f"Full version info: {yt_dlp.__version__}")
                
        except Exception as e:
            print(f"Could not determine yt-dlp version: {e}")
            print("Consider updating yt-dlp with: pip install --upgrade yt-dlp")
    
    def list_formats(self, url):
        """List available formats for a URL (useful for debugging)."""
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'listformats': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'formats' in info:
                    print(f"Available formats for {url}:")
                    for fmt in info['formats']:
                        print(f"  {fmt.get('format_id', 'N/A')} - {fmt.get('ext', 'N/A')} - {fmt.get('format_note', 'N/A')}")
                else:
                    print("No format information available")
        except Exception as e:
            print(f"Error listing formats: {e}")
    
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
            
            url = f"https://musicbrainz.org/ws/2/recording/?query={query}&fmt=json&inc=releases+artist-credits+tags"
            headers = {
                "User-Agent": "MusicDownloader/1.0 (your@email.com)"  # Required by MusicBrainz
            }
            
            # Add delay to respect MusicBrainz rate limiting
            time.sleep(1)
            
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
                            "artist": None,
                            "album": None,
                            "year": None,
                            "genre": None,
                            "track": None,
                            "album_art_url": None
                        }
                        
                        # Get artist information
                        if best_match.get("artist-credit"):
                            artists = []
                            for artist_credit in best_match["artist-credit"]:
                                if isinstance(artist_credit, dict) and "artist" in artist_credit:
                                    artists.append(artist_credit["artist"]["name"])
                                elif isinstance(artist_credit, dict) and "name" in artist_credit:
                                    artists.append(artist_credit["name"])
                            if artists:
                                metadata["artist"] = ", ".join(artists)
                        
                        # Get genre from tags
                        if "tags" in best_match and best_match["tags"]:
                            # Get the most popular tag as genre
                            sorted_tags = sorted(best_match["tags"], key=lambda x: x.get("count", 0), reverse=True)
                            if sorted_tags:
                                metadata["genre"] = sorted_tags[0]["name"]
                        
                        # Try to get album info and cover art
                        if "releases" in best_match and len(best_match["releases"]) > 0:
                            release = best_match["releases"][0]
                            metadata["album"] = release.get("title")
                            
                            if "date" in release:
                                metadata["year"] = release["date"][:4] if release["date"] else None
                            
                            # Get track number from release
                            if "track-number" in release:
                                metadata["track"] = release["track-number"]
                            
                            # Try to get cover art from Cover Art Archive
                            release_id = release.get("id")
                            if release_id:
                                cover_art_url = self.get_cover_art_url(release_id)
                                if cover_art_url:
                                    metadata["album_art_url"] = cover_art_url
                        
                        # Filter out None values
                        return {k: v for k, v in metadata.items() if v is not None}
            
            return {}
        except Exception as e:
            print(f"Error fetching metadata from MusicBrainz: {e}")
            return {}
    
    def get_cover_art_url(self, release_id):
        """Get cover art URL from MusicBrainz Cover Art Archive."""
        try:
            url = f"https://coverartarchive.org/release/{release_id}"
            headers = {
                "User-Agent": "MusicDownloader/1.0 (your@email.com)"
            }
            
            # Add delay to respect rate limiting
            time.sleep(0.5)
            
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if "images" in data and len(data["images"]) > 0:
                    # Get the first (usually front) cover image
                    for image in data["images"]:
                        if image.get("front", False) or not any(img.get("front", False) for img in data["images"]):
                            return image.get("image")
            return None
        except Exception as e:
            print(f"Error fetching cover art: {e}")
            return None
    
    def download_album_art(self, url, file_path):
        """Download album art and return the image data."""
        try:
            headers = {
                "User-Agent": "MusicDownloader/1.0 (your@email.com)"
            }
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                return response.content
            return None
        except Exception as e:
            print(f"Error downloading album art: {e}")
            return None
    
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
        
        # Try to get artist from YouTube info (channel name, uploader, etc.)
        if 'uploader' in info and info['uploader']:
            # Use uploader as artist if we couldn't extract from title
            if artist == "Unknown Artist":
                metadata['artist'] = info['uploader']
        
        if 'channel' in info and info['channel']:
            # Use channel name as artist if available and more reliable
            if artist == "Unknown Artist" or "Topic" in info['channel']:
                clean_channel = info['channel'].replace(" - Topic", "").replace("VEVO", "").strip()
                if clean_channel:
                    metadata['artist'] = clean_channel
        
        # Try to get track number
        if 'track' in info:
            metadata['track'] = info['track']
        elif 'playlist_index' in info:
            metadata['track'] = str(info['playlist_index'])
        
        # Try to get upload date as year
        if 'upload_date' in info:
            metadata['year'] = info['upload_date'][:4]  # First 4 chars should be year
        
        # Try to get genre from YouTube info
        if 'genre' in info:
            if isinstance(info['genre'], list) and info['genre']:
                metadata['genre'] = info['genre'][0]
            elif isinstance(info['genre'], str):
                metadata['genre'] = info['genre']
        
        # Try to get categories as genre fallback
        if 'categories' in info and info['categories'] and 'genre' not in metadata:
            if isinstance(info['categories'], list) and info['categories']:
                # Filter out generic categories
                categories = [cat for cat in info['categories'] if cat.lower() not in ['music', 'entertainment']]
                if categories:
                    metadata['genre'] = categories[0]
        
        # Try to get thumbnail for album art
        if 'thumbnail' in info:
            metadata['album_art_url'] = info['thumbnail']
        elif 'thumbnails' in info and info['thumbnails']:
            # Get the highest quality thumbnail
            thumbnails = sorted(info['thumbnails'], key=lambda x: x.get('width', 0) * x.get('height', 0), reverse=True)
            if thumbnails:
                metadata['album_art_url'] = thumbnails[0]['url']
        
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
        
        # Configure yt-dlp options with better format selection and error handling
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best[height<=720]/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
            'quiet': False,
            'no_warnings': False,
            'ignoreerrors': False,
            'extract_flat': False,
        }
        
        # First extract info without downloading
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'ignoreerrors': True}) as ydl:
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
        
        except Exception as e:
            print(f"Error extracting video info: {e}")
            # Use basic metadata if info extraction fails
            final_metadata = metadata if metadata else {'title': 'Unknown Title', 'artist': 'Unknown Artist'}
            output_path = os.path.join(self.output_dir, 'Unknown Artist')
            self.ensure_dir_exists(output_path)
            ydl_opts['outtmpl'] = f'{output_path}/%(title)s.%(ext)s'
        
        # Now download with the configured options
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
            
            # Update metadata
            if os.path.exists(downloaded_file):
                self.update_metadata(downloaded_file, final_metadata)
                print(f"Downloaded with metadata: {final_metadata}")
                return downloaded_file
            else:
                print(f"Warning: Downloaded file not found at expected location: {downloaded_file}")
                return None
                
        except Exception as e:
            print(f"Error downloading video: {e}")
            print("This might be due to:")
            print("1. Video being unavailable or private")
            print("2. Geographic restrictions")
            print("3. YouTube format changes")
            print("4. Network issues")
            print("\nSuggestions:")
            print("- Try updating yt-dlp: pip install --upgrade yt-dlp")
            print("- Check if the video is accessible in your browser")
            print("- Try a different video URL")
            return None
    
    def download_album(self, url, album_metadata=None):
        """Download an album (playlist) and update metadata for all songs."""
        if album_metadata is None:
            album_metadata = {}
        
        # Configure yt-dlp options for info extraction with error handling
        info_opts = {
            'quiet': True,
            'extract_flat': True,  # Only extract basic info first
            'ignoreerrors': True,  # Continue even if some videos fail
        }
        
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except Exception as e:
                print(f"Error extracting playlist info: {e}")
                print("Trying to download as single song instead...")
                return self.download_song(url, album_metadata)
            
            # Check if this is a playlist
            if 'entries' not in info:
                print("The URL does not appear to be a playlist. Downloading as single song instead.")
                return self.download_song(url, album_metadata)
            
            # Try to get album name from playlist title
            playlist_title = info.get('title', 'Unknown Album')
            
            # If user provided album name, use that instead
            album_name = album_metadata.get('album', playlist_title)
            
            # Try to get artist from multiple sources
            artist_name = album_metadata.get('artist')
            
            # Try to extract artist from playlist uploader/channel
            if not artist_name:
                if 'uploader' in info and info['uploader']:
                    artist_name = info['uploader']
                elif 'channel' in info and info['channel']:
                    clean_channel = info['channel'].replace(" - Topic", "").replace("VEVO", "").strip()
                    if clean_channel:
                        artist_name = clean_channel
            
            # Fallback: try to get artist from first track
            if not artist_name and info['entries']:
                # Get info from first available track
                for entry in info['entries']:
                    if entry:
                        # Extract full info for first track
                        try:
                            with yt_dlp.YoutubeDL({'quiet': True, 'ignoreerrors': True}) as track_ydl:
                                first_track_info = track_ydl.extract_info(entry['url'], download=False)
                                youtube_metadata = self.get_metadata_from_youtube(first_track_info)
                                potential_artist = youtube_metadata.get('artist', '')
                                if potential_artist and potential_artist != 'Unknown Artist':
                                    artist_name = potential_artist
                                    break
                        except:
                            continue
            
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
        
        # Configure yt-dlp options for download with better error handling
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best[height<=720]/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
            'outtmpl': f'{album_path}/%(playlist_index)s - %(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'ignoreerrors': True,  # Continue downloading even if some videos fail
            'extract_flat': False,
        }
        
        # Download the album
        downloaded_files = []
        failed_videos = []
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                
                # Process each song in the playlist
                if 'entries' in info:
                    for idx, entry in enumerate(info['entries'], 1):
                        if entry is None:
                            print(f"Track {idx}: Skipped (unavailable)")
                            failed_videos.append(idx)
                            continue
                        
                        try:
                            print(f"\nProcessing Track {idx}...")
                            filename = ydl.prepare_filename(entry).replace('.webm', '.mp3').replace('.m4a', '.mp3')
                            
                            # Check if file actually exists
                            if not os.path.exists(filename):
                                print(f"Track {idx}: File not found after download, skipping metadata update")
                                failed_videos.append(idx)
                                continue
                            
                            # Get detailed metadata from YouTube for this track
                            track_youtube_metadata = self.get_metadata_from_youtube(entry)
                            
                            # Combine with base album metadata (base takes precedence for album info)
                            track_metadata = {**track_youtube_metadata, **base_metadata}
                            
                            # Ensure track number is set correctly
                            track_metadata['track'] = str(idx)
                            
                            # If artist is still generic, try to extract better artist info
                            if track_metadata.get('artist') in ['Unknown Artist', 'Various Artists', None]:
                                # Try to extract from track title
                                track_title = entry.get('title', '')
                                extracted_artist, _ = self.extract_title_artist(track_title)
                                if extracted_artist and extracted_artist != 'Unknown Artist':
                                    track_metadata['artist'] = extracted_artist
                            
                            # Enrich with MusicBrainz if enabled
                            print(f"  └─ Searching for additional metadata...")
                            final_track_metadata = self.enrich_metadata(track_metadata)
                            
                            # Update metadata for this track
                            print(f"  └─ Updating metadata...")
                            if self.update_metadata(filename, final_track_metadata):
                                downloaded_files.append(filename)
                                print(f"✓ Track {idx}: Successfully processed")
                            else:
                                print(f"⚠ Track {idx}: Downloaded but failed to update metadata")
                                downloaded_files.append(filename)
                        
                        except Exception as e:
                            print(f"✗ Track {idx}: Error processing - {str(e)}")
                            failed_videos.append(idx)
                            continue
            
            except Exception as e:
                print(f"Error during album download: {e}")
                if not downloaded_files:
                    raise
        
        # Report results
        print(f"\nDownload completed!")
        print(f"Successfully downloaded: {len(downloaded_files)} tracks")
        if failed_videos:
            print(f"Failed/skipped tracks: {len(failed_videos)} (positions: {failed_videos})")
        
        return album_path
    
    def update_metadata(self, file_path, metadata):
        """Update metadata of an MP3 file including album art."""
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
                print(f"  └─ Title: {metadata['title']}")
            
            if 'artist' in metadata:
                audio['TPE1'] = TPE1(encoding=3, text=metadata['artist'])
                audio['TPE2'] = TPE2(encoding=3, text=metadata['artist'])  # Album artist
                print(f"  └─ Artist: {metadata['artist']}")
            
            if 'album' in metadata:
                audio['TALB'] = TALB(encoding=3, text=metadata['album'])
                print(f"  └─ Album: {metadata['album']}")
            
            if 'track' in metadata:
                audio['TRCK'] = TRCK(encoding=3, text=metadata['track'])
                print(f"  └─ Track: {metadata['track']}")
            
            if 'year' in metadata:
                audio['TYER'] = TYER(encoding=3, text=metadata['year'])
                print(f"  └─ Year: {metadata['year']}")
            
            if 'genre' in metadata:
                audio['TCON'] = TCON(encoding=3, text=metadata['genre'])
                print(f"  └─ Genre: {metadata['genre']}")
            
            # Download and add album art
            if self.download_album_art and 'album_art_url' in metadata:
                album_art_data = self.download_album_art(metadata['album_art_url'], file_path)
                if album_art_data:
                    # Determine MIME type based on content
                    mime_type = 'image/jpeg'  # Default
                    if album_art_data.startswith(b'\x89PNG'):
                        mime_type = 'image/png'
                    elif album_art_data.startswith(b'GIF'):
                        mime_type = 'image/gif'
                    elif album_art_data.startswith(b'\xff\xd8'):
                        mime_type = 'image/jpeg'
                    
                    # Add album art to ID3 tags
                    audio['APIC'] = APIC(
                        encoding=3,  # UTF-8
                        mime=mime_type,
                        type=3,  # Cover (front)
                        desc='Cover',
                        data=album_art_data
                    )
                    print(f"  └─ Album art: Downloaded and embedded")
                else:
                    print(f"  └─ Album art: Failed to download")
            elif not self.download_album_art:
                print(f"  └─ Album art: Skipped (disabled)")
            
            # Save changes
            audio.save(file_path)
            print(f"✓ Updated metadata for: {os.path.basename(file_path)}")
            return True
            
        except Exception as e:
            print(f"Error updating metadata: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description='Download music and update metadata')
    parser.add_argument('url', nargs='?', help='URL of the song or album to download')
    parser.add_argument('--output', '-o', default='downloads', help='Output directory')
    parser.add_argument('--album', help='Album name (optional, auto-detected)')
    parser.add_argument('--artist', help='Artist name (optional, auto-detected)')
    parser.add_argument('--title', help='Song title (optional, auto-detected)')
    parser.add_argument('--year', help='Release year (optional, auto-detected)')
    parser.add_argument('--genre', help='Music genre (optional, auto-detected)')
    parser.add_argument('--album-mode', '-a', action='store_true', help='Download as album (forces playlist download)')
    parser.add_argument('--no-auto-metadata', action='store_true', help='Disable automatic metadata detection')
    parser.add_argument('--no-album-art', action='store_true', help='Skip downloading album art')
    parser.add_argument('--list-formats', action='store_true', help='List available formats for the URL (for debugging)')
    parser.add_argument('--update-ytdlp', action='store_true', help='Update yt-dlp before downloading')
    
    args = parser.parse_args()
    
    if args.update_ytdlp:
        print("Updating yt-dlp...")
        import subprocess
        try:
            result = subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print("yt-dlp updated successfully!")
            else:
                print(f"Failed to update yt-dlp: {result.stderr}")
        except Exception as e:
            print(f"Error updating yt-dlp: {e}")
        return
    
    if not args.url:
        parser.error("URL is required unless using --update-ytdlp")
    
    downloader = MusicDownloader(args.output, not args.no_auto_metadata, not args.no_album_art)
    
    if args.list_formats:
        downloader.list_formats(args.url)
        return
    
    metadata = {
        'artist': args.artist,
        'album': args.album,
        'title': args.title,
        'year': args.year,
        'genre': args.genre
    }
    
    # Filter out None values
    metadata = {k: v for k, v in metadata.items() if v is not None}
    
    try:
        if args.album_mode:
            print(f"Downloading album from: {args.url}")
            album_path = downloader.download_album(args.url, metadata)
            if album_path:
                print(f"Album downloaded to: {album_path}")
            else:
                print("Album download failed or was incomplete")
        else:
            print(f"Downloading song from: {args.url}")
            song_path = downloader.download_song(args.url, metadata)
            if song_path:
                print(f"Song downloaded to: {song_path}")
            else:
                print("Song download failed")
    except Exception as e:
        print(f"Download failed with error: {e}")
        print("\nTroubleshooting steps:")
        print("1. Update yt-dlp: python MusicDownloader.py --update-ytdlp")
        print("2. Check available formats: python MusicDownloader.py --list-formats <URL>")
        print("3. Verify the URL is accessible in your browser")
        sys.exit(1)

if __name__ == "__main__":
    main()

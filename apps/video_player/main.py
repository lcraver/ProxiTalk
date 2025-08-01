import os
import subprocess
import time
import tempfile
import threading
from interfaces import AppBase
from PIL import Image, ImageDraw


class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.video_path = None
        self.playing = False
        self.paused = False
        self.process = None
        self.font = context["fonts"]["small"]
        self.width = context["screen_width"]
        self.height = context["screen_height"]
        self.current_time = 0
        self.duration = 0
        self.emulator = context["emulator"]
        self.play_sfx = context["audio"]["play_sfx"]  # ProxiTalk audio system
        self.path = context["app_path"]

        # Video simulation
        self.frame_count = 0
        self.t = 0  # Tick counter for updates
        self.total_frames = 0
        self.fps = 12  # Device FPS - reduced to 12fps for better performance
        self.source_fps = 24  # Original video FPS
        self.target_fps = 12  # Target display FPS (reduced to 12fps)
        self.frame_cache = {}  # Cache for extracted frames
        self.temp_dir = None  # Temporary directory for frame extraction

        # Optimized buffering for 12fps device (more conservative)
        # Buffer 10 seconds worth of frames (120 frames at 12fps)
        self.buffer_size = 120
        self.extract_batch_size = 60  # Extract 5 seconds at a time (60 frames)
        self.buffer_threshold = 24  # Start buffering when we have less than 2 seconds left
        self.aggressive_preload = True  # Enable aggressive preloading for smooth playback

        # Frame extraction state management
        self._extracting_frames = False  # Flag to prevent concurrent extractions
        self._preloading_frames = False  # Flag to prevent concurrent preloading
        self._background_extractor_running = False  # Background extraction thread
        # Signal to stop background extraction
        self._stop_background_extraction = False

        # Audio playback using new streaming system
        self.audio_temp_file = None  # Temporary audio file for video audio
        self.video_start_time = None  # Time when video playback started
        self.audio_start_time = None  # Time when audio started playing
        self.pause_start_time = None  # Time when pause started
        self.audio_ready = False  # Flag to indicate audio is ready for playback
        self.waiting_for_audio = False  # Flag to indicate we're waiting for audio setup

        # Video playlist management
        self.video_directory = None
        self.video_files = []
        self.current_video_index = 0
        self.video_extensions = ['.mp4', '.avi',
                                 '.mov', '.mkv', '.wmv', '.flv', '.webm']

        # UI toggle
        self.show_ui = True  # Toggle for showing UI overlay

        # Cached ffmpeg paths to avoid repeated searches
        # Will store {"ffmpeg": "/path/to/ffmpeg", "ffprobe": "/path/to/ffprobe"}
        self._ffmpeg_cache = {}

    def start(self):
        # Check if there's a pending video file from code editor
        pending_file = self.context.get('pending_video_file', None)
        if pending_file:
            print(f"[Video Player] Found pending video file: {pending_file}")
            # Clear the pending file
            self.context['pending_video_file'] = None
            # Use onopen to handle the file
            self.onopen(pending_file)
            return

        self._clear_screen()
        self.context["drawing"]["draw_text"](
            "Video Player", 2, 2, self.font, 255)
        self.context["drawing"]["draw_text"](
            "Loading videos from app folder...", 2, 15, self.font, 255)
        print("[Video Player] App started, scanning app folder for videos...")

        # Set the app directory as the video directory
        self.video_directory = self.context["app_path"]
        print(f"[Video Player] Scanning app directory: {self.video_directory}")

        # Find all video files in the app directory
        self._scan_video_files()

        if not self.video_files:
            print("[Video Player] No video files found in app directory")
            self.context["drawing"]["draw_text"](
                "No video files found in app folder.", 2, 28, self.font, 255)
            self.context["drawing"]["draw_text"](
                "Place video files in the app folder", 2, 41, self.font, 255)
            self.context["drawing"]["draw_text"](
                "or select from code editor.", 2, 54, self.font, 255)
            return

        # Start playing the first video automatically
        self.current_video_index = 0
        self.video_path = os.path.join(
            self.video_directory, self.video_files[self.current_video_index])
        print(f"[Video Player] Auto-playing first video: {self.video_path}")

        self._get_video_info()
        self._start_playback()

    def onopen(self, file_path=None):
        print(f"[Video Player] onopen called with file_path: {file_path}")
        print(f"[Video Player] Current working directory: {os.getcwd()}")
        print(
            f"[Video Player] File exists check: {os.path.exists(file_path) if file_path else 'No file path'}")

        # Immediately clear the screen to take control
        self._clear_screen()
        self.context["drawing"]["draw_text"](
            "Loading videos...", 2, 2, self.font, 255)

        if not file_path:
            print(f"[Video Player] No file path provided")
            self._show_error("No file selected.")
            return

        if not os.path.isfile(file_path):
            print(f"[Video Player] File does not exist: {file_path}")
            print(
                f"[Video Player] Absolute path: {os.path.abspath(file_path)}")
            self._show_error("File not found.")
            return

        # Get the directory containing the selected file
        self.video_directory = os.path.dirname(file_path)
        print(f"[Video Player] Scanning directory: {self.video_directory}")

        # Find all video files in the directory
        self._scan_video_files()

        if not self.video_files:
            print(f"[Video Player] No video files found in directory")
            self._show_error("No video files found in directory.")
            return

        # Find the index of the selected file or start with the first video
        selected_file = os.path.basename(file_path)
        try:
            self.current_video_index = self.video_files.index(selected_file)
            print(
                f"[Video Player] Starting with selected video at index {self.current_video_index}: {selected_file}")
        except ValueError:
            # If the selected file isn't a video, start with the first video
            self.current_video_index = 0
            print(
                f"[Video Player] Selected file is not a video, starting with first video: {self.video_files[0]}")

        # Set the current video path
        self.video_path = os.path.join(
            self.video_directory, self.video_files[self.current_video_index])
        print(f"[Video Player] Playing: {self.video_path}")

        self._get_video_info()
        self._start_playback()

    def update(self):
        """Update method called by ProxiTalk framework - optimized for performance"""
        if not self.playing:
            return

        self.t += 1

        # If we're waiting for audio to be ready, don't start video timing yet
        if self.waiting_for_audio:
            if self.audio_ready:
                # Audio is now ready - start video timing
                self.video_start_time = time.time()
                self.waiting_for_audio = False
                print(
                    f"[Video Player] Audio ready - starting video playback synchronization")
                # Clear the loading message
                self.context["drawing"]["clear_overlay_area"](
                    0, self.height - 20, self.width, 20)
            else:
                # Still waiting - just show a loading frame occasionally
                if self.t % 12 == 0:  # Every 12 updates
                    self._draw_video_frame()
                return

        # Check if we should advance to the next frame based on audio timing
        if not self.paused:
            current_time = time.time()
            frame_changed = False

            # Calculate how much time has passed since video started
            if self.video_start_time:
                elapsed_time = current_time - self.video_start_time

                # Calculate which frame we should be showing based on elapsed time
                # Use the source video's original framerate for proper timing
                target_frame = int(elapsed_time * self.source_fps)

                # Map source frame to display frame (since we extract at target_fps)
                # We need to scale down from source fps to target fps
                display_frame = int(
                    target_frame * (self.target_fps / self.source_fps))
                display_frame = min(display_frame, self.total_frames - 1)

                # If we're significantly behind, skip frames to catch up
                frame_lag = display_frame - self.frame_count
                # If more than 3 frames behind (more aggressive)
                if frame_lag > 3:
                    # Skip frames to catch up quickly
                    # Skip up to 10 frames max
                    skip_frames = min(frame_lag - 1, 10)
                    print(
                        f"[Video Player] Catching up: skipping {skip_frames} frames from {self.frame_count} to {self.frame_count + skip_frames} (lag: {frame_lag})")
                    self.frame_count += skip_frames
                    self.current_time = elapsed_time
                    frame_changed = True
                elif display_frame > self.frame_count:
                    # Normal frame advance
                    self.frame_count = display_frame
                    self.current_time = elapsed_time
                    frame_changed = True

                # Minimal debug output to reduce I/O overhead
                # Show first 10 updates, then every 120th (6 seconds at 20Hz)
                if self.t < 10 or self.t % 120 == 0:
                    print(
                        f"[Video Player] Frame: {self.frame_count}/{self.total_frames}, Lag: {frame_lag if 'frame_lag' in locals() else 0}")

                # Only draw if frame actually changed or every 6th update (to handle paused frames)
                if frame_changed or self.t % 6 == 0:
                    self._draw_video_frame()

                # Check audio synchronization much less frequently
                # Check sync every 30 frames (2.5 seconds)
                if self.frame_count % 30 == 0:
                    self._check_audio_sync()

                # Log frame changes much less frequently to reduce spam
                if frame_changed and (self.t < 10 or self.frame_count % 15 == 0):
                    print(
                        f"[Video Player] Advanced to frame {self.frame_count} at {elapsed_time:.2f}s")
            else:
                # If no video start time, just draw a fallback occasionally
                if self.t % 12 == 0:  # Every 12 updates
                    self._draw_video_frame()

            # Auto-advance to next video when current finishes
            # Only check for end if we have a reasonable number of total frames
            if self.total_frames > 5 and self.frame_count >= self.total_frames - 1:
                print(
                    f"[Video Player] Video finished - Frame: {self.frame_count}/{self.total_frames}, Auto-advancing to next video")
                if len(self.video_files) > 1:
                    self._next_video()
                else:
                    self.playing = False
                    self._draw_status("Done.")
            elif self.total_frames <= 5:
                print(
                    f"[Video Player] Warning: Very low total_frames ({self.total_frames}), likely video info extraction failed")

    def onclose(self):
        self._stop_playback()
        self._clear_screen()

    def onkeydown(self, key):
        if key in ("KEY_SPACE", " "):
            self.paused = not self.paused
            self._handle_audio_pause_resume()
            self._draw_status()
        elif key in ("KEY_LEFT", "KEY_A"):
            if len(self.video_files) > 1:
                self._previous_video()
        elif key in ("KEY_RIGHT", "KEY_D"):
            if len(self.video_files) > 1:
                self._next_video()
        elif key in ("KEY_U", "u"):
            # Toggle UI overlay
            self.show_ui = not self.show_ui
            self._draw_video_frame()  # Redraw to show/hide UI
        elif key in ("KEY_ESC", "ESC", "KEY_Q", "q"):
            # Stop all video and audio playback before exiting
            self._stop_playback()
            # Clear the screen completely before leaving
            self._clear_screen()
            self.context["app_manager"].swap_app_async(
                "video_player", "launcher", update_rate_hz=20.0, delay=0.1)

    def _scan_video_files(self):
        """Scan the video directory for all video files"""
        self.video_files = []
        try:
            for filename in os.listdir(self.video_directory):
                file_ext = os.path.splitext(filename)[1].lower()
                if file_ext in self.video_extensions:
                    self.video_files.append(filename)

            # Sort video files alphabetically
            self.video_files.sort()
            print(
                f"[Video Player] Found {len(self.video_files)} video files: {self.video_files}")

        except Exception as e:
            print(f"[Video Player] Error scanning directory: {e}")
            self.video_files = []

    def _next_video(self):
        """Switch to the next video in the directory"""
        if len(self.video_files) <= 1:
            return

        self.current_video_index = (
            self.current_video_index + 1) % len(self.video_files)
        self._switch_video()

    def _previous_video(self):
        """Switch to the previous video in the directory"""
        if len(self.video_files) <= 1:
            return

        self.current_video_index = (
            self.current_video_index - 1) % len(self.video_files)
        self._switch_video()

    def _switch_video(self):
        """Switch to a different video"""
        print(
            f"[Video Player] Switching to video {self.current_video_index + 1}/{len(self.video_files)}: {self.video_files[self.current_video_index]}")

        # Stop current playback (including audio)
        self._stop_playback()

        # Set new video path
        self.video_path = os.path.join(
            self.video_directory, self.video_files[self.current_video_index])

        # Clear screen and show loading
        self._clear_screen()
        self.context["drawing"]["draw_text"](
            "Loading next video...", 2, 2, self.font, 255)

        # Get video info and start playback (with audio)
        self._get_video_info()
        self._start_playback()

    def _seek_relative(self, seconds):
        """Seek relative to current position"""
        if not self.playing or self.duration <= 0:
            return

        # Calculate new time position
        new_time = max(0, min(self.duration, self.current_time + seconds))
        self._seek_to_time(new_time)

    def _seek_to_time(self, target_time):
        """Seek to specific time position"""
        if not self.playing or self.duration <= 0:
            return

        print(f"[Video Player] Seeking to {target_time:.1f}s")

        # Update current time
        self.current_time = target_time

        # Calculate target frame based on new time
        target_frame = int(target_time * self.target_fps)
        target_frame = max(0, min(target_frame, self.total_frames - 1))

        # Update frame count
        old_frame = self.frame_count
        self.frame_count = target_frame

        # Adjust video start time to maintain sync
        current_real_time = time.time()
        self.video_start_time = current_real_time - target_time

        # Stop and restart audio at new position if possible
        if self.audio_temp_file:
            self._stop_audio()
            # Small delay to ensure clean stop
            time.sleep(0.1)
            self._start_audio_at_position(target_time)

        # Clear frame cache around the new position to force re-extraction
        frames_to_remove = []
        for cached_frame in list(self.frame_cache.keys()):
            if abs(cached_frame - target_frame) > 10:  # Keep frames within 10 of target
                frames_to_remove.append(cached_frame)

        for frame_num in frames_to_remove:
            del self.frame_cache[frame_num]

        # Extract frames around new position
        start_extract = max(0, target_frame - 5)
        end_extract = min(self.total_frames, target_frame + 15)
        self._extract_frames(start_extract, end_extract)

        # Force immediate redraw
        self._draw_video_frame()

        print(
            f"[Video Player] Seek complete: {old_frame} -> {target_frame} ({target_time:.1f}s)")

    def _start_audio_at_position(self, start_time):
        """Start audio playback from a specific time position"""
        if not self.video_path:
            print(f"[Video Player] Cannot start audio - no video path")
            return

        try:
            # Find ffmpeg executable
            ffmpeg_cmd = self._find_ffmpeg_executable("ffmpeg")
            if not ffmpeg_cmd:
                print(f"[Video Player] ffmpeg not found, cannot extract audio")
                return

            # Extract audio starting from the specified time
            self.audio_temp_file = os.path.join(self.path, "temp_audio.wav")

            print(
                f"[Video Player] Extracting audio from {start_time:.1f}s to: {self.audio_temp_file}")

            # Get current mixer settings
            mixer_frequency = 22050
            mixer_channels = 1

            try:
                import pygame
                mixer_info = pygame.mixer.get_init()
                if mixer_info:
                    mixer_frequency, _, mixer_channels = mixer_info
            except:
                pass

            # Build ffmpeg command to extract audio from specific time
            cmd = [
                ffmpeg_cmd, "-i", self.video_path,
                "-ss", str(start_time),  # Start from this time
                "-vn",  # No video
                "-acodec", "pcm_s16le",
                "-ar", str(mixer_frequency),
                "-ac", str(mixer_channels),
                "-f", "wav",
                self.audio_temp_file,
                "-y", "-v", "quiet"
            ]

            # Extract and play audio in background
            def extract_and_play_audio():
                try:
                    result = subprocess.run(
                        cmd, capture_output=True, timeout=30)

                    if result.returncode == 0 and os.path.exists(self.audio_temp_file):
                        file_size = os.path.getsize(self.audio_temp_file)
                        print(
                            f"[Video Player] Audio extracted from {start_time:.1f}s, file size: {file_size} bytes")

                        # Start streaming
                        success = self.context["audio"]["start_stream"](
                            self.audio_temp_file)
                        if success:
                            self.audio_start_time = time.time()
                            self.audio_ready = True  # Mark audio as ready for seeking
                            print(
                                f"[Video Player] Started audio streaming from {start_time:.1f}s")
                        else:
                            print(
                                f"[Video Player] Failed to start audio streaming")
                    else:
                        error_msg = result.stderr.decode() if result.stderr else "Unknown error"
                        print(
                            f"[Video Player] Audio extraction failed: {error_msg}")

                except Exception as e:
                    print(
                        f"[Video Player] Error extracting audio from position: {e}")

            # Start audio extraction in background
            audio_thread = threading.Thread(
                target=extract_and_play_audio, daemon=True)
            audio_thread.start()

        except Exception as e:
            print(f"[Video Player] Error starting audio at position: {e}")

    def _get_video_info(self):
        """Get video duration and frame rate using ffprobe"""
        try:
            # Find ffprobe executable (cross-platform)
            ffprobe_cmd = self._find_ffmpeg_executable("ffprobe")
            if not ffprobe_cmd:
                print(f"[Video Player] ffprobe not found, using default values")
                self.duration = 10.0  # Default 10 seconds
                self.source_fps = 24  # Default source FPS
                self.fps = self.target_fps  # Always use target FPS
                self.total_frames = int(self.duration * self.target_fps)
                print(
                    f"[Video Player] Using default video info - Duration: {self.duration}s, Source FPS: {self.source_fps}, Target FPS: {self.target_fps}, Total frames: {self.total_frames}")
                return

            # Get duration
            result = subprocess.run([
                ffprobe_cmd, "-v", "quiet", "-show_entries", "format=duration",
                "-of", "csv=p=0", self.video_path
            ], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.duration = float(result.stdout.strip())
            else:
                self.duration = 10.0  # Default if ffprobe fails

            # Get frame rate
            result = subprocess.run([
                ffprobe_cmd, "-v", "quiet", "-show_entries", "stream=r_frame_rate",
                "-select_streams", "v:0", "-of", "csv=p=0", self.video_path
            ], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                fps_str = result.stdout.strip()
                if '/' in fps_str:
                    num, den = fps_str.split('/')
                    self.source_fps = float(num) / float(den)
                else:
                    self.source_fps = float(fps_str)
            else:
                self.source_fps = 24  # Default

            # Always use 12 FPS for display regardless of source
            self.fps = self.target_fps

            # Calculate total frames based on target FPS
            self.total_frames = int(
                self.duration * self.target_fps) if self.duration > 0 else 100
            print(
                f"[Video Player] Video info - Duration: {self.duration}s, Source FPS: {self.source_fps}, Target FPS: {self.target_fps}, Total frames: {self.total_frames}")
        except Exception as e:
            print(f"[Video Player] Error getting video info: {e}")
            self.duration = 10.0  # Default 10 seconds
            self.source_fps = 24  # Default source FPS
            self.fps = self.target_fps  # Always use target FPS
            self.total_frames = int(self.duration * self.target_fps)

    def _start_playback(self):
        """Start video playback"""
        print(
            f"[Video Player] Starting playback for: {os.path.basename(self.video_path)}")
        print(
            f"[Video Player] Video info - Duration: {self.duration}s, Total frames: {self.total_frames}, Target FPS: {self.target_fps}")
        self.playing = True
        self.paused = False
        self.current_time = 0
        self.frame_count = 0
        self.t = 0
        self.frame_cache = {}
        self.video_start_time = None  # Will be set when audio is ready
        self.audio_start_time = None  # Will be set when audio actually starts
        self.audio_ready = False  # Reset audio ready flag
        self.waiting_for_audio = True  # Set waiting flag

        # Reset frame extraction flags
        self._extracting_frames = False
        self._preloading_frames = False

        # Create temporary directory for frame extraction
        if self.temp_dir:
            try:
                import shutil
                shutil.rmtree(self.temp_dir)
            except:
                pass

        self.temp_dir = tempfile.mkdtemp(prefix="proxitalk_video_")
        print(f"[Video Player] Created temp directory: {self.temp_dir}")

        # Clear the entire screen first
        self._clear_screen()
        self._draw_status()

        # Extract initial buffer of frames - much larger for smoother playback
        initial_frames = min(self.buffer_size, self.total_frames)
        print(
            f"[Video Player] Pre-buffering {initial_frames} frames for smooth playback")
        self._extract_frames(0, initial_frames)

        # Start background frame extraction thread for continuous buffering
        self._start_background_extractor()

        # Start audio streaming - this will set audio_ready when complete
        self._start_audio()

        print(f"[Video Player] Playback setup complete - waiting for audio to be ready")

        # Show "Loading audio..." message while waiting
        self.context["drawing"]["draw_overlay_text"](
            "Loading audio...", 2, self.height - 15, self.font, 255)

    def _stop_playback(self):
        """Stop video playback"""
        self.playing = False
        self.audio_ready = False  # Reset audio ready flag
        self.waiting_for_audio = False  # Reset waiting flag

        # Stop background frame extraction
        self._stop_background_extraction = True

        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except:
                pass
            self.process = None

        # Stop audio playback using streaming system
        self._stop_audio()

        # Clear all overlay elements that might persist
        self.context["drawing"]["clear_overlay_area"](
            0, 0, self.width, self.height)

        # Clean up temporary directory
        if self.temp_dir:
            try:
                import shutil
                shutil.rmtree(self.temp_dir)
                self.temp_dir = None
            except:
                pass

    def _extract_frames(self, start_frame, end_frame):
        """Extract frames from video using ffmpeg"""
        if not self.video_path:
            print(f"[Video Player] Cannot extract frames - no video path")
            return

        # Don't extract frames we already have
        frames_needed = []
        for i in range(start_frame, end_frame):
            if i not in self.frame_cache:
                frames_needed.append(i)

        if not frames_needed:
            # print(f"[Video Player] All frames {start_frame}-{end_frame} already cached")
            return

        print(
            f"[Video Player] Extracting {len(frames_needed)} frames: {start_frame}-{end_frame} (buffer: {len(self.frame_cache)} total)")

        # Find ffmpeg executable (cross-platform)
        ffmpeg_cmd = self._find_ffmpeg_executable("ffmpeg")
        if not ffmpeg_cmd:
            print(f"[Video Player] ffmpeg not found in common locations or PATH")
            return

        try:
            # Calculate the time interval for frame sampling at target FPS
            # We want to extract frames at regular intervals to achieve target_fps
            frame_interval = 1.0 / self.target_fps  # Time between frames at target FPS

            # Calculate which source frames we need to extract
            extracted_frames = []
            for i in range(start_frame, end_frame):
                # Calculate the time this frame should represent
                target_time = i * frame_interval
                # Find the closest source frame at this time
                source_frame_index = int(target_time * self.source_fps)
                # (display_frame_index, time_in_video)
                extracted_frames.append((i, target_time))

            if not extracted_frames:
                return

            # Extract frames to temporary directory
            output_pattern = os.path.join(self.temp_dir, "frame_%04d.png")

            # Extract all needed frames in one ffmpeg call using select filter
            # Build a select filter that picks frames at the right times
            start_time = extracted_frames[0][1]  # Time of first frame
            end_time = extracted_frames[-1][1]   # Time of last frame
            duration = end_time - start_time + frame_interval

            cmd = [
                ffmpeg_cmd, "-i", self.video_path,
                "-ss", str(start_time),  # Start time
                "-t", str(duration),     # Duration
                "-vf", f"fps={self.target_fps},scale={self.width}:{self.height}:force_original_aspect_ratio=decrease:flags=fast_bilinear",
                "-pix_fmt", "gray",      # Use grayscale to reduce processing
                "-f", "image2",          # Output as image sequence
                "-frames:v", str(len(extracted_frames)),
                output_pattern,
                "-y", "-v", "error",     # Only show errors
                "-threads", "2"          # Limit threads to reduce system load
            ]

            # print(f"[Video Player] Extracting frames {start_frame}-{end_frame} using: {os.path.basename(ffmpeg_cmd)}")
            # print(f"[Video Player] Command: ffmpeg -ss {start_time:.2f} -t {duration:.2f} ...")
            result = subprocess.run(cmd, capture_output=True, timeout=15)

            if result.returncode == 0:
                # Load extracted frames into cache
                frames_loaded = 0
                for idx, (display_frame_idx, _) in enumerate(extracted_frames):
                    frame_file = os.path.join(
                        self.temp_dir, f"frame_{idx+1:04d}.png")
                    if os.path.exists(frame_file):
                        try:
                            img = Image.open(frame_file).convert(
                                "1")  # Convert to 1-bit
                            self.frame_cache[display_frame_idx] = img
                            frames_loaded += 1
                            # Don't print each frame to reduce spam
                            # if frames_loaded <= 3 or frames_loaded == len(frames_needed):
                            #     print(f"[Video Player] Cached frame {display_frame_idx}")
                        except Exception as e:
                            print(
                                f"[Video Player] Error loading frame {display_frame_idx}: {e}")

                        # Clean up the frame file to save disk space
                        try:
                            os.remove(frame_file)
                        except:
                            pass

                print(
                    f"[Video Player] Successfully extracted and cached {frames_loaded}/{len(extracted_frames)} frames (total cache: {len(self.frame_cache)})")

                # Clean up old frames from cache to manage memory, but keep a reasonable buffer
                # Keep frames around current position, remove frames that are too far behind
                frames_to_remove = []
                for cached_frame in list(self.frame_cache.keys()):
                    # Remove frames more than 45 frames (3 seconds at 15fps) behind current position
                    if cached_frame < self.frame_count - 45:
                        frames_to_remove.append(cached_frame)

                for frame_num in frames_to_remove:
                    del self.frame_cache[frame_num]

                if frames_to_remove:
                    print(
                        f"[Video Player] Cleaned up {len(frames_to_remove)} old frames (keeping recent buffer)")

            else:
                error_msg = result.stderr.decode() if result.stderr else "Unknown error"
                print(
                    f"[Video Player] ffmpeg error (code {result.returncode}): {error_msg}")

        except subprocess.TimeoutExpired:
            print(
                f"[Video Player] ffmpeg timeout while extracting frames {start_frame}-{end_frame}")
        except Exception as e:
            print(f"[Video Player] Error extracting frames: {e}")

    def _start_background_extractor(self):
        """Start background thread for continuous frame extraction"""
        if self._background_extractor_running:
            return

        self._background_extractor_running = True
        self._stop_background_extraction = False

        def background_extract():
            print(f"[Video Player] Starting background frame extractor")

            while not self._stop_background_extraction and self.playing:
                try:
                    # Find gaps in our frame cache that need to be filled
                    current_frame = self.frame_count
                    max_frame_to_buffer = min(
                        self.total_frames, current_frame + self.buffer_size)

                    # Find the next range that needs extraction
                    start_extract = None
                    end_extract = None

                    for frame_idx in range(current_frame, max_frame_to_buffer):
                        if frame_idx not in self.frame_cache:
                            if start_extract is None:
                                start_extract = frame_idx
                            end_extract = frame_idx + 1
                        elif start_extract is not None:
                            # Found a gap, extract it
                            break

                    if start_extract is not None and end_extract is not None:
                        # Limit batch size for responsiveness but make it larger for efficiency
                        batch_end = min(
                            end_extract, start_extract + self.extract_batch_size)

                        if not self._extracting_frames:  # Don't interfere with on-demand extraction
                            # Only log occasionally to reduce I/O overhead
                            if start_extract % 60 == 0:  # Every 60 frames
                                print(
                                    f"[Video Player] Background extracting frames {start_extract}-{batch_end}")
                            self._extract_frames(start_extract, batch_end)

                    # Clean up old frames to save memory (more aggressive cleanup)
                    frames_to_remove = []
                    for cached_frame in list(self.frame_cache.keys()):
                        # Keep 3 seconds behind (12fps * 3)
                        if cached_frame < current_frame - 36:
                            frames_to_remove.append(cached_frame)

                    for frame_num in frames_to_remove:
                        del self.frame_cache[frame_num]

                    # Sleep longer to reduce CPU overhead and give drawing priority
                    time.sleep(0.1)  # Increased from 0.05 to 0.1

                except Exception as e:
                    print(f"[Video Player] Background extractor error: {e}")
                    time.sleep(1.0)  # Wait longer on error

            print(f"[Video Player] Background extractor stopped")
            self._background_extractor_running = False

        # Start the background thread
        threading.Thread(target=background_extract, daemon=True).start()

    def _draw_video_frame(self):
        """Draw actual video frame - optimized for performance with ProxiTalk batching"""
        # Use ProxiTalk's batching system for optimal performance
        self.context["drawing"]["begin_batch"]()

        try:
            # Try to get frame from cache first
            if self.frame_count in self.frame_cache:
                # Display actual video frame
                frame_img = self.frame_cache[self.frame_count]

                # Calculate centering offsets once
                img_w, img_h = frame_img.size
                x_offset = (self.width - img_w) // 2
                y_offset = (self.height - img_h) // 2

                try:
                    # Clear only the necessary area, not the entire screen
                    self.context["drawing"]["draw_area"](
                        x_offset, y_offset, img_w, img_h, 0)

                    # Draw the frame image
                    self.context["drawing"]["draw_image"](
                        frame_img, x_offset, y_offset)

                    # Only draw UI overlay if enabled and update less frequently
                    # Update UI every 6 frames (0.5 seconds)
                    if self.show_ui and (self.frame_count % 6 == 0):
                        # Draw filename as overlay text
                        filename = os.path.basename(
                            self.video_path) if self.video_path else "test.mp4"
                        display_filename = filename[:30] + \
                            "..." if len(filename) > 33 else filename
                        self.context["drawing"]["draw_overlay_text"](
                            display_filename, 2, 2, self.font, 255)

                except Exception as e:
                    print(f"[Video Player] Error displaying frame: {e}")
                    self._draw_fallback_frame()
            else:
                # Frame not cached - show fallback with minimal operations
                self._draw_fallback_frame()

                # Log missing frames much less frequently to reduce I/O overhead
                if self.frame_count % 30 == 0:  # Every 2.5 seconds at 12fps
                    frames_available = len(
                        [f for f in self.frame_cache.keys() if f >= self.frame_count])
                    print(
                        f"[Video Player] Frame {self.frame_count} not cached, showing fallback (ahead buffer: {frames_available} frames)")

            # Update status overlay only if UI is shown and much less frequently
            # Update status every 12 frames (1 second)
            if self.show_ui and (self.frame_count % 12 == 0):
                self._draw_status()

        finally:
            # Execute all drawing operations at once for optimal hardware performance
            self.context["drawing"]["end_batch"]()

    def _draw_fallback_frame(self):
        """Draw a minimal fallback frame when video frame is not available"""
        # Use a much simpler fallback - just clear the center area
        fallback_width = self.width // 3
        fallback_height = self.height // 3
        x_offset = (self.width - fallback_width) // 2
        y_offset = (self.height - fallback_height) // 2

        # Just draw a simple black rectangle - no complex patterns
        self.context["drawing"]["draw_area"](
            x_offset, y_offset, fallback_width, fallback_height, 0)

        # Draw a simple border
        border_thickness = 1
        # Top border
        self.context["drawing"]["draw_area"](
            x_offset, y_offset, fallback_width, border_thickness, 255)
        # Bottom border
        self.context["drawing"]["draw_area"](
            x_offset, y_offset + fallback_height - border_thickness, fallback_width, border_thickness, 255)
        # Left border
        self.context["drawing"]["draw_area"](
            x_offset, y_offset, border_thickness, fallback_height, 255)
        # Right border
        self.context["drawing"]["draw_area"](
            x_offset + fallback_width - border_thickness, y_offset, border_thickness, fallback_height, 255)

        # Only show loading message if UI is enabled and infrequently
        if self.show_ui and (self.frame_count % 30 == 0):
            self.context["drawing"]["draw_overlay_text"](
                "Loading...", x_offset + 5, y_offset + 5, self.font, 255)

    def _draw_status(self, msg=None):
        """Draw status with ProxiTalk batching for optimal performance"""
        # Only draw status if UI is enabled
        if not self.show_ui:
            return

        # Use batching for multiple drawing operations
        self.context["drawing"]["begin_batch"]()

        try:
            # Clear status area only when needed - make room for progress bar
            self.context["drawing"]["draw_overlay_area"](
                0, self.height-20, self.width, 20, 0)

            # Draw progress bar at the bottom (less frequently)
            # Update progress every 12 frames (1 second)
            if self.frame_count % 12 == 0:
                self._draw_progress_bar()

            # Draw play/pause icon (even less frequently)
            # Update icon every 24 frames (2 seconds)
            if self.frame_count % 24 == 0:
                self._draw_playback_icon()

        finally:
            # Execute all status drawing operations at once
            self.context["drawing"]["end_batch"]()

    def _draw_playback_icon(self):
        """Draw a small play or pause icon"""
        icon_size = 4
        icon_x = 1
        icon_y = self.height - 10

        # Create a small icon image
        icon_img = Image.new("1", (icon_size, icon_size), 0)
        draw = ImageDraw.Draw(icon_img)

        if self.paused:
            # Draw pause icon (two vertical bars with gap)
            draw.rectangle([0, 0, 0, 3], fill=255)  # Left bar (1 pixel wide)
            draw.rectangle([2, 0, 2, 3], fill=255)  # Right bar (1 pixel wide)
        else:
            # Draw play icon (triangle pointing right) - properly sized for 4x4
            draw.polygon([(0, 0), (0, 3), (2, 2), (2, 1)],
                         fill=255)  # Small centered triangle

        # Draw the icon on the overlay
        self.context["drawing"]["draw_overlay_image"](icon_img, icon_x, icon_y)

    def _draw_progress_bar(self):
        """Draw progress bar showing current playback position - optimized"""
        if self.duration <= 0:
            return

        # Progress bar dimensions
        bar_x = 2
        bar_y = self.height - 4
        bar_width = self.width - 4
        bar_height = 2

        # Calculate progress (0.0 to 1.0)
        progress = min(1.0, max(0.0, self.current_time / self.duration))

        # Use batching for all progress bar drawing operations
        self.context["drawing"]["begin_batch"]()

        try:
            # Draw background bar (empty)
            self.context["drawing"]["draw_overlay_area"](
                bar_x, bar_y, bar_width, bar_height, 0)

            # Draw progress bar outline efficiently
            # Top border
            self.context["drawing"]["draw_overlay_area"](
                bar_x, bar_y-1, bar_width, 1, 255)
            # Bottom border
            self.context["drawing"]["draw_overlay_area"](
                bar_x, bar_y+bar_height, bar_width, 1, 255)
            # Left border
            self.context["drawing"]["draw_overlay_area"](
                bar_x-1, bar_y-1, 1, bar_height+2, 255)
            # Right border
            self.context["drawing"]["draw_overlay_area"](
                bar_x+bar_width, bar_y-1, 1, bar_height+2, 255)

            # Draw filled progress
            if progress > 0:
                filled_width = int(bar_width * progress)
                if filled_width > 0:
                    self.context["drawing"]["draw_overlay_area"](
                        bar_x, bar_y, filled_width, bar_height, 255)

            # Draw scrubber handle (current position indicator)
            scrubber_x = bar_x + int((bar_width - 1) * progress)
            scrubber_y = bar_y - 1
            scrubber_height = bar_height + 2

            # Draw scrubber as a vertical line
            self.context["drawing"]["draw_overlay_area"](
                scrubber_x, scrubber_y, 1, scrubber_height, 255)

        finally:
            # Execute all progress bar operations at once
            self.context["drawing"]["end_batch"]()

    def _format_time(self, seconds):
        """Format time in seconds to MM:SS format"""
        if seconds < 0:
            return "0:00"

        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes}:{seconds:02d}"

    def _show_error(self, msg):
        self._clear_screen()
        self.context["drawing"]["draw_text"](
            "Video Player Error:", 2, 2, self.font, 255)
        self.context["drawing"]["draw_text"](msg, 2, 15, self.font, 255)
        self.context["drawing"]["draw_text"](
            "Press Q or ESC to exit", 2, 30, self.font, 255)

    def _clear_screen(self):
        self.context["drawing"]["clear_screen"]()
        # Also clear any overlay elements that might persist
        self.context["drawing"]["clear_overlay_area"](
            0, 0, self.width, self.height)

    def _find_ffmpeg_executable(self, executable_name):
        """Find ffmpeg/ffprobe executable cross-platform with caching"""
        # Check cache first
        if executable_name in self._ffmpeg_cache:
            cached_path = self._ffmpeg_cache[executable_name]
            # Verify cached path still exists and is executable
            if os.path.exists(cached_path) and os.access(cached_path, os.X_OK):
                # print(f"[Video Player] Using cached {executable_name}: {cached_path}")
                return cached_path
            else:
                print(
                    f"[Video Player] Cached {executable_name} path no longer valid: {cached_path}")
                # Remove invalid cache entry
                del self._ffmpeg_cache[executable_name]

        import platform
        is_windows = platform.system() == "Windows"

        # Add .exe extension on Windows
        exe_name = f"{executable_name}.exe" if is_windows else executable_name

        # Common installation paths
        possible_paths = []

        if is_windows:
            # Windows paths
            possible_paths = [
                rf"C:\ffmpeg\bin\{exe_name}",
                rf"C:\Program Files\ffmpeg\bin\{exe_name}",
                rf"C:\Program Files (x86)\ffmpeg\bin\{exe_name}",
                os.path.join(os.path.dirname(os.path.abspath(
                    __file__)), exe_name),  # In app folder
                os.path.join(self.context["app_path"],
                             exe_name),  # In app folder
            ]
        else:
            # Linux/Unix paths
            possible_paths = [
                f"/usr/bin/{executable_name}",
                f"/usr/local/bin/{executable_name}",
                f"/opt/ffmpeg/bin/{executable_name}",
                f"/snap/bin/{executable_name}",  # Snap installations
                os.path.join(os.path.dirname(os.path.abspath(
                    __file__)), executable_name),  # In app folder
                os.path.join(self.context["app_path"],
                             executable_name),  # In app folder
            ]

        # Check each possible path
        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                print(f"[Video Player] Found {executable_name} at: {path}")
                # Cache the found path
                self._ffmpeg_cache[executable_name] = path
                return path

        # Try to find in PATH as fallback
        try:
            subprocess.run([executable_name, "-version"],
                           capture_output=True, timeout=2)
            print(f"[Video Player] Using {executable_name} from PATH")
            # Cache the PATH version
            self._ffmpeg_cache[executable_name] = executable_name
            return executable_name
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
            print(
                f"[Video Player] {executable_name} not found in common locations or PATH")
            return None

    def _start_audio(self):
        """Start audio playback using ProxiTalk streaming system"""
        if not self.video_path:
            print(f"[Video Player] Cannot start audio - no video path")
            return

        try:
            # Find ffmpeg executable (cross-platform)
            ffmpeg_cmd = self._find_ffmpeg_executable("ffmpeg")
            if not ffmpeg_cmd:
                print(f"[Video Player] ffmpeg not found, cannot extract audio")
                return

            # Extract audio to temporary wav file in the app directory
            self.audio_temp_file = os.path.join(self.path, "temp_audio.wav")

            print(
                f"[Video Player] Extracting audio to: {self.audio_temp_file}")

            # Get current mixer settings to match format
            mixer_frequency = 22050  # Default
            mixer_channels = 1       # Default

            try:
                import pygame
                mixer_info = pygame.mixer.get_init()
                if mixer_info:
                    mixer_frequency, _, mixer_channels = mixer_info
                    print(
                        f"[Video Player] Using mixer format: {mixer_frequency}Hz, {mixer_channels} channels")
                else:
                    print(f"[Video Player] Mixer not initialized, using defaults")
            except ImportError:
                print(f"[Video Player] pygame not available, using defaults")
            except Exception:
                print(f"[Video Player] Could not get mixer info, using defaults")

            print(
                f"[Video Player] Keeping audio at normal speed, video will sync to audio timing")

            # Build ffmpeg command without audio processing - keep audio at normal speed
            cmd = [
                ffmpeg_cmd, "-i", self.video_path,
                "-vn",  # No video
                # PCM 16-bit little-endian (matches pygame)
                "-acodec", "pcm_s16le",
                "-ar", str(mixer_frequency),  # Match current mixer sample rate
                "-ac", str(mixer_channels),   # Match current mixer channels
                "-f", "wav",  # Force WAV format
                self.audio_temp_file,
                "-y", "-v", "quiet"  # Overwrite and reduce output
            ]

            # Extract audio in background thread
            def extract_and_play_audio():
                try:
                    print(
                        f"[Video Player] Running ffmpeg command: {' '.join(cmd[:5])}...")
                    result = subprocess.run(
                        cmd, capture_output=True, timeout=30)

                    if result.returncode == 0:
                        if os.path.exists(self.audio_temp_file):
                            file_size = os.path.getsize(self.audio_temp_file)
                            print(
                                f"[Video Player] Audio extracted successfully, file size: {file_size} bytes")

                            # Start streaming using ProxiTalk's new streaming system
                            success = self.context["audio"]["start_stream"](
                                self.audio_temp_file)
                            if success:
                                self.audio_start_time = time.time()  # Record when audio actually started
                                self.audio_ready = True  # Signal that audio is ready
                                print(
                                    f"[Video Player] Audio streaming started successfully - video can now begin")
                            else:
                                print(
                                    f"[Video Player] Failed to start audio streaming")
                                # Even if audio fails, allow video to start after a delay
                                time.sleep(2.0)
                                self.audio_ready = True
                        else:
                            print(
                                f"[Video Player] Audio file not created despite success code")
                            # Allow video to start anyway after a delay
                            time.sleep(2.0)
                            self.audio_ready = True
                    else:
                        error_msg = result.stderr.decode() if result.stderr else "Unknown error"
                        print(
                            f"[Video Player] Audio extraction failed (code {result.returncode}): {error_msg}")
                        if result.stdout:
                            print(
                                f"[Video Player] ffmpeg stdout: {result.stdout.decode()}")
                        # Allow video to start anyway after a delay
                        time.sleep(2.0)
                        self.audio_ready = True

                except subprocess.TimeoutExpired:
                    print(
                        f"[Video Player] Audio extraction timeout after 30 seconds")
                    # Allow video to start anyway
                    self.audio_ready = True
                except Exception as e:
                    print(f"[Video Player] Error extracting audio: {e}")
                    import traceback
                    traceback.print_exc()
                    # Allow video to start anyway
                    self.audio_ready = True

            # Start audio extraction in background thread
            audio_thread = threading.Thread(
                target=extract_and_play_audio, daemon=True)
            audio_thread.start()

        except Exception as e:
            print(f"[Video Player] Error starting audio: {e}")

    def _stop_audio(self):
        """Stop audio playback and clean up"""
        # Stop audio streaming
        self.context["audio"]["stop_stream"]()

        # Clean up temporary audio file
        if self.audio_temp_file and os.path.exists(self.audio_temp_file):
            try:
                os.remove(self.audio_temp_file)
                self.audio_temp_file = None
                print(f"[Video Player] Cleaned up audio file")
            except Exception as e:
                print(f"[Video Player] Error cleaning up audio file: {e}")

    def _handle_audio_pause_resume(self):
        """Handle audio pause/resume using streaming system"""
        current_time = time.time()

        if self.paused:
            # Pausing - record pause time for timing adjustment
            self.pause_start_time = current_time
            self.context["audio"]["pause_stream"]()
        else:
            # Resuming - adjust start times to account for pause duration
            if hasattr(self, 'pause_start_time') and self.pause_start_time:
                pause_duration = current_time - self.pause_start_time
                if self.video_start_time:
                    self.video_start_time += pause_duration
                if self.audio_start_time:
                    self.audio_start_time += pause_duration
                print(
                    f"[Video Player] Adjusted timing after {pause_duration:.2f}s pause")

            self.context["audio"]["resume_stream"]()

    def _get_current_video_time(self):
        """Get the current video time based on frame count and target FPS"""
        return self.frame_count / self.target_fps

    def _should_sync_audio(self):
        """Check if audio needs to be synchronized with video"""
        if not self.audio_temp_file:
            return False

        video_time = self._get_current_video_time()
        # Get audio position from streaming system if available
        audio_time = self.context["audio"].get(
            "get_stream_position", lambda: 0.0)()

        # Allow up to 0.2 second desync before correcting
        time_diff = abs(video_time - audio_time)
        return time_diff > 0.2

    def _check_audio_sync(self):
        """Check and correct audio/video synchronization"""
        if not self.audio_temp_file or self.paused:
            return

        # Check if audio is still playing
        if not self.context["audio"]["is_stream_playing"]():
            print(
                f"[Video Player] Audio stopped unexpectedly at frame {self.frame_count}")
            # Could attempt to restart audio here if needed
            return

        # With the new approach, video timing follows audio timing automatically
        # so we mainly just need to ensure audio hasn't stopped unexpectedly
        current_time = time.time()
        if self.video_start_time and self.audio_start_time:
            video_elapsed = current_time - self.video_start_time
            audio_elapsed = current_time - self.audio_start_time

            # # Just log the timing relationship occasionally for debugging
            # if self.frame_count % 30 == 0:  # Every 30 frames
            #     print(f"[Video Player] Sync check - Video: {video_elapsed:.2f}s, Audio: {audio_elapsed:.2f}s, Frame: {self.frame_count}")

# Usage: This app can be launched from code_editor by selecting a video file
# The code_editor should call: app_manager.load_app("video_player").onopen(file_path)

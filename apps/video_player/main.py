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
        self.fps = 12  # Default FPS - increased for smoother playback
        self.source_fps = 24  # Original video FPS
        self.target_fps = 12  # Target display FPS (fixed at 12)
        self.frame_cache = {}  # Cache for extracted frames
        self.temp_dir = None  # Temporary directory for frame extraction
        
        # Audio playback using new streaming system
        self.audio_temp_file = None  # Temporary audio file for video audio
        self.video_start_time = None  # Time when video playback started
        self.audio_start_time = None  # Time when audio started playing
        self.pause_start_time = None  # Time when pause started
        
        # Video playlist management
        self.video_directory = None
        self.video_files = []
        self.current_video_index = 0
        self.video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm']
        
        # UI toggle
        self.show_ui = True  # Toggle for showing UI overlay

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
        self.context["drawing"]["draw_text"]("Video Player", 2, 2, self.font, 255)
        self.context["drawing"]["draw_text"]("Loading videos from app folder...", 2, 15, self.font, 255)
        print("[Video Player] App started, scanning app folder for videos...")
        
        # Set the app directory as the video directory
        self.video_directory = self.context["app_path"]
        print(f"[Video Player] Scanning app directory: {self.video_directory}")
        
        # Find all video files in the app directory
        self._scan_video_files()
        
        if not self.video_files:
            print("[Video Player] No video files found in app directory")
            self.context["drawing"]["draw_text"]("No video files found in app folder.", 2, 28, self.font, 255)
            self.context["drawing"]["draw_text"]("Place video files in the app folder", 2, 41, self.font, 255)
            self.context["drawing"]["draw_text"]("or select from code editor.", 2, 54, self.font, 255)
            return
        
        # Start playing the first video automatically
        self.current_video_index = 0
        self.video_path = os.path.join(self.video_directory, self.video_files[self.current_video_index])
        print(f"[Video Player] Auto-playing first video: {self.video_path}")
        
        self._get_video_info()
        self._start_playback()

    def onopen(self, file_path=None):
        print(f"[Video Player] onopen called with file_path: {file_path}")
        print(f"[Video Player] Current working directory: {os.getcwd()}")
        print(f"[Video Player] File exists check: {os.path.exists(file_path) if file_path else 'No file path'}")
        
        # Immediately clear the screen to take control
        self._clear_screen()
        self.context["drawing"]["draw_text"]("Loading videos...", 2, 2, self.font, 255)
        
        if not file_path:
            print(f"[Video Player] No file path provided")
            self._show_error("No file selected.")
            return
            
        if not os.path.isfile(file_path):
            print(f"[Video Player] File does not exist: {file_path}")
            print(f"[Video Player] Absolute path: {os.path.abspath(file_path)}")
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
            print(f"[Video Player] Starting with selected video at index {self.current_video_index}: {selected_file}")
        except ValueError:
            # If the selected file isn't a video, start with the first video
            self.current_video_index = 0
            print(f"[Video Player] Selected file is not a video, starting with first video: {self.video_files[0]}")
        
        # Set the current video path
        self.video_path = os.path.join(self.video_directory, self.video_files[self.current_video_index])
        print(f"[Video Player] Playing: {self.video_path}")
        
        self._get_video_info()
        self._start_playback()

    def update(self):
        """Update method called by ProxiTalk framework"""
        if not self.playing:
            return
            
        self.t += 1
        
        # Check if we should advance to the next frame based on audio timing
        if not self.paused:
            current_time = time.time()
            
            # Calculate how much time has passed since video started
            if self.video_start_time:
                elapsed_time = current_time - self.video_start_time
                
                # Calculate which frame we should be showing based on elapsed time
                # Use the source video's original framerate for proper timing
                target_frame = int(elapsed_time * self.source_fps)
                
                # Map source frame to display frame (since we extract at target_fps)
                # We need to scale down from source fps to target fps
                display_frame = int(target_frame * (self.target_fps / self.source_fps))
                display_frame = min(display_frame, self.total_frames - 1)
                
                # Only advance frame if we need to (don't go backwards)
                if display_frame > self.frame_count:
                    self.frame_count = display_frame
                    self.current_time = elapsed_time
                    self._draw_video_frame()
                    
                    # Check audio synchronization occasionally
                    if self.frame_count % 10 == 0:  # Check sync every 10 frames
                        self._check_audio_sync()
                elif display_frame == self.frame_count:
                    # Hold the current frame - just update the display without advancing
                    self._draw_video_frame()
            
            # Auto-advance to next video when current finishes
            if self.frame_count >= self.total_frames - 1:
                if len(self.video_files) > 1:
                    # print(f"[Video Player] Auto-advancing to next video")
                    self._next_video()
                else:
                    self.playing = False
                    self._draw_status("Done.")

    def onclose(self):
        self._stop_playback()
        self._clear_screen()

    def onkeydown(self, key):
        if key in ("KEY_SPACE", " "):
            self.paused = not self.paused
            self._handle_audio_pause_resume()
            self._draw_status()
        elif key in ("KEY_LEFT", "KEY_A"):
            self._previous_video()
        elif key in ("KEY_RIGHT", "KEY_D"):
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
            self.context["app_manager"].swap_app_async("video_player", "launcher", update_rate_hz=20.0, delay=0.1)

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
            print(f"[Video Player] Found {len(self.video_files)} video files: {self.video_files}")
            
        except Exception as e:
            print(f"[Video Player] Error scanning directory: {e}")
            self.video_files = []

    def _next_video(self):
        """Switch to the next video in the directory"""
        if len(self.video_files) <= 1:
            return
            
        self.current_video_index = (self.current_video_index + 1) % len(self.video_files)
        self._switch_video()

    def _previous_video(self):
        """Switch to the previous video in the directory"""
        if len(self.video_files) <= 1:
            return
            
        self.current_video_index = (self.current_video_index - 1) % len(self.video_files)
        self._switch_video()

    def _switch_video(self):
        """Switch to a different video"""
        print(f"[Video Player] Switching to video {self.current_video_index + 1}/{len(self.video_files)}: {self.video_files[self.current_video_index]}")
        
        # Stop current playback (including audio)
        self._stop_playback()
        
        # Set new video path
        self.video_path = os.path.join(self.video_directory, self.video_files[self.current_video_index])
        
        # Clear screen and show loading
        self._clear_screen()
        self.context["drawing"]["draw_text"]("Loading next video...", 2, 2, self.font, 255)
        
        # Get video info and start playback (with audio)
        self._get_video_info()
        self._start_playback()

    def _get_video_info(self):
        """Get video duration and frame rate using ffprobe"""
        try:
            # Find ffprobe executable (cross-platform)
            ffprobe_cmd = self._find_ffmpeg_executable("ffprobe")
            if not ffprobe_cmd:
                print(f"[Video Player] ffprobe not found, using default values")
                self.duration = 10.0  # Default 10 seconds
                self.fps = 24
                self.total_frames = 240
                return
                
                # Get duration
                result = subprocess.run([
                    ffprobe_cmd, "-v", "quiet", "-show_entries", "format=duration",
                    "-of", "csv=p=0", self.video_path
                ], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    self.duration = float(result.stdout.strip())
                
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
                self.total_frames = int(self.duration * self.target_fps) if self.duration > 0 else 100
                print(f"[Video Player] Video info - Duration: {self.duration}s, Source FPS: {self.source_fps}, Target FPS: {self.target_fps}, Total frames: {self.total_frames}")
        except Exception as e:
            print(f"[Video Player] Error getting video info: {e}")
            self.duration = 10.0  # Default 10 seconds
            self.source_fps = 24  # Default source FPS
            self.fps = self.target_fps  # Always use target FPS
            self.total_frames = int(self.duration * self.target_fps)

    def _start_playback(self):
        """Start video playback"""
        print(f"[Video Player] Starting playback for: {os.path.basename(self.video_path)}")
        self.playing = True
        self.paused = False
        self.current_time = 0
        self.frame_count = 0
        self.t = 0
        self.frame_cache = {}
        self.video_start_time = time.time()  # Record when video playback started
        self.audio_start_time = None  # Will be set when audio actually starts
        
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
        
        # Extract some frames to start with
        self._extract_frames(0, min(25, self.total_frames))  # Extract first 25 frames
        
        # Start audio streaming using new ProxiTalk streaming system
        self._start_audio()
        
        print(f"[Video Player] Playback started")

    def _stop_playback(self):
        """Stop video playback"""
        self.playing = False
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
        self.context["drawing"]["clear_overlay_area"](0, 0, self.width, self.height)
        
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
            print(f"[Video Player] All frames {start_frame}-{end_frame} already cached")
            return
        
        # print(f"[Video Player] Need to extract {len(frames_needed)} frames: {frames_needed[:5]}{'...' if len(frames_needed) > 5 else ''}")
        
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
                extracted_frames.append((i, target_time))  # (display_frame_index, time_in_video)
            
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
                "-vf", f"fps={self.target_fps},scale={self.width}:{self.height}:force_original_aspect_ratio=decrease",
                "-frames:v", str(len(extracted_frames)),
                output_pattern,
                "-y", "-v", "error"  # Only show errors
            ]
            
            # print(f"[Video Player] Extracting frames {start_frame}-{end_frame} using: {os.path.basename(ffmpeg_cmd)}")
            # print(f"[Video Player] Command: ffmpeg -ss {start_time:.2f} -t {duration:.2f} ...")
            result = subprocess.run(cmd, capture_output=True, timeout=15)
            
            if result.returncode == 0:
                # Load extracted frames into cache
                frames_loaded = 0
                for idx, (display_frame_idx, _) in enumerate(extracted_frames):
                    frame_file = os.path.join(self.temp_dir, f"frame_{idx+1:04d}.png")
                    if os.path.exists(frame_file):
                        try:
                            img = Image.open(frame_file).convert("1")  # Convert to 1-bit
                            self.frame_cache[display_frame_idx] = img
                            frames_loaded += 1
                            # Don't print each frame to reduce spam
                            # if frames_loaded <= 3 or frames_loaded == len(frames_needed):
                            #     print(f"[Video Player] Cached frame {display_frame_idx}")
                        except Exception as e:
                            print(f"[Video Player] Error loading frame {display_frame_idx}: {e}")
                        
                        # Clean up the frame file to save disk space
                        try:
                            os.remove(frame_file)
                        except:
                            pass
                
                # print(f"[Video Player] Successfully extracted and cached {frames_loaded}/{len(extracted_frames)} frames")
                
                # Clean up old frames from cache to manage memory
                # Keep frames around current position, remove old ones
                frames_to_remove = []
                for cached_frame in list(self.frame_cache.keys()):
                    if cached_frame < self.frame_count - 20:  # Remove frames more than 20 behind
                        frames_to_remove.append(cached_frame)
                
                for frame_num in frames_to_remove:
                    del self.frame_cache[frame_num]
                
                # if frames_to_remove:
                #     print(f"[Video Player] Cleaned up {len(frames_to_remove)} old cached frames")
                    
            else:
                error_msg = result.stderr.decode() if result.stderr else "Unknown error"
                print(f"[Video Player] ffmpeg error (code {result.returncode}): {error_msg}")
                
        except subprocess.TimeoutExpired:
            print(f"[Video Player] ffmpeg timeout while extracting frames {start_frame}-{end_frame}")
        except Exception as e:
            print(f"[Video Player] Error extracting frames: {e}")

    def _draw_video_frame(self):
        """Draw actual video frame"""
        # Clear the entire screen area for video
        self.context["drawing"]["draw_area"](0, 0, self.width, self.height, 0)
        
        # Try to get frame from cache
        if self.frame_count in self.frame_cache:
            # Display actual video frame
            frame_img = self.frame_cache[self.frame_count]
            
            # Center the image using full screen
            img_w, img_h = frame_img.size
            x_offset = (self.width - img_w) // 2
            y_offset = (self.height - img_h) // 2
            
            try:
                self.context["drawing"]["draw_image"](frame_img, x_offset, y_offset)
                
                # Only draw UI overlay if enabled
                if self.show_ui:
                    # Draw filename as overlay text
                    filename = os.path.basename(self.video_path) if self.video_path else "test.mp4"
                    display_filename = filename[:30] + "..." if len(filename) > 33 else filename
                    self.context["drawing"]["draw_overlay_text"](display_filename, 2, 2, self.font, 255)
                    
                    # Draw frame info
                    frame_info = f"Frame: {self.frame_count}/{self.total_frames}"
                    self.context["drawing"]["draw_overlay_text"](frame_info, 2, 12, self.font, 255)
                
            except Exception as e:
                print(f"[Video Player] Error displaying frame: {e}")
                self._draw_fallback_frame()
        else:
            # Only print debug info when frames are missing
            if self.frame_count % 5 == 0:  # Reduce debug spam
                print(f"[Video Player] Frame {self.frame_count} not cached")
            
            # Extract more frames if we need them and haven't reached the end
            if self.frame_count < self.total_frames:
                # Extract next batch of frames starting from current frame
                start_frame = self.frame_count
                end_frame = min(self.total_frames, self.frame_count + 15)  # Extract 15 frames
                self._extract_frames(start_frame, end_frame)
                
                # Check if we now have the frame after extraction
                if self.frame_count in self.frame_cache:
                    print(f"[Video Player] Frame {self.frame_count} now available after extraction")
                    # Display the actual frame
                    frame_img = self.frame_cache[self.frame_count]
                    img_w, img_h = frame_img.size
                    x_offset = (self.width - img_w) // 2
                    y_offset = (self.height - img_h) // 2
                    
                    try:
                        self.context["drawing"]["draw_image"](frame_img, x_offset, y_offset)
                        
                        # Only draw UI overlay if enabled
                        if self.show_ui:
                            # Draw filename as overlay text
                            filename = os.path.basename(self.video_path) if self.video_path else "test.mp4"
                            display_filename = filename[:30] + "..." if len(filename) > 33 else filename
                            self.context["drawing"]["draw_overlay_text"](display_filename, 2, 2, self.font, 255)
                            
                            # Draw frame info
                            frame_info = f"Frame: {self.frame_count}/{self.total_frames}"
                            self.context["drawing"]["draw_overlay_text"](frame_info, 2, 12, self.font, 255)
                        
                        print(f"[Video Player] Frame {self.frame_count} displayed successfully after extraction")
                    except Exception as e:
                        print(f"[Video Player] Error displaying extracted frame: {e}")
                        self._draw_fallback_frame()
                else:
                    print(f"[Video Player] Frame {self.frame_count} still not available after extraction")
                    self._draw_fallback_frame()
            else:
                print(f"[Video Player] Reached end of video at frame {self.frame_count}")
                self._draw_fallback_frame()
        
        # Preload next batch if we're getting close to running out
        next_needed_frame = self.frame_count + 3  # Reduced lookahead
        if (next_needed_frame not in self.frame_cache and 
            next_needed_frame < self.total_frames):
            next_start = next_needed_frame
            next_end = min(self.total_frames, next_start + 10)  # Smaller batch
            self._extract_frames(next_start, next_end)
        
        # Update status overlay only if UI is shown
        if self.show_ui:
            self._draw_status()

    def _draw_fallback_frame(self):
        """Draw a fallback frame when video frame is not available"""
        # Create a simple placeholder using full screen
        img = Image.new("1", (self.width // 2, self.height // 2), 0)
        draw = ImageDraw.Draw(img)
        
        # Draw a simple pattern
        for i in range(0, img.width, 10):
            draw.line([(i, 0), (i, img.height)], fill=1)
        for i in range(0, img.height, 10):
            draw.line([(0, i), (img.width, i)], fill=1)
        
        # Center the placeholder on full screen
        x_offset = (self.width - img.width) // 2
        y_offset = (self.height - img.height) // 2
        
        self.context["drawing"]["draw_image"](img, x_offset, y_offset)
        
        # Only show loading message if UI is enabled
        if self.show_ui:
            self.context["drawing"]["draw_overlay_text"]("Loading video frame...", 2, 22, self.font, 255)

    def _draw_status(self, msg=None):
        # Only draw status if UI is enabled
        if not self.show_ui:
            return
            
        # Clear status area
        self.context["drawing"]["draw_overlay_area"](0, self.height-15, self.width, 15, 0)
        
        status = "Paused" if self.paused else "Playing"
        if msg:
            status = msg
        
        # Add audio indicator using streaming system
        audio_playing = self.context["audio"]["is_stream_playing"]() if self.audio_temp_file else False
        audio_status = "♪" if audio_playing else ""
        if audio_status and not self.paused:
            status = f"{status} {audio_status}"
        
        # Show video counter and status
        if len(self.video_files) > 1:
            video_counter = f"({self.current_video_index + 1}/{len(self.video_files)})"
            status_line = f"{status} {video_counter}"
        else:
            status_line = status
        
        self.context["drawing"]["draw_overlay_text"](status_line, 1, self.height-14, self.font, 255)
        
        # Show controls - updated to include UI toggle
        if len(self.video_files) > 1:
            controls = "SPACE=Pause | A/D=Prev/Next | U=UI | Q=Exit"
        else:
            controls = "SPACE=Pause | U=UI | Q/ESC=Exit"
        
        self.context["drawing"]["draw_overlay_text"](controls[:35], 1, self.height-9, self.font, 255)
        
        # Show time if available
        if self.duration > 0:
            time_str = f"{self.current_time:.1f}s/{self.duration:.1f}s"
            self.context["drawing"]["draw_overlay_text"](time_str, 1, self.height-4, self.font, 255)

    def _show_error(self, msg):
        self._clear_screen()
        self.context["drawing"]["draw_text"]("Video Player Error:", 2, 2, self.font, 255)
        self.context["drawing"]["draw_text"](msg, 2, 15, self.font, 255)
        self.context["drawing"]["draw_text"]("Press Q or ESC to exit", 2, 30, self.font, 255)

    def _clear_screen(self):
        self.context["drawing"]["clear_screen"]()
        # Also clear any overlay elements that might persist
        self.context["drawing"]["clear_overlay_area"](0, 0, self.width, self.height)

    def _find_ffmpeg_executable(self, executable_name):
        """Find ffmpeg/ffprobe executable cross-platform"""
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
                os.path.join(os.path.dirname(os.path.abspath(__file__)), exe_name),  # In app folder
                os.path.join(self.context["app_path"], exe_name),  # In app folder
            ]
        else:
            # Linux/Unix paths
            possible_paths = [
                f"/usr/bin/{executable_name}",
                f"/usr/local/bin/{executable_name}",
                f"/opt/ffmpeg/bin/{executable_name}",
                f"/snap/bin/{executable_name}",  # Snap installations
                os.path.join(os.path.dirname(os.path.abspath(__file__)), executable_name),  # In app folder
                os.path.join(self.context["app_path"], executable_name),  # In app folder
            ]
        
        # Check each possible path
        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                print(f"[Video Player] Found {executable_name} at: {path}")
                return path
        
        # Try to find in PATH as fallback
        try:
            subprocess.run([executable_name, "-version"], capture_output=True, timeout=2)
            print(f"[Video Player] Using {executable_name} from PATH")
            return executable_name
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
            print(f"[Video Player] {executable_name} not found in common locations or PATH")
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
            
            print(f"[Video Player] Extracting audio to: {self.audio_temp_file}")
            
            # Get current mixer settings to match format
            mixer_frequency = 22050  # Default
            mixer_channels = 1       # Default
            
            try:
                import pygame
                mixer_info = pygame.mixer.get_init()
                if mixer_info:
                    mixer_frequency, _, mixer_channels = mixer_info
                    print(f"[Video Player] Using mixer format: {mixer_frequency}Hz, {mixer_channels} channels")
                else:
                    print(f"[Video Player] Mixer not initialized, using defaults")
            except ImportError:
                print(f"[Video Player] pygame not available, using defaults")
            except Exception:
                print(f"[Video Player] Could not get mixer info, using defaults")
            
            print(f"[Video Player] Keeping audio at normal speed, video will sync to audio timing")
            
            # Build ffmpeg command without speed adjustment - keep audio at normal speed
            cmd = [
                ffmpeg_cmd, "-i", self.video_path,
                "-vn",  # No video
                "-acodec", "pcm_s16le",  # PCM 16-bit little-endian (matches pygame)
                "-ar", str(mixer_frequency),  # Match current mixer sample rate
                "-ac", str(mixer_channels),   # Match current mixer channels
                "-f", "wav",  # Force WAV format
                self.audio_temp_file,
                "-y", "-v", "quiet"  # Overwrite and reduce output
            ]
            
            # Extract audio in background thread
            def extract_and_play_audio():
                try:
                    print(f"[Video Player] Running ffmpeg command: {' '.join(cmd[:5])}...")
                    result = subprocess.run(cmd, capture_output=True, timeout=30)
                    
                    if result.returncode == 0:
                        if os.path.exists(self.audio_temp_file):
                            file_size = os.path.getsize(self.audio_temp_file)
                            print(f"[Video Player] Audio extracted successfully, file size: {file_size} bytes")
                            
                            # Start streaming using ProxiTalk's new streaming system
                            success = self.context["audio"]["start_stream"](self.audio_temp_file)
                            if success:
                                self.audio_start_time = time.time()  # Record when audio actually started
                                print(f"[Video Player] Started audio streaming, audio start time recorded")
                            else:
                                print(f"[Video Player] Failed to start audio streaming")
                        else:
                            print(f"[Video Player] Audio file not created despite success code")
                    else:
                        error_msg = result.stderr.decode() if result.stderr else "Unknown error"
                        print(f"[Video Player] Audio extraction failed (code {result.returncode}): {error_msg}")
                        if result.stdout:
                            print(f"[Video Player] ffmpeg stdout: {result.stdout.decode()}")
                            
                except subprocess.TimeoutExpired:
                    print(f"[Video Player] Audio extraction timeout after 30 seconds")
                except Exception as e:
                    print(f"[Video Player] Error extracting audio: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Start audio extraction in background thread
            audio_thread = threading.Thread(target=extract_and_play_audio, daemon=True)
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
                print(f"[Video Player] Adjusted timing after {pause_duration:.2f}s pause")
            
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
        audio_time = self.context["audio"].get("get_stream_position", lambda: 0.0)()
        
        # Allow up to 0.2 second desync before correcting
        time_diff = abs(video_time - audio_time)
        return time_diff > 0.2
    
    def _check_audio_sync(self):
        """Check and correct audio/video synchronization"""
        if not self.audio_temp_file or self.paused:
            return
            
        # Check if audio is still playing
        if not self.context["audio"]["is_stream_playing"]():
            print(f"[Video Player] Audio stopped unexpectedly at frame {self.frame_count}")
            # Could attempt to restart audio here if needed
            return
            
        # With the new approach, video timing follows audio timing automatically
        # so we mainly just need to ensure audio hasn't stopped unexpectedly
        current_time = time.time()
        if self.video_start_time and self.audio_start_time:
            video_elapsed = current_time - self.video_start_time
            audio_elapsed = current_time - self.audio_start_time
            
            # Just log the timing relationship occasionally for debugging
            if self.frame_count % 30 == 0:  # Every 30 frames
                print(f"[Video Player] Sync check - Video: {video_elapsed:.2f}s, Audio: {audio_elapsed:.2f}s, Frame: {self.frame_count}")

# Usage: This app can be launched from code_editor by selecting a video file
# The code_editor should call: app_manager.load_app("video_player").onopen(file_path)

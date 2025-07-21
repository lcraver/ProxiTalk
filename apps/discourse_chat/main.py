from interfaces import AppBase
import time
import threading
import os
import urllib.request
import urllib.parse
import json
import http.cookiejar
import datetime
import re
import requests
from PIL import Image
import io

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.width = context["screen_width"]
        self.height = context["screen_height"]
        self.context = context
        
        # Chat URL for A Lilian Garden Discourse
        self.chat_url = "https://a-lilian-garden.discourse.group/chat/c/blanket-fort/4"
        
        # Load login credentials
        self.credentials = self.load_credentials()
        
        # Browser state
        self.loading = False
        self.error_message = ""
        self.messages = []
        self.scroll_offset = 0
        
        # Debug mode - set to True to use test messages instead of API calls
        # This is useful for testing the UI without making actual requests
        self.debug_mode = False  # Change to True for offline testing
        
        # Input state
        self.input_mode = False
        self.input_buffer = ""
        
        # Cursor blinking for input
        self.cursor_blink_timer = 0
        self.cursor_visible = True
        self.cursor_blink_rate = 10  # Blink every 10 ticks
        
        # Update timing
        self.last_fetch = time.time()  # Initialize to current time to prevent immediate double-fetch
        self.fetch_interval = 120  # Fetch every 30 seconds
        
        # Performance optimization
        self.needs_redraw = True
        self.has_animated_content = False  # Track if we have GIFs or spinner
        
        # HTTP session management
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))
        self.opener.addheaders = [
            ('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
            ('Accept', 'application/json, text/plain, */*'),
            ('Accept-Language', 'en-US,en;q=0.9'),
        ]
        self.logged_in = False
        self.csrf_token = None
        
        # Session cache file path
        self.session_cache_path = os.path.join(os.path.dirname(__file__), "session_cache.json")
        
        # Load cached session on startup
        self.load_session_cache()
        
    def load_credentials(self):
        """Load login credentials from config file"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                   "config", "discourse_login.conf")
        credentials = {
            "username": "",
            "password": "",
            "email": "",
            "session_token": "",
            "chat_url": self.chat_url
        }
        
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('#') or not line:
                            continue
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip().lower()
                            value = value.strip()
                            
                            if key == "username":
                                credentials["username"] = value
                            elif key == "password":
                                credentials["password"] = value
                            elif key == "email":
                                credentials["email"] = value
                            elif key == "session_token":
                                credentials["session_token"] = value
                            elif key == "chat_url":
                                if value:
                                    credentials["chat_url"] = value
                                    self.chat_url = value
        except Exception as e:
            print(f"[Discourse Chat] Error loading credentials: {e}")
            
        return credentials
        
    def save_session_cache(self):
        """Save session data to cache file"""
        try:
            # Ensure the app directory exists
            app_dir = os.path.dirname(self.session_cache_path)
            os.makedirs(app_dir, exist_ok=True)
            
            # Convert cookies to a serializable format
            cookies_data = []
            for cookie in self.cookie_jar:
                cookies_data.append({
                    'name': cookie.name,
                    'value': cookie.value,
                    'domain': cookie.domain,
                    'path': cookie.path,
                    'secure': cookie.secure,
                    'expires': cookie.expires,
                    'discard': cookie.discard,
                    'comment': cookie.comment,
                    'comment_url': cookie.comment_url,
                    'rest': dict(cookie.rest) if cookie.rest else {}
                })
            
            cache_data = {
                'csrf_token': self.csrf_token,
                'cookies': cookies_data,
                'logged_in': self.logged_in,
                'username': self.credentials.get('username', ''),
                'timestamp': time.time()
            }
            
            with open(self.session_cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            print(f"[Discourse Chat] Session cache saved")
            
        except Exception as e:
            print(f"[Discourse Chat] Failed to save session cache: {e}")
    
    def load_session_cache(self):
        """Load session data from cache file"""
        try:
            if not os.path.exists(self.session_cache_path):
                print("[Discourse Chat] No session cache found")
                return False
            
            with open(self.session_cache_path, 'r') as f:
                cache_data = json.load(f)
            
            # Check if cache is still valid (less than 24 hours old)
            cache_age = time.time() - cache_data.get('timestamp', 0)
            if cache_age > 86400:  # 24 hours
                print("[Discourse Chat] Session cache expired")
                return False
            
            # Check if it's for the same username
            if cache_data.get('username') != self.credentials.get('username'):
                print("[Discourse Chat] Session cache is for different user")
                return False
            
            # Restore CSRF token
            self.csrf_token = cache_data.get('csrf_token')
            self.logged_in = cache_data.get('logged_in', False)
            
            # Restore cookies
            self.cookie_jar.clear()
            for cookie_data in cache_data.get('cookies', []):
                cookie = http.cookiejar.Cookie(
                    version=0,
                    name=cookie_data['name'],
                    value=cookie_data['value'],
                    port=None,
                    port_specified=False,
                    domain=cookie_data['domain'],
                    domain_specified=True,
                    domain_initial_dot=cookie_data['domain'].startswith('.'),
                    path=cookie_data['path'],
                    path_specified=True,
                    secure=cookie_data['secure'],
                    expires=cookie_data['expires'],
                    discard=cookie_data['discard'],
                    comment=cookie_data['comment'],
                    comment_url=cookie_data['comment_url'],
                    rest=cookie_data['rest']
                )
                self.cookie_jar.set_cookie(cookie)
            
            print(f"[Discourse Chat] Session cache loaded successfully (age: {cache_age/3600:.1f} hours)")
            return True
            
        except Exception as e:
            print(f"[Discourse Chat] Failed to load session cache: {e}")
            return False
    
    def generate_test_messages(self):
        """Generate test messages for debug mode"""
        import random
        
        test_users = ['Alice', 'Bob', 'Charlie', 'Diana', 'Eve', 'Frank', 'Grace', 'Henry']
        test_messages = [
            "Hey everyone! How's it going?",
            "Just finished working on the new feature",
            "Anyone want to grab coffee later?",
            "https://vitamin.games/_astro/screenshot%20(3).Cx9jCDKx_uHIVb.webp",
        ]
        
        messages = []
        current_time = datetime.datetime.now()
        
        # Generate 15 test messages with timestamps spread over the last few hours
        for i in range(15):
            # Messages from 3 hours ago to now
            time_offset = random.randint(0, 180)  # 0 to 180 minutes ago
            msg_time = current_time - datetime.timedelta(minutes=time_offset)
            
            message = {
                'username': random.choice(test_users),
                'content': random.choice(test_messages),
                'time': msg_time.strftime('%H:%M')
            }
            
            # Process message for images
            message = self.process_message_with_images(message)
            
            print(f"[Discourse Chat] Generated message: {message['username']} at {message['time']}: {message['content']}")
            messages.append(message)
        
        # Sort by time (oldest first)
        messages.sort(key=lambda x: x['time'])
        
        print(f"[Discourse Chat] Generated {len(messages)} test messages for debug mode")
        return messages
        
    def start(self):
        """Initialize the browser app"""
        print("[Discourse Chat] Started")
        
        # Check if credentials are configured
        if not self.credentials["username"] or self.credentials["username"] == "your_username_here":
            self.error_message = "Please configure login credentials in config/discourse_login.conf"
        else:
            self.error_message = "Loading chat..."
            
        self.refresh_display()
        
        # Start loading messages if credentials are available
        if self.credentials["username"] and self.credentials["username"] != "your_username_here":
            self.fetch_messages_async()
        
    def fetch_messages_async(self):
        """Fetch messages in a separate thread"""
        def fetch_worker():
            try:
                self.loading = True
                self.error_message = "Connecting to chat..."
                
                # Debug mode: use test messages instead of API
                if self.debug_mode:
                    print("[Discourse Chat] Debug mode: using test messages")
                    self.error_message = "Loading test messages..."
                    time.sleep(1)  # Simulate loading time
                    
                    messages = self.generate_test_messages()
                    self.messages = messages
                    self.loading = False
                    self.error_message = ""
                    self.scroll_to_bottom()
                    self.refresh_display()
                    return
                
                # Production mode: use real API
                # First, try to use cached session if not already logged in
                if not self.logged_in:
                    print("[Discourse Chat] Attempting to use cached session...")
                    if self.load_session_cache():
                        # Test if cached session is still valid by trying to fetch messages
                        test_messages = self.fetch_chat_messages()
                        if test_messages and len(test_messages) > 0 and not any('Unable to fetch messages' in msg.get('content', '') for msg in test_messages):
                            print("[Discourse Chat] Cached session is valid")
                            self.messages = test_messages
                            self.loading = False
                            self.error_message = ""
                            self.scroll_to_bottom()
                            self.refresh_display_smart()  # Use smart refresh for callbacks
                            return
                        else:
                            print("[Discourse Chat] Cached session invalid, need fresh login")
                            self.logged_in = False
                            self.csrf_token = None
                    
                    # If cached session failed, do fresh login
                    if not self.login():
                        return
                
                # Fetch chat messages
                self.error_message = "Loading messages..."
                messages = self.fetch_chat_messages()
                
                if messages:
                    self.messages = messages
                    self.loading = False
                    self.error_message = ""
                    # Auto-scroll to show latest messages immediately
                    self.scroll_to_bottom()
                    self.refresh_display_smart()  # Use smart refresh for async callbacks
                else:
                    self.loading = False
                    self.error_message = "No messages found or access denied"
                
            except Exception as e:
                self.loading = False
                self.error_message = f"Connection failed: {str(e)}"
                print(f"[Discourse Chat] Error: {e}")
        
        threading.Thread(target=fetch_worker, daemon=True).start()
    
    def login(self):
        """Login to Discourse"""
        try:
            print(f"[Discourse Chat] Attempting to login as {self.credentials['username']}")
            
            base_url = self.chat_url.split('/chat')[0]
            
            # Step 1: Visit the main site to establish session
            main_response = self.opener.open(base_url)
            print("[Discourse Chat] Established initial session")
            
            # Step 2: Get CSRF token
            csrf_url = f"{base_url}/session/csrf.json"
            try:
                response = self.opener.open(csrf_url)
                response_text = response.read().decode('utf-8')
                print(f"[Discourse Chat] CSRF response: {response_text[:100]}...")
                
                if response_text.strip():
                    csrf_data = json.loads(response_text)
                    self.csrf_token = csrf_data.get('csrf')
                else:
                    print("[Discourse Chat] Empty CSRF response, trying alternative method")
                    # Try alternative CSRF endpoint
                    csrf_url = f"{base_url}/session/csrf"
                    response = self.opener.open(csrf_url)
                    response_text = response.read().decode('utf-8')
                    csrf_data = json.loads(response_text)
                    self.csrf_token = csrf_data.get('csrf')
                    
            except json.JSONDecodeError as e:
                print(f"[Discourse Chat] JSON decode error: {e}")
                print(f"[Discourse Chat] Response text: {response_text}")
                self.error_message = "Failed to get CSRF token - invalid response"
                return False
            
            if not self.csrf_token:
                self.error_message = "Failed to get CSRF token"
                print("[Discourse Chat] No CSRF token in response")
                return False
            
            print(f"[Discourse Chat] Got CSRF token: {self.csrf_token[:10]}...")
            
            # Step 3: Perform login
            login_url = f"{base_url}/session.json"
            login_data = {
                'login': self.credentials['username'],
                'password': self.credentials['password']
            }
            
            data = urllib.parse.urlencode(login_data).encode('utf-8')
            request = urllib.request.Request(login_url, data, method='POST')
            request.add_header('X-CSRF-Token', self.csrf_token)
            request.add_header('Content-Type', 'application/x-www-form-urlencoded')
            request.add_header('X-Requested-With', 'XMLHttpRequest')
            request.add_header('Accept', 'application/json')
            
            response = self.opener.open(request)
            result_text = response.read().decode('utf-8')
            print(f"[Discourse Chat] Login response: {result_text[:200]}...")
            
            if result_text.strip():
                result = json.loads(result_text)
                
                if 'error' in result:
                    self.error_message = f"Login failed: {result['error']}"
                    return False
                elif 'user' in result:
                    self.logged_in = True
                    print("[Discourse Chat] Login successful")
                    self.save_session_cache()  # Cache the successful session
                    return True
                else:
                    # Sometimes login succeeds without explicit user data
                    self.logged_in = True
                    print("[Discourse Chat] Login appears successful")
                    self.save_session_cache()  # Cache the successful session
                    return True
            else:
                self.error_message = "Empty login response"
                return False
            
        except urllib.error.HTTPError as e:
            error_text = e.read().decode('utf-8') if e.fp else str(e)
            self.error_message = f"HTTP Error {e.code}: {error_text[:100]}"
            print(f"[Discourse Chat] HTTP Error: {e.code} - {error_text}")
            return False
        except Exception as e:
            self.error_message = f"Login error: {str(e)}"
            print(f"[Discourse Chat] Login error: {e}")
            return False
    
    def fetch_chat_messages(self):
        """Fetch chat messages from Discourse"""
        try:
            # Extract channel ID from URL
            # URL format: https://a-lilian-garden.discourse.group/chat/c/blanket-fort/4
            channel_id = self.chat_url.split('/')[-1]
            base_url = self.chat_url.split('/chat')[0]
            
            # Based on official Discourse source code, the correct endpoints are:
            # GET /chat/api/channels/:channel_id/messages - for fetching messages
            # GET /chat/api/channels/:channel_id - for channel info (may include recent messages)
            # Add query parameters to limit the number of messages
            api_endpoints = [
                f"{base_url}/chat/api/channels/{channel_id}/messages?page_size=20",
                f"{base_url}/chat/api/channels/{channel_id}/messages?limit=20",
                f"{base_url}/chat/api/channels/{channel_id}?page_size=20"
            ]
            
            for api_url in api_endpoints:
                try:
                    print(f"[Discourse Chat] Trying endpoint: {api_url}")
                    
                    request = urllib.request.Request(api_url)
                    request.add_header('X-CSRF-Token', self.csrf_token)
                    request.add_header('X-Requested-With', 'XMLHttpRequest')
                    request.add_header('Accept', 'application/json')
                    
                    response = self.opener.open(request)
                    response_text = response.read().decode('utf-8')
                    print(f"[Discourse Chat] API response length: {len(response_text)}")
                    
                    # Save raw response to file for debugging
                    # self.save_api_response(api_url, response_text)
                    
                    data = json.loads(response_text)
                    messages = []
                    
                    # Try different response formats based on Discourse source code
                    chat_messages = (data.get('messages') or 
                                   data.get('chat_messages') or 
                                   data.get('channel', {}).get('messages') or [])
                    
                    if chat_messages:
                        for msg in chat_messages:  # Process all messages since we're limiting at API level
                            # Parse message data according to Discourse API format
                            user_data = msg.get('user', {})
                            username = user_data.get('username') or msg.get('username', 'Unknown')
                            content = msg.get('message') or msg.get('content') or msg.get('text', 'No content')
                            created_at = msg.get('created_at') or msg.get('timestamp', '')
                            
                            # Parse timestamp and store datetime for sorting
                            sort_datetime = None
                            try:
                                if 'T' in created_at:  # ISO format
                                    dt = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                                    # Convert to local timezone
                                    local_dt = dt.astimezone()
                                    time_str = local_dt.strftime('%H:%M')
                                    sort_datetime = local_dt
                                else:
                                    time_str = created_at[:5] if created_at else "??:??"
                                    # Try to parse time for basic sorting
                                    if len(created_at) >= 10:
                                        try:
                                            sort_datetime = datetime.datetime.fromisoformat(created_at[:10])
                                        except:
                                            pass
                            except:
                                time_str = created_at[:5] if created_at else "??:??"
                            
                            # Use minimum datetime as fallback for unparseable timestamps
                            if sort_datetime is None:
                                sort_datetime = datetime.datetime.min
                            
                            message = {
                                'username': username,
                                'content': content,
                                'time': time_str,
                                'sort_datetime': sort_datetime
                            }
                            
                            # Process message for images
                            message = self.process_message_with_images(message)
                            messages.append(message)
                        
                        # Sort messages by datetime to ensure chronological order (oldest first)
                        messages.sort(key=lambda x: x['sort_datetime'])
                        
                        # Remove the sort_datetime field as it's no longer needed
                        for msg in messages:
                            del msg['sort_datetime']
                        
                        print(f"[Discourse Chat] Successfully fetched and sorted {len(messages)} messages by time")
                        return messages
                    else:
                        print(f"[Discourse Chat] No messages in response, available keys: {list(data.keys())}")
                        # If this is channel info endpoint, it might have different structure
                        if 'channel' in data:
                            channel_data = data['channel']
                            print(f"[Discourse Chat] Channel data keys: {list(channel_data.keys())}")
                        
                except urllib.error.HTTPError as e:
                    error_text = ""
                    try:
                        error_text = e.read().decode('utf-8')
                    except:
                        pass
                    print(f"[Discourse Chat] HTTP Error for {api_url}: {e.code} - {error_text[:100]}")
                    if e.code == 403:
                        print("[Discourse Chat] Access denied - check authentication and permissions")
                    elif e.code == 404:
                        print("[Discourse Chat] Channel not found - check channel ID")
                    continue
                except json.JSONDecodeError as e:
                    print(f"[Discourse Chat] JSON Error for {api_url}: {e}")
                    continue
            
            # If all endpoints fail, return demo messages
            return [
                {"username": "system", "content": "Unable to fetch messages - API access may be restricted", "time": datetime.datetime.now().strftime("%H:%M")},
                {"username": "info", "content": "Check console for detailed error messages", "time": datetime.datetime.now().strftime("%H:%M")},
            ]
            
        except Exception as e:
            print(f"[Discourse Chat] Error fetching messages: {e}")
            return [
                {"username": "error", "content": f"Failed to get messages: {str(e)}", "time": datetime.datetime.now().strftime("%H:%M")},
            ]
    
    def send_message(self, message_text):
        """Send a message to the chat"""
        def send_worker():
            try:
                # Extract channel ID from URL
                channel_id = self.chat_url.split('/')[-1]
                base_url = self.chat_url.split('/chat')[0]
                
                # Based on official Discourse source code, the correct endpoints are:
                # POST /chat/api/channels/:channel_id/messages - for creating new messages
                # POST /chat/:channel_id - legacy endpoint that also works
                send_endpoints = [
                    f"{base_url}/chat/api/channels/{channel_id}/messages",
                    f"{base_url}/chat/{channel_id}"
                ]
                
                message_data = {
                    'message': message_text,
                    'upload_ids': []
                }
                
                success = False
                for api_url in send_endpoints:
                    try:
                        print(f"[Discourse Chat] Trying to send message to: {api_url}")
                        
                        data = urllib.parse.urlencode(message_data).encode('utf-8')
                        request = urllib.request.Request(api_url, data, method='POST')
                        request.add_header('X-CSRF-Token', self.csrf_token)
                        request.add_header('Content-Type', 'application/x-www-form-urlencoded')
                        request.add_header('X-Requested-With', 'XMLHttpRequest')
                        request.add_header('Accept', 'application/json')
                        
                        response = self.opener.open(request)
                        response_text = response.read().decode('utf-8')
                        print(f"[Discourse Chat] Send response: {response_text[:100]}...")
                        
                        if response_text.strip():
                            result = json.loads(response_text)
                            
                            # Check for successful response patterns from Discourse source
                            if 'message_id' in result or 'success' in result or response.code == 200:
                                print("[Discourse Chat] Message sent successfully")
                                success = True
                                # Refresh messages to show the sent message
                                time.sleep(1)  # Brief delay before refresh
                                self.fetch_messages_async()
                                break
                            else:
                                print(f"[Discourse Chat] Unexpected response format: {list(result.keys())}")
                        else:
                            # Sometimes successful requests return empty responses
                            if response.code == 200:
                                print("[Discourse Chat] Message sent successfully (empty response)")
                                success = True
                                time.sleep(1)
                                self.fetch_messages_async()
                                break
                            
                    except urllib.error.HTTPError as e:
                        error_text = ""
                        try:
                            error_text = e.read().decode('utf-8')
                        except:
                            pass
                        print(f"[Discourse Chat] HTTP Error for {api_url}: {e.code} - {error_text[:100]}")
                        if e.code == 403:
                            print("[Discourse Chat] Permission denied - may need proper authentication")
                        elif e.code == 422:
                            print("[Discourse Chat] Validation error - check message format")
                        continue
                    except json.JSONDecodeError as e:
                        print(f"[Discourse Chat] JSON decode error for {api_url}: {e}")
                        continue
                    except Exception as e:
                        print(f"[Discourse Chat] Error with {api_url}: {e}")
                        continue
                
                if not success:
                    print("[Discourse Chat] All send endpoints failed")
                    # Add as local message if sending fails
                    new_message = {
                        "username": "You (failed)",
                        "content": message_text,
                        "time": datetime.datetime.now().strftime("%H:%M")
                    }
                    self.messages.append(new_message)
                    # Auto-scroll to show the failed message
                    self.scroll_to_bottom()
                    
            except Exception as e:
                print(f"[Discourse Chat] Error sending message: {e}")
                # Add as local message if sending fails
                new_message = {
                    "username": "You (failed)",
                    "content": message_text,
                    "time": datetime.datetime.now().strftime("%H:%M")
                }
                self.messages.append(new_message)
                # Auto-scroll to show the failed message
                self.scroll_to_bottom()
        
        threading.Thread(target=send_worker, daemon=True).start()
    
    def update(self):
        """Update the app display"""
        # Refresh display periodically
        if hasattr(self, 't'):
            self.t += 1
        else:
            self.t = 0
            
        # Handle cursor blinking when in input mode
        cursor_changed = False
        if self.input_mode:
            self.cursor_blink_timer += 1
            if self.cursor_blink_timer >= self.cursor_blink_rate:
                self.cursor_visible = not self.cursor_visible
                self.cursor_blink_timer = 0
                cursor_changed = True  # Track cursor state change for selective update
        else:
            # Reset cursor state when not in input mode
            if self.cursor_visible != True or self.cursor_blink_timer != 0:
                self.cursor_visible = True
                self.cursor_blink_timer = 0
                self.needs_redraw = True
        
        # Handle different types of updates
        # For animated content, update specific areas without full screen clear
        if self.has_animated_content and self.t % 2 == 0:
            # Update animated areas every 2 ticks (0.1 seconds at 20Hz)
            self.update_animated_areas()
        elif cursor_changed:
            # Only update input area when cursor blinks
            self.update_input_area()
        elif self.needs_redraw:
            # Full redraw for static content changes
            if self.t % 10 == 0:  # Only update every 0.5 seconds for efficiency
                self.refresh_display()
                self.needs_redraw = False        
        # Auto-refresh messages every 30 seconds
        current_time = time.time()
        if current_time - self.last_fetch > self.fetch_interval and not self.loading:
            self.last_fetch = current_time
            self.fetch_messages_async()
    
    def update_animated_areas(self):
        """Update only the animated areas without clearing the whole screen"""
        font = self.context["fonts"]["small"]
        
        # Track if we detected animated content
        self.has_animated_content = False
        
        # Update loading spinner area if loading
        if self.loading:
            self.has_animated_content = True
            # Clear only the spinner area (small rectangle in top right)
            spinner_x = self.width - 12
            spinner_y = 1
            spinner_area_width = 12
            spinner_area_height = 6
            
            # Use batching for spinner update
            self.context["drawing"]["begin_batch"]()
            
            # Clear the spinner area with black background
            self.context["drawing"]["draw_area"](spinner_x, spinner_y, spinner_area_width, spinner_area_height, 0)
            
            # Draw the animated spinner
            spinner_chars = ["|", "/", "-", "\\"]
            spinner_index = (getattr(self, 't', 0) // 2) % len(spinner_chars)
            spinner_char = spinner_chars[spinner_index]
            self.context["drawing"]["draw_text"](f"[{spinner_char}]", spinner_x, spinner_y, font)
            
            self.context["drawing"]["end_batch"]()
        else:
            # Clear spinner area when not loading (ensures spinner disappears)
            if hasattr(self, '_was_loading') and self._was_loading:
                spinner_x = self.width - 12
                spinner_y = 1
                spinner_area_width = 12
                spinner_area_height = 6
                
                self.context["drawing"]["begin_batch"]()
                self.context["drawing"]["draw_area"](spinner_x, spinner_y, spinner_area_width, spinner_area_height, 0)
                self.context["drawing"]["end_batch"]()
                
                self._was_loading = False
                self.needs_redraw = True  # Trigger a full refresh to show messages
        
        # Track loading state for spinner cleanup
        self._was_loading = self.loading
        
        # Update animated GIFs in messages (if any)
        self.update_animated_gifs()
    
    def update_animated_gifs(self):
        """Update only animated GIF areas in messages"""
        if not self.messages:
            return
            
        font = self.context["fonts"]["small"]
        line_height = 5
        top_y = 2
        input_area_reserve = 15
        bottom_y = self.height - input_area_reserve
        
        # Calculate which messages are visible and check for animated GIFs
        total_messages = len(self.messages)
        start_message_index = max(0, total_messages - self.scroll_offset - 1)
        
        # Track current drawing position
        y_pos = top_y
        max_line_width = 30
        username_line_width = max_line_width - 2
        content_line_width = max_line_width - 4
        
        for i in range(start_message_index, total_messages):
            if y_pos >= bottom_y:
                break
                
            message = self.messages[i]
            
            # Calculate message layout (similar to draw_messages)
            time_username = f"{message['username']} [{message['time']}]"
            username_lines = self.wrap_text(time_username, username_line_width)
            content_lines = self.wrap_text(message['content'], content_line_width)
            
            # Skip past username and content lines
            y_pos += (len(username_lines) + len(content_lines) + 1) * line_height
            
            # Check for animated images
            if 'images' in message and message['images']:
                for img_data in message['images']:
                    if y_pos >= bottom_y:
                        break
                        
                    if self.has_image_data(img_data) and img_data.get('type') == 'animated':
                        self.has_animated_content = True
                        
                        # Get current image frame
                        current_image = self.get_current_image(img_data)
                        img_width = img_data['width']
                        img_height = img_data['height']
                        
                        # Calculate position (centered horizontally)
                        x_offset = (self.width - img_width) // 2
                        
                        # Make sure image fits in available space
                        max_image_height = min(img_height, bottom_y - y_pos - 5)
                        if max_image_height > 10:
                            if img_height > max_image_height:
                                # Scale the image to fit
                                scale_factor = max_image_height / img_height
                                new_width = int(img_width * scale_factor)
                                new_height = int(max_image_height)
                                
                                # Resize the PIL image
                                from PIL import Image
                                scaled_image = current_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                                
                                # Clear only the scaled image area
                                x_offset = (self.width - new_width) // 2
                                self.context["drawing"]["draw_area"](x_offset, y_pos, new_width, new_height, 0)
                                self.context["drawing"]["draw_image"](scaled_image, x_offset, y_pos)
                                y_pos += new_height + 2
                            else:
                                # Clear only the original image area
                                self.context["drawing"]["draw_area"](x_offset, y_pos, img_width, img_height, 0)
                                self.context["drawing"]["draw_image"](current_image, x_offset, y_pos)
                                y_pos += img_height + 2
                        else:
                            # Not enough space, skip
                            y_pos += line_height
                    else:
                        # Skip non-animated images or placeholders
                        if self.has_image_data(img_data):
                            y_pos += img_data['height'] + 2
                        else:
                            y_pos += line_height
            
            # Add gap between messages
            y_pos += line_height
    
    def refresh_display_smart(self):
        """Smart refresh that uses selective updates when possible"""
        if self.has_animated_content:
            # If we have animated content, do selective updates
            self.update_animated_areas()
        else:
            # Otherwise do a full refresh
            self.refresh_display()
    
    def update_input_area(self):
        """Update only the input area for cursor blinking"""
        if self.input_mode:
            # For cursor blinking, we only need to clear and redraw the cursor on overlay
            # The base layer with text remains unchanged
            font = self.context["fonts"]["small"]
            line_height = 5
            
            # Calculate cursor position
            max_input_width = 28
            prefix = "Say: "
            content_width = max_input_width - len(prefix)
            wrapped_lines = self.wrap_text(self.input_buffer, content_width)
            max_input_lines = 3
            display_lines = wrapped_lines[-max_input_lines:] if len(wrapped_lines) > max_input_lines else wrapped_lines
            
            if display_lines:
                input_y = self.height - 12
                start_y = input_y - (len(display_lines) - 1) * line_height
                last_line_y = start_y + (len(display_lines) - 1) * line_height
                last_line = display_lines[-1]
                cursor_prefix = prefix if len(display_lines) == 1 else " " * len(prefix)
                
                # Calculate cursor position
                cursor_text = cursor_prefix + last_line
                text_width, _ = self.context["get_text_size"](cursor_text, font)
                cursor_x = 2 + text_width
                
                # Clear the overlay area where cursor might be (wider area to ensure we clear it)
                self.context["drawing"]["clear_overlay_area"](cursor_x - 2, last_line_y - 1, 4, line_height + 1)
                
                # Draw cursor if visible
                if self.cursor_visible and cursor_x < self.width - 2:
                    self.context["drawing"]["draw_overlay_area"](cursor_x, last_line_y, 1, line_height - 1, 0)
    
    def refresh_display(self):
        """Refresh the entire display (full redraw)"""
        self.context["drawing"]["begin_batch"]()
        self.context["drawing"]["clear_screen"]()
        self.context["drawing"]["clear_overlay_area"](0, 0, self.width, self.height)  # Clear overlay as well
        
        font = self.context["fonts"]["small"]
        line_height = 5
        
        # Track if we have animated content that needs frequent updates
        self.has_animated_content = False
        
        # Draw loading spinner in top right if loading
        if self.loading:
            self.has_animated_content = True  # Mark that we have animated content
            spinner_chars = ["|", "/", "-", "\\"]
            spinner_index = (getattr(self, 't', 0) // 2) % len(spinner_chars)  # Rotate every 0.1 seconds at 20Hz
            spinner_char = spinner_chars[spinner_index]
            spinner_x = self.width - 12  # Position in top right
            self.context["drawing"]["draw_text"](f"[{spinner_char}]", spinner_x, 1, font)
        
        if self.error_message and not self.loading:
            # Show error message only when not loading
            lines = self.wrap_text(self.error_message, 28)  # Slightly less than max for error messages
            y_pos = 12
            for line in lines[:3]:  # Show max 3 lines of error
                self.context["drawing"]["draw_text"](line, 2, y_pos, font)
                y_pos += line_height
            
            # Show configuration instructions if no credentials
            if "configure login" in self.error_message.lower():
                y_pos += line_height
                config_lines = [
                    "1. Edit config/discourse_login.conf",
                    "2. Replace 'your_username_here'",
                    "   with your actual username",
                    "3. Add your password and email",
                    "4. Restart this app",
                    "",
                    "The config file is hidden from git."
                ]
                for line in config_lines:
                    if y_pos < self.height - 25:  # Leave room for status
                        self.context["drawing"]["draw_text"](line, 2, y_pos, font)
                        y_pos += line_height
            else:
                # Show note about real implementation
                y_pos += line_height
                note_lines = [
                    "Note: This is a demo interface.",
                    "Real chat would need Discourse API",
                    "or proper authentication."
                ]
                for line in note_lines:
                    self.context["drawing"]["draw_text"](line, 2, y_pos, font)
                    y_pos += line_height
                
        elif self.messages or self.loading:
            # Show messages when we have them OR when loading (to show "Loading messages...")
            self.draw_messages()
        
        # Draw input area
        self.draw_input_area()
        
        self.context["drawing"]["end_batch"]()
    
    def draw_messages(self):
        """Draw the chat messages ensuring latest messages are visible above input area"""
        font = self.context["fonts"]["small"]
        line_height = 5
        
        # Calculate message area boundaries
        top_y = 2  # Start after title and separator
        # Reserve space for input area at bottom
        input_area_reserve = 15  # Reserve enough space for input area
        bottom_y = self.height - input_area_reserve
        
        available_height = bottom_y - top_y
        
        if not self.messages:
            # if loading show loading message
            if self.loading:
                self.context["drawing"]["draw_text"]("Loading messages...", 2, top_y, font)
            else:
                self.context["drawing"]["draw_text"]("No messages yet", 2, top_y, font)
            return
        
        # Calculate optimal text width based on screen size
        max_line_width = 30
        username_line_width = max_line_width - 2  # Account for indent
        content_line_width = max_line_width - 4   # Account for content indent
        
        # Calculate which messages to show based on scroll offset
        total_messages = len(self.messages)
        
        # Determine the starting message index based on scroll offset
        # scroll_offset = 0 means show the most recent messages
        # scroll_offset > 0 means scroll back to show older messages
        start_message_index = max(0, total_messages - self.scroll_offset-1)
        
        # Pre-calculate message data for the range we want to display
        messages_to_display = []
        current_height = 0
        
        # Process messages from start_message_index forward, but limit by available space
        for i in range(start_message_index, total_messages):
                
            message = self.messages[i]
            
            # Calculate space needed for this message
            time_username = f"{message['username']} [{message['time']}]"
            username_lines = self.wrap_text(time_username, username_line_width)
            content_lines = self.wrap_text(message['content'], content_line_width)
            
            # Calculate total height needed for this message
            message_height = (len(username_lines) + len(content_lines) + 1) * line_height  # +1 for gap
            
            # Add height for images if any
            if 'images' in message and message['images']:
                for img_data in message['images']:
                    if 'image' in img_data:
                        message_height += img_data['height'] + 2  # +2 for gap after image
                    else:
                        message_height += line_height  # For "[Image]" placeholder
            
            # # Check if we have room for this message
            # if current_height + message_height > available_height:
            #     break  # Can't fit any more messages
            
            # Add this message to the display list
            messages_to_display.append({
                'message': message,
                'username_lines': username_lines,
                'content_lines': content_lines,
                'height': message_height
            })
            
            current_height += message_height
        
        # Now draw the messages from top to bottom in the available space
        y_pos = top_y
        
        for msg_data in messages_to_display:
            # Draw username/time lines with white background
            for line in msg_data['username_lines']:
                if y_pos < bottom_y:  # Make sure we don't draw into input area
                    # Calculate background width based on text length
                    text_width, _ = self.context["get_text_size"](line, font)
                    bg_width = text_width + 2  # Add some padding
                    
                    # Draw white background for username line
                    self.context["drawing"]["draw_area"](0, y_pos-1, bg_width+1, line_height, 255)
                    
                    # Draw username/time text in black on white background
                    self.context["drawing"]["draw_text"](line, 2, y_pos, font, 0)
                    y_pos += line_height
            
            # Draw content lines (indented)
            for content_line in msg_data['content_lines']:
                if y_pos < bottom_y:  # Make sure we don't draw into input area
                    self.context["drawing"]["draw_text"](f" {content_line}", 2, y_pos, font)
                    y_pos += line_height
            
            # Draw images if any are available
            message = msg_data['message']
            if 'images' in message and message['images']:
                for img_data in message['images']:
                    if y_pos < bottom_y and self.has_image_data(img_data):
                        # Check if this is an animated GIF
                        if img_data.get('type') == 'animated':
                            self.has_animated_content = True  # Mark that we have animated GIFs
                        
                        # Get the current image to display
                        current_image = self.get_current_image(img_data)
                        img_width = img_data['width']
                        img_height = img_data['height']
                        
                        # Center the image horizontally
                        x_offset = (self.width - img_width) // 2
                        
                        # Make sure image fits in available space (allow some overlap with input area if needed)
                        max_image_height = min(img_height, bottom_y - y_pos - 5)  # Leave at least 5px buffer
                        if max_image_height > 10:  # Only draw if we have reasonable space
                            # Scale image down if needed to fit available space
                            if img_height > max_image_height:
                                # Scale the image to fit
                                scale_factor = max_image_height / img_height
                                new_width = int(img_width * scale_factor)
                                new_height = int(max_image_height)
                                
                                # Resize the PIL image
                                scaled_image = current_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                                
                                # Re-center horizontally
                                x_offset = (self.width - new_width) // 2
                                self.context["drawing"]["draw_image"](scaled_image, x_offset, y_pos)
                                y_pos += new_height + 2
                            else:
                                # Image fits as-is
                                self.context["drawing"]["draw_image"](current_image, x_offset, y_pos)
                                y_pos += img_height + 2  # Add small gap after image
                        else:
                            # Not enough space for image, show placeholder
                            self.context["drawing"]["draw_text"](" [Image]", 2, y_pos, font)
                            y_pos += line_height
                            y_pos += line_height
            
            # Add gap between messages
            if y_pos < bottom_y:
                y_pos += line_height
        
        # Draw scrollbar on the right side if there are messages to scroll through
        if len(self.messages) > 1:  # Only show scrollbar if there's something to scroll
            scrollbar_x = self.width - 3  # Position at right edge
            scrollbar_top = top_y
            scrollbar_bottom = bottom_y
            scrollbar_height = scrollbar_bottom - scrollbar_top
            
            # Calculate scrollbar position based on scroll_offset
            max_scroll = max(0, len(self.messages) - 1)
            if max_scroll > 0:
                # Calculate the position of the scroll indicator
                scroll_ratio = self.scroll_offset / max_scroll
                # Invert the ratio since scroll_offset=0 means bottom (newest), max means top (oldest)
                scroll_ratio = 1.0 - scroll_ratio
                
                # Calculate indicator position (leave some padding at top and bottom)
                indicator_height = max(2, scrollbar_height // 10)  # At least 2px tall
                usable_height = scrollbar_height - indicator_height
                indicator_y = scrollbar_top + int(scroll_ratio * usable_height)
                
                # Draw scrollbar background (light gray track)
                self.context["drawing"]["draw_area"](scrollbar_x+2, scrollbar_top, 1, scrollbar_height, 255)
                
                # Draw scroll indicator (dark gray/black)
                self.context["drawing"]["draw_area"](scrollbar_x, indicator_y, 2, indicator_height, 255)
    
    def draw_input_area(self):
        """Draw the input area"""
        font = self.context["fonts"]["small"]
        line_height = 5
        input_y = self.height - 12
        
        if self.input_mode:
            # Calculate available width for input text (account for "Say: " prefix)
            max_input_width = 28  # Total width for 128px screen
            prefix = "Say: "
            content_width = max_input_width - len(prefix)
            
            # Wrap the input buffer text
            wrapped_lines = self.wrap_text(self.input_buffer, content_width)
            
            # Show up to 3 lines of input text
            max_input_lines = 3
            display_lines = wrapped_lines[-max_input_lines:] if len(wrapped_lines) > max_input_lines else wrapped_lines
            
            # Calculate starting Y position (move up if we have multiple lines)
            start_y = input_y - (len(display_lines) - 1) * line_height
            
            # Calculate background area dimensions
            bg_width = self.width
            bg_height = (len(display_lines) + 1) * line_height + 4  # Include help text and padding
            bg_y = start_y - 2  # Start background slightly above text
            
            # Draw white background for input area
            self.context["drawing"]["draw_area"](0, bg_y, bg_width, bg_height, 255)
            
            # Draw the input lines
            for i, line in enumerate(display_lines):
                y = start_y + i * line_height
                if i == 0:
                    # First line includes the "Say: " prefix
                    display_text = f"{prefix}{line}"
                else:
                    # Subsequent lines are indented to align with the text after "Say: "
                    display_text = f"{' ' * len(prefix)}{line}"
                
                # Truncate if still too long (safety check)
                if len(display_text) > max_input_width:
                    display_text = display_text[:max_input_width-3] + "..."
                
                self.context["drawing"]["draw_text"](display_text, 2, y, font, 0)  # Black text on white background
            
            # Add cursor indicator on the last line (blinking vertical line)
            if len(display_lines) > 0 and self.cursor_visible:
                last_line_y = start_y + (len(display_lines) - 1) * line_height
                last_line = display_lines[-1]
                cursor_prefix = prefix if len(display_lines) == 1 else " " * len(prefix)
                
                # Calculate cursor position using actual text width measurement
                # The cursor should appear after the prefix and the content of the last line
                cursor_text = cursor_prefix + last_line
                text_width, _ = self.context["get_text_size"](cursor_text, font)
                cursor_x = 2 + text_width
                
                if cursor_x < self.width - 2:  # Make sure cursor fits on screen
                    # Draw cursor as a black vertical line on overlay layer (not base layer)
                    self.context["drawing"]["draw_overlay_area"](cursor_x, last_line_y, 1, line_height - 1, 0)
            
            # Show character count and help text below input area (calculate properly)
            char_count = len(self.input_buffer)
            help_y = start_y + len(display_lines) * line_height  # Position help text after all input lines
            help_text = f"({char_count}/200) Enter=Send ESC=Cancel"
            if len(help_text) > max_input_width:
                help_text = f"({char_count}/200) Enter/ESC"
            self.context["drawing"]["draw_text"](help_text, 2, help_y, font, 0)  # Black text on white background
            
        else:
            # Show help with white background
            help_text = "Press I to type a message"
            bg_width = len(help_text) * 4 + 4  # Calculate width based on character width (4px per char) + padding
            bg_height = line_height + 2  # Height for one line plus padding
            status_y = self.height - 7
            
            # Draw white background area
            self.context["drawing"]["draw_area"](0, input_y - 1, self.width, bg_height * 2, 255)  # White background
            self.context["drawing"]["draw_text"](help_text, 2, input_y, font, 0)  # Black text on white background
            
            # Draw status line
            if self.input_mode:
                status = "Type: Enter=Send, ESC=Cancel"
            elif not self.credentials["username"] or self.credentials["username"] == "your_username_here":
                status = "C:Config R:Refresh ESC:Quit"
            elif self.logged_in:
                status = f"{self.credentials['username'][:4]} UP/DN:Scroll I:Input ESC:Quit"
            else:
                status = f"{self.credentials['username'][:4]} [ERROR] ESC:Quit"
            self.context["drawing"]["draw_text"](status, 2, status_y, font, 0)
    
    def wrap_text(self, text, width):
        """Wrap text to specified width, preserving trailing spaces"""
        if not text:
            return [""]
        
        # Check if text ends with spaces - we need to preserve them
        trailing_spaces = len(text) - len(text.rstrip())
        
        # Split into words, but preserve spaces
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            if len(current_line + " " + word) <= width:
                if current_line:
                    current_line += " " + word
                else:
                    current_line = word
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        # If the original text had trailing spaces, add them to the last line
        if trailing_spaces > 0 and lines:
            lines[-1] += " " * trailing_spaces
        
        return lines if lines else [""]
    
    def save_api_response(self, endpoint_url, response_text):
        """Save API response to file for debugging"""
        try:
            # Create a safe filename from the endpoint URL
            import re
            endpoint_name = re.sub(r'[^\w\-_]', '_', endpoint_url.split('/')[-1])
            if not endpoint_name:
                endpoint_name = "messages"
            
            # Create timestamp for unique filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"discourse_api_response_{endpoint_name}_{timestamp}.json"
            
            # Save to the same directory as the main app
            app_dir = os.path.dirname(__file__)
            filepath = os.path.join(app_dir, filename)
            
            # Pretty format the JSON if possible
            try:
                parsed_json = json.loads(response_text)
                formatted_response = json.dumps(parsed_json, indent=2, ensure_ascii=False)
            except:
                formatted_response = response_text
            
            with open(filepath, 'w', encoding='utf-8') as f:
                # f.write(f"# Discourse API Response\n")
                # f.write(f"# Endpoint: {endpoint_url}\n")
                # f.write(f"# Timestamp: {datetime.datetime.now().isoformat()}\n")
                # f.write(f"# Response Length: {len(response_text)} characters\n")
                # f.write(f"#\n\n")
                f.write(formatted_response)
            
            print(f"[Discourse Chat] API response saved to: {filepath}")
            
        except Exception as e:
            print(f"[Discourse Chat] Failed to save API response: {e}")
    
    def scroll_to_bottom(self):
        """Automatically scroll to show the latest messages"""
        # Set scroll_offset to 0 to show the most recent messages
        self.scroll_offset = 0
    
    def show_config_info(self):
        """Show configuration file information"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                   "config", "discourse_login.conf")
        self.error_message = f"Config file: {config_path}"
        print(f"[Discourse Chat] Config file location: {config_path}")
    
    def onkeyup(self, keycode):
        """Handle keyboard input"""
        if self.input_mode:
            self.handle_input_mode(keycode)
        else:
            self.handle_browser_mode(keycode)
    
    def handle_input_mode(self, keycode):
        """Handle keyboard input in input mode"""
        if keycode == "KEY_ESC":
            self.input_mode = False
            self.input_buffer = ""
            self.needs_redraw = True
            
        elif keycode == "KEY_ENTER":
            if self.input_buffer.strip():
                # Send the message to the real chat
                if self.logged_in:
                    self.send_message(self.input_buffer.strip())
                else:
                    # Add as local message if not logged in
                    new_message = {
                        "username": "You (local)",
                        "content": self.input_buffer.strip(),
                        "time": datetime.datetime.now().strftime("%H:%M")
                    }
                    self.messages.append(new_message)
                    # Auto-scroll to show the new message
                    self.scroll_to_bottom()
                
            self.input_mode = False
            self.input_buffer = ""
            self.needs_redraw = True
            
        elif keycode == "KEY_BACKSPACE":
            if self.input_buffer:
                self.input_buffer = self.input_buffer[:-1]
                # Reset cursor blinking when typing
                self.cursor_visible = True
                self.cursor_blink_timer = 0
                self.needs_redraw = True
        
        else:
            # Handle character input
            char = self.keycode_to_char(keycode)
            if char and len(self.input_buffer) < 200:  # Increased limit for multi-line input
                self.input_buffer += char
                # Reset cursor blinking when typing
                self.cursor_visible = True
                self.cursor_blink_timer = 0
                self.needs_redraw = True
    
    def handle_browser_mode(self, keycode):
        """Handle keyboard input in browser mode"""
            
        if keycode == "KEY_UP" or (keycode == "KEY_W" and not self.input_mode):
            # Increase scroll_offset to go back in time (show older messages)
            max_scroll = max(0, len(self.messages) - 1)  # Can scroll back to the very first message
            if self.scroll_offset < max_scroll:
                self.scroll_offset += 1
                self.needs_redraw = True
                
        elif keycode == "KEY_DOWN" or (keycode == "KEY_S" and not self.input_mode):
            # Decrease scroll_offset to go forward in time (show newer messages)
            if self.scroll_offset > 0:
                self.scroll_offset -= 1
                self.needs_redraw = True
                
        elif keycode == "KEY_I":
            if self.credentials["username"] and self.credentials["username"] != "your_username_here":
                self.input_mode = True
                self.input_buffer = ""
                # Reset cursor blinking state
                self.cursor_visible = True
                self.cursor_blink_timer = 0
                self.needs_redraw = True
            
        elif keycode == "KEY_R" and not self.input_mode:
            self.fetch_messages_async()
            self.needs_redraw = True
            
        elif keycode == "KEY_C" and not self.input_mode:
            # Show config file location
            self.show_config_info()
            self.needs_redraw = True
            
        elif (keycode == "KEY_Q" and not self.input_mode) or keycode == "KEY_ESC":
            self.return_to_launcher()
    
    def keycode_to_char(self, keycode):
        """Convert keycode to character"""
        key_map = {
            "KEY_SPACE": " ",
            "KEY_A": "a", "KEY_B": "b", "KEY_C": "c", "KEY_D": "d", "KEY_E": "e",
            "KEY_F": "f", "KEY_G": "g", "KEY_H": "h", "KEY_I": "i", "KEY_J": "j",
            "KEY_K": "k", "KEY_L": "l", "KEY_M": "m", "KEY_N": "n", "KEY_O": "o",
            "KEY_P": "p", "KEY_Q": "q", "KEY_R": "r", "KEY_S": "s", "KEY_T": "t",
            "KEY_U": "u", "KEY_V": "v", "KEY_W": "w", "KEY_X": "x", "KEY_Y": "y",
            "KEY_Z": "z",
            "KEY_0": "0", "KEY_1": "1", "KEY_2": "2", "KEY_3": "3", "KEY_4": "4",
            "KEY_5": "5", "KEY_6": "6", "KEY_7": "7", "KEY_8": "8", "KEY_9": "9",
            "KEY_SEMICOLON": ";", "KEY_APOSTROPHE": "'", "KEY_COMMA": ",",
            "KEY_PERIOD": ".", "KEY_SLASH": "/", "KEY_BACKSLASH": "\\",
            "KEY_LEFTBRACE": "[", "KEY_RIGHTBRACE": "]", "KEY_MINUS": "-",
            "KEY_EQUAL": "=", "KEY_GRAVE": "`"
        }
        return key_map.get(keycode, "")
    
    def return_to_launcher(self):
        """Return to the launcher app"""
        app_manager = self.context["app_manager"]
        app_manager.swap_app_async("discourse_chat", "launcher", update_rate_hz=20.0, delay=0.1)
    
    def stop(self):
        """Clean up when app stops"""
        print("[Discourse Chat] Stopped")
    
    def is_image_url(self, url):
        """Check if a URL points to an image"""
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
        try:
            # Parse the URL and check extension
            parsed = urllib.parse.urlparse(url.lower())
            path = parsed.path
            return any(path.endswith(ext) for ext in image_extensions)
        except:
            return False
    
    def extract_image_urls(self, text):
        """Extract image URLs from message text"""
        # Pattern to match URLs
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+\.(jpg|jpeg|png|gif|bmp|webp)(?:\?[^\s]*)?'
        urls = re.findall(url_pattern, text, re.IGNORECASE)
        # Return the full URLs (re.findall returns tuples with groups, so we need to reconstruct)
        image_urls = []
        for match in re.finditer(url_pattern, text, re.IGNORECASE):
            image_urls.append(match.group(0))
        return image_urls
    
    def download_and_process_image(self, url, max_width=120, max_height=40):
        """Download and process an image for display, with GIF animation support"""
        try:
            # Download image with timeout
            response = requests.get(url, timeout=5, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            
            # Load image from bytes
            image_data = io.BytesIO(response.content)
            image = Image.open(image_data)
            
            # Check if this is an animated GIF
            is_animated = hasattr(image, 'is_animated') and image.is_animated
            
            if is_animated:
                print(f"[Discourse Chat] Processing animated GIF with {image.n_frames} frames")
                return self.process_animated_gif(image, max_width, max_height)
            else:
                # Process static image
                return self.process_static_image(image, max_width, max_height)
            
        except Exception as e:
            print(f"[Discourse Chat] Failed to download image {url}: {e}")
            return None
    
    def process_static_image(self, image, max_width, max_height):
        """Process a static image"""
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Calculate scaling to fit within max dimensions
        img_width, img_height = image.size
        scale_x = max_width / img_width
        scale_y = max_height / img_height
        scale = min(scale_x, scale_y, 1.0)  # Don't upscale
        
        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        
        # Resize image
        resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Convert to 1-bit (monochrome) for the display system
        gray_image = resized_image.convert('L')
        mono_image = gray_image.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
        
        return {
            'type': 'static',
            'image': mono_image,
            'width': new_width,
            'height': new_height
        }
    
    def process_animated_gif(self, gif_image, max_width, max_height):
        """Process an animated GIF into frames"""
        frames = []
        durations = []
        
        # Calculate scaling once for all frames
        img_width, img_height = gif_image.size
        scale_x = max_width / img_width
        scale_y = max_height / img_height
        scale = min(scale_x, scale_y, 1.0)  # Don't upscale
        
        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        
        try:
            for frame_num in range(gif_image.n_frames):
                gif_image.seek(frame_num)
                
                # Get frame duration (in milliseconds)
                duration = gif_image.info.get('duration', 100)  # Default 100ms if not specified
                durations.append(max(duration, 50))  # Minimum 50ms per frame to avoid too fast animation
                
                # Convert frame to RGB
                frame = gif_image.convert('RGB')
                
                # Resize frame
                resized_frame = frame.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Convert to 1-bit (monochrome) for the display system
                gray_frame = resized_frame.convert('L')
                mono_frame = gray_frame.convert('1', dither=Image.Dither.FLOYDSTEINBERG)
                
                frames.append(mono_frame)
                
        except Exception as e:
            print(f"[Discourse Chat] Error processing GIF frames: {e}")
            # Fall back to first frame as static image
            gif_image.seek(0)
            return self.process_static_image(gif_image, max_width, max_height)
        
        print(f"[Discourse Chat] Processed {len(frames)} frames from animated GIF")
        
        return {
            'type': 'animated',
            'frames': frames,
            'durations': durations,
            'width': new_width,
            'height': new_height,
            'current_frame': 0,
            'last_frame_time': time.time()
        }

    def has_image_data(self, img_data):
        """Check if image data contains displayable image"""
        if img_data['type'] == 'static':
            return 'image' in img_data
        elif img_data['type'] == 'animated':
            return 'frames' in img_data and len(img_data['frames']) > 0
        return False
    
    def get_current_image(self, img_data):
        """Get the current image to display (handles animation)"""
        if img_data['type'] == 'static':
            return img_data['image']
        elif img_data['type'] == 'animated':
            return self.update_animation_frame(img_data)
        return None
    
    def update_animation_frame(self, img_data):
        """Update animation frame and return current frame"""
        current_time = time.time()
        
        # Check if it's time to advance to the next frame
        frame_duration = img_data['durations'][img_data['current_frame']] / 1000.0  # Convert ms to seconds
        
        if current_time - img_data['last_frame_time'] >= frame_duration:
            # Advance to next frame
            img_data['current_frame'] = (img_data['current_frame'] + 1) % len(img_data['frames'])
            img_data['last_frame_time'] = current_time
        
        return img_data['frames'][img_data['current_frame']]

    def process_message_with_images(self, message):
        """Process a message and detect/download any images"""
        content = message['content']
        image_urls = self.extract_image_urls(content)
        
        # Remove image URLs from the displayed content
        display_content = content
        for url in image_urls:
            # Remove the URL from the display content
            display_content = display_content.replace(url, '').strip()
        
        # Clean up any extra whitespace or empty lines
        display_content = ' '.join(display_content.split())
        
        # Update the message content for display (keep original for reference)
        message['original_content'] = content  # Store original content
        message['content'] = display_content if display_content else "[Image]"  # Use cleaned content for display
        
        # Add image data to message if images found
        if image_urls:
            message['images'] = []
            for url in image_urls:
                print(f"[Discourse Chat] Found image URL: {url}")
                # Download image in a separate thread to avoid blocking
                def download_image(url, msg):
                    img_data = self.download_and_process_image(url)
                    if img_data:
                        img_data['url'] = url
                        msg['images'].append(img_data)
                        print(f"[Discourse Chat] Downloaded and processed image: {url}")
                        # Trigger display refresh - mark for redraw instead of immediate refresh
                        self.needs_redraw = True
                
                # Start download in background
                thread = threading.Thread(target=download_image, args=(url, message))
                thread.daemon = True
                thread.start()
        
        return message

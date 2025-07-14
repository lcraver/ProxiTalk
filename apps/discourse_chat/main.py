from interfaces import AppBase
import time
import threading
import os
import urllib.request
import urllib.parse
import json
import http.cookiejar
import datetime

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
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
            "The weather is amazing today!",
            "I found a great tutorial on Python decorators",
            "Weekend plans anyone?",
            "This chat app is working great!",
            "Does anyone know a good restaurant nearby?",
            "I'm debugging some tricky code right now",
            "Happy Friday everyone! 🎉",
            "Check out this cool project I found",
            "The scrolling feature is working nicely",
            "Who's joining the meeting later?",
            "I love how responsive this interface is",
            "Just deployed the latest updates",
            "Time for lunch break!",
            "The message sorting looks perfect now",
            "Anyone tried the new API endpoints?",
            "Great work on the session caching!",
            "This debug mode is really helpful"
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
                            self.refresh_display()
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
                    self.refresh_display()  # Force immediate display refresh
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
                            
                            messages.append({
                                'username': username,
                                'content': content,
                                'time': time_str,
                                'sort_datetime': sort_datetime
                            })
                        
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
        if self.input_mode:
            self.cursor_blink_timer += 1
            if self.cursor_blink_timer >= self.cursor_blink_rate:
                self.cursor_visible = not self.cursor_visible
                self.cursor_blink_timer = 0
        else:
            # Reset cursor state when not in input mode
            self.cursor_visible = True
            self.cursor_blink_timer = 0
            
        if self.t % 10 == 0:  # Update every 0.5 seconds at 20Hz
            self.refresh_display()
            
        # Auto-refresh messages every 30 seconds
        current_time = time.time()
        if current_time - self.last_fetch > self.fetch_interval and not self.loading:
            self.last_fetch = current_time
            self.fetch_messages_async()
    
    def refresh_display(self):
        """Refresh the display with current status"""
        self.display_queue.put(("clear_base",))
        
        font = self.context["fonts"]["small"]
        line_height = 5
        
        # Draw title bar
        title = "Discourse Chat - Blanket Fort"
        self.display_queue.put(("draw_base_text", font, title, 2, 1, 255))
        
        # Draw loading spinner in top right if loading
        if self.loading:
            spinner_chars = ["|", "/", "-", "\\"]
            spinner_index = (getattr(self, 't', 0) // 2) % len(spinner_chars)  # Rotate every 0.1 seconds at 20Hz
            spinner_char = spinner_chars[spinner_index]
            spinner_x = self.width - 12  # Position in top right
            self.display_queue.put(("draw_base_text", font, f"[{spinner_char}]", spinner_x, 1, 255))
        
        # Draw separator line
        self.display_queue.put(("draw_base_text", font, "-" * 20, 2, 6, 255))
        
        if self.error_message and not self.loading:
            # Show error message only when not loading
            lines = self.wrap_text(self.error_message, 28)  # Slightly less than max for error messages
            y_pos = 12
            for line in lines[:3]:  # Show max 3 lines of error
                self.display_queue.put(("draw_base_text", font, line, 2, y_pos, 255))
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
                        self.display_queue.put(("draw_base_text", font, line, 2, y_pos, 255))
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
                    self.display_queue.put(("draw_base_text", font, line, 2, y_pos, 255))
                    y_pos += line_height
                
        else:
            # Always show messages (even when loading)
            self.draw_messages()
        
        # Draw input area
        self.draw_input_area()
    
    def draw_messages(self):
        """Draw the chat messages ensuring latest messages are visible above input area"""
        font = self.context["fonts"]["small"]
        line_height = 5
        
        # Calculate message area boundaries
        top_y = 10  # Start after title and separator
        # Reserve space for input area at bottom
        input_area_reserve = 15  # Reserve enough space for input area
        bottom_y = self.height - input_area_reserve
        
        available_height = bottom_y - top_y
        
        # draw a box around the message area
        # self.display_queue.put(("draw_base_area", 0, top_y, self.width, available_height, 255))
        
        if not self.messages:
            # if loading show loading message
            if self.loading:
                self.display_queue.put(("draw_base_text", font, "Loading messages...", 2, top_y))
            else:
                self.display_queue.put(("draw_base_text", font, "No messages yet", 2, top_y))
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
                    self.display_queue.put(("draw_base_area", 0, y_pos, bg_width, line_height-1, 255))
                    
                    # Draw username/time text in black on white background
                    self.display_queue.put(("draw_base_text", font, line, 2, y_pos, 0))
                    y_pos += line_height
            
            # Draw content lines (indented)
            for content_line in msg_data['content_lines']:
                if y_pos < bottom_y:  # Make sure we don't draw into input area
                    self.display_queue.put(("draw_base_text", font, f" {content_line}", 2, y_pos))
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
                self.display_queue.put(("draw_base_area", scrollbar_x+2, scrollbar_top, 0, scrollbar_height, 255))
                
                # Draw scroll indicator (dark gray/black)
                self.display_queue.put(("draw_base_area", scrollbar_x, indicator_y, 2, indicator_height, 255))
    
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
            self.display_queue.put(("draw_base_area", 0, bg_y, bg_width, bg_height, 255))
            
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
                
                self.display_queue.put(("draw_base_text", font, display_text, 2, y, 0))  # Black text on white background
            
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
                    # Draw cursor as a black vertical line (similar to code editor)
                    self.display_queue.put(("draw_base_area", cursor_x, last_line_y, 1, line_height - 1, 0))
            
            # Show character count and help text below input area (calculate properly)
            char_count = len(self.input_buffer)
            help_y = start_y + len(display_lines) * line_height  # Position help text after all input lines
            help_text = f"({char_count}/200) Enter=Send ESC=Cancel"
            if len(help_text) > max_input_width:
                help_text = f"({char_count}/200) Enter/ESC"
            self.display_queue.put(("draw_base_text", font, help_text, 2, help_y, 0))  # Black text on white background
            
        else:
            # Show help with white background
            help_text = "Press I to type a message"
            bg_width = len(help_text) * 4 + 4  # Calculate width based on character width (4px per char) + padding
            bg_height = line_height + 2  # Height for one line plus padding
            status_y = self.height - 7
            
            # Draw white background area
            self.display_queue.put(("draw_base_area", 0, input_y - 1, self.width, bg_height * 2, 255))  # White background
            self.display_queue.put(("draw_base_text", font, help_text, 2, input_y, 0))  # Black text on white background
            
            # Draw status line
            if self.input_mode:
                status = "Type: Enter=Send, ESC=Cancel"
            elif not self.credentials["username"] or self.credentials["username"] == "your_username_here":
                status = "C:Config R:Refresh ESC:Quit"
            elif self.logged_in:
                status = f"{self.credentials['username'][:4]} UP/DN:Scroll I:Input ESC:Quit"
            else:
                status = f"{self.credentials['username'][:4]} [ERROR] ESC:Quit"
            self.display_queue.put(("draw_base_text", font, status, 2, status_y, 0))
    
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
            
        elif keycode == "KEY_BACKSPACE":
            if self.input_buffer:
                self.input_buffer = self.input_buffer[:-1]
                # Reset cursor blinking when typing
                self.cursor_visible = True
                self.cursor_blink_timer = 0
        
        else:
            # Handle character input
            char = self.keycode_to_char(keycode)
            if char and len(self.input_buffer) < 200:  # Increased limit for multi-line input
                self.input_buffer += char
                # Reset cursor blinking when typing
                self.cursor_visible = True
                self.cursor_blink_timer = 0
    
    def handle_browser_mode(self, keycode):
        """Handle keyboard input in browser mode"""
        if keycode == "KEY_ESC":
            self.return_to_launcher()
            
        elif keycode == "KEY_UP":
            # Increase scroll_offset to go back in time (show older messages)
            max_scroll = max(0, len(self.messages) - 1)  # Can scroll back to the very first message
            if self.scroll_offset < max_scroll:
                self.scroll_offset += 1
                
        elif keycode == "KEY_DOWN":
            # Decrease scroll_offset to go forward in time (show newer messages)
            if self.scroll_offset > 0:
                self.scroll_offset -= 1
                
        elif keycode == "KEY_I":
            if self.credentials["username"] and self.credentials["username"] != "your_username_here":
                self.input_mode = True
                self.input_buffer = ""
                # Reset cursor blinking state
                self.cursor_visible = True
                self.cursor_blink_timer = 0
            
        elif keycode == "KEY_R":
            self.fetch_messages_async()
            
        elif keycode == "KEY_C":
            # Show config file location
            self.show_config_info()
            
        elif keycode == "KEY_Q":
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
        self.display_queue.put(("set_screen", "Launcher", "Returning to Launcher..."))
        
        if "app_manager" in self.context:
            app_manager = self.context["app_manager"]
            app_manager.swap_app_async("discourse_chat", "launcher", update_rate_hz=20.0, delay=0.1)
        else:
            print("[Discourse Chat] No app_manager available in context")
    
    def stop(self):
        """Clean up when app stops"""
        print("[Discourse Chat] Stopped")

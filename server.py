import os
import uuid
import asyncio
import threading
import re
import time
import html
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, session, make_response
from flask_cors import CORS
import json
import secrets
from werkzeug.security import safe_join

# Import the necessary modules
from main import WikiTranslator
from wikipedia import Wikipedia

app = Flask(__name__, static_url_path='')
# Configure CORS to only allow requests from trusted origins
CORS(app, resources={r"/api/*": {"origins": os.environ.get("ALLOWED_ORIGINS", "http://localhost:5000").split(","),
                                "supports_credentials": True}})

# Configure session
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", secrets.token_hex(16))
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Rate limiting configuration
RATE_LIMIT = int(os.environ.get("RATE_LIMIT", "10"))  # requests per minute
RATE_LIMIT_WINDOW = 60  # seconds
rate_limit_data = {}  # {ip: [timestamp1, timestamp2, ...]}

# Max concurrent jobs configuration
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "5"))

# Dictionary to store translation jobs
translation_jobs = {}

# Dictionary to store CSRF tokens
csrf_tokens = {}

def generate_csrf_token():
    """Generate a secure CSRF token"""
    return secrets.token_hex(32)

def csrf_required(f):
    """Decorator to require CSRF token for POST requests"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == "POST":
            token = request.headers.get('X-CSRF-Token')
            if not token or token not in csrf_tokens.values():
                return jsonify({"error": "Invalid or missing CSRF token"}), 403
        return f(*args, **kwargs)
    return decorated_function

def rate_limit(f):
    """Decorator to apply rate limiting"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ip = request.remote_addr
        current_time = time.time()
        
        # Initialize or clean up old timestamps
        if ip not in rate_limit_data:
            rate_limit_data[ip] = []
        
        # Remove timestamps older than the window
        rate_limit_data[ip] = [t for t in rate_limit_data[ip] if current_time - t < RATE_LIMIT_WINDOW]
        
        # Check if rate limit exceeded
        if len(rate_limit_data[ip]) >= RATE_LIMIT:
            return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
        
        # Add current timestamp
        rate_limit_data[ip].append(current_time)
        
        return f(*args, **kwargs)
    return decorated_function

def check_concurrent_jobs(f):
    """Decorator to limit concurrent jobs per IP"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ip = request.remote_addr
        
        # Count active jobs for this IP
        active_jobs = sum(1 for job in translation_jobs.values()
                         if job.get("ip") == ip and job.get("status") in ["queued", "processing"])
        
        if active_jobs >= MAX_CONCURRENT_JOBS:
            return jsonify({"error": f"Maximum of {MAX_CONCURRENT_JOBS} concurrent jobs allowed"}), 429
        
        return f(*args, **kwargs)
    return decorated_function

def sanitize_glossary(content):
    """Sanitize glossary content to prevent injection attacks"""
    if not content:
        return ""
    
    # HTML escape the content
    content = html.escape(content)
    
    # Only allow valid glossary entries (term:translation format)
    sanitized_lines = []
    for line in content.splitlines():
        if ":" in line:
            term, translation = line.split(":", 1)
            # Basic validation of terms and translations
            if re.match(r'^[\w\s\-.,;\'\"()]+$', term) and re.match(r'^[\w\s\-.,;\'\"()]+$', translation):
                sanitized_lines.append(f"{term.strip()}:{translation.strip()}")
    
    return "\n".join(sanitized_lines)

def run_translation(job_id, title_name, th_title_name, glossary_file):
    """
    Run the translation process in a separate thread.
    
    Args:
        job_id: The unique ID for this translation job
        title_name: The English Wikipedia article title
        th_title_name: The Thai title for the article
        glossary_file: Path to the glossary file (or None for default)
    """
    try:
        # Update job status to "processing"
        translation_jobs[job_id]["status"] = "processing"
        
        # Use default glossary if none provided
        if not glossary_file:
            glossary_file = "my_glossary.txt"
        
        # Create translator instance
        translator = WikiTranslator(
            title_name=title_name,
            th_title_name=th_title_name,
            glossary_file=glossary_file
        )
        
        # Run the translation process
        async def run_async():
            translated_sections = await translator.process_tasks(translator.wikitext)
            final_translation = "\n".join(translated_sections)
            final_translation = translator.page.replace_references(final_translation)
            
            # Update job with completed status and result
            translation_jobs[job_id]["status"] = "completed"
            translation_jobs[job_id]["result"] = final_translation
        
        # Create and run the asyncio event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_async())
        loop.close()
        
    except Exception as e:
        # Update job with error status
        translation_jobs[job_id]["status"] = "error"
        translation_jobs[job_id]["error"] = str(e)

@app.route('/')
def index():
    """Serve the main HTML page"""
    response = make_response(send_from_directory('frontend', 'index.html'))
    # Set Content Security Policy
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'"
    # Set other security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

@app.route('/css/<path:filename>')
def serve_css(filename):
    """Serve CSS files"""
    try:
        # Use safe_join to prevent path traversal
        return send_from_directory('frontend/css', filename)
    except Exception as e:
        app.logger.error(f"Error serving CSS file: {str(e)}")
        return jsonify({"error": "File not found"}), 404

@app.route('/js/<path:filename>')
def serve_js(filename):
    """Serve JavaScript files"""
    try:
        # Use safe_join to prevent path traversal
        return send_from_directory('frontend/js', filename)
    except Exception as e:
        app.logger.error(f"Error serving JS file: {str(e)}")
        return jsonify({"error": "File not found"}), 404

@app.route('/api/csrf-token', methods=['GET'])
def get_csrf_token():
    """Get a CSRF token for form submission"""
    token = generate_csrf_token()
    session_id = str(uuid.uuid4())
    csrf_tokens[session_id] = token
    
    # Clean up old tokens (simple cleanup mechanism)
    if len(csrf_tokens) > 1000:  # Arbitrary limit
        old_tokens = list(csrf_tokens.keys())[:-100]  # Keep the 100 most recent
        for old_token in old_tokens:
            csrf_tokens.pop(old_token, None)
    
    response = jsonify({"token": token})
    response.set_cookie('session_id', session_id, httponly=True, secure=True, samesite='Lax')
    return response

@app.route('/api/translate', methods=['POST'])
@csrf_required
@rate_limit
@check_concurrent_jobs
def translate():
    """
    Start a new translation job.
    
    Expected JSON payload:
    {
        "title": "English Wikipedia article title",
        "th_title": "Thai title for the article",
        "glossary": "Optional custom glossary content"
    }
    
    Returns:
    {
        "job_id": "Unique job ID for tracking the translation"
    }
    """
    try:
        data = request.json
        
        # Validate required fields
        if not data or 'title' not in data or 'th_title' not in data:
            return jsonify({"error": "Missing required fields: title and th_title"}), 400
        
        # Validate and sanitize inputs
        title = data['title'].strip()
        th_title = data['th_title'].strip()
        
        if not title or not th_title:
            return jsonify({"error": "Title and Thai title cannot be empty"}), 400
            
        # Generate a unique job ID
        job_id = str(uuid.uuid4())
        
        # Create a custom glossary file if provided
        glossary_file = None
        if 'glossary' in data and data['glossary']:
            # Sanitize glossary content
            sanitized_glossary = sanitize_glossary(data['glossary'])
            if sanitized_glossary:
                glossary_file = f"custom_glossary_{job_id}.txt"
                try:
                    with open(glossary_file, "w", encoding="utf-8") as f:
                        f.write(sanitized_glossary)
                except Exception as e:
                    app.logger.error(f"Error writing glossary file: {str(e)}")
                    return jsonify({"error": "Failed to create glossary file"}), 500
        
        # Initialize job in the dictionary
        translation_jobs[job_id] = {
            "title": title,
            "th_title": th_title,
            "status": "queued",
            "glossary_file": glossary_file,
            "result": None,
            "error": None,
            "ip": request.remote_addr,
            "created_at": time.time()
        }
        
        # Start translation in a separate thread
        thread = threading.Thread(
            target=run_translation,
            args=(job_id, title, th_title, glossary_file)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({"job_id": job_id})
    except Exception as e:
        app.logger.error(f"Error in translate endpoint: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500

@app.route('/api/status/<job_id>', methods=['GET'])
def get_status(job_id):
    """
    Get the status of a translation job.
    
    Returns:
    {
        "status": "queued|processing|completed|error",
        "progress": 0-100 (percentage complete, if available)
    }
    """
    try:
        # Validate job_id format to prevent injection
        if not re.match(r'^[0-9a-f\-]+$', job_id):
            return jsonify({"error": "Invalid job ID format"}), 400
            
        if job_id not in translation_jobs:
            return jsonify({"error": "Job not found"}), 404
        
        job = translation_jobs[job_id]
        
        response = {
            "status": job["status"],
            "title": job["title"],
            "th_title": job["th_title"]
        }
        
        # Add error message if there was an error, but sanitize it
        if job["status"] == "error" and job["error"]:
            # Sanitize error message to avoid exposing sensitive information
            error_msg = job["error"]
            # Remove file paths, stack traces, etc.
            error_msg = re.sub(r'(at|in) [A-Za-z]:\\.*', '[internal path]', error_msg)
            error_msg = re.sub(r'File ".*?"', 'File "[internal]"', error_msg)
            error_msg = re.sub(r'line \d+', 'line [number]', error_msg)
            
            response["error"] = "An error occurred during translation"
            # Log the actual error for debugging
            app.logger.error(f"Job {job_id} error: {job['error']}")
        
        return jsonify(response)
    except Exception as e:
        app.logger.error(f"Error in get_status endpoint: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500

@app.route('/api/result/<job_id>', methods=['GET'])
def get_result(job_id):
    """
    Get the result of a completed translation job.
    
    Returns:
    {
        "result": "Translated content"
    }
    """
    try:
        # Validate job_id format to prevent injection
        if not re.match(r'^[0-9a-f\-]+$', job_id):
            return jsonify({"error": "Invalid job ID format"}), 400
            
        if job_id not in translation_jobs:
            return jsonify({"error": "Job not found"}), 404
        
        job = translation_jobs[job_id]
        
        if job["status"] != "completed":
            return jsonify({"error": "Translation not completed yet"}), 400
        
        # Clean up glossary file if it exists
        if job.get("glossary_file") and os.path.exists(job["glossary_file"]):
            try:
                os.remove(job["glossary_file"])
            except Exception as e:
                app.logger.warning(f"Failed to remove glossary file: {str(e)}")
        
        return jsonify({"result": job["result"]})
    except Exception as e:
        app.logger.error(f"Error in get_result endpoint: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500

# Cleanup job for old translation jobs
def cleanup_old_jobs():
    """Remove old translation jobs to prevent memory leaks"""
    current_time = time.time()
    jobs_to_remove = []
    
    for job_id, job in translation_jobs.items():
        # Remove completed or error jobs older than 1 hour
        if job.get("created_at") and current_time - job["created_at"] > 3600:
            if job["status"] in ["completed", "error"]:
                jobs_to_remove.append(job_id)
                
                # Clean up glossary file if it exists
                if job.get("glossary_file") and os.path.exists(job["glossary_file"]):
                    try:
                        os.remove(job["glossary_file"])
                    except Exception as e:
                        app.logger.warning(f"Failed to remove glossary file: {str(e)}")
    
    # Remove the jobs
    for job_id in jobs_to_remove:
        translation_jobs.pop(job_id, None)
    
    # Schedule the next cleanup
    threading.Timer(300, cleanup_old_jobs).start()  # Run every 5 minutes

if __name__ == '__main__':
    # Create frontend directory if it doesn't exist
    os.makedirs('frontend/css', exist_ok=True)
    os.makedirs('frontend/js', exist_ok=True)
    
    # Start the cleanup job
    cleanup_old_jobs()
    
    # Run the app with debug mode disabled in production
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(debug=debug_mode, port=5000)
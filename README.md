# Wiki Translator

## Project Overview and Purpose

Wiki Translator is a comprehensive tool designed to translate English Wikipedia articles to Thai with high accuracy and proper formatting. The project leverages two powerful AI technologies:

1. **Google Cloud Translation API** - For efficient translation of standard text and terminology
2. **Google Generative AI (Gemini)** - For intelligent handling of complex content, context preservation, and natural-sounding translations

The application offers both a command-line interface for batch processing and a modern web interface for interactive use, making it accessible to both developers and end users.

## Architecture Overview

The Wiki Translator implements a hybrid architecture combining traditional machine translation with advanced AI capabilities:

```mermaid
graph TD
    A[User] -->|Web Interface| B[Flask Server]
    A -->|Command Line| C[CLI Interface]
    B -->|Translation Request| D[WikiTranslator]
    C -->|Translation Request| D
    D -->|Fetch Article| E[Wikipedia API]
    D -->|Translate Text| F[Google Cloud Translation API]
    D -->|Process Complex Text| G[Google Generative AI (Gemini)]
    D -->|Apply Glossary| H[Custom Glossary]
    D -->|Output| I[Translated Article]
```

### Backend Components

- **Python Core** - Handles the main translation logic and processing
- **Flask Server** - Provides RESTful API endpoints and serves the web interface
- **Asynchronous Processing** - Manages translation jobs efficiently with asyncio

### Frontend Components

- **HTML/CSS/JavaScript** - Provides an intuitive user interface
- **Responsive Design** - Works on both desktop and mobile devices

## Key Features and Capabilities

### Gemini AI Integration (Key Feature)

The project leverages Google's Gemini AI model to provide superior translation quality:

- **Context-Aware Translation** - Understands the broader context of the article
- **Specialized Content Handling** - Properly processes technical terms, idioms, and cultural references
- **Natural Language Output** - Produces fluent, natural-sounding Thai text

### Other Features

- **Wikipedia-Specific Formatting** - Preserves article structure, references, and special formatting
- **Custom Glossary Support** - Allows for consistent translation of specific terms
- **Asynchronous Processing** - Handles large articles efficiently
- **Reference Preservation** - Maintains all citations and references in the proper format
- **Web Interface** - User-friendly interface for submitting translation requests and viewing results
- **RESTful API** - Programmatic access to translation functionality
- **Job Management** - Track the status of translation jobs

## Installation Instructions

### Prerequisites

- Python 3.6+
- Google Cloud Platform account with Translation API enabled
- Google AI Studio account for Gemini API access
- Git

### Steps

1. **Clone the repository:**

   ```bash
   git clone https://github.com/z3tz3r0/ai-wiki-translator.git
   cd "Wiki translator"
   ```

2. **Install Python dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Set up Google Cloud Translation API:**

   - Create a Google Cloud Platform project
   - Enable the Cloud Translation API
   - Create a service account and download the JSON key file
   - Set the environment variable:

     ```bash
     # On Linux/macOS
     export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/keyfile.json"

     # On Windows
     set GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\your\keyfile.json"
     ```

4. **Set up Google Generative AI (Gemini):**

   - Create an API key in Google AI Studio
   - Set the environment variable:

     ```bash
     # On Linux/macOS
     export API_KEY="your-gemini-api-key"

     # On Windows
     set API_KEY="your-gemini-api-key"
     ```

## Usage Instructions

### Command-Line Interface

1. **Configure translation parameters:**
   Edit the `main.py` file to specify:

   - `TITLE_NAME`: The English Wikipedia article title
   - `TH_TITLE_NAME`: The desired Thai title
   - `GLOSSARY_FILE`: Path to your custom glossary file (optional)

2. **Run the translator:**

   ```bash
   python main.py
   ```

3. **View the output:**
   The translated content will be saved to `output.txt`

### Web Interface

1. **Start the web server:**

   ```bash
   python server.py
   ```

2. **Access the web interface:**
   Open your browser and navigate to `http://localhost:5000`

3. **Submit a translation request:**

   - Enter the English Wikipedia article title
   - Enter the desired Thai title
   - Optionally, provide a custom glossary
   - Click "Translate"

4. **Monitor translation progress:**
   The interface will show the current status of your translation job

5. **View and download results:**
   Once complete, you can view, copy, or download the translated article

### API Endpoints

The Wiki Translator provides a RESTful API for programmatic access:

#### 1. Start a Translation Job

- **Endpoint:** `/api/translate`
- **Method:** POST
- **Request Body:**
  ```json
  {
    "title": "English Wikipedia article title",
    "th_title": "Thai title for the article",
    "glossary": "Optional custom glossary content"
  }
  ```
- **Response:**
  ```json
  {
    "job_id": "unique-job-id"
  }
  ```

#### 2. Check Translation Status

- **Endpoint:** `/api/status/<job_id>`
- **Method:** GET
- **Response:**
  ```json
  {
    "status": "queued|processing|completed|error",
    "title": "English Wikipedia article title",
    "th_title": "Thai title for the article",
    "error": "Error message (if status is 'error')"
  }
  ```

#### 3. Get Translation Result

- **Endpoint:** `/api/result/<job_id>`
- **Method:** GET
- **Response:**
  ```json
  {
    "result": "Translated content"
  }
  ```

## Configuration Details

### Google Cloud Translation API

The project uses the Google Cloud Translation API v3 for translating standard text. Configuration is handled through:

- Environment variable: `GOOGLE_APPLICATION_CREDENTIALS`
- Environment variable: `GOOGLE_CLOUD_PROJECT_ID` for the Google Cloud project ID

### Google Generative AI (Gemini)

The Gemini AI model is used for handling complex text translation with context awareness. Configuration is managed through:

- Environment variable: `API_KEY`
- Model configuration in `assistant.py`:
  - Model: `gemini-1.5-flash`
  - Temperature: 1
  - Top-p: 0.95
  - Top-k: 64
  - Max output tokens: 8192

### Custom Glossary

The glossary file allows for consistent translation of specific terms:

- Default file: `my_glossary.txt`
- Format: `English Term:Thai Translation` (one per line)
- Example:
  ```
  Narcissism:ความหลงตนเอง
  self-love:รักตัวเอง
  ```

### Security Configuration

The application includes several security features that can be configured through environment variables:

- `SECRET_KEY`: Secret key for session management (defaults to a randomly generated key)
- `ALLOWED_ORIGINS`: Comma-separated list of allowed origins for CORS (defaults to "http://localhost:5000")
- `RATE_LIMIT`: Maximum number of requests per minute per IP (defaults to 10)
- `MAX_CONCURRENT_JOBS`: Maximum number of concurrent translation jobs per IP (defaults to 5)
- `FLASK_DEBUG`: Set to "true" to enable debug mode (should be "false" in production)

## Project Structure

### Core Files

- `main.py` - Main entry point and translation workflow
- `wikipedia.py` - Handles fetching and parsing Wikipedia content
- `translator.py` - Interfaces with Google Cloud Translation API
- `assistant.py` - Interfaces with Google Generative AI (Gemini)
- `utils.py` - Utility functions for text processing
- `server.py` - Flask web server and API endpoints

### Frontend Files

- `frontend/index.html` - Main web interface
- `frontend/css/styles.css` - Styling for the web interface
- `frontend/js/script.js` - Client-side functionality

### Other Files

- `requirements.txt` - Python dependencies
- `my_glossary.txt` - Default glossary file
- `output.txt` - Default output file for CLI mode

## Security Features

The Wiki Translator implements several security measures to protect against common vulnerabilities:

### API Key and Credential Management

- Google Cloud project ID is stored in environment variables
- API keys and credentials are not hardcoded in the source code
- Session management with secure cookies

### Input Validation and Sanitization

- All user inputs are validated and sanitized
- Custom glossary content is sanitized to prevent injection attacks
- File path handling includes protection against path traversal attacks

### Error Handling and Information Disclosure

- Error messages are sanitized to prevent information leakage
- Detailed errors are logged but not exposed to users
- Proper exception handling throughout the application

### Web Security

- CSRF protection for all POST requests
- Content Security Policy headers to prevent XSS attacks
- CORS configuration to only allow requests from trusted origins
- HTTP security headers (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection)

### Rate Limiting and Resource Management

- Rate limiting to prevent abuse (configurable via environment variables)
- Limits on concurrent translation jobs per IP address
- Automatic cleanup of old translation jobs and temporary files

## Technologies Used

### Backend

- **Python** - Core programming language
- **Flask** - Web framework
- **Google Cloud Translation API** - Machine translation service
- **Google Generative AI (Gemini)** - Advanced AI model for context-aware translation
- **asyncio** - Asynchronous I/O for efficient processing

### Frontend

- **HTML5** - Structure
- **CSS3** - Styling with responsive design
- **JavaScript** - Client-side functionality
- **Fetch API** - Asynchronous HTTP requests

### Development Tools

- **Git** - Version control
- **pip** - Package management

## Contributing

This project is not currently open for external contributions.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

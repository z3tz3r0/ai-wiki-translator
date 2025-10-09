"""Application factory for the AI Wiki Translator backend."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, send_from_directory
from flask_cors import CORS

from app.controllers.translation_controller import create_translation_blueprint
from app.services.wiki_translation_service import WikiTranslationService


load_dotenv()


def create_app() -> Flask:
    app = Flask(__name__, static_url_path="")

    allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5000").split(",")
    CORS(app, resources={r"/api/*": {"origins": allowed_origins, "supports_credentials": True}})

    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", os.urandom(16)),
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    prompt_template = os.environ.get(
        "PROMPT_TEMPLATE_PATH", "app/prompts/system_instruction_en.md"
    )
    translation_service = WikiTranslationService(prompt_template=prompt_template)
    blueprint = create_translation_blueprint(
        translation_service,
        rate_limit=int(os.environ.get("RATE_LIMIT", "10")),
        rate_limit_window=int(os.environ.get("RATE_LIMIT_WINDOW", "60")),
        max_concurrent_jobs=int(os.environ.get("MAX_CONCURRENT_JOBS", "5")),
    )
    app.register_blueprint(blueprint)

    @app.route("/")
    def index():
        response = make_response(send_from_directory("frontend", "index.html"))
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

    @app.route("/css/<path:filename>")
    def serve_css(filename: str):
        return send_from_directory("frontend/css", filename)

    @app.route("/js/<path:filename>")
    def serve_js(filename: str):
        return send_from_directory("frontend/js", filename)

    @app.errorhandler(404)
    def not_found(_: Exception):
        return jsonify({"error": "Not found"}), 404

    return app


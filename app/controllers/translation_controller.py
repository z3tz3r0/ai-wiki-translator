"""Flask blueprint exposing the translation workflow."""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from functools import wraps
from pathlib import Path
from typing import Callable, Dict

from flask import Blueprint, jsonify, request, session

from app.models.translation_request import TranslationRequest
from app.services.wiki_translation_service import WikiTranslationService


def create_translation_blueprint(
    translation_service: WikiTranslationService,
    *,
    rate_limit: int = 10,
    rate_limit_window: int = 60,
    max_concurrent_jobs: int = 5,
) -> Blueprint:
    blueprint = Blueprint("translation", __name__, url_prefix="/api")

    translation_jobs: Dict[str, Dict] = {}
    rate_limit_data: Dict[str, list[float]] = {}
    csrf_tokens: Dict[str, str] = {}
    glossary_directory = Path(".cache/glossaries")
    glossary_directory.mkdir(parents=True, exist_ok=True)

    def generate_csrf_token() -> str:
        token = uuid.uuid4().hex
        csrf_tokens[token] = token
        return token

    def csrf_required(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if request.method == "POST":
                token = request.headers.get("X-CSRF-Token")
                if not token or token not in csrf_tokens:
                    return jsonify({"error": "Invalid or missing CSRF token"}), 403
            return func(*args, **kwargs)

        return wrapper

    def rate_limited(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            ip = request.remote_addr or "anonymous"
            now = time.time()
            entries = rate_limit_data.setdefault(ip, [])
            rate_limit_data[ip] = [ts for ts in entries if now - ts < rate_limit_window]
            if len(rate_limit_data[ip]) >= rate_limit:
                return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429
            rate_limit_data[ip].append(now)
            return func(*args, **kwargs)

        return wrapper

    def limit_concurrent_jobs(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            ip = request.remote_addr or "anonymous"
            active_jobs = sum(
                1
                for job in translation_jobs.values()
                if job.get("ip") == ip and job.get("status") in {"queued", "processing"}
            )
            if active_jobs >= max_concurrent_jobs:
                return (
                    jsonify({"error": f"Maximum of {max_concurrent_jobs} concurrent jobs allowed"}),
                    429,
                )
            return func(*args, **kwargs)

        return wrapper

    def clean_glossary_lines(content: str | None) -> str:
        if not content:
            return ""
        sanitized_lines = []
        for line in content.splitlines():
            if ":" not in line:
                continue
            term, translation = line.split(":", 1)
            sanitized_lines.append(f"{term.strip()}:{translation.strip()}")
        return "\n".join(sanitized_lines)

    def write_custom_glossary(job_id: str, content: str) -> Path | None:
        sanitized = clean_glossary_lines(content)
        if not sanitized:
            return None
        gloss_path = glossary_directory / f"{job_id}.txt"
        gloss_path.write_text(sanitized, encoding="utf-8")
        return gloss_path

    def run_translation(job_id: str, request_payload: Dict) -> None:
        translation_jobs[job_id]["status"] = "processing"
        try:
            translation_request = TranslationRequest(
                title_name=request_payload["title_name"],
                thai_title_name=request_payload["thai_title_name"],
                glossary_path=request_payload.get("glossary_path"),
            )
            result = asyncio.run(translation_service.translate(translation_request))
            translation_jobs[job_id]["status"] = "completed"
            translation_jobs[job_id]["result"] = result
        except Exception as exc:  # pragma: no cover - defensive
            translation_jobs[job_id]["status"] = "error"
            translation_jobs[job_id]["error"] = str(exc)

    @blueprint.route("/csrf-token", methods=["GET"])
    def get_csrf_token():
        token = generate_csrf_token()
        session["csrf_token"] = token
        return jsonify({"token": token})

    @blueprint.route("/translate", methods=["POST"])
    @csrf_required
    @rate_limited
    @limit_concurrent_jobs
    def create_translation_job():
        data = request.get_json(force=True)
        title_name = data.get("title_name") or data.get("title")
        thai_title_name = data.get("thai_title_name") or data.get("th_title")
        glossary_path = data.get("glossary_path")
        inline_glossary = data.get("glossary")
        if not title_name or not thai_title_name:
            return jsonify({"error": "title_name and thai_title_name are required"}), 400

        job_id = str(uuid.uuid4())
        translation_jobs[job_id] = {
            "status": "queued",
            "ip": request.remote_addr or "anonymous",
            "glossary_preview": clean_glossary_lines(inline_glossary),
        }
        if inline_glossary and not glossary_path:
            gloss_path = write_custom_glossary(job_id, inline_glossary)
            glossary_path = str(gloss_path) if gloss_path else None

        payload = {
            "title_name": title_name,
            "thai_title_name": thai_title_name,
            "glossary_path": glossary_path,
        }
        thread = threading.Thread(target=run_translation, args=(job_id, payload), daemon=True)
        thread.start()
        return jsonify({"job_id": job_id}), 202

    @blueprint.route("/translate/<job_id>", methods=["GET"])
    def get_translation_job(job_id: str):
        job = translation_jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        response = {k: v for k, v in job.items() if k != "ip"}
        return jsonify(response)

    @blueprint.route("/status/<job_id>", methods=["GET"])
    def get_status(job_id: str):
        job = translation_jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        return jsonify({"status": job.get("status"), "error": job.get("error")})

    @blueprint.route("/result/<job_id>", methods=["GET"])
    def get_result(job_id: str):
        job = translation_jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        if job.get("status") != "completed":
            return jsonify({"error": "Translation not completed"}), 400
        return jsonify({"result": job.get("result")})

    return blueprint


"""Typer CLI · the primary user surface.

Three single-command Typer apps, each wired as its own ``[project.scripts]``
entry point:

* ``wiki-translate <title>`` · translate one Thai article on demand
* ``wiki-translate-queue [--config PATH]`` · run a TOML queue
* ``wiki-list-drafts [--since DATE]`` · list drafts on disk
"""

from __future__ import annotations

import asyncio
import datetime
from pathlib import Path
from typing import Annotated

import typer

from app.application.dto import Draft, TranslateArticleCommand
from app.application.use_cases.run_queued import parse_queue_toml
from app.interfaces.cli import bootstrap as bootstrap

_DEFAULT_QUEUE_PATH: Path = Path.home() / ".config" / "wiki-translator" / "queue.toml"

translate_app = typer.Typer(add_completion=False, no_args_is_help=True)
translate_queue_app = typer.Typer(add_completion=False)
list_drafts_app = typer.Typer(add_completion=False)


def _format_draft_summary(draft: Draft) -> str:
    status = "passed" if draft.validation.passed else "REJECTED"
    return (
        f"{status} · {draft.slug} · source={draft.source_lang} · "
        f"words={draft.source_score.word_count} · refs={draft.source_score.ref_count}"
    )


def _print_draft(draft: Draft) -> None:
    typer.echo(_format_draft_summary(draft))
    if not draft.validation.passed:
        for reason in draft.validation.reasons:
            typer.echo(f"  - {reason}")


@translate_app.command()
def translate(
    title: Annotated[
        str,
        typer.Argument(help="Thai-Wikipedia article title to translate."),
    ],
    source_lang: Annotated[
        str | None,
        typer.Option(
            "--source-lang",
            help="Force a source language (skips auto picker).",
        ),
    ] = None,
    glossary: Annotated[
        Path | None,
        typer.Option(
            "--glossary",
            help="Path to a `term:translation` glossary file.",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            help="Override base directory for draft output.",
            file_okay=False,
        ),
    ] = None,
) -> None:
    """Translate one article and write a review-ready draft to disk."""
    cmd = TranslateArticleCommand(
        title=title,
        source_lang_override=source_lang,
        glossary_path=str(glossary) if glossary is not None else None,
    )
    try:
        use_case = bootstrap.build_translate_use_case(output_dir=output_dir)
        draft = asyncio.run(use_case.execute(cmd))
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    _print_draft(draft)


@translate_queue_app.command()
def translate_queue(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            help="Path to queue TOML. Defaults to ~/.config/wiki-translator/queue.toml.",
        ),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            help="Override base directory for draft output.",
            file_okay=False,
        ),
    ] = None,
) -> None:
    """Run translations for every entry in a TOML queue."""
    queue_path = config if config is not None else _DEFAULT_QUEUE_PATH
    if not queue_path.is_file():
        typer.echo(f"queue file not found: {queue_path}", err=True)
        raise typer.Exit(code=2)
    text = queue_path.read_text(encoding="utf-8")
    try:
        commands = parse_queue_toml(text)
    except (ValueError, KeyError, TypeError) as exc:
        typer.echo(f"queue parse error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if not commands:
        typer.echo("(queue is empty)")
        return
    try:
        use_case = bootstrap.build_translate_use_case(output_dir=output_dir)
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    for cmd in commands:
        try:
            draft = asyncio.run(use_case.execute(cmd))
        except Exception as exc:
            typer.echo(f"error processing {cmd.title!r}: {exc}", err=True)
            continue
        _print_draft(draft)


@list_drafts_app.command()
def list_drafts(
    since: Annotated[
        str | None,
        typer.Option(
            "--since",
            help="Only show drafts on or after YYYY-MM-DD.",
        ),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            help="Override base directory to scan for drafts.",
            file_okay=False,
        ),
    ] = None,
) -> None:
    """List recent drafts on disk · newest first."""
    cutoff: datetime.datetime | None
    if since is None:
        cutoff = None
    else:
        try:
            d = datetime.date.fromisoformat(since)
        except ValueError as exc:
            typer.echo(f"invalid --since {since!r} · expected YYYY-MM-DD")
            raise typer.Exit(code=2) from exc
        cutoff = datetime.datetime(d.year, d.month, d.day)
    try:
        use_case = bootstrap.build_list_drafts_use_case(output_dir=output_dir)
        drafts = asyncio.run(use_case.execute(since=cutoff))
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if not drafts:
        typer.echo("(no drafts)")
        return
    for draft in drafts:
        typer.echo(f"{draft.when.isoformat()}  {draft.slug}  {draft.dir}")

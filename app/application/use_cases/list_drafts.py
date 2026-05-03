"""ListDraftsUseCase · thin wrapper over DraftStorage.list_drafts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.application.dto import DraftMetadata
from app.application.ports import DraftStorage


@dataclass(frozen=True)
class ListDraftsUseCase:
    storage: DraftStorage

    async def execute(self, since: datetime | None = None) -> list[DraftMetadata]:
        return await self.storage.list_drafts(since=since)

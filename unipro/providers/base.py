from __future__ import annotations

from abc import ABC, abstractmethod

from unipro.models import ProviderResult, SearchRequest, TravelMode


class TravelProvider(ABC):
    provider_id: str
    display_name: str
    supported_modes: frozenset[TravelMode]

    @abstractmethod
    async def search(self, request: SearchRequest) -> ProviderResult:
        raise NotImplementedError

    def supports(self, request: SearchRequest) -> bool:
        return bool(set(request.modes) & set(self.supported_modes))

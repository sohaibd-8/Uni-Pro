from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote, urlencode

from unipro.models import AvailabilityState, Journey, ProviderResult, SearchRequest, TravelMode
from unipro.providers.base import TravelProvider
from unipro.providers.web_common import PublicWebApiMixin, normalize_text, number, parse_datetime


FLYTODAY_BUS_LOCATION_URL = "https://placesearch.flytoday.ir/api/Bus/Search"
FLYTODAY_BUS_SEARCH_URL = "https://www.flytodayir.com/api/gateway/V1/Bus/Search"


class FlyTodayProvider(PublicWebApiMixin, TravelProvider):
    provider_id = "flytoday"
    display_name = "فلای‌تودی"
    supported_modes = frozenset({TravelMode.BUS})

    async def search(self, request: SearchRequest) -> ProviderResult:
        if TravelMode.BUS not in request.modes:
            return ProviderResult(self.provider_id, AvailabilityState.UNAVAILABLE, [])
        try:
            journeys = await self._search_bus(request)
        except Exception as exc:
            return ProviderResult(self.provider_id, AvailabilityState.ERROR, [], str(exc))
        return ProviderResult(
            self.provider_id,
            AvailabilityState.AVAILABLE if journeys else AvailabilityState.UNAVAILABLE,
            journeys,
        )

    @staticmethod
    def _base_headers(path: str) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://www.flytodayir.com",
            "Referer": "https://www.flytodayir.com/",
            "X-App": "www.flytodayir.com",
            "x-currency": "IRR",
            "x-origin": "https://www.flytodayir.com",
            "X-Path": path,
        }

    async def _search_bus(self, request: SearchRequest) -> list[Journey]:
        origin, destination = await asyncio.gather(
            self._resolve_location(request.origin),
            self._resolve_location(request.destination),
        )
        if origin[0] == destination[0]:
            return []

        result_url = self._result_url(request, origin, destination)
        response = await self._request_json(
            FLYTODAY_BUS_SEARCH_URL,
            method="POST",
            payload={
                "originDestinations": [
                    {
                        "originId": origin[0],
                        "destinationId": destination[0],
                        "departureDate": request.travel_date.isoformat(),
                    }
                ]
            },
            headers=self._base_headers(result_url),
        )
        if not isinstance(response, dict):
            raise RuntimeError("FlyToday bus response shape changed")
        raw_legs = response.get("originDestinationItineraries")
        search_id = str(response.get("searchId") or "").strip()
        if not isinstance(raw_legs, list) or not search_id:
            raise RuntimeError("FlyToday bus response is missing itinerary/search id")

        rows: list[dict[str, Any]] = []
        for leg in raw_legs:
            if not isinstance(leg, dict):
                continue
            leg_origin = leg.get("origin")
            leg_destination = leg.get("destination")
            departure = parse_datetime(leg.get("departureDate"))
            if (
                not isinstance(leg_origin, dict)
                or not isinstance(leg_destination, dict)
                or str(leg_origin.get("cityId") or "") != origin[0]
                or str(leg_destination.get("cityId") or "") != destination[0]
                or departure is None
                or departure.date() != request.travel_date
            ):
                continue
            itineraries = leg.get("itineraries")
            if isinstance(itineraries, list):
                rows.extend(row for row in itineraries if isinstance(row, dict))

        journeys: list[Journey] = []
        for row in rows:
            departure = parse_datetime(row.get("departureDate"))
            price_rials = number(row.get("price"))
            remaining = number(row.get("remainingSeat"))
            row_origin = row.get("origin")
            row_destination = row.get("destination")
            if not isinstance(row_origin, dict) or not isinstance(row_destination, dict):
                continue
            company = " ".join(
                str(
                    row.get("busGroupCompanyNameFa")
                    or row.get("busCompanyNameFa")
                    or row.get("name")
                    or ""
                ).split()
            )
            bus_class = " ".join(str(row.get("busType") or "").split())
            origin_terminal = " ".join(
                str(row_origin.get("terminalNameFa") or row_origin.get("nameFa") or "").split()
            )
            destination_terminal = " ".join(
                str(row_destination.get("terminalNameFa") or row_destination.get("nameFa") or "").split()
            )
            source = str(row.get("fareSourceCode") or "").strip()
            if (
                not source
                or departure is None
                or departure.date() != request.travel_date
                or price_rials is None
                or price_rials <= 0
                or remaining is None
                or remaining < request.passengers
                or str(row_origin.get("cityId") or "") != origin[0]
                or str(row_destination.get("cityId") or "") != destination[0]
                or not company
                or not bus_class
                or not origin_terminal
                or not destination_terminal
                or row.get("isFull") is True
            ):
                continue

            service_id = "|".join(
                [
                    normalize_text(company),
                    normalize_text(origin_terminal),
                    normalize_text(destination_terminal),
                    departure.strftime("%H:%M"),
                ]
            )
            journeys.append(
                Journey(
                    provider_id=self.provider_id,
                    seller_name=self.display_name,
                    mode=TravelMode.BUS,
                    origin=origin[2],
                    destination=destination[2],
                    departure_at=departure,
                    arrival_at=None,
                    price_irr=round(price_rials * request.passengers),
                    booking_url=result_url,
                    service_id=service_id,
                    seats=max(0, round(remaining)),
                    raw={
                        "proposal_id": f"{search_id}:{source}",
                        "operator": company,
                        "vehicle_class": bus_class,
                        "origin_terminal": origin_terminal,
                        "destination_terminal": destination_terminal,
                    },
                )
            )
        return journeys

    async def _resolve_location(self, value: str) -> tuple[str, str, str]:
        response = await self._request_json(
            FLYTODAY_BUS_LOCATION_URL,
            method="POST",
            payload={
                "searchTerm": value,
                "pageSize": 100,
                "pageNumber": 0,
            },
            headers=self._base_headers("https://www.flytodayir.com/bus"),
        )
        rows = response.get("locations") if isinstance(response, dict) else None
        if not isinstance(rows, list):
            raise RuntimeError("FlyToday bus location response shape changed")

        needle = normalize_text(value)
        matches: dict[str, tuple[str, str, str]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            city_id = str(row.get("cityId") or row.get("id") or "").strip()
            slug = " ".join(str(row.get("cityName") or row.get("name") or "").split())
            name = " ".join(str(row.get("cityNameFa") or row.get("nameFa") or "").split())
            if not city_id or not slug or not name:
                continue
            candidates = {
                normalize_text(city_id),
                normalize_text(slug),
                normalize_text(name),
                normalize_text(row.get("id")),
                normalize_text(row.get("name")),
                normalize_text(row.get("nameFa")),
            }
            if needle in candidates:
                matches[city_id] = (city_id, slug, name)
        if len(matches) != 1:
            raise RuntimeError("FlyToday bus city could not be resolved uniquely")
        return next(iter(matches.values()))

    @staticmethod
    def _result_url(
        request: SearchRequest,
        origin: tuple[str, str, str],
        destination: tuple[str, str, str],
    ) -> str:
        route = (
            f"{quote(origin[1].lower(), safe='-')}-"
            f"{quote(destination[1].lower(), safe='-')}"
        )
        query = urlencode(
            {
                "origin": origin[0],
                "destination": destination[0],
                "departureDate": request.travel_date.isoformat(),
            }
        )
        return f"https://www.flytodayir.com/bus/{route}?{query}"

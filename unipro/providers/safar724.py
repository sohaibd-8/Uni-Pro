from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

from unipro.models import AvailabilityState, Journey, ProviderResult, SearchRequest, TravelMode
from unipro.providers.base import TravelProvider
from unipro.providers.web_common import (
    PublicWebApiMixin,
    departure_from_clock,
    jalali_dash,
    normalize_text,
    number,
)


SAFAR724_CITIES_URL = "https://safar724.com/route/getcities"
SAFAR724_SEARCH_URL = "https://service.safar724.com/cs/api/bus/route"


class Safar724Provider(PublicWebApiMixin, TravelProvider):
    provider_id = "safar724"
    display_name = "سفر ۷۲۴"
    supported_modes = frozenset({TravelMode.BUS})

    async def search(self, request: SearchRequest) -> ProviderResult:
        if TravelMode.BUS not in request.modes:
            return ProviderResult(self.provider_id, AvailabilityState.UNAVAILABLE, [])
        try:
            journeys = await self._search_bus(request)
        except Exception as exc:
            return ProviderResult(
                self.provider_id,
                AvailabilityState.ERROR,
                [],
                str(exc),
            )
        return ProviderResult(
            self.provider_id,
            AvailabilityState.AVAILABLE if journeys else AvailabilityState.UNAVAILABLE,
            journeys,
        )

    async def _search_bus(self, request: SearchRequest) -> list[Journey]:
        cities = await self._city_rows()
        origin = self._resolve_city(request.origin, cities)
        destination = self._resolve_city(request.destination, cities)
        if origin[0] == destination[0]:
            return []

        jalali_date = jalali_dash(request.travel_date)
        response = await self._request_json(
            SAFAR724_SEARCH_URL,
            params={
                "Date": jalali_date,
                "Destination": destination[0],
                "Origin": origin[0],
            },
            headers={"Referer": "https://safar724.com/"},
        )
        if not isinstance(response, dict):
            raise RuntimeError("Safar724 bus response shape changed")
        if str(response.get("originCode") or "") != origin[0]:
            raise RuntimeError("Safar724 origin mismatch")
        if str(response.get("destinationCode") or "") != destination[0]:
            raise RuntimeError("Safar724 destination mismatch")
        rows = response.get("items")
        if not isinstance(rows, list):
            raise RuntimeError("Safar724 response does not contain items")

        journeys: list[Journey] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            departure = departure_from_clock(request.travel_date, row.get("departureTime"))
            price = number(row.get("price"))
            seats = number(row.get("availableSeatCount"))
            company = " ".join(
                str(row.get("companyPersianName") or row.get("companyName") or "").split()
            )
            bus_class = " ".join(str(row.get("busType") or "").split())
            origin_terminal = " ".join(
                str(row.get("originTerminalPersianName") or "").split()
            )
            destination_terminal = " ".join(
                str(row.get("destinationTerminalPersianName") or "").split()
            )
            if (
                departure is None
                or price is None
                or price <= 0
                or seats is None
                or seats < request.passengers
                or not company
                or normalize_text(row.get("vehicleType")) != "bus"
                or normalize_text(row.get("status")) != "available"
            ):
                continue

            route = (
                f"{quote(origin[1].lower(), safe='-')}-"
                f"{quote(destination[1].lower(), safe='-')}"
            )
            booking_url = (
                f"https://safar724.com/bus/{route}?"
                f"{urlencode({'date': jalali_date})}"
            )
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
                    price_irr=round(price * request.passengers),
                    booking_url=booking_url,
                    service_id=service_id,
                    seats=max(0, round(seats)),
                    raw={
                        "proposal_id": str(row.get("id") or ""),
                        "operator": company,
                        "vehicle_class": bus_class,
                        "origin_terminal": origin_terminal,
                        "destination_terminal": destination_terminal,
                    },
                )
            )
        return journeys

    async def _city_rows(self) -> list[dict[str, Any]]:
        response = await self._request_json(
            SAFAR724_CITIES_URL,
            headers={
                "Referer": "https://safar724.com/",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        if not isinstance(response, list):
            raise RuntimeError("Safar724 city response shape changed")
        rows = [row for row in response if isinstance(row, dict)]
        if not rows:
            raise RuntimeError("Safar724 returned no cities")
        return rows

    @staticmethod
    def _resolve_city(value: str, rows: list[dict[str, Any]]) -> tuple[str, str, str]:
        needle = normalize_text(value)
        matches: dict[str, tuple[str, str, str]] = {}
        for row in rows:
            code = str(row.get("Code") or "").strip()
            english = " ".join(str(row.get("Name") or "").split())
            persian = " ".join(str(row.get("PersianName") or "").split())
            if not code or not english or not persian:
                continue
            candidates = {
                normalize_text(code),
                normalize_text(english),
                normalize_text(persian),
            }
            aliases = row.get("SearchExpressions")
            if isinstance(aliases, list):
                candidates.update(normalize_text(alias) for alias in aliases)
            if needle in candidates:
                matches[code] = (code, english, persian)
        if len(matches) != 1:
            raise RuntimeError("Safar724 city could not be resolved uniquely")
        return next(iter(matches.values()))

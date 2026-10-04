from __future__ import annotations

import asyncio
import re
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

from unipro.models import AvailabilityState, Journey, ProviderResult, SearchRequest, TravelMode
from unipro.providers.base import TravelProvider
from unipro.providers.iran_locations import resolve_rail_station
from unipro.providers.web_common import (
    PublicWebApiMixin,
    normalize_text,
    number,
    parse_datetime,
    jalali_dash,
)


ALIBABA_TRAIN_URL = "https://ws.alibaba.ir/api/v2/train/available"
ALIBABA_BUS_URL = "https://ws.alibaba.ir/api/v2/bus/available"
ALIBABA_BUS_STATIONS_URL = "https://ws.alibaba.ir/api/v1/bus/stations"


# Warm fallback only; live station lookup remains authoritative for bus.
_ALIBABA_BUS_FALLBACK = {
    "تهران": ("11320000", "THR", "تهران"),
    "مشهد": ("31310000", "MHD", "مشهد"),
    "اصفهان": ("21310000", "IFN", "اصفهان"),
    "رشت": ("54310000", "RHD", "رشت"),
    "تبریز": ("26310000", "TBZ", "تبریز"),
    "یزد": ("93310000", "AZD", "یزد"),
    "شیراز": ("41310000", "SYZ", "شیراز"),
    "اهواز": ("36310000", "AWZ", "اهواز"),
    "کرمان": ("45310000", "KER", "کرمان"),
}


class AlibabaProvider(PublicWebApiMixin, TravelProvider):
    provider_id = "alibaba"
    display_name = "علی‌بابا"
    supported_modes = frozenset({TravelMode.TRAIN, TravelMode.BUS})

    async def search(self, request: SearchRequest) -> ProviderResult:
        tasks = []
        if TravelMode.TRAIN in request.modes:
            tasks.append(self._search_train(request))
        if TravelMode.BUS in request.modes:
            tasks.append(self._search_bus(request))
        if not tasks:
            return ProviderResult(self.provider_id, AvailabilityState.UNAVAILABLE, [])

        results = await asyncio.gather(*tasks, return_exceptions=True)
        journeys: list[Journey] = []
        errors: list[str] = []
        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
            else:
                journeys.extend(result)

        if journeys:
            return ProviderResult(
                self.provider_id,
                AvailabilityState.AVAILABLE,
                journeys,
                "; ".join(errors) if errors else None,
            )
        if errors and len(errors) == len(results):
            return ProviderResult(
                self.provider_id,
                AvailabilityState.ERROR,
                [],
                "; ".join(errors),
            )
        return ProviderResult(
            self.provider_id,
            AvailabilityState.UNAVAILABLE,
            [],
            "; ".join(errors) if errors else None,
        )

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "Origin": "https://www.alibaba.ir",
            "Referer": "https://www.alibaba.ir/",
        }

    async def _search_train(self, request: SearchRequest) -> list[Journey]:
        origin = resolve_rail_station(request.origin)
        destination = resolve_rail_station(request.destination)
        if origin is None or destination is None:
            raise RuntimeError("Alibaba train station is not in the verified station catalogue")
        if origin.code == destination.code:
            return []

        created = await self._request_json(
            ALIBABA_TRAIN_URL,
            method="POST",
            payload={
                "origin": origin.code,
                "destination": destination.code,
                "departureDate": request.travel_date.isoformat(),
                "returnDate": None,
                "passengerCount": request.passengers,
                "isExclusiveCompartment": False,
                "ticketType": "Family",
            },
            headers=self._headers(),
        )
        if not isinstance(created, dict) or created.get("success") is not True:
            raise RuntimeError("Alibaba train search creation failed")
        result = created.get("result")
        request_id = result.get("requestId") if isinstance(result, dict) else None
        if not request_id:
            raise RuntimeError("Alibaba train search did not return requestId")

        rows: list[dict[str, Any]] | None = None
        completed = False
        for attempt in range(5):
            response = await self._request_json(
                f"{ALIBABA_TRAIN_URL}/{request_id}",
                headers=self._headers(),
            )
            if isinstance(response, dict) and response.get("success") is True:
                data = response.get("result")
                if isinstance(data, dict):
                    candidate = data.get("departing")
                    completed = data.get("isCompleted") is True
                    if isinstance(candidate, list) and (candidate or completed):
                        rows = [row for row in candidate if isinstance(row, dict)]
                        break
            if attempt < 4:
                await asyncio.sleep(0.2)
        if rows is None:
            if completed:
                return []
            raise RuntimeError("Alibaba train search did not complete")

        journeys: list[Journey] = []
        for row in rows:
            departure = parse_datetime(row.get("departureDateTime"))
            arrival = parse_datetime(row.get("arrivalDateTime"))
            price_rials = number(row.get("cost"))
            train_number = str(row.get("trainNumber") or "").strip()
            company = str(row.get("companyName") or "").strip()
            wagon = str(row.get("wagonName") or "").strip()
            proposal = row.get("proposalId")
            if (
                departure is None
                or arrival is None
                or arrival <= departure
                or price_rials is None
                or price_rials < 0
                or not train_number
                or not company
                or proposal is None
            ):
                continue
            if departure.date() != request.travel_date:
                continue
            provider_origin = str(row.get("originCode") or row.get("orginCode") or "").upper()
            provider_destination = str(row.get("destinationCode") or "").upper()
            if provider_origin != origin.code.upper() or provider_destination != destination.code.upper():
                continue
            seats_value = number(row.get("seat"))
            if seats_value is not None and seats_value < request.passengers:
                continue

            query = urlencode(
                {
                    "adult": request.passengers,
                    "child": 0,
                    "infant": 0,
                    "departing": jalali_dash(request.travel_date),
                    "ticketType": "Family",
                    "isExclusive": "false",
                }
            )
            booking_url = f"https://www.alibaba.ir/train/{origin.code}-{destination.code}?{query}"
            journeys.append(
                Journey(
                    provider_id=self.provider_id,
                    seller_name=self.display_name,
                    mode=TravelMode.TRAIN,
                    origin=origin.name,
                    destination=destination.name,
                    departure_at=departure,
                    arrival_at=arrival,
                    price_irr=round(price_rials) * request.passengers,
                    booking_url=booking_url,
                    service_id=train_number,
                    seats=(round(seats_value) if seats_value is not None else None),
                    raw={
                        "proposal_id": str(proposal),
                        "operator": company,
                        "vehicle_class": wagon,
                    },
                )
            )
        return journeys

    async def _search_bus(self, request: SearchRequest) -> list[Journey]:
        origin, destination = await asyncio.gather(
            self._resolve_bus_station(request.origin),
            self._resolve_bus_station(request.destination),
        )
        if origin[0] == destination[0]:
            return []

        response = await self._request_json(
            ALIBABA_BUS_URL,
            params={
                # Alibaba's public web contract currently spells this key this way.
                "orginCityCode": origin[0],
                "destinationCityCode": destination[0],
                "requestDate": request.travel_date.isoformat(),
                "passengerCount": request.passengers,
                "serviceType": "Bus",
            },
            headers=self._headers(),
        )
        if not isinstance(response, dict) or response.get("success") is not True:
            raise RuntimeError("Alibaba bus search failed")
        result = response.get("result")
        rows = result.get("availableList") if isinstance(result, dict) else None
        if not isinstance(rows, list):
            raise RuntimeError("Alibaba bus response shape changed")

        journeys: list[Journey] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            departure = parse_datetime(row.get("departureDateTime"))
            price_rials = number(row.get("price"))
            available = number(row.get("availableSeats"))
            company = " ".join(str(row.get("companyName") or "").split())
            bus_type = " ".join(str(row.get("busType") or "").split()).split("-", 1)[0].strip()
            origin_terminal = " ".join(str(row.get("orginTerminal") or "").split())
            destination_terminal = " ".join(str(row.get("destinationTerminal") or "").split())
            if (
                departure is None
                or departure.date() != request.travel_date
                or price_rials is None
                or price_rials < 0
                or not company
            ):
                continue
            if available is not None and available < request.passengers:
                continue
            if str(row.get("originCityCode") or row.get("orginCityCode") or "") != origin[0]:
                continue
            if str(row.get("destinationCityCode") or "") != destination[0]:
                continue
            if row.get("type") and normalize_text(row.get("type")) != "bus":
                continue

            query = urlencode({"departing": jalali_dash(request.travel_date)})
            booking_url = f"https://www.alibaba.ir/bus/{origin[1]}-{destination[1]}?{query}"
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
                    price_irr=round(price_rials) * request.passengers,
                    booking_url=booking_url,
                    service_id=service_id,
                    seats=(max(0, round(available)) if available is not None else None),
                    raw={
                        "proposal_id": str(row.get("proposalId") or ""),
                        "operator": company,
                        "vehicle_class": bus_type,
                        "origin_terminal": origin_terminal,
                        "destination_terminal": destination_terminal,
                    },
                )
            )
        return journeys

    async def _resolve_bus_station(self, value: str) -> tuple[str, str, str]:
        needle = normalize_text(value)
        for key, station in _ALIBABA_BUS_FALLBACK.items():
            if needle in {normalize_text(key), normalize_text(station[1]), normalize_text(station[0])}:
                return station

        safe = re.sub(r"['{}\\]", "", " ".join(value.split()))
        response = await self._request_json(
            ALIBABA_BUS_STATIONS_URL,
            params={"filter": f"q={{ct:'{safe}'}}"},
            headers=self._headers(),
        )
        if not isinstance(response, dict) or response.get("success") is not True:
            raise RuntimeError("Alibaba bus station lookup failed")
        result = response.get("result")
        rows = result.get("items") if isinstance(result, dict) else None
        if not isinstance(rows, list):
            raise RuntimeError("Alibaba bus station response shape changed")

        candidates: list[tuple[str, str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            country = row.get("country")
            if isinstance(country, dict) and country.get("domainCode") != "IRN":
                continue
            domain_code = str(row.get("domainCode") or "").strip()
            name = " ".join(str(row.get("name") or "").split())
            route_code = ""
            display_names = row.get("displayNames")
            if isinstance(display_names, list):
                for item in display_names:
                    if not isinstance(item, dict) or item.get("language") != "en-US":
                        continue
                    candidate = str(item.get("value") or "").strip().upper()
                    if re.fullmatch(r"[A-Z0-9]{2,12}", candidate):
                        route_code = candidate
                        break
            if not domain_code or not route_code or not name:
                continue
            if needle in {normalize_text(domain_code), normalize_text(route_code), normalize_text(name)}:
                candidates.append((domain_code, route_code, name))

        if len(candidates) != 1:
            raise RuntimeError("Alibaba bus station could not be resolved uniquely")
        return candidates[0]

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from urllib.parse import quote, urlencode

from unipro.models import AvailabilityState, Journey, ProviderResult, SearchRequest, TravelMode
from unipro.providers.base import TravelProvider
from unipro.providers.web_common import PublicWebApiMixin, normalize_text, number, parse_datetime


SNAPPTRIP_TRAIN_STATIONS_URL = "https://train.snapptrip.com/statics/v1/stations"
SNAPPTRIP_TRAIN_SEARCH_URL = "https://train.snapptrip.com/listing/v2/search"
SNAPPTRIP_BUS_LOCATIONS_URL = "https://fp.snapptrip.com/bus-listing-go/v3/endpoints"
SNAPPTRIP_BUS_AVAILABILITY_URL = "https://bus.snapptrip.com/bus-listing-go/v2/availability"

_TRAIN_ALIASES = {
    "THR": "تهران",
    "MHD": "مشهد",
    "IFN": "اصفهان",
    "RHD": "رشت",
    "TBZ": "تبریز",
    "AZD": "یزد",
    "SYZ": "شیراز",
    "AWZ": "اهواز",
    "KER": "کرمان",
}

_BUS_ALIASES = dict(_TRAIN_ALIASES)


class SnappTripProvider(PublicWebApiMixin, TravelProvider):
    provider_id = "snapptrip"
    display_name = "اسنپ‌تریپ"
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
            return ProviderResult(self.provider_id, AvailabilityState.ERROR, [], "; ".join(errors))
        return ProviderResult(
            self.provider_id,
            AvailabilityState.UNAVAILABLE,
            [],
            "; ".join(errors) if errors else None,
        )

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "Origin": "https://www.snapptrip.com",
            "Referer": "https://www.snapptrip.com/",
        }

    async def _search_train(self, request: SearchRequest) -> list[Journey]:
        station_rows = await self._train_station_rows()
        origin = self._resolve_train_station(request.origin, station_rows)
        destination = self._resolve_train_station(request.destination, station_rows)
        if origin[0].casefold() == destination[0].casefold():
            return []

        response = await self._request_json(
            SNAPPTRIP_TRAIN_SEARCH_URL,
            method="POST",
            payload={
                "ticketType": "NORMAL",
                "adultCount": request.passengers,
                "childCount": 0,
                "infantCount": 0,
                "origin": origin[0],
                "destination": destination[0],
                "moveDate": request.travel_date.isoformat(),
                "isExclusive": False,
            },
            headers=self._headers(),
        )
        envelope = response.get("solutions") if isinstance(response, dict) else None
        rows = envelope.get("solutions") if isinstance(envelope, dict) else None
        if number(envelope.get("responseCode")) != 200 if isinstance(envelope, dict) else True:
            raise RuntimeError("SnappTrip train response code is invalid")
        if not isinstance(rows, list):
            raise RuntimeError("SnappTrip train response shape changed")

        journeys: list[Journey] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            departure = parse_datetime(row.get("departureDateTime"))
            duration = number(row.get("duration"))
            seats = number(row.get("seatsRemaining"))
            pricing = row.get("pricing")
            price_rials = number(pricing.get("totalPayablePrice")) if isinstance(pricing, dict) else None
            provider_origin = str(row.get("origin") or "").strip()
            provider_destination = str(row.get("destination") or "").strip()
            origin_name = self._fa(row.get("originName"))
            destination_name = self._fa(row.get("destinationName"))
            company = self._fa(row.get("trainCompany"))
            train_number = str(row.get("trainNumber") or "").strip()
            wagon = self._fa(row.get("wagonName"))
            capacity_status = str(row.get("capacityStatus") or "").strip().upper()
            ticket_type = str(row.get("ticketType") or "").strip().upper()
            exclusive = row.get("exclusible")
            if (
                departure is None
                or duration is None
                or not float(duration).is_integer()
                or duration <= 0
                or duration > 10080
                or seats is None
                or seats < request.passengers
                or price_rials is None
                or price_rials < 0
                or not company
                or not train_number
                or not wagon
                or ticket_type != "NORMAL"
                or capacity_status != "AVAILABLE"
                or exclusive is not False
            ):
                continue
            if (
                departure.date() != request.travel_date
                or provider_origin.casefold() != origin[2].casefold()
                or provider_destination.casefold() != destination[2].casefold()
                or normalize_text(origin_name) != normalize_text(origin[1])
                or normalize_text(destination_name) != normalize_text(destination[1])
            ):
                continue

            arrival = departure + timedelta(minutes=round(duration))
            query = urlencode(
                {
                    "adultCount": request.passengers,
                    "childCount": 0,
                    "infantCount": 0,
                    "departureDate": request.travel_date.isoformat(),
                    "isExclusive": "false",
                    "ticketType": "NORMAL",
                    "source": "searchBox",
                    "saleType": "one-way",
                }
            )
            booking_url = (
                "https://www.snapptrip.com/train-ticket/"
                f"{quote(origin[0], safe='')}/{quote(destination[0], safe='')}?{query}"
            )
            journeys.append(
                Journey(
                    provider_id=self.provider_id,
                    seller_name=self.display_name,
                    mode=TravelMode.TRAIN,
                    origin=origin[1],
                    destination=destination[1],
                    departure_at=departure,
                    arrival_at=arrival,
                    price_irr=round(price_rials),
                    booking_url=booking_url,
                    service_id=train_number,
                    seats=max(0, round(seats)),
                    raw={
                        "proposal_id": str(row.get("id") or ""),
                        "operator": company,
                        "vehicle_class": wagon,
                    },
                )
            )
        return journeys

    async def _train_station_rows(self) -> list[dict[str, Any]]:
        response = await self._request_json(
            SNAPPTRIP_TRAIN_STATIONS_URL,
            headers=self._headers(),
        )
        if not isinstance(response, list):
            raise RuntimeError("SnappTrip train station response shape changed")
        rows = [
            row for row in response
            if isinstance(row, dict)
            and row.get("isActive") is True
            and self._station_endpoint(row)
            and self._station_name(row)
            and self._station_code(row)
        ]
        if not rows:
            raise RuntimeError("SnappTrip returned no active train stations")
        return rows

    def _resolve_train_station(
        self,
        value: str,
        rows: list[dict[str, Any]],
    ) -> tuple[str, str, str]:
        lookup = _TRAIN_ALIASES.get(value.strip().upper(), value.strip())
        needle = normalize_text(lookup)
        matches: dict[str, tuple[str, str, str]] = {}
        for row in rows:
            endpoint = self._station_endpoint(row)
            name = self._station_name(row)
            code = self._station_code(row)
            if not endpoint or not name or not code:
                continue
            if needle in {
                normalize_text(endpoint),
                normalize_text(name),
                normalize_text(code),
            }:
                matches[endpoint.casefold()] = (endpoint, name, code)
        if len(matches) != 1:
            raise RuntimeError("SnappTrip train station could not be resolved uniquely")
        return next(iter(matches.values()))

    async def _search_bus(self, request: SearchRequest) -> list[Journey]:
        origin, destination = await asyncio.gather(
            self._resolve_bus_endpoint(request.origin),
            self._resolve_bus_endpoint(request.destination),
        )
        if origin[0].casefold() == destination[0].casefold():
            return []

        url = (
            f"{SNAPPTRIP_BUS_AVAILABILITY_URL}/"
            f"{quote(origin[0], safe='')}/to/"
            f"{quote(destination[0], safe='')}/on/"
            f"{quote(request.travel_date.isoformat(), safe='')}"
        )
        response = await self._request_json(url, headers=self._headers())
        rows = response.get("solutions") if isinstance(response, dict) else None
        if not isinstance(rows, list):
            raise RuntimeError("SnappTrip bus response shape changed")

        journeys: list[Journey] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            departure = parse_datetime(row.get("departureDatetime"))
            arrival = parse_datetime(row.get("arrivalDatetime"))
            price_rials = number(row.get("finalPrice"))
            if price_rials is None:
                price_rials = number(row.get("price"))
            limit = number(row.get("providerPerOrderLimit"))
            company_data = row.get("company")
            company = (
                " ".join(str(company_data.get("name") or "").split())
                if isinstance(company_data, dict)
                else ""
            )
            origin_terminal_data = row.get("originTerminal")
            destination_terminal_data = row.get("destinationTerminal")
            origin_terminal = (
                " ".join(str(origin_terminal_data.get("name") or "").split())
                if isinstance(origin_terminal_data, dict)
                else ""
            )
            destination_terminal = (
                " ".join(str(destination_terminal_data.get("name") or "").split())
                if isinstance(destination_terminal_data, dict)
                else ""
            )
            bus_class = " ".join(str(row.get("busDescription") or row.get("busType") or "").split())
            provider_origin = str(row.get("originCity") or "").strip()
            provider_destination = str(row.get("destinationCity") or "").strip()
            if (
                departure is None
                or departure.date() != request.travel_date
                or (arrival is not None and arrival <= departure)
                or price_rials is None
                or price_rials < 0
                or not company
                or not origin_terminal
                or not destination_terminal
                or not bus_class
                or row.get("multiStop") is True
            ):
                continue
            if normalize_text(provider_origin) not in {normalize_text(origin[0]), normalize_text(origin[1])}:
                continue
            if normalize_text(provider_destination) not in {normalize_text(destination[0]), normalize_text(destination[1])}:
                continue
            provider_date = str(row.get("departureDate") or "").strip()
            if provider_date and provider_date != request.travel_date.isoformat():
                continue
            if limit is not None and limit < request.passengers:
                continue
            capacity = number(row.get("capacity"))
            if capacity is not None and capacity < request.passengers:
                continue

            query = urlencode(
                {
                    "source": "searchBox",
                    "departureDate": request.travel_date.isoformat(),
                }
            )
            booking_url = (
                f"https://www.snapptrip.com/bus/"
                f"{quote(origin[0], safe='')}/{quote(destination[0], safe='')}?{query}"
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
                    origin=provider_origin or origin[1],
                    destination=provider_destination or destination[1],
                    departure_at=departure,
                    arrival_at=arrival,
                    price_irr=round(price_rials * request.passengers),
                    booking_url=booking_url,
                    service_id=service_id,
                    seats=(max(0, round(capacity)) if capacity is not None else None),
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

    async def _resolve_bus_endpoint(self, value: str) -> tuple[str, str]:
        lookup = _BUS_ALIASES.get(value.strip().upper(), value.strip())
        response = await self._request_json(
            SNAPPTRIP_BUS_LOCATIONS_URL,
            params={"query": lookup},
            headers=self._headers(),
        )
        rows = response.get("endpoints") if isinstance(response, dict) else None
        if not isinstance(rows, list):
            raise RuntimeError("SnappTrip bus endpoint response shape changed")
        needle = normalize_text(lookup)
        matches: dict[str, tuple[str, str]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get("code") or "").strip()
            name = " ".join(str(row.get("city") or row.get("name") or "").split())
            city_en = " ".join(str(row.get("cityEn") or "").split())
            if code and name and needle in {
                normalize_text(code),
                normalize_text(name),
                normalize_text(city_en),
            }:
                matches[code.casefold()] = (code, name)
        if len(matches) != 1:
            raise RuntimeError("SnappTrip bus city could not be resolved uniquely")
        return next(iter(matches.values()))

    @staticmethod
    def _fa(value: Any) -> str:
        return " ".join(str(value or "").split()).replace("ي", "ی").replace("ك", "ک")

    @staticmethod
    def _station_endpoint(row: dict[str, Any]) -> str | None:
        endpoint = str(row.get("nameEn") or "").strip()
        return endpoint if endpoint and endpoint.isascii() else None

    @staticmethod
    def _station_code(row: dict[str, Any]) -> str | None:
        raw = row.get("code")
        if isinstance(raw, bool):
            return None
        code = str(raw or "").strip()
        return code if code and code.isdigit() else None

    @classmethod
    def _station_name(cls, row: dict[str, Any]) -> str:
        return cls._fa(row.get("nameFa"))

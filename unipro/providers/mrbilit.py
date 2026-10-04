from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlencode

from unipro.models import AvailabilityState, Journey, ProviderResult, SearchRequest, TravelMode
from unipro.providers.base import TravelProvider
from unipro.providers.iran_locations import resolve_rail_station
from unipro.providers.web_common import PublicWebApiMixin, normalize_text, number, parse_datetime


MRBILIT_TRAIN_URL = "https://train.mrbilit.com/api/GetAvailable/v2"
MRBILIT_BUS_CITIES_URL = "https://bus.mrbilit.ir/api/CityList/GetBusCityList"
MRBILIT_BUS_SEARCH_URL = "https://bus.mrbilit.ir/api/GetBusServices"


class MrBilitProvider(PublicWebApiMixin, TravelProvider):
    provider_id = "mrbilit"
    display_name = "مستربلیط"
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
            "Origin": "https://mrbilit.com",
            "Referer": "https://mrbilit.com/",
        }

    async def _search_train(self, request: SearchRequest) -> list[Journey]:
        origin = resolve_rail_station(request.origin)
        destination = resolve_rail_station(request.destination)
        if origin is None or destination is None:
            raise RuntimeError("MrBilit train station is not in the verified station catalogue")
        if origin.station_id == destination.station_id:
            return []

        response = await self._request_json(
            MRBILIT_TRAIN_URL,
            params={
                "from": origin.station_id,
                "to": destination.station_id,
                "date": f"{request.travel_date.isoformat()}T00:00:00.000Z",
                "genderCode": 3,
                "adultCount": request.passengers,
                "childCount": 0,
                "infantCount": 0,
                "disableCache": "false",
                "exclusive": "false",
                "availableStatus": "Both",
            },
            headers=self._headers(),
        )
        if not isinstance(response, dict):
            raise RuntimeError("MrBilit train response shape changed")
        rows = response.get("trains")
        if not isinstance(rows, list):
            raise RuntimeError("MrBilit train response does not contain trains")

        journeys: list[Journey] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            departure = parse_datetime(row.get("departureTime"))
            arrival = parse_datetime(row.get("arrivalTime"))
            train_number = str(row.get("trainNumber") or "").strip()
            company = " ".join(
                str(row.get("corporationName") or row.get("providerName") or "").split()
            )
            if (
                departure is None
                or arrival is None
                or arrival <= departure
                or departure.date() != request.travel_date
                or number(row.get("from")) != origin.station_id
                or number(row.get("to")) != destination.station_id
                or not train_number
                or not company
            ):
                continue

            prices = row.get("prices")
            if not isinstance(prices, list):
                continue
            for price_group in prices:
                if not isinstance(price_group, dict) or number(price_group.get("sellType")) != 3:
                    continue
                classes = price_group.get("classes")
                if not isinstance(classes, list):
                    continue
                for price_class in classes:
                    if not isinstance(price_class, dict):
                        continue
                    price = number(price_class.get("price"))
                    discount = number(price_class.get("discount")) or 0
                    capacity = number(price_class.get("capacity"))
                    min_people = number(price_class.get("minPersons")) or 1
                    wagon = " ".join(str(price_class.get("wagonName") or "").split())
                    if (
                        price is None
                        or price <= 0
                        or discount < 0
                        or discount > price
                        or capacity is None
                        or capacity < request.passengers
                        or min_people > request.passengers
                        or price_class.get("isAvailable") is not True
                        or price_class.get("reservationAvailable") is not True
                        or not wagon
                    ):
                        continue

                    operator = " ".join(str(price_class.get("ownerName") or company).split())
                    query = urlencode(
                        {
                            "departureDate": request.travel_date.isoformat(),
                            "adultCount": request.passengers,
                            "childCount": 0,
                            "infantCount": 0,
                        }
                    )
                    booking_url = (
                        f"https://mrbilit.com/trains/{origin.slug}-{destination.slug}?{query}"
                    )
                    journeys.append(
                        Journey(
                            provider_id=self.provider_id,
                            seller_name=self.display_name,
                            mode=TravelMode.TRAIN,
                            origin=origin.name,
                            destination=destination.name,
                            departure_at=departure,
                            arrival_at=arrival,
                            price_irr=round((price - discount) * request.passengers),
                            booking_url=booking_url,
                            service_id=train_number,
                            seats=max(0, round(capacity)),
                            raw={
                                "train_id": str(row.get("id") or ""),
                                "class_id": str(price_class.get("id") or ""),
                                "operator": operator,
                                "vehicle_class": wagon,
                            },
                        )
                    )
        return journeys

    async def _search_bus(self, request: SearchRequest) -> list[Journey]:
        rows = await self._bus_city_rows()
        origin = self._resolve_bus_city(request.origin, rows)
        destination = self._resolve_bus_city(request.destination, rows)
        if origin[0] == destination[0]:
            return []

        response = await self._request_json(
            MRBILIT_BUS_SEARCH_URL,
            method="POST",
            payload={
                "from": origin[0],
                "to": destination[0],
                "date": f"{request.travel_date.isoformat()}T00:00:00.000Z",
                "includeClosed": True,
                "includePromotions": True,
                "loadFromDbOnUnavailability": True,
                "includeUnderDevelopment": False,
            },
            headers={
                **self._headers(),
                "Content-Type": "application/json-patch+json",
            },
        )
        if not isinstance(response, dict):
            raise RuntimeError("MrBilit bus response shape changed")
        buses = response.get("buses")
        if not isinstance(buses, list):
            raise RuntimeError("MrBilit bus response does not contain buses")

        journeys: list[Journey] = []
        for row in buses:
            if not isinstance(row, dict):
                continue
            departure = parse_datetime(row.get("departureTime"))
            arrival = parse_datetime(row.get("arrivalTime"))
            price = number(row.get("price"))
            capacity = number(row.get("capacity"))
            company = " ".join(
                str(row.get("superCorporation") or row.get("corporation") or "").split()
            )
            bus_class = " ".join(str(row.get("shortTitle") or row.get("busType") or "").split())
            origin_terminal = " ".join(
                str(row.get("fromTerminal") or row.get("fromName") or "").split()
            )
            destination_terminal = " ".join(
                str(row.get("toTerminal") or row.get("toName") or "").split()
            )
            if (
                departure is None
                or departure.date() != request.travel_date
                or price is None
                or price <= 0
                or capacity is None
                or capacity < request.passengers
                or row.get("reservable") is not True
                or row.get("isCar") is True
                or not company
            ):
                continue
            if normalize_text(row.get("fromCity")) not in {
                normalize_text(origin[2]),
                normalize_text(f"{origin[2]} (همه پایانه‌ها)"),
            }:
                continue
            if normalize_text(row.get("toCity")) not in {
                normalize_text(destination[2]),
                normalize_text(f"{destination[2]} (همه پایانه‌ها)"),
            }:
                continue

            query = urlencode(
                {
                    "departureDate": request.travel_date.isoformat(),
                    "adultCount": request.passengers,
                }
            )
            booking_url = (
                f"https://mrbilit.com/buses/{origin[1]}-{destination[1]}?{query}"
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
                    arrival_at=arrival if arrival and arrival > departure else None,
                    price_irr=round(price * request.passengers),
                    booking_url=booking_url,
                    service_id=service_id,
                    seats=max(0, round(capacity)),
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

    async def _bus_city_rows(self) -> list[dict[str, Any]]:
        response = await self._request_json(
            MRBILIT_BUS_CITIES_URL,
            params={
                "getCities": "true",
                "groupTerminals": "true",
                "domestic": "true",
                "includePopular": "true",
            },
            headers=self._headers(),
        )
        if not isinstance(response, list):
            raise RuntimeError("MrBilit bus city response shape changed")
        rows: list[dict[str, Any]] = []
        for province in response:
            if not isinstance(province, dict):
                continue
            cities = province.get("cities")
            if isinstance(cities, list):
                rows.extend(item for item in cities if isinstance(item, dict))
        if not rows:
            raise RuntimeError("MrBilit returned no bus cities")
        return rows

    @staticmethod
    def _resolve_bus_city(value: str, rows: list[dict[str, Any]]) -> tuple[int, str, str]:
        needle = normalize_text(value)
        matches: dict[int, tuple[int, str, str]] = {}
        for row in rows:
            identifier = number(row.get("id"))
            code = str(row.get("code") or "").strip()
            raw_name = " ".join(str(row.get("title") or row.get("persianTitle") or "").split())
            english = " ".join(str(row.get("englishTitle") or "").split())
            if (
                identifier is None
                or not float(identifier).is_integer()
                or identifier <= 0
                or round(identifier) % 10000 != 0
                or not code
                or not raw_name
            ):
                continue
            name = raw_name.removesuffix(" - همه پایانه‌ها").strip()
            candidates = {
                normalize_text(round(identifier)),
                normalize_text(code),
                normalize_text(name),
                normalize_text(english),
            }
            if needle in candidates:
                matches[round(identifier)] = (round(identifier), code, name)
        if len(matches) != 1:
            raise RuntimeError("MrBilit bus city could not be resolved uniquely")
        return next(iter(matches.values()))

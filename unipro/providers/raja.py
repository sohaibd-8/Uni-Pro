from __future__ import annotations

import base64
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import jdatetime
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA1
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad

from unipro.models import AvailabilityState, Journey, ProviderResult, SearchRequest, TravelMode
from unipro.providers.base import TravelProvider
from unipro.providers.web_common import PublicWebApiMixin, number, parse_datetime, TEHRAN_TZ


RAJA_STATIONS_URL = "https://www.raja.ir/assets/File/station.json"
RAJA_TRAIN_LIST_URL = "https://hostservice.raja.ir/Api/ServiceProvider/TrainListEq"


class RajaProvider(PublicWebApiMixin, TravelProvider):
    """Raja direct train inventory adapter.

    Requires an authorized API key and Raja query-encryption password supplied
    via environment variables. It deliberately does not scrape keys from the
    Raja frontend bundle or reuse leaked/stale credentials.
    """

    provider_id = "raja"
    display_name = "رجا"
    supported_modes = frozenset({TravelMode.TRAIN})

    def __init__(self, *, api_key: str, query_password: str) -> None:
        self.api_key = api_key.strip()
        self.query_password = query_password.encode("utf-8")

    async def search(self, request: SearchRequest) -> ProviderResult:
        if TravelMode.TRAIN not in request.modes:
            return ProviderResult(self.provider_id, AvailabilityState.UNAVAILABLE, [])
        if not self.api_key or not self.query_password:
            return ProviderResult(
                self.provider_id,
                AvailabilityState.ERROR,
                [],
                "Raja credentials are not configured",
            )

        try:
            journeys = await self._search_train(request)
        except Exception as exc:
            return ProviderResult(self.provider_id, AvailabilityState.ERROR, [], str(exc))

        return ProviderResult(
            self.provider_id,
            AvailabilityState.AVAILABLE if journeys else AvailabilityState.UNAVAILABLE,
            journeys,
        )

    async def _search_train(self, request: SearchRequest) -> list[Journey]:
        stations = await self._station_rows()
        origin = self._resolve_station(request.origin, stations)
        destination = self._resolve_station(request.destination, stations)
        if origin[0] == destination[0]:
            return []

        query_plain = self._encode_query(
            from_station=origin[0],
            to_station=destination[0],
            travel_date=request.travel_date,
            passengers=request.passengers,
        )
        encrypted = self._encrypt_query(query_plain, self.query_password)

        response = await self._request_json(
            RAJA_TRAIN_LIST_URL,
            params={"q": encrypted},
            headers={
                "api-key": self.api_key,
                "Origin": "https://www.raja.ir",
                "Referer": "https://www.raja.ir/",
            },
        )
        if not isinstance(response, dict):
            raise RuntimeError("Raja train response shape changed")
        rows = response.get("GoTrains")
        if not isinstance(rows, list):
            raise RuntimeError("Raja train response does not contain GoTrains")

        journeys: list[Journey] = []
        for row in rows:
            if not isinstance(row, dict):
                continue

            departure = self._departure_datetime(row)
            arrival = self._arrival_datetime(row, departure)
            train_number = str(row.get("TrainNumber") or "").strip()
            company = " ".join(str(row.get("CompanyName") or "رجا").split())
            wagon = " ".join(str(row.get("WagonName") or "").split())
            cost = number(row.get("Cost"))
            seats = self._available_seats(row)

            if (
                departure is None
                or departure.date() != request.travel_date
                or not train_number
                or cost is None
                or cost <= 0
                or seats is None
                or seats < request.passengers
            ):
                continue

            if number(row.get("FromStation")) not in {None, float(origin[0])}:
                continue
            if number(row.get("ToStation")) not in {None, float(destination[0])}:
                continue

            booking_url = "https://www.raja.ir/"
            journeys.append(
                Journey(
                    provider_id=self.provider_id,
                    seller_name=self.display_name,
                    mode=TravelMode.TRAIN,
                    origin=origin[1],
                    destination=destination[1],
                    departure_at=departure,
                    arrival_at=arrival,
                    price_irr=round(cost * request.passengers),
                    booking_url=booking_url,
                    service_id=train_number,
                    seats=max(0, round(seats)),
                    raw={
                        "operator": company,
                        "vehicle_class": wagon,
                        "wagon_type": row.get("WagonType"),
                        "compartment_capacity": row.get("CompartmentCapicity"),
                        "path_code": row.get("PathCode"),
                        "row_id": row.get("RowId"),
                        "cost_display": row.get("CostDisplay"),
                    },
                )
            )
        return journeys

    async def _station_rows(self) -> list[dict[str, Any]]:
        response = await self._request_json(
            RAJA_STATIONS_URL,
            headers={"Referer": "https://www.raja.ir/"},
        )
        if not isinstance(response, list):
            raise RuntimeError("Raja station response shape changed")
        rows = [row for row in response if isinstance(row, dict)]
        if not rows:
            raise RuntimeError("Raja returned no stations")
        return rows

    @staticmethod
    def _resolve_station(
        value: str,
        rows: list[dict[str, Any]],
    ) -> tuple[int, str, str]:
        needle = RajaProvider._normalize(value)
        matches: dict[int, tuple[int, str, str]] = {}
        for row in rows:
            code_raw = row.get("Code")
            try:
                code = int(code_raw)
            except (TypeError, ValueError):
                continue
            fa = " ".join(str(row.get("Name") or "").split())
            en = " ".join(str(row.get("EnglishName") or "").split())
            if not fa:
                continue
            candidates = {
                RajaProvider._normalize(code),
                RajaProvider._normalize(fa),
                RajaProvider._normalize(en),
            }
            if needle in candidates:
                matches[code] = (code, fa, en)
        if len(matches) != 1:
            raise RuntimeError("Raja station could not be resolved uniquely")
        return next(iter(matches.values()))

    @staticmethod
    def _normalize(value: Any) -> str:
        return (
            " ".join(str(value or "").split())
            .replace("ي", "ی")
            .replace("ك", "ک")
            .replace("‌", "")
            .casefold()
        )

    @staticmethod
    def _encode_query(
        *,
        from_station: int,
        to_station: int,
        travel_date,
        passengers: int,
    ) -> str:
        j = jdatetime.date.fromgregorian(date=travel_date)
        jalali = f"{j.year:04d}{j.month:02d}{j.day:02d}"
        return (
            f"{from_station}-{to_station}-Family-1-{jalali}--"
            f"{passengers}-false-0-0-L1"
        )

    @staticmethod
    def _encrypt_query(value: str, password: bytes) -> str:
        salt = get_random_bytes(16)
        iv = get_random_bytes(16)
        key = PBKDF2(password, salt, dkLen=32, count=100, hmac_hash_module=SHA1)
        cipher = AES.new(key, AES.MODE_CBC, iv=iv)
        encrypted = cipher.encrypt(pad(value.encode("utf-8"), AES.block_size))
        return base64.b64encode(salt + iv + encrypted).decode("ascii")

    @staticmethod
    def _available_seats(row: dict[str, Any]) -> float | None:
        candidates = [
            number(row.get("Counting")),
            number(row.get("AvaliableSellCount")),
            number(row.get("Remain")),
        ]
        valid = [value for value in candidates if value is not None and value >= 0]
        if not valid:
            return None
        return max(valid)

    @staticmethod
    def _departure_datetime(row: dict[str, Any]) -> datetime | None:
        departure = parse_datetime(row.get("ExitDateTime") or row.get("ExitDate"))
        if departure is None:
            return None
        clock = str(row.get("ExitTime") or "").strip()
        if clock and ":" in clock:
            try:
                hour, minute = map(int, clock.split(":")[:2])
                departure = departure.astimezone(TEHRAN_TZ).replace(
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0,
                )
            except (TypeError, ValueError):
                pass
        return departure

    @staticmethod
    def _arrival_datetime(
        row: dict[str, Any],
        departure: datetime | None,
    ) -> datetime | None:
        arrival = parse_datetime(row.get("ArrivalDate"))
        if arrival is not None:
            return arrival
        if departure is None:
            return None

        clock = str(row.get("TimeOfArrival") or "").strip()
        if not clock or ":" not in clock:
            return None
        try:
            hour, minute = map(int, clock.split(":")[:2])
        except (TypeError, ValueError):
            return None

        candidate = departure.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= departure:
            from datetime import timedelta
            candidate = candidate + timedelta(days=1)
        return candidate

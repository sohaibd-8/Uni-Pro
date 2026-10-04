from datetime import date

import pytest

from unipro.models import SearchRequest, TravelMode
from unipro.providers.snapptrip import (
    SNAPPTRIP_TRAIN_SEARCH_URL,
    SNAPPTRIP_TRAIN_STATIONS_URL,
    SnappTripProvider,
)


@pytest.mark.asyncio
async def test_snapptrip_train_contract_is_normalized():
    provider = SnappTripProvider()

    async def fake_request(url, *, method="GET", params=None, payload=None, headers=None):
        if url == SNAPPTRIP_TRAIN_STATIONS_URL:
            return [
                {
                    "isActive": True,
                    "nameEn": "Tehran",
                    "nameFa": "تهران",
                    "code": "1",
                },
                {
                    "isActive": True,
                    "nameEn": "Mashhad",
                    "nameFa": "مشهد",
                    "code": "191",
                },
            ]
        assert url == SNAPPTRIP_TRAIN_SEARCH_URL
        return {
            "solutions": {
                "responseCode": 200,
                "solutions": [
                    {
                        "id": "snapp-1",
                        "departureDateTime": "2026-11-11T18:30:00+03:30",
                        "duration": 720,
                        "seatsRemaining": 5,
                        "pricing": {"totalPayablePrice": 9_400_000},
                        "origin": "1",
                        "destination": "191",
                        "originName": "تهران",
                        "destinationName": "مشهد",
                        "trainCompany": "رجا",
                        "trainNumber": "401",
                        "wagonName": "4 تخته",
                        "ticketType": "NORMAL",
                        "capacityStatus": "AVAILABLE",
                        "exclusible": False,
                    }
                ],
            }
        }

    provider._request_json = fake_request
    result = await provider.search(
        SearchRequest(
            origin="تهران",
            destination="مشهد",
            travel_date=date(2026, 11, 11),
            modes=(TravelMode.TRAIN,),
            passengers=1,
        )
    )

    assert result.journeys
    journey = result.journeys[0]
    assert journey.provider_id == "snapptrip"
    assert journey.service_id == "401"
    assert journey.price_irr == 9_400_000
    assert journey.seats == 5

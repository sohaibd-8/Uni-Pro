from datetime import date

import pytest

from unipro.models import SearchRequest, TravelMode
from unipro.providers.safar724 import Safar724Provider, SAFAR724_CITIES_URL


@pytest.mark.asyncio
async def test_safar724_bus_contract_is_normalized():
    provider = Safar724Provider()

    async def fake_request(url, *, method="GET", params=None, payload=None, headers=None):
        if url == SAFAR724_CITIES_URL:
            return [
                {
                    "Code": "11320000",
                    "Name": "tehran",
                    "PersianName": "تهران",
                    "SearchExpressions": ["Tehran"],
                },
                {
                    "Code": "21310000",
                    "Name": "esfahan",
                    "PersianName": "اصفهان",
                    "SearchExpressions": ["Isfahan"],
                },
            ]
        return {
            "originCode": "11320000",
            "destinationCode": "21310000",
            "items": [
                {
                    "id": "bus-1",
                    "departureTime": "21:30",
                    "price": 5_500_000,
                    "availableSeatCount": 3,
                    "capacity": 25,
                    "companyPersianName": "رویال سفر",
                    "busType": "VIP",
                    "originTerminalPersianName": "ترمینال جنوب",
                    "destinationTerminalPersianName": "کاوه",
                    "vehicleType": "Bus",
                    "status": "Available",
                }
            ],
        }

    provider._request_json = fake_request
    result = await provider.search(
        SearchRequest(
            origin="تهران",
            destination="اصفهان",
            travel_date=date(2026, 11, 11),
            modes=(TravelMode.BUS,),
            passengers=1,
        )
    )

    assert result.journeys
    journey = result.journeys[0]
    assert journey.provider_id == "safar724"
    assert journey.price_irr == 5_500_000
    assert journey.seats == 3
    assert journey.arrival_at is None

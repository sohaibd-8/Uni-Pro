from datetime import date

import pytest

from unipro.models import SearchRequest, TravelMode
from unipro.providers.flytoday import (
    FLYTODAY_BUS_LOCATION_URL,
    FLYTODAY_BUS_SEARCH_URL,
    FlyTodayProvider,
)


@pytest.mark.asyncio
async def test_flytoday_bus_contract_is_normalized():
    provider = FlyTodayProvider()

    async def fake_request(url, *, method="GET", params=None, payload=None, headers=None):
        if url == FLYTODAY_BUS_LOCATION_URL:
            term = payload["searchTerm"]
            if term == "تهران":
                return {
                    "locations": [
                        {"cityId": "1", "cityName": "tehran", "cityNameFa": "تهران"}
                    ]
                }
            return {
                "locations": [
                    {"cityId": "2", "cityName": "isfahan", "cityNameFa": "اصفهان"}
                ]
            }

        assert url == FLYTODAY_BUS_SEARCH_URL
        return {
            "searchId": "search-1",
            "originDestinationItineraries": [
                {
                    "origin": {"cityId": "1"},
                    "destination": {"cityId": "2"},
                    "departureDate": "2026-11-11T00:00:00+03:30",
                    "itineraries": [
                        {
                            "fareSourceCode": "fare-1",
                            "departureDate": "2026-11-11T21:00:00+03:30",
                            "price": 5_300_000,
                            "remainingSeat": 4,
                            "origin": {
                                "cityId": "1",
                                "terminalNameFa": "ترمینال جنوب",
                            },
                            "destination": {
                                "cityId": "2",
                                "terminalNameFa": "کاوه",
                            },
                            "busGroupCompanyNameFa": "همسفر",
                            "busType": "VIP",
                            "isFull": False,
                        }
                    ],
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
    assert journey.provider_id == "flytoday"
    assert journey.price_irr == 5_300_000
    assert journey.seats == 4
    assert journey.raw["operator"] == "همسفر"

from datetime import date

import pytest

from unipro.models import SearchRequest, TravelMode
from unipro.providers.mrbilit import MrBilitProvider


@pytest.mark.asyncio
async def test_mrbilit_train_contract_is_normalized():
    provider = MrBilitProvider()

    async def fake_request(url, *, method="GET", params=None, payload=None, headers=None):
        return {
            "trains": [
                {
                    "id": "train-1",
                    "trainNumber": "401",
                    "departureTime": "2026-11-11T18:30:00+03:30",
                    "arrivalTime": "2026-11-12T06:30:00+03:30",
                    "from": 1,
                    "to": 191,
                    "corporationName": "رجا",
                    "corporationID": "RAJA",
                    "prices": [
                        {
                            "sellType": 3,
                            "classes": [
                                {
                                    "id": "c1",
                                    "price": 9_700_000,
                                    "discount": 200_000,
                                    "capacity": 4,
                                    "minPersons": 1,
                                    "wagonName": "4 تخته",
                                    "isAvailable": True,
                                    "reservationAvailable": True,
                                    "ownerName": "رجا",
                                }
                            ],
                        }
                    ],
                }
            ],
            "contentPath": "",
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
    assert journey.provider_id == "mrbilit"
    assert journey.service_id == "401"
    assert journey.price_irr == 9_500_000
    assert journey.seats == 4

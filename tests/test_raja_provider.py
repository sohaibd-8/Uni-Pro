from datetime import date

import pytest

from unipro.models import SearchRequest, TravelMode
from unipro.providers.raja import RajaProvider, RAJA_STATIONS_URL, RAJA_TRAIN_LIST_URL


def test_raja_query_format():
    value = RajaProvider._encode_query(
        from_station=1,
        to_station=191,
        travel_date=date(2026, 11, 11),
        passengers=1,
    )
    assert value.startswith("1-191-Family-1-")
    assert value.endswith("--1-false-0-0-L1")


@pytest.mark.asyncio
async def test_raja_train_contract_is_normalized(monkeypatch):
    provider = RajaProvider(api_key="official-key", query_password="official-password")
    monkeypatch.setattr(provider, "_encrypt_query", lambda value, password: "encrypted-query")

    async def fake_request(url, *, method="GET", params=None, payload=None, headers=None):
        if url == RAJA_STATIONS_URL:
            return [
                {"Code": 1, "Name": "تهران", "EnglishName": "Tehran"},
                {"Code": 191, "Name": "مشهد", "EnglishName": "Mashhad"},
            ]
        assert url == RAJA_TRAIN_LIST_URL
        assert params == {"q": "encrypted-query"}
        assert headers["api-key"] == "official-key"
        return {
            "GoTrains": [
                {
                    "FromStation": 1,
                    "ToStation": 191,
                    "TrainNumber": 401,
                    "ExitDateTime": "2026-11-11T18:30:00+03:30",
                    "ArrivalDate": "2026-11-12T06:30:00+03:30",
                    "Cost": 9_500_000,
                    "Counting": 4,
                    "AvaliableSellCount": 4,
                    "Remain": 4,
                    "WagonName": "4 تخته",
                    "CompanyName": "رجا",
                }
            ]
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
    assert journey.provider_id == "raja"
    assert journey.service_id == "401"
    assert journey.price_irr == 9_500_000
    assert journey.seats == 4

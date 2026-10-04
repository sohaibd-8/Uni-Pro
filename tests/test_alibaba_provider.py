from datetime import date

import pytest

from unipro.models import SearchRequest, TravelMode
from unipro.providers.alibaba import AlibabaProvider, ALIBABA_TRAIN_URL


@pytest.mark.asyncio
async def test_alibaba_train_contract_is_normalized():
    provider = AlibabaProvider()
    calls = []

    async def fake_request(url, *, method="GET", params=None, payload=None, headers=None):
        calls.append((url, method, params, payload))
        if url == ALIBABA_TRAIN_URL and method == "POST":
            return {"success": True, "result": {"requestId": "req-1"}}
        return {
            "success": True,
            "result": {
                "isCompleted": True,
                "departing": [
                    {
                        "proposalId": 123,
                        "departureDateTime": "2026-11-11T18:30:00+03:30",
                        "arrivalDateTime": "2026-11-12T06:30:00+03:30",
                        "cost": 9_500_000,
                        "originCode": "THR",
                        "destinationCode": "MHD",
                        "companyName": "رجا",
                        "companyCode": "RAJA",
                        "wagonName": "4 تخته",
                        "trainNumber": "401",
                        "seat": 6,
                    }
                ],
            },
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
    assert journey.provider_id == "alibaba"
    assert journey.service_id == "401"
    assert journey.price_irr == 9_500_000
    assert journey.seats == 6
    assert len(calls) == 2

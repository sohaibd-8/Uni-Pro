from __future__ import annotations

from unipro.config import Settings
from unipro.models import TravelMode
from unipro.providers.alibaba import AlibabaProvider
from unipro.providers.base import TravelProvider
from unipro.providers.demo import DemoProvider
from unipro.providers.mrbilit import MrBilitProvider
from unipro.providers.safar724 import Safar724Provider


class ProviderRegistry:
    def __init__(self, providers: list[TravelProvider]):
        self.providers = providers

    @classmethod
    def from_settings(cls, settings: Settings) -> "ProviderRegistry":
        providers: list[TravelProvider] = []

        if settings.demo_mode:
            providers.extend(
                [
                    DemoProvider(
                        "demo_rail_a",
                        "Demo Rail A",
                        {TravelMode.TRAIN},
                        price_multiplier=1.00,
                        timezone_name=settings.app_timezone,
                    ),
                    DemoProvider(
                        "demo_rail_b",
                        "Demo Rail B",
                        {TravelMode.TRAIN},
                        price_multiplier=1.06,
                        timezone_name=settings.app_timezone,
                    ),
                    DemoProvider(
                        "demo_bus_a",
                        "Demo Bus",
                        {TravelMode.BUS},
                        price_multiplier=0.98,
                        timezone_name=settings.app_timezone,
                    ),
                ]
            )
            return cls(providers)

        if settings.enable_alibaba:
            provider = AlibabaProvider()
            provider.request_timeout_seconds = settings.provider_timeout_seconds
            providers.append(provider)

        if settings.enable_mrbilit:
            provider = MrBilitProvider()
            provider.request_timeout_seconds = settings.provider_timeout_seconds
            providers.append(provider)

        if settings.enable_safar724:
            provider = Safar724Provider()
            provider.request_timeout_seconds = settings.provider_timeout_seconds
            providers.append(provider)

        return cls(providers)

    def status_lines(self) -> list[str]:
        if not self.providers:
            return ["هیچ Provider فعالی ثبت نشده است."]
        return [
            f"• {p.display_name} (`{p.provider_id}`): "
            f"{', '.join(sorted(mode.value for mode in p.supported_modes))}"
            for p in self.providers
        ]

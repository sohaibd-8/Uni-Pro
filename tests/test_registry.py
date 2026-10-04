from unipro.config import Settings
from unipro.providers.registry import ProviderRegistry


def test_live_registry_uses_real_providers_only():
    settings = Settings(
        demo_mode=False,
        enable_alibaba=True,
        enable_mrbilit=True,
        enable_safar724=True,
    )
    registry = ProviderRegistry.from_settings(settings)
    assert {p.provider_id for p in registry.providers} == {
        "alibaba",
        "mrbilit",
        "safar724",
    }


def test_demo_registry_does_not_mix_live_inventory():
    settings = Settings(demo_mode=True)
    registry = ProviderRegistry.from_settings(settings)
    assert all(p.provider_id.startswith("demo_") for p in registry.providers)

from __future__ import annotations

from dataclasses import dataclass

from unipro.providers.web_common import normalize_text


@dataclass(frozen=True, slots=True)
class RailStation:
    name: str
    code: str
    station_id: int
    slug: str
    aliases: tuple[str, ...] = ()


RAIL_STATIONS = (
    RailStation("تهران", "THR", 1, "tehran"),
    RailStation("مشهد", "MHD", 191, "mashhad"),
    RailStation("اصفهان", "IFN", 21, "isfahan"),
    RailStation("شیراز", "SYZ", 255, "shiraz"),
    RailStation("تبریز", "TBZ", 55, "tabriz"),
    RailStation("اهواز", "AWZ", 25, "ahvaz"),
    RailStation("رشت", "RASHT", 451, "rasht", ("RHD",)),
    RailStation("کرمان", "KER", 167, "kerman"),
    RailStation("یزد", "AZD", 219, "yazd"),
    RailStation("بندرعباس", "BND", 37, "bandarabbas", ("بندر عباس",)),
    RailStation("ساری", "SRY", 100, "sari"),
    RailStation("گرگان", "GBT", 175, "gorgan"),
    RailStation("کرمانشاه", "KERSHAH", 195, "kermanshah"),
    RailStation("ارومیه", "OMH", 448, "urmia"),
    RailStation("زاهدان", "ZAH", 259, "zahedan"),
    RailStation("قم", "QUM", 161, "qom"),
    RailStation("کاشان", "KASHAN", 162, "kashan"),
    RailStation("قزوین", "GZW", 160, "qazvin"),
    RailStation("شهرکرد", "SHKORD", 600, "shahrekord"),
    RailStation("کرج", "KAR", 165, "karaj"),
)


def resolve_rail_station(value: str) -> RailStation | None:
    needle = normalize_text(value)
    matches: list[RailStation] = []
    for station in RAIL_STATIONS:
        values = {
            normalize_text(station.name),
            normalize_text(station.code),
            normalize_text(station.station_id),
            normalize_text(station.slug),
            *(normalize_text(alias) for alias in station.aliases),
        }
        if needle in values:
            matches.append(station)
    return matches[0] if len(matches) == 1 else None

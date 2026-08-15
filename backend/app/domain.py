from enum import StrEnum


class ForecastHorizon(StrEnum):
    h1 = "1h"
    h3 = "3h"
    h6 = "6h"
    h12 = "12h"
    h24 = "24h"
    h48 = "48h"
    h72 = "72h"
    d5 = "5d"
    d7 = "7d"


class PrecipitationType(StrEnum):
    rain = "rain"
    snow = "snow"
    sleet = "sleet"
    freezing_rain = "freezing_rain"
    none = "none"


HORIZON_HOURS: dict[ForecastHorizon, int] = {
    ForecastHorizon.h1: 1,
    ForecastHorizon.h3: 3,
    ForecastHorizon.h6: 6,
    ForecastHorizon.h12: 12,
    ForecastHorizon.h24: 24,
    ForecastHorizon.h48: 48,
    ForecastHorizon.h72: 72,
    ForecastHorizon.d5: 120,
    ForecastHorizon.d7: 168,
}

REQUIRED_HORIZONS = list(HORIZON_HOURS.keys())

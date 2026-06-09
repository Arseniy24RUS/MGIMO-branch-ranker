from __future__ import annotations

from typing import Any

import pandas as pd
import requests

COMTRADE_V1 = "https://comtradeapi.un.org/data/v1/get"


def fetch_trade_data(
    reporter_code: str,
    partner_code: str = "643",
    period: int | str | None = None,
    flow_code: str = "all",
    type_code: str = "C",
    freq_code: str = "A",
    classification_code: str = "HS",
    commodity_code: str = "TOTAL",
    subscription_key: str | None = None,
    **extra_params: Any,
) -> pd.DataFrame:  # pragma: no cover - network helper
    """Thin UN Comtrade API wrapper.

    By default the partner is Russia (UN M49 code 643) and the commodity is
    total goods trade. High-volume production runs should use an API key and/or
    bulk downloads according to UN Comtrade rules.
    """
    url = f"{COMTRADE_V1}/{type_code}/{freq_code}/{classification_code}"
    params: dict[str, Any] = {
        "reporterCode": reporter_code,
        "partnerCode": partner_code,
        "cmdCode": commodity_code,
        "flowCode": flow_code,
    }
    if period is not None:
        params["period"] = str(period)
    params.update(extra_params)
    headers = {"Ocp-Apim-Subscription-Key": subscription_key} if subscription_key else None
    r = requests.get(url, params=params, headers=headers, timeout=120)
    r.raise_for_status()
    payload = r.json()
    data = payload.get("data", payload if isinstance(payload, list) else [])
    return pd.DataFrame(data)

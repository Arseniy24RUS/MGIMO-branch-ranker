from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET

from mgimo_ranker.utils import http_get_text

CBR_DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"


def fetch_usd_rub(date: dt.date | None = None) -> float:
    params = None
    if date is not None:
        params = {"date_req": date.strftime("%d/%m/%Y")}
    xml_text = http_get_text(CBR_DAILY_URL, params=params)
    root = ET.fromstring(xml_text)
    for valute in root.findall("Valute"):
        char_code = valute.findtext("CharCode")
        if char_code == "USD":
            value = valute.findtext("Value")
            nominal = valute.findtext("Nominal") or "1"
            if value is None:
                break
            return float(value.replace(",", ".")) / float(nominal.replace(",", "."))
    raise RuntimeError("USD rate was not found in CBR XML response")

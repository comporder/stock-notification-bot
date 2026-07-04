"""
Borsa İstanbul hisseleri için günlük değişim takibi yapan ve Telegram üzerinden
bildirim gönderen script.

Takip edilecek hisseler ve eşik değerleri config.json dosyasından okunur.
Kimlik bilgileri (Telegram token/chat id) ortam değişkenlerinden (environment
variables) okunur; kodun içine ASLA yazılmaz.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
REQUEST_TIMEOUT = 10


@dataclass
class TakipEdilenHisse:
    ticker: str  # örn: "BETAE.IS"
    ad: str  # örn: "Beta Enerji"
    esik_yuzde: float  # bu değerin altına düşerse bildirim gider


def config_yukle(path: Path = CONFIG_PATH) -> list[TakipEdilenHisse]:
    with open(path, "r", encoding="utf-8") as f:
        veri = json.load(f)
    return [
        TakipEdilenHisse(
            ticker=item["ticker"],
            ad=item.get("ad", item["ticker"]),
            esik_yuzde=float(item["esik_yuzde"]),
        )
        for item in veri["hisseler"]
    ]


def guncel_fiyat_ve_degisim(ticker: str) -> tuple[float, float]:
    """Yahoo Finance chart API'sinden anlık fiyatı ve önceki kapanışa göre
    yüzde değişimi döndürür."""
    url = YAHOO_CHART_URL.format(ticker=ticker)
    r = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    meta = r.json()["chart"]["result"][0]["meta"]
    fiyat = meta["regularMarketPrice"]
    onceki_kapanis = meta["previousClose"]
    degisim_yuzde = (fiyat - onceki_kapanis) / onceki_kapanis * 100
    return fiyat, degisim_yuzde


def telegram_mesaj_gonder(token: str, chat_id: str, mesaj: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        url,
        data={"chat_id": chat_id, "text": mesaj, "parse_mode": "HTML"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()


def main() -> int:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("HATA: TELEGRAM_TOKEN ve/veya TELEGRAM_CHAT_ID ortam değişkeni tanımlı değil.", file=sys.stderr)
        return 1

    hisseler = config_yukle()
    if not hisseler:
        print("UYARI: config.json içinde takip edilecek hisse tanımlı değil.")
        return 0

    hata_sayisi = 0
    for hisse in hisseler:
        try:
            fiyat, degisim = guncel_fiyat_ve_degisim(hisse.ticker)
        except Exception as exc:  # noqa: BLE001 - dış API çağrısı, geniş yakalama kasıtlı
            print(f"[{hisse.ad}] Fiyat çekilemedi: {exc}", file=sys.stderr)
            hata_sayisi += 1
            continue

        print(f"[{hisse.ad}] Fiyat: {fiyat} TL | Değişim: %{degisim:.2f} (eşik: %{hisse.esik_yuzde})")

        if degisim < hisse.esik_yuzde:
            mesaj = (
                f"⚠️ <b>{hisse.ad}</b> artış hızı kesildi\n"
                f"Değişim: %{degisim:.2f} (eşik: %{hisse.esik_yuzde})\n"
                f"Güncel fiyat: {fiyat} TL"
            )
            try:
                telegram_mesaj_gonder(token, chat_id, mesaj)
                print(f"[{hisse.ad}] Bildirim gönderildi.")
            except Exception as exc:  # noqa: BLE001
                print(f"[{hisse.ad}] Bildirim gönderilemedi: {exc}", file=sys.stderr)
                hata_sayisi += 1

    return 1 if hata_sayisi else 0


if __name__ == "__main__":
    raise SystemExit(main())

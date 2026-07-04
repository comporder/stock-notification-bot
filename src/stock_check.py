"""
Borsa İstanbul hisseleri için GÜNLÜK ÖZET bildirimi gönderen script.

Tüm takip edilen hisseler tek bir Telegram mesajında raporlanır:
- Güncel fiyat ve günlük değişim yüzdesi
- Bugün tavan yapılıp yapılmadığı
- Kaç gündür kesintisiz tavan serisi sürdüğü (state.json'da saklanır)
- Halka arz fiyatına göre toplam getiri (config.json'da tanımlıysa)

Özel durumlar hata olarak değil, bilgi olarak ele alınır:
- Hafta sonu (Cumartesi/Pazar): piyasa kapalı olduğu için tek satırlık
  bir bilgi mesajı gönderilir, hisse verisi çekilmeye çalışılmaz.
- Henüz borsada işlem görmeyen bir hisse (örn. yeni halka arz, henüz
  kota alınmamış): "henüz işlem görmüyor" notu düşülür, script hata
  vermez / job'ı FAIL ettirmez.

Bu script SATIŞ/TUTMA tavsiyesi vermez, sadece objektif veriyi bir araya
getirip Telegram'a gönderir. Karar kullanıcıya aittir.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests

PROJE_KOKU = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJE_KOKU / "config.json"
STATE_PATH = PROJE_KOKU / "state.json"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
REQUEST_TIMEOUT = 10
HAFTA_SONU_GUNLERI = (5, 6)  # Python'da Cumartesi=5, Pazar=6


@dataclass
class TakipEdilenHisse:
    ticker: str
    ad: str
    tavan_esigi: float
    adet: float | None = None
    maliyet_fiyati: float | None = None


def config_yukle(path: Path = CONFIG_PATH) -> list[TakipEdilenHisse]:
    with open(path, "r", encoding="utf-8") as f:
        veri = json.load(f)
    return [
        TakipEdilenHisse(
            ticker=item["ticker"],
            ad=item.get("ad", item["ticker"]),
            tavan_esigi=float(item["tavan_esigi"]),
            adet=item.get("adet"),
            maliyet_fiyati=item.get("maliyet_fiyati"),
        )
        for item in veri["hisseler"]
    ]


def state_yukle(path: Path = STATE_PATH) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def state_kaydet(state: dict, path: Path = STATE_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def guncel_fiyat_ve_degisim(ticker: str) -> tuple[float, float]:
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


def hisse_blogu_olustur(hisse: TakipEdilenHisse, fiyat: float, degisim: float, tavan_serisi: int, tavan_bugun: bool) -> str:
    satirlar = [
        f"📊 <b>{hisse.ad}</b>",
        f"Fiyat: {fiyat:.2f} TL | Bugünkü değişim: %{degisim:.2f}",
    ]

    if hisse.adet and hisse.maliyet_fiyati:
        guncel_deger = fiyat * hisse.adet
        toplam_maliyet = hisse.maliyet_fiyati * hisse.adet
        kar_zarar_tl = guncel_deger - toplam_maliyet
        kar_zarar_yuzde = (fiyat - hisse.maliyet_fiyati) / hisse.maliyet_fiyati * 100
        isaret = "🟢" if kar_zarar_tl >= 0 else "🔴"
        satirlar.append(
            f"Pozisyon: {hisse.adet:g} adet, maliyet {hisse.maliyet_fiyati:.2f} TL"
        )
        satirlar.append(
            f"Güncel değer: {guncel_deger:,.2f} TL | Kâr/Zarar: {isaret} {kar_zarar_tl:,.2f} TL (%{kar_zarar_yuzde:.2f})"
        )

    durum = "Tavanda kapadı ✅" if tavan_bugun else "Tavan yapılamadı ⚠️"
    satirlar.append(f"Durum: {durum} | Tavan serisi: {tavan_serisi} gün")
    return "\n".join(satirlar)


def hisse_bekleniyor_blogu_olustur(hisse: TakipEdilenHisse) -> str:
    return f"⏳ <b>{hisse.ad}</b>\nHenüz borsada işlem görmüyor, veri mevcut değil."


def main() -> int:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("HATA: TELEGRAM_TOKEN ve/veya TELEGRAM_CHAT_ID tanımlı değil.", file=sys.stderr)
        return 1

    bugun_tarih = date.today()

    if bugun_tarih.weekday() in HAFTA_SONU_GUNLERI:
        mesaj = f"📅 {bugun_tarih.isoformat()} — Bugün hafta sonu, BIST kapalı. Herhangi bir değişiklik yok."
        print(mesaj)
        try:
            telegram_mesaj_gonder(token, chat_id, mesaj)
        except Exception as exc:  # noqa: BLE001
            print(f"Bildirim gönderilemedi: {exc}", file=sys.stderr)
            return 1
        return 0

    hisseler = config_yukle()
    state = state_yukle()
    bugun = bugun_tarih.isoformat()
    bloklar: list[str] = []
    toplam_guncel_deger = 0.0
    toplam_maliyet = 0.0
    portfoy_hesaplanabilir = False

    for hisse in hisseler:
        try:
            fiyat, degisim = guncel_fiyat_ve_degisim(hisse.ticker)
        except Exception as exc:  # noqa: BLE001
            # Hisse henüz işlem görmüyor olabilir (örn. yeni halka arz, henüz
            # kota alınmamış). Bu bir hata değil, beklenen bir durum -
            # job'ı FAIL ettirmeden bilgi notu ekleyip devam ediyoruz.
            print(f"[{hisse.ad}] Henüz veri yok (muhtemelen işlem görmüyor): {exc}")
            bloklar.append(hisse_bekleniyor_blogu_olustur(hisse))
            continue

        tavan_bugun = degisim >= hisse.tavan_esigi
        onceki_durum = state.get(hisse.ticker, {})
        onceki_seri = onceki_durum.get("tavan_serisi", 0)
        yeni_seri = onceki_seri + 1 if tavan_bugun else 0
        state[hisse.ticker] = {"son_tarih": bugun, "tavan_serisi": yeni_seri}

        if hisse.adet and hisse.maliyet_fiyati:
            toplam_guncel_deger += fiyat * hisse.adet
            toplam_maliyet += hisse.maliyet_fiyati * hisse.adet
            portfoy_hesaplanabilir = True

        print(f"[{hisse.ad}] Fiyat: {fiyat} TL | Değişim: %{degisim:.2f} | Seri: {yeni_seri}")
        bloklar.append(hisse_blogu_olustur(hisse, fiyat, degisim, yeni_seri, tavan_bugun))

    if not bloklar:
        print("Raporlanacak hisse yok.")
        return 0

    mesaj = f"🗓️ Günlük Hisse Özeti ({bugun})\n\n" + "\n\n".join(bloklar)

    if portfoy_hesaplanabilir:
        toplam_kar_zarar = toplam_guncel_deger - toplam_maliyet
        toplam_yuzde = (toplam_kar_zarar / toplam_maliyet * 100) if toplam_maliyet else 0.0
        isaret = "🟢" if toplam_kar_zarar >= 0 else "🔴"
        mesaj += (
            f"\n\n💼 <b>Toplam Portföy</b>\n"
            f"Güncel değer: {toplam_guncel_deger:,.2f} TL | Maliyet: {toplam_maliyet:,.2f} TL\n"
            f"Toplam Kâr/Zarar: {isaret} {toplam_kar_zarar:,.2f} TL (%{toplam_yuzde:.2f})"
        )

    mesaj += "\n\nℹ️ Bu bilgilendirme amaçlıdır, yatırım tavsiyesi değildir."

    try:
        telegram_mesaj_gonder(token, chat_id, mesaj)
        print("Günlük özet gönderildi.")
    except Exception as exc:  # noqa: BLE001
        print(f"Bildirim gönderilemedi: {exc}", file=sys.stderr)
        return 1

    state_kaydet(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

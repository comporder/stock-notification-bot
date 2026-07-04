# stock-notification-bot

Borsa İstanbul'da seçtiğin hisselerin günlük yüzde değişimini takip eder;
değişim belirlediğin eşiğin altına düştüğünde Telegram üzerinden bildirim
gönderir. GitHub Actions üzerinde bulutta çalışır — bilgisayarının veya
telefonunun açık olması gerekmez.

## Klasör yapısı

```
stock-notification-bot/
├── config.json                     # Takip edilecek hisseler ve eşik değerleri
├── requirements.txt
├── .env.example                    # Yerel test için örnek ortam değişkenleri
├── src/
│   └── stock_check.py              # Ana script
└── .github/workflows/
    └── stock-check.yml             # Zamanlanmış çalıştırma (cron)
```

## Kurulum

### 1) Telegram botu oluştur
1. Telegram'da **@BotFather**'a git, `/newbot` yaz, adını belirle.
2. Sana verilen **token**'ı not al.
3. Botuna Telegram'dan bir mesaj gönder (örn. "merhaba") — bot sana ancak
   önce sen ona yazdıktan sonra mesaj gönderebilir.
4. Chat ID'ni öğrenmek için tarayıcıda şu adresi aç (TOKEN'ı kendi tokeninle
   değiştir):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Dönen JSON'daki `"chat":{"id": ...}` alanındaki sayı senin chat_id'in.

### 2) Hangi hisseleri takip edeceğini belirle
`config.json` dosyasını düzenle:

```json
{
  "hisseler": [
    { "ticker": "BETAE.IS", "ad": "Beta Enerji", "esik_yuzde": 9.5 }
  ]
}
```

- `ticker`: Yahoo Finance formatı — BIST hisseleri için sonuna `.IS` eklenir.
- `esik_yuzde`: Günlük değişim bu değerin altına düşerse bildirim gönderilir.

### 3) GitHub'a yükle

Bu klasörü, oluşturduğun `stock-notification-bot` reposuna push et:

```bash
cd stock-notification-bot
git init
git add .
git commit -m "İlk kurulum: hisse takip botu"
git branch -M main
git remote add origin https://github.com/KULLANICI_ADIN/stock-notification-bot.git
git push -u origin main
```

(Repoyu zaten GitHub'da oluşturduysan ve içinde dosya varsa, önce
`git clone` ile indirip dosyaları içine kopyaman ve öyle push etmen gerekebilir.)

### 4) Secrets'ları GitHub'a ekle

Repo → **Settings → Secrets and variables → Actions → New repository secret**:
- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`

### 5) Çalıştığını doğrula

Repo → **Actions** sekmesi → **Hisse Takip** workflow'u → **Run workflow**
ile elle bir kere tetikle, loglardan çalıştığını doğrula.

## Yerel test (isteğe bağlı, bilgisayarda)

```bash
pip install -r requirements.txt
export TELEGRAM_TOKEN=...
export TELEGRAM_CHAT_ID=...
python src/stock_check.py
```

## Notlar

- Script hafta içi 07:00-15:10 UTC (10:00-18:10 TR saati) arasında 15
  dakikada bir çalışacak şekilde ayarlı; `.github/workflows/stock-check.yml`
  içindeki `cron` satırından değiştirebilirsin.
- Bu proje bir yatırım tavsiyesi aracı değildir, sadece belirlediğin eşiğe
  göre bildirim gönderir.
# stock-notification-bot

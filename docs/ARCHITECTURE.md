# معماری UniPro Travel Watch

## اصل طراحی

UniPro یک فروشنده بلیت نیست؛ یک **Travel Intent + Watch Platform** است. کاربر می‌گوید کجا و چه زمانی باید برود و سیستم چند منبع را پایش، نرمال‌سازی و مقایسه می‌کند.

```text
Telegram Bot
    ↓
Travel Request / Watch
    ↓
Deduplicated Watch Groups
    ↓
Search Orchestrator
 ┌────────────┬────────────┐
 │ Train APIs │  Bus APIs  │   (+ Flight later)
 └────────────┴────────────┘
    ↓
Normalized Journey[]
    ↓
Price Comparison / Deduplication
    ↓
Direct route available?
    ├─ Yes → Alert + Booking Link
    └─ No  → Alternative Route Engine → one-stop route suggestions
```

## چرا Watchها Deduplicate می‌شوند؟

اگر 500 کاربر دقیقاً `بندرعباس → تهران، 20 آبان، قطار` را بخواهند، UniPro نباید 500 بار Provider را صدا بزند. `WatchRunner` Watchهای یکسان را در هر چرخه بر اساس route/date/mode/passengers گروه‌بندی می‌کند و یک Search را برای همه آن کاربران reuse می‌کند.

## Provider Contract

هر Provider باید `TravelProvider.search(SearchRequest)` را پیاده کند و `ProviderResult` برگرداند. Provider می‌تواند وضعیت زیر را اعلام کند:

- `AVAILABLE`
- `UNAVAILABLE`
- `NOT_RELEASED`
- `ERROR`

Core نباید درباره endpoint، header یا authentication فروشنده چیزی بداند.

## مسیر جایگزین

نسخه MVP مسیرهای یک‌توقفه را بررسی می‌کند. برای هر Hub:

1. Origin → Hub
2. Hub → Destination
3. بررسی حداقل زمان انتقال
4. حذف انتظار بیش از سقف مشخص
5. امتیازدهی بر اساس قیمت + زمان کل + زمان انتظار

برای مقیاس بزرگ‌تر، این بخش باید به graph search با cache زمانی و timetable index ارتقا پیدا کند.

## امنیت

- توکن بات و کلید API فقط Environment Variable.
- `ADMIN_IDS` allowlist است.
- هیچ اطلاعات بانکی در MVP ذخیره نمی‌شود.
- خرید خارج از UniPro و روی لینک فروشنده انجام می‌شود.
- Provider واقعی باید rate-limit و terms-of-service را رعایت کند.

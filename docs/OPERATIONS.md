# استقرار و پایش

## Deploy پیشنهادی MVP

یک Container همیشه روشن با Volume پایدار برای SQLite کافی است. برای Pilot بزرگ‌تر، PostgreSQL و Worker جدا پیشنهاد می‌شود.

### حداقل متغیرها

- `TELEGRAM_BOT_TOKEN`
- `ADMIN_IDS`
- `DATABASE_PATH`
- `DEMO_MODE=false` پس از اضافه شدن Provider واقعی

## Health Check

`GET /health` روی `HEALTH_PORT` وضعیت موارد زیر را می‌دهد:

- database
- polling_enabled
- providers count
- demo_mode
- last_cycle_at
- last_group_count

## Alertهای عملیاتی پیشنهادی

پس از اتصال Provider واقعی:

1. Health endpoint برای 2 چرخه متوالی Down شد.
2. `last_cycle_at` بیش از 3× poll interval قدیمی شد.
3. Error rate یک Provider در 10 دقیقه از 20% گذشت.
4. هیچ نتیجه‌ای از یک Provider پرترافیک برای مدت غیرعادی دریافت نشد.
5. Queue/Watch cycle بیش از زمان poll interval طول کشید.

## Backup

در SQLite: روزانه snapshot فایل DB و نگهداری حداقل 7 نسخه. قبل از migration نسخه فوری گرفته شود.

## Runbook

### Provider خراب است
- Provider را از Registry/feature flag غیرفعال کن.
- Core و سایر Providerها ادامه می‌دهند.
- علت و response code ثبت شود.

### Telegram مشکل دارد
- Watch data در DB باقی می‌ماند.
- پس از recovery چرخه بعدی اجرا می‌شود.

### Watch Engine باید متوقف شود
از `/admin` دکمه «توقف Watch Engine» استفاده کن؛ Bot و پنل مدیریت همچنان آنلاین می‌مانند.

## قبل از Production

- PostgreSQL
- Redis cache / distributed lock
- Sentry یا معادل آن
- Prometheus/OpenTelemetry metrics
- CI تست و lint
- secrets manager
- rate limit per provider
- provider-specific retry/backoff

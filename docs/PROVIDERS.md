# Provider Status — 2026-10-04

این فایل قراردادهای HTTP فعلی‌ای را که UniPro برای **خواندن موجودی و مقایسه قیمت** استفاده می‌کند ثبت می‌کند. این قراردادها با API رسمی شریک تجاری یکی نیستند مگر صراحتاً ذکر شود.

## Alibaba

### قطار
- `POST https://ws.alibaba.ir/api/v2/train/available`
- سپس `GET https://ws.alibaba.ir/api/v2/train/available/{requestId}`
- خروجی مورد استفاده: زمان حرکت/رسیدن، قیمت، شماره قطار، شرکت، کلاس واگن، ظرفیت و proposal id.

### اتوبوس
- جست‌وجوی پایانه: `GET https://ws.alibaba.ir/api/v1/bus/stations`
- موجودی: `GET https://ws.alibaba.ir/api/v2/bus/available`
- پارامتر موجودی `orginCityCode` عمداً با همین spelling استفاده می‌شود چون قرارداد وب فعلی همین نام را دارد.

## MrBilit

### قطار
- `GET https://train.mrbilit.com/api/GetAvailable/v2`
- station id، تاریخ، تعداد مسافر و sell type در Query ارسال می‌شود.

### اتوبوس
- شهرها: `GET https://bus.mrbilit.ir/api/CityList/GetBusCityList`
- موجودی: `POST https://bus.mrbilit.ir/api/GetBusServices`
- درخواست موجودی با `application/json-patch+json` فرستاده می‌شود.

## SnappTrip

### قطار
- ایستگاه‌ها: `GET https://train.snapptrip.com/statics/v1/stations`
- موجودی: `POST https://train.snapptrip.com/listing/v2/search`
- شناسه‌های endpoint از فهرست زندهٔ ایستگاه‌ها resolve می‌شوند.

### اتوبوس
- شهرها: `GET https://fp.snapptrip.com/bus-listing-go/v3/endpoints`
- موجودی: `GET https://bus.snapptrip.com/bus-listing-go/v2/availability/{origin}/to/{destination}/on/{date}`

## Safar724

### اتوبوس
- شهرها: `GET https://safar724.com/route/getcities`
- موجودی: `GET https://service.safar724.com/cs/api/bus/route`
- تاریخ به شمسی ارسال می‌شود.

Safar724 علاوه بر قرارداد وب، به‌صورت رسمی Web Service فروش بلیت اتوبوس برای همکاری تجاری ارائه می‌کند. برای نسخه تجاری UniPro باید مهاجرت به credential رسمی در اولویت باشد.

## FlyToday

### اتوبوس
- جست‌وجوی شهر: `POST https://placesearch.flytoday.ir/api/Bus/Search`
- موجودی: `POST https://www.flytodayir.com/api/gateway/V1/Bus/Search`
- درخواست وب فعلی از headerهای `X-App`, `x-currency`, `x-origin` و `X-Path` استفاده می‌کند.
- این Provider در MVP فقط برای اتوبوس فعال است؛ پرواز خارج از Scope فعلی Travel Watch است.

## Raja

### قطار مستقیم
- ایستگاه‌ها: `GET https://www.raja.ir/assets/File/station.json`
- موجودی: `GET https://hostservice.raja.ir/Api/ServiceProvider/TrainListEq?q=...`
- Header موردنیاز: `api-key`
- Query به فرمت زیر ساخته می‌شود و سپس با AES-CBC + PBKDF2-SHA1 رمز می‌شود:
  `FromStation-ToStation-Family-1-yyyyMMdd--Passengers-false-0-0-L1`
- پاسخ اصلی از `GoTrains` خوانده می‌شود.

UniPro این Adapter را پیاده کرده، اما فقط وقتی هر سه شرط برقرار باشند ثبت می‌کند:
1. `DEMO_MODE=false`
2. `ENABLE_RAJA=true`
3. `RAJA_API_KEY` و `RAJA_QUERY_PASSWORD` از Secret/Environment داده شده باشند.

UniPro کلید API را از JavaScript سایت استخراج نمی‌کند و credential قدیمی/منتشرشده را reuse نمی‌کند. 401/403 نیز دور زده یا retry نمی‌شود.

## سیاست شکست Provider

تغییر یک سایت نباید Bot را Down کند:
- خطای Provider داخل `ProviderResult.ERROR` ایزوله می‌شود.
- بقیه Providerها ادامه می‌دهند.
- 401/403 retry نمی‌شود.
- 429/502/503/504 حداکثر یک retry کوتاه دارند.
- تست‌های contract parser در CI بدون تماس شبکه اجرا می‌شوند.

## نکته حقوقی/عملیاتی

وجود endpoint در frontend وب به معنی تضمین API عمومی یا اجازه استفاده تجاری نامحدود نیست. قبل از Pilot تجاری گسترده، Terms، rate limit و قرارداد Provider باید بررسی شود.

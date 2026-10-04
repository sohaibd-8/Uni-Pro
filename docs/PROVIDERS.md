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

## Raja

Provider مستقیم Raja فعلاً در Registry فعال نیست.

نمونه‌های عمومی قدیمی برای موجودی قطار از `hostservice.raja.ir/Api/ServiceProvider/TrainListEq` با query رمز‌شده و credential/API key استفاده می‌کنند. چون یک قرارداد عمومی، پایدار و مجاز برای استفاده بدون credential رسمی تأیید نشده، UniPro آن endpoint محافظت‌شده را hard-code نکرده است.

مسیر درست:
1. دریافت دسترسی رسمی Raja/سامانه ریلی یا از Aggregator قراردادی.
2. ساخت `RajaProvider` با credential در Secret Manager.
3. تست contract و rate limit.
4. فعال‌سازی با Feature Flag.

## سیاست شکست Provider

تغییر یک سایت نباید Bot را Down کند:
- خطای Provider داخل `ProviderResult.ERROR` ایزوله می‌شود.
- بقیه Providerها ادامه می‌دهند.
- 401/403 retry نمی‌شود.
- 429/502/503/504 حداکثر یک retry کوتاه دارند.
- تست‌های contract parser در CI بدون تماس شبکه اجرا می‌شوند.

## نکته حقوقی/عملیاتی

وجود endpoint در frontend وب به معنی تضمین API عمومی یا اجازه استفاده تجاری نامحدود نیست. قبل از Pilot تجاری گسترده، Terms، rate limit و قرارداد Provider باید بررسی شود.

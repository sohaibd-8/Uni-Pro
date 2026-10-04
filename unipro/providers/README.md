# Provider adapters

Core UniPro فقط قرارداد `TravelProvider` را می‌شناسد. جزئیات HTTP هر فروشنده داخل Adapter خودش ایزوله شده است.

## Providerهای فعلی

- `AlibabaProvider`: قطار + اتوبوس
- `MrBilitProvider`: قطار + اتوبوس
- `Safar724Provider`: اتوبوس
- `DemoProvider`: تست محلی بدون شبکه

## قواعد اتصال

1. Core پروژه نباید endpoint اختصاصی یک فروشنده را بشناسد.
2. Credential و secret فقط از Environment خوانده شوند.
3. درخواست‌ها read-only هستند؛ UniPro در MVP رزرو یا پرداخت انجام نمی‌دهد.
4. HTTP 401/403 retry یا دور زده نمی‌شود.
5. Retry فقط برای خطاهای شبکه و وضعیت‌های موقت 429/502/503/504 انجام می‌شود.
6. CAPTCHA، challenge انسانی و احراز هویت دور زده نمی‌شوند.
7. برای Production تجاری، API رسمی/قراردادی نسبت به web contract اولویت دارد.
8. `NOT_RELEASED` فقط وقتی Provider واقعاً بتواند «فروش هنوز شروع نشده» را از «ظرفیت نیست» تفکیک کند برگردانده می‌شود.

## Demo vs Live

`DEMO_MODE=true` فقط Demo Providerها را فعال می‌کند و داده واقعی و ساختگی را با هم مخلوط نمی‌کند.

برای Live:

```env
DEMO_MODE=false
ENABLE_ALIBABA=true
ENABLE_MRBILIT=true
ENABLE_SAFAR724=true
```

وضعیت و endpointهای تأییدشده در `docs/PROVIDERS.md` ثبت می‌شوند.

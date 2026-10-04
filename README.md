# UniPro 🎓

**دستیار زندگی دانشجویی — با Travel Watch به‌عنوان اولین ماژول**

UniPro یک ربات تلگرام برای دانشجوهاست که سفر را از «جست‌وجوی دستی بلیت» به «درخواست و پایش خودکار» تبدیل می‌کند.

## MVP فعلی

- 🔔 ثبت Watch برای مسیر و تاریخ مشخص
- 🔍 جست‌وجوی فوری هنگام ثبت Watch
- 🚆 قطار و 🚌 اتوبوس از طریق Provider Adapter
- 💰 نرمال‌سازی و مقایسه قیمت چند فروشنده
- 👀 پایش خودکار Watchهای یکتا (Deduplicated Watch Engine)
- 🔀 پیشنهاد مسیر یک‌توقفه در صورت نبود مسیر مستقیم
- 📩 هشدار تلگرام + لینک خرید
- 🛠 پنل مدیریت داخل خود ربات برای ادمین
- ❤️ Health endpoint برای پایش سرویس
- 🌐 Provider زنده: Alibaba (قطار/اتوبوس)، MrBilit (قطار/اتوبوس)، Safar724 (اتوبوس)
- 🧪 Demo Provider برای تست بدون شبکه

> Providerهای زنده از قراردادهای **read-only وب** فروشندگان استفاده می‌کنند و پشت Provider Adapter ایزوله‌اند. این endpointها لزوماً API عمومیِ دارای SLA نیستند و ممکن است با تغییر سایت عوض شوند؛ برای همکاری تجاری باید دسترسی رسمی/قراردادی هر فروشنده جداگانه گرفته شود. UniPro CAPTCHA، احراز هویت یا کنترل دسترسی فروشنده را دور نمی‌زند.

## اجرای سریع

```bash
cp .env.example .env
# TELEGRAM_BOT_TOKEN و ADMIN_IDS را تنظیم کنید
pip install -r requirements.txt
python -m unipro.main
```

برای تست بدون شبکه، `DEMO_MODE=true` را نگه دارید. برای جست‌وجوی زنده، `DEMO_MODE=false` کنید؛ سپس هر Provider را با `ENABLE_ALIBABA`، `ENABLE_MRBILIT` و `ENABLE_SAFAR724` روشن/خاموش کنید.

## منوی اصلی ربات

- 🔔 بلیت این تاریخ اومد، خبرم کن
- 🔍 الان بلیت پیدا کن
- 🆘 هرجوری شده برسون من
- 👀 سفرهای تحت نظر

## پنل ادمین داخل بات

با `/admin` و فقط برای شناسه‌های موجود در `ADMIN_IDS`. اگر شناسه عددی خودت را نمی‌دانی، داخل بات `/id` بزن:

- آمار کاربران و Watchها
- مشاهده Watchهای اخیر
- وضعیت Providerها
- توقف/فعال‌سازی Watch Engine
- Health و آخرین چرخه پایش
- Broadcast به کاربران

## وضعیت Providerهای واقعی

| Provider | قطار | اتوبوس | نوع اتصال |
|---|---:|---:|---|
| Alibaba | ✅ | ✅ | قرارداد وب read-only |
| MrBilit | ✅ | ✅ | قرارداد وب read-only |
| Safar724 | — | ✅ | قرارداد وب read-only؛ Web Service رسمی هم با قرارداد ارائه می‌شود |
| Raja مستقیم | ⏳ | — | نیازمند دسترسی رسمی/پایدار؛ endpoint محافظت‌شده داخل محصول فعال نشده |

جزئیات endpointها، محدودیت‌ها و Feature Flagها در [Provider Status](docs/PROVIDERS.md) آمده است.

جزئیات:
- [معماری](docs/ARCHITECTURE.md)
- [نقشه راه](docs/ROADMAP.md)
- [استقرار و پایش](docs/OPERATIONS.md)

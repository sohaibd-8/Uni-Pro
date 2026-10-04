# Roadmap

## Phase 0 — Core MVP (اکنون)

- Telegram UX
- Watch creation
- Search now
- Train/Bus provider interface
- Price comparison
- Deduplicated polling
- One-stop alternative routes
- Admin panel
- Health endpoint
- Demo providers

## Phase 1 — اولین Pilot واقعی

هدف: 50 تا 200 دانشجو.

- اتصال حداقل یک Provider رسمی/قراردادی قطار
- اتصال حداقل یک Provider رسمی/قراردادی اتوبوس
- ثبت `provider_latency`, `provider_error_rate`, `search_success_rate`
- Deeplink واقعی خرید
- تشخیص دقیق `NOT_RELEASED` در Providerهایی که داده لازم را می‌دهند
- اصلاح تجربه فارسی و تقویم

**Go / No-Go Metrics**
- حداقل 25% کاربران ثبت Watch انجام دهند
- حداقل 10% کاربران طی 30 روز Watch دوم بسازند
- Alert → booking click بالاتر از 20%
- Provider error rate کمتر از 5% در ساعات عادی

## Phase 2 — Product Fit

- Price Drop Alert
- چند Watch هم‌زمان با فیلتر بودجه
- اعلان شروع پیش‌فروش
- انتخاب ساعت حرکت
- تعداد مسافر و نوع صندلی/کوپه
- attribution برای affiliate/referral
- Analytics funnel: Start → Watch → Found → Click

## Phase 3 — «هرجوری شده برسون من» واقعی

- Arrival Deadline
- چند وسیله در یک Route
- مسیرهای دو توقفه فقط در صورت نیاز
- Reliability score برای connectionها
- جلوگیری از connectionهای پرریسک
- Flight provider

## Phase 4 — UniPro Student Life

Travel فقط Feature #1 باقی می‌ماند و Home به Hub زندگی دانشجویی تبدیل می‌شود:

- خوابگاه
- تغذیه
- آموزش
- رفت‌وآمد شهری
- رویدادها
- کار دانشجویی
- فرصت آموزشی
- تخفیف دانشجویی

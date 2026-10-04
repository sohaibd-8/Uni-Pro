# Provider adapters

هر فروشنده یا منبع واقعی باید یک کلاس جدید بر پایه `TravelProvider` داشته باشد و فقط خروجی استاندارد `ProviderResult` تولید کند.

قواعد:
1. Core پروژه نباید endpoint اختصاصی یک فروشنده را بشناسد.
2. API key و secret فقط از Environment خوانده شوند.
3. Rate limit و retry در Adapter یا لایه Orchestrator مدیریت شود.
4. در صورت نبود API رسمی/قراردادی، scraping فقط پس از بررسی حقوقی و فنی و به‌عنوان fallback جداگانه اضافه شود؛ نه به Core.
5. `NOT_RELEASED` را فقط وقتی Provider واقعاً بتواند بین «فروش باز نشده» و «ظرفیت تمام شده» تمایز بگذارد برگردانید.

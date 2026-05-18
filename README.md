# مولّد ريلز القرآن الكريم — موقع ويب (Next.js)

موقع ويب يولّد فيديوهات قصيرة عمودية (1080x1920) لآيات من القرآن الكريم
بخلفية طبيعة + صوت تلاوة القارئ + النص العربي للآيات.

## البنية
```
.
├── app/
│   ├── page.tsx                         # الصفحة الرئيسية (RTL عربية)
│   ├── layout.tsx
│   ├── globals.css                      # ثيم أخضر/كريمي + خطوط Amiri / Noto Naskh
│   └── api/
│       ├── generate/route.ts            # بدء مهمة توليد
│       ├── status/[id]/route.ts         # الاستعلام عن حالة المهمة
│       └── video/[name]/route.ts        # تقديم الفيديو النهائي
├── components/
│   └── reels-generator.tsx              # واجهة الأداة (قارئ/سورة/نطاق آيات)
├── lib/
│   ├── quran-data.ts                    # قائمة القراء والسور
│   ├── jobs.ts                          # متجر مهام داخل الذاكرة
│   └── video-pipeline.ts                # خط الأنابيب: ffmpeg + ImageMagick
├── assets/fonts/Amiri-Regular.ttf       # (اختياري) خط عربي للنص
└── outputs/
    ├── video/                           # الفيديو النهائي
    ├── audio/                           # ملفات صوت الآيات (everyayah)
    ├── tmp_audio/                       # ملفات صوت مؤقتة (دمج)
    ├── tmp_frames/                      # صور النصوص PNG (ImageMagick)
    └── backgrounds/                     # فيديوهات الطبيعة .mp4
```

## المتطلبات على الجهاز
- Node.js 18+
- **FFmpeg** و **ffprobe** في PATH
- **ImageMagick** (`magick` أو `convert`) في PATH
- اتصال إنترنت (لـ everyayah.com و api.alquran.cloud)

## التشغيل
```bash
pnpm install
pnpm dev
```
ثم افتح: http://localhost:3000

## ملاحظات
- ضع فيديو/فيديوهات `.mp4` داخل `outputs/backgrounds/` لاستخدامها كخلفية. إن لم يوجد، يُولَّد تدرّج لوني احتياطياً.
- ضع `Amiri-Regular.ttf` داخل `assets/fonts/` لأفضل عرض للنص العربي.
- الحد الأقصى 30 آية لكل فيديو.

## مصادر البيانات
- **everyayah.com** — أصوات القراء (mp3 لكل آية).
- **api.alquran.cloud** — النص العربي العثماني.

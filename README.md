<div dir="rtl" align="center">

# 🚀 ربات پیام‌رسان مستقیم تلگرام

**ربات پیشرفته پیام‌رسان مستقیم — پل ارتباطی کاربران و ادمین**

<br>

[![Version](https://img.shields.io/badge/version-3.0.0-8A2BE2?style=for-the-badge&labelColor=1a1a2e)](https://github.com/mrVXBoT/the-messenger)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=1a1a2e)](https://python.org)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.x-00BFFF?style=for-the-badge&logo=telegram&logoColor=white&labelColor=1a1a2e)](https://docs.aiogram.dev)
[![License](https://img.shields.io/badge/license-MIT-32CD32?style=for-the-badge&labelColor=1a1a2e)](https://github.com/mrVXBoT/the-messenger/blob/main/LICENSE)

<br>

<img src="https://img.shields.io/badge/📨_پیام_رسان_مستقیم-FFD700?style=flat-square&labelColor=1a1a2e" width="300">

---

### 🔗 ارتباط با ما

[![Channel](https://img.shields.io/badge/📢_کانال_تلگرام-@l27__0-2CA5E0?style=flat-square&logo=telegram&logoColor=white)](https://t.me/l27_0)
[![Developer](https://img.shields.io/badge/👨‍💻_توسعه‌دهنده-@koxvx-FF69B4?style=flat-square&logo=telegram&logoColor=white)](https://t.me/koxvx)
[![GitHub](https://img.shields.io/badge/🐙_گیت‌هاب-mrVXBoT-181717?style=flat-square&logo=github&logoColor=white)](https://github.com/mrVXBoT/the-messenger)

<br>

</div>

---

<div dir="rtl">

## 📋 فهرست مطالب

- [✨ ویژگی‌ها](#-ویژگی‌ها)
- [📸 پیش‌نمایش](#-پیش‌نمایش)
- [⚙️ نصب و راه‌اندازی](#️-نصب-و-راه‌اندازی)
- [🛠️ تنظیمات](#️-تنظیمات)
- [🤖 دستورات و دکمه‌ها](#-دستورات-و-دکمه‌ها)
- [📊 آمار و قرعه‌کشی](#-آمار-و-قرعه‌کشی)
- [🔒 قابلیت‌های امنیتی](#-قابلیت‌های-امنیتی)
- [📜 لاگ و خطایابی](#-لاگ-و-خطایابی)
- [🧩 تکنولوژی‌های استفاده شده](#-تکنولوژی‌های-استفاده-شده)
- [🤝 مشارکت](#-مشارکت)

---

## ✨ ویژگی‌ها

<div align="right">

| ویژگی | توضیح |
|:---|---:|
| 📨 **پیام‌رسان مستقیم** | کاربران پیام می‌فرستند، ادمین دریافت می‌کند و پاسخ می‌دهد |
| 🔄 **سینک ویرایش** | ویرایش پاسخ توسط ادمین، خودکار به کاربر سینک می‌شود |
| 🚫 **سیستم مسدودسازی** | مسدودسازی کاربر با دلیل (اسپم، مزاحمت، دلخواه) |
| 🔒 **جوین اجباری** | کاربر باید در کانال‌های مشخصی عضو باشد |
| 🎁 **قرعه‌کشی** | انتخاب تصادفی برندگان از بین کاربران |
| 📊 **آمار پیشرفته** | آمار کاربران و پیام‌ها با نمودار میله‌ای |
| 📢 **ارسال همگانی** | ارسال پیام به همه کاربران یا کاربران فعال |
| 🔧 **حالت تعمیر** | غیرفعال کردن موقت ربات برای کاربران عادی |
| 🏷️ **پروفایل کاربری** | نمایش اطلاعات کاربر + آخرین پیام‌ها |
| 🔍 **جستجوی کاربر** | جستجو با آیدی، یوزرنیم یا نام |

</div>

---

## ⚙️ نصب و راه‌اندازی

### پیش‌نیازها

- Python 3.10+
- یک ربات تلگرام (از [@BotFather](https://t.me/BotFather) بسازید)

### مراحل نصب

```bash
# 1. کلون کردن مخزن
git clone https://github.com/mrVXBoT/the-messenger.git
cd the-messenger

# 2. نصب وابستگی‌ها
pip install -r requirements.txt

# 3. تنظیم توکن ربات
# فایل .env را باز کنید و توکن خود را قرار دهید:
echo "BOT_TOKEN=123456789:ABCdefGHIjklmNOPqrstUVwxyz" > .env

# 4. اجرای ربات
python bot.py
```

### تنظیم ادمین

ادمین‌ها به دو صورت تعیین می‌شوند:

1. **مقدار پیش‌فرض** — در کد (`ADMIN_IDS = [12345678]`)
2. **از طریق دیتابیس** — مقدار ذخیره شده در `xv_settings` با کلید `admin_ids`

> پس از اجرای اول، ادمین‌ها به صورت خودکار از دیتابیس بارگذاری می‌شوند.

---

## 🛠️ تنظیمات

### تنظیمات عمومی

از پنل ادمین می‌توانید تنظیمات زیر را مدیریت کنید:

| تنظیم | توضیح |
|:---|---:|
| 🔒 **جوین اجباری** | فعال/غیرفعال کردن عضویت اجباری در کانال‌ها |
| 📝 **متن خوش‌آمدید** | متنی که کاربر پس از عضویت می‌بیند |
| 📝 **متن جوین اجباری** | متنی که هنگام جوین اجباری نمایش داده می‌شود |
| 🚫 **متن بن** | پیامی که به کاربر مسدود شده نمایش داده می‌شود |
| 🔧 **حالت تعمیر** | غیرفعال کردن ربات برای کاربران عادی |
| 📝 **متن تعمیر** | پیام حالت تعمیر |

> 💡 **نکته:** برای بازگشت به متن پیش‌فرض، کافیست در هنگام ویرایش، متن خالی ارسال کنید.

---

## 🤖 دستورات و دکمه‌ها

### منوی کاربری

| دکمه | عملکرد |
|:---|---:|
| 👤 **پروفایل من** | نمایش اطلاعات حساب کاربری |
| ✉️ **ارسال پیام** | ارسال پیام مستقیم به ادمین |

### پنل مدیریت

| دکمه | عملکرد |
|:---|---:|
| 👥 **مدیریت کاربران** | لیست کاربران، جستجو، مسدودسازی |
| 📢 **ارسال همگانی** | ارسال پیام به همه یا کاربران فعال |
| 🎁 **قرعه‌کشی** | انتخاب تصادفی برندگان |
| 📊 **آمار** | مشاهده آمار کاربران و پیام‌ها |
| ⚙️ **تنظیمات** | مدیریت تنظیمات ربات |

### وضعیت پیام‌ها

| آیکون | وضعیت | توضیح |
|:---:|:---:|:---|
| 🔴 | **ارسال شد** | پیام توسط کاربر ارسال شده |
| 👀 | **خوانده شد** | ادمین پیام را مشاهده کرده (۰.۸ ثانیه تأخیر) |
| 💬 | **پاسخ داده شد** | ادمین به پیام پاسخ داده |

---

## 📊 آمار و قرعه‌کشی

### آمار پیشرفته

- تعداد کل کاربران
- کاربران جدید امروز / این هفته / این ماه
- تعداد پیام‌های امروز / این هفته / این ماه
- **نمایش بصری با میله‌های پیشرفت** 📊

### قرعه‌کشی

- انتخاب تصادفی برندگان از بین کاربران
- امکان انتخاب تعداد برندگان
- ارسال پیام تبریک به برندگان

---

## 🔒 قابلیت‌های امنیتی

| ویژگی | توضیح |
|:---|---:|
| 🛡️ **حفاظت ادمین** | ادمین نمی‌تواند خودش را مسدود کند |
| 🔐 **حالت تعمیر** | کاربران عادی نمی‌توانند از ربات استفاده کنند |
| 🚫 **سیستم بن هوشمند** | بن شدن ادمین → خودکار آنبن در استارت بعدی |
| 📝 **HTML Escaping** | جلوگیری از XSS در پیام‌های کاربران |
| ⏱️ **Rate Limiting** | محدودیت نرخ ارسال همگانی |
| 🔄 **Retry on 429** | تلاش مجدد در صورت محدودیت تلگرام |
| 🔗 **جوین اجباری** | کاربر باید در کانال‌ها عضو باشد |
| ⚡ **Race Condition Fix** | مدیریت هم‌زمانی در مدیا گروه‌ها |

---

## 📜 لاگ و خطایابی

ربات از ماژول استاندارد `logging` استفاده می‌کند:

```python
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
```

سطوح لاگ:
- `INFO` — لاگ عادی فعالیت‌ها
- `WARNING` — هشدارها (مانند خطا در بررسی جوین)
- `ERROR` — خطاهای جدی

---

## 🧩 تکنولوژی‌های استفاده شده

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Aiogram-3.x-00BFFF?style=for-the-badge&logo=telegram&logoColor=white" alt="Aiogram">
  <img src="https://img.shields.io/badge/AioSQLite-0.19+-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="AioSQLite">
  <img src="https://img.shields.io/badge/Redis-5.0+-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis">
</p>

---

## 🤝 مشارکت

اگر ایده‌ای برای بهبود ربات دارید، خوشحال می‌شویم کمک کنید:

1. **Fork** کنید 🍴
2. یک **برنچ جدید** بسازید (`git checkout -b feature/awesome`)
3. **Commit** کنید (`git commit -m 'Add awesome feature'`)
4. **Push** کنید (`git push origin feature/awesome`)
5. یک **Pull Request** ثبت کنید 🎉

---

<div align="center">

**🌟 اگر از این پروژه خوشتان آمد، ستاره‌اش کنید! 🌟**

<br>

[![GitHub stars](https://img.shields.io/github/stars/mrVXBoT/the-messenger?style=social)](https://github.com/mrVXBoT/the-messenger)
[![GitHub forks](https://img.shields.io/github/forks/mrVXBoT/the-messenger?style=social)](https://github.com/mrVXBoT/the-messenger)

---

**توسعه یافته با ❤️ توسط [@koxvx](https://t.me/koxvx)**  

</div>

</div>

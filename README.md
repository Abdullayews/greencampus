# 🟢 GreenCampus

> Kampus həyatını bir panelə yığan tələbə portalı — ərizələr, yeməkxana, camaşırxana, bildirişlər və AI köməkçi, hamısı bir yerdə.

![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask&logoColor=white)
![MySQL](https://img.shields.io/badge/Database-TiDB%20Cloud-4479A1?logo=mysql&logoColor=white)
![Deploy](https://img.shields.io/badge/Hosted%20on-Render-46E3B7?logo=render&logoColor=white)

---

## ✨ Nə edir?

| | |
|---|---|
| 🔐 **Auth** | Sessiya əsaslı tələbə girişi/çıxışı |
| 🏠 **Dashboard** | Ümumi kampus icmalı |
| 📝 **Ərizələr** | Göndər, yenilə, sil, izlə |
| 🍽️ **Yeməkxana** | Həftəlik menyu |
| 📢 **Elanlar & sorğular** | Kampus xəbərləri |
| 🧺 **Camaşırxana** | Maşınların anlıq statusu |
| 🔔 **Bildirişlər** | Tələbəyə xüsusi axın |
| 💸 **Cərimələr** | Görüntülə |
| 👤 **Profil** | Məlumat + AI API açarı idarəsi |
| 🏘️ **Otaq yoldaşları** | Kim kiminlə eyni otaqdadır |
| 🤖 **AI köməkçi** | Şəxsi API açarı ilə işləyən sorğu-cavab |

## 🛠️ Stack

**Backend:** Python · Flask
**Database:** MySQL-uyğun (TiDB Cloud üzərində, SSL bağlantı, `PyMySQL`)
**Server:** Gunicorn (`Procfile`) / Passenger WSGI (cPanel üçün)
**Deploy:** Render + GitHub

## 📁 Struktur

```
greencampus/
├── app.py                  # Flask app + route qeydiyyatı
├── config.py                # DB bağlantısı (PyMySQL, SSL)
├── index_route.py           # Ana səhifə render
├── ai_handler.py            # AI köməkçi endpoint-i
├── login.py / logout.py     # Autentifikasiya
├── get_*.py                 # Oxuma (GET) endpoint-ləri
├── submit_application.py    # Ərizə yaratma (POST)
├── update_*.py               # Yeniləmə endpoint-ləri (POST)
├── delete_application.py    # Ərizə silmə (POST)
├── templates/index.html      # Frontend
├── requirements.txt
├── Procfile
└── passenger_wsgi.py         # cPanel/Passenger giriş nöqtəsi
```

## 🔑 Environment

Bütün DB dəyərləri env variable-lardan oxunur — kodda heç bir credential yoxdur:

| Dəyişən | Təsvir |
|---|---|
| `DB_HOST` | MySQL host |
| `DB_PORT` | Port (default `4000`, TiDB Cloud) |
| `DB_NAME` | Baza adı |
| `DB_USER` | İstifadəçi |
| `DB_PASSWORD` | Şifrə |

Bağlantı default olaraq SSL üzərindən qurulur.

## 🌐 API marşrutları

Frontend-in mövcud `fetch()` çağırışları ilə uyğunluq üçün `.php` adlandırması saxlanılıb.

| Method | Route | |
|---|---|---|
| GET | `/` | Ana səhifə |
| POST | `/login.php` | Giriş |
| GET | `/logout.php` | Çıxış |
| GET | `/get_home.php` | Dashboard datası |
| GET | `/get_applications.php` | Ərizə siyahısı |
| GET | `/get_canteen.php` | Yeməkxana menyusu |
| GET | `/get_contents.php` | Elan/sorğu siyahısı |
| GET | `/get_laundry.php` | Camaşırxana statusu |
| GET | `/get_notifications.php` | Bildirişlər |
| GET | `/get_penalties.php` | Cərimələr |
| GET | `/get_profile.php` | Profil |
| GET | `/get_roommates.php` | Otaq yoldaşları |
| POST | `/submit_application.php` | Ərizə yarat |
| POST | `/update_application.php` | Ərizə yenilə |
| POST | `/delete_application.php` | Ərizə sil |
| POST | `/update_profile.php` | Profil yenilə |
| POST | `/update_api_key.php` | AI API açarını yenilə |
| POST | `/ai_handler.php` | AI köməkçi sorğusu |

## 🔗 Bağlı repo

Admin tərəfi: **[greencampusadmin →](https://github.com/Abdullayews/greencampusadmin)**

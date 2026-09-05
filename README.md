# 🟢 GreenCampus

> Kampus həyatını bir panelə yığan tələbə portalı — ev seçmə planı, qruplar, ərizələr, yeməkxana, camaşırxana, tələb sistemi, bildirişlər və AI köməkçi, hamısı bir yerdə.

![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-000000?logo=flask&logoColor=white)
![MySQL](https://img.shields.io/badge/Database-TiDB%20Cloud-4479A1?logo=mysql&logoColor=white)
![Deploy](https://img.shields.io/badge/Hosted%20on-Render-46E3B7?logo=render&logoColor=white)

---

## ✨ Nə edir?

| | |
|---|---|
| 🔐 **Auth** | Sessiya əsaslı giriş/çıxış — **avtomatik çıxış yoxdur** (daimi sessiya) |
| 🏠 **Dashboard** | Ümumi kampus icmalı |
| 🚪 **Mənim evim** | 3 hal: *Ev seçilib* → otaq yoldaşları + inventar; *Ev seçilməyib* → ev seçmə planı; *Rədd edilib* → "Siz yataqxanada yaşamırsınız" |
| 🗺️ **Ev seçmə planı** | 60/40 layout — solda evlər **grid** formatda (4 sütun), sağda tələbə axtarışı (SQL filtrləri: ad/ixtisas/kurs) + qruplar |
| 👥 **Qruplar** | Ev birlikdə seçmək üçün — maksimum 6 üzv, canlı sıra nömrələri (1, 2, 3...), boşalan qrup avtomatik silinir |
| ⚧ **Cins ayrılığı** | Oğlan binası: evlər **101–120**, qız binası: **121–140** — hər cins yalnız öz binasını görür |
| 📨 **Dəvət sistemi** | Otaq Yoldaşı Axtar → "Dəvət et" → qarşı tərəf "Tələblər"də Qəbul/Rədd edir |
| 🗳️ **Qovma / Çıxma + səsvermə** | Ev sakinləri hər kəsi səsvermə ilə qova/çıxara bilər; tək olanda avtomatik çıxış |
| 🔔 **Bildirişlər** | Elan/anket/cərimə/**Tələb** sayları — sayı 0 olanlar avtomatik gizlənir |
| 📝 **Ərizələr** | Göndər, yenilə, sil, izlə — təsdiqlənəndə **notlar** sahəsi avtomatik yaranır |
| 🍽️ **Yeməkxana** | Həftəlik menyu (Yataqxana / Universitet) |
| 🧺 **Camaşırxana** | Maşınların anlıq statusu |
| 💸 **Cərimələr** | Görüntülə |
| 👤 **Profil** | Məlumat + xarakteristikalar + şəxsi AI API açarı |
| 🤖 **AI köməkçi** | Şəxsi Gemini API açarı ilə chat + otaq yoldaşı uyğunluq faizi |

## 🛠️ Stack

**Backend:** Python · Flask
**Database:** MySQL-uyğun (TiDB Cloud, SSL, `PyMySQL`) — normalizə edilmiş sxem, indekslənmiş axtarış
**Server:** Gunicorn (`Procfile`)
**Deploy:** Render + GitHub

## 📁 Struktur

```
greencampus/
├── app.py                  # Flask app + bütün route-lar
├── config.py                # DB bağlantısı (PyMySQL, SSL)
├── templates/index.html     # Frontend (tək səhifə, SPA tipli)
├── requirements.txt
└── Procfile
```

## 🔑 Environment

Bütün dəyərlər env variable-lardan oxunur:

| Dəyişən | Təsvir |
|---|---|
| `DB_HOST` | MySQL host |
| `DB_PORT` | Port (default `4000`) |
| `DB_NAME` | Baza adı |
| `DB_USER` | İstifadəçi |
| `DB_PASSWORD` | Şifrə |
| `SECRET_KEY` | Session açarı — **dəyişməz olmalıdır** (deploy-lar arası sessiyalar qorunur; fallback: `secret_key.txt`) |

## 🗄️ Verilənlər bazası sxemi

| Cədvəl | Sütunlar | Qeyd |
|---|---|---|
| `students` | id, ad_soyad, email (unique), sifre, universitet, ixtisas, kurs, ev_deyisme_isteyi, api_key, **cins**, **ev**, **group_id** | `ev`: Ev seçilib / Ev seçilməyib / Rədd edilib |
| `students_profiles` | student_id (PK), yuxu_rejimi, temizlik, sosial_munasibet, hayat_terzi | AI uyğunluq hesabı üçün |
| `rooms` | id, capacity, **cins** | 101–120 Kişi, 121–140 Qadın binası |
| `room_slots` | (room_id, slot) PK, student_id (unique), yataq/skaf/oturacaq_status | Normalizə: 1 sətir = 1 yataq yeri |
| `student_groups` | id (AI), created_at | Qrup ləğvi: boşalandə avtomatik |
| `home_requests` | id, type (invite/kick/leave), room_id, target_id, requester_id, status, created_at | Tələb sistemi |
| `home_request_votes` | (request_id, voter_id) PK, vote | Səsvermə — hamı təsdiq → icra, 1 rədd → bağlanır |
| `applications` | id, student_id, basliq, muraciet, priority, status, **notlar**, created_at | |
| `contents` | id, type (announcement/survey), title, description, priority, status, created_at | |
| `canteen_menu` | id, location, day_of_week, meal_name | |
| `laundry` | student_id (PK), machine_1-3_status | |
| `penalties` | id, student_id, amount, reason, status, created_at | |

## 🌐 API marşrutları

| Method | Route | |
|---|---|---|
| GET | `/` | Ana səhifə |
| POST | `/login` | Giriş |
| GET | `/logout` | Çıxış |
| GET | `/get_home` | Mənim evim (3 hal + plan datası) |
| GET | `/get_applications` | Ərizələr (+ avtomatik notlar) |
| GET | `/get_canteen` | Yeməkxana |
| GET | `/get_contents` | Elanlar və anketlər |
| GET | `/get_laundry` | Camaşırxana |
| GET | `/get_notifications` | Bildirişlər (+ Tələb sayı) |
| GET | `/get_penalties` | Cərimələr |
| GET | `/get_profile` | Profil |
| GET | `/get_roommates` | Otaq yoldaşı axtarışı (cins filtri) |
| GET | `/get_available_rooms` | Evlər (cins + self-heal slotlar) |
| GET | `/search_students` | Plan axtarışı (SQL filtrləri) |
| GET | `/get_groups` | Qruplar (canlı nömrələmə) |
| GET | `/get_requests` | Tələblər (dəvət/qovma/çıxma) |
| POST | `/submit_application` | Ərizə yarat |
| POST | `/update_application` | Ərizə yenilə |
| POST | `/delete_application` | Ərizə sil |
| POST | `/update_profile` | Profil yenilə |
| POST | `/update_api_key` | AI açarı yenilə |
| POST | `/create_group` | Qrup yarat |
| POST | `/join_group` | Qrupa qoşul |
| POST | `/leave_group` | Qrupdan çıx |
| POST | `/add_group_member` | Üzv əlavə et |
| POST | `/select_home` | Ev seç (qrupla birlikdə) |
| POST | `/invite_roommate` | Evə dəvət et |
| POST | `/respond_invite` | Dəvətə cavab |
| POST | `/request_kick` | Qovma tələbi |
| POST | `/request_leave` | Evdən çıxma tələbi |
| POST | `/vote_request` | Tələbə səs ver |
| POST | `/ai_handler` | AI chat / uyğunluq |

## 🔗 Bağlı repo

Admin tərəfi: **[greencampusadmin →](https://github.com/Abdullayews/greencampusadmin)**

<div align="center">

# 🟢 GreenCampus

**One dashboard for the entire campus life.**

*Home-picking plans · roommate groups · applications · canteen · laundry · penalties · notifications · AI assistant*

[![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![Database](https://img.shields.io/badge/DB-TiDB_Cloud-4479A1?style=for-the-badge&logo=mysql&logoColor=white)](https://tidbcloud.com)
[![Server](https://img.shields.io/badge/WSGI-Gunicorn-499848?style=for-the-badge&logo=gunicorn&logoColor=white)](https://gunicorn.org)
[![Deploy](https://img.shields.io/badge/Hosted_on-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://render.com)

[Admin panel → greencampusadmin](https://github.com/Abdullayews/greencampusadmin)

</div>

---

## 🧭 What is this?

GreenCampus is a **student portal for dormitory life**. Instead of ten notice boards, five group chats and one lost paper list, everything a student needs lives behind a single login:

- pick a home (room) on an interactive floor plan,
- form a **roommate group** of up to 6 people and choose the home together,
- send, update and track **applications** to the administration,
- check the weekly **canteen menu** and live **laundry machine** status,
- keep an eye on **penalties** and **notifications**,
- chat with a **personal AI assistant** powered by your own Gemini API key.

The whole app is a single-page Flask application backed by a **normalized, MySQL-compatible schema on TiDB Cloud** (SSL, PyMySQL), with self-healing room slots and a **vote-based system** for inviting, kicking or leaving homes.

> 🛠️ Running the campus from the other side? Check out **[GreenCampus Admin](https://github.com/Abdullayews/greencampusadmin)** — the administrative panel that reads and manages the *same* database.

## ✨ Features

| | |
|---|---|
| 🔐 **Auth** | Session-based login / logout — **no auto-logout** (sessions persist) |
| 🏠 **Dashboard** | Campus overview at a glance |
| 🚪 **My Home — 3 states** | *Home selected* → roommates + inventory; *not selected* → home-picking plan; *rejected* → "you don't live in the dorm" |
| 🗺️ **Home-picking plan** | 60/40 layout — homes in a 4-column **grid** on the left, student search (SQL filters: name / major / course) + groups on the right |
| 👥 **Groups** | Pick a home together — max **6 members**, live queue numbers (1, 2, 3…), empty groups auto-delete |
| ⚧ **Gender separation** | Boys building: rooms **101–120**, girls building: **121–140** — each gender only ever sees its own building |
| 📨 **Invite system** | Find a roommate → *Invite* → they accept or reject it under *Requests* |
| 🗳️ **Kick / leave + voting** | Residents vote on every kick/leave request — everyone approves → executed, one reject → closed; last resident leaves automatically |
| 🔔 **Notifications** | Announcement / survey / penalty / request counters — anything at 0 is auto-hidden |
| 📝 **Applications** | Create, update, delete, track — a **notes** field appears automatically once approved |
| 🍽️ **Canteen** | Weekly menu for both locations (Dormitory / University) |
| 🧺 **Laundry** | Live per-machine status |
| 💸 **Penalties** | All your fines, in one place |
| 👤 **Profile** | Personal info + lifestyle characteristics + your private AI API key |
| 🤖 **AI assistant** | Chat via your own **Gemini API key** + roommate **compatibility score** computed from lifestyle profiles |

## 🛠️ Tech stack

| Layer | Technology |
|---|---|
| Backend | Python · **Flask** |
| Database | MySQL-compatible **TiDB Cloud** — SSL, `PyMySQL`, normalized schema, indexed search |
| Server | **Gunicorn** (`Procfile`) |
| Deploy | **Render** + GitHub |

## 📁 Repository structure

```
greencampus/
├── app.py                  # Flask app + all 31 routes (~1.5k lines)
├── config.py               # DB connection (PyMySQL, SSL)
├── templates/
│   └── index.html          # Frontend — one page, SPA-style
├── requirements.txt
└── Procfile                # gunicorn entrypoint for Render
```

## 🔑 Environment variables

Everything is read from the environment — **no credentials in code**:

| Variable | Description |
|---|---|
| `DB_HOST` | MySQL / TiDB host |
| `DB_PORT` | Port (default `4000`) |
| `DB_NAME` | Database name |
| `DB_USER` | Database user |
| `DB_PASSWORD` | Database password |
| `DB_SSL` | SSL connection (default `true`) |
| `SECRET_KEY` | Session key — **must stay the same across deploys** (sessions survive; fallback: `secret_key.txt`) |

## 🗄️ Database schema

| Table | Columns | Notes |
|---|---|---|
| `students` | id, ad_soyad, email *(unique)*, sifre, universitet, ixtisas, kurs, ev_deyisme_isteyi, api_key, **cins**, **ev**, **group_id** | `ev`: selected / not selected / rejected |
| `students_profiles` | student_id *(PK)*, yuxu_rejimi, temizlik, sosial_munasibet, hayat_terzi | feeds the AI compatibility score |
| `rooms` | id, capacity, **cins** | 101–120 boys, 121–140 girls |
| `room_slots` | (room_id, slot) PK, student_id *(unique)*, bed / locker / chair status | normalized: 1 row = 1 bed slot |
| `student_groups` | id *(AI)*, created_at | auto-deleted when empty |
| `home_requests` | id, type *(invite / kick / leave)*, room_id, target_id, requester_id, status, created_at | the request system |
| `home_request_votes` | (request_id, voter_id) PK, vote | all approve → execute · 1 reject → closed |
| `applications` | id, student_id, basliq, muraciet, priority, status, **notlar**, created_at | |
| `contents` | id, type *(announcement / survey)*, title, description, priority, status, created_at | |
| `canteen_menu` | id, location, day_of_week, meal_name | |
| `laundry` | student_id *(PK)*, machine_1–3_status | |
| `penalties` | id, student_id, amount, reason, status, created_at | |

## 🌐 API routes — all 31

**Session**

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | Main page |
| POST | `/login` | Sign in |
| GET | `/logout` | Sign out |

**Home & floor plan**

| Method | Route | Purpose |
|---|---|---|
| GET | `/get_home` | "My Home" — all 3 states + plan data |
| GET | `/get_available_rooms` | Rooms (gender filter + self-healing slots) |
| POST | `/select_home` | Select a home (together with your group) |
| GET | `/search_students` | Plan search (SQL filters) |
| GET | `/get_roommates` | Roommate search (gender filter) |

**Groups**

| Method | Route | Purpose |
|---|---|---|
| GET | `/get_groups` | Groups with live queue numbers |
| POST | `/create_group` | Create a group |
| POST | `/join_group` | Join a group |
| POST | `/leave_group` | Leave a group |
| POST | `/add_group_member` | Add a member |

**Requests & voting**

| Method | Route | Purpose |
|---|---|---|
| GET | `/get_requests` | Invite / kick / leave requests |
| POST | `/invite_roommate` | Invite someone to your home |
| POST | `/respond_invite` | Accept / reject an invite |
| POST | `/request_kick` | Request a resident's removal |
| POST | `/request_leave` | Request to leave the home |
| POST | `/vote_request` | Vote on an active request |

**Applications, content & services**

| Method | Route | Purpose |
|---|---|---|
| GET | `/get_applications` | Applications (+ auto notes) |
| POST | `/submit_application` | Create an application |
| POST | `/update_application` | Update an application |
| POST | `/delete_application` | Delete an application |
| GET | `/get_contents` | Announcements & surveys |
| GET | `/get_canteen` | Canteen menu |
| GET | `/get_laundry` | Laundry status |
| GET | `/get_penalties` | Penalties |
| GET | `/get_notifications` | Notifications (+ request counter) |
| GET | `/get_profile` | Profile |
| POST | `/update_profile` | Update profile |
| POST | `/ai_handler` | AI assistant chat (Gemini) |

## 🚀 Installation

```bash
git clone https://github.com/Abdullayews/greencampus.git
cd greencampus

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# point it at your database
export DB_HOST="..."
export DB_NAME="..."
export DB_USER="..."
export DB_PASSWORD="..."
export SECRET_KEY="$(openssl rand -hex 32)"

python app.py          # dev server
# or: gunicorn app:app  # production
```

The schema is expected on a MySQL-compatible server — create the tables
listed above (or run the sibling admin panel once, which initializes the
same database).

## 📄 License

Personal / educational project — built to make one real campus run smoother.


## 👤 Author

**Muhəmməd Abdullayev** — Computer Engineering student · Qarabağ University & Holberton School

<p>
<a href="https://github.com/Abdullayews"><img src="https://img.shields.io/badge/GitHub-@Abdullayews-181717?style=flat-square&logo=github&logoColor=white" alt="GitHub"></a>
<a href="https://t.me/arasss08"><img src="https://img.shields.io/badge/Telegram-@arasss08-26A5E4?style=flat-square&logo=telegram&logoColor=white" alt="Telegram"></a>
<a href="mailto:08abdullayevv@gmail.com"><img src="https://img.shields.io/badge/Email-08abdullayevv@gmail.com-EA4335?style=flat-square&logo=gmail&logoColor=white" alt="Email"></a>
</p>

> 🇦🇿 Bu layihə Azərbaycan tələbə həyatı üçün hazırlanıb — *GreenCampus — kampus həyatı bir panelə yığılır.*

# Community Watch

A small community safety platform for a hackathon demo.

- **Frontend:** plain HTML, CSS and JavaScript. No React, no build step.
- **Backend:** Python FastAPI with a simple SQLite database.
- **WhatsApp:** official Meta WhatsApp Cloud API webhook.
- **AI:** OpenRouter extracts the incident type, location and summary from free text.
- **Voice:** ElevenLabs transcribes WhatsApp voice notes. No local Whisper model.

The original React project was not changed. This simplified version lives in
`C:\Users\HP\Desktop\Community Watch`.

## What it does

1. A resident sends a WhatsApp message such as:
   `Fire behind Mokolo market, smoke from a shop, 20 minutes ago.`
2. The webhook receives the message and the bot extracts the incident details.
3. The report is saved and appears on the dashboard.
4. The bot asks for the area if no location was found.
5. Verified quarter heads whose quarter or city matches the report receive a WhatsApp alert.
6. Dashboard operators can change status, pin a location, verify quarter heads or delete demo data.

The bot also handles:

- Greetings, help and thanks
- `register as quarter head` registration through WhatsApp
- WhatsApp location messages
- Voice notes through ElevenLabs
- AI failures with a keyword-based fallback, so reporting still works

## Folder map

```
Community Watch/
├── backend/
│   ├── main.py          FastAPI routes and WhatsApp webhook
│   ├── bot.py           WhatsApp conversation logic and notifications
│   ├── ai.py            OpenRouter extraction and ElevenLabs transcription
│   ├── db.py            SQLite tables and queries
│   ├── config.py        Reads backend/.env
│   ├── seed_demo.py     Optional sample reports and quarter heads
│   ├── requirements.txt
│   └── .env             Your private credentials
├── frontend/
│   ├── index.html       Dashboard markup
│   ├── style.css        Responsive styling
│   └── app.js           Calls the API and renders the dashboard
└── README.md
```

## Quick start

### 1. Start the backend

Open a terminal in the backend folder:

```powershell
cd "C:\Users\HP\Desktop\Community Watch\backend"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The dashboard and API are now both available from the backend:

- Dashboard: `http://localhost:8000`
- API documentation: `http://localhost:8000/docs`

A `.env` file was copied from the previous project so the existing WhatsApp,
OpenRouter and ElevenLabs credentials can be reused. **Never commit `.env`.**
If you move the project, copy `.env.example` to `.env` and fill in the values.

### 2. Optional: serve the frontend separately

You do not need this step. It is useful if you want to study the frontend
without touching the backend:

```powershell
cd "C:\Users\HP\Desktop\Community Watch\frontend"
python -m http.server 5500
```

Open `http://localhost:5500`. `app.js` automatically points to
`http://localhost:8000/api` on port 5500. When the page is served by the backend
(or by Render), it automatically uses `/api`.

### 3. Optional demo data

If the dashboard is empty before the WhatsApp demo:

```powershell
cd "C:\Users\HP\Desktop\Community Watch\backend"
.\.venv\Scripts\activate
python seed_demo.py
```

The script only adds data when the database has no reports.

## Deploy on Render

We deploy one web service. It runs the FastAPI backend and serves the plain
frontend from the same URL. There is no Blueprint or `render.yaml`; all settings
are entered in the Render dashboard.

### Before deploying

Push the latest code to GitHub:

```powershell
cd "C:\Users\HP\Desktop\Community Watch"
git add .
git commit -m "Update project"
git push
```

### Create the Render web service

1. Sign in to [render.com](https://render.com).
2. Click **New > Web Service**.
3. Connect your GitHub account and select
   `Emmanuel-Praise/Community-Watch`.
4. Fill in the form:
   - **Name:** `community-watch`
   - **Region:** closest to you
   - **Branch:** `main`
   - **Root Directory:** `backend`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** Free
5. Open **Advanced** and set:
   - **Health Check Path:** `/api/health`
6. Click **Create Web Service**.

Render installs the packages and starts the server. The first deploy takes a
few minutes.

### Add environment variables

In the service, open **Environment** and add:

| Key | Value |
| --- | --- |
| `PYTHON_VERSION` | `3.11.11` |
| `BOT_NAME` | `Community Watch` |
| `CORS_ALLOW_ALL` | `true` |
| `WHATSAPP_VERIFY_TOKEN` | any secret phrase you choose |
| `WHATSAPP_ACCESS_TOKEN` | from Meta |
| `WHATSAPP_PHONE_NUMBER_ID` | from Meta |
| `WHATSAPP_APP_SECRET` | optional, from Meta |
| `OPENROUTER_API_KEY` | your OpenRouter key |
| `OPENROUTER_MODEL` | `openrouter/auto` |
| `ELEVENLABS_API_KEY` | your ElevenLabs key |
| `ELEVENLABS_STT_MODEL` | `scribe_v2` |

Click **Save Changes**. Render redeploys automatically.

### Test the deployment

Open these URLs, replacing `YOUR-SERVICE` with your Render subdomain:

- Dashboard: `https://YOUR-SERVICE.onrender.com`
- Health check: `https://YOUR-SERVICE.onrender.com/api/health`
- API docs: `https://YOUR-SERVICE.onrender.com/docs`

### Connect WhatsApp

In Meta's WhatsApp webhook settings, use:

```
https://YOUR-SERVICE.onrender.com/api/whatsapp/webhook
```

Enter the same `WHATSAPP_VERIFY_TOKEN` in Meta, subscribe to the `messages`
field, then send a test WhatsApp message from an allowed number.

### Important Render notes

- The free plan sleeps after inactivity. The first request after a break can
  take 30-60 seconds.
- The free plan has no persistent disk, so the SQLite database is deleted when
  the service restarts or redeploys. For a demo this is usually fine: run
  `python seed_demo.py` in the Render Shell, or send a new WhatsApp report.
- For persistent data, add a Render Disk mounted at `/var/data` and set
  `DATABASE_PATH` to `/var/data/community_watch.db`.
- The frontend automatically calls `/api` on Render, so no URL editing is
  needed.
- Push a new commit to GitHub to redeploy the latest code.

## WhatsApp Cloud API setup

The Meta setup is done in the Meta developer dashboard. The short version:

1. Create a Meta developer app and add the **WhatsApp** product.
2. Open **WhatsApp > API Setup**.
3. Copy the **Phone number ID** and the **access token** into `backend/.env`:

   ```env
   WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
   WHATSAPP_ACCESS_TOKEN=your_access_token
   WHATSAPP_VERIFY_TOKEN=the_phrase_you_choose
   ```

4. Restart `uvicorn` after changing `.env`.
5. Expose your local backend with a public HTTPS URL:

   ```powershell
   ngrok http 8000
   ```

6. In the Meta dashboard, set the webhook callback URL to:

   ```
   https://YOUR-NGROK-URL/api/whatsapp/webhook
   ```

7. Enter the same verify token that is in `.env`.
8. Subscribe the app to the `messages` webhook field.
9. Add the phone numbers you will test with to the allowed recipient list.
10. Send a WhatsApp message to the test business number.

### Check the webhook

Open this in a browser:

```
http://localhost:8000/api/whatsapp/webhook
```

You should see a small JSON status page. Meta verification uses:

```
/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=123
```

When the token matches, the response body is exactly `123`.

### Important WhatsApp notes

- A Meta **temporary access token expires**, often within 24 hours. Replace it
  before the demo or use a permanent/system-user token.
- Free-form replies are allowed inside the 24-hour customer service window,
  which starts when the user messages your business. For the hackathon demo,
  have the user send the first message.
- The recipient test number must be added in the Meta dashboard.
- If `WHATSAPP_APP_SECRET` is set, the backend verifies
  `X-Hub-Signature-256` on every webhook POST. If it is empty, signature
  checking is disabled for local development.

## AI and voice

### OpenRouter

`OPENROUTER_API_KEY` enables incident extraction. The model is asked to return
JSON only. If the key is missing, the request fails, or the JSON is invalid, the
backend uses keyword rules and marks the report with `ai_processed = false`.
Reports are still saved and routed.

Relevant variables:

```env
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openrouter/auto
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

### ElevenLabs

`ELEVENLABS_API_KEY` enables voice-note transcription. The backend downloads the
audio from Meta and sends it to the ElevenLabs speech-to-text endpoint. If the
key is missing, the bot asks the sender to type instead.

Relevant variables:

```env
ELEVENLABS_API_KEY=
ELEVENLABS_STT_MODEL=scribe_v2
```

## API overview

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Backend and integration status |
| GET | `/api/stats` | Dashboard counters |
| GET | `/api/reports` | List or filter reports |
| POST | `/api/reports` | Create a manual report |
| GET | `/api/reports/{id}` | Read one report |
| PATCH | `/api/reports/{id}/status` | Change report status |
| PATCH | `/api/reports/{id}/location` | Save coordinates |
| DELETE | `/api/reports/{id}` | Delete a report |
| GET | `/api/reports/{id}/matching-heads` | Preview routing |
| GET | `/api/quarter-heads` | List quarter heads |
| POST | `/api/quarter-heads` | Register a quarter head |
| PATCH | `/api/quarter-heads/{id}/status` | Verify or reject a head |
| GET | `/api/whatsapp/webhook` | Meta verification handshake |
| POST | `/api/whatsapp/webhook` | Receive WhatsApp events |
| GET | `/api/whatsapp/status` | Safe integration status for the dashboard |

## How routing works

A report matches a quarter head with simple text matching:

- The report's area text is its `location_name`, description and AI summary.
- A verified head matches when their quarter name appears in that text, or the
  text appears in their quarter name.
- The city is used as a fallback match.
- At most 10 heads are notified per report.
- The reporter is skipped when notifications are sent.

This intentionally avoids maps, PostGIS and complex geo calculations.

## Plain-language guide for the team

- **Frontend:** the files the browser displays. `app.js` calls the backend with
  `fetch()` and writes the results into the page.
- **Backend:** the Python program that stores data and answers API requests.
- **API:** a set of URLs the frontend calls, such as `/api/reports`.
- **Webhook:** a URL Meta calls automatically when a WhatsApp message arrives.
- **SQLite:** a small database stored in one file, `community_watch.db`.
- **AI extraction:** turning a sentence into fields such as type, priority and
  location.
- **Quarter head:** a local area leader who receives reports for their area.
- **Routing:** choosing which quarter heads should receive a report.

### Where to change things

| I want to... | File |
| --- | --- |
| Change dashboard layout or text | `frontend/index.html` |
| Change colors or spacing | `frontend/style.css` |
| Change dashboard behavior | `frontend/app.js` |
| Add or change API endpoints | `backend/main.py` |
| Change bot replies or conversation flow | `backend/bot.py` |
| Change AI prompt or voice call | `backend/ai.py` |
| Change the database fields | `backend/db.py` |
| Change environment variable names | `backend/config.py` |

### Useful database commands

The database is created automatically. To reset it:

```powershell
cd "C:\Users\HP\Desktop\Community Watch\backend"
Remove-Item community_watch.db
uvicorn main:app --reload --port 8000
python seed_demo.py
```

## Privacy and security

- Reports store a SHA-256 hash of the reporter's WhatsApp number, not the raw number.
- Quarter-head numbers are stored because they are needed to send alerts.
- The quarter-head list in the dashboard shows only the last three digits.
- There is no dashboard login. This is a hackathon demo, not a production system.
- `CORS_ALLOW_ALL=true` is convenient locally. Set it to `false` and configure
  `CORS_ORIGINS` before deploying publicly.
- Do not commit `.env` or the SQLite database.

## Troubleshooting

**The dashboard says it cannot reach the backend.**
Start `uvicorn main:app --reload --port 8000` in `backend` and check that
`API_BASE` in `app.js` points to the right address.

**The dashboard says WhatsApp is not connected.**
Check `WHATSAPP_ACCESS_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` in
`backend/.env`, then restart the backend.

**Meta webhook verification fails.**
The verify token in Meta must match `WHATSAPP_VERIFY_TOKEN` exactly. The callback
URL must be the public HTTPS URL ending in `/api/whatsapp/webhook`.

**Messages arrive but no reply is sent.**
The access token may have expired. Also confirm the recipient is allowed in the
Meta test setup and that the user messaged the business first.

**AI is not being used.**
OpenRouter credits, key or model may be unavailable. The bot will still save
reports using keyword rules. Check the dashboard banner and `ai_error` in a
report.

**Voice notes are not transcribed.**
Add `ELEVENLABS_API_KEY` and make sure the account has credits. Otherwise the
bot asks the user to type.

**I changed `.env` but nothing changed.**
Stop and restart `uvicorn`. Environment values are loaded at startup.

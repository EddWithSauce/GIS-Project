# URSM Flood GIS (Prototype)
 V1.2 Changelogs (taken from Angelo's Changes)

# Additions:
  - Implemented Supabase integration and API.
  - User Log-in and Sign-in is now authenticated using Supabase
  - Added tables in supabase for appropriate data (please add more to this when the data isn't mock)
  - Added user exclusivity content

# Upcoming
  - I want to implement a notification system. But I will withhold it for now until we have real data to test it to. I will test it separately in private build.

Otherwise everything is identical to the previous version.


## Phase 1 Refactor (2026-01-25)
- Added `config.py` for env/config flags.
- Added `data_provider.py` + `providers/` for switching between STANDBY (mock) and LIVE (Supabase) data sources.
- API endpoints now call the provider, so removing mock later becomes a simple provider swap.


## Phase 2: Raspberry Pi Ingestion (LIVE)

Send sensor readings to the server:

- **POST** `/api/sensors/ingest`
- Header (recommended): `X-API-KEY: <DEVICE_API_KEY>`

Example JSON:
```json
{
  "station_code": "URSM_01",
  "humidity": 72.5,
  "temperature": 29.1,
  "wind": 1.2,
  "rain_mm_hr": 3.4,
  "water_level_m": 0.91
}
```

Set these in `.env`:
- `DEVICE_READY=true`
- `AI_READY=false` (forecast stays standby)
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`
- Optional: `DEVICE_API_KEY=<secret>`


## Phase 4: Prediction Pipeline + Notification Improvements (2026-01-25)
- Added `ml_service.py` (standby rule-based predictor).
- On every device ingest (`POST /api/sensors/ingest`), the server also writes a row to `predictions`:
  - Today: rule-based (uses water level thresholds) + stores extra fields in `predictions.payload`
  - Later: swap in your trained ML models without changing routes/JS.
- Notifications now use the latest prediction payload to show:
  - predicted rainfall intensity
  - alert level (Warning/Critical)
  - predicted flood risk
  - estimated hours before flooding (standby until ML can provide it)

### New/Required Supabase table (if not created yet)
Create `user_notifications` (used by the Notifications page + email sending):
```sql
create table if not exists public.user_notifications (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  email text,
  station_id uuid,
  created_at timestamptz default now(),
  alert_level text,
  title text,
  message text,
  predicted_rainfall_intensity text,
  predicted_flood_risk text,
  hours_before_flood real,
  peak_rain_mm_hr real,
  current_water_level_m real,
  channel text default 'both',
  is_read boolean default false
);
create index if not exists user_notifications_user_id_idx on public.user_notifications(user_id);
create index if not exists user_notifications_created_at_idx on public.user_notifications(created_at);
```


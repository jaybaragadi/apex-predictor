# Corrections

Explicit, reviewed overrides applied after ingestion and before scoring. Use
when the FIA's published classification differs from an API (late penalty,
DSQ, amended result). Each entry is logged in the snapshot.

```json
[{"round": 12, "session": "race", "driver": "some_driver_id",
  "set": {"position_text": "D", "points": 0, "status": "Disqualified"},
  "reason": "Technical infringement, FIA decision doc 45", "source": "https://www.fia.com/..."}]
```

`data/entries/<year>.json` works the same way for confirmed entry lists:
`[{"round": 21, "drivers": ["drv_bearman", "drv_ocon"], "status": "confirmed"}]` (internal ids from `data/registry`).
Only `"confirmed"` entries change the simulated grid; announcements do not.

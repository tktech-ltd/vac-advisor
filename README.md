# VAC Advisory Risk Index

Automated travel advisory dashboard for Canadian VAC cities in sub-Saharan Africa.

## How It Works

```
GitHub Actions (every 6 hours)
  └── fetch_advisories.py
        ├── Canada:    data.international.gc.ca JSON API
        ├── USA:       travel.state.gov RSS feed
        ├── UK FCDO:   gov.uk/foreign-travel-advice HTML
        └── Australia: smartraveller.gov.au API
              ↓
        advisory_data.json  (committed to repo)
              ↓
GitHub Pages serves index.html + advisory_data.json
              ↓
Browser reads ./advisory_data.json — NO CORS, NO PROXY
```

**Cost: $0. No servers. No workers. No proxies. Fully automatic.**

---

## Setup (5 minutes)

### Step 1 — Create the repository

```bash
# On GitHub.com: New repository → name it "vac-advisory" → Public → Create

# Then upload these files:
# - index.html
# - fetch_advisories.py
# - .github/workflows/refresh.yml
# - advisory_data.json  (upload the initial one from this package)
```

Or via git:
```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/vac-advisory.git
git push -u origin main
```

### Step 2 — Enable GitHub Pages

1. Repository → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: **main** / **(root)**
4. Click **Save**

Your dashboard will be at: `https://YOUR_USERNAME.github.io/vac-advisory/`

### Step 3 — Update index.html

Edit the top of `index.html` and replace:
```javascript
const GITHUB_USER = "YOUR_GITHUB_USERNAME";
const GITHUB_REPO = "vac-advisory";
```

### Step 4 — Verify the workflow runs

1. Go to your repo → **Actions** tab
2. Click **Refresh Advisory Data** → **Run workflow** (manual trigger)
3. Watch it run — should complete in ~3 minutes
4. Check that `advisory_data.json` was updated in your repo
5. Visit your GitHub Pages URL — data should be live

### Step 5 — Done

The workflow runs automatically every 6 hours. You never need to do anything again.

---

## Manual Refresh

Two options:
1. **From the dashboard**: Click the "↻ Refresh" button — it reloads the latest `advisory_data.json`
2. **Force a new fetch**: Go to Actions → Refresh Advisory Data → Run workflow

---

## Files

| File | Purpose |
|------|---------|
| `index.html` | The dashboard — reads advisory_data.json |
| `fetch_advisories.py` | Fetches all 4 sources, writes advisory_data.json |
| `.github/workflows/refresh.yml` | Runs fetch_advisories.py on a schedule |
| `advisory_data.json` | The data file served to the dashboard |

---

## Updating Advisory Notes

Edit the `NOTES` dictionary in `fetch_advisories.py`:
```python
NOTES = {
    "NG": "Your updated note for Nigeria",
    ...
}
```
Then commit. The next scheduled run will include the new notes.

---

## Advisory Sources

| Source | URL | API Type |
|--------|-----|----------|
| 🇨🇦 Canada | data.international.gc.ca/travel-voyage/index-updated.json | Official JSON |
| 🇺🇸 USA | travel.state.gov/_res/rss/TAsTWs.xml | Official RSS |
| 🇬🇧 UK FCDO | gov.uk/foreign-travel-advice/{country} | HTML scrape |
| 🇦🇺 Australia | smartraveller.gov.au/destinations-export | Official API |

---

## WCRI Scoring

```
Score = (CA×25% + US×30% + UK×25% + AU×20%)
      + Divergence penalty (±15 if 2-level gap, ±25 if 3-level gap)
      + Regional advisory bonus (+5)
      [capped at 100]

Bands:  0-30 Manageable | 31-55 Elevated | 56-75 High | 76-100 Extreme
```

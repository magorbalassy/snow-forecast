# Roadmap

## Worldwide coverage: OpenSkiMap + Open-Meteo

Scraping snow-forecast.com does not scale to all larger resorts worldwide:

- ~3000 resorts x 3 levels = ~9000 pages (~280 KB each, ~2.5 GB) per run; 2-3 hours at 1 request/s.
- High risk of rate limiting / blocking, and their terms most likely do not allow bulk scraping.
  If their data is needed at scale, ask whether they offer a data feed.
- robots.txt allows `/resorts/*/6day`, but disallows the 9/12/16-day pages.
- No JSON API behind the pages; HTML layout changes break the scraper.
- Their resort lists don't say how large a resort is.

Plan: keep snow-forecast.com for the favourite resorts in `resorts.yaml`, add a second source for the worldwide overview.

### Resort list: OpenSkiMap

- Free download of ski areas worldwide (from OpenStreetMap): location, lifts, piste km, min/max elevation.
- "Larger resorts" becomes a filter, e.g. > 50 km of pistes or > 800 m vertical.
- Top / bottom elevation come with the data, no scraping needed.

### Forecasts: Open-Meteo

- Free API (no key for non-commercial use); query by latitude/longitude plus `elevation`, which maps to top / mid / bot.
- Hourly snowfall, precipitation, freezing level, temperature, wind speed, **wind gusts** (snow-forecast only has
  mean wind; gusts would improve the lift wind risk map), weather code.
- Several models available: ECMWF, ICON, GFS, and 2 km Alpine models (MeteoSwiss ICON-CH2, ICON-D2, ~2 days ahead).
- Many locations per request, but the free tier has a daily limit (~10,000 calls, counted per location);
  worldwide runs several times a day may need the paid tier.

### Findings from comparing both sources (Oct 2026)

- **Don't use Open-Meteo `snowfall` directly for mountain tops.** It is computed at the model's own terrain height
  (Arosa: 1766 m, Sölden: 2150 m), so near the freezing level it reports rain where the top station gets snow.
  The `elevation` parameter only corrects temperature.
- Better: estimate snow from `precipitation` in hours where `temperature_2m` at the station elevation is <= ~0.5 °C
  (roughly 1 mm -> 1 cm; less for wet snow around 0 °C), or check against `freezing_level_height`.
- Example, Sölden top (3250 m), Thu 8 Oct PM + night: snow-forecast 12 cm; Open-Meteo snowfall 0-15 cm depending on
  the model; precipitation-based estimate 9-27 cm (models split into a wetter and a drier group).
- Example, Arosa top (2865 m), same period: snow-forecast 12 cm; Open-Meteo snowfall 0.4-2.4 cm for most models,
  but 17-28 mm precipitation below freezing (~15-25 cm); ICON-CH2 (2 km) 19.5 cm.

### Steps

1. Collect Open-Meteo forecasts for the current resorts next to snow-forecast for a few weeks
   (same index or a second one, with a `source` field) and compare on the dashboard.
2. Add the snow-from-precipitation estimate, plus wind gusts for the lift wind risk map.
3. Import the OpenSkiMap ski areas, pick the "larger" ones, and run Open-Meteo for them.

## Needed before scaling up (any source)

- Collector: parallel requests with a rate limit, retries with backoff, `run_id` shared by all documents of a run,
  scheduled with cron or a systemd timer.
- Storage: data stream with ILM (delete or downsample old runs); ~9000 documents per run with 18 nested slots each.
- "Latest run": the Vega specs pick the latest run themselves with a 1000-hit limit. At scale, also write a small
  "latest" index (one document per resort + level, overwritten each run) and point the dashboards at it.
- Dashboards: country/region filters, "top 20 by snow" views, map clustering; the snow line chart only for a region
  or shortlist.

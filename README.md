# Snow Forecast scraper 

A tool to scrape snow forecast data and feed data to Elasticsearch or other tools.

## SnowForecast.py 

A class to scrape data from snow-forecast.com.  
Uses a logger named `snow_forecast_logger`.  

### SnowForecast Class

The `SnowForecast` class is designed to fetch and parse weather forecast data from the website [snow-forecast.com](https://www.snow-forecast.com). It provides methods to retrieve information about countries, resorts, and detailed weather forecasts for specific resorts. The class uses the `requests` library to make HTTP requests and `BeautifulSoup` from the `bs4` library to parse HTML content.

#### Key Methods

- **`get_countries()`**: Fetches a list of countries available on the snow-forecast.com website. It returns a list of dictionaries, each containing the name and URL of a country.

- **`get_resorts_with_tabs(country)`**: Retrieves a list of resorts for a given country. It handles multiple tabs on the country page to ensure all resorts are fetched. The method returns a list of dictionaries, each containing the name, data URL, and URL of a resort.

- **`get_resort_coordinates(resort_url)`**: Retrieves the geographical coordinates (latitude and longitude) for a specific resort. It returns a dictionary containing 'lat' and 'lon' keys. The coordinates are automatically adjusted for direction (negative values for South latitude and West longitude). Returns None if coordinates cannot be found.

- **`forecast_for_resort(resort_url)`**: Fetches the 6-day weather forecast for a specific resort. It extracts data such as snow forecast, freezing level, humidity, and wind from the forecast table. The method returns a list of dictionaries, each containing the date, time, and weather data for a specific time period.

#### Example Usage

```python
from SnowForecast import SnowForecast

# Initialize the SnowForecast class
snow_forecast = SnowForecast()

# Get the list of countries
countries = snow_forecast.get_countries()
print(countries)

# Get the list of resorts for a specific country
resorts = snow_forecast.get_resorts_with_tabs('Switzerland')
print(resorts)

# Get the 6-day weather forecast for a specific resort
forecast = snow_forecast.forecast_for_resort('/resorts/Hoch-Ybrig/6day/mid')
print(forecast)
```

This class is useful for applications that need to display or process weather forecast data for ski resorts, such as weather dashboards, travel planning tools, or automated alert systems.


# Running

```
python3 -m venv venv-snowf && source venv-snowf/bin/activate
pip install -r requirements.txt
ES_PASSWORD=<password> python3 forecast-elastic.py
```

Optional: `ES_URL` (default `http://192.168.10.5:9200`) and `ES_USER` (default `elastic`).
Resorts are configured in `resorts.yaml`; top, mid and bottom forecasts are fetched for each.


# Elasticsearch setup

Define the ingest pipeline to flatten field for Vega:
```
PUT _ingest/pipeline/snow-forecast
{
  "description": "Pipeline to flatten forecast data",
  "processors": [
    {
      "script": {
        "lang": "painless",
        "source": """
          def flat = [:];
          for (def forecast : ctx.forecasts) {
            def key = forecast.date + ' ' + forecast.time;
            flat[key] = [
              'snow': forecast.snow.replace('cm', '').trim() != '' ? Float.parseFloat(forecast.snow.replace('cm', '')) : 0,
              'freezing_level': forecast.freezing_level != null ? Integer.parseInt(forecast.freezing_level) : null,
              'humidity': forecast.humidity != null ? Integer.parseInt(forecast.humidity) : null,
              'wind': forecast.wind
            ];
          }
          ctx.forecasts_flat = flat;
        """
      }
    }
  ]
}
```

Define the default pipeline for the index:
```
PUT snow-forecasts/_settings
{
  "index.default_pipeline": "snow-forecast"
}
```
`forecast-elastic.py` now installs the pipeline (`snow-forecast.pipeline.json`) and the index template (`snow-forecast.template.json`) on every run, so the manual steps above are only needed without the script.

# Kibana dashboard

`kibana-dashboard.ndjson` contains the dashboard and everything it uses: snow map, snow table (`vega.json`), lift wind risk map, wind table (`vega-wind.json`), snow line chart (`vega-snowline.json`), the Level control and the data view. The `vega-*.json` files are readable copies of the specs inside the ndjson.

Upload (overwrites existing objects):
```
curl -u elastic:<password> -X POST 'http://<kibana>:5601/api/saved_objects/_import?overwrite=true' \
  -H 'kbn-xsrf: true' --form file=@kibana-dashboard.ndjson
```

Export again after changing the dashboard in Kibana:
```
curl -u elastic:<password> -X POST 'http://<kibana>:5601/api/saved_objects/_export' \
  -H 'kbn-xsrf: true' -H 'Content-Type: application/json' \
  -d '{"objects":[{"type":"dashboard","id":"snow-forecast-dashboard"}],"includeReferencesDeep":true,"excludeExportDetails":true}' \
  -o kibana-dashboard.ndjson
```

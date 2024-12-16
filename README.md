# Snow Forecast scraper 

A tool to scrape snow forecast data and feed data to Elasticsearch or other tools.

## SnowForecast.py 

A class to scrape data from snow-forecast.com.  
Uses a logger named `snow_forecast_logger`.  

### SnowForecast Class

The `SnowForecast` class is designed to fetch and parse weather forecast data from the website [snow-forecast.com](https://www.snow-forecast.com). It provides methods to retrieve information about countries, resorts, and detailed weather forecasts for specific resorts. The class uses the `requests` library to make HTTP requests and `BeautifulSoup` from the `bs4` library to parse HTML content.

#### Key Methods

- **`get_countries()`**: Fetches a list of countries available on the snow-forecast.com website. It returns a list of dictionaries, each containing the name and URL of a country.

- **`forecast_for_resort(resort_url)`**: Fetches the 6-day weather forecast for a specific resort. It extracts data such as snow forecast, freezing level, humidity, and wind from the forecast table. The method returns a list of dictionaries, each containing the date, time, and weather data for a specific time period.

- **`get_resorts_with_tabs(country)`**: Retrieves a list of resorts for a given country. It handles multiple tabs on the country page to ensure all resorts are fetched. The method returns a list of dictionaries, each containing the name, data URL, and URL of a resort.

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
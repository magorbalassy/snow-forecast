from dataclasses import dataclass
from typing import List, Dict, Optional
import datetime
import bs4
import logging
import os
import requests
import yaml

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p')
logging.info('==== Starting new run ====')

@dataclass
class Resort:
    name: str
    country: str
    url: str
    data_url: str

@dataclass
class ForecastData:
    date: str
    time: str
    snow: Optional[str]
    freezing_level: Optional[str]
    humidity: Optional[str]
    wind: Optional[str]  # Add wind field

class ResortRepository:
    """Handles loading and storing resort configurations"""
    def __init__(self, config_file: str = 'resorts.yaml'):
        self.config_file = config_file
        self.user_resorts: Dict[str, List[str]] = {}  # country -> list of resort names
        self.available_resorts: Dict[str, List[Resort]] = {}  # country -> list of resort details

    def load_user_resorts(self) -> Dict[str, List[str]]:
        """Load just the resort names per country that user wants to monitor"""
        if not os.path.exists(self.config_file):
            raise FileNotFoundError(f"Configuration file '{self.config_file}' not found")
        
        with open(self.config_file) as file:
            self.user_resorts = yaml.load(file, Loader=yaml.FullLoader)
        return self.user_resorts

    def get_matching_resort(self, country: str, resort_name: str) -> Optional[Resort]:
        """Find matching resort from available resorts based on name"""
        if country not in self.available_resorts:
            return None
            
        # Try to find exact match first
        for resort in self.available_resorts[country]:
            if resort.name.lower() == resort_name.lower():
                return resort
                
        # Try fuzzy matching if no exact match found
        for resort in self.available_resorts[country]:
            if resort_name.lower() in resort.name.lower():
                return resort
                
        return None

    def update_available_resorts(self, snow_forecast: 'SnowForecast'):
        """Fetch all available resorts from snow-forecast.com"""
        for country in self.user_resorts.keys():
            resorts = snow_forecast.get_resorts_with_tabs(country)
            self.available_resorts[country] = [
                Resort(
                    name=r['name'],
                    country=country,
                    url=r['url'],
                    data_url=r['data_url']
                ) 
                for r in resorts
            ]

class SnowForecast:
    """Handles only fetching forecast data from the website"""
    def __init__(self):
        self.base_url = "https://www.snow-forecast.com"
        self.headers = {'User-Agent': 'Mozilla/5.0'}

    def get_countries(self):
        url = f"{self.base_url}/countries"
        response = requests.get(url)
        response.raise_for_status()
        soup = bs4.BeautifulSoup(response.text, 'html.parser')
        
        europe_anchor = soup.find('a', id='europe')
        if not europe_anchor:
            return []
        
        countries_list = europe_anchor.find_next('ul', class_='countries-list')
        if not countries_list:
            return []
        
        countries = []
        for li in countries_list.find_all('li'):
            country_link = li.find('a')
            if country_link:
                country_name = country_link.text.strip()
                country_url = country_link['href']
                countries.append({'name': country_name, 'url': country_url})
        
        return countries

    def get_resorts_with_tabs(self, country):
        base_url = f"{self.base_url}/countries/{country}/resorts/"
        response = requests.get(base_url)
        response.raise_for_status()
        soup = bs4.BeautifulSoup(response.text, 'html.parser')

        #  Extract resorts from the main page / first tab
        resorts = self._extract_resorts_from_page(soup)
        
        # Check if tabs are present
        tabs_div = soup.find('div', id='ctry_tabs')
        if tabs_div:
            tab_links = tabs_div.find_all('a')
            tab_urls = [link['href'] for link in tab_links]

            for tab_url in tab_urls:
                full_tab_url = f"{self.base_url}{tab_url}"
                tab_response = requests.get(full_tab_url)
                tab_response.raise_for_status()
                tab_soup = bs4.BeautifulSoup(tab_response.text, 'html.parser')
                resorts.extend(self._extract_resorts_from_page(tab_soup))        

        return resorts

    def _extract_resorts_from_page(self, soup):
        resorts = []
        resort_rows = soup.find_all('tr', class_='digest-row')
        for row in resort_rows:
            resort_url = row.get('data-url')
            name_cell = row.find('div', class_='name')
            if name_cell and resort_url:
                resort_name = name_cell.get_text(strip=True)
                resort_a_href = name_cell.find('a')
                resorts.append({
                    'name': resort_name,
                    'data_url': resort_url,
                    'url': resort_a_href['href']
                })
        return resorts

    # Fetch the 6-day forecast data for a specific resort: 
    # snow forecast, freeze level, humidity - return in a json object
    # Also fetch the date and time of the forecast from the header row
    # Header row is: tr class="forecast-table__row" data-row="days" and this contains the days
    # Time row is: <tr class="forecast-table__row" data-row="time"> and this contains the time slots
    # Data is in a table with class=forecast-table__table
    # Snow is in a row tr class="forecast-table__row" data-row="snow"
    # Freeze level is in a row tr class="forecast-table__row" data-row="freezing-level"
    # Humidity is in a row tr class="forecast-table__row" data-row="humidity"
    # Wind is in a row tr class="forecast-table__row" data-row="wind"
    # Example file is example-forecast.html
    def forecast_for_resort(self, resort_url):
        full_url = f"{self.base_url}{resort_url}"
        response = requests.get(full_url, headers=self.headers)
        response.raise_for_status()
        html_content = response.text

        soup = bs4.BeautifulSoup(html_content, 'html.parser')
        forecast_table = soup.find('table', class_='forecast-table__table')
        if not forecast_table:
            logging.error("Forecast table not found")
            return None

        # Extract dates and time slots from the header rows
        days_row = forecast_table.find('tr', attrs={'data-row': 'days'})
        if not days_row:
            logging.error("Days row not found")
        else:
            logging.info("Days row found")
        time_row = forecast_table.find('tr', attrs={'data-row': 'time'})
        if not time_row:
            logging.error("Time row not found")
        else:
            logging.info("Time row found")

        dates = []
        times = []

        if days_row and time_row:
            # Find all 'td' elements in the days row
            day_cells = days_row.find_all('td', class_='forecast-table-days__cell')
            if not day_cells:
                logging.error("Day cells not found")
            else:
                logging.info(f"Found {len(day_cells)} day cells")

            time_cells = time_row.find_all('td', class_='forecast-table__cell')
            if not time_cells:
                logging.error("Time cells not found")
            else:
                logging.info(f"Found {len(time_cells)} time cells")

            # Extract dates from 'data-date' attribute and repeat according to 'colspan'
            for day_cell in day_cells:
                date_text = day_cell.get('data-date')
                # Get colspan to know how many time periods this date applies to
                colspan = int(day_cell.get('colspan', 1))
                # Add the date multiple times based on colspan
                dates.extend([date_text] * colspan)
                logging.debug(f"Date {date_text} found, repeated {colspan} times")

            # Extract time slots
            for time_cell in time_cells:
                time_text = time_cell.get_text(strip=True)
                times.append(time_text)
                logging.debug(f"Time slot found: {time_text}")

        # Extract data rows
        snow_row = forecast_table.find('tr', attrs={'data-row': 'snow'})
        freezing_level_row = forecast_table.find('tr', attrs={'data-row': 'freezing-level'})
        humidity_row = forecast_table.find('tr', attrs={'data-row': 'humidity'})
        wind_row = forecast_table.find('tr', attrs={'data-row': 'wind'})  # Add wind row extraction

        # Get the data cells
        snow_data = [td.get_text(strip=True) for td in snow_row.find_all('td')] if snow_row else []
        # Replace em dash '—' with '0'
        snow_data = ['0' if cm == '—' else cm for cm in snow_data]
        logging.debug(f"Snow data after cleaning: {snow_data}")
        
        freezing_level_data = [td.get_text(strip=True) for td in freezing_level_row.find_all('td')] if freezing_level_row else []
        humidity_data = [td.get_text(strip=True) for td in humidity_row.find_all('td')] if humidity_row else []
        wind_data = [td.get_text(strip=True) for td in wind_row.find_all('td')] if wind_row else []  # Add wind data extraction
        logging.debug(f"Wind data: {wind_data}")

        # Combine data into a list of dictionaries
        forecast_data = []
        total_periods = len(times)
        for i in range(total_periods):
            day_forecast = {
                'date': dates[i] if i < len(dates) else None,
                'time': times[i],
                'snow': snow_data[i] if i < len(snow_data) else None,
                'freezing_level': freezing_level_data[i] if i < len(freezing_level_data) else None,
                'humidity': humidity_data[i] if i < len(humidity_data) else None,
                'wind': wind_data[i] if i < len(wind_data) else None  # Add wind to forecast
            }
            forecast_data.append(day_forecast)

        return forecast_data

class ForecastService:
    """Coordinates between repositories and data fetching"""
    def __init__(self):
        self.repository = ResortRepository()
        self.snow_forecast = SnowForecast()
        
    def get_forecasts_for_user_resorts(self) -> Dict[str, List[ForecastData]]:
        """Get forecasts for all user-configured resorts"""
        forecasts = {}
        
        # Load user's desired resorts
        user_resorts = self.repository.load_user_resorts()
        
        # Fetch available resorts from snow-forecast.com
        self.repository.update_available_resorts(self.snow_forecast)
        
        # Get forecasts for matching resorts
        for country, resort_names in user_resorts.items():
            for resort_name in resort_names:
                resort = self.repository.get_matching_resort(country, resort_name)
                if resort:
                    logging.info(f"Found matching resort for {resort_name}: {resort.name} ({resort.url} , {resort.data_url})")
                    forecast_data_dicts = self.snow_forecast.forecast_for_resort(resort.data_url)
                    if forecast_data_dicts:
                        # Convert dictionaries to ForecastData objects
                        forecast_data_objects = [
                            ForecastData(
                                date=data['date'],
                                time=data['time'],
                                snow=data['snow'],
                                freezing_level=data['freezing_level'],
                                humidity=data['humidity'],
                                wind=data['wind']  # Add wind to ForecastData object creation
                            )
                            for data in forecast_data_dicts
                        ]
                        forecasts[resort.name] = forecast_data_objects
                else:
                    logging.warning(f"No matching resort found for {resort_name} in {country}")
                    
        return forecasts

if __name__ == '__main__':
    # SnowForecast example usage
    snow_forecast = SnowForecast()
    print(snow_forecast.forecast_for_resort('/resorts/Hoch-Ybrig/6day/mid'))
    print(snow_forecast.forecast_for_resort('/resorts/Engelberg/6day/mid'))
    
    # Example usage
    service = ForecastService()
    all_forecasts = service.get_forecasts_for_user_resorts()
    print(all_forecasts)
    
    # Print forecasts by resort
    for resort_name, forecast_periods in all_forecasts.items():
        print(f"\nForecast for {resort_name}:")
        for period in forecast_periods:
            print(
                f"{period.date} {period.time}: "
                f"Snow: {period.snow}, "
                f"Freezing: {period.freezing_level}, "
                f"Humidity: {period.humidity}, "
                f"Wind: {period.wind}"  # Add wind to print statement
            )
import datetime
import bs4
import logging
import requests

# Use the custom logger
logger = logging.getLogger('snow_forecast_logger')

class SnowForecast:
    """Handles fetching forecast data from the website snow-forecast.com"""
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
            logger.error("Forecast table not found")
            return None

        # Extract dates and time slots from the header rows
        days_row = forecast_table.find('tr', attrs={'data-row': 'days'})
        if not days_row:
            logger.error("Days row not found")
        else:
            logger.info("Days row found")
        time_row = forecast_table.find('tr', attrs={'data-row': 'time'})
        if not time_row:
            logger.error("Time row not found")
        else:
            logger.info("Time row found")

        dates = []
        times = []

        if days_row and time_row:
            # Find all 'td' elements in the days row
            day_cells = days_row.find_all('td', class_='forecast-table-days__cell')
            if not day_cells:
                logger.error("Day cells not found")
            else:
                logger.info(f"Found {len(day_cells)} day cells")

            time_cells = time_row.find_all('td', class_='forecast-table__cell')
            if not time_cells:
                logger.error("Time cells not found")
            else:
                logger.info(f"Found {len(time_cells)} time cells")

            # Extract dates from 'data-date' attribute and repeat according to 'colspan'
            for day_cell in day_cells:
                date_text = day_cell.get('data-date')
                # Get colspan to know how many time periods this date applies to
                colspan = int(day_cell.get('colspan', 1))
                # Add the date multiple times based on colspan
                dates.extend([date_text] * colspan)
                logger.debug(f"Date {date_text} found, repeated {colspan} times")

            # Extract time slots
            for time_cell in time_cells:
                time_text = time_cell.get_text(strip=True)
                times.append(time_text)
                logger.debug(f"Time slot found: {time_text}")

        # Extract data rows
        snow_row = forecast_table.find('tr', attrs={'data-row': 'snow'})
        freezing_level_row = forecast_table.find('tr', attrs={'data-row': 'freezing-level'})
        humidity_row = forecast_table.find('tr', attrs={'data-row': 'humidity'})
        wind_row = forecast_table.find('tr', attrs={'data-row': 'wind'})  # Add wind row extraction

        # Get the data cells
        snow_data = [td.get_text(strip=True) for td in snow_row.find_all('td')] if snow_row else []
        # Replace em dash '—' with '0'
        snow_data = ['0' if cm == '—' else cm for cm in snow_data]
        logger.debug(f"Snow data after cleaning: {snow_data}")
        
        freezing_level_data = [td.get_text(strip=True) for td in freezing_level_row.find_all('td')] if freezing_level_row else []
        humidity_data = [td.get_text(strip=True) for td in humidity_row.find_all('td')] if humidity_row else []
        wind_data = [td.get_text(strip=True) for td in wind_row.find_all('td')] if wind_row else []  # Add wind data extraction
        logger.debug(f"Wind data: {wind_data}")

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

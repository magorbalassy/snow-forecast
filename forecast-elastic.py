from dataclasses import dataclass
from typing import List, Dict, Optional
from SnowForecast import SnowForecast
import logging
import os
import yaml

# Configure custom logger
logger = logging.getLogger('snow_forecast_logger')
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.info('==== Starting new run ====')

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
                    logger.info(f"Found matching resort for {resort_name}: {resort.name} ({resort.url} , {resort.data_url})")
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
                    logger.warning(f"No matching resort found for {resort_name} in {country}")
                    
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
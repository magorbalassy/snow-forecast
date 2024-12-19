import json
from dataclasses import dataclass
from typing import List, Dict, Optional
from SnowForecast import SnowForecast
import logging
import os
import yaml
from datetime import datetime
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import ssl
import certifi

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
    url: Optional[str] = None
    data_url: Optional[str] = None
    geo: Optional[Dict[str, float]] = None

@dataclass
class SnowForecastDocument:
    """Represents a snow forecast document for Elasticsearch"""
    name: str
    country: str
    geo: Dict[str, float]
    forecasts: List[Dict[str, str]]  # List of daily forecasts with date, time, snow, freezing_level, humidity, wind
    total_snow_cm: float  # Sum of all snow forecasts
    timestamp: str  # ISO8601 date when the forecast was fetched

def load_user_resorts(yaml_path: str) -> List[Resort]:
    with open(yaml_path, 'r') as file:
        yaml_data = yaml.safe_load(file)
    
    resorts = []
    for country, resort_names in yaml_data.items():
        if resort_names:  # Check if the list is not None
            for resort_name in resort_names:
                resorts.append(Resort(name=resort_name, country=country))
    return resorts

def load_snow_forecast_resorts(countries: List[str], force_load: bool = False) -> Dict[str, List[Resort]]:
    cache_file = 'snow_forecast_resorts.ndjson'
    
    if not force_load and os.path.exists(cache_file):
        resorts_by_country = {}
        with open(cache_file, 'r') as f:
            for line in f:
                data = json.loads(line)
                country = data['country']
                if country not in resorts_by_country:
                    resorts_by_country[country] = []
                # Convert cached data directly to Resort object
                resort = Resort(**data['resort_data'])
                resorts_by_country[country].append(resort)
        return resorts_by_country

    sf = SnowForecast()
    resorts_by_country = {}
    
    for country in countries:
        logger.info(f"Loading resorts for {country}")
        raw_resorts = sf.get_resorts_with_tabs(country.lower())
        resorts = []
        for raw_resort in raw_resorts:            
            resort = Resort(
                name=raw_resort['name'],
                country=country,
                url=raw_resort['url'],
                data_url=raw_resort['data_url']
            )
            resorts.append(resort)
        resorts_by_country[country] = resorts
        
        # Save complete Resort objects to NDJSON file
        with open(cache_file, 'a') as f:
            for resort in resorts:
                resort_dict = {
                    'country': country,
                    'resort_data': {
                        'name': resort.name,
                        'country': resort.country,
                        'url': resort.url,
                        'data_url': resort.data_url
                    }
                }
                json.dump(resort_dict, f)
                f.write('\n')
    
    return resorts_by_country

def update_user_resorts(user_resorts: List[Resort], snow_forecast_resorts: Dict[str, List[Resort]]):
    for user_resort in user_resorts:
        country_resorts = snow_forecast_resorts.get(user_resort.country, [])
        for sf_resort in country_resorts:
            if user_resort.name.lower() in sf_resort.name.lower():
                user_resort.url = sf_resort.url
                user_resort.data_url = sf_resort.data_url
                break

def create_snow_forecast_document(resort: Resort, forecast_data: List[Dict]) -> SnowForecastDocument:
    """Create a SnowForecastDocument from resort and its forecast data"""
    # Calculate total snow from forecast data
    total_snow = sum(
        float(point['snow'].replace('cm', '0')) 
        for point in forecast_data 
        if point.get('snow')
    )
    
    return SnowForecastDocument(
        name=resort.name,
        country=resort.country,
        geo=resort.geo or {},
        forecasts=forecast_data,
        total_snow_cm=total_snow,
        timestamp=datetime.utcnow().isoformat()
    )

def create_es_client():
    """Create Elasticsearch client with SSL and authentication"""
    return Elasticsearch(
        ['https://192.168.10.150:30920'],
        basic_auth=('elastic', 'ox2UYL4cj90p19q63nm6gA8b'),
        verify_certs=False,
        ssl_show_warn=False
    )

def setup_index(es_client, index_name='snow-forecasts'):
    """Create or update index with proper mappings"""
    with open('elasticsearch-mapping.json', 'r') as f:
        mapping = json.load(f)
    
    if not es_client.indices.exists(index=index_name):
        es_client.indices.create(index=index_name, body=mapping)
        logger.info(f"Created index {index_name}")

def prepare_documents(elastic_documents, index_name='snow-forecasts'):
    """Convert documents to Elasticsearch bulk format"""
    for doc in elastic_documents:
        # Convert dataclass to dict and ensure all fields are present
        doc_dict = {
            '_index': index_name,
            '_source': {
                '@timestamp': doc.timestamp,
                'name': doc.name,
                'country': doc.country,
                'geo': doc.geo,
                'total_snow_cm': doc.total_snow_cm,
                'forecasts': doc.forecasts
            }
        }
        yield doc_dict
            
if __name__ == '__main__':
    user_resorts_file = 'user_resorts.json'
    yaml_resorts = load_user_resorts('resorts.yaml')
    reload_needed = True
    sf = SnowForecast()

    if os.path.exists(user_resorts_file) and os.path.getsize(user_resorts_file) > 0:
        # Load existing user resorts from JSON
        with open(user_resorts_file, 'r') as f:
            user_resorts_data = json.load(f)
            loaded_resorts = [Resort(**data) for data in user_resorts_data]
            
        # Compare loaded resorts with yaml resorts
        if len(loaded_resorts) == len(yaml_resorts):
            yaml_resort_keys = {(r.name, r.country) for r in yaml_resorts}
            loaded_resort_keys = {(r.name, r.country) for r in loaded_resorts}
            if yaml_resort_keys == loaded_resort_keys:
                user_resorts = loaded_resorts
                reload_needed = False
                logger.info(f"Loaded {len(user_resorts)} matching resort(s) from {user_resorts_file}")
    
    if reload_needed:
        # Perform the original scraping and data collection
        user_resorts = yaml_resorts
        logger.info(f"User resorts: {user_resorts}")
        unique_countries = list(set(resort.country for resort in user_resorts))
        snow_forecast_resorts = load_snow_forecast_resorts(unique_countries)
        logger.debug(f"Snow forecast resorts: {snow_forecast_resorts}")
        update_user_resorts(user_resorts, snow_forecast_resorts)
        
        # Add geo coordinates to user resorts
        for user_resort in user_resorts:
            if user_resort.url:
                user_resort.geo = sf.get_resort_coordinates(user_resort.url)
                logger.info(f"Added geo coordinates for {user_resort.name}: {user_resort.geo}")
                
        # Save the updated resorts
        with open(user_resorts_file, 'w') as f:
            json.dump([resort.__dict__ for resort in user_resorts], f, indent=4)
            
    # Fetch snow forecast data for each resort
    logger.info("Fetching snow forecast data for resorts...")
    elastic_documents = []
    for resort in user_resorts:
        if resort.data_url:
            logger.info(f"Fetching forecast for {resort.name}")
            forecast_data = sf.forecast_for_resort(resort.data_url)
            if forecast_data:
                doc = create_snow_forecast_document(resort, forecast_data)
                elastic_documents.append(doc)
                logger.info(f"Successfully created document for {resort.name}")
            else:
                logger.error(f"Failed to fetch forecast for {resort.name}")
    
    logger.info(f"Created {len(elastic_documents)} documents ready for Elasticsearch")
    logger.debug('Documents:', elastic_documents)
    
    # After creating elastic_documents, send to Elasticsearch
    try:
        es = create_es_client()
        setup_index(es)
        
        # Bulk index the documents
        success, failed = bulk(es, prepare_documents(elastic_documents))
        logger.info(f"Successfully indexed {success} documents")
        if failed:
            logger.error(f"Failed to index {len(failed)} documents")
            
    except Exception as e:
        logger.error(f"Error connecting to Elasticsearch: {str(e)}")

import json
import os
import time
from argparse import ArgumentParser
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from typing import List, Tuple, Optional
from logging import getLogger
import logging
import sys
import random
from dotenv import load_dotenv

load_dotenv()

root = getLogger(__name__)
root.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
root.addHandler(handler)

logger = getLogger(__name__)
def format_bsf_object(elem):
    s = []
    for c in elem.contents:
        cc = c
        if not isinstance(cc, str):
            cc = cc.get_text()
        if not cc:
            continue
        s.append(cc)
    return s[0], "\n".join(s[1:])


class FreeFitPartialClub(BaseModel):
    Id: int
    Name: str


def get_all_clubs(area) -> List[FreeFitPartialClub]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'en-US,en;q=0.9,he;q=0.8',
        'Origin': 'https://freefit.co.il',
        'Referer': 'https://freefit.co.il/CLUBS/',
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/json; charset=UTF-8'
    }
    
    clubz = requests.post(
        "https://freefit.co.il/Master.asmx/SearchClubList",
        json={
            "CompanyID": 0,
            "subcategoryId": "-1",
            "area": area,
            "freeText": "",
            "CompanyName": ""
        },
        headers=headers
    )
    
    # Add debugging information
    logger.debug(f"Status code: {clubz.status_code}")
    logger.debug(f"Response headers: {clubz.headers}")
    logger.debug(f"Response content: {clubz.text[:500]}")  # First 500 chars
    
    # Check status code first
    clubz.raise_for_status()
    
    try:
        data = clubz.json()
    except requests.exceptions.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON response: {str(e)}")
        logger.error(f"Response content: {clubz.text[:500]}")
        raise
    
    clubz = data.get("d")
    if clubz is None:
        logger.error("No 'd' field found in response")
        logger.error(f"Full response: {data}")
        raise ValueError("Invalid response format")
    
    # Handle empty list case
    if len(clubz) == 0:
        logger.info(f"No clubs found for area: {area}")
        return []
        
    return [FreeFitPartialClub(**x) for x in clubz]


class Club(BaseModel):
    id: int
    title: str
    lat_lng: Optional[Tuple[float, float]]
    address: str
    phone: str
    website: str
    tags: List[str]
    logo_url: str
    about: str
    latest_ts: int = Field(default_factory=lambda: int(time.time()))


def find_address_in_google(address, title=None):
    logger.info(f"Trying to search for: {title} at {address} in google.")
    
    # Combine title and address for better search accuracy
    search_query = f"{title} {address}, ישראל" if title else f"{address}, ישראל"
    
    params = {
        "input": search_query,
        "inputtype": "textquery",
        "key": os.getenv("GOOGLE_API_KEY"),
        "fields": ["geometry", "formatted_address", "place_id", "name"],
        "locationbias": "circle:50000@31.7767,35.2345",
        "language": "iw"
    }
    
    try:
        # Log the actual request being made
        logger.debug(f"Making request with params: {params}")
        
        response = requests.get(
            "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
            params=params,
            timeout=10
        )
        response.raise_for_status()
        json_res = response.json()
        
        # Log the response for debugging
        logger.debug(f"Google Places API response: {json_res}")
        
        if "candidates" not in json_res or not json_res["candidates"]:
            logger.info(f"First attempt failed, trying with address only: {address}")
            params["input"] = f"{address}, ישראל"
            
            response = requests.get(
                "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
                params=params,
                timeout=10
            )
            json_res = response.json()
            logger.debug(f"Second attempt response: {json_res}")
            
        if "candidates" not in json_res or not json_res["candidates"]:
            logger.warning(f"No location found for: {search_query}")
            # Try one last time with a more specific search
            params["input"] = "Star1 gym Shamai Street Jerusalem"
            response = requests.get(
                "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
                params=params,
                timeout=10
            )
            json_res = response.json()
            logger.debug(f"Final attempt response: {json_res}")
            
        if "candidates" not in json_res or not json_res["candidates"]:
            return None
            
        logger.info("Successfully found location")
        location = json_res["candidates"][0]["geometry"]["location"]
        logger.info(f"Found coordinates: {location}")
        return location.get("lat"), location.get("lng")
        
    except Exception as e:
        logger.error(f"Error finding address in Google: {str(e)}")
        logger.exception("Full traceback:")
        return None


def parse_club(session, club_id):
    # Use the session to make requests
    response = session.get(
        f"https://freefit.co.il/CLUBS/?CLUB={club_id}&SUBCLUBCATEGORY=-1"
    )
    response.raise_for_status()

    # Proceed with parsing the response as before
    bsf = BeautifulSoup(response.text, 'html.parser')

    # Rest of your parsing logic...
    header = bsf.find(id="headerText")
    if not header:
        logger.error(f"Could not find header for club {club_id}")
        raise ValueError("Missing header element")
    
    title_elem = header.find("h1")
    if not title_elem:
        logger.error(f"Could not find title for club {club_id}")
        raise ValueError("Missing title element")
    title = title_elem.get_text()

    logo_elem = bsf.find(id="logo")
    if not logo_elem or not logo_elem.find("img"):
        logger.error(f"Could not find logo for club {club_id}")
        raise ValueError("Missing logo element")
    logo_url = "https://freefit.co.il" + logo_elem.find("img")['src']

    about_elem = bsf.find(id="textAbout")
    if not about_elem:
        logger.error(f"Could not find about section for club {club_id}")
        raise ValueError("Missing about element")
    about = about_elem.get_text()

    club_details = bsf.find_all("div", {"class": "detail"})
    if len(club_details) < 12:
        logger.error(f"Insufficient club details found for club {club_id}. Found {len(club_details)}")
        raise ValueError("Insufficient club details")

    # Extract club details as before
    _, address = format_bsf_object(club_details[3])
    _, phone = format_bsf_object(club_details[2])
    _, website = format_bsf_object(club_details[6])

    # Handle latitude and longitude extraction
    try:
        lat_lng = club_details[8].find("a")['href'].split("/")[6]
        lat, lng, *_ = lat_lng.replace("@", "").split(",")
        lat_lng = (float(lat), float(lng))
    except Exception:
        try:
            lat_lng = find_address_in_google(address, title)  # Pass both address and title
        except Exception as e:
            lat_lng = None

    tags = [format_bsf_object(x)[1] for x in club_details[11:]]

    return Club(
        id=club_id,
        title=title,
        tags=tags,
        address=address,
        phone=phone,
        lat_lng=lat_lng,
        website=website,
        logo_url=logo_url,
        about=about
    )


def write_clubs(clubs, clubs_file):
    with open(clubs_file, "w+", encoding="utf-8") as f:
        json.dump(clubs, f, indent=4, ensure_ascii=False)


def scrape(clubs_file, areas):
    # Convert single string to list if necessary
    if isinstance(areas, str):
        areas = [areas]
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/119.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://freefit.co.il/CLUBS/',
        'Connection': 'keep-alive',
    })
    
    # Load existing clubs data
    try:
        with open(clubs_file, "r", encoding="utf-8") as fr:
            clubs = json.load(fr)
        logger.info(f"Loaded {len(clubs)} existing clubs from {clubs_file}")
    except FileNotFoundError:
        logger.info(f"No existing clubs file found at {clubs_file}. Starting fresh.")
        clubs = {}
    except json.JSONDecodeError:
        logger.warning(f"Corrupted clubs file at {clubs_file}. Starting fresh.")
        clubs = {}

    # Track which clubs we've seen in this run
    processed_clubs = set()
    
    all_clubs = []
    for area in areas:
        logger.info(f"Fetching clubs for area: {area}")
        area_clubs = get_all_clubs(area)
        logger.info(f"Found {len(area_clubs)} clubs in {area}")
        all_clubs.extend(area_clubs)
    
    logger.info(f"Found total of {len(all_clubs)} clubs across all areas")
    
    # Process new clubs and update existing ones if needed
    for club in all_clubs:
        club_id = str(club.Id)
        processed_clubs.add(club_id)
        
        # Skip if club exists and was updated recently (e.g., within last 24 hours)
        if club_id in clubs:
            last_update = clubs[club_id].get('latest_ts', 0)
            if time.time() - last_update < 86400:  # 24 hours in seconds
                logger.info(f"Skipping {club_id}, was updated recently")
                continue
        
        logger.info(f"Processing club {club_id}")
        try:
            parsed_club = parse_club(session, club.Id)
            clubs[club_id] = parsed_club.dict()
            write_clubs(clubs, clubs_file)
            time.sleep(random.uniform(1, 3))
        except Exception as e:
            logger.error(f"Failed processing club {club_id}: {str(e)}")
            continue

    # Don't remove clubs that weren't in the current search areas
    logger.info(f"Processed {len(processed_clubs)} clubs in this run")
    logger.info(f"Total clubs in database: {len(clubs)}")


def extract_city_names(filename):
    prefix = "רשימת מכוני כושר ב"
    cities = []
    
    with open(filename, 'r', encoding='utf-8') as file:
        for line in file:
            if line.startswith(prefix):
                # Extract the city name by removing the prefix
                city = line[len(prefix):].strip()
                cities.append(city)
    
    return cities
if __name__ == "__main__":
    cities = extract_city_names("cities_list.txt")
    parser = ArgumentParser()
    parser.add_argument("--clubs_file", default="./clubs.json")
    parser.add_argument(
        "--areas", 
        nargs="+",  # This allows multiple arguments
        # default=["הרצליה","תל אביב","רמת השרון","ירושלים","רמת גן","גבעתיים","רחובות","פתח תקווה"],
        default=cities,
        help="Areas to search clubs in, space-separated. Example: --areas 'ירושלים' 'תל אביב' 'רמת השרון'"
    )
    args = parser.parse_args()

    scrape(args.clubs_file, args.areas)

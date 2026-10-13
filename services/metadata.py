import re
import aiohttp
from typing import Optional, Dict, Any
from config import OMDB_API_KEY, logger

NOISE_PATTERNS = [
    # Resolutions
    r"\b(2160p|1080p|720p|480p|360p|4k|uhd|fhd|hd)\b",
    # Sources / Rips
    r"\b(bluray|bdrip|brrip|web-?dl|webrip|web|hdrip|dvdrip|dvd|camrip|cam|hdts|telecine|telesync|hdtv)\b",
    # Codecs & specs
    r"\b(x264|x265|h264|h265|hevc|10bit|8bit|hdr10\+?|hdr|remux|proper|repack)\b",
    # Audio & Languages
    r"\b(hindi|english|tamil|telugu|malayalam|kannada|bengali|marathi|punjabi|korean|japanese|chinese)\b",
    r"\b(dual audio|multi audio|dubbed|esub|subbed|subtitles?|org audio)\b",
    r"\b(aac|ac3|dts(-hd)?|dd5\.1|dolby|atmos)\b",
    # Container formats
    r"\b(mkv|mp4|avi)\b"
]

def clean_movie_title(raw_text: str, keep_year: bool = False) -> str:
    """Strip release tags, resolutions, audio/languages to get core movie title."""
    text = re.sub(r"[\._\-\[\]\(\)]+", " ", raw_text)
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    if not keep_year:
        text = re.sub(r"\b(19\d\d|20\d\d)\b", " ", text)
    return " ".join(text.split())

def parse_search_query(query: str) -> Dict[str, Any]:
    """Parse a complex movie query like 'Spider-Man 2 2004 1080p Hindi'."""
    year = extract_year(query)
    clean_title = clean_movie_title(query, keep_year=False)
    return {
        "raw_query": query,
        "clean_title": clean_title,
        "year": year
    }

def format_file_size(size_bytes: int) -> str:
    """Format bytes into readable string (KB, MB, GB)."""
    if not size_bytes or size_bytes <= 0:
        return "Unknown size"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def extract_year(text: str) -> Optional[str]:
    """Extract a 4-digit release year (1900-2099) from string."""
    match = re.search(r"\b(19\d\d|20\d\d)\b", text)
    return match.group(1) if match else None

async def fetch_movie_metadata(title: str, year: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetch movie details and poster from OMDb API if key is available."""
    if not OMDB_API_KEY:
        return None

    cleaned = clean_movie_title(title)
    if not cleaned:
        return None

    extracted_y = year or extract_year(title)
    # If year is extracted, remove it from title query to prevent double year search in OMDb
    if extracted_y:
        search_title = re.sub(rf"\b{extracted_y}\b", "", cleaned).strip() or cleaned
    else:
        search_title = cleaned

    url = f"http://www.omdbapi.com/?t={aiohttp.helpers.quote(search_title)}&apikey={OMDB_API_KEY}"
    if extracted_y:
        url += f"&y={extracted_y}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("Response") == "True":
                        return {
                            "title": data.get("Title", search_title),
                            "year": data.get("Year", extracted_y or "N/A"),
                            "genre": data.get("Genre", "N/A"),
                            "rating": data.get("imdbRating", "N/A"),
                            "plot": data.get("Plot", "No plot available."),
                            "poster": data.get("Poster") if data.get("Poster") != "N/A" else None,
                            "imdb_id": data.get("imdbID")
                        }
    except Exception as e:
        logger.warning(f"Error fetching OMDb metadata for '{cleaned}': {e}")
    return None

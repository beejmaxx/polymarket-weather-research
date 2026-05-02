from __future__ import annotations

from pwmk.models.domain import Location

KNOWN_LOCATIONS: dict[str, Location] = {
    "atlanta": Location(
        name="Atlanta",
        region="GA",
        latitude=33.7490,
        longitude=-84.3880,
        timezone="America/New_York",
    ),
    "austin": Location(
        name="Austin", region="TX", latitude=30.2672, longitude=-97.7431, timezone="America/Chicago"
    ),
    "baltimore": Location(
        name="Baltimore",
        region="MD",
        latitude=39.2904,
        longitude=-76.6122,
        timezone="America/New_York",
    ),
    "boston": Location(
        name="Boston",
        region="MA",
        latitude=42.3601,
        longitude=-71.0589,
        timezone="America/New_York",
    ),
    "charlotte": Location(
        name="Charlotte",
        region="NC",
        latitude=35.2271,
        longitude=-80.8431,
        timezone="America/New_York",
    ),
    "chicago": Location(
        name="Chicago",
        region="IL",
        latitude=41.8781,
        longitude=-87.6298,
        timezone="America/Chicago",
    ),
    "dallas": Location(
        name="Dallas", region="TX", latitude=32.7767, longitude=-96.7970, timezone="America/Chicago"
    ),
    "denver": Location(
        name="Denver", region="CO", latitude=39.7392, longitude=-104.9903, timezone="America/Denver"
    ),
    "detroit": Location(
        name="Detroit",
        region="MI",
        latitude=42.3314,
        longitude=-83.0458,
        timezone="America/Detroit",
    ),
    "houston": Location(
        name="Houston",
        region="TX",
        latitude=29.7604,
        longitude=-95.3698,
        timezone="America/Chicago",
    ),
    "indianapolis": Location(
        name="Indianapolis",
        region="IN",
        latitude=39.7684,
        longitude=-86.1581,
        timezone="America/Indiana/Indianapolis",
    ),
    "kansas city": Location(
        name="Kansas City",
        region="MO",
        latitude=39.0997,
        longitude=-94.5786,
        timezone="America/Chicago",
    ),
    "las vegas": Location(
        name="Las Vegas",
        region="NV",
        latitude=36.1716,
        longitude=-115.1391,
        timezone="America/Los_Angeles",
    ),
    "los angeles": Location(
        name="Los Angeles",
        region="CA",
        latitude=34.0522,
        longitude=-118.2437,
        timezone="America/Los_Angeles",
    ),
    "miami": Location(
        name="Miami", region="FL", latitude=25.7617, longitude=-80.1918, timezone="America/New_York"
    ),
    "minneapolis": Location(
        name="Minneapolis",
        region="MN",
        latitude=44.9778,
        longitude=-93.2650,
        timezone="America/Chicago",
    ),
    "nashville": Location(
        name="Nashville",
        region="TN",
        latitude=36.1627,
        longitude=-86.7816,
        timezone="America/Chicago",
    ),
    "new orleans": Location(
        name="New Orleans",
        region="LA",
        latitude=29.9511,
        longitude=-90.0715,
        timezone="America/Chicago",
    ),
    "new york": Location(
        name="New York",
        region="NY",
        latitude=40.7128,
        longitude=-74.0060,
        timezone="America/New_York",
    ),
    "new york city": Location(
        name="New York",
        region="NY",
        latitude=40.7128,
        longitude=-74.0060,
        timezone="America/New_York",
    ),
    "nyc": Location(
        name="New York",
        region="NY",
        latitude=40.7128,
        longitude=-74.0060,
        timezone="America/New_York",
    ),
    "orlando": Location(
        name="Orlando",
        region="FL",
        latitude=28.5383,
        longitude=-81.3792,
        timezone="America/New_York",
    ),
    "philadelphia": Location(
        name="Philadelphia",
        region="PA",
        latitude=39.9526,
        longitude=-75.1652,
        timezone="America/New_York",
    ),
    "phoenix": Location(
        name="Phoenix",
        region="AZ",
        latitude=33.4484,
        longitude=-112.0740,
        timezone="America/Phoenix",
    ),
    "portland": Location(
        name="Portland",
        region="OR",
        latitude=45.5152,
        longitude=-122.6784,
        timezone="America/Los_Angeles",
    ),
    "san diego": Location(
        name="San Diego",
        region="CA",
        latitude=32.7157,
        longitude=-117.1611,
        timezone="America/Los_Angeles",
    ),
    "san francisco": Location(
        name="San Francisco",
        region="CA",
        latitude=37.7749,
        longitude=-122.4194,
        timezone="America/Los_Angeles",
    ),
    "seattle": Location(
        name="Seattle",
        region="WA",
        latitude=47.6062,
        longitude=-122.3321,
        timezone="America/Los_Angeles",
    ),
    "st. louis": Location(
        name="St. Louis",
        region="MO",
        latitude=38.6270,
        longitude=-90.1994,
        timezone="America/Chicago",
    ),
    "st louis": Location(
        name="St. Louis",
        region="MO",
        latitude=38.6270,
        longitude=-90.1994,
        timezone="America/Chicago",
    ),
    "tampa": Location(
        name="Tampa", region="FL", latitude=27.9506, longitude=-82.4572, timezone="America/New_York"
    ),
    "washington dc": Location(
        name="Washington",
        region="DC",
        latitude=38.9072,
        longitude=-77.0369,
        timezone="America/New_York",
    ),
    "washington d.c.": Location(
        name="Washington",
        region="DC",
        latitude=38.9072,
        longitude=-77.0369,
        timezone="America/New_York",
    ),
    "washington": Location(
        name="Washington",
        region="DC",
        latitude=38.9072,
        longitude=-77.0369,
        timezone="America/New_York",
    ),
}


def find_known_location(text: str) -> Location | None:
    normalized = text.lower()
    for key in sorted(KNOWN_LOCATIONS, key=len, reverse=True):
        if key in normalized:
            return KNOWN_LOCATIONS[key]
    return None

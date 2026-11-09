import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from .weather import weather_rows
# archive a fixed NASA POWER pilot and its acquisition provenance.



QUERY = dict(parameters="ALLSKY_SFC_SW_DWN,T2M", community="RE",
             longitude="-118.778410", latitude="35.205583", start="20250701",
             end="20250707", format="JSON", **{"time-standard": "UTC"})
URL = "https://power.larc.nasa.gov/api/temporal/hourly/point?" + urlencode(QUERY)
DEFAULT = Path(__file__).resolve().parents[2] / "data/raw_context/nasa_power/arvin_20250701_20250707"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new directory to preserve the archive")

    with urlopen(URL, timeout=60) as response:
        raw = response.read()

    payload = json.loads(raw)
    rows = weather_rows(payload)
    provenance = {"source": "NASA POWER", "request_url": URL, "query": QUERY,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(raw).hexdigest(), "hour_count": len(rows),
        "header": payload["header"], "parameters": payload["parameters"],
        "returned_geometry": payload["geometry"],
        "coordinate_reference": "https://et.water.ca.gov/api/station/125",
        "classification": "gridded environmental estimates; not station or farm observations"}

    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "response.json").write_bytes(raw)
    (args.output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")

    print(f"Archived {len(rows)} validated hours in {args.output}")




if __name__ == "__main__":
    main()

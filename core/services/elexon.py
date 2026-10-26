import requests

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"


def fetch_wind_forecasts(published_from, published_to):
    url = f"{BASE_URL}/datasets/WINDFOR/stream"

    params = {
        "publishDateTimeFrom": published_from,
        "publishDateTimeTo": published_to,
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError("Unexpected response from Elexon")

    return data


def fetch_wind_actuals(published_from, published_to):
    url = f"{BASE_URL}/datasets/FUELHH/stream"

    params = {
        "publishDateTimeFrom": published_from,
        "publishDateTimeTo": published_to,
    }

    response = requests.get(
        url,
        params=params,
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError("Unexpected response from Elexon")

    return [
        row for row in data
        if row.get("fuelType", "").upper() == "WIND"
    ]
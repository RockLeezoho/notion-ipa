import os
import time
import requests

from dotenv import load_dotenv


# =========================================================
# LOAD ENV
# =========================================================

load_dotenv()


NOTION_API_VERSION = os.getenv(
    "NOTION_API_VERSION",
    "2026-03-11"
)

BASE_URL = "https://api.notion.com/v1"


WORD_PROPERTY = os.getenv(
    "NOTION_WORD_PROPERTY",
    "Word"
)

POS_PROPERTY = os.getenv(
    "NOTION_POS_PROPERTY",
    "Parts of Speech"
)

IPA_PROPERTY = os.getenv(
    "NOTION_IPA_PROPERTY",
    "IPA"
)


# =========================================================
# RETRY CONFIG
# =========================================================

MAX_RETRIES = 3
RETRY_DELAY = 0.5
REQUEST_TIMEOUT = 20


# =========================================================
# ENV & CONFIG
# =========================================================

def get_notion_config():
    """Return the current Notion configuration from the environment."""

    return {
        "token": os.getenv("NOTION_TOKEN"),
        "database_id": os.getenv("NOTION_DATABASE_ID"),
        "data_source_id": os.getenv("NOTION_DATA_SOURCE_ID"),
    }


def build_headers():
    """Build request headers using the latest environment values."""

    token = get_notion_config()["token"]

    if not token:
        raise RuntimeError(
            "Missing NOTION_TOKEN in .env file."
        )

    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json",
    }


def validate_config():
    """Validate required environment variables."""

    config = get_notion_config()
    missing = []

    for key, value in config.items():
        if not value or not str(value).strip():
            missing.append(
                f"NOTION_{key.upper()}".replace("_ID", "_ID")
            )

    if config["token"] is None or not str(config["token"]).strip():
        missing.append("NOTION_TOKEN")

    if config["database_id"] is None or not str(config["database_id"]).strip():
        missing.append("NOTION_DATABASE_ID")

    if config["data_source_id"] is None or not str(config["data_source_id"]).strip():
        missing.append("NOTION_DATA_SOURCE_ID")

    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(sorted(set(missing)))
            + "."
        )

    return config


# =========================================================
# RETRY HELPER
# =========================================================

def get_retry_delay(attempt):
    """Calculate the delay between retry attempts."""

    return RETRY_DELAY * (2 ** (attempt - 1))


def should_retry_status(status_code):
    """Determine whether an HTTP status code should be retried."""

    return (
        status_code == 429
        or 500 <= status_code <= 599
    )


# =========================================================
# REQUEST HELPER
# =========================================================

def request_with_retry(method, url, payload=None):
    """Send a Notion request and retry on transient failures."""

    validate_config()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=build_headers(),
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )

            if response.ok:
                return response.json()

            if should_retry_status(response.status_code):
                print(
                    f"Notion {method.upper()} error "
                    f"{response.status_code} "
                    f"(attempt {attempt}/{MAX_RETRIES})"
                )

                if attempt < MAX_RETRIES:
                    delay = get_retry_delay(attempt)
                    print(f"Retrying in {delay:.1f}s...")
                    time.sleep(delay)
                    continue

            print(f"Notion API {method.upper()} error:")
            print(response.status_code)
            print(response.text)
            response.raise_for_status()

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        ) as e:
            print(
                f"Notion {method.upper()} network error "
                f"(attempt {attempt}/{MAX_RETRIES}): {e}"
            )

            if attempt < MAX_RETRIES:
                delay = get_retry_delay(attempt)
                print(f"Retrying in {delay:.1f}s...")
                time.sleep(delay)
                continue

            print(
                f"Notion {method.upper()} request failed "
                "after all retry attempts."
            )
            raise

        except requests.exceptions.RequestException:
            raise

    raise RuntimeError(f"Notion {method.upper()} request failed.")


def notion_get(url):
    """Send a GET request to the Notion API."""

    return request_with_retry("GET", url)


def notion_patch(url, payload):
    """Send a PATCH request to the Notion API."""

    return request_with_retry("PATCH", url, payload)


# =========================================================
# PROPERTY HELPERS
# =========================================================

def extract_title_value(property_data):
    """
    Extract text from a Title property.
    """

    if not property_data:
        return ""

    if property_data.get("type") != "title":
        return ""

    title = property_data.get(
        "title",
        []
    )

    if not title:
        return ""

    return "".join(
        item.get("plain_text", "")
        for item in title
    ).strip()


def extract_rich_text_value(property_data):
    """
    Extract text from a Rich Text property.
    """

    if not property_data:
        return ""

    if property_data.get("type") != "rich_text":
        return ""

    rich_text = property_data.get(
        "rich_text",
        []
    )

    return "".join(
        item.get("plain_text", "")
        for item in rich_text
    ).strip()


def extract_select_value(property_data):
    """
    Extract the value from a Select property.
    """

    if not property_data:
        return ""

    if property_data.get("type") != "select":
        return ""

    select = property_data.get("select")

    if not select:
        return ""

    return select.get(
        "name",
        ""
    ).strip()


# =========================================================
# GET PAGE
# =========================================================

def get_page_data(page_id):
    """
    Get the Word, POS, and IPA of a Notion page.
    """

    validate_config()

    url = f"{BASE_URL}/pages/{page_id}"

    page = notion_get(url)

    properties = page.get(
        "properties",
        {}
    )

    word = extract_title_value(
        properties.get(WORD_PROPERTY)
    )

    pos = extract_select_value(
        properties.get(POS_PROPERTY)
    )

    ipa = extract_rich_text_value(
        properties.get(IPA_PROPERTY)
    )

    return {
        "page_id": page_id,
        "word": word,
        "pos": pos,
        "ipa": ipa,
        "properties": properties,
    }


# =========================================================
# UPDATE IPA
# =========================================================

def update_ipa(
    page_id: str,
    ipa: str
):
    """
    Update the IPA value in Notion.

    ipa can be:
        "[BrE] /dɒɡ/ [AmE] /dɔːɡ/"

    or:
        ""

    When ipa == "":
        The Rich Text property will be cleared.

    If Notion encounters a network error:
        notion_patch() will retry the request.

    If all retry attempts fail:
        an exception will be raised and passed to app.py.

    app.py will not report the update as successful.
    """

    validate_config()

    # -----------------------------------------------------
    # Allow empty IPA
    # -----------------------------------------------------

    if ipa is None:
        ipa = ""

    # -----------------------------------------------------
    # Build payload
    # -----------------------------------------------------

    if ipa.strip():

        payload = {
            "properties": {
                IPA_PROPERTY: {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": ipa
                            }
                        }
                    ]
                }
            }
        }

    else:

        # Empty IPA → clear the entire Rich Text property
        payload = {
            "properties": {
                IPA_PROPERTY: {
                    "rich_text": []
                }
            }
        }

    # -----------------------------------------------------
    # PATCH
    # -----------------------------------------------------

    url = f"{BASE_URL}/pages/{page_id}"

    notion_patch(
        url,
        payload
    )

    return True


# =========================================================
# DATA SOURCE PROPERTIES
# =========================================================

def get_data_source_properties():
    """
    Get the list of Data Source properties from Notion.
    """

    config = validate_config()

    url = (
        f"{BASE_URL}/data_sources/"
        f"{config['data_source_id']}"
    )

    data = notion_get(url)

    return data.get(
        "properties",
        {}
    )


# =========================================================
# PROPERTY IDS
# =========================================================

def get_property_ids():
    """
    Return the IDs of the required properties:

    Word
    Parts of Speech
    IPA
    """

    properties = get_data_source_properties()

    result = {}

    for property_name in [
        "Word",
        "Parts of Speech",
        "IPA"
    ]:

        property_info = properties.get(
            property_name
        )

        if property_info:

            result[property_name] = (
                property_info["id"]
            )

    return result


# =========================================================
# TEST PAGE
# =========================================================

def test_page(page_id):
    """
    Test reading data from a Notion page.
    """

    data = get_page_data(
        page_id
    )

    print()
    print("==============================")
    print("NOTION PAGE TEST")
    print("==============================")

    print(
        f"Page ID : {data['page_id']}"
    )

    print(
        f"Word    : {data['word']}"
    )

    print(
        f"POS     : {data['pos']}"
    )

    print(
        f"IPA     : {data['ipa']}"
    )

    print("==============================")
    print()

    return data

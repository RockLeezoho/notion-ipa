import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
from urllib.parse import quote


# =========================================================
# CONFIG
# =========================================================

OXFORD_BASE_URL = (
    "https://www.oxfordlearnersdictionaries.com"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 20

# Maximum number of retry attempts when Oxford
# encounters a network error
MAX_RETRIES = 3

# Delay between retry attempts
# attempt 1 -> 0.5s
# attempt 2 -> 1.0s
RETRY_DELAY = 0.5


# =========================================================
# RESULT STATUS
# =========================================================

STATUS_SUCCESS = "success"
STATUS_NOT_FOUND = "not_found"
STATUS_NETWORK_ERROR = "network_error"


# =========================================================
# POS MAPPING
# =========================================================

POS_MAP = {
    "n": "noun",
    "noun": "noun",

    "v": "verb",
    "verb": "verb",

    "adj": "adjective",
    "adjective": "adjective",

    "adv": "adverb",
    "adverb": "adverb",

    "prep": "preposition",
    "preposition": "preposition",
}


SUPPORTED_POS = {
    "noun",
    "verb",
    "adjective",
    "adverb",
    "preposition",
}


def normalize_pos(pos: str) -> str:
    """
    Convert the POS from Notion to Oxford's full POS name.

    Examples:
        n    -> noun
        v    -> verb
        adj  -> adjective
        adv  -> adverb
        prep -> preposition
    """

    if not pos:
        return ""

    pos = pos.strip().lower()

    return POS_MAP.get(pos, "")


# =========================================================
# FETCH OXFORD PAGE
# =========================================================

def fetch_url(url: str):
    """
    Request an Oxford dictionary page.

    Return:

        {
            "status": STATUS_SUCCESS,
            "soup": BeautifulSoup(...)
        }

    or:

        {
            "status": STATUS_NOT_FOUND,
            "soup": None
        }

    or:

        {
            "status": STATUS_NETWORK_ERROR,
            "soup": None
        }

    Rules:

    - 200 -> success
    - 404 -> not found, do not retry
    - Timeout / ConnectionError -> retry
    - Other HTTP errors -> retry
    - After MAX_RETRIES -> network_error
    """

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 404:
                return {"status": STATUS_NOT_FOUND, "soup": None}

            response.raise_for_status()
            return {
                "status": STATUS_SUCCESS,
                "soup": BeautifulSoup(response.text, "html.parser"),
            }

        except requests.exceptions.Timeout:
            print(f"Oxford timeout (attempt {attempt}/{MAX_RETRIES})")
        except requests.exceptions.ConnectionError:
            print(f"Oxford connection error (attempt {attempt}/{MAX_RETRIES})")
        except requests.exceptions.RequestException as error:
            print(
                f"Oxford request error "
                f"(attempt {attempt}/{MAX_RETRIES}): {error}"
            )

        if attempt < MAX_RETRIES:
            delay = RETRY_DELAY * attempt
            print(f"Retrying Oxford in {delay:.1f}s...")
            time.sleep(delay)

    print(f"Oxford request failed after {MAX_RETRIES} attempts.")
    return {"status": STATUS_NETWORK_ERROR, "soup": None}

def find_candidate_urls(word: str):
    """Build possible Oxford entry URLs for a word."""

    word = word.strip().lower()
    if not word:
        return []

    word_encoded = quote(word, safe="")
    base_url = f"{OXFORD_BASE_URL}/definition/english/{word_encoded}"

    return [base_url] + [
        f"{base_url}_{number}"
        for number in range(1, 11)
    ]


# =========================================================
# EXTRACT PAGE TITLE
# =========================================================

def extract_page_title(
    soup: BeautifulSoup
) -> str:

    title = soup.title

    if not title:
        return ""

    return title.get_text(
        " ",
        strip=True
    )


# =========================================================
# CHECK WORD MATCH
# =========================================================

def is_word_match(
    soup: BeautifulSoup,
    word: str
) -> bool:
    """
    Check whether the Oxford page matches the target word.

    The main heading is preferred instead of searching
    the entire page text.
    """

    target = word.strip().lower()

    if not target:
        return False

    # -----------------------------------------------------
    # Method 1: h1
    # -----------------------------------------------------

    h1 = soup.select_one("h1")

    if h1:

        heading = h1.get_text(
            " ",
            strip=True
        ).lower()

        heading = re.sub(
            r"\s+",
            " ",
            heading
        ).strip()

        if heading == target:
            return True

    # -----------------------------------------------------
    # Method 2: page title
    # -----------------------------------------------------

    title = extract_page_title(
        soup
    ).lower()

    if title:

        pattern = (
            rf"^\s*{re.escape(target)}\b"
        )

        if re.search(
            pattern,
            title
        ):
            return True

    return False


# =========================================================
# EXTRACT POS
# =========================================================

def extract_pos(
    soup: BeautifulSoup
) -> str | None:
    """
    Extract the POS of the main entry.

    The entire page text is not searched because Oxford
    may contain other POS entries in the "Other results"
    section.
    """

    # -----------------------------------------------------
    # Method 1: .pos
    # -----------------------------------------------------

    pos_element = soup.select_one(
        ".pos"
    )

    if pos_element:

        text = pos_element.get_text(
            " ",
            strip=True
        ).lower()

        text = re.sub(
            r"\s+",
            " ",
            text
        ).strip()

        normalized = normalize_pos(
            text
        )

        if normalized:
            return normalized

        # Some cases may contain additional text.
        # Example: "noun [countable]"
        for possible_pos in SUPPORTED_POS:

            if re.search(
                rf"\b{re.escape(possible_pos)}\b",
                text
            ):
                return possible_pos

    # -----------------------------------------------------
    # Method 2: find POS near the main heading
    # -----------------------------------------------------

    h1 = soup.select_one("h1")

    if h1:

        parent = h1.parent

        if parent:

            nearby_text = parent.get_text(
                " ",
                strip=True
            ).lower()

            for possible_pos in SUPPORTED_POS:

                if re.search(
                    rf"\b{re.escape(possible_pos)}\b",
                    nearby_text
                ):
                    return possible_pos

    return None


# =========================================================
# EXTRACT BRITISH IPA
# =========================================================

def get_british_ipa(
    soup: BeautifulSoup
) -> str | None:

    element = soup.select_one(
        ".phons_br .phon"
    )

    if not element:
        return None

    ipa = element.get_text(
        " ",
        strip=True
    )

    return ipa or None


# =========================================================
# EXTRACT AMERICAN IPA
# =========================================================

def get_american_ipa(
    soup: BeautifulSoup
) -> str | None:

    element = soup.select_one(
        ".phons_n_am .phon"
    )

    if not element:
        return None

    ipa = element.get_text(
        " ",
        strip=True
    )

    return ipa or None


# =========================================================
# EXTRACT BRITISH AUDIO
# =========================================================

def get_british_audio(
    soup: BeautifulSoup
) -> str | None:

    element = soup.select_one(
        ".phons_br .sound[data-src-mp3]"
    )

    if not element:
        return None

    return element.get(
        "data-src-mp3"
    )


# =========================================================
# EXTRACT AMERICAN AUDIO
# =========================================================

def get_american_audio(
    soup: BeautifulSoup
) -> str | None:

    element = soup.select_one(
        ".phons_n_am .sound[data-src-mp3]"
    )

    if not element:
        return None

    return element.get(
        "data-src-mp3"
    )


# =========================================================
# FORMAT IPA
# =========================================================

def format_ipa(
    british: str | None,
    american: str | None
) -> str:

    parts = []

    if british:

        parts.append(
            f"[BrE] {british}"
        )

    if american:

        parts.append(
            f"\n[AmE] {american}"
        )

    return " ".join(parts)


# =========================================================
# FIND ENTRY BY POS
# =========================================================

def find_entry_by_pos(
    word: str,
    target_pos: str
):
    """
    Find the correct Oxford entry based on:

        Word + POS

    Return:

        {
            "status": "success",
            "word": ...,
            "pos": ...,
            "url": ...,
            "british": ...,
            "american": ...,
            "ipa": ...,
            "british_audio": ...,
            "american_audio": ...
        }

    or:

        {
            "status": "not_found"
        }

    or:

        {
            "status": "network_error"
        }

    Examples:

        initiate + v
            ↓
        initiate_1

        initiate + n
            ↓
        initiate_2
    """

    word = word.strip()
    if not word:
        return {"status": STATUS_NOT_FOUND}

    target_pos = normalize_pos(target_pos)
    if not target_pos:
        return {"status": STATUS_NOT_FOUND}

    candidates = find_candidate_urls(word)
    had_network_error = False
    executor = ThreadPoolExecutor(max_workers=min(8, len(candidates)))
    futures = {
        executor.submit(fetch_url, url): url
        for url in candidates
    }

    try:
        for future in as_completed(futures):
            url = futures[future]

            try:
                result = future.result()
            except Exception as error:
                print(f"Oxford candidate error for {url}: {error}")
                had_network_error = True
                continue

            status = result["status"]
            if status == STATUS_NETWORK_ERROR:
                had_network_error = True
                continue
            if status == STATUS_NOT_FOUND:
                continue

            soup = result["soup"]
            if not soup or not is_word_match(soup, word):
                continue

            current_pos = extract_pos(soup)
            if current_pos != target_pos:
                continue

            british = get_british_ipa(soup)
            american = get_american_ipa(soup)
            if not british and not american:
                continue

            return {
                "status": STATUS_SUCCESS,
                "word": word,
                "pos": current_pos,
                "url": url,
                "british": british,
                "american": american,
                "ipa": format_ipa(british, american),
                "british_audio": get_british_audio(soup),
                "american_audio": get_american_audio(soup),
            }
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    if had_network_error:
        return {"status": STATUS_NETWORK_ERROR}

    return {"status": STATUS_NOT_FOUND}


# =========================================================
# SIMPLE GET IPA
# =========================================================

def get_ipa(
    word: str,
    pos: str
) -> str | None:
    """Return the IPA string for a word and part of speech."""

    entry = find_entry_by_pos(word, pos)

    if entry["status"] != STATUS_SUCCESS:
        return None

    return entry["ipa"]

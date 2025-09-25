from dataclasses import dataclass
from urllib.parse import urljoin
import csv
import time
from selenium import webdriver
from selenium.common import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm

BASE_URL = "https://webscraper.io/"
HOME_URL = urljoin(BASE_URL, "test-sites/e-commerce/more/")


@dataclass
class Product:
    title: str
    description: str
    price: float
    rating: int
    num_of_reviews: int


def parse_product_element(el: WebElement) -> Product:
    """
    Parses a product HTML element to extract relevant data fields.

    Args:
        el: Selenium WebElement representing a product container.

    Returns:
        Product object with extracted details: title, description, price, rating, number of reviews.
    """
    # Extract product title from 'title' attribute of element with class 'title'
    title = (
        el.find_element(By.CLASS_NAME, "title").get_attribute("title").strip()
    )

    # Extract product description text
    description = el.find_element(By.CLASS_NAME, "description").text.strip()

    # Extract price, remove currency symbol, convert to float
    price_text = (
        el.find_element(By.CLASS_NAME, "price").text.strip().replace("$", "")
    )
    price = float(price_text)

    # Count number of stars by counting elements with class 'glyphicon-star' (indicates rating)
    rating = len(el.find_elements(By.CLASS_NAME, "glyphicon-star"))

    # Extract number of reviews from the second paragraph inside element with class 'ratings'
    reviews_text = (
        el.find_element(By.CLASS_NAME, "ratings")
        .find_elements(By.TAG_NAME, "p")[1]
        .text
    )
    num_of_reviews = int(
        reviews_text.split(" ")[0]
    )  # Extract the number from text like "14 reviews"

    return Product(title, description, price, rating, num_of_reviews)


def accept_cookies_if_needed(driver: WebDriver) -> None:
    """
    Checks for cookie consent banner and clicks 'Agree' if present to proceed.

    Args:
        driver: Selenium WebDriver instance.
    """
    try:
        # Wait up to 2 seconds for the cookie consent button to become clickable
        btn = WebDriverWait(driver, 2).until(
            ec.element_to_be_clickable(
                (By.CLASS_NAME, "cookie-consent__agree")
            )
        )
        btn.click()  # Accept cookies to avoid blocking interactions
    except TimeoutException:
        pass  # No cookie consent banner appeared, continue silently


def scroll_and_load_all(driver: WebDriver) -> None:
    """
    Scrolls the page to load all products by repeatedly clicking the 'More' button.

    Args:
        driver: Selenium WebDriver instance.
    """
    while True:
        try:
            # Find the 'More' button which loads additional products
            btn = driver.find_element(By.CLASS_NAME, "btn-primary")

            if btn.is_displayed():
                # Scroll to the button to make sure it's visible
                driver.execute_script(
                    "arguments[0].scrollIntoView(true);", btn
                )
                time.sleep(1)  # Small delay to ensure smooth scrolling

                btn.click()  # Click the button to load more products
                time.sleep(2)  # Wait for new products to load
            else:
                break  # Button not visible means no more products to load
        except (NoSuchElementException, ElementClickInterceptedException):
            break  # Button not found means all products are loaded


def scrape_page(
        driver: WebDriver,
        url: str,
        filename: str,
        use_more_button: bool = False
) -> None:
    """
    Loads a page URL and scrapes all product data, then saves it to CSV.

    Args:
        driver: Selenium WebDriver instance.
        url: URL of the page to scrape.
        filename: CSV filename to save the extracted product data.
        use_more_button: Boolean flag indicating if 'More' button should be clicked to load all products.
    """
    driver.get(url)  # Navigate to the target URL

    accept_cookies_if_needed(driver)  # Handle cookie consent popup if present

    # If specified, load all products by clicking the 'More' button repeatedly
    if use_more_button:
        scroll_and_load_all(driver)

    # Wait until all product thumbnails are present in the DOM (max 10 seconds)
    WebDriverWait(driver, 10).until(
        ec.presence_of_all_elements_located((By.CLASS_NAME, "thumbnail"))
    )

    # Find all product elements on the page
    products = driver.find_elements(By.CLASS_NAME, "thumbnail")
    result = []

    # Iterate over all product elements with a progress bar (tqdm)
    for el in tqdm(products, desc=f"Scraping {filename}"):
        try:
            product = parse_product_element(
                el
            )  # Parse product info from element
            result.append(product)  # Add parsed product to results list
        except Exception as e:
            # Log parse errors but continue processing other products
            print(f"Failed to parse product: {e}")
            continue

    # Write all scraped product data to a CSV file with appropriate headers
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["title", "description", "price", "rating", "num_of_reviews"]
        )
        for product in result:
            writer.writerow(
                [
                    product.title,
                    product.description,
                    product.price,
                    product.rating,
                    product.num_of_reviews
                ]
            )


def get_all_products() -> None:
    """
    Main driver function that sets up Selenium WebDriver and scrapes multiple product pages.

    It scrapes various categories and saves each category to a separate CSV file.
    """
    options = Options()
    options.add_argument("--headless")  # Run Chrome in headless mode (no GUI)
    options.add_argument(
        "--disable-gpu"
    )  # Disable GPU usage (mostly for Windows headless)
    options.add_argument(
        "--no-sandbox"
    )  # Bypass OS security model (useful for Linux servers)

    # Setup ChromeDriver service with webdriver-manager for automatic driver management
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        # Define list of pages to scrape:
        # Each tuple contains (filename_prefix, URL, whether to click "More" button)
        pages = [
            ("home", HOME_URL, False),
            ("computers", urljoin(HOME_URL, "computers"), False),
            ("laptops", urljoin(HOME_URL, "computers/laptops"), True),
            ("tablets", urljoin(HOME_URL, "computers/tablets"), True),
            ("phones", urljoin(HOME_URL, "phones"), False),
            ("touch", urljoin(HOME_URL, "phones/touch"), True),
        ]

        # Loop through each page and scrape products accordingly
        for name, url, use_more in pages:
            scrape_page(driver, url, f"{name}.csv", use_more_button=use_more)
    finally:
        driver.quit()  # Ensure browser is closed regardless of success or error


if __name__ == "__main__":
    get_all_products()

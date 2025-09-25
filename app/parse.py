import logging
from dataclasses import dataclass
from urllib.parse import urljoin
import csv
from selenium import webdriver
from selenium.common import (
    TimeoutException,
    NoSuchElementException, ElementClickInterceptedException,
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

# Base URL for the test e-commerce site
BASE_URL = "https://webscraper.io/"
HOME_URL = urljoin(BASE_URL, "test-sites/e-commerce/more/")


@dataclass
class Product:
    """
    Data structure representing a single product with all required fields.
    """
    title: str
    description: str
    price: float
    rating: int
    num_of_reviews: int


def parse_product_element(el: WebElement) -> Product:
    """
    Extracts product details from a single product HTML container.

    Args:
        el: Selenium WebElement that wraps a single product's information.

    Returns:
        A Product instance with parsed data (title, description, price, rating, reviews).
    """
    title = (
        el.find_element(By.CLASS_NAME, "title").get_attribute("title").strip()
    )
    description = el.find_element(By.CLASS_NAME, "description").text.strip()
    price = float(el.find_element(By.CLASS_NAME, "price").text.strip().replace("$", ""))
    rating = len(el.find_elements(By.CLASS_NAME, "glyphicon-star"))

    # Attempt to extract number of reviews from second <p> tag inside the 'ratings' div
    try:
        reviews_elements = el.find_element(By.CLASS_NAME, "ratings").find_elements(By.TAG_NAME, "p")
        if len(reviews_elements) > 1:
            reviews_text = reviews_elements[1].text.strip()
            parts = reviews_text.split(" ")
            num_of_reviews = int(parts[0]) if parts[0].isdigit() else 0
        else:
            num_of_reviews = 0
    except NoSuchElementException:
        num_of_reviews = 0

    return Product(title, description, price, rating, num_of_reviews)


def accept_cookies_if_needed(driver: WebDriver) -> None:
    """
    Detects and accepts the cookie consent popup if it appears.

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
        WebDriverWait(driver, 5).until(
            ec.invisibility_of_element(btn)
        )
    except TimeoutException:
        pass  # No cookie popup appeared, continue as usual


def scroll_and_load_all(driver: WebDriver) -> None:
    """
    Handles "Load More" button pagination by clicking it repeatedly until all products are loaded.

    Args:
        driver: Selenium WebDriver instance.
    """
    while True:
        try:
            # Wait until "More" button is clickable
            btn = WebDriverWait(driver, 5).until(
                ec.element_to_be_clickable((By.CLASS_NAME, "ecomerce-items-scroll-more"))
            )
        except TimeoutException:
            break  # No more "More" button — all products loaded

        prev_count = len(driver.find_elements(By.CLASS_NAME, "thumbnail"))

        try:
            btn.click()
        except ElementClickInterceptedException:
            # Attempt to close overlay (like cookie banner) if blocking click
            try:
                close_btn = driver.find_element(By.CLASS_NAME, "acceptCookies")
                close_btn.click()
                WebDriverWait(driver, 2).until(ec.invisibility_of_element(close_btn))
                btn.click()
            except (NoSuchElementException, TimeoutException, ElementClickInterceptedException):
                break  # If still blocked, exit loop

        # Wait until more products are added to the DOM
        try:
            WebDriverWait(driver, 10).until(
                lambda d: len(d.find_elements(By.CLASS_NAME, "thumbnail")) > prev_count
            )
        except TimeoutException:
            break  # No new products appeared — stop scrolling


def scrape_page(
        driver: WebDriver,
        url: str,
        filename: str,
        use_more_button: bool = False
) -> None:
    """
    Scrapes product data from a single category page and writes it to a CSV file.

    Args:
        driver: Selenium WebDriver instance.
        url: Full URL of the category page.
        filename: Filename to store the CSV results.
        use_more_button: Whether to click the "More" button to load all products.
    """
    driver.get(url)  # Navigate to the target URL

    accept_cookies_if_needed(driver)  # Handle cookie consent popup if present

    # Attempt to dismiss cookie overlays if still present
    try:
        WebDriverWait(driver, 5).until(
            ec.invisibility_of_element_located((By.CLASS_NAME, "acceptCookies"))
        )
    except TimeoutException:
        pass

    if use_more_button:
        scroll_and_load_all(driver)

    # Ensure all product thumbnails are loaded
    WebDriverWait(driver, 10).until(
        ec.presence_of_all_elements_located((By.CLASS_NAME, "thumbnail"))
    )

    # Collect all product containers
    products = driver.find_elements(By.CLASS_NAME, "thumbnail")
    result = []

    # Parse each product with progress bar
    for element in tqdm(products, desc=f"Scraping {filename}"):
        try:
            product = parse_product_element(
                element
            )  # Parse product info from element
            result.append(product)  # Add parsed product to results list
        except Exception as e:
            # Log parse errors but continue processing other products
            print(f"Failed to parse product: {e}")
            continue

    # Write all extracted data to CSV
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
    Main function that initializes the Selenium WebDriver and scrapes all defined product pages.

    Each page's data is stored in a separate CSV file named after the category.
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
    driver = None

    # Setup error logging
    logging.basicConfig(level=logging.ERROR)

    try:
        # Define which pages to scrape:
        driver = webdriver.Chrome(service=service, options=options)
        pages = [
            ("home", HOME_URL, False),
            ("computers", urljoin(HOME_URL, "computers"), False),
            ("laptops", urljoin(HOME_URL, "computers/laptops"), True),
            ("tablets", urljoin(HOME_URL, "computers/tablets"), True),
            ("phones", urljoin(HOME_URL, "phones"), False),
            ("touch", urljoin(HOME_URL, "phones/touch"), True),
        ]

        # Scrape all defined pages
        for name, url, use_more in pages:
            try:
                scrape_page(driver, url, f"{name}.csv", use_more_button=use_more)
            except Exception as e:
                logging.error(f"Error processing page {url}: {e}", exc_info=True)
    finally:
        if driver is not None:
            driver.quit()  # Ensure browser closes on exit


if __name__ == "__main__":
    get_all_products()

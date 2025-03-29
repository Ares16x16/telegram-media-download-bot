import requests
from bs4 import BeautifulSoup
import re
import json
import time
from urllib.parse import urljoin
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def fetch_monthly_news(year, month):
    """Fetch news list for the specified year and month from Nogizaka46 website."""
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        # Set language to Japanese
        chrome_options.add_argument("--lang=ja")
        chrome_options.add_argument("--accept-lang=ja")

        # Set browser language preference header
        chrome_options.add_experimental_option(
            "prefs", {"intl.accept_languages": "ja,ja_JP"}
        )

        driver = webdriver.Chrome(options=chrome_options)
        driver.get("https://www.nogizaka46.com")
        driver.add_cookie({"name": "wovn_selected_lang", "value": "ja"})
        driver.add_cookie({"name": "language", "value": "ja"})

        url = (
            f"https://www.nogizaka46.com/s/n46/news/list?ima=0623&dy={year}{month:02d}"
        )
        print(f"Loading news page with Selenium: {url}")

        driver.get(url)

        # Wait for the news items to load (up to 15 seconds)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".m--nsone"))
            )
        except:
            print(
                "Timed out waiting for news items to load, proceeding with what we have"
            )
        time.sleep(1)

        html_content = driver.page_source
        driver.quit()

        soup = BeautifulSoup(html_content, "html.parser")

        items = soup.select(".m--nsone")
        print(f"Found {len(items)} news items")

        if not items:
            items = soup.select("div[class*='nsone']")
            print(f"Alternative selector found {len(items)} items")

            if not items:
                items = soup.select("a[href*='/news/detail/']")
                print(f"Link selector found {len(items)} items")

        result = []
        for item in items:
            try:
                link = item if item.name == "a" else item.find("a")
                if not link or not link.has_attr("href"):
                    continue

                url = link["href"]
                if "/news/detail/" not in url:
                    continue

                # Make URL absolute
                if not url.startswith("http"):
                    url = urljoin("https://www.nogizaka46.com", url)

                # title
                title_elem = item.select_one(".m--nsone__ttl")
                title = title_elem.get_text(strip=True) if title_elem else ""

                if not title:
                    title_elem = item.select_one("[class*='ttl']")
                    title = title_elem.get_text(strip=True) if title_elem else ""

                if not title and link:
                    title = link.get_text(strip=True)

                # date
                date_elem = item.select_one(".m--nsone__date") or item.select_one(
                    "[class*='date']"
                )
                date = date_elem.get_text(strip=True) if date_elem else ""

                # category
                cat_elem = item.select_one(".m--nsone__cat__name") or item.select_one(
                    "[class*='cat']"
                )
                category = cat_elem.get_text(strip=True) if cat_elem else ""

                if title:
                    result.append(
                        {
                            "title": title,
                            "date": date,
                            "type": category,
                            "url": url,
                        }
                    )
            except Exception as e:
                print(f"Error extracting news item: {e}")

        return result

    except Exception as e:
        print(f"Error during Selenium fetch: {e}")
        # Fall back
        return fetch_news_from_api(year, month)


def fetch_news_from_api(year, month):
    """Fallback method to fetch news from API if Selenium fails."""
    api_url = "https://www.nogizaka46.com/s/n46/api/list/news"
    params = {
        "ima": "0623",
        "dy": f"{year}{month:02d}",
        "rw": "30",
        "st": "0",
        "callback": "",
    }

    print(f"Trying API fallback: {api_url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": f"https://www.nogizaka46.com/s/n46/news/list?ima=0623&dy={year}{month:02d}",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ja,ja_JP;q=0.9,en;q=0.8",  # Request Japanese content
        "X-Requested-With": "XMLHttpRequest",
    }

    try:
        session = requests.Session()

        session.cookies.set("wovn_selected_lang", "ja", domain=".nogizaka46.com")
        session.cookies.set("language", "ja", domain=".nogizaka46.com")

        main_url = (
            f"https://www.nogizaka46.com/s/n46/news/list?ima=0623&dy={year}{month:02d}"
        )
        session.get(main_url, headers=headers)

        resp = session.get(api_url, params=params, headers=headers)

        if resp.status_code != 200:
            print(f"API error: {resp.status_code}")
            return []

        try:
            data = json.loads(resp.text)
            if "data" in data and isinstance(data["data"], list):
                news_list = data["data"]
                result = []

                for item in news_list:
                    title = item.get("title", "")
                    date = item.get("date", "")
                    category = item.get("cate", "")
                    news_id = item.get("code", "")
                    detail_url = f"https://www.nogizaka46.com/s/n46/news/detail/{news_id}?ima=0623"

                    if title:
                        result.append(
                            {
                                "title": title,
                                "date": date,
                                "type": category,
                                "url": detail_url,
                            }
                        )

                return result
        except json.JSONDecodeError:
            print("Failed to parse API response as JSON")
    except Exception as e:
        print(f"API fetch error: {e}")

    return []


def fetch_news_detail(url):
    """Fetch detail HTML from a Nogizaka46 news article."""
    try:
        # Use Selenium to fetch the news detail page
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--lang=ja")
        chrome_options.add_argument("--accept-lang=ja")
        chrome_options.add_experimental_option(
            "prefs", {"intl.accept_languages": "ja,ja_JP"}
        )

        driver = webdriver.Chrome(options=chrome_options)
        driver.get("https://www.nogizaka46.com")
        driver.add_cookie({"name": "wovn_selected_lang", "value": "ja"})
        driver.add_cookie({"name": "language", "value": "ja"})

        print(f"Loading news detail page: {url}")

        driver.get(url)

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".m--nd"))
            )
        except:
            print("Timed out waiting for news content to load")

        time.sleep(1)

        html_content = driver.page_source
        driver.quit()

        soup = BeautifulSoup(html_content, "html.parser")

        # title
        title_elem = soup.select_one(".c--dettl.f--head.a--tx.js-tdi")
        title_text = title_elem.get_text(strip=True) if title_elem else ""

        # date and type
        post_data_elems = soup.select(".m--pstdata__one")
        date_text = ""
        category_text = ""

        if post_data_elems and len(post_data_elems) >= 2:
            date_text = post_data_elems[0].get_text(strip=True)
            category_text = post_data_elems[1].get_text(strip=True)

        result = []
        if title_text:
            result.append(f"📰 {title_text}")
        if date_text:
            result.append(f"📅 {date_text}")
        if category_text:
            result.append(f"🏷️ {category_text}")

        # article content
        content_elem = soup.select_one(".m--nd.a--op.js-pos.is-v")
        if not content_elem:
            content_elem = soup.select_one(
                ".m--nd.a--op.js-pos"
            )  # Fallback if 'is-v' is missing

        if content_elem:
            article_content = extract_article_content(content_elem)
            if article_content:
                result.append(article_content)

        return "\n\n".join(result) if result else "No detail found."

    except Exception as e:
        print(f"Error fetching news detail: {e}")

        # Fallback
        try:
            session = requests.Session()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept-Language": "ja,ja_JP;q=0.9,en;q=0.8",
            }
            session.cookies.set("wovn_selected_lang", "ja", domain=".nogizaka46.com")
            session.cookies.set("language", "ja", domain=".nogizaka46.com")

            resp = session.get(url, headers=headers)
            if resp.status_code != 200:
                return "Failed to fetch details."

            soup = BeautifulSoup(resp.text, "html.parser")

            # title
            title_elem = soup.select_one(".c--dettl.f--head.a--tx.js-tdi")
            title_text = title_elem.get_text(strip=True) if title_elem else ""

            # date and type
            post_data_elems = soup.select(".m--pstdata__one")
            date_text = ""
            category_text = ""

            if post_data_elems and len(post_data_elems) >= 2:
                date_text = post_data_elems[0].get_text(strip=True)
                category_text = post_data_elems[1].get_text(strip=True)

            result = []
            if title_text:
                result.append(f"📰 {title_text}")
            if date_text:
                result.append(f"📅 {date_text}")
            if category_text:
                result.append(f"🏷️ {category_text}")

            # article content
            content_elem = soup.select_one(".m--nd.a--op.js-pos.is-v")
            if not content_elem:
                content_elem = soup.select_one(".m--nd.a--op.js-pos")  # Fallback

            if content_elem:
                article_content = extract_article_content(content_elem)
                if article_content:
                    result.append(article_content)

            return "\n\n".join(result) if result else "No detail found."
        except Exception as e:
            print(f"Fallback fetch failed: {e}")
            return "Failed to fetch article details."


def extract_article_content(element):
    """
    Extract article content preserving links and structure.
    Specifically designed to handle Nogizaka46 article content.
    """
    if not element:
        return ""

    def process_node(node):
        if isinstance(node, str):
            return node.strip()

        if node.name == "br":
            return "\n"

        elif node.name == "a" and node.has_attr("href"):
            href = node.get("href", "")
            if not href or href.startswith("#"):  # Skip empty or anchor links
                return node.get_text(strip=True)

            # Make URLs absolute
            if not href.startswith(("http://", "https://")):
                if href.startswith("/"):
                    href = f"https://www.nogizaka46.com{href}"
                else:
                    href = f"https://www.nogizaka46.com/{href}"

            link_text = node.get_text(strip=True)
            return f"[{link_text}]({href})"

        # For block elements, add an extra newline
        elif node.name in ["p", "div", "h1", "h2", "h3", "h4", "h5", "h6"]:
            result = []
            for child in node.children:
                processed = process_node(child)
                if processed:
                    result.append(processed)
            text = " ".join(result)
            # Only add extra newlines for non-empty blocks
            return f"\n{text}\n" if text.strip() else ""

        else:
            result = []
            for child in node.children:
                processed = process_node(child)
                if processed:
                    result.append(processed)
            return " ".join(result)

    content = process_node(element)

    # Clean up multiple consecutive spaces and newlines
    content = re.sub(r" +", " ", content)  # Multiple spaces to single space
    content = re.sub(r"\n\s+", "\n", content)  # Space after newline
    content = re.sub(r"\s+\n", "\n", content)  # Space before newline
    content = re.sub(
        r"\n{3,}", "\n\n", content
    )  # More than 2 newlines to double newline

    return content.strip()

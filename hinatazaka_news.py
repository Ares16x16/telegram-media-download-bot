import requests
from bs4 import BeautifulSoup
import re


def fetch_monthly_news(year, month):
    """Fetch news list for the specified year and month from Hinatazaka46 website."""
    base_url = "https://www.hinatazaka46.com/s/official/news/list?ima=0000&dy="
    y_m = f"{year}{month:02d}"
    url = base_url + y_m
    resp = requests.get(url)
    if resp.status_code != 200:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    items = soup.select(".p-news__item")
    result = []

    for item in items:
        link_tag = item.find("a", href=True)
        if not link_tag:
            continue

        detail_url = link_tag["href"]
        full_url = "https://www.hinatazaka46.com" + detail_url

        date_elem = item.select_one(".c-news__date")
        category_elem = item.select_one(".c-news__category")
        title_elem = item.select_one(".c-news__text")

        date = date_elem.get_text(strip=True) if date_elem else ""
        category = category_elem.get_text(strip=True) if category_elem else ""
        title = title_elem.get_text(strip=True) if title_elem else ""

        # Skip items with empty titles
        if not title:
            continue

        result.append(
            {
                "title": title,
                "date": date,
                "type": category,
                "url": full_url,
            }
        )

    return result


def fetch_news_detail(url):
    """Fetch detail HTML from a Hinatazaka46 news article."""
    resp = requests.get(url)
    if resp.status_code != 200:
        return "Failed to fetch details."

    soup = BeautifulSoup(resp.text, "html.parser")

    article_container = soup.select_one(".l-maincontents--news-detail")
    if not article_container:
        return "No article found."

    title_elem = article_container.select_one(".c-article__title")
    title_text = title_elem.get_text(strip=True) if title_elem else ""

    info_section = article_container.select_one(".p-article__info")
    if info_section:
        date_elem = info_section.select_one(".c-news__date")
        category_elem = info_section.select_one(".c-news__category")
        date_text = date_elem.get_text(strip=True) if date_elem else ""
        category_text = category_elem.get_text(strip=True) if category_elem else ""
    else:
        date_text = ""
        category_text = ""

    # member tag
    tag_section = article_container.select_one(".c-article__tag")
    if tag_section:
        # Process member links
        member_links = []
        for link in tag_section.find_all("a", href=True):
            href = link.get("href")
            # Make absolute URLs
            if href and not href.startswith(("http://", "https://")):
                href = f"https://www.hinatazaka46.com{href}"

            member_name = link.get_text(strip=True)
            if member_name:
                member_links.append(f"[{member_name}]({href})")

        # Join member links with commas
        members_text = ", ".join(member_links) if member_links else ""
        # Get tag title if present (usually "メンバー")
        tag_title = tag_section.find("b")
        tag_title_text = tag_title.get_text(strip=True) if tag_title else ""

        if tag_title_text and members_text:
            tag_full_text = f"{tag_title_text}: {members_text}"
        else:
            tag_full_text = members_text or tag_title_text
    else:
        tag_full_text = ""

    result = []
    if title_text:
        result.append(f"📰 {title_text}")
    if date_text:
        result.append(f"📅 {date_text}")
    if category_text:
        result.append(f"🏷️ {category_text}")
    if tag_full_text:
        result.append(f"🔖 {tag_full_text}")

    content_elem = article_container.select_one(".p-article__text")

    if content_elem:
        # extract all text and links
        article_content = extract_article_content(content_elem)
        if article_content:
            result.append(article_content)

    return "\n\n".join(result) if result else "No detail found."


def extract_article_content(element):
    """
    Extract article content preserving links and structure.
    Specifically designed to handle the p-article__text element.
    """
    if not element:
        return ""

    text_parts = []

    def process_node(node):
        if isinstance(node, str):
            return node.strip()

        if node.name == "br":
            return "\n"

        elif node.name == "a" and node.has_attr("href"):
            href = node.get("href", "")
            # Skip anchor links
            if not href or href.startswith("#"):
                return node.get_text(strip=True)

            # Make URLs absolute
            if not href.startswith(("http://", "https://")):
                if href.startswith("/"):
                    href = f"https://www.hinatazaka46.com{href}"
                else:
                    href = f"https://www.hinatazaka46.com/{href}"

            link_text = node.get_text(strip=True)
            return f"[{link_text}]({href})"

        result = []
        for child in node.children:
            processed = process_node(child)
            if processed:
                result.append(processed)

        return " ".join(result)

    content = process_node(element)

    # Clean up the content:
    # 1. Replace multiple spaces with a single space
    content = re.sub(r" +", " ", content)
    # 2. Normalize line breaks (preserve intentional breaks but remove extras)
    content = re.sub(r"\n\s+", "\n", content)
    content = re.sub(r"\s+\n", "\n", content)
    content = re.sub(r"\n{3,}", "\n\n", content)

    return content.strip()


def extract_content_with_links(element):
    """Extract text content from an element while preserving links as markdown."""
    if not element:
        return ""

    content_parts = []

    for child in element.contents:
        if isinstance(child, str):
            text = child.strip()
            if text:
                content_parts.append(text)

        elif child.name == "br":
            content_parts.append("\n")

        elif child.name == "a" and child.has_attr("href"):
            # Link - convert to markdown
            href = child.get("href", "")
            if not href or href.startswith("#"):
                # Skip empty or anchor links
                content_parts.append(child.get_text(strip=True))
                continue

            # Make absolute URLs
            if not href.startswith(("http://", "https://")):
                if href.startswith("/"):
                    href = f"https://www.hinatazaka46.com{href}"
                else:
                    href = f"https://www.hinatazaka46.com/{href}"

            link_text = child.get_text(strip=True)
            if link_text:
                content_parts.append(f"[{link_text}]({href})")

        elif child.name in [
            "p",
            "div",
            "span",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        ]:
            sub_content = extract_content_with_links(child)
            if sub_content:
                content_parts.append(sub_content)

        else:
            # Other elements - just get their text
            text = child.get_text(strip=True)
            if text:
                content_parts.append(text)

    # Join all parts, collapse multiple spaces and newlines
    content = " ".join(content_parts)
    content = re.sub(r"\s+", " ", content)
    return content.strip()

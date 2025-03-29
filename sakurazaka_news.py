import requests
from bs4 import BeautifulSoup
import re


def fetch_monthly_news(year, month):
    """Fetch news list for the specified year and month."""
    base_url = "https://sakurazaka46.com/s/s46/news/list?ima=0000&dy="
    y_m = f"{year}{month:02d}"
    url = base_url + y_m
    resp = requests.get(url)
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select("li[class^='cate-']")
    result = []
    for itm in items:
        link_tag = itm.find("a", href=True)
        if not link_tag:
            continue
        detail_url = link_tag["href"]
        full_url = "https://sakurazaka46.com" + detail_url
        title_elm = itm.select_one(".lead")
        date_elm = itm.select_one(".date")
        type_elm = itm.select_one(".type")

        title = title_elm.get_text(strip=True) if title_elm else ""
        date = date_elm.get_text(strip=True) if date_elm else ""
        news_type = type_elm.get_text(strip=True) if type_elm else ""

        # Skip items with empty titles
        if not title or title == "No title":
            continue

        result.append(
            {
                "title": title,
                "date": date,
                "type": news_type,
                "url": full_url,
            }
        )
    return result


def fetch_news_detail(url):
    """Fetch detail HTML from the col-c post section."""
    resp = requests.get(url)
    if resp.status_code != 200:
        return "Failed to fetch details."

    soup = BeautifulSoup(resp.text, "html.parser")

    # Find the main content section
    detail_section = soup.select_one(".col-c.post")
    if not detail_section:
        return "No detail found."

    # type
    title = detail_section.select_one(".title")
    title_text = title.get_text(strip=True) if title else ""

    # date
    date = detail_section.select_one(".date")
    date_text = date.get_text(strip=True) if date else ""

    # title
    lead = detail_section.select_one(".lead")
    lead_text = lead.get_text(strip=True) if lead else ""

    result = []
    if title_text:
        result.append(f"📰 {title_text}")
    if date_text:
        result.append(f"📅 {date_text}")
    if lead_text:
        result.append(f"📝 {lead_text}")

    # Get the article content - improved version to ensure all content is captured
    article = detail_section.select_one(".article")

    if article:
        # Get the article content with links preserved - this will process the entire article
        article_content = extract_content_with_links(article)
        if article_content:
            result.append(article_content)

    # If no content was found, use the full text from detail section as fallback
    # if len(result) <= 3:  # Only title, date, and lead were found
    #    all_text = detail_section.get_text("\n", strip=True)
    #    if all_text:
    #        result.append(all_text)

    # Return the combined result with proper spacing
    return "\n\n".join(result) if result else "No detail found."


def extract_content_with_links(element):
    """Extract text content from an element while preserving links as markdown."""
    if not element:
        return ""

    content_parts = []

    # First, handle the direct text nodes of this element
    for child in element.contents:
        if isinstance(child, str):
            # Direct text node
            text = child.strip()
            if text:
                content_parts.append(text)

        elif child.name == "br":
            # Line breaks
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
                    href = f"https://sakurazaka46.com{href}"
                else:
                    href = f"https://sakurazaka46.com/{href}"

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
            # extract content from these elements
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

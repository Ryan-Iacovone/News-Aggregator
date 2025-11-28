# Standard library imports
import os
import re
import random
from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Third-party imports
import pandas as pd
import feedparser
import pytz
from pathlib import Path
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from dateutil import parser
import markdown
from sqlalchemy import create_engine, text

# Gathering XML articles
def retrieve_xml_articles(xml_links):
        
    chrome_options = Options()
    chrome_options.add_argument("--headless")                  # Run in headless mode
    chrome_options.add_argument("--disable-gpu")               # Disable GPU (usually helpful on Windows)
    chrome_options.add_argument("--no-sandbox")  

    driver = webdriver.Chrome()

    # Initalizing news articles df  
    new_articles = pd.DataFrame(columns=["title", "link", "source", "language", "published_date", "last_modified", "keywords"])  

    for url in xml_links:
        driver.get(url)
        xml_site = driver.page_source
        soup = BeautifulSoup(xml_site, "lxml-xml")

        articles = soup.find_all("url")

        for article in articles:

            title = article.find("news:title").get_text()
            link = article.find("loc").text # get_text doesn't work here for links 
            source = article.find("news:name").get_text()
            language = article.find("news:language").get_text()
            published_date = article.find("news:publication_date").get_text()
            last_modified = article.find("lastmod").get_text(strip=True) if article.find("lastmod") else None  
            keywords = article.find("news:keywords").get_text(strip=True) if article.find("news:keywords") else None


            tempdf = pd.DataFrame({
            "title": title,
            "link": link,
            "source": source,
            "language": language,
            "published_date": published_date,
            "last_modified": last_modified,
            "keywords": [keywords]}, index=[0]) 

            new_articles = pd.concat([new_articles, tempdf], ignore_index=True)

    driver.quit()

    # Use .replace when replacing entire value, else use str.replace which incoroprates regex
    new_articles["language"] = new_articles["language"].replace("en", "eng") 

    new_articles = new_articles[new_articles['language'] == 'eng']
    
    return new_articles


# Gathering RSS articles
def retrieve_rss_feeds(rss_urls_list):
    rss_stories = pd.DataFrame(columns=["title", "summary", "link", "published_date", "source"])

    for rss_url in rss_urls_list:

        # Parse the feed
        feed = feedparser.parse(rss_url)

        for entry in feed.entries: # Figure out way to limit entires

            tempdf = pd.DataFrame({
            "title": entry.title,
            "link": entry.link,
            "summary": entry.description,
            "published_date": entry.published,
            "source": feed.channel.title}, index=[0]) 
            
            rss_stories = pd.concat([rss_stories, tempdf], ignore_index=True)

    return rss_stories


# Defining how to normalize dates in a really simple way
def normalize_date(x):
    return parser.parse(x).astimezone(tz=None)


# Extracting keywords for specific articles using the links variable 
def extract_keywords(row):
    source = row['source']
    link = row['link']

    # Associated Press
    if source == "Associated Press":
        if "article/" in link:
            keywords = ", ".join(link.split("article/")[1].split("-")[:-1])
            return keywords
        else:
            return None

    # WSJ sources
    elif source in ["WSJ.com: World News", "Technology - WSJ.com"]:
        keywords = ", ".join(link.split("/")[-1].split("-")[:-1])
        return keywords

    # All other sources
    else:
        return row['keywords']



# Mapping a cateogry to each article based on 
def extract_categories(df):

    category_keywords = {
        "China": ["china", "beijing", "xi", "taiwan"],
        "Semiconductors": ["semiconductor", "chip", "nvidia", "intel", "amd"],
        "Technology": ["ai", "data", "cloud", "software", "technology"],
        "Politics": ["election", "government", "policy", "congress"],
        "Finance": ["stock", "market", "finance", "economy", "inflation"]}

    df['category'] = None

    for i, row in df.iterrows():

        # Safely build combined text (handle NaN)
        title = '' if pd.isna(row.get('title')) else str(row['title'])
        summary = '' if pd.isna(row.get('summary')) else str(row['summary'])
        keywords = '' if pd.isna(row.get('keywords')) else str(row['keywords'])
        combined_text = " ".join([title, keywords, summary]).lower()

        # Initialize matched_category state to none
        matched_category = None

        for category, kw_list in category_keywords.items():
            if any(re.search(rf"\b{kw}\b", combined_text) for kw in kw_list):
                matched_category = category
                df.at[i, 'category'] = matched_category  # Use .at instead of loc or iloc
                break # exiting the loop on first match

        # Default fallback
        if not matched_category:
            df.at[i, 'category'] = "Other"

    return df



# Taking my cleaned df and converting it into a clean markdown output

def df_to_markdown(df):

    # Grabbing unique categories from sqlite db
    categories = df['category'].unique().tolist() 

    # Build markdown string
    markdown_output = f"# 📰 Demolition Daily\n\n"

    # list of emojis to itterate through for fun!
    news_emojis = ["🆕", "📰", "🌎", "📢", "🖥️", "🗃️", "🗞️"] 

    for category in categories:
        subset = df[df["category"] == category]
        if subset.empty:
            continue

        markdown_output += f"""<h2 style="text-decoration: underline; font-size: 28px; margin-top: 30px;">{category}</h2> \n\n"""

        for i, row in subset.iterrows():
            # Handle summary / keywords fallback
            summary_text = None
            if pd.notna(row.get('summary')) and str(row['summary']).strip():
                summary_text = row['summary']
            elif pd.notna(row.get('keywords')) and str(row['keywords']).strip():
                summary_text = row['keywords']
            else:
                summary_text = 'No summary available.'

            # Handle source field gracefully
            source = row.get('source', 'Unknown Source')

            # Build the visually grouped “Card” markdown block
            markdown_output += (
                f"> ### {random.choice(news_emojis)} [{row['title']}]({row['link']})\n"
                f"> **Source:** {source}  \n"
                f"> **Published:** {row['published_date']}  \n"
                f"> **Tags:** {summary_text}\n\n"
            )

    # Write to markdown file
    output_path = Path("news_digest.md")
    output_path.write_text(markdown_output, encoding="utf-8")

    return print(f"✅ Markdown file generated at: {output_path.resolve()} \n")


def send_markdown_as_email(markdown_path, email_sender, email_pass, email_to, today_date):
    with open(markdown_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    # Converting markdown file to HTML (actually works pretty well!)
    html = markdown.markdown(md_text)

    msg = MIMEMultipart("alternative")
    msg["From"] = email_sender
    msg["To"] = ", ".join(email_to)  # Convert list to header string
    msg["Subject"] = f"Demolitoin Daily — {today_date}"

    msg.attach(MIMEText(md_text, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(email_sender, email_pass)
        server.send_message(msg)

    return print("Email successfully sent!")
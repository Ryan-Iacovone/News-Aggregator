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
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from dateutil import parser
import markdown
from sqlalchemy import create_engine, text

# Local imports
from functions import *


# Configuration / constants
engine = create_engine("sqlite:///articles.db")
TIMEZONE = pytz.timezone('America/New_York')

# Load environment variables
load_dotenv()


# Reading in XML articles
with engine.connect() as connection:
    xml_links = pd.read_sql_query(
        text("""SELECT article_links FROM article_sources" \
        "where source_type == 'XML'""" ), connection)   
xml_links_list = xml_links['article_links'].tolist()

new_articles = retrieve_xml_articles(xml_links_list)


# Reading in RSS articles
with engine.connect() as connection:
    rss_links = pd.read_sql_query(
        text("""SELECT article_links FROM article_sources" \
        "where source_type == 'RSS'""" ), connection)
rss_links_list = rss_links['article_links'].tolist()

rss_stories = retrieve_rss_feeds(rss_links_list)


# comining articles sources together 
combined_articles = pd.concat([new_articles, rss_stories], ignore_index=True)

#### Doing some data cleaning on combined articles ####

# Normalizing dates across article sources
combined_articles['published_date'] = combined_articles['published_date'].apply(normalize_date)

# Forcing everything into EST for consistency
combined_articles['published_date'] = pd.to_datetime(combined_articles['published_date'], errors='coerce').dt.tz_convert(TIMEZONE)


# Extracting keywords from the links variable 
combined_articles['keywords'] = combined_articles.apply(extract_keywords, axis=1)

# Extracting the categories from each article based on title, keywords, and summary
combined_articles = extract_categories(combined_articles)


# manually input a separate category for powerbi 
combined_articles.loc[combined_articles['source'] == "Microsoft Power BI Blog | Microsoft Power BI", 'category'] = "PowerBi"

# Filtering out all news articles that didn't get assigned a caetegory
cleaned_articles = combined_articles[combined_articles['category'] != 'Other']

# Capitalizes all the keywords that are in list format
cleaned_articles['keywords'] = cleaned_articles['keywords'].apply(
    lambda x: ", ".join(w.strip().capitalize() for w in x.split(",")) if isinstance(x, str) else x)


#### Uploading the clean dataframe to my SQL db, ensuring I don't add duplicates ####
local_time = datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')

cleaned_articles['upload_date'] = local_time

with engine.connect() as connection:
    articles_db = pd.read_sql_query(
        text("SELECT * FROM news_articles"),connection,
        parse_dates=['published_date', 'last_modified', 'upload_date'])

articles_db = articles_db.drop(columns=["id"])

# Using the link variable to check for duplicates
combined = pd.concat([articles_db, cleaned_articles]).drop_duplicates(subset="link")

# Filtering the combined data to only include this batches articles that are not duplicates
final_output = combined[combined['upload_date'] == local_time]

# uploading the final output df to SQL DB
final_output.to_sql(name="news_articles", con=engine, if_exists='append', index=False)



#### Taking my cleaned df and converting it into a clean markdown output ####
df_to_markdown(final_output)

#### Sending email to recipients with Markdown file as body ####

# Gathering email info from .env file
email_pass = os.getenv("email_pass") 
email_sender = os.getenv("email_sender") 

# Grabbing email recipients dynamically from SQL
with engine.connect() as connection:
    email_recipients = pd.read_sql_query(
        text("""SELECT emails FROM email_recipients""" ), connection)

email_recipients = email_recipients['emails'].tolist()

# Grabbing today's date as a string for the subject
today_date = datetime.now().strftime("%A, %B %d, %Y")

# Taking that Markdown file we saved above, converting it to HTML and sending as an email
send_markdown_as_email("news_digest.md", email_sender, email_pass, email_recipients, today_date)
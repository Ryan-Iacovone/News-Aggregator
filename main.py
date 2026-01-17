# Standard library imports
import os
import re
import random
from datetime import datetime
from zoneinfo import ZoneInfo
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Third-party imports
import pandas as pd
import feedparser
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
today = datetime.now(tz=ZoneInfo("UTC")).strftime('%Y-%m-%d %H:%M:%S') + ".000000" # Grabbing today's date in UTC format with extra format for storage in sqlite 
   
# Loading in environment variables
load_dotenv()

# Reading in XML article sources
with engine.connect() as connection:
    xml_links = pd.read_sql_query(
        text("""SELECT article_links FROM article_sources
                where source_type == 'XML'""" ), connection)   
xml_links_list = xml_links['article_links'].tolist()

news_articles = retrieve_xml_articles(xml_links_list)


# Reading in RSS article sources
with engine.connect() as connection:
    rss_links = pd.read_sql_query(
        text("""SELECT article_links FROM article_sources
        where source_type == 'RSS'"""), connection)
rss_links_list = rss_links['article_links'].tolist()

rss_stories = retrieve_rss_feeds(rss_links_list)


# Combine RSS and regular news articles together in 1 df 
combined_articles = pd.concat([news_articles, rss_stories], ignore_index=True)


######### Doing some data cleaning on the combined articles df #########

# Normalizing published dates to consistent datetime format (keeps timezone differences)
combined_articles['published_date'] = combined_articles['published_date'].apply(normalize_date)

# Converting all dates into proper datetimes and UTC for consistency (UTC = True converts dates that are not utc to utc)
combined_articles['published_date'] = pd.to_datetime(combined_articles['published_date'], utc=True)

# Extracting keywords from the links variable from AP and WSJ articles specifically
combined_articles['keywords'] = combined_articles.apply(extract_keywords, axis=1)

# Assigning each article a category based on the title, keywords, and summary
combined_articles = extract_categories(combined_articles)

# Manually inputing a separate category for powerbi 
combined_articles.loc[combined_articles['source'] == "Microsoft Power BI Blog | Microsoft Power BI", 'category'] = "PowerBi"

# Filtering out all news articles that didn't get assigned a caetegory
cleaned_articles = combined_articles[combined_articles['category'] != 'Other']

# Capitalizing all the keywords that are in list format
cleaned_articles.loc[:, 'keywords'] = cleaned_articles['keywords'].apply(
    lambda x: ", ".join(w.strip().capitalize() for w in x.split(","))
    if isinstance(x, str) else x)

# Using a .copy to avoid SettingWithCopyWarning when I add new variable
cleaned_articles = cleaned_articles.copy()

# Applying todays date as the uploaded date 
cleaned_articles["upload_date"] = today


######### Uploading the clean dataframe to my SQL db, ensuring I don't add duplicates #########

# Reading in all articles from the db (Could do the date filtering here instead of in python)
engine = create_engine("sqlite:///articles.db")
with engine.connect() as connection:
    articles_db = pd.read_sql_query(
        text("""SELECT * FROM news_articles"""),connection)
        #parse_dates=['published_date', 'upload_date'])
    
# Localizing the date variables from sqlite into UTC
articles_db["published_date"] = (
    pd.to_datetime(articles_db["published_date"])
    .dt.tz_localize("UTC"))

articles_db["upload_date"] = (
    pd.to_datetime(articles_db["upload_date"])
    .dt.tz_localize("UTC"))

# Dropping unnecessary id column
articles_db = articles_db.drop(columns=["id"])

# Using the link variable to check for duplicates
combined = pd.concat([articles_db, cleaned_articles]).drop_duplicates(subset="link")

# Filtering the combined data to only include this batch's articles that are not duplicates
final_output = combined[combined['upload_date'] == today]

# uploading the final output df to SQL DB
final_output.to_sql(name="news_articles", con=engine, if_exists='append', index=False)


# After uploading final_output to sqlite db I convert dates to EST for article viewing
final_output = final_output.copy() # avoiding copy error
final_output["published_date"] = final_output["published_date"].dt.tz_convert("US/Eastern")

# Making the EST published date more readable for the markdown file
final_output["published_date"] = final_output["published_date"].dt.strftime("%B %d, %I:%M %p")  # January 16, 11:57 PM


######### Taking my cleaned combined df and converting it into a structured markdown file #########
df_to_markdown(final_output)

######### Sending news letter email to recipients with Markdown file as body #########

# Gathering email info from .env file
email_pass = os.getenv("email_pass") 
email_sender = os.getenv("email_sender") 

# Grabbing email recipients dynamically from SQL
with engine.connect() as connection:
    email_recipients = pd.read_sql_query(
        text("""SELECT emails 
             FROM email_recipients"""), connection)
email_recipients = email_recipients['emails'].tolist()

# Grabbing today's date in EST (local) time formatted as readable string  
today_date = datetime.now(tz=ZoneInfo("US/Eastern")).strftime("%A, %B %d, %Y")

# Taking that Markdown file we saved above, converting it to HTML and sending as an email
#send_markdown_as_email("news_digest.md", email_sender, email_pass, email_recipients, today_date)
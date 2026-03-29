# News Aggregator

A simple Python application that scrapes news articles from multiple sources, aggregates them, and stores them in a SQLite database for easy querying.

## Features

- **Multiple RSS/HTML sources** – Add new feeds or sites with minimal configuration.
- **Duplicate detection** – Uses article title and URL hash to avoid storing the same article twice.
- **Timezone handling** – All timestamps are stored in UTC and can be displayed in local time.
- **Command‑line interface** – Run `python -m news_aggregator.run` to fetch and store the latest articles.

## Installation

```bash
# Clone the repo
git clone https://github.com/your-username/news-aggregator.git
cd news-aggregator

# Initialize uv and install dependencies
uv init
uv sync
```

## Usage

```bash
# Run the aggregator
python -m news_aggregator.run
```

The application will create a `data/news.db` SQLite database in the project root and populate it with scraped articles.

## Configuration

Feed URLs are defined in `news_aggregator/config.py`. Add a new feed by appending a dictionary to the `FEEDS` list:

```python
FEEDS = [
    {
        "name": "Example News",
        "url": "https://example.com/rss",
    },
    # Add more feeds here
]
```

## Testing

Run the test suite with:

```bash
pytest tests/
```

## Contributing

Pull requests are welcome! Please open an issue or PR and follow the project's coding style.

---

© 2026 News Aggregator. All rights reserved.

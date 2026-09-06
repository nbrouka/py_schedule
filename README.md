# Schedule Parser

A Python-based tool for extracting teacher schedules from university schedule documents using pluggable storage backends (Google Drive, Nextcloud, etc.).

## Overview

This project automatically:
1. Downloads schedule documents from a configured storage backend
2. Parses PDF schedules to extract class information
3. Filters classes by teacher name
4. Determines week types (green/white/both/all) based on cell colors
5. Outputs structured JSON data

## Features

- **Pluggable storage backends** via Strategy pattern:
  - `google_drive` - Downloads schedules from Google Drive
  - `nextcloud` - Downloads schedules from Nextcloud public shares
- **Week type detection** - Analyzes cell colors to determine when classes occur:
  - `green` - Even weeks (2, 4, 6, 8, 10, 12, 14)
  - `white` - Odd weeks (1, 3, 5, 7, 9, 11, 13)
  - `both` - Alternating weeks
  - `all` - Every week
- **GitHub Actions automation** - Runs nightly and auto-updates schedule

## Requirements

- Python 3.11+
- LibreOffice (for DOCX to PDF conversion)
- Storage backend: Google Drive folder or Nextcloud share with schedule documents

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd py_schedule

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

Or with pyproject.toml (Poetry):
```bash
poetry install
```

## Configuration

1. Copy the sample environment file:
    ```bash
    cp sample.env .env
    ```

2. Edit `.env` with your settings:
    ```env
    # Select storage backend: google_drive or nextcloud
    STORAGE_TYPE=google_drive

    # Google Drive folder ID (used when STORAGE_TYPE=google_drive)
    FOLDER_ID=your_google_drive_folder_id_here

    # Nextcloud share URL (used when STORAGE_TYPE=nextcloud)
    NEXTCLOUD_URL=https://nextcloud.psu.by/index.php/s/no5zKbMrns6j5jQ?dir=/2026-2027/...

    # Optional Nextcloud credentials (if share requires auth)
    NEXTCLOUD_USERNAME=
    NEXTCLOUD_PASSWORD=

    # Teacher name to search for in schedules
    TARGET_TEACHER=Бровко Н.В.
    ```

## Usage

### Local Development

```bash
# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Run parser
python parser.py
```

Or with custom teacher:
```bash
python parser.py "Иванов И.И."
```

### GitHub Actions (Manual Trigger)

To run the parser manually via GitHub:

1. Go to your repository on GitHub
2. Navigate to **Actions** → **Schedule Parser**
3. Click **Run workflow** → **Run workflow**

Alternatively, push to main branch to trigger automatically:
```bash
git add .
git commit -m "Manual trigger"
git push origin main
```

### Output

The parser generates `schedule.json` with entries like:
```json
[
    {
        "group": "24-ВС",
        "day": "Среда",
        "time": "11:45 13:10",
        "text": "3н. Тестирование ПО (л.з.) Бровко Н.В. 303Г",
        "week_type": "white"
    }
]
```

## Logging

The script logs operations to both console and file:
- **Console** - Shows progress and results
- **parser.log** - Detailed log file with timestamps (not committed to git)

Log levels:
- `INFO` - Normal operations (downloaded files, found lessons, etc.)
- `WARNING` - Non-critical issues (missing files, fallback methods)
- `ERROR` - Critical errors (network failures, parsing errors)

### GitHub Actions Logs

When running via GitHub Actions, logs are visible in the Actions tab:
1. Go to repository → **Actions** → **Schedule Parser**
2. Click on the workflow run
3. View logs under each step

## GitHub Actions

The project includes automated GitHub Actions workflow that:
- Runs nightly at 2:00 AM UTC (5:00 AM Minsk time)
- Can be triggered manually
- Auto-commits schedule changes if detected

### Workflow Triggers

| Trigger | Description |
|---------|-------------|
| **Schedule** | Nightly at 2:00 AM UTC |
| **Manual** | Workflow dispatch - click "Run workflow" in Actions tab |
| **Push** | Any push to main branch |

### Setting Up GitHub Secrets

1. Go to your repository → Settings → Secrets and variables → Actions
2. Add these secrets:
   - `STORAGE_TYPE` - Storage backend: `google_drive` or `nextcloud`
   - `FOLDER_ID` - Google Drive folder ID (for `google_drive`)
   - `NEXTCLOUD_URL` - Nextcloud share URL (for `nextcloud`)
   - `NEXTCLOUD_USERNAME` - Nextcloud username (optional)
   - `NEXTCLOUD_PASSWORD` - Nextcloud password (optional)
   - `TARGET_TEACHER` - Teacher name to search for

## Project Structure

```
py_schedule/
├── .github/workflows/     # GitHub Actions
│   └── schedule-parser.yml
├── .env                   # Environment variables (not committed)
├── .gitignore
├── sample.env             # Template for .env
├── converter.py           # DOCX to PDF conversion utility
├── parser.py              # Main parser script
├── schedule.json          # Generated output
├── storage.py             # Storage strategies (Strategy pattern)
├── WEEK_ALGORITHM.md      # Week detection algorithm
├── pdfs/                  # Downloaded schedule PDFs (not committed)
└── venv/                  # Virtual environment (not committed)
    └── ...
```

## Extending Storage Backends

The project uses the **Strategy pattern** to support multiple storage backends. To add a new backend:

1. Create a new class inheriting from `storage.ScheduleStorage`
2. Implement `get_schedule_files(self) -> List[str]`
3. Register the new backend in `storage.create_storage()`

Example:
```python
from storage import ScheduleStorage

class MyStorage(ScheduleStorage):
    def get_schedule_files(self) -> List[str]:
        # Download files and return list of local PDF paths
        ...
```

## Algorithm

Week types are determined by analyzing cell colors in schedule PDFs:
- **Green cells** → Even weeks only
- **White cells** → All weeks
- **Mixed cells** → Both white and green weeks
- **Text indicators** (e.g., "1н", "2н") → Override based on week number

See [WEEK_ALGORITHM.md](WEEK_ALGORITHM.md) for details.

## License

MIT

# Schedule Parser

A Python-based tool for extracting teacher schedules from university schedule documents stored in Google Drive.

## Overview

This project automatically:
1. Downloads schedule documents from a Google Drive folder
2. Parses PDF schedules to extract class information
3. Filters classes by teacher name
4. Determines week types (green/white/both/all) based on cell colors
5. Outputs structured JSON data

## Features

- **Automatic Google Drive integration** - Downloads schedules directly from Drive
- **Week type detection** - Analyzes cell colors to determine when classes occur:
  - `green` - Even weeks (2, 4, 6, 8, 10, 12, 14)
  - `white` - Odd weeks (1, 3, 5, 7, 9, 11, 13)
  - `both` - Alternating weeks
  - `all` - Every week
- **GitHub Actions automation** - Runs nightly and auto-updates schedule

## Requirements

- Python 3.11+
- Google Drive folder with schedule documents

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
pip install requests pdfplumber pillow gdown python-dotenv
```

## Configuration

1. Copy the sample environment file:
   ```bash
   cp sample.env .env
   ```

2. Edit `.env` with your settings:
   ```env
   FOLDER_ID=your_google_drive_folder_id
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
- Runs nightly at 2:00 AM UTC
- Can be triggered manually
- Auto-commits schedule changes if detected

### Setting Up GitHub Secrets

1. Go to your repository → Settings → Secrets and variables → Actions
2. Add these secrets:
   - `FOLDER_ID` - Google Drive folder ID
   - `TARGET_TEACHER` - Teacher name to search for

## Project Structure

```
py_schedule/
├── .github/workflows/     # GitHub Actions
│   └── schedule-parser.yml
├── .env                   # Environment variables (not committed)
├── .gitignore
├── sample.env             # Template for .env
├── parser.py              # Main parser script
├── schedule.json          # Generated output
├── WEEK_ALGORITHM.md      # Week detection algorithm
└── Расписание занятий/    # Source schedules (if local)
    └── ...
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

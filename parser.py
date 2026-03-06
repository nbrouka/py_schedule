# -*- coding: utf-8 -*-
"""
Schedule Parser for Google Docs
Automatically finds and parses schedule files for a specific teacher from a Google Drive folder.
"""
import os
import sys
import logging
import requests
import pdfplumber
import io
import json
import re
import gdown
from PIL import Image
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add file handler for logging to file
file_handler = logging.FileHandler('parser.log', encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(file_handler)

# Load environment variables from .env file
load_dotenv()

# Configuration
TARGET_TEACHER = os.getenv('TARGET_TEACHER', "Бровко Н.В.")  # Can be overridden via command line

# Google Drive folder ID from environment variable
FOLDER_ID = os.getenv('FOLDER_ID')

# Validate required configuration
if not FOLDER_ID or FOLDER_ID == "your_folder_id_here":
    logger.error("Error: FOLDER_ID is not set")
    logger.error("Please set FOLDER_ID in .env file or GitHub secrets")
    exit(1)


def get_pdf_content(doc_id):
    """Download PDF content from Google Docs."""
    url = f"https://docs.google.com/document/d/{doc_id}/export?format=pdf"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return response.content
        else:
            logger.error(f"Error loading file {doc_id}: HTTP {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        logger.error(f"Timeout loading file {doc_id}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error loading file {doc_id}: {e}")
        return None


def check_teacher_in_pdf(pdf_bytes, teacher_name):
    """
    Quick check if teacher name appears in the PDF.
    Returns True if found, False otherwise.
    """
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text and teacher_name.lower() in text.lower():
                    return True
    except Exception:
        pass
    return False


def analyze_cell_color(cell_image):
    """
    Analyze cell color to determine if it's green, white, or divided.
    
    Returns:
        tuple: (primary_color, has_division, green_pct, white_pct)
    """
    if cell_image.mode != 'RGB':
        cell_image = cell_image.convert('RGB')
    
    width, height = cell_image.size
    sample_step = max(1, min(width, height) // 20)
    
    green_count = 0
    white_count = 0
    
    for y in range(0, height, sample_step):
        for x in range(0, width, sample_step):
            r, g, b = cell_image.getpixel((x, y))[:3]
            
            # Light green detection (typical schedule green: ~200, 255, ~200)
            if g > 180 and g > r + 20 and g > b + 20:
                green_count += 1
            # White detection
            elif r > 240 and g > 240 and b > 240:
                white_count += 1
    
    total = green_count + white_count
    if total == 0:
        return "white", False, 0, 0
    
    green_percentage = green_count / total * 100
    white_percentage = white_count / total * 100
    
    # Check for division: if both green and white are significant (both > 15%)
    has_division = green_percentage > 15 and white_percentage > 15
    
    # Determine primary color
    if green_percentage > 20:
        primary_color = "green"
    else:
        primary_color = "white"
    
    return primary_color, has_division, green_percentage, white_percentage


def clean_day_name(day_text):
    """Clean day name by joining spaced letters."""
    if not day_text:
        return day_text
    parts = day_text.split(' ')
    cleaned_parts = []
    
    p = 0
    while p < len(parts):
        current = parts[p]
        potential_word = current
        q = p + 1
        
        while q < len(parts):
            next_part = parts[q]
            should_join = False
            
            has_cyrillic_current = any(ord(c) > 1000 for c in potential_word if c.isalpha())
            has_cyrillic_next = any(ord(c) > 1000 for c in next_part if c.isalpha())
            
            if has_cyrillic_current and has_cyrillic_next:
                if len(potential_word) <= 3 or len(next_part) <= 3:
                    should_join = True
            
            if should_join:
                potential_word += next_part
                q += 1
            else:
                break
        
        cleaned_parts.append(potential_word)
        p = q
    
    return ' '.join(cleaned_parts)


def parse(pdf_bytes, teacher_name):
    """
    Parse PDF bytes and extract schedule information.
    
    Week type algorithm:
    - Division is when a SINGLE CELL contains both green and white regions
    - If cell has division (both green and white parts) -> classes in BOTH white and green weeks
    - If cell is entirely green (no division) -> green weeks only
    - If cell is entirely white (no division) -> all weeks
    """
    lessons = []
    seen_lessons = {}
    
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_image = page.to_image(resolution=150)
                pil_image = page_image.original
                
                scale_x = pil_image.width / page.width
                scale_y = pil_image.height / page.height
                
                tables = page.find_tables()
                if not tables:
                    continue
                
                for table in tables:
                    table_data = table.extract()
                    if not table_data:
                        continue
                    
                    num_rows = len(table_data)
                    num_cols = len(table_data[0]) if table_data[0] else 0
                    
                    all_x = set()
                    for cell in table.cells:
                        all_x.add(cell[0])
                        all_x.add(cell[2])
                    col_boundaries = sorted(all_x)
                    
                    all_y = set()
                    for cell in table.cells:
                        all_y.add(cell[1])
                        all_y.add(cell[3])
                    row_boundaries = sorted(all_y)
                    
                    column_headers = [""] * num_cols
                    
                    header_row = table_data[0]
                    if header_row:
                        for col_idx, cell in enumerate(header_row):
                            if col_idx >= num_cols: break
                            if cell:
                                cell_text = cell.replace('\n', ' ').strip()
                                group_match = re.search(r'\d{2}-[À-ßA-Z]{2,}', cell_text)
                                if group_match:
                                    column_headers[col_idx] = group_match.group(0)
                    
                    current_group = ""
                    for col_idx in range(num_cols):
                        if column_headers[col_idx]:
                            current_group = column_headers[col_idx]
                        else:
                            column_headers[col_idx] = current_group
                    
                    if not any(column_headers[2:]):
                        try:
                            page_height = page.height
                            page_width = page.width
                            top_crop = page.within_bbox((0, 0, page_width, page_height * 0.20))
                            header_text = top_crop.extract_text() or ""
                            all_groups = re.findall(r'\d{2}-[À-ßA-Z]{2,}', header_text)
                            
                            if all_groups:
                                num_data_cols = num_cols - 2
                                num_groups = len(all_groups)
                                
                                if num_groups > 0 and num_data_cols > 0:
                                    cols_per_group = num_data_cols / num_groups
                                    
                                    for group_idx, group in enumerate(all_groups):
                                        start_col = 2 + int(group_idx * cols_per_group)
                                        end_col = 2 + int((group_idx + 1) * cols_per_group)
                                        
                                        for col_idx in range(start_col, min(end_col, num_cols)):
                                            column_headers[col_idx] = group
                        except Exception:
                            pass
                    
                    cell_bbox_map = {}
                    for cell_bbox in table.cells:
                        x0, top, x1, bottom = cell_bbox
                        
                        row_idx = None
                        for i, y in enumerate(row_boundaries[:-1]):
                            if abs(y - top) < 1:
                                row_idx = i
                                break
                        
                        col_idx = None
                        for i, x in enumerate(col_boundaries[:-1]):
                            if abs(x - x0) < 1:
                                col_idx = i
                                break
                        
                        if row_idx is not None and col_idx is not None:
                            cell_bbox_map[(row_idx, col_idx)] = cell_bbox
                    
                    curr_day, curr_time = "", ""
                    
                    for row_idx in range(num_rows):
                        row = table_data[row_idx]
                        
                        if row[0]:
                            day_text = row[0].replace('\n', ' ')
                            day_text = re.sub(r'\s+', ' ', day_text).strip()
                            if day_text:
                                curr_day = clean_day_name(day_text)
                        
                        if len(row) > 1 and row[1]:
                            time_text = row[1].replace('\n', ' ')
                            time_text = re.sub(r'\s+', ' ', time_text).strip()
                            if time_text:
                                curr_time = time_text
                        
                        for col_idx in range(2, len(row)):
                            content = row[col_idx]
                            if not content:
                                continue
                            
                            content = content.replace('\n', ' ')
                            
                            if teacher_name.lower() in content.lower():
                                cell_bbox = cell_bbox_map.get((row_idx, col_idx))
                                if not cell_bbox:
                                    continue
                                
                                x0, top, x1, bottom = cell_bbox
                                
                                img_x0 = int(x0 * scale_x)
                                img_x1 = int(x1 * scale_x)
                                img_y0 = int(top * scale_y)
                                img_y1 = int(bottom * scale_y)
                                
                                cell_image = pil_image.crop((img_x0, img_y0, img_x1, img_y1))
                                
                                primary_color, has_division, green_pct, white_pct = analyze_cell_color(cell_image)
                                
                                if has_division:
                                    week_type = "both"
                                elif primary_color == "green":
                                    week_type = "green"
                                else:
                                    week_type = "all"
                                
                                parts = re.split(r'(?=\b\d+í\.?\s|[\d-]+íåä\.?\s)', content)
                                
                                for part in parts:
                                    if part.strip() and teacher_name.lower() in part.lower():
                                        clean_part = part.strip()
                                        
                                        week_match = re.search(r'(\d+)í', clean_part)
                                        if week_match:
                                            week_num = int(week_match.group(1))
                                            if week_num % 2 == 0:
                                                week_type = "green"
                                            else:
                                                week_type = "white"
                                        elif '1-12 íåä' in clean_part or '1-14 íåä' in clean_part:
                                            week_type = "all"
                                        
                                        group_info = column_headers[col_idx] if col_idx < len(column_headers) else ""
                                        
                                        lesson_key = (group_info, curr_day, curr_time, clean_part)
                                        
                                        if lesson_key in seen_lessons:
                                            existing_type = seen_lessons[lesson_key]
                                            if existing_type != week_type:
                                                seen_lessons[lesson_key] = "both"
                                        else:
                                            seen_lessons[lesson_key] = week_type
    except Exception as e:
        logger.error(f"Error parsing PDF: {e}")
        import traceback
        traceback.print_exc()
    
    for (group, day, time, text), week_type in seen_lessons.items():
        lessons.append({
            "group": group,
            "day": day,
            "time": time,
            "text": text,
            "week_type": week_type
        })
    
    return lessons


def get_folder_contents(folder_id):
    """
    Get list of files in a Google Drive folder using Google Drive API v3.
    
    Args:
        folder_id: Google Drive folder ID
        
    Returns:
        list: List of dicts with 'id', 'name', 'mimeType' for each file
    """
    import urllib.parse
    
    files = []
    
    # Use the Drive API to list files
    api_url = f"https://www.googleapis.com/drive/v3/files"
    
    params = {
        'q': f"'{folder_id}' in parents and trashed = false",
        'fields': 'files(id, name, mimeType)',
        'pageSize': 100
    }
    
    try:
        # First try without API key (public folders)
        response = requests.get(api_url, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            files = data.get('files', [])
        else:
            # Try alternative method: parse folder page
            logger.warning(f"Drive API returned {response.status_code}, trying alternative method...")
            files = get_folder_contents_via_page(folder_id)
    except Exception as e:
        logger.error(f"Error accessing Drive API: {e}")
        files = get_folder_contents_via_page(folder_id)
    
    return files


def get_folder_contents_via_page(folder_id):
    """
    Alternative method to get folder contents by parsing the folder's HTML page.
    """
    files = []
    
    folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
    
    try:
        response = requests.get(folder_url, timeout=30)
        if response.status_code == 200:
            html = response.text
            
            # Look for file IDs in the HTML
            # Pattern: "id":"xxxxx","name":"filename"
            import re
            
            # Try to extract file info from JavaScript data
            # Look for patterns like: [["xxxxx","filename",...]]
            file_pattern = r'\["([a-zA-Z0-9_-]{20,})","([^"]+)"'
            matches = re.findall(file_pattern, html)
            
            for file_id, file_name in matches:
                files.append({
                    'id': file_id,
                    'name': file_name,
                    'mimeType': 'application/vnd.google-apps.document'
                })
            
            if not files:
                # Try another pattern
                # Look for: /d/{file_id}/
                id_pattern = r'/d/([a-zA-Z0-9_-]{20,})/'
                ids = re.findall(id_pattern, html)
                for file_id in set(ids):
                    if file_id != folder_id:
                        files.append({
                            'id': file_id,
                            'name': f'document_{file_id[:8]}',
                            'mimeType': 'application/vnd.google-apps.document'
                        })
    except Exception as e:
        logger.error(f"  Error parsing folder page: {e}")
    
    return files


def download_folder_from_drive(folder_id):
    """
    Download all files from a Google Drive folder as PDF.
    
    Args:
        folder_id: Google Drive folder ID
        
    Returns:
        list: List of paths to downloaded PDF files
    """
    if not folder_id:
        logger.error("Error: FOLDER_ID environment variable is not set")
        return []
    
    url = f'https://drive.google.com/drive/folders/{folder_id}'
    logger.info(f"\nDownloading files from Google Drive folder...")
    logger.info(f"Folder URL: {url}")
    
    downloaded_files = []
    
    try:
        # Get list of files in the folder
        logger.info("\nFetching folder contents...")
        files = get_folder_contents(folder_id)
        
        if not files:
            logger.warning("  No files found or unable to access folder")
            logger.warning("  Trying gdown download_folder as fallback...")
            return download_folder_via_gdown(folder_id)
        
        logger.info(f"  Found {len(files)} file(s)")
        
        # Export each file as PDF
        logger.info(f"\nExporting {len(files)} file(s) as PDF...")
        
        for file_info in files:
            file_id = file_info['id']
            file_name = file_info['name']
            mime_type = file_info.get('mimeType', '')
            
            logger.info(f"\nExporting: {file_name}")
            
            # Clean filename for output
            safe_name = re.sub(r'[^\w\s\-\.\u0400-\u04FF]', '', file_name)
            if safe_name.endswith('.docx') or safe_name.endswith('.doc'):
                safe_name = safe_name.rsplit('.', 1)[0] + '.pdf'
            elif not safe_name.endswith('.pdf'):
                safe_name = safe_name + '.pdf'
            
            output_path = os.path.join(os.getcwd(), safe_name)
            
            # Export as PDF from Google Docs
            export_url = f"https://docs.google.com/document/d/{file_id}/export?format=pdf"
            
            try:
                resp = requests.get(export_url, timeout=60)
                if resp.status_code == 200 and b'%PDF' in resp.content[:10]:
                    with open(output_path, 'wb') as f:
                        f.write(resp.content)
                    print(f"  Exported as PDF: {safe_name}")
                    downloaded_files.append(output_path)
                else:
                    print(f"  Failed to export: HTTP {resp.status_code}")
                    # Check if response is HTML (login page)
                    if b'html' in resp.content[:100].lower():
                        print(f"  Note: File may require authentication or is not a Google Doc")
            except Exception as e:
                print(f"  Error: {e}")
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    return downloaded_files


def download_folder_via_gdown(folder_id):
    """
    Fallback method using gdown.download_folder.
    Downloads files and then exports them as PDF.
    """
    import tempfile
    import shutil
    
    url = f'https://drive.google.com/drive/folders/{folder_id}'
    downloaded_files = []
    
    try:
        temp_dir = tempfile.mkdtemp(prefix='schedule_')
        
        # Download folder using gdown
        logger.info(f"  Downloading to temp directory...")
        gdown.download_folder(url, quiet=False, use_cookies=False, output=temp_dir)
        
        # Find all downloaded files
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                temp_path = os.path.join(root, file)
                logger.info(f"\n  Downloaded: {file}")
                
                # If it's a PDF, just copy it
                if file.endswith('.pdf'):
                    safe_name = re.sub(r'[^\w\s\-\.\u0400-\u04FF]', '', file)
                    output_path = os.path.join(os.getcwd(), safe_name)
                    shutil.copy(temp_path, output_path)
                    downloaded_files.append(output_path)
                    logger.info(f"    Copied: {safe_name}")
                else:
                    # For non-PDF files, try to find the Google Doc ID and export
                    # This is a limitation - we can't easily get the Doc ID from downloaded file
                    logger.warning(f"    Note: Non-PDF file downloaded but not converted")
        
        # Clean up temp directory
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
            
    except Exception as e:
        logger.error(f"  gdown fallback error: {e}")
        import traceback
        traceback.print_exc()
    
    return downloaded_files


def find_teacher_schedule_files(teacher_name, downloaded_files):
    """
    Find all schedule files from downloaded files that contain the teacher's name.
    
    Args:
        teacher_name: Name of the teacher to search for
        downloaded_files: List of paths to downloaded files
        
    Returns:
        list: List of file paths containing the teacher
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Looking for teacher: {teacher_name}")
    logger.info(f"Checking {len(downloaded_files)} file(s)")
    logger.info(f"{'='*60}")
    
    teacher_files = []
    for file_path in downloaded_files:
        logger.info(f"\nChecking: {file_path}...")
        try:
            with open(file_path, 'rb') as f:
                pdf_data = f.read()
            
            if check_teacher_in_pdf(pdf_data, teacher_name):
                logger.info(f"  [OK] Found '{teacher_name}' in this file!")
                teacher_files.append(file_path)
            else:
                logger.warning(f"  [--] Teacher not found in this file")
        except Exception as e:
            logger.error(f"  [ERROR] Failed to read file: {e}")
    
    return teacher_files


if __name__ == "__main__":
    import sys
    
    # Allow teacher name to be passed as command line argument
    if len(sys.argv) > 1:
        TARGET_TEACHER = sys.argv[1]
    
    logger.info(f"Target teacher: {TARGET_TEACHER}")
    
    # Download files from Google Drive folder
    downloaded_files = download_folder_from_drive(FOLDER_ID)
    
    if not downloaded_files:
        logger.warning("\nNo files downloaded from Google Drive folder")
    else:
        # Find files containing the teacher
        teacher_files = find_teacher_schedule_files(TARGET_TEACHER, downloaded_files)
        
        if not teacher_files:
            logger.warning(f"\nNo schedule files found for teacher: {TARGET_TEACHER}")
        else:
            logger.info(f"\n{'='*60}")
            logger.info(f"Found {len(teacher_files)} schedule file(s) for {TARGET_TEACHER}")
            logger.info(f"{'='*60}")
            
            all_lessons = []
            for file_path in teacher_files:
                logger.info(f"\nParsing: {file_path}...")
                try:
                    with open(file_path, 'rb') as f:
                        pdf_data = f.read()
                    lessons = parse(pdf_data, TARGET_TEACHER)
                    all_lessons.extend(lessons)
                    logger.info(f"  Found lessons: {len(lessons)}")
                except Exception as e:
                    logger.error(f"  Error parsing file: {e}")
            
            with open('schedule.json', 'w', encoding='utf-8') as f:
                json.dump(all_lessons, f, ensure_ascii=False, indent=4)
            
            logger.info(f"\n{'='*60}")
            logger.info(f"TOTAL lessons found: {len(all_lessons)}")
            logger.info(f"{'='*60}")
            
            week_types = {}
            for lesson in all_lessons:
                wt = lesson['week_type']
                week_types[wt] = week_types.get(wt, 0) + 1
            
            logger.info("\nBy week type:")
            for wt, count in sorted(week_types.items()):
                logger.info(f"  {wt}: {count}")
            
            logger.info(f"\nResult saved to schedule.json")

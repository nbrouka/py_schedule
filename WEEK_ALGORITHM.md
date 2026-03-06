# Algorithm for Determining White and Green Weeks

## Overview

This document describes the algorithm for determining week types based on cell colors in schedule PDF files.

## Week Types

- **green** - Classes held only in green (even) weeks: 2, 4, 6, 8, 10, 12, 14
- **white** - Classes held only in white (odd) weeks: 1, 3, 5, 7, 9, 11, 13
- **both** - Classes held in both white and green weeks (alternating weeks)
- **all** - Classes held every week (same as "both")

## Color Detection

### Cell Color Classification

Cells are classified based on RGB color analysis:

- **Green cell**: Light green color where G > 180 and G > R + 20 and G > B + 20
- **White cell**: Near-white color where R > 240 and G > 240 and B > 240

The classification samples pixels throughout the cell and determines the dominant color type.

### Division Detection

Division is detected when a single cell contains both significant green and white regions (both > 15%).

## Algorithm

```
FOR each cell containing target teacher:
    
    # Analyze cell color
    primary_color, has_division = analyze_cell_color(cell_image)
    
    # Determine week type
    IF has_division:
        week_type = "both"  # Cell has both green and white parts
    ELSE IF primary_color == "green":
        week_type = "green"  # Entirely green cell
    ELSE:
        week_type = "all"  # Entirely white cell
    
    # Handle duplicates (same lesson in multiple rows due to merged cells)
    IF lesson already seen with different week_type:
        week_type = "both"  # Division detected via duplicate
    
    # Text indicators can override
    IF text contains week number (e.g., "1н", "2н", "3н", etc.):
        week_type = "green" if even, "white" if odd
    IF text contains "1-12 нед" or "1-14 нед":
        week_type = "all"
```

## Rules Summary

| Cell Color | Text Indicator | Week Type |
|------------|----------------|------------|
| White      | -              | all        |
| Green      | -              | green      |
| Mixed      | -              | both       |
| -          | 1н, 3н, 5н... | white      |
| -          | 2н, 4н, 6н... | green      |
| -          | 1-12 нед       | all        |

## Technical Details

### Cell Boundary Detection

The algorithm uses pdfplumber's `table.cells` property to get actual cell boundaries, which correctly handles merged cells. The boundaries are mapped to row/column indices for processing.

### Coordinate Conversion

PDF coordinates are converted to image coordinates using scale factors:
- `scale_x = image_width / page_width`
- `scale_y = image_height / page_height`

### Deduplication

When the same lesson (same group, day, time, text) appears in multiple rows due to merged cells with different colors, the algorithm detects this as division and marks it as "both".

## Files

- `parser.py` - Main parser implementation
- `schedule.json` - Output file with parsed schedule data

## Example Output

```json
{
    "group": "24-ВС",
    "day": "Среда",
    "time": "13:40 15:05",
    "text": "Схемотехника (л.) Дровосекова Т.Н. медиа",
    "week_type": "all"
},
{
    "group": "24-ВС",
    "day": "Среда",
    "time": "15:20 16:45",
    "text": "Схемотехника (пр.) Дровосекова Т.Н. медиа",
    "week_type": "green"
},
{
    "group": "24-ВС",
    "day": "Четверг",
    "time": "10:05 11:30",
    "text": "3н. Тестирование ПО (л.з.) Бровко Н.В. 303Г",
    "week_type": "white"
}
```

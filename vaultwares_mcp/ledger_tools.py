import os
import json
from datetime import datetime
from typing import Any, List, Optional

LEDGER_ROOT = r"C:\Users\Administrator\Desktop\Github Repos\agent-ledger\events"

def get_ledger_entries(
    n: int = 25,
    project: Optional[str] = None,
    kind: Optional[str] = None,
    model: Optional[str] = None,
    assistant: Optional[str] = None,
    date: Optional[str] = None
) -> List[dict]:
    """
    Fetch the last N ledger entries with optional filters.
    backtracks through months if needed.
    """
    entries = []
    
    # Target date or today
    if date:
        try:
            target_dt = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            target_dt = datetime.now()
    else:
        target_dt = datetime.now()

    # We iterate backwards from target_dt's month
    curr_year = target_dt.year
    curr_month = target_dt.month

    while len(entries) < n:
        month_dir = os.path.join(LEDGER_ROOT, str(curr_year), f"{curr_month:02d}")
        if os.path.exists(month_dir):
            # Get all JSON files in this month, sorted newest first
            files = sorted([f for f in os.listdir(month_dir) if f.endswith(".json")], reverse=True)
            
            for f in files:
                if len(entries) >= n:
                    break
                    
                path = os.path.join(month_dir, f)
                try:
                    with open(path, 'r', encoding='utf-8') as jf:
                        data = json.load(jf)
                        
                        # Apply filters
                        if project and project.lower() not in data.get("Project", "").lower():
                            continue
                        if kind and kind.lower() not in data.get("Kind", "").lower():
                            continue
                        if model and model.lower() not in data.get("Model", "").lower():
                            continue
                        if assistant and assistant.lower() not in data.get("Actor", "").lower():
                            continue
                        if date and not f.startswith(date.replace("-", "")):
                            # If a specific date was requested, skip files from other dates in that month
                            # This is a bit strict, but follows the "date" parameter intent
                            continue
                            
                        entries.append(data)
                except Exception:
                    continue
        
        # Go back one month
        curr_month -= 1
        if curr_month == 0:
            curr_month = 12
            curr_year -= 1
            
        # Hard stop if we go back too far (e.g. before 2025)
        if curr_year < 2025:
            break

    return entries

def search_ledger(query: str, n: int = 10) -> List[dict]:
    """
    Search through recent ledger entries for a specific query string.
    """
    results = []
    # Just reuse get_ledger_entries with a larger N and then filter locally
    candidates = get_ledger_entries(n=100) # Scan last 100 entries
    
    query = query.lower()
    for entry in candidates:
        if len(results) >= n:
            break
            
        # Search in Summary, PlanPath, Files, Commands
        text_to_search = (
            entry.get("Summary", "") + " " + 
            entry.get("PlanPath", "") + " " +
            " ".join(entry.get("Files", [])) + " " +
            " ".join(entry.get("Commands", []))
        ).lower()
        
        if query in text_to_search:
            results.append(entry)
            
    return results

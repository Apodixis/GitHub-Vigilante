# standard library packages (Python-native)
import json, os, re
from datetime import datetime

# local imports
import config
from Modules import state # access global state variables

# third-party packages
import openpyxl
from openpyxl.utils import get_column_letter


def _sanitize_excel_value(value):
    """
    Input: value (str)
    Output: String sanitized of control characters
    Method: Use regular expression to remove control characters that openpyxl cannot store in worksheet cells
    """
    ILLEGAL_CHARACTERS_RE = re.compile(r'[\000-\010]|[\013-\014]|[\016-\037]')
    
    # If the value is a string, remove illegal characters using regex
    if isinstance(value, str):
        return ILLEGAL_CHARACTERS_RE.sub("", value)
    
    return value

def write_to_excel(
    results_data: list[dict],
    validation_metrics: dict[str, int | float | None] | None = None,
    *,
    searched_logins: list[str] | None = None,
    searched_emails: list[str] | None = None,
    user_records: list[dict] | None = None,
) -> str:
    """
    Inputs: Search results, optional aggregate user-validation metrics, exact search targets, and user records for summary counts
    Outputs: Excel file using the following file naming convention: f"{YYYYMMDDHHMM}{search_method}_{target}{enriched}.xlsx"
    Method: Write a summary worksheet followed by the search results worksheet
    """
    # Create workbook with a run summary as the first worksheet
    wb = openpyxl.Workbook()
    summary_ws = wb.active
    summary_ws.title = "Summary"
    ws = wb.create_sheet("Results")

    # omitted keys to be excluded from the results worksheet
    excluded_keys = {"starred_users"}

    # Preserve column order: start with keys from first user, append any new keys found in other users
    if results_data:
        all_keys = [key for key in results_data[0] if key not in excluded_keys]
        for user in results_data[1:]:
            for k in user.keys():
                if k not in all_keys and k not in excluded_keys:
                    all_keys.append(k)
    else:
        all_keys = []
    
    # Write header
    for col, key in enumerate(all_keys, 1):
        ws.cell(row=1, column=col, value=key)
	
    # Write user data
    for row, user in enumerate(results_data, 2):
        for col, key in enumerate(all_keys, 1):
            val = user.get(key, "")
            
            # Convert sets/lists to comma-separated string for Excel
            if isinstance(val, (set, list)):
                val = ', '.join(str(item) for item in val)
            
            elif isinstance(val, dict):
                val = str(val)
            
            val = _sanitize_excel_value(val)
            ws.cell(row=row, column=col, value=val)
    
    # Count unique user records by case-insensitive login
    users_by_login = {
        user["login"].strip().casefold(): user
        for user in (user_records if user_records is not None else results_data)
        if isinstance(user.get("login"), str) and user["login"].strip()
    }
    
    # Count unique user records corresponding to input target logins
    searched_login_set = {
        login.strip().casefold()
        for login in searched_logins or []
        if isinstance(login, str) and login.strip()
    }
    
    # Count unique user records corresponding to input target emails
    searched_email_set = {
        email.strip().casefold()
        for email in searched_emails or []
        if isinstance(email, str) and email.strip()
    }
    
    # Count unique user records for records in the blacklisted logins set
    blacklist_logins = {
        login.strip().casefold()
        for login in config.BAD_LOGINS
        if isinstance(login, str) and login.strip()
    }
    
    # Count unique user records for records in the validation logins set
    validation_logins = {
        login.strip().casefold()
        for login in config.VALIDATION_SET_LOGINS
        if isinstance(login, str) and login.strip()
    }
    
    # Count unique user records for records in the blacklisted emails set
    blacklist_emails = {
        email.strip().casefold()
        for email in config.BAD_EMAILS
        if isinstance(email, str) and email.strip()
    }

    # Exclude blacklisted emails from validation matches so overlaps count only as blacklist records
    validation_emails = {
        email.strip().casefold()
        for email in config.VALIDATION_SET_EMAILS
        if isinstance(email, str) and email.strip()
    } - blacklist_emails
    
    # normalizes user emails to ensure indexing does not cause errors
    def user_emails(user: dict) -> set[str]:
        raw_emails = user.get("emails") or []
        if isinstance(raw_emails, str):
            raw_emails = [raw_emails]
        
        # 
        return {
            email.strip().casefold()
            for email in raw_emails
            if isinstance(email, str) and email.strip()
        }
    
    # Count unique user records for records in the searched logins and emails sets
    searched_user_count = sum(
        login in searched_login_set or bool(user_emails(user) & searched_email_set)
        for login, user in users_by_login.items()
    )
    
    # Count unique user records for records in the blacklist logins and emails sets
    blacklist_user_count = sum(
        login in blacklist_logins or bool(user_emails(user) & blacklist_emails)
        for login, user in users_by_login.items()
    )
    
    # Count unique user records for records in the validation logins and emails sets
    validation_user_count = sum(
        login in validation_logins or bool(user_emails(user) & validation_emails)
        for login, user in users_by_login.items()
    )
    
    # Build summary rows for output file
    summary_rows = [
        ("Total user records in output", len(users_by_login)),
        ("Records matching searched logins/emails", searched_user_count),
        ("Blacklist user records in output", blacklist_user_count),
        ("Validation user records in output", validation_user_count),
    ]
    
    # Append configured validation metrics to the summary rows
    if validation_metrics is not None:
        summary_rows.extend([
            ("Validation emails total", validation_metrics.get("validation_emails_total")),
            ("Validation emails found", validation_metrics.get("validation_emails_found")),
            ("Validation email coverage", validation_metrics.get("validation_email_coverage")),
            ("Validation logins total", validation_metrics.get("validation_logins_total")),
            ("Validation logins found", validation_metrics.get("validation_logins_found")),
            ("Validation average precision", validation_metrics.get("validation_average_precision")),
            ("Validation positive accounts found", validation_metrics.get("validation_positive_accounts_found")),
            ("Recall@K (K)", validation_metrics.get("validation_recall_k")),
            ("Recall@K", validation_metrics.get("validation_recall_at_k")),
            ("Mean reciprocal rank", validation_metrics.get("validation_mean_reciprocal_rank")),
        ])
    
    # Write summary rows column names to the summary worksheet
    summary_ws.append(["Metric", "Value"])
    
    # Write each summary row to the summary worksheet
    for label, value in summary_rows:
        summary_ws.append([label, value])
    
    # Set column widths for better readability
    summary_ws.column_dimensions["A"].width = 44
    summary_ws.column_dimensions["B"].width = 20
    
    # Autosize columns
    for col in range(1, len(all_keys)+1):
        ws.column_dimensions[get_column_letter(col)].auto_size = True
    
    # Build filename and path to Downloads
    date_str = datetime.now().strftime("%Y%m%d%H%M")
    filename = f"{date_str}{state.outfile_title}.xlsx"
    downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(downloads_folder, exist_ok=True)
    file_path = os.path.join(downloads_folder, filename)
    
    # Save results to workbook
    wb.save(file_path)
    
    return filename

def write_to_json(results_data, file_title: str) -> str:
    """Write records to a timestamped JSON file in Downloads."""
    # Build filename and path to Downloads
    date_str = datetime.now().strftime("%Y%m%d%H%M")
    filename = f"{date_str}{file_title}.json"
    downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(downloads_folder, exist_ok=True)
    file_path = os.path.join(downloads_folder, filename)
    
    # Convert sets to sorted lists for JSON serialization
    json_records = [
        {
            key: sorted(value) if isinstance(value, set) else value
            for key, value in record.items()
        }
        for record in results_data
    ]
    
    # Write JSON records to file with UTF-8 encoding and pretty-printing
    with open(file_path, "w", encoding="utf-8") as output_file:
        json.dump(json_records, output_file, ensure_ascii=False, indent=2)
    
    return filename
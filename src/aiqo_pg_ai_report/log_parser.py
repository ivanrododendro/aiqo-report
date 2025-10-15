import logging
import re
import io
import gzip
import zipfile

logger = logging.getLogger(__name__)


def parse_log_entry(log_entry_text):
    duration_ms = None
    first_line = log_entry_text.splitlines()[0]
    duration_match = re.search(r"duration: (\d+\.?\d*) ms", first_line)
    if duration_match:
        try:
            duration_ms = float(duration_match.group(1))
        except ValueError:
            logger.warning(f"Could not parse duration from line: {first_line}")
            duration_ms = None  # Ensure it's None if parsing fails

    # Extract the timestamp from the first 23 characters of the log entry
    timestamp = log_entry_text[:23].strip()
    # Extract the block from "Query Text:" to "Settings:"
    match = re.search(r"Query Text:(.*?)$", log_entry_text, re.DOTALL)
    if not match:
        raise ValueError("Could not parse log entry: Missing query text or execution plan.")

    # Extract the full block
    full_block = match.group(1).strip()
    lines = full_block.splitlines()

    # Extract the title (first one or two lines of the query)
    if len(lines) >= 2 and lines[0].strip().startswith("--") and lines[1].strip().startswith("--"):
        job_name = lines[0]
        query_name = lines[1]
        start_index = 2  # Skip the title lines for further processing
    else:
        job_name = ""
        query_name = [" ".join(lines[0:])]
        start_index = 0

    job_name = "\n".join(job_name).strip().replace("\t", "").replace("\n", "")
    query_name = "\n".join(query_name).strip().replace("\t", "").replace("\n", "")

    # Split based on the first occurrence of "cost="
    query_lines = []
    plan_lines = []
    found_plan = False

    for line in lines[start_index:]:  # Start from the appropriate index
        if not found_plan and "cost=" in line:
            found_plan = True
        if found_plan:
            plan_lines.append(line)
        else:
            query_lines.append(line)

    if not plan_lines:
        raise ValueError("No execution plan found in the log entry.")

    # Extract startup_cost, total cost and rows from the first plan line containing 'cost='
    startup_cost = None
    total_cost = None
    rows = None
    first_cost_line = None
    for pline in plan_lines:
        if "cost=" in pline:
            first_cost_line = pline
            break
    if first_cost_line:
        cost_match = re.search(r"cost=(\d+(?:\.\d+)?)\.\.(\d+(?:\.\d+)?)", first_cost_line)
        if cost_match:
            try:
                startup_cost = float(cost_match.group(1))
                total_cost = float(cost_match.group(2))
            except ValueError:
                logger.warning(f"Could not parse cost values from line: {first_cost_line}")
        rows_match = re.search(r"rows=(\d+)", first_cost_line)
        if rows_match:
            try:
                rows = int(rows_match.group(1))
            except ValueError:
                logger.warning(f"Could not parse rows value from line: {first_cost_line}")

    return {
        "timestamp": timestamp,
        "query_name": query_name,
        "job_name": job_name,
        "query_text": "\n".join(query_lines).strip(),
        "execution_plan": "\n".join(plan_lines).strip(),
        "duration": duration_ms,
        "startup_cost": startup_cost,
        "cost": total_cost,
        "rows": rows,
    }


def extract_plan_starting_at_line(file_iterator, first_line):
    """
    Extracts a full PostgreSQL autoexplain plan block starting from first_line
    until a line starting with "Settings:" is found.
    """
    plan_lines = [first_line]
    for line in file_iterator:
        plan_lines.append(line)
        if line.strip().startswith("Settings:"):
            break
    return "".join(plan_lines)


class LogParser:
    def __init__(self):
        pass

    def _process_plain_text_file(self, file_obj, log_file_path):
        logger.info(f"Processing plain text file {file_obj.name} from {log_file_path}")
        line_number = 0
        for line in file_obj:
            line_number += 1
            if "plan:" in line:
                try:
                    # Pass the file_obj (iterator) and the current line
                    log_entry_text = extract_plan_starting_at_line(file_obj, line)
                    yield parse_log_entry(log_entry_text)
                except ValueError as e:
                    logger.warning(
                        f"Skipping log entry at line {line_number} in {log_file_path} due to parsing error: {e}"
                    )
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error processing log entry at line {line_number} in {log_file_path}: {e}")
                    continue

    def parse_log_file(self, log_file_path):
        if str(log_file_path).endswith(".gz"):
            logger.info(f"Uncompressing and parsing gzip file: {log_file_path}")
            with gzip.open(log_file_path, "rt", encoding="utf-8") as f:
                yield from self._process_plain_text_file(f, log_file_path)
        elif str(log_file_path).endswith(".zip"):
            logger.info(f"Uncompressing and parsing zip file: {log_file_path}")
            with zipfile.ZipFile(log_file_path, "r") as zip_ref:
                for file_name in zip_ref.namelist():
                    with zip_ref.open(file_name) as raw_f:
                        # Wrap the raw bytes file with TextIOWrapper for UTF-8 decoding
                        f = io.TextIOWrapper(raw_f, encoding="utf-8", errors="replace")
                        yield from self._process_plain_text_file(f, log_file_path)
        else:
            logger.info(f"Parsing plain text log file: {log_file_path}")
            with open(log_file_path, "r", encoding="utf-8") as f:
                yield from self._process_plain_text_file(f, log_file_path)

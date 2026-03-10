import gzip
import io
import json
import logging
import re
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterator, Protocol

logger = logging.getLogger(__name__)


class LogParserInterface(Protocol):
    def parse_log_file(self, log_file_path: str | Path) -> Iterator[dict[str, Any]]:
        ...


class AbstractLogParser(LogParserInterface, ABC):
    def __init__(self):
        # Track total log lines processed across parsed files.
        self.total_log_lines_processed = 0

    @abstractmethod
    def _process_plain_text_file(self, file_obj: io.TextIOBase, log_file_path: str | Path) -> Iterator[dict[str, Any]]:
        """
        Process a plain text file-like object and yield parsed entries.
        """

    def parse_log_file(self, log_file_path: str | Path) -> Iterator[dict[str, Any]]:
        """
        Handle file opening and decompression before delegating to the concrete parser implementation.
        """
        if str(log_file_path).endswith(".gz"):
            logger.info(f"Uncompressing and parsing gzip file: {log_file_path}")
            with gzip.open(log_file_path, "rt", encoding="utf-8") as f:
                yield from self._process_plain_text_file(f, log_file_path)
        elif str(log_file_path).endswith(".zip"):
            logger.info(f"Uncompressing and parsing zip file: {log_file_path}")
            with zipfile.ZipFile(log_file_path, "r") as zip_ref:
                for file_name in zip_ref.namelist():
                    with zip_ref.open(file_name) as raw_f:
                        f = io.TextIOWrapper(raw_f, encoding="utf-8", errors="replace")
                        yield from self._process_plain_text_file(f, log_file_path)
        else:
            logger.info(f"Parsing plain text log file: {log_file_path}")
            with open(log_file_path, "r", encoding="utf-8") as f:
                yield from self._process_plain_text_file(f, log_file_path)


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
    logger.debug(f"Parsing log entry with timestamp: {timestamp}")
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
    first_cost_line_index = -1
    for i, pline in enumerate(plan_lines):
        if "cost=" in pline:
            first_cost_line = pline
            first_cost_line_index = i
            break
    if first_cost_line:
        cost_match = re.search(r"cost=(\d+(?:\.\d+)?)\.\.(\d+(?:\.\d+)?)", first_cost_line)
        if cost_match:
            try:
                startup_cost = float(cost_match.group(1))
                total_cost = float(cost_match.group(2))
            except ValueError:
                logger.warning(f"Could not parse cost values from line: {first_cost_line}")
        # Prefer actual rows over estimated rows
        rows_match = re.search(r"actual rows=(\d+)", first_cost_line)
        if rows_match:
            try:
                rows = int(rows_match.group(1))
                logger.debug(f"Parsed 'actual rows' from first cost line: {rows}")
            except ValueError:
                logger.warning(f"Could not parse actual rows value from line: {first_cost_line}")
        else:
            rows_match = re.search(r"rows=(\d+)", first_cost_line)
            if rows_match:
                try:
                    rows = int(rows_match.group(1))
                except ValueError:
                    logger.warning(f"Could not parse rows value from line: {first_cost_line}")

        def _find_first_positive_rows(lines_to_scan: list[str], pattern: str) -> int | None:
            for plan_line in lines_to_scan:
                rows_candidate_match = re.search(pattern, plan_line)
                if not rows_candidate_match:
                    continue
                try:
                    candidate_rows = int(rows_candidate_match.group(1))
                except ValueError:
                    logger.warning(f"Could not parse row count value from line: {plan_line}")
                    continue
                if candidate_rows > 0:
                    return candidate_rows
            return None

        # ModifyTable roots for INSERT/UPDATE/DELETE often report actual rows=0.
        # In that case, use the first positive child row count found in the plan.
        if rows == 0 and re.search(r"\b(Insert|Update|Delete|ModifyTable)\b", first_cost_line, re.IGNORECASE):
            logger.debug("Rows is 0 on a DML root node. Searching for a better value in subsequent nodes.")
            child_plan_lines = plan_lines[first_cost_line_index + 1:]
            nested_actual_rows = _find_first_positive_rows(child_plan_lines, r"actual rows=(\d+)")
            if nested_actual_rows is not None:
                logger.debug(f"Found new rows value from child actual rows: {nested_actual_rows}")
                rows = nested_actual_rows
            else:
                nested_estimated_rows = _find_first_positive_rows(child_plan_lines, r"rows=(\d+)")
                if nested_estimated_rows is not None:
                    logger.debug(f"Found new rows value from child estimated rows: {nested_estimated_rows}")
                    rows = nested_estimated_rows

    logger.debug(f"Parsed plan line metrics: cost={total_cost}, rows={rows}")

    # Parse buffer statistics from the entire log entry
    buffers = {
        "shared_hit": None,
        "shared_read": None,
        "shared_dirtied": None,
        "shared_written": None,
        "temp_read": None,
        "temp_written": None,
    }
    
    buffers_match = re.search(
        r"Buffers:\s+shared\s+hit=(\d+)(?:\s+read=(\d+))?(?:\s+dirtied=(\d+))?(?:\s+written=(\d+))?(?:,\s*temp\s+read=(\d+))?(?:\s+written=(\d+))?",
        log_entry_text
    )
    if buffers_match:
        try:
            buffers["shared_hit"] = int(buffers_match.group(1)) if buffers_match.group(1) else None
            buffers["shared_read"] = int(buffers_match.group(2)) if buffers_match.group(2) else None
            buffers["shared_dirtied"] = int(buffers_match.group(3)) if buffers_match.group(3) else None
            buffers["shared_written"] = int(buffers_match.group(4)) if buffers_match.group(4) else None
            buffers["temp_read"] = int(buffers_match.group(5)) if buffers_match.group(5) else None
            buffers["temp_written"] = int(buffers_match.group(6)) if buffers_match.group(6) else None
            logger.debug(f"Parsed buffer statistics: {buffers}")
        except (ValueError, IndexError) as e:
            logger.warning(f"Could not parse buffer statistics: {e}")

    # Parse WAL statistics from the entire log entry
    wal = {
        "records": None,
        "fpi": None,
        "bytes": None,
    }
    
    wal_match = re.search(
        r"WAL:\s+records=(\d+)(?:\s+fpi=(\d+))?(?:\s+bytes=(\d+))?",
        log_entry_text
    )
    if wal_match:
        try:
            wal["records"] = int(wal_match.group(1)) if wal_match.group(1) else None
            wal["fpi"] = int(wal_match.group(2)) if wal_match.group(2) else None
            wal["bytes"] = int(wal_match.group(3)) if wal_match.group(3) else None
            logger.debug(f"Parsed WAL statistics: {wal}")
        except (ValueError, IndexError) as e:
            logger.warning(f"Could not parse WAL statistics: {e}")

    query_text_clean = "\n".join(query_lines).strip()
    title = (job_name + " " + query_name).strip()
    if not title:
        title = query_text_clean

    result = {
        "timestamp": timestamp,
        "query_name": query_name,
        "job_name": job_name,
        "title": title,
        "query_text": query_text_clean,
        "execution_plan": "\n".join(plan_lines).strip(),
        "duration": duration_ms,
        "startup_cost": startup_cost,
        "cost": total_cost,
        "rows": rows,
        "buffers": buffers,
        "wal": wal,
    }
    
    logger.debug(f"Completed parsing log entry: timestamp={timestamp}, duration={duration_ms}ms, "
                 f"cost={total_cost}, rows={rows}, buffers={buffers}, wal={wal}")
    
    return result


def extract_plan_starting_at_line(file_iterator, first_line):
    """
    Extracts a full PostgreSQL autoexplain plan block starting from first_line
    until a line starting with "Settings:" is found or a new log entry starts.
    """
    plan_lines = [first_line]
    lines_consumed = 1
    for line in file_iterator:
        lines_consumed += 1
        if re.match(r"^\d{4}-\d{2}-\d{2} ", line):
            break
        plan_lines.append(line)
        if line.strip().startswith("Settings:"):
            break
    return "".join(plan_lines), lines_consumed


class TextLogParser(AbstractLogParser):
    def __init__(self):
        super().__init__()

    def _process_plain_text_file(self, file_obj, log_file_path):
        logger.info(f"Processing plain text file {file_obj.name} from {log_file_path}")
        line_number = 0
        lines_processed = 0
        for line in file_obj:
            line_number += 1
            lines_processed += 1
            if "plan:" in line:
                try:
                    entry_start_line = line_number
                    # Pass the file_obj (iterator) and the current line
                    log_entry_text, consumed_lines = extract_plan_starting_at_line(file_obj, line)
                    lines_processed += consumed_lines - 1  # first line already counted
                    line_number += consumed_lines - 1
                    if re.search(r'"Query Text"\s*:', log_entry_text):
                        parsed_entry = parse_json_log_entry(log_entry_text)
                    else:
                        parsed_entry = parse_log_entry(log_entry_text)
                    parsed_entry["source_line"] = entry_start_line
                    yield parsed_entry
                except ValueError as e:
                    logger.warning(
                        f"Skipping log entry at line {line_number} in {log_file_path} due to parsing error: {e}"
                    )
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error processing log entry at line {line_number} in {log_file_path}: {e}")
                    continue

        self.total_log_lines_processed += lines_processed


def parse_json_log_entry(log_entry_text: str) -> dict[str, Any]:
    # Extract duration
    duration_ms = None
    first_line = log_entry_text.splitlines()[0]
    duration_match = re.search(r"duration: (\d+\.?\d*) ms", first_line)
    if duration_match:
        try:
            duration_ms = float(duration_match.group(1))
        except ValueError:
            logger.warning(f"Could not parse duration from line: {first_line}")

    # Timestamp from first 23 characters, consistent with text parser
    timestamp = log_entry_text[:23].strip()
    logger.debug(f"Parsing JSON log entry with timestamp: {timestamp}")

    json_start = log_entry_text.find("{")
    if json_start == -1:
        raise ValueError("Could not parse JSON log entry: Missing JSON plan payload.")

    json_section = log_entry_text[json_start:]

    try:
        plan_json_obj = json.loads(json_section)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not decode JSON plan: {exc}") from exc

    if not isinstance(plan_json_obj, dict):
        raise ValueError("JSON plan payload is not in expected object format.")

    query_text_raw = plan_json_obj.get("Query Text", "")
    job_name = ""
    query_name = ""
    query_text = query_text_raw.strip() if isinstance(query_text_raw, str) else ""

    if isinstance(query_text_raw, str):
        # Prefer extracting job/task comments when present in a single line
        comment_pattern = re.compile(
            r"--\s*Job:\s*(?P<job>.*?)\s+--\s*Task\s*(?P<task>.*?)(?P<sql>(?:update|insert|select|delete|with|create|alter|drop)\b.*)",
            re.IGNORECASE | re.DOTALL,
        )
        comment_match = comment_pattern.match(query_text_raw.strip())
        if comment_match:
            job_name = f"-- Job: {comment_match.group('job').strip()}"
            query_name = f"-- Task {comment_match.group('task').strip()}"
            query_text = comment_match.group("sql").strip()
        else:
            query_lines = [line.strip() for line in query_text_raw.splitlines() if line.strip()]
            if len(query_lines) >= 2 and query_lines[0].startswith("--") and query_lines[1].startswith("--"):
                job_name = query_lines[0]
                query_name = query_lines[1]
                query_text = "\n".join(query_lines[2:]).strip()
            elif query_lines:
                query_text = "\n".join(query_lines[1:]).strip() if query_lines[0].startswith("--") else "\n".join(query_lines)

    job_name = job_name.replace("\t", "").replace("\n", "")
    query_name = query_name.replace("\t", "").replace("\n", "")

    plan_root = plan_json_obj.get("Plan")
    if not isinstance(plan_root, dict):
        raise ValueError("JSON plan payload is missing a Plan object.")

    startup_cost = plan_root.get("Startup Cost")
    total_cost = plan_root.get("Total Cost")

    rows = plan_root.get("Actual Rows") if plan_root.get("Actual Rows") is not None else plan_root.get("Plan Rows")

    def _first_actual_rows(node: dict[str, Any]) -> int | None:
        """Return the first non-zero Actual Rows found depth-first in child plans."""
        plans = node.get("Plans")
        if not isinstance(plans, list):
            return None
        for child in plans:
            if not isinstance(child, dict):
                continue
            actual = child.get("Actual Rows")
            if isinstance(actual, (int, float)) and actual > 0:
                return int(actual)
            fallback = _first_actual_rows(child)
            if fallback is not None:
                return fallback
        return None

    if rows == 0:
        nested_rows = _first_actual_rows(plan_root)
        if nested_rows is not None:
            rows = nested_rows

    buffers = {
        "shared_hit": plan_root.get("Shared Hit Blocks"),
        "shared_read": plan_root.get("Shared Read Blocks"),
        "shared_dirtied": plan_root.get("Shared Dirtied Blocks"),
        "shared_written": plan_root.get("Shared Written Blocks"),
        "temp_read": plan_root.get("Temp Read Blocks"),
        "temp_written": plan_root.get("Temp Written Blocks"),
    }
    wal = {
        "records": plan_root.get("WAL Records"),
        "fpi": plan_root.get("WAL FPI"),
        "bytes": plan_root.get("WAL Bytes"),
    }

    title = (job_name + " " + query_name).strip()
    if not title:
        title = query_text

    result = {
        "timestamp": timestamp,
        "query_name": query_name,
        "job_name": job_name,
        "title": title,
        "query_text": query_text,
        "execution_plan": json.dumps(plan_json_obj, indent=2),
        "duration": duration_ms,
        "startup_cost": startup_cost,
        "cost": total_cost,
        "rows": rows,
        "buffers": buffers,
        "wal": wal,
    }

    logger.debug(
        f"Completed parsing JSON log entry: timestamp={timestamp}, duration={duration_ms}ms, "
        f"cost={total_cost}, rows={rows}, buffers={buffers}, wal={wal}"
    )

    return result


class JsonLogParser(AbstractLogParser):
    def __init__(self):
        super().__init__()

    def _process_plain_text_file(self, file_obj, log_file_path):
        logger.info(f"Processing JSON log file {file_obj.name} from {log_file_path}")
        buffer_lines: list[str] = []
        in_plan = False
        current_entry_line: int | None = None
        lines_processed = 0
        for line_number, line in enumerate(file_obj, start=1):
            lines_processed += 1
            if not in_plan and "plan:" in line:
                in_plan = True
                buffer_lines = [line]
                current_entry_line = line_number
                continue

            if in_plan:
                if re.match(r"^\d{4}-\d{2}-\d{2} ", line):
                    # Next log entry reached; parse current buffer and continue with new entry
                    try:
                        log_entry_text = "".join(buffer_lines)
                        parsed_entry = parse_json_log_entry(log_entry_text)
                        parsed_entry["source_line"] = current_entry_line
                        yield parsed_entry
                    except ValueError as e:
                        logger.warning(f"Skipping JSON log entry due to parsing error: {e}")
                    buffer_lines = [line]
                    in_plan = "plan:" in line
                    current_entry_line = line_number if in_plan else None
                else:
                    buffer_lines.append(line)

        # Handle final buffered entry if any
        if buffer_lines and in_plan:
            try:
                log_entry_text = "".join(buffer_lines)
                parsed_entry = parse_json_log_entry(log_entry_text)
                parsed_entry["source_line"] = current_entry_line
                yield parsed_entry
            except ValueError as e:
                logger.warning(f"Skipping JSON log entry due to parsing error: {e}")

        self.total_log_lines_processed += lines_processed

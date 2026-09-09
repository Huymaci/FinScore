import csv
import hashlib
import io
import json
import os
import re
import unicodedata
import zipfile
from datetime import date, datetime, timedelta
from xml.etree import ElementTree

from sqlalchemy import delete, func, select, update
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import CategorizationRule, Category, ImportBatch, ImportError, ImportTemplate, Transaction, utcnow
from app.repositories import AccountRepository

from .common import ValidationError, owned_or_404
from .statement_profiler import detect_number_convention, infer_layout, parse_number, to_import_mapping
from .statement_profiler import parse_date as profile_date

ALLOWED = {".csv", ".xlsx"}
PREVIEW_PAGE_SIZE = 25

AUTO_HEADER_ALIASES = {
    "date": {"date", "transaction date", "posting date", "trans date", "ngay", "ngay giao", "ngay giao dich", "ngay hach toan"},
    "description": {"description", "details", "remark", "remarks", "transaction details", "noi dung", "dien giai", "mo ta"},
    "amount": {"amount", "transaction amount", "signed amount", "so tien"},
    "debit": {"debit", "debit amount", "withdrawal", "withdrawal amount", "ghi no", "phat sinh no", "so tien ghi no", "tien ra"},
    "credit": {"credit", "credit amount", "deposit", "deposit amount", "ghi co", "phat sinh co", "so tien ghi co", "tien vao"},
    "direction": {"direction", "transaction type", "type", "loai giao dich", "thu chi"},
    "ref_no": {"ref", "ref no", "reference", "reference no", "transaction id", "transaction no", "ma giao dich", "so tham chieu", "so but toan"},
}


def _safe_recompute(user_id):
    """Recompute alerts after an import change without letting a failure there
    turn an already-committed import into a 500. The transactions are saved; a
    stale alert set is recoverable on the next nightly pass.
    """
    from flask import current_app

    from .alerts import recompute
    try:
        recompute(user_id)
    except Exception:
        db.session.rollback()
        current_app.logger.exception("alert recompute failed after import change for user %s", user_id)


def dedup_key(account_id, posted_at, amount, ref_no, description):
    canonical = "|".join((str(account_id), posted_at.date().isoformat(), str(amount), ref_no.strip(), description.strip()))
    return hashlib.sha256(canonical.encode("utf-8")).digest()


def _future_date_message(posted_at, row_number=None, current_date=None):
    current_date = current_date or date.today()
    if posted_at.date() <= current_date:
        return None
    prefix = f"Dòng {row_number}: " if row_number is not None else ""
    return (
        f"{prefix}Ngày giao dịch {posted_at.date().isoformat()} vượt quá "
        f"ngày hiện tại {current_date.isoformat()}"
    )


# NFR-06: an XLSX is a zip, so the 5 MB MAX_CONTENT_LENGTH bounds only the
# *compressed* upload. A 797 KB file that inflates to 800 MB was measured
# exhausting the worker's memory; at the full 5 MB allowance the same ratio
# reaches roughly 5 GB. Every member is therefore checked against its declared
# size first and then streamed with a hard cap, because file_size is attacker
# controlled and cannot be trusted on its own.
MAX_UNCOMPRESSED_MEMBER = 32 * 1024 * 1024
MAX_UNCOMPRESSED_TOTAL = 64 * 1024 * 1024


def _safe_read(package, name, budget):
    info = package.getinfo(name)
    if info.file_size > MAX_UNCOMPRESSED_MEMBER or info.file_size > budget[0]:
        raise ValidationError("Tệp XLSX giải nén vượt giới hạn cho phép")
    with package.open(name) as handle:
        data = handle.read(MAX_UNCOMPRESSED_MEMBER + 1)
    if len(data) > MAX_UNCOMPRESSED_MEMBER or len(data) > budget[0]:
        raise ValidationError("Tệp XLSX giải nén vượt giới hạn cho phép")
    budget[0] -= len(data)
    return data


def _xlsx_rows(content):
    if not content.startswith(b"PK\x03\x04"):
        raise ValidationError("Tệp XLSX không có magic byte ZIP hợp lệ")
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        budget = [MAX_UNCOMPRESSED_TOTAL]
        shared = []
        if "xl/sharedStrings.xml" in package.namelist():
            root = ElementTree.fromstring(_safe_read(package, "xl/sharedStrings.xml", budget))
            shared = ["".join(node.text or "" for node in item.iter() if node.tag.endswith("}t")) for item in root]
        sheet_name = next((name for name in package.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")), None)
        if not sheet_name:
            raise ValidationError("Không tìm thấy worksheet trong XLSX")
        root = ElementTree.fromstring(_safe_read(package, sheet_name, budget))
        table = []
        for row in (n for n in root.iter() if n.tag.endswith("}row")):
            values = []
            for cell in (n for n in row if n.tag.endswith("}c")):
                reference = cell.attrib.get("r", "A1")
                letters = re.match(r"[A-Z]+", reference).group(0)
                column = 0
                for letter in letters:
                    column = column * 26 + ord(letter) - 64
                while len(values) < column - 1:
                    values.append("")
                raw = next((n.text or "" for n in cell.iter() if n.tag.endswith("}v")), "")
                if cell.attrib.get("t") == "inlineStr":
                    raw = "".join(n.text or "" for n in cell.iter() if n.tag.endswith("}t"))
                values.append(shared[int(raw)] if cell.attrib.get("t") == "s" and raw else raw)
            table.append(values)
        return table


CSV_DELIMITERS = (",", ";", "\t", "|")


def _sniff_delimiter(text, sample_lines=60):
    """Pick the delimiter that splits the data rows most consistently.

    csv.Sniffer gives up on real statements: it samples the first 8 KB, which
    on these files begins with letterhead lines carrying no delimiter at all,
    and raises "Could not determine delimiter". Semicolons matter in practice
    because that is what Excel writes in locales where the comma is the decimal
    separator. Counting candidates across the lines that do look tabular is
    both simpler and steadier than sniffing prose.
    """
    lines = [line for line in text.splitlines() if line.strip()][:sample_lines]
    if not lines:
        return ","
    best, best_score = ",", 0
    for candidate in CSV_DELIMITERS:
        counts = [line.count(candidate) for line in lines]
        tabular = [count for count in counts if count > 0]
        if len(tabular) < 2:
            continue
        # Reward a high field count that repeats identically on many lines:
        # that is what a real column layout looks like.
        modal = max(set(tabular), key=tabular.count)
        score = modal * tabular.count(modal)
        if score > best_score:
            best, best_score = candidate, score
    return best


def _table(content, extension):
    if extension == ".xlsx":
        return _xlsx_rows(content)
    if b"\x00" in content[:1024]:
        raise ValidationError("Tệp CSV không hợp lệ")
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ValidationError("CSV UTF-16 chưa được hỗ trợ; hãy lưu lại dưới dạng CSV UTF-8")
    decoded = None
    for encoding in ("utf-8-sig", "cp1258", "cp1252"):
        try:
            decoded = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise ValidationError("Không đọc được encoding của tệp CSV")
    return list(csv.reader(io.StringIO(decoded), delimiter=_sniff_delimiter(decoded)))


def _header_name(value):
    decomposed = unicodedata.normalize("NFKD", str(value).strip().lower())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def _alias_mapping(rows, required=True):
    best = None
    for row_index, row in enumerate(rows[:15]):
        mapping = {"header_rows": row_index + 1, "date_formats": ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"]}
        for column, heading in enumerate(row):
            normalised = _header_name(heading)
            for key, aliases in AUTO_HEADER_ALIASES.items():
                if any(
                    normalised == alias or alias in normalised or (len(normalised) >= 4 and normalised in alias)
                    for alias in aliases
                ) and key not in mapping:
                    mapping[key] = column
                    break
        valid_amount = "amount" in mapping or "debit" in mapping or "credit" in mapping
        score = sum(key in mapping for key in AUTO_HEADER_ALIASES)
        if "date" in mapping and valid_amount and (best is None or score > best[0]):
            best = score, mapping
    if best is None and required:
        raise ValidationError("Không tự nhận diện được cột ngày và số tiền. Hãy kiểm tra hàng tiêu đề của CSV")
    return best[1] if best else None


def _auto_mapping(rows):
    """Infer arbitrary statement layouts, retaining header-only roles as hints."""
    aliases = _alias_mapping(rows, required=False)
    try:
        result = infer_layout(rows)
        mapping = to_import_mapping(result)
        # When the running balance proves the numeric mapping, retain it and use
        # headers only for semantic text. Without that proof, an explicit header
        # is safer than a statistical guess (for example STT versus Số tiền).
        header_roles = ("description", "ref_no", "direction") if result.balance_verified else tuple(AUTO_HEADER_ALIASES)
        if aliases and not result.balance_verified:
            if "amount" in aliases:
                mapping.pop("debit", None)
                mapping.pop("credit", None)
            elif "debit" in aliases or "credit" in aliases:
                mapping.pop("amount", None)
        for role in header_roles:
            if aliases and role in aliases:
                mapping[role] = aliases[role]
        headers = rows[result.header_row] if result.header_row < len(rows) else []
        mapping["_detection"] = {
            "header_row": result.header_row + 1,
            "confidence": result.confidence,
            "balance_verified": result.balance_verified,
            "needs_review": result.needs_human_review,
            "columns": {
                role: str(headers[index]).strip()
                for role, index in mapping.items()
                if role in AUTO_HEADER_ALIASES and isinstance(index, int) and index < len(headers)
            },
        }
        return mapping
    except ValueError:
        mapping = aliases or _alias_mapping(rows)
        header_index = mapping["header_rows"] - 1
        headers = rows[header_index] if header_index < len(rows) else []
        mapping["_detection"] = {
            "header_row": mapping["header_rows"],
            "confidence": 0.7,
            "balance_verified": False,
            "needs_review": True,
            "columns": {
                role: str(headers[index]).strip()
                for role, index in mapping.items()
                if role in AUTO_HEADER_ALIASES and isinstance(index, int) and index < len(headers)
            },
        }
        return mapping


def _parse_date(value, mapping):
    order = "mdy" if (mapping.get("date_formats") or [""])[0].startswith("%m") else "dmy"
    raw = value
    if isinstance(value, str) and re.fullmatch(r"\d+(?:\.0+)?", value.strip()):
        raw = float(value)
    profiled = profile_date(raw, order)
    if profiled:
        return profiled
    formats = mapping.get("date_formats") or [mapping.get("date_format", "%Y-%m-%d")]
    for date_format in formats:
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue
    raise ValueError(f"Ngày không hợp lệ: {value}")


def _amount_int(raw, convention="en"):
    """Parse a statement money cell to a signed integer VND.

    Delegates to statement_profiler.parse_number with the convention the column
    was profiled as (vn: 1.234.567,89 / en: 1,234,567.89). This function used to
    guess the thousands/decimal marks per cell, so the profiler could prove a
    column was the amount under one reading while preview() then parsed the same
    cell under another. One parser, one reading (P2.5).
    """
    parsed = parse_number(raw, convention)
    if parsed is None:
        raise ValueError("Thiếu số tiền")
    return int(round(parsed))


def _zero_as_absent(raw, convention="en"):
    """Return the parsed amount, or None when the cell is blank or zero."""
    if not str(raw).strip():
        return None
    parsed = parse_number(raw, convention)
    if parsed is None:
        return None
    return int(round(parsed)) or None


def _statement_number_convention(mapping, rows, start):
    """Decide vn vs en once for the whole file from its amount/debit/credit
    columns, matching how statement_profiler settles it per column. Only used as
    a fallback: a mapping that came through the profiler already carries a
    proven `number_convention`, and setdefault() leaves that untouched.
    """
    columns = [mapping[role] for role in ("amount", "debit", "credit") if isinstance(mapping.get(role), int)]
    sample = [
        text
        for row in rows[start:]
        for text in (str(row[column]).strip() for column in columns if column < len(row))
        if text
    ]
    return detect_number_convention(sample) if sample else "en"


def _parse_row(row, mapping):
    convention = mapping.get("number_convention", "en")

    def value(key):
        column = mapping.get(key)
        if column is None or column >= len(row):
            return ""
        return str(row[column]).strip()
    posted_at = _parse_date(value("date"), mapping)
    description = value("description")
    ref_no = value("ref_no")
    if mapping.get("amount") is not None:
        signed = _amount_int(value("amount"), convention)
        direction_value = _header_name(value("direction"))
        outgoing = {"out", "debit", "expense", "withdrawal", "chi", "ghi no", "tien ra"}
        incoming = {"in", "credit", "income", "deposit", "thu", "ghi co", "tien vao"}
        direction = "OUT" if direction_value in outgoing else "IN" if direction_value in incoming else "IN" if signed >= 0 else "OUT"
        amount = abs(signed)
    else:
        # Several Vietnamese banks write the unused side as "0.00" rather than
        # leaving it blank. Testing the raw string means "0.00" is truthy, so
        # every incoming row was charged to the debit branch, evaluated to zero
        # and rejected — silently dropping every salary and transfer received.
        # Measured on the MB-template files: exactly the 15 credit rows failed.
        # Compare parsed values instead.
        debit = _zero_as_absent(value("debit"), convention)
        credit = _zero_as_absent(value("credit"), convention)
        if debit is not None and credit is not None:
            raise ValueError("Dòng có cả ghi nợ và ghi có")
        if debit is not None:
            amount, direction = abs(debit), "OUT"
        elif credit is not None:
            amount, direction = abs(credit), "IN"
        else:
            raise ValueError("Thiếu số tiền ghi nợ/ghi có")
    if amount <= 0:
        raise ValueError("Số tiền phải lớn hơn 0")
    return posted_at, amount, direction, ref_no, description


def _public_import_row(row):
    return {key: value for key, value in row.items() if key != "dedup_key"}


def _preview_page_data(payload, page=1, per_page=PREVIEW_PAGE_SIZE):
    rows = payload.get("rows", [])
    summary = payload.get("summary", {})
    errors = payload.get("errors", summary.get("errors", []))
    entries = [(row.get("row_number", 0), "row", row) for row in rows]
    entries.extend((error.get("row_number", 0), "error", error) for error in errors)
    entries.sort(key=lambda entry: entry[0])
    total = len(entries)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(int(page), 1), pages)
    start = (page - 1) * per_page
    selected = entries[start:start + per_page]
    return {
        "rows": [_public_import_row(item) for _, kind, item in selected if kind == "row"],
        "errors": [item for _, kind, item in selected if kind == "error"],
        "page": page,
        "pages": pages,
        "per_page": per_page,
        "preview_total": total,
        "preview_truncated": pages > 1,
    }


def preview(user, account_id, template_id, uploaded):
    account = owned_or_404(AccountRepository.owned(account_id, user.id, include_archived=False))
    template_query = select(ImportTemplate).where(ImportTemplate.active.is_(True))
    if template_id is None:
        # The current import screen intentionally has no bank-template picker;
        # files are profiled automatically. Keep accepting an explicit ID for
        # API clients and older screens.
        template_query = template_query.where(ImportTemplate.bank_code == "AUTO").order_by(ImportTemplate.id)
    else:
        template_query = template_query.where(ImportTemplate.id == template_id)
    template = db.session.scalar(template_query.limit(1))
    if not template:
        raise ValidationError("Không có mẫu tự nhận diện đang hoạt động; hãy chạy migration và seed dữ liệu")
    filename = secure_filename(uploaded.filename or "")
    extension = os.path.splitext(filename)[1].lower()
    if extension not in ALLOWED:
        raise ValidationError("Chỉ chấp nhận .csv hoặc .xlsx")
    content = uploaded.read()
    rows = _table(content, extension)
    mapping = json.loads(template.mapping_json)
    if mapping.get("auto_detect"):
        mapping = _auto_mapping(rows)
    header_index = max(int(mapping.get("header_rows", 1)) - 1, 0)
    headers = rows[header_index] if header_index < len(rows) else []
    detection = mapping.get("_detection") or {
        "header_row": header_index + 1,
        "confidence": 1.0,
        "balance_verified": False,
        "needs_review": False,
        "columns": {
            role: str(headers[index]).strip()
            for role, index in mapping.items()
            if role in AUTO_HEADER_ALIASES and isinstance(index, int) and index < len(headers)
        },
    }
    results, errors, duplicates, probable = [], [], 0, 0
    seen = set()
    existing = set(db.session.scalars(select(Transaction.dedup_key).where(Transaction.account_id == account.id, Transaction.dedup_key.is_not(None))))
    categories = _available_categories(user.id)
    rules = list(db.session.scalars(select(CategorizationRule).where(CategorizationRule.active.is_(True)).order_by(CategorizationRule.priority)))
    start = int(mapping.get("header_rows", 1))
    mapping.setdefault("number_convention", _statement_number_convention(mapping, rows, start))
    current_date = date.today()
    for row_number, row in enumerate(rows[start:], start=start + 1):
        if not any(str(cell).strip() for cell in row if cell is not None):
            continue
        try:
            posted_at, amount, direction, ref_no, description = _parse_row(row, mapping)
            future_date_message = _future_date_message(posted_at, current_date=current_date)
            if future_date_message:
                raise ValueError(future_date_message)
            key = dedup_key(account.id, posted_at, amount, ref_no, description)
            if key in existing or key in seen:
                duplicates += 1
                continue
            seen.add(key)
            fuzzy = db.session.scalar(select(Transaction.id).where(
                Transaction.account_id == account.id,
                Transaction.source == "MANUAL",
                Transaction.posted_at >= posted_at - timedelta(days=1),
                Transaction.posted_at <= posted_at + timedelta(days=1),
                Transaction.amount >= int(amount * 0.99),
                Transaction.amount <= int(amount * 1.01),
            ).limit(1))
            if fuzzy:
                probable += 1
            suggestion = _category_suggestion(user, description, direction, categories, rules)
            results.append({
                "row_number": row_number,
                "date": posted_at.date().isoformat(),
                "amount": amount,
                "category_id": suggestion["id"], "category_name": suggestion["name"],
                "category_confidence": suggestion["confidence"], "category_reason": suggestion["reason"],
                "description": description, "direction": direction, "ref_no": ref_no,
                "account_id": account.id, "account_name": account.name,
                "dedup_key": key.hex(), "probable_duplicate_id": fuzzy,
            })
        except (ValueError, IndexError) as exc:
            reason = str(exc)
            errors.append({
                "row_number": row_number,
                "reason": reason,
                "type": "FUTURE_DATE" if reason.startswith("Ngày giao dịch ") else "INVALID_ROW",
            })
    summary = {
        "new": len(results),
        "duplicate": duplicates,
        "probable_duplicate": probable,
        "error": len(errors),
        "future_date_error": sum(error["type"] == "FUTURE_DATE" for error in errors),
        "conflicts": [_public_import_row(row) for row in results if row.get("probable_duplicate_id")],
        "account": {"id": account.id, "name": account.name},
        "categories": [{"id": category.id, "name": category.name} for category in categories],
        "detection": detection,
    }
    payload = {"summary": summary.copy(), "rows": results, "errors": errors}
    first_page = _preview_page_data(payload)
    summary.update(first_page)
    summary["sample"] = first_page["rows"][:10]
    batch = ImportBatch(user_id=user.id, account_id=account.id, template_id=template.id, filename=filename, preview_json=json.dumps(payload, ensure_ascii=False))
    db.session.add(batch)
    db.session.flush()
    db.session.add_all(ImportError(batch_id=batch.id, row_number=error["row_number"], reason=error["reason"]) for error in errors)
    db.session.commit()
    summary["batch_id"] = batch.id
    return summary


def preview_page(user, batch_id, page=1, per_page=PREVIEW_PAGE_SIZE):
    batch = db.session.scalar(select(ImportBatch).where(
        ImportBatch.id == batch_id,
        ImportBatch.user_id == user.id,
        ImportBatch.status == "PREVIEW",
    ))
    if not batch:
        raise ValidationError("Bản xem trước không tồn tại hoặc đã được xử lý")
    per_page = min(max(int(per_page), 1), 100)
    return _preview_page_data(json.loads(batch.preview_json), page, per_page)


def _normalise(value):
    decomposed = unicodedata.normalize("NFKD", value.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _available_categories(user_id):
    return list(db.session.scalars(select(Category).where(
        Category.nature.is_not(None),
        (Category.owner_id.is_(None)) | (Category.owner_id == user_id),
    ).order_by(Category.owner_id, Category.name)))


def _category_suggestion(user, description, direction, categories=None, rules=None):
    categories = categories or _available_categories(user.id)
    if not categories:
        raise ValidationError("Chưa có danh mục khả dụng để nhập giao dịch")
    available = {category.id: category for category in categories}
    rules = rules or list(db.session.scalars(select(CategorizationRule).where(CategorizationRule.active.is_(True)).order_by(CategorizationRule.priority)))
    merchant = _normalise(description)
    for rule in rules:
        try:
            matched = re.search(rule.pattern, merchant, re.IGNORECASE)
        except re.error:
            matched = False
        if matched and rule.category_id in available:
            category = available[rule.category_id]
            return {"id": category.id, "name": category.name, "confidence": 0.98, "reason": "rule"}

    preferred = ("thu nhap", "income") if direction == "IN" else ()
    by_name = {_normalise(category.name): category for category in categories}
    for name in preferred:
        if name in by_name:
            category = by_name[name]
            return {"id": category.id, "name": category.name, "confidence": 0.9, "reason": "direction"}

    for category in categories:
        category_name = _normalise(category.name)
        if len(category_name) >= 3 and category_name in merchant:
            return {"id": category.id, "name": category.name, "confidence": 0.8, "reason": "category_name"}

    for fallback in ("khac", "uncategorised"):
        if fallback in by_name:
            category = by_name[fallback]
            return {"id": category.id, "name": category.name, "confidence": 0.45, "reason": "fallback"}
    category = categories[0]
    return {"id": category.id, "name": category.name, "confidence": 0.25, "reason": "fallback"}


def _classified_category(user, description, direction="OUT"):
    return _category_suggestion(user, description, direction)["id"]


def confirm(user, batch_id, decisions=None, category_overrides=None, notes=None):
    batch = db.session.scalar(select(ImportBatch).where(ImportBatch.id == batch_id, ImportBatch.user_id == user.id, ImportBatch.status == "PREVIEW"))
    if not batch:
        raise ValidationError("Batch preview không tồn tại hoặc đã được xử lý")
    decisions = decisions or {}
    category_overrides = category_overrides or {}
    notes = notes or {}
    payload = json.loads(batch.preview_json)
    added = 0
    try:
        for row in payload["rows"]:
            row_key = str(row["row_number"])
            posted_at = datetime.strptime(row["date"], "%Y-%m-%d")
            future_date_message = _future_date_message(posted_at, row["row_number"])
            if future_date_message:
                raise ValidationError(future_date_message)
            decision = decisions.get(row_key, "KEEP")
            if decision not in {"KEEP", "MERGE", "REJECT"}:
                raise ValidationError(f"Lựa chọn import không hợp lệ tại dòng {row_key}")
            if decision in {"MERGE", "REJECT"}:
                continue
            raw_key = bytes.fromhex(row["dedup_key"])
            if db.session.scalar(select(Transaction.id).where(Transaction.dedup_key == raw_key)):
                continue
            category_id = category_overrides.get(row_key) or row.get("category_id") or _classified_category(user, row["description"], row["direction"])
            category = db.session.scalar(select(Category).where(Category.id == int(category_id), (Category.owner_id.is_(None)) | (Category.owner_id == user.id)))
            if not category:
                raise ValidationError(f"Category override không hợp lệ tại dòng {row_key}")
            note = str(notes.get(row_key, "")).strip()
            if len(note) > 500:
                raise ValidationError(f"Ghi chú không được vượt quá 500 ký tự tại dòng {row_key}")
            db.session.add(Transaction(import_batch_id=batch.id, account_id=batch.account_id, category_id=category.id, posted_at=posted_at, amount=row["amount"], direction=row["direction"], description=row["description"], note=note, ref_no=row["ref_no"], source="IMPORT", dedup_key=raw_key))
            added += 1
        batch.status = "COMMITTED"
        batch.created_at = utcnow()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    _safe_recompute(user.id)
    return added


def cancel_preview(user, batch_id):
    batch = db.session.scalar(select(ImportBatch).where(
        ImportBatch.id == batch_id,
        ImportBatch.user_id == user.id,
        ImportBatch.status == "PREVIEW",
    ))
    if not batch:
        raise ValidationError("Bản xem trước không tồn tại hoặc đã được xử lý")
    db.session.execute(delete(ImportError).where(ImportError.batch_id == batch.id))
    db.session.delete(batch)
    db.session.commit()


def _detach_import_batches(batch_ids):
    """Import history is metadata. Deleting it must leave committed financial
    transactions intact, so surviving rows are unlinked instead of removed."""
    db.session.execute(update(Transaction).where(
        Transaction.import_batch_id.in_(batch_ids)
    ).values(import_batch_id=None))
    db.session.execute(delete(ImportError).where(ImportError.batch_id.in_(batch_ids)))
    db.session.execute(delete(ImportBatch).where(ImportBatch.id.in_(batch_ids)))


def _delete_batch_transactions(batch_ids):
    transactions = list(db.session.scalars(select(Transaction).where(
        Transaction.import_batch_id.in_(batch_ids),
    )))
    for transaction in transactions:
        db.session.delete(transaction)
    return len(transactions)


def _remove_import_history(user, batch_ids, remove_transactions):
    if not batch_ids:
        return {"deleted": 0, "removed_transactions": 0}
    removed = 0
    try:
        if remove_transactions:
            removed = _delete_batch_transactions(batch_ids)
        _detach_import_batches(batch_ids)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    # Balances only move when transactions went with the history entry.
    if removed:
        _safe_recompute(user.id)
    return {"deleted": len(batch_ids), "removed_transactions": removed}


def delete_import_history(user, batch_id, remove_transactions=False):
    """Delete one history entry the user owns, keeping or removing the
    transactions that import created as the user chose."""
    batch = db.session.scalar(select(ImportBatch).where(
        ImportBatch.id == batch_id,
        ImportBatch.user_id == user.id,
        ImportBatch.status.in_(("COMMITTED", "REVERTED")),
    ))
    if not batch:
        raise ValidationError("Lần nhập sao kê không tồn tại")
    return _remove_import_history(user, [batch.id], remove_transactions)


def clear_import_history(user, remove_transactions=False, batch_ids=None):
    """Delete history entries in one step: the ones the user selected, or every
    entry they own when no selection is given. Ownership is re-checked here, so
    ids belonging to somebody else are simply not matched."""
    query = select(ImportBatch.id).where(
        ImportBatch.user_id == user.id,
        ImportBatch.status.in_(("COMMITTED", "REVERTED")),
    )
    if batch_ids is not None:
        query = query.where(ImportBatch.id.in_(batch_ids))
    return _remove_import_history(user, list(db.session.scalars(query)), remove_transactions)


def import_history(user, limit=50):
    batches = list(db.session.scalars(
        select(ImportBatch).where(
            ImportBatch.user_id == user.id,
            ImportBatch.status.in_(("COMMITTED", "REVERTED")),
        ).order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc()).limit(limit)
    ))
    batch_ids = [batch.id for batch in batches]
    # One grouped count for the whole page rather than a query per batch (NFR-09).
    counts = dict(db.session.execute(
        select(Transaction.import_batch_id, func.count())
        .where(Transaction.import_batch_id.in_(batch_ids))
        .group_by(Transaction.import_batch_id)
    ).all()) if batch_ids else {}
    items = []
    for batch in batches:
        transaction_count = counts.get(batch.id, 0)
        items.append({
            "id": batch.id,
            "filename": batch.filename,
            "account_id": batch.account_id,
            "status": batch.status,
            "transaction_count": transaction_count,
            "created_at": batch.created_at.isoformat(),
            "can_delete_transactions": batch.status == "COMMITTED",
        })
    return items


def delete_imported_transactions(user, batch_id):
    """Remove transactions created by a committed import, without a time limit."""
    batch = db.session.scalar(select(ImportBatch).where(
        ImportBatch.id == batch_id,
        ImportBatch.user_id == user.id,
        ImportBatch.status == "COMMITTED",
    ))
    if not batch:
        raise ValidationError("Lần nhập sao kê không tồn tại hoặc giao dịch đã được xóa")

    transactions = list(db.session.scalars(select(Transaction).where(
        Transaction.import_batch_id == batch.id,
    )))
    try:
        for transaction in transactions:
            db.session.delete(transaction)
        batch.status = "REVERTED"
        batch.reverted_at = utcnow()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    _safe_recompute(user.id)
    return len(transactions)


def error_csv(user, batch_id):
    batch = db.session.scalar(select(ImportBatch).where(ImportBatch.id == batch_id, ImportBatch.user_id == user.id))
    if not batch:
        from flask import abort
        abort(404)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["row_number", "reason"])
    for error in db.session.scalars(select(ImportError).where(ImportError.batch_id == batch.id).order_by(ImportError.row_number)):
        writer.writerow([error.row_number, error.reason])
    return io.BytesIO(output.getvalue().encode("utf-8-sig"))

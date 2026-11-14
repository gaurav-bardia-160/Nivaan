"""Domain router for pre-retrieval intent classification and strict domain isolation."""
from __future__ import annotations
from backend.modules.explainer import QueryModality, classify_query_modality

import re
from enum import Enum
from typing import Optional


class Domain(str, Enum):
    TRANSPORT = "transport"
    EDUCATION = "education"
    IDENTITY = "identity"
    TAXATION = "taxation"
    BANKING = "banking"
    AGRICULTURE = "agriculture"
    LEGAL_CONSUMER = "legal_consumer"
    GENERAL_CIVIC = "general_civic"
    UNCOVERED = "uncovered"
    UNKNOWN = "unknown"


# Uncovered domain patterns to prevent nearest-neighbor RAG bleed
_UNCOVERED_DOMAIN_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "mca_spice": (
        re.compile(
            r"(?:"
            r"\b(?:"
            r"mca|mca21|spice\s+plus|spice\s+part|form\s+spice|roc|registrar\s+of\s+companies|"
            r"director\s+identification\s+number|"
            r"din\s+(?:number|no|kyc|status|application|allotment|verification|portal|form|details)|"
            r"(?:director|mca)\s+din|\bcin\b|corporate\s+affairs|"
            r"incorporat(?:e|ion)\s+(?:of\s+)?(?:(?:a|the)\s+)?(?:new\s+)?company|"
            r"company\s+incorporat(?:e|ion)|company\s+registration|"
            r"private\s+limited\s+company|public\s+limited\s+company|"
            r"one\s+person\s+company|\bopc\b|\bllp\b|limited\s+liability\s+partnership|"
            r"inc-?29|inc-?32|dir-?3|mgt-?7"
            r")\b"
            r"|\bspice\+(?!\w)"
            r")",
            re.IGNORECASE,
        ),
        # Case-sensitive DIN acronym check (only uppercase DIN to prevent collision with Hindi 'din' = days)
        re.compile(r"\bDIN\b"),
    ),
    "petroleum_lpg": (
        re.compile(
            r"\b(?:"
            r"lpg|liquefied\s+petroleum|gas\s+cylinder|cylinder\s+booking|commercial\s+cylinder|"
            r"domestic\s+cylinder|indane|bharat\s*gas|hp\s*gas|omc|refill\s+booking|"
            r"subsidized\s+cylinder|"
            r"pahal\s+(?:scheme|yojana|dbtl|subsidy|lpg)|(?:lpg|dbtl)\s+pahal|"
            r"dbtl|mopng|cooking\s+gas|gas\s+subsidy|gas\s+connection|"
            r"cylinder\s+(?:delivery|booking|refill|status|subsidy|agency|delay|delayed)"
            r")\b",
            re.IGNORECASE,
        ),
        # Case-sensitive PAHAL acronym
        re.compile(r"\bPAHAL\b"),
    ),
    "nsp_scholarships": (
        re.compile(
            r"\b(?:"
            r"nsp|national\s+scholarship\s+portal|"
            r"pre[-\s]?matric\s+scholarship|post[-\s]?matric\s+scholarship|"
            r"merit[-\s]cum[-\s]means|scholarship\s+disbursement|scholarship\s+scheme|"
            r"scholarship\s+(?:portal|application|status|registration)|"
            r"scholarships\.gov\.in"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    "trademark_patent": (
        re.compile(r"\b(?:patent|trademark|ipindia|copyright\s+office)\b", re.IGNORECASE),
    ),
}


# Domain-defining entities and acronyms (ordered by specificity)
_DOMAIN_PATTERNS: dict[Domain, tuple[re.Pattern[str], ...]] = {
    Domain.TRANSPORT: (
        re.compile(r"\b(?:fastag|fast-tag|fast\s+tag|toll|toll\s+plaza|nhai|ihmcl)\b", re.IGNORECASE),
        re.compile(r"\b(?:parivahan|mparivahan|vahan|sarathi|rto)\b", re.IGNORECASE),
        re.compile(r"\b(?:rc\b|registration\s+certificate|chassis|chasis)\b", re.IGNORECASE),
        re.compile(r"\b(?:traffic\s+police|traffic\s+fine|challan|echallan|e-challan)\b", re.IGNORECASE),
        re.compile(r"\b(?:driving\s+licen[sc]e|learner\s+licen[sc]e|\bdl\b)\b", re.IGNORECASE),
        re.compile(r"\b(?:motor\s+vehicle|road\s+tax|vehicle\s+fitness|hypothecation|puc)\b", re.IGNORECASE),
    ),
    Domain.EDUCATION: (
        re.compile(r"\b(?:cbse|icse|cisce|state\s+board|nios)\b", re.IGNORECASE),
        re.compile(r"\b(?:marksheet|mark\s+sheet|board\s+exam|roll\s+number)\b", re.IGNORECASE),
        re.compile(r"\b(?:passing\s+certificate|migration\s+certificate|provisional\s+certificate)\b", re.IGNORECASE),
        re.compile(r"\b(?:class\s+(?:10|12|x|xii)|tenth\s+marksheet|twelfth\s+marksheet)\b", re.IGNORECASE),
        re.compile(r"\b(?:school\s+board|college\s+degree|degree\s+certificate)\b", re.IGNORECASE),
    ),
    Domain.IDENTITY: (
        re.compile(r"\b(?:digilocker|digi\s+locker)\b", re.IGNORECASE),
        re.compile(r"\b(?:aadhaar|aadhar|uidai|eaadhaar|pvc\s+card|baal\s+aadhaar|mbu|srn|error\s+330|biometric\s+lock|biometric\s+unlock|cross-limit|name\s+and\s+gender\s+update|dob\s+update|aadhaar\s+handbook|citizen\s+charter)\b", re.IGNORECASE),
        re.compile(r"\b(?:pan\s+card|pancard|form\s+49a|form\s+49aa|e-pan|epan|utiitsl|protean|tin-pan)\b", re.IGNORECASE),
        re.compile(r"\b(?:passport|psk|popsk|tatkaal)\b", re.IGNORECASE),
        re.compile(r"\b(?:voter\s+id|voterid|epic|e-epic|nvsp|eci|voters\.eci|blo|booth\s+level\s+officer|form\s+[678]|ngsp)\b", re.IGNORECASE),
    ),
    Domain.TAXATION: (
        re.compile(r"\b(?:income\s+tax|incometax|itr|itr-[1-7]|tax\s+return)\b", re.IGNORECASE),
        re.compile(r"\b(?:form\s+16|form\s+26as|ais|tis|assessment\s+year|ay\s+20\d\d)\b", re.IGNORECASE),
        re.compile(r"\b(?:143\(1\)|139\(9\)|139\(5\)|139\(4\)|section\s+139|section\s+119|119\(2\)\(b\)|234f)\b", re.IGNORECASE),
        re.compile(r"\b(?:section\s+147|section\s+148|section\s+148a|section\s+149|section\s+151|148a\(b\)|148a\(d\)|148a|148|147|149|151|reassessment|escaped\s+income|time-barred\s+assessment|(?:tax\s+)?reassessment\s+limitation|escaped\s+income\s+time\s+limit|reassessment\s+time\s+limit|tax\s+limitation)\b", re.IGNORECASE),
        re.compile(r"\b(?:206aa|section\s+206aa|234h|section\s+234h|inoperative\s+pan|rule\s+114aaa|circular\s+03/2023|circular\s+3/2023)\b", re.IGNORECASE),
        re.compile(r"\b(?:defective\s+return|prima\s+facie\s+adjustment|pfa|refund\s+unpaid|refund\s+reissue|bank\s+validation|pre-validation|challan\s+280|advance\s+tax|tds|tcs)\b", re.IGNORECASE),
        re.compile(r"\b(?:gst|gstn|gstr-3b|gstr-7|drc-01b|drc-01c|itc\s+mismatch|input\s+tax\s+credit)\b", re.IGNORECASE),
        re.compile(r"\b(?:eway\s+bill|e-way\s+bill|ewb|rule\s+138|ship\s+to\s+bill\s+to|transporter\s+id)\b", re.IGNORECASE),
        re.compile(r"\b(?:cbic|customs|baggage\s+rules|atithi|duty\s+free\s+allowance|customs\s+clearance|transfer\s+of\s+residence)\b", re.IGNORECASE),
    ),
    Domain.BANKING: (
        re.compile(r"\b(?:savings\s+account|current\s+account|bank\s+account|ifsc)\b", re.IGNORECASE),
        re.compile(r"\b(?:loan\s+agreement|emi|prepayment|foreclosure|housing\s+loan|personal\s+loan)\b", re.IGNORECASE),
        re.compile(r"\b(?:credit\s+card|debit\s+card|unsolicited\s+card|rbi|integrated\s+ombudsman|cms\.rbi|zero\s+liability|unauthorised\s+transaction)\b", re.IGNORECASE),
        re.compile(r"\b(?:cibil|experian|crif|credit\s+score|credit\s+report)\b", re.IGNORECASE),
        re.compile(r"\b(?:upi|atm\s+withdrawal|failed\s+upi|rbi\s+penalty|auto-debit|rtgs|neft|positive\s+pay)\b", re.IGNORECASE),
        re.compile(r"\b(?:udgam|unclaimed\s+deposit|unclaimed\s+dividend|unclaimed\s+shares|iepf|iepfa|iepf-5|form\s+iepf-5|mca|mca21|pension\s+sahayak|pfrda|apy|nps\s+grievance|dfs|department\s+of\s+financial\s+services)\b", re.IGNORECASE),
        re.compile(r"\b(?:dicgc|deposit\s+insurance|5\s+lakh|sebi|scores|scores\s+2\.0|smart\s+odr|two-tier\s+review)\b", re.IGNORECASE),
        re.compile(r"\b(?:ifsca|gift\s+city|ancillary\s+services|ship\s+leasing|fiu-ind|fiu|fingate|finnet|str|ctr|aml)\b", re.IGNORECASE),
        re.compile(r"\b(?:sidbi|msme\s+grievance|chief\s+grievance\s+officer|jansamarth|mudra|pmegp|standup\s+india)\b", re.IGNORECASE),
    ),
    Domain.AGRICULTURE: (
        re.compile(r"\b(?:pm\s*kisan|pmkisan|pm-kisan|kcc|kisan\s+credit\s+card)\b", re.IGNORECASE),
        re.compile(r"\b(?:farmer\s+subsidy|landholding|krishi|crop\s+insurance|pmfby)\b", re.IGNORECASE),
    ),
    Domain.LEGAL_CONSUMER: (
        re.compile(r"\b(?:police\s+fir|\bfir\b|police\s+complaint)\b", re.IGNORECASE),
        re.compile(r"\b(?:cybercrime|cyber\s+crime|1930|cybercrime\.gov\.in)\b", re.IGNORECASE),
        re.compile(r"\b(?:consumer\s+court|edaakhil|e-daakhil|district\s+commission|dcdrc|scdrc|ncdrc|consumer\s+handbook|consumer\s+helpline)\b", re.IGNORECASE),
        re.compile(r"\b(?:legal\s+notice|section\s+138|section\s+141|section\s+142|section\s+143a|cheque\s+bounce|cheque\s+dishonou?r|dishonou?r\s+of\s+cheque|negotiable\s+instruments|ni\s+act|demand\s+notice|return\s+memo|interim\s+compensation|nalsa|free\s+legal\s+aid|lok\s+adalat|legal\s+services\s+authority)\b", re.IGNORECASE),
    ),
    Domain.GENERAL_CIVIC: (
        re.compile(r"\b(?:epfo|epf|provident\s+fund|uan|joint\s+declaration|member\s+profile)\b", re.IGNORECASE),
        re.compile(r"\b(?:cpgrams|pgportal|darpg|public\s+grievance|appellate\s+authority)\b", re.IGNORECASE),
        re.compile(r"\b(?:nclt|certified\s+copy|sop\s+e-certified|efiling\.nclt)\b", re.IGNORECASE),
        re.compile(r"\b(?:ibbi|cirp|insolvency|resolution\s+professional|liquidation|form\s+[cd])\b", re.IGNORECASE),
        re.compile(r"\b(?:nfra|statutory\s+auditor|audit\s+file|audit\s+quality|accounting\s+fraud)\b", re.IGNORECASE),
    ),
}

# Mapping of curated entry IDs to their exact canonical domains
ENTRY_DOMAIN_MAP: dict[str, Domain] = {
    # Identity
    "pan_card_new": Domain.IDENTITY,
    "aadhaar_enrolment_basics": Domain.IDENTITY,
    "passport_application_new": Domain.IDENTITY,
    "aadhaar_pvc_payment_failed": Domain.IDENTITY,
    "passport_police_verification_delayed": Domain.IDENTITY,
    "voter_id_new_registration": Domain.IDENTITY,
    "digilocker_cbse_name_mismatch": Domain.IDENTITY,
    # Taxation
    "itr_filing_basics": Domain.TAXATION,
    "link_pan_aadhaar": Domain.TAXATION,
    "itr_bank_validation_failed": Domain.TAXATION,
    # Banking
    "loan_agreement_explainer": Domain.BANKING,
    "open_savings_account": Domain.BANKING,
    "rbi_failed_upi_atm_penalty": Domain.BANKING,
    # Transport
    "fastag_toll_dispute_refund": Domain.TRANSPORT,
    "parivahan_vahan_rc_correction": Domain.TRANSPORT,
    # Agriculture & Schemes
    "pm_kisan_scheme": Domain.AGRICULTURE,
    "pf_withdrawal_process": Domain.GENERAL_CIVIC,
    "epf_joint_declaration_correction": Domain.GENERAL_CIVIC,
    # Legal / Consumer
    "file_police_fir": Domain.LEGAL_CONSUMER,
    "consumer_court_complaint": Domain.LEGAL_CONSUMER,
}


def classify_domain(query: str | None, document_text: str | None = None) -> Domain:
    """Classify the user input into a specific civic domain before retrieval."""
    combined = f"{query or ''} {document_text or ''}".strip()
    if not combined:
        return Domain.UNKNOWN

    # Check uncovered domains FIRST before any other domain pattern matching
    # to prevent domain bleed into unrelated civic/banking/tax domains.
    # Guardrail: IEPF, UDGAM, DEA Fund, unclaimed shares, and unclaimed dividends are supported
    # under BANKING/CIVIC; do NOT let uncovered MCA SPICe+ patterns intercept them.
    is_unclaimed_or_investor = bool(
        re.search(
            r"\b(?:iepf|iepfa|unclaimed\s+(?:shares?|dividends?|deposits?)|unpaid\s+dividends?|iepf-?5[a-z]?|entitlement\s+letter|investor\s+education|udgam|dea\s+fund|deaf)\b",
            combined,
            re.IGNORECASE,
        )
    )

    for cat_name, category_patterns in _UNCOVERED_DOMAIN_PATTERNS.items():
        if cat_name == "mca_spice" and is_unclaimed_or_investor:
            continue
        for pat in category_patterns:
            if pat.search(combined):
                return Domain.UNCOVERED

    # Check domains in order of high specificity: Transport & Education before Identity/Tax/Banking
    for domain, patterns in _DOMAIN_PATTERNS.items():
        for pat in patterns:
            if pat.search(combined):
                return domain

    return Domain.UNKNOWN


def get_allowed_rag_categories(domain: Domain | str | None, query: str | None = None) -> set[str] | None:
    """Return the set of RAG corpus categories allowed for this domain to prevent cross-contamination."""
    if domain in (Domain.UNCOVERED, "uncovered"):
        return set()  # Strictly zero categories allowed for uncovered domains
    if domain == Domain.TRANSPORT:
        return {"civic"}  # Strictly eliminates "tax", "aadhaar", "pan", "banking"
    if domain == Domain.EDUCATION:
        return {"civic"}  # Strictly eliminates "tax", "aadhaar", "pan", "banking"
    if query:
        q_lower = query.lower()
        is_pan_tds = (
            any(w in q_lower for w in ("inoperative", "206aa", "234h", "114aaa", "circular 03/2023", "circular 3/2023", "excess 20%", "20% tds", "salary tds"))
            and any(w in q_lower for w in ("pan", "aadhaar", "aadhar", "linking"))
        ) or ("inoperative pan" in q_lower) or ("206aa" in q_lower)
        if is_pan_tds and domain in (Domain.TAXATION, "tax", "taxation", Domain.IDENTITY, "identity"):
            return {"tax", "pan", "civic"}
    if domain == Domain.TAXATION:
        return {"tax", "civic"}  # Allows official tax and civic guidance
    if domain == Domain.IDENTITY:
        return {"aadhaar", "pan", "civic"}  # Allows identity and civil registries
    if domain == Domain.BANKING:
        return {"banking", "civic"}  # Allows banking, monetary, market and financial civic
    if domain in (Domain.LEGAL_CONSUMER, Domain.GENERAL_CIVIC, Domain.AGRICULTURE):
        return {"civic", "banking"}  # Allows legal, civic and scheme datasets
    return None  # Unfiltered for unknown queries


def entry_matches_domain(entry_id: str, entry_category: str | None, query_domain: Domain | str | None) -> bool:
    """Validate whether a knowledge base entry belongs to the query's domain."""
    if query_domain in (Domain.UNCOVERED, "uncovered"):
        return False
    if query_domain in (Domain.UNKNOWN, None, "unknown"):
        return True

    entry_domain = ENTRY_DOMAIN_MAP.get(entry_id)
    if entry_domain is None:
        cat = (entry_category or "").lower()
        if cat == "tax":
            entry_domain = Domain.TAXATION
        elif cat == "banking":
            entry_domain = Domain.BANKING
        elif cat == "legal":
            entry_domain = Domain.LEGAL_CONSUMER
        elif cat == "scheme":
            entry_domain = Domain.AGRICULTURE
        else:
            entry_domain = Domain.GENERAL_CIVIC

    # Transport queries must ONLY match transport entries
    if query_domain == Domain.TRANSPORT:
        return entry_domain == Domain.TRANSPORT

    # Education queries must ONLY match education or identity entries (e.g. DigiLocker)
    if query_domain == Domain.EDUCATION:
        return entry_domain in (Domain.EDUCATION, Domain.IDENTITY)

    # Taxation queries must ONLY match taxation entries
    if query_domain == Domain.TAXATION:
        return entry_domain == Domain.TAXATION

    # Banking queries must ONLY match banking entries
    if query_domain == Domain.BANKING:
        return entry_domain == Domain.BANKING

    # Agriculture queries must ONLY match agriculture entries
    if query_domain == Domain.AGRICULTURE:
        return entry_domain == Domain.AGRICULTURE

    # Legal queries must ONLY match legal entries
    if query_domain == Domain.LEGAL_CONSUMER:
        return entry_domain == Domain.LEGAL_CONSUMER

    return True


__all__ = [
    "Domain",
    "classify_domain",
    "get_allowed_rag_categories",
    "entry_matches_domain",
    "ENTRY_DOMAIN_MAP",
    "_UNCOVERED_DOMAIN_PATTERNS",
    "QueryModality",
    "classify_query_modality",
]

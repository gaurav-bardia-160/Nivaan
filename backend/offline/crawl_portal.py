"""Production-grade official government portal crawler and ingestion pipeline.

This pipeline performs safe, authoritative ingestion of targeted government portals:
1. Validates TLS, public DNS, and approved host constraints using native OS trust store (truststore).
2. Employs headless Chrome (Playwright) or secure requests to overcome Akamai WAF / SPA client-side rendering.
3. Extracts raw HTML/PDF documents with cryptographic provenance into backend/data/raw/official_sources/<site_id>/<sha256>/.
4. Cleans boilerplate, navigations, scripts, footers, and challenge markers while preserving form instructions and interactive tabs.
5. Employs SimHash Hamming deduplication and produces schema-compliant ChunkRecords.
6. Writes refined JSONL files into backend/data/refined/official_sources/<site_id>/.
7. Atomically registers new datasets into backend/data/rag_manifest.json.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import os
import re
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from urllib.parse import urljoin, urlsplit

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from playwright.async_api import async_playwright

from backend.config import DATA_DIR
from backend.rag.loader import DEFAULT_MANIFEST, load_corpus
from backend.rag.models import ChunkRecord, CorpusManifest, DatasetSpec
from backend.offline.ingest_official_source import (
    RAW_ROOT,
    REFINED_ROOT,
    DEFAULT_CHUNK_WORDS,
    DEFAULT_OVERLAP_WORDS,
    _atomic_write,
    _clean_lines,
    _existing_fingerprints,
    _normalize_text,
    _safe_id,
    _simhash,
    _validate_https_url,
    _validate_public_dns,
    build_records,
    extract_text,
    FetchResult,
    IngestionError,
)

MIN_CHUNK_WORDS = 25

PORTAL_SPECS = {
    # 1. Previously ingested portals (kept for reference / idempotent re-runs)
    "iepf": {
        "site_id": "iepf_portal",
        "title_prefix": "IEPF Official: ",
        "source_authority": "Investor Education and Protection Fund Authority (IEPFA), Ministry of Corporate Affairs, Government of India",
        "allowed_hosts": ["www.iepf.gov.in", "iepf.gov.in", "mca.gov.in", "www.mca.gov.in"],
        "category": "civic",
        "jurisdiction": "IN",
        "scheme": "Investor Education and Protection Fund (IEPF)",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["iepf", "iepfa", "unclaimed shares", "unclaimed dividend", "form iepf-5", "refund claim", "corporate seva kendra", "investor education"],
        "use_browser": False,
        "seed_urls": [
            "https://www.iepf.gov.in/content/iepf/global/master/Home/Home.html",
            "https://www.iepf.gov.in/content/iepf/global/master/Home/HelpAndFAQs/faqs-for-claimants-v3/iepf-5.html",
            "https://www.iepf.gov.in/content/iepf/global/master/Home/HelpAndFAQs/faqs-for-company-v3/iepf-5-evr.html",
            "https://www.iepf.gov.in/content/dam/iepf/faqs/IEPF-FAQs-20260421.pdf",
            "https://www.iepf.gov.in/content/iepf/global/master/Home/AboutUS/about-us/IEPFLegislation.html",
            "https://www.iepf.gov.in/content/iepf/global/master/Home/AboutUS/about-us/AboutIEPFA.html",
            "https://www.iepf.gov.in/content/iepf/global/master/Home/Services/CorporateSevaKendra.html",
            "https://www.iepf.gov.in/content/dam/iepf/pdf/IEPFBrochure_09042018.pdf",
            "https://www.iepf.gov.in/content/iepf/global/master/Home/HelpAndFAQs/instruction-kit-for-offline-payment-process.html",
        ],
    },
    "mca": {
        "site_id": "mca_portal",
        "title_prefix": "MCA Official: ",
        "source_authority": "Ministry of Corporate Affairs, Government of India",
        "allowed_hosts": ["www.mca.gov.in", "mca.gov.in"],
        "category": "civic",
        "jurisdiction": "IN",
        "scheme": "MCA Services & Corporate Portal",
        "document_type": "official_portal_guidance",
        "tags": ["mca", "mca21", "iepf-5 tracking", "srn status", "cin", "investor services", "company filings"],
        "use_browser": False,
        "seed_urls": [
            "https://www.mca.gov.in/content/mca/global/en/mca/iepf-related-services/search-unclaimed-unpaid-amount-shares.html",
            "https://www.mca.gov.in/content/mca/global/en/mca/iepf-related-services/IEPF-5.html",
            "https://www.mca.gov.in/content/mca/global/en/home.html",
            "https://www.mca.gov.in/content/mca/global/en/contact-us/grievance-cell.html",
        ],
    },
    "udgam": {
        "site_id": "udgam_portal",
        "title_prefix": "UDGAM Portal: ",
        "source_authority": "Reserve Bank of India (RBI) & ReBIT",
        "allowed_hosts": ["udgam.rbi.org.in", "www.rbi.org.in", "rbi.org.in"],
        "category": "civic",
        "jurisdiction": "IN",
        "scheme": "UDGAM - Unclaimed Deposits Gateway to Access Information",
        "document_type": "official_portal_guidance",
        "tags": ["udgam", "rbi", "unclaimed deposits", "dormant accounts", "bank search", "inoperative accounts", "dea fund", "deaf"],
        "use_browser": False,
        "seed_urls": [
            "https://www.rbi.org.in/Scripts/FAQView.aspx?Id=140",
            "https://www.rbi.org.in/scripts/FS_Notification.aspx?Id=8900&fn=2&Mode=0",
            "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=56223",
            "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=56490",
            "https://udgam.rbi.org.in/",
        ],
    },
    "pension_sahayak": {
        "site_id": "pension_sahayak_portal",
        "title_prefix": "Pension Sahayak: ",
        "source_authority": "Pension Fund Regulatory and Development Authority (PFRDA), Government of India",
        "allowed_hosts": ["pensionsahayak.pfrda.org.in", "www.pfrda.org.in", "pfrda.org.in"],
        "category": "civic",
        "jurisdiction": "IN",
        "scheme": "Pension Sahayak - PFRDA Grievance Redressal",
        "document_type": "official_portal_guidance",
        "tags": ["pension sahayak", "pfrda", "nps grievance", "apy grievance", "pran", "token tracking", "pension redressal"],
        "use_browser": True,
        "seed_urls": [
            "https://pensionsahayak.pfrda.org.in/",
        ],
        "sub_tabs": [
            "About Us",
            "Our Process",
            "FAQ's",
            "Grievance Policy",
            "Ombudsman",
        ],
    },
    "dfs": {
        "site_id": "dfs_portal",
        "title_prefix": "DFS Official: ",
        "source_authority": "Department of Financial Services, Ministry of Finance, Government of India",
        "allowed_hosts": ["financialservices.gov.in", "www.financialservices.gov.in"],
        "category": "civic",
        "jurisdiction": "IN",
        "scheme": "Department of Financial Services Financial Redressal & Notices",
        "document_type": "official_portal_guidance",
        "tags": ["dfs", "financial services", "ministry of finance", "grievance redressal", "orders and notices", "gazettes", "financial policies"],
        "use_browser": False,
        "seed_urls": [
            "https://financialservices.gov.in/",
            "https://financialservices.gov.in/grievance-redressal",
            "https://financialservices.gov.in/orders-and-notices",
            "https://financialservices.gov.in/gazettes-notification",
            "https://financialservices.gov.in/acts",
        ],
    },

    # 2. Civil Identity & Electoral Registries
    "uidai": {
        "site_id": "uidai_portal",
        "title_prefix": "UIDAI Aadhaar Official: ",
        "source_authority": "Unique Identification Authority of India (UIDAI), Ministry of Electronics and IT, Government of India",
        "allowed_hosts": ["uidai.gov.in", "www.uidai.gov.in"],
        "category": "civic",
        "jurisdiction": "IN",
        "scheme": "Aadhaar - Civil Identity & Demographic Services",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["aadhaar", "uidai", "biometric unlock", "error 330", "dob update", "name change exception", "gazette notification", "mandatory biometric update", "myaadhaar"],
        "use_browser": False,
        "seed_urls": [
            "https://uidai.gov.in/images/LR_Aadhaar_Handbook_2026.pdf",
            "https://uidai.gov.in/images/SOP_28.10.2021-Name_And_Gender_UpdateRequest_under_Exception_Handling_Process.pdf",
            "https://uidai.gov.in/images/SOP_for_DOB_update.pdf",
            "https://uidai.gov.in/images/Citizen_Charter_Jan_24.pdf",
        ],
    },
    "eci": {
        "site_id": "eci_portal",
        "title_prefix": "ECI Voters Official: ",
        "source_authority": "Election Commission of India (ECI)",
        "allowed_hosts": ["voters.eci.gov.in", "eci.gov.in", "www.eci.gov.in"],
        "category": "civic",
        "jurisdiction": "IN",
        "scheme": "Voters' Services & Electoral Registration",
        "document_type": "official_portal_guidance",
        "tags": ["eci", "epic", "voter id", "form 8", "form 6", "address shift", "blo verification", "ngsp", "e-epic download"],
        "use_browser": True,
        "seed_urls": [
            "https://voters.eci.gov.in/home/ngsp",
            "https://voters.eci.gov.in/HomePageFaq",
            "https://voters.eci.gov.in/",
        ],
    },

    # 3. Direct Taxation & Corporate PAN
    "incometax": {
        "site_id": "incometax_portal",
        "title_prefix": "Income Tax Department: ",
        "source_authority": "Central Board of Direct Taxes (CBDT), Directorate of Systems, Income Tax Department, Government of India",
        "allowed_hosts": ["www.incometax.gov.in", "incometax.gov.in"],
        "category": "tax",
        "jurisdiction": "IN",
        "scheme": "Direct Taxes & e-Filing Portal Services",
        "document_type": "official_portal_guidance",
        "tags": ["income tax", "cbdt", "cpc", "prima facie adjustment", "defective notice 139(9)", "my bank account validation", "evc pre-validation", "refund reissue", "service request"],
        "use_browser": False,
        "seed_urls": [
            "https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/prima%20facie%20adjustment",
            "https://www.incometax.gov.in/iec/foportal/help/my-bank-account",
            "https://www.incometax.gov.in/iec/foportal/help/how-to-raise-e-filing-service-requests?mobile-app=1",
            "https://www.incometax.gov.in/iec/foportal/help/how-to-use-my-e-filing-profile",
            "https://www.incometax.gov.in/iec/foportal/help/how-to-e-verify-your-e-filing-return",
            "https://www.incometax.gov.in/iec/foportal/help/refund_status_user_manual",
            "https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/refund-reissue?mobile-app=1",
        ],
    },
    "tin_protean": {
        "site_id": "tin_protean_portal",
        "title_prefix": "Protean TIN PAN: ",
        "source_authority": "Protean eGov Technologies Limited / Income Tax Department",
        "allowed_hosts": ["tinpan.proteantech.in", "www.protean-tinpan.com", "tin.tin.nsdl.com"],
        "category": "tax",
        "jurisdiction": "IN",
        "scheme": "Permanent Account Number (PAN) Issuance & Corrections",
        "document_type": "official_portal_guidance",
        "tags": ["pan", "tin", "protean", "form 49a", "form 49aa", "pan correction csf", "dsc signature", "ao code"],
        "use_browser": False,
        "seed_urls": [
            "https://tinpan.proteantech.in/faqs/pan/faq-pan-procedure.html",
        ],
    },
    "utiitsl_pan": {
        "site_id": "utiitsl_pan_portal",
        "title_prefix": "UTIITSL PAN Official: ",
        "source_authority": "UTI Infrastructure Technology And Services Limited (UTIITSL)",
        "allowed_hosts": ["www.pan.utiitsl.com", "pan.utiitsl.com", "www.utiitsl.com"],
        "category": "tax",
        "jurisdiction": "IN",
        "scheme": "UTIITSL PAN Application & Correction Services",
        "document_type": "official_portal_guidance",
        "tags": ["utiitsl", "pan card", "form 49a", "csf correction", "pan landing", "physical pan", "e-pan"],
        "use_browser": True,
        "seed_urls": [
            "https://www.pan.utiitsl.com/panonline_website/redirect/formLanding",
            "https://www.pan.utiitsl.com/panonline_website/redirectCsf/formLanding",
        ],
    },

    # 4. Indirect Taxation, Invoicing Networks & Border Clearance
    "gstn": {
        "site_id": "gstn_portal",
        "title_prefix": "GSTN Official: ",
        "source_authority": "Goods and Services Tax Network (GSTN), Ministry of Finance, Government of India",
        "allowed_hosts": ["tutorial.gst.gov.in", "www.gst.gov.in", "gst.gov.in"],
        "category": "tax",
        "jurisdiction": "IN",
        "scheme": "GST Compliance & Return Filings (DRC-01B, DRC-01C, GSTR-3B, GSTR-7)",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["gst", "gstn", "drc-01b", "drc-01c", "itc mismatch", "gstr-3b", "gstr-7", "taxpayer dashboard", "return compliance"],
        "use_browser": False,
        "seed_urls": [
            "https://tutorial.gst.gov.in/userguide/returns/FAQs_Return_Compliance_ITC.htm",
            "https://tutorial.gst.gov.in/userguide/taxpayersdashboard/index.htm",
            "https://tutorial.gst.gov.in/userguide/returns/FAQs_Return_Compliance.htm",
            "https://tutorial.gst.gov.in/userguide/returns/Manual_Return_Compliance.htm",
            "https://tutorial.gst.gov.in/userguide/returns/Manual_Return_Compliance_ITC.htm",
            "https://tutorial.gst.gov.in/downloads/news/return_compliance_itc_mismatch_intimation_in_form_gst_drc_01c.pdf",
            "https://tutorial.gst.gov.in/downloads/gstr3bofflineutility.pdf",
            "https://tutorial.gst.gov.in/downloads/gstr7offlineutility.pdf",
        ],
    },
    "ewaybill": {
        "site_id": "ewaybill_portal",
        "title_prefix": "E-Way Bill System: ",
        "source_authority": "Goods and Services Tax Network (GSTN) & National Informatics Centre (NIC)",
        "allowed_hosts": ["docs.ewaybillgst.gov.in", "ewaybillgst.gov.in"],
        "category": "tax",
        "jurisdiction": "IN",
        "scheme": "Electronic Way Bill (E-Way Bill) Logistics & Transport Compliance",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["e-way bill", "ewaybill", "rule 138", "ship to bill to", "ewb blocking", "vehicle update", "transporter id", "rfid"],
        "use_browser": False,
        "seed_urls": [
            "https://docs.ewaybillgst.gov.in/html/faq_new.html",
            "https://docs.ewaybillgst.gov.in/apidocs/downloads/faqs_on_ship_to_field.pdf",
            "https://docs.ewaybillgst.gov.in/documents/EWBRules.pdf",
            "https://docs.ewaybillgst.gov.in/html/faq.html",
            "https://docs.ewaybillgst.gov.in/Documents/faq_block_latest.pdf",
        ],
    },
    "cbic": {
        "site_id": "cbic_portal",
        "title_prefix": "CBIC Customs Official: ",
        "source_authority": "Central Board of Indirect Taxes and Customs (CBIC), Department of Revenue, Ministry of Finance",
        "allowed_hosts": ["www.cbic.gov.in", "cbic.gov.in", "taxinformation.cbic.gov.in", "atithi.cbic.gov.in"],
        "category": "tax",
        "jurisdiction": "IN",
        "scheme": "Customs Passenger Clearance, Baggage Rules & International Declarations",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["cbic", "customs", "baggage rules 2016", "atithi app", "duty free allowance", "green channel", "red channel", "currency declaration", "transfer of residence"],
        "use_browser": False,
        "seed_urls": [
            "https://www.cbic.gov.in/resources/htdocs-cbec/frequently_asked_questions_faqs.pdf",
            "https://www.cbic.gov.in/resources/htdocs-cbec/travellerguide_atithi.pdf",
            "https://www.cbic.gov.in/resources/htdocs-cbec/customs_clearance_of_passengers_at_a_glance.pdf",
            "https://taxinformation.cbic.gov.in/content/html/tax_repository/customs/rules/baggage_rules_2016/documents/baggage_rules__2016_01_march_2016.html",
            "https://atithi.cbic.gov.in/",
        ],
    },

    # 5. Banking, Monetary Transmission & Deposit Insurance
    "rbi": {
        "site_id": "rbi_portal",
        "title_prefix": "RBI Master Directions: ",
        "source_authority": "Reserve Bank of India (RBI)",
        "allowed_hosts": ["www.rbi.org.in", "rbi.org.in", "m.rbi.org.in"],
        "category": "banking",
        "jurisdiction": "IN",
        "scheme": "RBI Master Directions, Customer Protection & Ombudsman Schemes",
        "document_type": "official_master_directions_and_faqs",
        "tags": ["rbi", "zero liability", "customer protection", "unauthorised electronic transactions", "rtgs", "neft", "integrated ombudsman scheme", "cheque bounce", "positive pay"],
        "use_browser": False,
        "seed_urls": [
            "https://www.rbi.org.in/commonman/Upload/English/Notification/PDFs/DBC070514DF.pdf",
            "https://www.rbi.org.in/commonman/Upload/English/FAQs/PDFs/FAQRTGS15102026.pdf",
            "https://www.rbi.org.in/commonman/Upload/English/FAQs/PDFs/RBIOS01072026.pdf",
            "https://www.rbi.org.in/commonman/Upload/English/FAQs/PDFs/CHEQUE07012026.pdf",
            "https://m.rbi.org.in/scripts/BS_ViewMasDirections.aspx?id=12300",
            "https://rbi.org.in/commonman/Upload/English/Notification/PDFs/21ODR602F0A579EB246AA885776A76122DB0C.PDF",
        ],
    },
    "dicgc": {
        "site_id": "dicgc_portal",
        "title_prefix": "DICGC Official: ",
        "source_authority": "Deposit Insurance and Credit Guarantee Corporation (DICGC), Reserve Bank of India",
        "allowed_hosts": ["www.dicgc.org.in", "dicgc.org.in"],
        "category": "banking",
        "jurisdiction": "IN",
        "scheme": "Deposit Insurance Scheme (Rs 5 Lakh Protection)",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["dicgc", "deposit insurance", "5 lakh insurance", "bank liquidation", "moratorium", "insured banks", "claim settlement"],
        "use_browser": False,
        "seed_urls": [
            "https://www.dicgc.org.in/FAQs",
            "https://www.dicgc.org.in/guide-to-deposit-insurance",
        ],
    },

    # 6. Securities, Market Infrastructures & IFSCA
    "sebi": {
        "site_id": "sebi_portal",
        "title_prefix": "SEBI Official: ",
        "source_authority": "Securities and Exchange Board of India (SEBI)",
        "allowed_hosts": ["scores.sebi.gov.in", "www.sebi.gov.in", "sebi.gov.in", "investor.sebi.gov.in", "www.cse-india.com"],
        "category": "banking",
        "jurisdiction": "IN",
        "scheme": "SCORES 2.0 & SMART ODR Securities Dispute Resolution",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["sebi", "scores 2.0", "smart odr", "investor grievance", "two-tier review", "designated body", "reit invit", "mutual funds"],
        "use_browser": False,
        "seed_urls": [
            "https://scores.sebi.gov.in/documents/d/guest/scores-2-0-faqs?download=true",
            "https://investor.sebi.gov.in/pdf/reference-material/languages/english/Securities%20Market%20Booklet.pdf",
            "https://www.sebi.gov.in/sebi_data/attachdocs/oct-2026/1792054744851.pdf",
        ],
    },
    "ifsca": {
        "site_id": "ifsca_portal",
        "title_prefix": "IFSCA Official: ",
        "source_authority": "International Financial Services Centres Authority (IFSCA), GIFT City",
        "allowed_hosts": ["ifsca.gov.in", "www.ifsca.gov.in"],
        "category": "banking",
        "jurisdiction": "IN",
        "scheme": "GIFT City Ancillary Services & Ship Leasing Regulations",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["ifsca", "gift city", "ancillary services", "ship leasing", "financial services centre", "fee circular"],
        "use_browser": False,
        "seed_urls": [
            "https://ifsca.gov.in/Document/Markets/FAQ_Ancillary_Services.pdf",
            "https://ifsca.gov.in/CommonDirect/DownloadFile?id=d09c93fc98191af1801a5914f315cd7a&fileName=ship-leasing-faq-23-07-22423072024054256.pdf",
        ],
    },

    # 7. Corporate Governance, Insolvency & AML
    "nclt": {
        "site_id": "nclt_portal",
        "title_prefix": "NCLT Official: ",
        "source_authority": "National Company Law Tribunal (NCLT), Ministry of Corporate Affairs, Government of India",
        "allowed_hosts": ["nclt.gov.in", "www.nclt.gov.in", "efiling.nclt.gov.in"],
        "category": "civic",
        "jurisdiction": "IN",
        "scheme": "NCLT e-Filing & Certified Copy Standard Operating Procedures",
        "document_type": "official_portal_guidance",
        "tags": ["nclt", "certified copy", "sop e-certified copy", "efiling", "nclt portal", "bench orders"],
        "use_browser": False,
        "seed_urls": [
            "https://nclt.gov.in/sop-e-certified-copy",
            "https://efiling.nclt.gov.in/downloads/userManualCertifiedCopy.pdf",
        ],
    },
    "ibbi": {
        "site_id": "ibbi_portal",
        "title_prefix": "IBBI Official: ",
        "source_authority": "Insolvency and Bankruptcy Board of India (IBBI)",
        "allowed_hosts": ["ibbi.gov.in", "www.ibbi.gov.in"],
        "category": "civic",
        "jurisdiction": "IN",
        "scheme": "Corporate Insolvency Resolution Process (CIRP) Claim Protocols",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["ibbi", "cirp", "insolvency", "creditors", "form c", "form d", "resolution professional", "liquidation"],
        "use_browser": False,
        "seed_urls": [
            "https://ibbi.gov.in/uploads/claims/ff4f782de00cd9e74d85b6140256046a.pdf",
            "https://ibbi.gov.in/uploads/claims/2025-08-20-180655-qmngk-95b42f8b760f6cc8dc1fe1d79af57bad.pdf",
        ],
    },
    "nfra": {
        "site_id": "nfra_portal",
        "title_prefix": "NFRA Official: ",
        "source_authority": "National Financial Reporting Authority (NFRA), Ministry of Corporate Affairs",
        "allowed_hosts": ["nfra.gov.in", "www.nfra.gov.in"],
        "category": "civic",
        "jurisdiction": "IN",
        "scheme": "Audit Oversight & NFRA Complaint Redressal Framework",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["nfra", "auditors", "audit oversight", "complaint handling", "statutory auditor", "accounting fraud"],
        "use_browser": False,
        "seed_urls": [
            "https://nfra.gov.in/complaints/",
            "https://nfra.gov.in/project/nfra-com/",
            "https://nfra.gov.in/nfra-circular-on-effective-communication-between-statutory-auditors-and-those-charged-with-governance-including-audit-committees/",
        ],
    },
    "fiu_ind": {
        "site_id": "fiu_ind_portal",
        "title_prefix": "FIU-IND Official: ",
        "source_authority": "Financial Intelligence Unit - India (FIU-IND), Department of Revenue, Ministry of Finance",
        "allowed_hosts": ["fiuindia.gov.in", "www.fiuindia.gov.in"],
        "category": "banking",
        "jurisdiction": "IN",
        "scheme": "Anti-Money Laundering & FINnet 2.0 / FINGate Reporting Portal",
        "document_type": "official_portal_guidance",
        "tags": ["fiu-ind", "fingate", "finnet 2.0", "pmla", "str", "ctr", "aml reporting", "reporting entity"],
        "use_browser": False,
        "seed_urls": [
            "https://fiuindia.gov.in/files/FAQs/faqs.html",
            "https://fiuindia.gov.in/pdfs/quicklinks/User_Manual_FINGate2.0.pdf",
            "https://fiuindia.gov.in/pdfs/quicklinks/User_Manual_Reports_FINGate_Portal.pdf",
        ],
    },

    # 8. Social Security, Labor & Pension
    "epfo": {
        "site_id": "epfo_portal",
        "title_prefix": "EPFO Official: ",
        "source_authority": "Employees' Provident Fund Organisation (EPFO), Ministry of Labour and Employment, Government of India",
        "allowed_hosts": ["pmvbry-cdn.epfindia.gov.in", "epfindia.gov.in", "www.epfindia.gov.in"],
        "category": "civic",
        "jurisdiction": "IN",
        "scheme": "EPFO Joint Declarations, Member Profile & UAN Corrections",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["epfo", "provident fund", "uan", "joint declaration sop", "member profile correction", "father name correction", "date of joining"],
        "use_browser": False,
        "seed_urls": [
            "https://pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2025/09/SOP_JointDeclarations_29082023-7.pdf",
            "https://pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2025/09/SimplificationOfJointDeclarationProcess_WSUCircular-10.pdf",
        ],
    },
    "pfrda_ombudsman": {
        "site_id": "pfrda_ombudsman_portal",
        "title_prefix": "PFRDA Ombudsman & Grievance: ",
        "source_authority": "Pension Fund Regulatory and Development Authority (PFRDA), Government of India",
        "allowed_hosts": ["pfrda.org.in", "www.pfrda.org.in"],
        "category": "civic",
        "jurisdiction": "IN",
        "scheme": "PFRDA Ombudsman for NPS and APY Grievance Redressal",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["pfrda", "ombudsman", "nps", "apy", "pran", "grievance escalation", "pension redressal"],
        "use_browser": False,
        "seed_urls": [
            "https://www.pfrda.org.in/compliance/grievance",
            "https://www.pfrda.org.in/faqs",
            "https://www.pfrda.org.in/w/pfrda-launches-ai-powered-pfrda-pension-sahayak-portal-to-transform-pension-grievance-redressal-1",
        ],
    },

    # 9. Consumer Protection, Legal Aid & Small Enterprise Credit
    "cpgrams": {
        "site_id": "cpgrams_portal",
        "title_prefix": "CPGRAMS Official: ",
        "source_authority": "Department of Administrative Reforms and Public Grievances (DARPG), Government of India",
        "allowed_hosts": ["pgportal.gov.in", "www.pgportal.gov.in"],
        "category": "civic",
        "jurisdiction": "IN",
        "scheme": "CPGRAMS Public Grievance Resolution & Appeal Mechanism",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["cpgrams", "pgportal", "darpg", "public grievance", "appeal", "appellate authority", "citizen charter"],
        "use_browser": False,
        "seed_urls": [
            "https://pgportal.gov.in/Home/Faq",
        ],
    },
    "edaakhil": {
        "site_id": "edaakhil_portal",
        "title_prefix": "e-Daakhil Consumer Protection: ",
        "source_authority": "Department of Consumer Affairs, National Consumer Disputes Redressal Commission (NCDRC)",
        "allowed_hosts": ["consumerhelpline.gov.in", "www.consumerhelpline.gov.in", "edaakhil.nic.in"],
        "category": "civic",
        "jurisdiction": "IN",
        "scheme": "National Consumer Helpline & e-Daakhil Online Consumer Complaints",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["edaakhil", "consumer helpline", "ncdrc", "consumer protection act 2019", "pecuniary jurisdiction", "district commission", "state commission"],
        "use_browser": False,
        "seed_urls": [
            "https://consumerhelpline.gov.in/public/assets/docs/consumerhandbooks/Consumer_Handbook.pdf",
        ],
    },
    "nalsa": {
        "site_id": "nalsa_portal",
        "title_prefix": "NALSA Official: ",
        "source_authority": "National Legal Services Authority (NALSA), Ministry of Law and Justice, Government of India",
        "allowed_hosts": ["nalsa.gov.in", "www.nalsa.gov.in", "sikkim.nalsa.gov.in"],
        "category": "civic",
        "jurisdiction": "IN",
        "scheme": "Free Legal Aid, Lok Adalat & Legal Services Clinics",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["nalsa", "legal aid", "section 12", "lok adalat", "free legal services", "legal services authority act 1987"],
        "use_browser": False,
        "seed_urls": [
            "https://nalsa.gov.in/faqs/",
            "https://nalsa.gov.in/about-nalsa/",
        ],
    },
    "sidbi": {
        "site_id": "sidbi_portal",
        "title_prefix": "SIDBI Official: ",
        "source_authority": "Small Industries Development Bank of India (SIDBI)",
        "allowed_hosts": ["www.sidbi.in", "sidbi.in"],
        "category": "banking",
        "jurisdiction": "IN",
        "scheme": "MSME Customer Grievance Redressal Policy & Credit Facilitation",
        "document_type": "official_guidelines_and_faqs",
        "tags": ["sidbi", "msme grievance", "chief grievance officer", "credit delivery", "turnaround time", "escalation matrix"],
        "use_browser": False,
        "seed_urls": [
            "https://www.sidbi.in/uploads/publicationreport/Customer-Grievance-Redressal-Policy.pdf",
            "https://www.sidbi.in/chief-grievance-officer",
            "https://www.sidbi.in/complaints",
        ],
    },
    "jansamarth": {
        "site_id": "jansamarth_portal",
        "title_prefix": "JanSamarth Portal: ",
        "source_authority": "Ministry of Finance, Government of India",
        "allowed_hosts": ["www.jansamarth.in", "jansamarth.in"],
        "category": "banking",
        "jurisdiction": "IN",
        "scheme": "JanSamarth Centralized Credit-Linked Government Schemes Portal",
        "document_type": "official_portal_guidance",
        "tags": ["jansamarth", "mudra", "pmegp", "standup india", "credit linked subsidy", "digital approval in principle", "loan eligibility"],
        "use_browser": True,
        "seed_urls": [
            "https://www.jansamarth.in/faq",
            "https://www.jansamarth.in/grievances",
            "https://www.jansamarth.in/TermsAndConditions",
        ],
    },
}


def extract_portal_text(result: FetchResult) -> tuple[str, str, str]:
    """Extract and refine text from HTML or PDF preserving procedural guidance and forms."""
    is_pdf = result.content_type == "application/pdf" or result.body.startswith(b"%PDF")
    if is_pdf:
        try:
            reader = PdfReader(io.BytesIO(result.body), strict=False)
            pages = []
            for i, page in enumerate(reader.pages):
                txt = page.extract_text() or ""
                if txt.strip():
                    pages.append(txt)
                if i >= 60:  # Cap at 60 pages for massive compendiums to retain high-density procedural guidance
                    break
        except Exception as exc:
            raise IngestionError(f"pdf_extraction_failed:{type(exc).__name__}") from exc

        text = _clean_lines("\n".join(pages).splitlines())
        text = text.replace("\x00", " ")
        title = ""
        if reader.metadata and reader.metadata.title:
            title = " ".join(str(reader.metadata.title).split())
        title = title.replace("\x00", "").strip()

        stem = Path(urlsplit(result.final_url).path).stem.replace("_", " ").replace("-", " ")
        if not title or len(title) < 4 or title.lower().endswith(".pdf") or "untitled" in title.lower():
            title = stem.title()

        lowered_stem = stem.lower()
        if "iepf-5-evr" in result.final_url.lower() or "iepf 5 evr" in lowered_stem:
            title = "Form IEPF-5 E-Verification Report Instruction Kit for Companies"
        elif "iepf-5" in result.final_url.lower() or "iepf 5" in lowered_stem:
            title = "Form IEPF-5 Instruction Kit for Claimants (Unclaimed Amounts and Shares)"
        elif "iepf-faqs" in result.final_url.lower() or "iepf faqs" in lowered_stem:
            title = "IEPF Authority FAQs on Claim Processing, Resubmissions and Queue"
        elif "faqview" in lowered_stem and "140" in result.final_url:
            title = "RBI FAQs on Unclaimed Deposits, Inoperative Accounts and DEA Fund Interest Calculation"
        elif "fs_notification" in lowered_stem and "8900" in result.final_url:
            title = "RBI Depositor Education and Awareness (DEA) Fund Scheme 2014"

        return title or "Official document", text, ".pdf"

    if result.content_type and result.content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
        raise IngestionError(f"unsupported_content_type:{result.content_type}")

    try:
        decoded = result.body.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = result.body.decode("latin-1", errors="replace")

    soup = BeautifulSoup(decoded, "html.parser")
    title = " ".join((soup.title.get_text(" ", strip=True) if soup.title else "").split())

    # Decompose script, style, svg, canvas, template, etc. Preserving forms and buttons for interactive portal directions.
    for node in soup.find_all({"script", "style", "noscript", "svg", "canvas", "template"}):
        node.decompose()

    # Extract clean text from all content tags
    content_tags = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "th", "td", "label", "button", "div", "span"]
    raw_lines = []
    for elem in soup.find_all(content_tags):
        t = " ".join(elem.get_text(" ", strip=True).split())
        if t and len(t) > 2:
            raw_lines.append(t)

    text = _clean_lines(raw_lines)
    text = text.replace("\x00", " ")
    return title or "Official Portal Document", text, ".html"


async def fetch_page_with_browser(
    url: str,
    allowed_hosts: set[str],
    timeout_ms: int = 30000,
) -> FetchResult:
    """Fetch a web page using headless Chrome with anti-automation suppression."""
    host = _validate_https_url(url, allowed_hosts)
    _validate_public_dns(host, socket.getaddrinfo)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            locale="en-US",
        )
        page = await context.new_page()
        try:
            resp = await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        except Exception:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

        await page.wait_for_timeout(2000)

        html = await page.content()
        final_url = page.url
        status = resp.status if resp else 200
        await browser.close()

    if status >= 400 and status != 403:
        raise IngestionError(f"browser_fetch_http_error:{status}:{url}")

    raw_bytes = html.encode("utf-8")
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return FetchResult(
        requested_url=url,
        final_url=final_url,
        content_type="text/html",
        body=raw_bytes,
        fetched_at=fetched_at,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )


async def fetch_pension_sahayak_tabs(
    base_url: str,
    allowed_hosts: set[str],
    tabs: list[str],
) -> list[tuple[str, FetchResult]]:
    """Fetch all interactive tabs on Pension Sahayak using single session browser automation."""
    host = _validate_https_url(base_url, allowed_hosts)
    _validate_public_dns(host, socket.getaddrinfo)

    results: list[tuple[str, FetchResult]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = await browser.new_page()
        await page.goto(base_url, wait_until="networkidle", timeout=25000)
        await page.wait_for_timeout(2000)

        # 1. Base home page
        html = await page.content()
        raw_bytes = html.encode("utf-8")
        fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        results.append(("Home", FetchResult(
            requested_url=base_url,
            final_url=page.url,
            content_type="text/html",
            body=raw_bytes,
            fetched_at=fetched_at,
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
        )))

        # 2. Iterate tabs
        for tab in tabs:
            try:
                locator = page.locator(f"text={tab}").first
                if await locator.is_visible():
                    await locator.click()
                    await page.wait_for_timeout(1500)
                    tab_html = await page.content()
                    tab_bytes = tab_html.encode("utf-8")
                    tab_fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                    results.append((tab, FetchResult(
                        requested_url=f"{base_url}#{tab.lower().replace(' ', '_')}",
                        final_url=page.url,
                        content_type="text/html",
                        body=tab_bytes,
                        fetched_at=tab_fetched_at,
                        sha256=hashlib.sha256(tab_bytes).hexdigest(),
                    )))
            except Exception as e:
                print(f"Warning: could not click tab {tab}: {e}")

        await browser.close()

    return results


def fetch_page_with_requests(
    url: str,
    allowed_hosts: set[str],
    timeout_seconds: int = 30,
) -> FetchResult:
    """Fetch using requests with strict TLS and DNS checks."""
    host = _validate_https_url(url, allowed_hosts)
    _validate_public_dns(host, socket.getaddrinfo)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
    })

    resp = session.get(url, timeout=timeout_seconds, verify=True, allow_redirects=True)
    resp.raise_for_status()

    final_url = resp.url
    _validate_https_url(final_url, allowed_hosts)

    content_type = resp.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    raw_bytes = resp.content
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return FetchResult(
        requested_url=url,
        final_url=final_url,
        content_type=content_type,
        body=raw_bytes,
        fetched_at=fetched_at,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )


def register_dataset_in_manifest(
    *,
    manifest_path: Path,
    data_root: Path,
    dataset_id: str,
    relative_path: str,
    category: str,
    allowed_hosts: Sequence[str],
) -> None:
    """Safely register or update dataset spec in rag_manifest.json."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = CorpusManifest.model_validate(payload)

    # Safely replace any prior spec for this site_id or append new
    site_prefix = dataset_id.rsplit("_", 1)[0]
    updated_datasets = [spec for spec in manifest.datasets if not spec.id.startswith(f"{site_prefix}_") and spec.id != dataset_id] + [
        DatasetSpec(
            id=dataset_id,
            path=relative_path,
            category=category,
            allowed_hosts=sorted(set(allowed_hosts)),
        )
    ]
    updated = CorpusManifest(schema_version=manifest.schema_version, datasets=updated_datasets)
    updated_bytes = (json.dumps(updated.model_dump(), indent=2) + "\n").encode("utf-8")

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(manifest_path, updated_bytes)
    print(f"Registered {dataset_id} in {manifest_path.name}")


async def process_portal(
    portal_key: str,
    *,
    data_root: Path = DATA_DIR,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, object]:
    """Crawl, extract, refine, and register one official government portal."""
    if portal_key not in PORTAL_SPECS:
        raise ValueError(f"Unknown portal key: {portal_key}. Available: {list(PORTAL_SPECS.keys())}")

    spec = PORTAL_SPECS[portal_key]
    site_id = spec["site_id"]
    allowed_hosts = set(spec["allowed_hosts"])
    category = spec["category"]
    tags = spec["tags"]
    source_authority = spec["source_authority"]
    jurisdiction = spec["jurisdiction"]
    document_type = spec["document_type"]
    scheme = spec["scheme"]
    use_browser = spec["use_browser"]
    seed_urls = spec["seed_urls"]

    print(f"\n=======================================================")
    print(f"Starting ingestion for portal: {portal_key.upper()} ({site_id})")
    print(f"Authority: {source_authority}")
    print(f"Category: {category} | Scheme: {scheme}")
    print(f"=======================================================")

    exact_fingerprints, simhashes = _existing_fingerprints(manifest_path=manifest_path, data_root=data_root)

    site_raw_dir = RAW_ROOT / site_id
    site_refined_dir = REFINED_ROOT / site_id
    site_raw_dir.mkdir(parents=True, exist_ok=True)
    site_refined_dir.mkdir(parents=True, exist_ok=True)

    all_site_records: list[ChunkRecord] = []
    extracted_pages: list[dict] = []
    seen_site_hashes: set[str] = set()

    # Special handling for Pension Sahayak tab traversal
    if portal_key == "pension_sahayak" and "sub_tabs" in spec:
        print("Traversing Pension Sahayak interactive tabs with browser automation...")
        tab_results = await fetch_pension_sahayak_tabs(seed_urls[0], allowed_hosts, spec["sub_tabs"])
        fetch_items = [(tab_title, res) for tab_title, res in tab_results]
    else:
        fetch_items = []
        for url in seed_urls:
            print(f"Fetching: {url}")
            is_pdf_url = url.lower().endswith(".pdf") or "download=true" in url.lower() or "pdf" in url.lower()
            try:
                if is_pdf_url:
                    # PDF documents are fetched natively via requests to stream clean binary bytes
                    fetch_result = fetch_page_with_requests(url, allowed_hosts)
                elif use_browser:
                    fetch_result = await fetch_page_with_browser(url, allowed_hosts)
                else:
                    try:
                        fetch_result = fetch_page_with_requests(url, allowed_hosts)
                    except Exception as req_exc:
                        print(f"Requests failed ({req_exc}), falling back to browser...")
                        fetch_result = await fetch_page_with_browser(url, allowed_hosts)
                fetch_items.append((None, fetch_result))
            except Exception as exc:
                print(f"[ERROR] Failed to fetch {url}: {exc}")
                continue

    for tab_label, fetch_result in fetch_items:
        version_id = fetch_result.sha256
        if version_id in seen_site_hashes:
            print(f"Skipping duplicate content {version_id[:12]}")
            continue
        seen_site_hashes.add(version_id)

        # 1. Extract text
        try:
            title, text, extension = extract_portal_text(fetch_result)
            if tab_label:
                title = f"{title} - {tab_label}"
        except Exception as exc:
            print(f"[ERROR] Failed to extract text from {fetch_result.final_url}: {exc}")
            continue

        words = len(text.split())
        print(f"Extracted: '{title}' ({words} words)")
        if words < MIN_CHUNK_WORDS:
            print(f"Skipping: text has fewer than {MIN_CHUNK_WORDS} words")
            continue

        # 2. Save raw artifacts
        page_raw_dir = site_raw_dir / version_id
        page_raw_dir.mkdir(parents=True, exist_ok=True)
        raw_file = page_raw_dir / f"body{extension}"
        meta_file = page_raw_dir / "metadata.json"

        meta = {
            "schema_version": 1,
            "site_id": site_id,
            "requested_url": fetch_result.requested_url,
            "final_url": fetch_result.final_url,
            "fetched_at": fetch_result.fetched_at,
            "artifact_sha256": fetch_result.sha256,
            "artifact_bytes": len(fetch_result.body),
            "content_type": fetch_result.content_type,
            "extracted_title": title,
            "extracted_words": words,
            "source_authority": source_authority,
            "jurisdiction": jurisdiction,
            "scheme": scheme,
            "document_type": document_type,
        }
        _atomic_write(raw_file, fetch_result.body)
        _atomic_write(meta_file, (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))

        # 3. Refine into ChunkRecords
        page_records, stats = build_records(
            source_id=f"{site_id}_{version_id[:8]}",
            category=category,
            title=f"{spec['title_prefix']}{title}",
            text=text,
            source_url=fetch_result.final_url,
            fetched_date=fetch_result.fetched_at[:10],
            tags=tags,
            source_authority=source_authority,
            publication_date=None,
            effective_from=None,
            jurisdiction=jurisdiction,
            scheme=scheme,
            document_type=document_type,
            supersedes=(),
            existing_exact=exact_fingerprints,
            existing_simhashes=simhashes,
        )
        print(f"  Chunking stats: {stats}")
        all_site_records.extend(page_records)

        for r in page_records:
            norm = _normalize_text(r.text)
            exact_fingerprints.add(norm)
            simhashes.append(_simhash(norm))

        extracted_pages.append({
            "url": fetch_result.final_url,
            "title": title,
            "words": words,
            "chunks": len(page_records),
            "sha256": version_id,
        })

    if not all_site_records:
        raise IngestionError(f"No valid records produced for portal {site_id}")

    # 4. Save consolidated refined dataset for this portal
    combined_hash = hashlib.sha256(
        "".join(r.id for r in all_site_records).encode("utf-8")
    ).hexdigest()
    dataset_id = f"{site_id}_{combined_hash[:12]}"
    refined_filename = f"{combined_hash}.jsonl"
    refined_file = site_refined_dir / refined_filename

    jsonl_bytes = "".join(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"
        for record in all_site_records
    ).encode("utf-8")
    _atomic_write(refined_file, jsonl_bytes)
    print(f"\nWrote {len(all_site_records)} refined chunks to {refined_file.name}")

    # 5. Register in rag_manifest.json
    relative_refined_path = refined_file.resolve().relative_to(data_root.resolve()).as_posix()
    register_dataset_in_manifest(
        manifest_path=manifest_path,
        data_root=data_root,
        dataset_id=dataset_id,
        relative_path=relative_refined_path,
        category=category,
        allowed_hosts=sorted(allowed_hosts),
    )

    return {
        "portal_key": portal_key,
        "site_id": site_id,
        "dataset_id": dataset_id,
        "refined_path": relative_refined_path,
        "total_chunks": len(all_site_records),
        "pages_processed": len(extracted_pages),
        "extracted_pages": extracted_pages,
    }


def main():
    parser = argparse.ArgumentParser(description="Ingest authoritative official portals one by one.")
    parser.add_argument("--site", choices=list(PORTAL_SPECS.keys()) + ["all"], required=True,
                        help="Portal key to ingest: uidai, eci, incometax, etc., or all")
    args = parser.parse_args()

    sites_to_run = list(PORTAL_SPECS.keys()) if args.site == "all" else [args.site]
    results = {}

    for site_key in sites_to_run:
        try:
            res = asyncio.run(process_portal(site_key))
            results[site_key] = {"status": "ok", **res}
        except Exception as exc:
            print(f"[FATAL ERROR] Ingestion failed for {site_key}: {exc}")
            results[site_key] = {"status": "error", "error": str(exc)}
            sys.exit(1)

    print("\n=======================================================")
    print("Ingestion Summary:")
    print(json.dumps(results, indent=2))
    print("=======================================================")


if __name__ == "__main__":
    main()

p = 'backend/pipeline.py'
with open(p, 'r', encoding='utf-8') as f:
    text = f.read()

old = """    if entry_id == "pm_kisan_scheme":
        kisan_tokens = ("kisan", "pmkisan", "farmer", "agriculture", "crop", "landholding")
        if not any(token in lowered for token in kisan_tokens):
            return False
    return True"""

new = """    if entry_id == "pm_kisan_scheme":
        kisan_tokens = ("kisan", "pmkisan", "farmer", "agriculture", "crop", "landholding")
        if not any(token in lowered for token in kisan_tokens):
            return False
    if entry_id == "loan_agreement_review":
        loan_tokens = ("loan", "emi", "borrower", "lender", "foreclosure", "prepayment")
        if not any(token in lowered for token in loan_tokens):
            return False
    if entry_id == "consumer_complaint_basics":
        consumer_tokens = ("consumer", "edaakhil", "defective", "unfair trade", "deficiency")
        if not any(token in lowered for token in consumer_tokens):
            return False
    return True"""

if old in text:
    text = text.replace(old, new)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)
    print("Patched pipeline.py successfully")
else:
    print("Old text not found in pipeline.py")

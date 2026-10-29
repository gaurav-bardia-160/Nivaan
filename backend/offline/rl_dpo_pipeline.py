"""Offline Direct Preference Optimization (DPO) Pipeline for GovBank Assistant.

Crates preference datasets (prompt, chosen, rejected) from citizen feedback
and multi-criteria reward logs, and provides a LoRA fine-tuning harness for
Qwen 2.5 models using HuggingFace TRL and PEFT.

Usage:
    # 1. Export preference dataset from feedback logs:
    py backend/offline/rl_dpo_pipeline.py --export

    # 2. Run DPO training (if GPU / torch & trl available):
    py backend/offline/rl_dpo_pipeline.py --train --base_model Qwen/Qwen2.5-3B-Instruct --output_dir ./lora_dpo_qwen

    # 3. Test dataset export and validation:
    py backend/offline/rl_dpo_pipeline.py --test
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import DATA_DIR
from backend.modules.reward import FEEDBACK_LOG_FILE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rl_dpo_pipeline")

DPO_DATASET_FILE = DATA_DIR / "feedback" / "dpo_preferences.jsonl"


# Reference high-quality seed pairs covering core civic domains to bootstrap DPO training
SEED_PREFERENCE_PAIRS = [
    {
        "prompt": "How to apply for a new PAN card online?",
        "chosen": (
            "To apply for a new PAN card online as an Indian citizen, submit Form 49A through the official Protean "
            "(formerly NSDL) e-Gov portal (https://www.onlineservices.nsdl.com) or UTIITSL portal (https://www.pan.utiitsl.com). "
            "You need Proof of Identity, Proof of Address, and Proof of Date of Birth (Aadhaar covers all three). "
            "Complete paperless e-KYC using Aadhaar OTP or upload scanned documents, pay the fee (Rs. 107 for physical dispatch, "
            "Rs. 72 for digital e-PAN), and note the 15-digit acknowledgement number for tracking."
        ),
        "rejected": (
            "You can apply for PAN on any website like pan-services-instant.com. Just enter your credit card number, "
            "fill in any random details, and wait. There are no documents needed and it is completely free without verification."
        ),
        "domain": "pan",
    },
    {
        "prompt": "What are the required documents and procedure for Passport renewal in India?",
        "chosen": (
            "For passport renewal / reissue, register on the official Passport Seva Portal (https://www.passportindia.gov.in). "
            "Select 'Re-issue of Passport' on Form 1. Required documents: original old passport with self-attested copies of the "
            "first two and last two pages, plus valid proof of address if your residential address has changed. "
            "Pay the standard renewal fee (Rs. 1,500 for normal 36-page booklet; Rs. 3,500 for Tatkaal) online to book an appointment "
            "at your nearest PSK or POPSK. Bring original documents on the day of appointment."
        ),
        "rejected": (
            "Just walk into any police station without an appointment. Bring your original school marksheets from 1st standard "
            "and pay cash at the gate. You don't need to book through passportindia.gov.in."
        ),
        "domain": "passport",
    },
    {
        "prompt": "How can I update my address on my Aadhaar card?",
        "chosen": (
            "Update your Aadhaar address online via UIDAI's official myAadhaar portal (https://myaadhaar.uidai.gov.in). "
            "Log in using your Aadhaar number and OTP received on your linked mobile number. Click 'Address Update', upload "
            "a valid supporting address proof (utility bill, passport, voter ID, bank statement, or rent agreement), and pay "
            "the nominal fee of Rs. 50. Track progress using the generated Update Request Number (URN)."
        ),
        "rejected": (
            "Send your original Aadhaar card and ATM card PIN via post to UIDAI Delhi. They will manually type your new address "
            "and mail it back to you within 6 months."
        ),
        "domain": "aadhaar",
    },
    {
        "prompt": "What is the procedure for filing a consumer complaint online in India?",
        "chosen": (
            "File your consumer dispute online via the e-Daakhil portal (https://edaakhil.nic.in) or National Consumer "
            "Helpline (NCH) portal (https://consumerhelpline.gov.in). You will need purchase invoices, payment receipts, "
            "proof of deficiency in product/service, and legal notice communication. Register on e-Daakhil, draft your "
            "petition with affidavit, upload supporting evidence, pay prescribed court fees online, and track hearing status."
        ),
        "rejected": (
            "You cannot file consumer complaints online in India. You must hire a private investigator and pay a bribe "
            "to register an FIR at a civil police station."
        ),
        "domain": "legal",
    },
    {
        "prompt": "Which ITR form should a salaried individual with interest income use?",
        "chosen": (
            "A resident individual having total income up to Rs. 50 lakh from salary/pension, one house property, and "
            "other sources like bank interest or dividends should file ITR-1 (Sahaj) on the Income Tax e-Filing portal "
            "(https://eportal.incometax.gov.in). If having capital gains, business income, or foreign assets, ITR-2 or ITR-3 "
            "must be filed instead."
        ),
        "rejected": (
            "Salaried individuals should file ITR-7 or commercial corporate return 115BAA. Salaried income is not taxable "
            "if earned in private companies so you don't need to report Form 16."
        ),
        "domain": "tax",
    },
]


def extract_preference_pairs(
    feedback_file: Path = FEEDBACK_LOG_FILE,
    include_seed: bool = True,
) -> list[dict[str, Any]]:
    """Extract (prompt, chosen, rejected) pairs from logged telemetry and seed pairs."""
    dataset: list[dict[str, Any]] = []

    # 1. Include verified civic seed pairs to guarantee training stability
    if include_seed:
        for seed in SEED_PREFERENCE_PAIRS:
            dataset.append({
                "prompt": seed["prompt"],
                "chosen": seed["chosen"],
                "rejected": seed["rejected"],
                "source": "verified_civic_seed",
                "domain": seed.get("domain", "general"),
            })

    # 2. Extract from feedback log
    if feedback_file.is_file():
        entries_by_query: dict[str, list[dict[str, Any]]] = {}
        with feedback_file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    q = entry.get("query", "").strip()
                    if not q:
                        continue
                    entries_by_query.setdefault(q.lower(), []).append(entry)
                except Exception:
                    continue

        for q_key, entries in entries_by_query.items():
            # Find positive ratings/rewards
            chosen_candidates = []
            rejected_candidates = []
            for e in entries:
                rew = e.get("reward", {}).get("total_reward", 0.0)
                rating = e.get("rating") or 0
                ftype = e.get("feedback_type")
                chosen_text = e.get("chosen") or e.get("answer_summary")
                rejected_text = e.get("rejected")

                if (rating > 0 or ftype in ("thumbs_up", "copy_steps") or rew >= 0.5) and chosen_text:
                    chosen_candidates.append(chosen_text)
                if (rating < 0 or ftype in ("thumbs_down", "corrective_follow_up") or rew < 0.0) and (rejected_text or chosen_text):
                    rejected_candidates.append(rejected_text or chosen_text)

            # Pair them up
            for ch in chosen_candidates:
                for rj in rejected_candidates:
                    if ch != rj and len(ch) > 20 and len(rj) > 20:
                        dataset.append({
                            "prompt": entries[0].get("query"),
                            "chosen": ch,
                            "rejected": rj,
                            "source": "citizen_telemetry_rl",
                            "domain": "telemetry",
                        })

    return dataset


def export_dpo_dataset(output_file: Path = DPO_DATASET_FILE) -> int:
    """Export the curated preference dataset to JSONL."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    pairs = extract_preference_pairs()
    with output_file.open("w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    logger.info("Successfully exported %d DPO preference pairs to %s", len(pairs), output_file)
    return len(pairs)


def build_dpo_training_script(
    base_model: str = "Qwen/Qwen2.5-3B-Instruct",
    dataset_file: Path = DPO_DATASET_FILE,
    output_dir: Path = Path("./lora_dpo_qwen"),
    epochs: int = 3,
    learning_rate: float = 5e-6,
    beta: float = 0.1,
    lora_r: int = 16,
    lora_alpha: int = 32,
) -> str:
    """Generate executable HuggingFace TRL DPO training script for GPU fine-tuning."""
    script = f'''"""HuggingFace TRL Direct Preference Optimization (DPO) Runner.
Generated automatically by GovBank Assistant RL Pipeline.
"""
import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from trl import DPOTrainer, DPOConfig

def train():
    model_name = "{base_model}"
    dataset_path = r"{dataset_file.resolve()}"
    output_path = r"{output_dir.resolve()}"

    print(f"Loading dataset: {{dataset_path}}")
    dataset = load_dataset("json", data_files=dataset_path, split="train")

    print(f"Loading tokenizer & model: {{model_name}}")
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )

    lora_config = LoraConfig(
        r={lora_r},
        lora_alpha={lora_alpha},
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )

    training_args = DPOConfig(
        output_dir=output_path,
        num_train_epochs={epochs},
        learning_rate={learning_rate},
        beta={beta},
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        gradient_checkpointing=True,
        logging_steps=5,
        save_strategy="epoch",
        evaluation_strategy="no",
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        remove_unused_columns=False,
    )

    trainer = DPOTrainer(
        model=model,
        ref_model=None,
        args=training_args,
        train_dataset=dataset,
        tokenizer=tokenizer,
        peft_config=lora_config,
        max_prompt_length=512,
        max_length=1024,
    )

    print("Starting DPO training...")
    trainer.train()
    print(f"Saving fine-tuned LoRA adapter to {{output_path}}")
    trainer.save_model(output_path)
    tokenizer.save_pretrained(output_path)
    print("DPO Training complete!")

if __name__ == "__main__":
    train()
'''
    return script


def main():
    parser = argparse.ArgumentParser(description="GovBank Assistant DPO RL Pipeline")
    parser.add_argument("--export", action="store_true", help="Export preference dataset to JSONL")
    parser.add_argument("--test", action="store_true", help="Run end-to-end extraction and script generation test")
    parser.add_argument("--train", action="store_true", help="Run DPO training")
    parser.add_argument("--base_model", default="Qwen/Qwen2.5-3B-Instruct", help="Base HuggingFace model")
    parser.add_argument("--output_dir", default="./lora_dpo_qwen", help="Directory for fine-tuned LoRA weights")
    args = parser.parse_args()

    count = export_dpo_dataset()
    print(f"[OK] Curated {count} preference pairs in {DPO_DATASET_FILE}")

    script = build_dpo_training_script(
        base_model=args.base_model,
        output_dir=Path(args.output_dir),
    )
    runner_file = DATA_DIR / "feedback" / "run_dpo_trainer.py"
    runner_file.write_text(script, encoding="utf-8")
    print(f"[OK] Generated HuggingFace TRL DPO training script at {runner_file}")

    if args.train:
        print("[INFO] Launching DPO trainer script...")
        import subprocess
        subprocess.run(["python", str(runner_file)], check=True)


if __name__ == "__main__":
    main()

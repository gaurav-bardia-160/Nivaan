"""HuggingFace TRL Direct Preference Optimization (DPO) Runner.
Generated automatically by GovBank Assistant RL Pipeline.
"""
import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from trl import DPOTrainer, DPOConfig

def train():
    model_name = "Qwen/Qwen2.5-3B-Instruct"
    dataset_path = r"C:\Users\gaura\Documents\govbank-assistant\backend\data\feedback\dpo_preferences.jsonl"
    output_path = r"C:\Users\gaura\Documents\govbank-assistant\lora_dpo_qwen"

    print(f"Loading dataset: {dataset_path}")
    dataset = load_dataset("json", data_files=dataset_path, split="train")

    print(f"Loading tokenizer & model: {model_name}")
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
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )

    training_args = DPOConfig(
        output_dir=output_path,
        num_train_epochs=3,
        learning_rate=5e-06,
        beta=0.1,
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
    print(f"Saving fine-tuned LoRA adapter to {output_path}")
    trainer.save_model(output_path)
    tokenizer.save_pretrained(output_path)
    print("DPO Training complete!")

if __name__ == "__main__":
    train()

import logging
from backend.modules.llm import generate_llm_response

logger = logging.getLogger(__name__)

DISCRIMINATOR_FAILURE_PHRASE = "Live search failed to extract the procedural text from the official portal."

def is_navigation_or_boilerplate_text(text: str) -> bool:
    """
    Heuristic pre-filter to catch obvious DOM noise before burning LLM tokens.
    Saves RAM and latency on constrained hardware.
    """
    if not text or len(text.strip()) < 150:
        return True

    noise_keywords = [
        "skip to navigation", "skip to main content", "screen reader access",
        "terms and conditions", "all rights reserved", "enable javascript", 
        "cookie policy", "privacy policy", "toggle navigation"
    ]
    
    text_lower = text.lower()
    noise_count = sum(1 for keyword in noise_keywords if keyword in text_lower)
    
    # Reject if the text is drowning in standard web template noise
    if noise_count >= 3:
        return True
        
    return False

def discriminate_content(query: str, scraped_text: str) -> str:
    """
    Evaluates scraped web text. Rejects navigation/boilerplate noise, 
    or extracts the clean procedural payload if relevant.
    """
    if is_navigation_or_boilerplate_text(scraped_text):
        logger.warning("Discriminator: Heuristic caught boilerplate noise. Rejecting.")
        return DISCRIMINATOR_FAILURE_PHRASE

    # Hard-capped at ~4000 characters to prevent OOM on 6GB RAM
    truncated_text = scraped_text[:4000]

    prompt = f"""You are a strict Data Discriminator for an Indian Civic AI.
        
User Query: "{query}"

Scraped Text:
\"\"\"
{truncated_text}
\"\"\"

Task: Evaluate the scraped text. 
If it primarily consists of website navigation menus, homepage popups, irrelevant links, terms and conditions, or generic policy disclaimers, AND lacks specific, actionable procedural steps to answer the User Query, you must reject it.

If rejected, output EXACTLY this phrase and nothing else: "{DISCRIMINATOR_FAILURE_PHRASE}"

If approved, extract and output ONLY the clean, relevant procedural steps and statutory rules from the text. Do not add conversational filler.
"""
    
    try:
        response = generate_llm_response(prompt).strip()
    except Exception as e:
        logger.error(f"Discriminator LLM failed: {e}")
        return DISCRIMINATOR_FAILURE_PHRASE
    
    if DISCRIMINATOR_FAILURE_PHRASE in response:
        logger.warning("Discriminator: LLM rejected the scraped content.")
        return DISCRIMINATOR_FAILURE_PHRASE
        
    return response

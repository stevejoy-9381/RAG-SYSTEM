"""
src/llm.py — LLM Configuration and Prompt Template
────────────────────────────────────────────────────
WHAT THIS FILE DOES:
  Sets up the Groq LLM client and defines the prompt template that tells
  the LLM exactly how to behave when answering questions from document chunks.

WHY A SEPARATE FILE?
  Prompt engineering is its own concern. Keeping it separate means:
    - You can swap LLM providers without touching retriever.py
    - You can iterate on the prompt without touching anything else
    - Interviewers see clean architecture when they read your code

CONNECTIONS:
  → Imported by src/retriever.py which passes the LLM and prompt
    into the LangChain RetrievalQA chain.
"""

import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain.prompts import PromptTemplate

# Load GROQ_API_KEY from .env file
load_dotenv()


def get_llm() -> ChatGroq:
    """
    Create and return a Groq LLM client.

    WHY GROQ?
      - Free tier: 14,400 requests/day, no credit card for signup
      - Fast: Groq runs on custom LPU hardware → ~500 tokens/second
        (OpenAI GPT-4 is ~50 tokens/second for comparison)
      - Llama3-8B quality: very good for factual Q&A from context

    WHY temperature=0.2?
      Temperature controls randomness:
        0.0 → always picks the most likely next token (fully deterministic)
        1.0 → very creative/random
        0.2 → mostly deterministic with tiny variance
      For a Q&A system grounded in documents, low temperature = factual answers.
      We do NOT want the model being "creative" — we want it to report facts.

    COMMON ERROR:
      AuthenticationError → your GROQ_API_KEY is missing or wrong.
      Fix: check your .env file has the correct key from console.groq.com
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GROQ_API_KEY not found. "
            "Did you create a .env file from .env.example?"
        )

    model_name = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    llm = ChatGroq(
        api_key=api_key,
        model=model_name,
        temperature=temperature,
    )
    print(f"[LLM] Using Groq model: {model_name} (temperature={temperature})")
    return llm


def get_prompt_template() -> PromptTemplate:
    """
    Build and return the prompt template for grounded Q&A.

    WHAT IS A PROMPT TEMPLATE?
      A PromptTemplate is a reusable string with {placeholders}.
      LangChain fills in {context} (retrieved chunks) and {question}
      (user's question) before sending to the LLM.

    WHY THIS SPECIFIC PROMPT DESIGN?

      1. "Use ONLY the context below"
         → Prevents hallucination. The LLM is instructed not to use its
           training data — only what we retrieved from the document.

      2. 'If the answer is not in the context, say "I don't know"'
         → This is critical. Without this line, the LLM invents an answer.
           With it, the system admits uncertainty. Trust > fake confidence.

      3. "Be concise and cite the relevant section if possible."
         → Encourages source grounding in the answer text itself.

      4. "Context:" before the chunks
         → Clear signal to the model about where the document text starts.

    THE {context} PLACEHOLDER:
      LangChain automatically fills this with the 4 retrieved chunks,
      joined together as one string. Each chunk includes its metadata
      (page number, source) so the model can reference them.

    THE {question} PLACEHOLDER:
      Filled with whatever the user typed in the Streamlit text box.
    """
    template = """You are a precise document Q&A assistant.

Your job is to answer the user's question using ONLY the context provided below.
Do NOT use any knowledge from outside this context.
If the answer is not present in the context, respond with:
"I don't know — the answer is not in the provided document."

Context:
────────────────────────────────────
{context}
────────────────────────────────────

Question: {question}

Instructions:
- Answer directly and concisely.
- If the answer spans multiple sections, combine them clearly.
- If you reference a specific fact, mention which part of the context it came from.
- Do not make up information.

Answer:"""

    prompt = PromptTemplate(
        template=template,
        input_variables=["context", "question"],
    )
    return prompt

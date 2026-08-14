#!/usr/bin/env python3
"""One-shot DeepSeek swap across all fleet agents.

Idempotent. Skips files already swapped. Prints a per-file change summary.
"""
import re
import sys
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"
DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = 'os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")'

# 1) Universal ChatOpenAI swap (gpt-4o / gpt-4o-mini, any temperature)
CHAT_PAT = re.compile(
    r'ChatOpenAI\(model="gpt-4o(?:-mini)?",\s*temperature=([0-9.]+)\)'
)
CHAT_REPL = (
    f'ChatOpenAI(model={DEEPSEEK_MODEL}, temperature=\\1, '
    f'base_url="{DEEPSEEK_BASE}", api_key=os.getenv("DEEPSEEK_API_KEY"))'
)

changed = []


def chat_swap(text: str) -> str:
    return CHAT_PAT.sub(CHAT_REPL, text)


for agent_dir in sorted(AGENTS_DIR.iterdir()):
    if not agent_dir.is_dir():
        continue
    f = agent_dir / "agent.py"
    if not f.exists():
        continue
    name = agent_dir.name
    orig = f.read_text(encoding="utf-8")
    new = orig

    if "ChatOpenAI(" in orig:
        new = chat_swap(new)

    # 03-pdf-qa: llama-index OpenAI LLM -> DeepSeek + local embeddings
    if name == "03-pdf-qa-agent":
        new = new.replace(
            "from llama_index.core import SimpleDirectoryReader, VectorStoreIndex",
            "from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, Settings",
        )
        new = new.replace(
            "from llama_index.core.memory import ChatMemoryBuffer",
            "from llama_index.core.memory import ChatMemoryBuffer\n"
            "from llama_index.embeddings.huggingface import HuggingFaceEmbedding",
        )
        new = new.replace(
            'OpenAI(model="gpt-4o-mini", temperature=0)',
            f'OpenAI(model={DEEPSEEK_MODEL}, temperature=0, '
            f'api_base="{DEEPSEEK_BASE}", api_key=os.getenv("DEEPSEEK_API_KEY"))',
        )
        if "Settings.embed_model" not in new:
            new = new.replace(
                "load_dotenv()\n",
                'load_dotenv()\n\n'
                'Settings.embed_model = HuggingFaceEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")\n',
                1,
            )

    # 13-customer-support: OpenAIEmbeddings -> local HuggingFaceEmbeddings
    if name == "13-customer-support-agent":
        new = new.replace(
            "from langchain_openai import ChatOpenAI, OpenAIEmbeddings",
            "from langchain_openai import ChatOpenAI\n"
            "from langchain_huggingface import HuggingFaceEmbeddings",
        )
        new = new.replace(
            "embeddings = OpenAIEmbeddings()",
            'embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")',
        )

    if new != orig:
        f.write_text(new, encoding="utf-8")
        changed.append(name)

# .env.example updates
for env_file in sorted(AGENTS_DIR.glob("*/.env.example")):
    orig = env_file.read_text(encoding="utf-8")
    new = orig
    if "OPENAI_API_KEY" in new and "DEEPSEEK_API_KEY" not in new:
        new = new.replace(
            "OPENAI_API_KEY=your_openai_api_key_here",
            "DEEPSEEK_API_KEY=your_deepseek_api_key_here  # already in Windows env, optional",
        )
    if new != orig:
        env_file.write_text(new, encoding="utf-8")

print("CHANGED AGENTS:")
for c in changed:
    print("  -", c)
print(f"\nTotal changed: {len(changed)}")

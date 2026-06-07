import httpx
import asyncio

paper_ids = [
    "2005.14165",  # GPT-3
    "2010.11929",  # ViT
    "2006.11239",  # DDPM
    "2103.00020",  # CLIP
    "2302.13971",  # LLaMA
    "2305.10403",  # QLoRA
    "2106.09685",  # LoRA
    "1810.04805",  # BERT
    "2204.02311",  # PaLM
    "2307.09288",  # LLaMA 2
]


async def download(client, paper_id):
    url = f"https://arxiv.org/pdf/{paper_id}.pdf"
    response = await client.get(url, follow_redirects=True)
    with open(f"data/{paper_id}.pdf", "wb") as pdf_file:
        pdf_file.write(response.content)
    print(f"Downloaded {paper_id}")


async def main():
    async with httpx.AsyncClient() as client:
        tasks = [download(client, paper_id) for paper_id in paper_ids]
        await asyncio.gather(*tasks)


asyncio.run(main())

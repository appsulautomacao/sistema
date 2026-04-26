# ai/classifier.py
import os
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

SECTORS = [
    "vendas",
    "financeiro",
    "compras",
    "suporte",
    "outro"
]

def classify_sector(text):
    """
    Retorna um dos setores definidos em SECTORS.
    """
    if not text or len(text.strip()) < 5:
        return "outro"

    prompt = f"""
Você é um classificador de mensagens para um sistema de atendimento.

Classifique a mensagem abaixo em apenas UM dos setores:

{", ".join(SECTORS)}

Mensagem:
\"{text}\"

Responda somente com o nome do setor.
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Você classifica mensagens em setores de atendimento."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )

        sector = response.choices[0].message["content"].strip().lower()

        if sector not in SECTORS:
            return "outro"

        return sector

    except Exception as e:
        print("Erro IA:", e)
        return "outro"

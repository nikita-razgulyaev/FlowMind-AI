# FlowMind AI

## Быстрый старт

### Хостинг с Hugging Face

1. Получи токен: https://huggingface.co/settings/tokens
2. Создай `.env`:
```env
HF_TOKEN=hf_your_token
HF_MODEL=Qwen/Qwen2.5-1.5B-Instruct
CLOUD_PROVIDER=huggingface
LLM_MODE=cloud
```

### Локально с Ollama

```bash
git clone https://github.com/nikita-razgulyaev/FlowMind-AI.git
cd FlowMind-AI
docker compose up --build -d
docker compose exec ollama ollama pull llama3
```

Frontend: http://localhost 
<br>
API Docs: http://localhost:8000/docs

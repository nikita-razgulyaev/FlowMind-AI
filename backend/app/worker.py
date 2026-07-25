import asyncio
import httpx
import os


class LLMProvider:
    """Выбирает LLM-провайдер в зависимости от настроек узла"""
    
    def __init__(self):
        self.mode = os.getenv("LLM_MODE", "local")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3")
        self.hf_token = os.getenv("HF_TOKEN")
        self.hf_model = os.getenv("HF_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
        self.cloud_provider = os.getenv("CLOUD_PROVIDER", "huggingface")
    
    async def generate(self, prompt: str, model: str = None, temperature: float = 0.7, mode: str = None) -> str:
        effective_mode = mode or self.mode
        
        if effective_mode == "local":
            return await self._ollama_generate(prompt, model or self.ollama_model, temperature)
        elif effective_mode == "cloud":
            return await self._cloud_generate(prompt, model or self.hf_model, temperature)
        else:
            raise ValueError(f"Unknown LLM_MODE: {effective_mode}")
    
    async def _cloud_generate(self, prompt: str, model: str, temperature: float) -> str:
        if self.cloud_provider == "huggingface":
            return await self._hf_generate(prompt, model, temperature)
        else:
            raise ValueError(f"Unknown CLOUD_PROVIDER: {self.cloud_provider}")
    
    async def _ollama_generate(self, prompt: str, model: str, temperature: float) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temperature}
                }
            )
            data = response.json()
            return data.get("response", "")
    
    async def _hf_generate(self, prompt: str, model: str, temperature: float) -> str:
        if not self.hf_token:
            raise ValueError("HF_TOKEN not set")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"https://api-inference.huggingface.co/models/{model}",
                headers={"Authorization": f"Bearer {self.hf_token}"},
                json={
                    "inputs": prompt,
                    "parameters": {
                        "max_new_tokens": 500,
                        "temperature": temperature,
                        "return_full_text": False
                    }
                }
            )
            
            if response.status_code == 503:
                print("Model loading, waiting 20s...")
                await asyncio.sleep(20)
                return await self._hf_generate(prompt, model, temperature)
            
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("generated_text", "").strip()
            
            return str(data)


class WorkflowEngine:
    def __init__(self, workflow, execution_id):
        self.workflow = workflow
        self.execution_id = execution_id
        self.context = {}
        self.logs = []
        self.llm = LLMProvider()
    
    async def execute(self, trigger_data=None):
        self.context["input"] = trigger_data or {}  # ← input для подстановки в шаблоны
        for node in self.workflow["nodes"]:
            result = await self._execute_node(node, trigger_data)
            self.context[node["id"]] = result
            self.logs.append({
                "node_id": node["id"],
                "type": node["type"],
                "input": node.get("config", {}),
                "output": result,
                "timestamp": str(asyncio.get_event_loop().time())
            })
        return self.context
    
    async def _execute_node(self, node, trigger_data):
        handlers = {
            "manual": self._handle_manual,
            "llm": self._handle_llm,
            "http": self._handle_http,
            "condition": self._handle_condition,
            "print": self._handle_print,
        }
        handler = handlers.get(node["type"])
        if not handler:
            return f"Unknown node type: {node['type']}"
        return await handler(node.get("config", {}), trigger_data)
    
    async def _handle_manual(self, config, trigger_data):
        return trigger_data or {}
    
    async def _handle_llm(self, config, td):
        prompt = self._render_template(config.get("prompt", ""))
        model = config.get("model")
        temperature = config.get("temperature", 0.7)
        mode = config.get("mode", "cloud")  # ← "cloud" по умолчанию
        
        try:
            return await self.llm.generate(prompt, model, temperature, mode)
        except Exception as e:
            return f"LLM Error: {str(e)}"
    
    async def _handle_http(self, config, td):
        async with httpx.AsyncClient() as client:
            try:
                method = config.get("method", "GET").upper()
                url = self._render_template(config.get("url", ""))

                # Проверяем, что URL валидный после рендеринга
                if not url or not url.startswith(("http://", "https://")):
                    return f"HTTP Error: Invalid URL after template rendering: '{url}'. Make sure to provide a valid URL or trigger data."

                if method == "GET":
                    response = await client.get(url)
                else:
                    response = await client.post(url)
                return {
                    "status_code": response.status_code,
                    "body": response.text[:1000]
                }
            except Exception as e:
                return f"HTTP Error: {str(e)}"
    
    async def _handle_condition(self, config, td):
        expression = self._render_template(config.get("expression", "True"))
        try:
            result = eval(expression, {"__builtins__": {}}, self.context)
            return result
        except:
            return False
    
    async def _handle_print(self, config, td):
        value = self._render_template(config.get("value", "{last_result}"))
        print(f"[FlowMind] {value}")
        return value
    
    def _render_template(self, template):
        result = template
        for key, value in self.context.items():
            placeholder = f"{{{key}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value)[:500])
        return result
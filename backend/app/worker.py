import asyncio
import httpx

class WorkflowEngine:
    def __init__(self, workflow, execution_id):
        self.workflow = workflow
        self.execution_id = execution_id
        self.context = {}
        self.logs = []
    
    async def execute(self, trigger_data=None):
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
            "manual": lambda c, td: td or {},
            "llm": self._handle_llm,
            "http": self._handle_http,
            "condition": self._handle_condition,
            "print": self._handle_print,
        }
        
        handler = handlers.get(node["type"])
        if not handler:
            return f"Unknown node type: {node['type']}"
        
        return await handler(node.get("config", {}), trigger_data)
    
    async def _handle_llm(self, config, td):
        prompt = self._render_template(config.get("prompt", ""))
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": config.get("model", "llama3"),
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": config.get("temperature", 0.7)}
                    }
                )
                data = response.json()
                return data.get("response", "")
            except Exception as e:
                return f"LLM Error: {str(e)}"
    
    async def _handle_http(self, config, td):
        async with httpx.AsyncClient() as client:
            try:
                method = config.get("method", "GET").upper()
                url = self._render_template(config.get("url", ""))
                
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
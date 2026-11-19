from openai import OpenAI

client = OpenAI(
    api_key="",
    base_url=""
    )

try:
    response = client.chat.completions.create(
        model="",
        messages=[{"role": "user", "content": "Привет! Как дела?"}],
        max_tokens=200  # Попробуйте увеличить, если модель "думает"
    )
    
    # Безопасная проверка: проверяем, что choices не пуст и message не None
    if response.choices and response.choices[0].message:
        content = response.choices[0].message.content
        if content:
            print(content)
        else:
            print("Ответ пустой. Вероятно, модель потратила токены на reasoning или сработал фильтр.")
            # Для диагностики можно вывести finish_reason
            print(f"Finish reason: {response.choices[0].finish_reason}") 
    else:
        print("API вернул пустой список choices. Проверьте ID модели и URL эндпоинта.")
        
except Exception as e:
    print(f"Ошибка запроса: {e}")
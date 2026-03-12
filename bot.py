from Class_ModelResponse import ModelResponse
import telebot
import requests
import json
import os
import tempfile
from pathlib import Path

# Configuration
API_TOKEN = 'Y8448287429:AAFz046kAfgaQDZLxd5ucn21SuyYzJJmrzw'
LM_STUDIO_URL = 'http://localhost:1234/v1/chat/completions'
CHATTERBOX_TTS_URL = 'http://localhost:8000/tts'  # Adjust if different

bot = telebot.TeleBot(API_TOKEN)

# User context storage
user_contexts = {}
user_tts_preferences = {}  # Track user preferences for TTS

# ModelResponse class definition
class ModelResponse:
    def __init__(self, id=None, choices=None, created=None, model=None, **kwargs):
        self.id = id
        self.choices = choices or []
        self.created = created
        self.model = model
        for key, value in kwargs.items():
            setattr(self, key, value)

class Message:
    def __init__(self, role=None, content=None, **kwargs):
        self.role = role
        self.content = content
        for key, value in kwargs.items():
            setattr(self, key, value)

class Choice:
    def __init__(self, finish_reason=None, index=None, message=None, **kwargs):
        self.finish_reason = finish_reason
        self.index = index
        self.message = message
        for key, value in kwargs.items():
            setattr(self, key, value)

# Helper function to load JSON into ModelResponse
def load_model_response(data):
    if isinstance(data, str):
        data = json.loads(data)
    
    choices = []
    for choice_data in data.get('choices', []):
        message_data = choice_data.get('message', {})
        message = Message(**message_data)
        choice = Choice(
            finish_reason=choice_data.get('finish_reason'),
            index=choice_data.get('index'),
            message=message
        )
        choices.append(choice)
    
    return ModelResponse(
        id=data.get('id'),
        choices=choices,
        created=data.get('created'),
        model=data.get('model')
    )

# TTS generation function
def generate_voice_message(text, voice="default"):
    """Convert text to speech using Chatterbox TTS"""
    try:
        response = requests.post(
            CHATTERBOX_TTS_URL,
            json={
                "text": text,
                "voice": voice,
                "model": "chatterbox"
            },
            timeout=30
        )
        
        if response.status_code == 200:
            # Create a temporary file for the audio
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                temp_file.write(response.content)
                return temp_file.name
        else:
            print(f"TTS Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"TTS generation failed: {e}")
        return None

# Commands
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "Приветствую.\n"
        "Это LMmangO_bot, я ботяра, с установленой языковой моделью, могу поговорить, используй эти команды:\n"
        "/start - вывод всех доступных команд\n"
        "/model - выводит название используемой языковой модели.\n"
        "/clear - очистка контекста чата.\n"
        "/voice - включить/выключить голосовые ответы\n"
        "/voices - список доступных голосов\n"
        "/voice_set <name> - установить голос (например: /voice_set default)"
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['model'])
def send_model_name(message):
    try:
        response = requests.get('http://localhost:1234/v1/models', timeout=10)
        
        if response.status_code == 200:
            model_info = response.json()
            if model_info.get('data'):
                model_name = model_info['data'][0]['id']
                bot.reply_to(message, f"Используемая модель: {model_name}")
            else:
                bot.reply_to(message, 'Информация о модели не найдена.')
        else:
            bot.reply_to(message, 'Не удалось получить информацию о модели.')
    except Exception as e:
        bot.reply_to(message, f'Ошибка подключения: {str(e)}')

@bot.message_handler(commands=['clear'])
def clear_context(message):
    user_id = message.from_user.id
    if user_id in user_contexts:
        del user_contexts[user_id]
    bot.reply_to(message, "Контекст успешно очищен!")

@bot.message_handler(commands=['voice'])
def toggle_voice(message):
    user_id = message.from_user.id
    if user_id not in user_tts_preferences:
        user_tts_preferences[user_id] = {'enabled': True, 'voice': 'default'}
    
    current = user_tts_preferences[user_id]['enabled']
    user_tts_preferences[user_id]['enabled'] = not current
    
    status = "включены" if not current else "выключены"
    bot.reply_to(message, f"Голосовые ответы {status}!")

@bot.message_handler(commands=['voices'])
def list_voices(message):
    # You can customize this list based on available Chatterbox voices
    voices_list = (
        "Доступные голоса:\n"
        "- default (стандартный)\n"
        "- Добавьте свои голоса в Chatterbox TTS\n"
        "Используйте: /voice_set <имя_голоса>"
    )
    bot.reply_to(message, voices_list)

@bot.message_handler(commands=['voice_set'])
def set_voice(message):
    user_id = message.from_user.id
    parts = message.text.split()
    
    if len(parts) < 2:
        bot.reply_to(message, "Использование: /voice_set <имя_голоса>")
        return
    
    voice_name = parts[1]
    
    if user_id not in user_tts_preferences:
        user_tts_preferences[user_id] = {'enabled': True, 'voice': voice_name}
    else:
        user_tts_preferences[user_id]['voice'] = voice_name
    
    bot.reply_to(message, f"Голос установлен на: {voice_name}")

# Main message handler
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    user_query = message.text
    
    # Skip if message starts with slash (it's a command)
    if user_query.startswith('/'):
        return
    
    # Initialize context for new users
    if user_id not in user_contexts:
        user_contexts[user_id] = []
    
    # Add user message to context
    user_contexts[user_id].append({"role": "user", "content": user_query})
    
    # Prepare request to LM Studio
    request = {
        "messages": user_contexts[user_id],
        "temperature": 0.7,
        "max_tokens": 500
    }
    
    try:
        # Get response from LM Studio
        response = requests.post(
            LM_STUDIO_URL,
            json=request,
            timeout=60
        )
        
        if response.status_code == 200:
            # Parse the response
            model_response = load_model_response(response.text)
            assistant_response = model_response.choices[0].message.content
            
            # Add assistant response to context
            user_contexts[user_id].append({
                "role": "assistant",
                "content": assistant_response
            })
            
            # Limit context history (keep last 10 exchanges)
            if len(user_contexts[user_id]) > 20:
                user_contexts[user_id] = user_contexts[user_id][-20:]
            
            # Check if user wants voice responses
            send_voice = user_tts_preferences.get(user_id, {}).get('enabled', False)
            
            if send_voice:
                # Get voice preference
                voice_name = user_tts_preferences.get(user_id, {}).get('voice', 'default')
                
                # Generate voice message
                voice_file = generate_voice_message(assistant_response, voice_name)
                
                if voice_file:
                    try:
                        # Send voice message
                        with open(voice_file, 'rb') as audio:
                            bot.send_voice(
                                message.chat.id,
                                audio,
                                caption="🤖"
                            )
                        # Also send text as fallback
                        bot.send_message(message.chat.id, assistant_response)
                    finally:
                        # Clean up temp file
                        if os.path.exists(voice_file):
                            os.unlink(voice_file)
                else:
                    # Fallback to text if TTS fails
                    bot.reply_to(message, assistant_response)
            else:
                # Send text only
                bot.reply_to(message, assistant_response)
                
        else:
            error_msg = f'Ошибка при обращении к модели: {response.status_code}'
            bot.reply_to(message, error_msg)
            
    except requests.exceptions.Timeout:
        bot.reply_to(message, 'Превышено время ожидания ответа от модели.')
    except Exception as e:
        bot.reply_to(message, f'Произошла ошибка: {str(e)}')

# Start the bot
if __name__ == '__main__':
    print("Бот запущен...")
    print("Убедитесь, что:")
    print("1. LM Studio сервер работает на http://localhost:1234")
    print("2. Chatterbox TTS работает на http://localhost:8000")
    print("3. Бот готов к работе в Telegram")
    
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Ошибка запуска бота: {e}")
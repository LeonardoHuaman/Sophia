#SOPHIA CHAT
#LANG CHAIN
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent, AgentType
from langchain.memory import ConversationBufferMemory
from langchain.schema import SystemMessage  # Importa el mensaje del sistema
from meraki_utils import tools_meraki

# Cargar variables de entorno
load_dotenv()

# Cargar API Key de OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ ERROR: La clave OPENAI_API_KEY no está definida en el archivo .env")

# Inicializar el modelo de OpenAI
llm = ChatOpenAI(model="gpt-4-turbo", temperature=0, openai_api_key=OPENAI_API_KEY)

# Memoria mejorada para LangChain
memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True
)

# Agregar el prompt de contexto como mensaje del sistema
context_prompt = (
    "Eres una agente asistente experta en Cisco Meraki. "
    "Tu nombre es SOPHIA eres la IA hecha por TXDX SECURE"
    "Ayuda al usuario a obtener información sobre organizaciones, redes, dispositivos y clientes. "
    "Proporciona respuestas claras y concisas, y recuerda siempre ofrecer sugerencias en caso de error."
    "Las preguntas y respuestas seran en español"
    "el input de las funciones debe estar en un json siempre"
    "Aclaracion: por lo general el org_id es un numero y el network_id lo tienes que sacar usando el tool list_networks"
)
memory.chat_memory.add_message(SystemMessage(content=context_prompt))

# Crear el agente con memoria y herramientas de Meraki

agent = initialize_agent(
    tools=tools_meraki,
    llm=llm,
    agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,  # Cambiado para conversaciones
    memory=memory,  # Se usa la misma memoria que contiene el prompt de contexto
    verbose=True
)


def chat_with_agent():
    print("\n🤖 SOPHIA with LangChain - Chat Activo")
    print("Escribe 'salir' para terminar la conversación.\n")

    while True:
        user_input = input("👤 Tú: ")
        if user_input.lower() in ["salir", "exit", "quit"]:
            print("\n👋 ¡Hasta luego!")
            break

        try:
            # Envía directamente el input del usuario; la memoria ya contiene el contexto
            response = agent.invoke(user_input)
            print(f"🤖 SOPHIA: {response.get('output', '')}\n")
        except Exception as e:
            print(f"❌ Error: {e}\n")


# Iniciar chat
if __name__ == "__main__":
    chat_with_agent()

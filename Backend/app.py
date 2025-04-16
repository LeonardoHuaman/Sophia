from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from Sophia import agent  # Importamos el agente de LangChain

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"], 
)

class UserInput(BaseModel):
    message: str

@app.post("/chat/")
def chat(user_input: UserInput):
    try:
        response = agent.invoke(user_input.message)
        print("Respuesta del agente:", response)
        if isinstance(response, dict):
            return {"response": response.get("output", "Error en la respuesta")}
        else:
            return {"response": str(response)}
    except Exception as e:
        print("Error en la API:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def root():
    return {"message": "Bienvenido a la API de SOPHIA"}
